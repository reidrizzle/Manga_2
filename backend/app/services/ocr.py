from __future__ import annotations

import base64
import json
from dataclasses import dataclass
from io import BytesIO

from PIL import Image, ImageOps

from ..config import get_settings


OCR_MAX_SIDE = 1800


@dataclass
class OCRBlock:
    original_text: str
    language: str
    text_type: str
    tone: str
    x: float
    y: float
    width: float
    height: float
    confidence: float
    reading_order: int


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _normalize_box(block: OCRBlock, image_width: int, image_height: int, sent_width: int, sent_height: int) -> OCRBlock:
    """Convert model coordinates into original-image pixels.

    Vision models sometimes ignore the requested coordinate convention.
    We support the three common forms without relying on image size:
      * 0..1 normalized coordinates
      * 0..1000 normalized coordinates
      * pixel coordinates on the sent image
    """
    x, y, w, h = float(block.x), float(block.y), float(block.width), float(block.height)

    # 0..1 coordinates.
    if max(x, y, w, h) <= 1.01 and max(x + w, y + h) <= 1.02:
        x *= sent_width
        y *= sent_height
        w *= sent_width
        h *= sent_height
    else:
        # If the box cannot physically fit inside the sent image, it is very
        # likely a 0..1000 normalized box even when the image itself is < 1000px.
        exceeds_image = (x + w > sent_width * 1.08) or (y + h > sent_height * 1.08)
        looks_like_1000 = max(x, y, w, h) <= 1000.0
        if exceeds_image and looks_like_1000:
            x = x / 1000.0 * sent_width
            y = y / 1000.0 * sent_height
            w = w / 1000.0 * sent_width
            h = h / 1000.0 * sent_height

    # Convert OCR-image coordinates back to original-image coordinates.
    sx = image_width / max(1, sent_width)
    sy = image_height / max(1, sent_height)
    x *= sx
    y *= sy
    w *= sx
    h *= sy

    x = _clamp(x, 0, max(0, image_width - 1))
    y = _clamp(y, 0, max(0, image_height - 1))
    w = _clamp(w, 1, max(1, image_width - x))
    h = _clamp(h, 1, max(1, image_height - y))

    return OCRBlock(
        original_text=block.original_text.strip(),
        language=block.language or "unknown",
        text_type=block.text_type if block.text_type in {"dialogue", "narration", "thought", "sfx"} else "dialogue",
        tone=block.tone or "neutral",
        x=x,
        y=y,
        width=w,
        height=h,
        confidence=_clamp(float(block.confidence), 0, 1),
        reading_order=int(block.reading_order),
    )


def _dedupe_blocks(blocks: list[OCRBlock]) -> list[OCRBlock]:
    """Remove obvious duplicate detections while keeping reading order."""
    result: list[OCRBlock] = []
    for block in sorted(blocks, key=lambda item: (item.reading_order, item.y, item.x)):
        if not block.original_text:
            continue
        duplicate = False
        for existing in result:
            x_overlap = max(0.0, min(block.x + block.width, existing.x + existing.width) - max(block.x, existing.x))
            y_overlap = max(0.0, min(block.y + block.height, existing.y + existing.height) - max(block.y, existing.y))
            intersection = x_overlap * y_overlap
            smaller = min(block.width * block.height, existing.width * existing.height)
            if smaller > 0 and intersection / smaller >= 0.88 and block.original_text.strip() == existing.original_text.strip():
                duplicate = True
                break
        if not duplicate:
            result.append(block)
    return result


class MockOCRProvider:
    def detect_text(self, image_bytes: bytes) -> list[OCRBlock]:
        with Image.open(BytesIO(image_bytes)) as im:
            im = ImageOps.exif_transpose(im)
            w, h = im.size
        return [
            OCRBlock(
                original_text="[ตัวอย่าง] ข้อความในภาพ",
                language="unknown",
                text_type="dialogue",
                tone="casual",
                x=w * 0.18,
                y=h * 0.10,
                width=w * 0.50,
                height=h * 0.13,
                confidence=0.88,
                reading_order=0,
            )
        ]


class OpenAIOCRProvider:
    def __init__(self) -> None:
        settings = get_settings()
        if not settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is not configured")
        from openai import OpenAI

        self.client = OpenAI(api_key=settings.openai_api_key)
        self.model = settings.openai_model

    def detect_text(self, image_bytes: bytes) -> list[OCRBlock]:
        # Always work from the same orientation used by the app.
        with Image.open(BytesIO(image_bytes)) as raw:
            im = ImageOps.exif_transpose(raw).convert("RGB")
            original_w, original_h = im.size
            sent = im.copy()

        if max(sent.size) > OCR_MAX_SIDE:
            scale = OCR_MAX_SIDE / max(sent.size)
            sent = sent.resize(
                (max(1, round(sent.width * scale)), max(1, round(sent.height * scale))),
                Image.Resampling.LANCZOS,
            )

        buf = BytesIO()
        sent.save(buf, format="JPEG", quality=88, optimize=True)
        encoded = base64.b64encode(buf.getvalue()).decode("utf-8")
        data_url = f"data:image/jpeg;base64,{encoded}"

        schema = {
            "type": "object",
            "properties": {
                "blocks": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "original_text": {"type": "string"},
                            "language": {"type": "string"},
                            "text_type": {"type": "string", "enum": ["dialogue", "narration", "thought", "sfx"]},
                            "tone": {"type": "string"},
                            "x": {"type": "number"},
                            "y": {"type": "number"},
                            "width": {"type": "number"},
                            "height": {"type": "number"},
                            "confidence": {"type": "number"},
                            "reading_order": {"type": "integer"},
                        },
                        "required": [
                            "original_text",
                            "language",
                            "text_type",
                            "tone",
                            "x",
                            "y",
                            "width",
                            "height",
                            "confidence",
                            "reading_order",
                        ],
                        "additionalProperties": False,
                    },
                }
            },
            "required": ["blocks"],
            "additionalProperties": False,
        }
        response = self.client.responses.create(
            model=self.model,
            store=False,
            input=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": (
                                "Analyze this manga/manhwa page and detect every readable text region. "
                                "For each region, return a tight bounding rectangle around the COMPLETE visible text. "
                                "Coordinates MUST be pixels on the image supplied in this request, measured from the "
                                "TOP-LEFT corner: x, y, width, height. Do not use 0..1 or 0..1000 normalized values. "
                                "Include punctuation and all visible glyphs. Do not merge separate speech balloons. "
                                "Classify text as dialogue, narration, thought, or sfx. Include reading_order from natural reading flow."
                            ),
                        },
                        {"type": "input_image", "image_url": data_url, "detail": "high"},
                    ],
                }
            ],
            text={"format": {"type": "json_schema", "name": "ocr_blocks", "strict": True, "schema": schema}},
        )
        payload = json.loads(response.output_text)
        raw_blocks = [OCRBlock(**item) for item in payload.get("blocks", [])]
        normalized = [
            _normalize_box(block, original_w, original_h, sent.width, sent.height)
            for block in raw_blocks
        ]
        return _dedupe_blocks(normalized)


def get_ocr_provider():
    settings = get_settings()
    if settings.mock_mode:
        return MockOCRProvider()
    return OpenAIOCRProvider()
