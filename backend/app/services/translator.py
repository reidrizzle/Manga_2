from __future__ import annotations

import json
from dataclasses import dataclass

from ..config import get_settings


MAX_BLOCKS_PER_REQUEST = 30


@dataclass
class TranslationResult:
    translated_text: str
    tone: str
    character_name: str | None
    confidence: float


class MockTranslationProvider:
    def translate_page(self, blocks, context, characters, glossary, style, preserve_tone=True, preserve_honorifics=True, translate_sfx=True):
        results = []
        for b in blocks:
            if b.text_type == "sfx":
                thai = "ปัง!"
            elif "[ตัวอย่าง]" in b.original_text:
                thai = "[ตัวอย่าง] นี่คือข้อความภาษาไทย"
            else:
                thai = f"[TH] {b.original_text}"
            results.append(TranslationResult(thai, b.tone or "neutral", None, 0.80))
        return results


class OpenAITranslationProvider:
    def __init__(self) -> None:
        settings = get_settings()
        if not settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is not configured")
        from openai import OpenAI

        self.client = OpenAI(api_key=settings.openai_api_key)
        self.model = settings.openai_model

    def _translate_chunk(self, blocks, context, characters, glossary, style, preserve_tone, preserve_honorifics, translate_sfx):
        items = [
            {
                "id": i,
                "original_text": b.original_text,
                "text_type": b.text_type,
                "tone": b.tone,
                "reading_order": b.reading_order,
            }
            for i, b in enumerate(blocks)
        ]
        schema = {
            "type": "object",
            "properties": {
                "translations": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "integer"},
                            "translated_text": {"type": "string"},
                            "tone": {"type": "string"},
                            "character_name": {"type": ["string", "null"]},
                            "confidence": {"type": "number"},
                        },
                        "required": ["id", "translated_text", "tone", "character_name", "confidence"],
                        "additionalProperties": False,
                    },
                }
            },
            "required": ["translations"],
            "additionalProperties": False,
        }
        prompt = f"""
You are a professional Thai manga/manhwa localization translator.
Translate the source text into natural Thai suitable for a manga reader.
Do NOT translate word-for-word when that would sound stiff or unnatural.
Preserve meaning, emotion, characterization, and context.
Keep each translation concise enough to fit the SAME speech balloon / text region as the source whenever possible.
Avoid adding explanations, commentary, or information that is not in the source.
Prefer natural Thai line length and phrasing over literal structure.
Never output quotation marks or labels that were not present in the source.

Translation style: {style}
Preserve tone: {preserve_tone}
Preserve honorifics: {preserve_honorifics}
Translate SFX: {translate_sfx}

Previous context (most recent first):
{json.dumps(context[-12:], ensure_ascii=False)}

Characters:
{json.dumps(characters, ensure_ascii=False)}

Glossary:
{json.dumps(glossary, ensure_ascii=False)}

Current text blocks:
{json.dumps(items, ensure_ascii=False)}
"""
        response = self.client.responses.create(
            model=self.model,
            store=False,
            input=prompt,
            text={"format": {"type": "json_schema", "name": "translations", "strict": True, "schema": schema}},
        )
        payload = json.loads(response.output_text)
        by_id = {x["id"]: x for x in payload.get("translations", [])}
        results: list[TranslationResult] = []
        for i, _ in enumerate(blocks):
            item = by_id.get(
                i,
                {"translated_text": "", "tone": "neutral", "character_name": None, "confidence": 0.0},
            )
            results.append(
                TranslationResult(
                    translated_text=str(item.get("translated_text") or "").strip(),
                    tone=str(item.get("tone") or "neutral"),
                    character_name=item.get("character_name"),
                    confidence=max(0.0, min(1.0, float(item.get("confidence", 0.0)))),
                )
            )
        return results

    def translate_page(self, blocks, context, characters, glossary, style, preserve_tone=True, preserve_honorifics=True, translate_sfx=True):
        if not blocks:
            return []

        all_results: list[TranslationResult] = []
        running_context = list(context)
        for start in range(0, len(blocks), MAX_BLOCKS_PER_REQUEST):
            chunk = blocks[start:start + MAX_BLOCKS_PER_REQUEST]
            chunk_results = self._translate_chunk(
                chunk,
                running_context,
                characters,
                glossary,
                style,
                preserve_tone,
                preserve_honorifics,
                translate_sfx,
            )
            all_results.extend(chunk_results)
            for result in chunk_results:
                if result.translated_text:
                    running_context.append(result.translated_text)
        return all_results


def get_translation_provider():
    settings = get_settings()
    if settings.mock_mode:
        return MockTranslationProvider()
    return OpenAITranslationProvider()
