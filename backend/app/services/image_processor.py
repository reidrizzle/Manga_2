from __future__ import annotations

from io import BytesIO

import cv2
import numpy as np
from PIL import Image, ImageOps



def normalize_upload(data: bytes, content_type: str | None = None) -> tuple[bytes, str, int, int]:
    """Normalize EXIF orientation and return consistent image bytes/dimensions."""
    with Image.open(BytesIO(data)) as source:
        image = ImageOps.exif_transpose(source).convert("RGB")
        width, height = image.size
        output = BytesIO()
        if content_type == "image/png":
            image.save(output, format="PNG", optimize=True)
            mime = "image/png"
        elif content_type == "image/webp":
            image.save(output, format="WEBP", quality=95, method=6)
            mime = "image/webp"
        else:
            image.save(output, format="JPEG", quality=95, optimize=True)
            mime = "image/jpeg"
        return output.getvalue(), mime, width, height


def read_image(data: bytes) -> tuple[np.ndarray, int, int]:
    arr = np.frombuffer(data, dtype=np.uint8)
    image = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("Invalid image")
    h, w = image.shape[:2]
    return image, w, h


def _expand_bounds(x: float, y: float, width: float, height: float, image_width: int, image_height: int):
    # A small but deliberate expansion is important because OCR boxes tend to
    # hug glyphs too tightly. That otherwise leaves edge pixels of the source text.
    pad_x = max(4, min(48, int(round(width * 0.10))))
    pad_y = max(4, min(48, int(round(height * 0.14))))
    x1 = max(0, int(round(x)) - pad_x)
    y1 = max(0, int(round(y)) - pad_y)
    x2 = min(image_width, int(round(x + width)) + pad_x)
    y2 = min(image_height, int(round(y + height)) + pad_y)
    return x1, y1, x2, y2


def make_processed_background(image_bytes: bytes, blocks) -> bytes:
    image, w, h = read_image(image_bytes)
    mask = np.zeros((h, w), dtype=np.uint8)

    for block in blocks:
        # Keep source OCR geometry separate from the editable overlay geometry.
        # This prevents the original text from reappearing when a user drags the translation.
        source_box = None
        style_data = getattr(block, "style_data", None) or {}
        if isinstance(style_data, dict):
            source_box = style_data.get("source_box")
        if isinstance(source_box, dict):
            bx, by = float(source_box.get("x", block.x)), float(source_box.get("y", block.y))
            bw, bh = float(source_box.get("width", block.width)), float(source_box.get("height", block.height))
        else:
            bx, by, bw, bh = block.x, block.y, block.width, block.height
        x1, y1, x2, y2 = _expand_bounds(bx, by, bw, bh, w, h)
        if x2 > x1 and y2 > y1:
            mask[y1:y2, x1:x2] = 255

    if np.any(mask):
        # Smooth/expand the mask one more step to catch anti-aliased glyph edges.
        kernel_side = max(3, min(11, int(round(min(w, h) * 0.0025)) * 2 + 1))
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_side, kernel_side))
        mask = cv2.dilate(mask, kernel, iterations=1)

        # Telea works well for comic speech bubbles and simple line-art areas.
        radius = 5 if max(w, h) >= 1600 else 3
        image = cv2.inpaint(image, mask, radius, cv2.INPAINT_TELEA)

    ok, encoded = cv2.imencode(".png", image, [cv2.IMWRITE_PNG_COMPRESSION, 3])
    if not ok:
        raise RuntimeError("Could not encode processed image")
    return encoded.tobytes()


def expanded_render_box(x: float, y: float, width: float, height: float, image_width: float, image_height: float,
                        width_factor: float = 1.55, height_factor: float = 1.75) -> tuple[float, float, float, float]:
    """Return a larger box for the translated overlay while keeping the original OCR box separate.

    OCR usually hugs glyphs, but the translation needs a little breathing room for Thai wrapping.
    """
    cx = x + width / 2.0
    cy = y + height / 2.0
    rw = min(image_width, max(width, width * width_factor))
    rh = min(image_height, max(height, height * height_factor))
    rx = max(0.0, min(image_width - rw, cx - rw / 2.0))
    ry = max(0.0, min(image_height - rh, cy - rh / 2.0))
    return rx, ry, rw, rh


def fit_font_size(text: str, box_w: float, box_h: float) -> float:
    # Initial estimate only. The browser performs an actual fit against the
    # rendered Thai font because Thai line breaking is font-dependent.
    text = (text or "").strip()
    n = max(1, len(text))
    # More generous than the previous sqrt-area heuristic, which made Thai tiny.
    approx_by_width = box_w / max(1.0, n * 0.46)
    approx_by_height = box_h * 0.62
    return max(10.0, min(72.0, approx_by_width, approx_by_height))
