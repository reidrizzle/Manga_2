from celery import Celery
from .config import get_settings

settings = get_settings()
MAX_PAGE_RETRIES = 3

celery_app = Celery("mangathai", broker=settings.redis_url, backend=None)
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Bangkok",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
    task_default_queue="translation",
)


@celery_app.task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=60,
    retry_jitter=True,
    retry_kwargs={"max_retries": MAX_PAGE_RETRIES},
)
def process_page_task(self, page_id: int):
    from .db import SessionLocal
    from .services.pipeline import process_page

    db = SessionLocal()
    try:
        try:
            process_page(db, page_id)
        except Exception:
            # Keep the page visible as queued while Celery is scheduling a retry.
            # On the final attempt leave it as failed so the UI can show a real error.
            if self.request.retries < MAX_PAGE_RETRIES:
                from .models import Page, TranslationJob
                page = db.get(Page, page_id)
                if page:
                    page.status = "queued"
                    job = (
                        db.query(TranslationJob)
                        .filter_by(page_id=page_id)
                        .order_by(TranslationJob.id.desc())
                        .first()
                    )
                    if job:
                        job.status = "queued"
                    db.commit()
            raise
        return {"page_id": page_id, "status": "completed"}
    finally:
        db.close()
