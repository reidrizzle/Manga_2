from __future__ import annotations

from sqlalchemy.orm import Session

from ..models import Page, Project, TextBlock, TranslationJob
from .image_processor import make_processed_background
from .ocr import get_ocr_provider
from .translator import get_translation_provider


def _latest_job(db: Session, page_id: int) -> TranslationJob | None:
    return (
        db.query(TranslationJob)
        .filter(TranslationJob.page_id == page_id)
        .order_by(TranslationJob.id.desc())
        .first()
    )


def process_page(db: Session, page_id: int) -> None:
    page = db.get(Page, page_id)
    if not page:
        return
    project = db.get(Project, page.project_id)
    if not project:
        return

    page.status = "processing"
    page.error_message = None
    job = _latest_job(db, page.id)
    if job:
        job.status = "processing"
        job.error_message = None
    db.commit()

    try:
        ocr_blocks = get_ocr_provider().detect_text(page.original_image)
        page.text_blocks.clear()
        db.flush()

        characters = [
            {
                "name": c.name,
                "gender": c.gender,
                "personality": c.personality,
                "self_reference": c.self_reference,
                "speaking_style": c.speaking_style,
                "relationship_notes": c.relationship_notes,
            }
            for c in project.characters
        ]
        glossary = [
            {"source_term": g.source_term, "target_term": g.target_term, "note": g.note}
            for g in project.glossary
        ]

        blocks: list[TextBlock] = []
        for item in ocr_blocks:
            block = TextBlock(
                page_id=page.id,
                original_text=item.original_text,
                language=item.language,
                text_type=item.text_type,
                tone=item.tone,
                x=item.x,
                y=item.y,
                width=item.width,
                height=item.height,
                confidence=item.confidence,
                reading_order=item.reading_order,
                style_data={
                    "source_box": {
                        "x": item.x,
                        "y": item.y,
                        "width": item.width,
                        "height": item.height,
                    }
                },
            )
            db.add(block)
            blocks.append(block)
        db.flush()

        previous_context: list[str] = []
        for existing_page in project.pages:
            if existing_page.page_number < page.page_number:
                for tb in existing_page.text_blocks:
                    if tb.translated_text:
                        previous_context.append(tb.translated_text)
        previous_context = previous_context[-12:]

        translations = get_translation_provider().translate_page(
            blocks,
            previous_context,
            characters,
            glossary,
            project.style,
            preserve_tone=project.preserve_tone,
            preserve_honorifics=project.preserve_honorifics,
            translate_sfx=project.translate_sfx,
        )

        for block, result in zip(blocks, translations):
            block.translated_text = result.translated_text
            block.tone = result.tone or block.tone
            block.character_name = result.character_name
            block.confidence = min(1.0, max(block.confidence, result.confidence))

        # Always regenerate the background from the FINAL OCR boxes.
        # This ensures the original text is removed before Reader/Editor displays it.
        page.processed_image = make_processed_background(page.original_image, blocks)
        page.status = "completed"
        page.error_message = None
        if job:
            job.status = "completed"
            job.error_message = None
        db.commit()
    except Exception as exc:
        db.rollback()
        failed_page = db.get(Page, page_id)
        failed_job = _latest_job(db, page_id)
        if failed_page:
            failed_page.status = "failed"
            failed_page.error_message = str(exc)[:1000]
        if failed_job:
            failed_job.status = "failed"
            failed_job.error_message = str(exc)[:1000]
        db.commit()
        # Re-raise so Celery's retry policy can actually retry transient failures.
        raise


def rebuild_page_image(db: Session, page_id: int) -> None:
    page = db.get(Page, page_id)
    if not page:
        return
    page.processed_image = make_processed_background(page.original_image, page.text_blocks)
    db.commit()
