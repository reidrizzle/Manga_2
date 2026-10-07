from datetime import datetime
from pydantic import BaseModel, Field


class RegisterIn(BaseModel):
    email: str
    password: str = Field(min_length=6, max_length=128)


class LoginIn(BaseModel):
    email: str
    password: str


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    source_language: str = "auto"
    target_language: str = "th"
    style: str = "natural"
    preserve_tone: bool = True
    preserve_honorifics: bool = True
    translate_sfx: bool = True


class ProjectSettingsIn(BaseModel):
    source_language: str = "auto"
    style: str = "natural"
    preserve_tone: bool = True
    preserve_honorifics: bool = True
    translate_sfx: bool = True


class TextBlockUpdate(BaseModel):
    translated_text: str
    character_name: str | None = None
    text_type: str | None = None
    tone: str | None = None
    x: float | None = None
    y: float | None = None
    width: float | None = None
    height: float | None = None


class CharacterIn(BaseModel):
    name: str
    gender: str = "unknown"
    personality: str = ""
    self_reference: str = "ฉัน"
    speaking_style: str = "ธรรมชาติ"
    relationship_notes: str = ""


class GlossaryIn(BaseModel):
    source_term: str
    target_term: str
    note: str = ""


def page_dict(page):
    return {
        "id": page.id,
        "page_number": page.page_number,
        "filename": page.filename,
        "mime_type": page.mime_type,
        "status": page.status,
        "width": page.width,
        "height": page.height,
        "image_url": f"/api/pages/{page.id}/image?kind=processed",
        "original_url": f"/api/pages/{page.id}/image?kind=original",
        "text_blocks": [
            {
                "id": b.id,
                "original_text": b.original_text,
                "translated_text": b.translated_text,
                "language": b.language,
                "text_type": b.text_type,
                "tone": b.tone,
                "character_name": b.character_name,
                "x": b.x,
                "y": b.y,
                "width": b.width,
                "height": b.height,
                "confidence": b.confidence,
                "reading_order": b.reading_order,
                "style_data": b.style_data or {},
            }
            for b in page.text_blocks
        ],
    }


def project_dict(project):
    done = sum(1 for p in project.pages if p.status == "completed")
    return {
        "id": project.id,
        "name": project.name,
        "source_language": project.source_language,
        "target_language": project.target_language,
        "style": project.style,
        "preserve_tone": project.preserve_tone,
        "preserve_honorifics": project.preserve_honorifics,
        "translate_sfx": project.translate_sfx,
        "created_at": project.created_at.isoformat() if isinstance(project.created_at, datetime) else str(project.created_at),
        "updated_at": project.updated_at.isoformat() if isinstance(project.updated_at, datetime) else str(project.updated_at),
        "page_count": len(project.pages),
        "completed_count": done,
        "pages": [page_dict(p) for p in project.pages],
        "characters": [
            {
                "id": c.id,
                "name": c.name,
                "gender": c.gender,
                "personality": c.personality,
                "self_reference": c.self_reference,
                "speaking_style": c.speaking_style,
                "relationship_notes": c.relationship_notes,
            }
            for c in project.characters
        ],
        "glossary": [
            {"id": g.id, "source_term": g.source_term, "target_term": g.target_term, "note": g.note}
            for g in project.glossary
        ],
    }
