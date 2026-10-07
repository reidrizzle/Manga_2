from pathlib import Path
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import select
from .config import get_settings
from .db import SessionLocal, init_db
from .models import User, Project, Page, TextBlock, Character, Glossary, TranslationJob
from .schemas import RegisterIn, LoginIn, ProjectCreate, ProjectSettingsIn, TextBlockUpdate, CharacterIn, GlossaryIn, project_dict
from .security import hash_password, verify_password
from .celery_app import process_page_task
from .services.pipeline import process_page, rebuild_page_image

settings = get_settings()
app = FastAPI(title=settings.app_name, version="1.0.1-fixed2")
app.add_middleware(SessionMiddleware, secret_key=settings.app_secret, https_only=settings.cookie_https_only, same_site="lax")

ROOT = Path(__file__).resolve().parents[2]
STATIC_DIR = ROOT / "frontend"


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    user_id = request.session.get("user_id")
    if not user_id:
        raise HTTPException(401, "กรุณาเข้าสู่ระบบ")
    user = db.get(User, int(user_id))
    if not user:
        request.session.clear()
        raise HTTPException(401, "เซสชันหมดอายุ")
    return user


def user_project(project_id: int, user: User, db: Session) -> Project:
    project = db.get(Project, project_id)
    if not project or project.owner_id != user.id:
        raise HTTPException(404, "ไม่พบโปรเจกต์")
    return project


@app.on_event("startup")
def startup():
    init_db()


@app.get("/health")
def health():
    return {"ok": True, "service": settings.app_name, "mock_mode": settings.mock_mode}


@app.post("/api/auth/register")
def register(payload: RegisterIn, request: Request, db: Session = Depends(get_db)):
    email = payload.email.strip().lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(400, "อีเมลนี้ถูกใช้งานแล้ว")
    user = User(email=email, password_hash=hash_password(payload.password))
    db.add(user)
    db.commit()
    db.refresh(user)
    request.session["user_id"] = user.id
    return {"id": user.id, "email": user.email}


@app.post("/api/auth/login")
def login(payload: LoginIn, request: Request, db: Session = Depends(get_db)):
    email = payload.email.strip().lower()
    user = db.scalar(select(User).where(User.email == email))
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(401, "อีเมลหรือรหัสผ่านไม่ถูกต้อง")
    request.session["user_id"] = user.id
    return {"id": user.id, "email": user.email}


@app.post("/api/auth/logout")
def logout(request: Request):
    request.session.clear()
    return {"ok": True}


@app.get("/api/auth/me")
def me(user: User = Depends(current_user)):
    return {"id": user.id, "email": user.email}


@app.get("/api/projects")
def list_projects(user: User = Depends(current_user), db: Session = Depends(get_db)):
    projects = db.scalars(select(Project).where(Project.owner_id == user.id).order_by(Project.updated_at.desc())).all()
    return [project_dict(p) for p in projects]


