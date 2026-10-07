from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, Integer, LargeBinary, String, Text, Float, Boolean, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .db import Base


def now() -> datetime:
    return datetime.utcnow()


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    projects: Mapped[list["Project"]] = relationship(back_populates="owner", cascade="all, delete-orphan")


class Project(Base):
    __tablename__ = "projects"
    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    source_language: Mapped[str] = mapped_column(String(32), default="auto")
    target_language: Mapped[str] = mapped_column(String(32), default="th")
    style: Mapped[str] = mapped_column(String(32), default="natural")
    preserve_tone: Mapped[bool] = mapped_column(Boolean, default=True)
    preserve_honorifics: Mapped[bool] = mapped_column(Boolean, default=True)
    translate_sfx: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)
    owner: Mapped[User] = relationship(back_populates="projects")
    pages: Mapped[list["Page"]] = relationship(back_populates="project", cascade="all, delete-orphan", order_by="Page.page_number")
    characters: Mapped[list["Character"]] = relationship(back_populates="project", cascade="all, delete-orphan")
    glossary: Mapped[list["Glossary"]] = relationship(back_populates="project", cascade="all, delete-orphan")


class Page(Base):
    __tablename__ = "pages"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    page_number: Mapped[int] = mapped_column(Integer)
    filename: Mapped[str] = mapped_column(String(255))
    mime_type: Mapped[str] = mapped_column(String(80), default="image/png")
    original_image: Mapped[bytes] = mapped_column(LargeBinary)
    processed_image: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    width: Mapped[int] = mapped_column(Integer, default=1)
    height: Mapped[int] = mapped_column(Integer, default=1)
    project: Mapped[Project] = relationship(back_populates="pages")
    text_blocks: Mapped[list["TextBlock"]] = relationship(back_populates="page", cascade="all, delete-orphan", order_by="TextBlock.reading_order")


class TextBlock(Base):
    __tablename__ = "text_blocks"
    id: Mapped[int] = mapped_column(primary_key=True)
    page_id: Mapped[int] = mapped_column(ForeignKey("pages.id"), index=True)
    original_text: Mapped[str] = mapped_column(Text)
    translated_text: Mapped[str] = mapped_column(Text, default="")
    language: Mapped[str] = mapped_column(String(32), default="unknown")
    text_type: Mapped[str] = mapped_column(String(32), default="dialogue")
    tone: Mapped[str] = mapped_column(String(64), default="neutral")
    character_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    x: Mapped[float] = mapped_column(Float, default=0)
    y: Mapped[float] = mapped_column(Float, default=0)
    width: Mapped[float] = mapped_column(Float, default=0)
    height: Mapped[float] = mapped_column(Float, default=0)
    confidence: Mapped[float] = mapped_column(Float, default=0)
    reading_order: Mapped[int] = mapped_column(Integer, default=0)
    style_data: Mapped[dict] = mapped_column(JSON, default=dict)
    page: Mapped[Page] = relationship(back_populates="text_blocks")


class Character(Base):
    __tablename__ = "characters"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    gender: Mapped[str] = mapped_column(String(32), default="unknown")
    personality: Mapped[str] = mapped_column(Text, default="")
    self_reference: Mapped[str] = mapped_column(String(64), default="ฉัน")
    speaking_style: Mapped[str] = mapped_column(String(255), default="ธรรมชาติ")
    relationship_notes: Mapped[str] = mapped_column(Text, default="")
    project: Mapped[Project] = relationship(back_populates="characters")


class Glossary(Base):
    __tablename__ = "glossary"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    source_term: Mapped[str] = mapped_column(String(255))
    target_term: Mapped[str] = mapped_column(String(255))
    note: Mapped[str] = mapped_column(Text, default="")
    project: Mapped[Project] = relationship(back_populates="glossary")


class TranslationJob(Base):
    __tablename__ = "translation_jobs"
    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True)
    page_id: Mapped[int] = mapped_column(ForeignKey("pages.id"), index=True)
    celery_task_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="queued")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)