@app.post("/api/projects")
def create_project(payload: ProjectCreate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = Project(owner_id=user.id, **payload.model_dump())
    db.add(p)
    db.commit()
    db.refresh(p)
    return project_dict(p)


@app.get("/api/projects/{project_id}")
def get_project(project_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return project_dict(user_project(project_id, user, db))


@app.patch("/api/projects/{project_id}/settings")
def update_project_settings(project_id: int, payload: ProjectSettingsIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = user_project(project_id, user, db)
    for key, value in payload.model_dump().items():
        setattr(p, key, value)
    db.commit()
    return project_dict(p)


@app.post("/api/projects/{project_id}/pages")
async def upload_pages(project_id: int, files: list[UploadFile] = File(...), user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = user_project(project_id, user, db)
    if len(p.pages) + len(files) > settings.upload_limit_pages:
        raise HTTPException(400, f"โปรเจกต์นี้รองรับไม่เกิน {settings.upload_limit_pages} หน้าใน MVP")
    allowed = {"image/jpeg", "image/png", "image/webp"}
    for upload in files:
        if upload.content_type not in allowed:
            raise HTTPException(400, f"ไฟล์ {upload.filename} ไม่ใช่ JPG/PNG/WEBP")
        data = await upload.read()
        if len(data) > settings.max_upload_mb * 1024 * 1024:
            raise HTTPException(413, f"ไฟล์ {upload.filename} ใหญ่เกิน {settings.max_upload_mb} MB")
        next_num = len(p.pages) + 1
        try:
            from .services.image_processor import normalize_upload
            normalized_data, normalized_mime, width, height = normalize_upload(data, upload.content_type)
        except Exception:
            raise HTTPException(400, f"ไม่สามารถอ่าน/ปรับทิศทางรูป {upload.filename}")
        page = Page(
            project_id=p.id,
            page_number=next_num,
            filename=upload.filename or f"page-{next_num}.png",
            mime_type=normalized_mime,
            original_image=normalized_data,
            width=width,
            height=height,
            status="pending",
        )
        db.add(page)
        db.flush()
    db.commit()
    db.refresh(p)
    return project_dict(p)


@app.post("/api/projects/{project_id}/translate")
def translate_project(project_id: int, force: bool = False, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = user_project(project_id, user, db)
    queued = []

    # First commit page/job state. A worker may start immediately after .delay(), so
    # the job must already exist in the shared database before Celery sees the task.
    for page in p.pages:
        if page.status in {"queued", "processing"}:
            continue
        if page.status == "completed" and not force:
            continue
        page.status = "queued"
        page.error_message = None
        job = TranslationJob(project_id=p.id, page_id=page.id, status="queued")
        db.add(job)
        db.flush()
        queued.append((page.id, job.id))
    db.commit()

    created = []
    for page_id, job_id in queued:
        job = db.get(TranslationJob, job_id)
        try:
            task = process_page_task.delay(page_id)
            if job:
                job.celery_task_id = task.id
                db.commit()
        except Exception:
            # Local dev fallback when Redis/Celery is not running. A single broken page
            # must not prevent later pages from being processed.
            try:
                process_page(db, page_id)
            except Exception:
                pass
            else:
                db.commit()
        created.append(page_id)

    return {"queued_pages": created, "force": force}


@app.get("/api/projects/{project_id}/status")
def project_status(project_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = user_project(project_id, user, db)
    total = len(p.pages)
    counts = {"pending": 0, "queued": 0, "processing": 0, "completed": 0, "failed": 0}
    for page in p.pages:
        counts[page.status] = counts.get(page.status, 0) + 1
    return {"total": total, "counts": counts, "complete": counts.get("completed", 0) == total and total > 0}


@app.get("/api/pages/{page_id}/image")
def page_image(page_id: int, kind: str = "processed", user: User = Depends(current_user), db: Session = Depends(get_db)):
    page = db.get(Page, page_id)
    if not page or page.project.owner_id != user.id:
        raise HTTPException(404, "ไม่พบหน้า")
    if kind == "original":
        data, media_type = page.original_image, page.mime_type
    elif page.processed_image:
        data, media_type = page.processed_image, "image/png"
    else:
        data, media_type = page.original_image, page.mime_type
    return Response(content=data, media_type=media_type, headers={"Cache-Control": "private, max-age=3600"})


@app.get("/api/text-blocks/{block_id}")
def get_block(block_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    block = db.get(TextBlock, block_id)
    if not block or block.page.project.owner_id != user.id:
        raise HTTPException(404, "ไม่พบข้อความ")
    return {
        "id": block.id,
        "page_id": block.page_id,
        "original_text": block.original_text,
        "translated_text": block.translated_text,
        "language": block.language,
        "text_type": block.text_type,
        "tone": block.tone,
        "character_name": block.character_name,
        "x": block.x, "y": block.y, "width": block.width, "height": block.height,
    }


@app.put("/api/text-blocks/{block_id}")
def update_block(block_id: int, payload: TextBlockUpdate, user: User = Depends(current_user), db: Session = Depends(get_db)):
    block = db.get(TextBlock, block_id)
    if not block or block.page.project.owner_id != user.id:
        raise HTTPException(404, "ไม่พบข้อความ")
    data = payload.model_dump(exclude_none=True)
    page_id = block.page_id
    for k, v in data.items():
        setattr(block, k, v)
    db.commit()
    # Position changes must also move the text-removal mask, otherwise the old
    # source text can reappear when the user drags a block in the Editor.
    if any(key in data for key in ("x", "y", "width", "height")):
        rebuild_page_image(db, page_id)
    return get_block(block_id, user, db)


@app.post("/api/text-blocks/{block_id}/retranslate")
def retranslate_block(block_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    block = db.get(TextBlock, block_id)
    if not block or block.page.project.owner_id != user.id:
        raise HTTPException(404, "ไม่พบข้อความ")
    from .services.translator import get_translation_provider
    p = block.page.project
    chars = [{"name": c.name, "gender": c.gender, "personality": c.personality, "self_reference": c.self_reference, "speaking_style": c.speaking_style, "relationship_notes": c.relationship_notes} for c in p.characters]
    glossary = [{"source_term": g.source_term, "target_term": g.target_term, "note": g.note} for g in p.glossary]
    result = get_translation_provider().translate_page([block], [], chars, glossary, p.style, p.preserve_tone, p.preserve_honorifics, p.translate_sfx)[0]
    block.translated_text = result.translated_text
    block.tone = result.tone
    block.character_name = result.character_name
    db.commit()
    return get_block(block_id, user, db)


@app.post("/api/projects/{project_id}/characters")
def add_character(project_id: int, payload: CharacterIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = user_project(project_id, user, db)
    c = Character(project_id=p.id, **payload.model_dump())
    db.add(c); db.commit(); db.refresh(c)
    return {"id": c.id, **payload.model_dump()}


@app.post("/api/projects/{project_id}/glossary")
def add_glossary(project_id: int, payload: GlossaryIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = user_project(project_id, user, db)
    g = Glossary(project_id=p.id, **payload.model_dump())
    db.add(g); db.commit(); db.refresh(g)
    return {"id": g.id, **payload.model_dump()}


@app.delete("/api/projects/{project_id}")
def delete_project(project_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = user_project(project_id, user, db)
    db.delete(p); db.commit()
    return {"ok": True}


@app.get("/", include_in_schema=False)
def home():
    return FileResponse(STATIC_DIR / "index.html")

app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")


@app.get("/{full_path:path}", include_in_schema=False)
def spa_fallback(full_path: str):
    # Frontend routes are handled by the browser-side router.
    if full_path.startswith("api/") or full_path == "health":
        raise HTTPException(404, "Not found")
    return FileResponse(STATIC_DIR / "index.html")
