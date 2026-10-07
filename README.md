# MangaThai AI — Render MVP (v1.0.1-fixed2)

เว็บแปลมังงะ/มังฮวาจากภาพเป็นภาษาไทยแบบคำนึงถึงบริบท พร้อม Reader ในเว็บ

สถาปัตยกรรม:

- FastAPI — web/API
- Celery — background jobs
- Render Key Value — queue
- Render Postgres — project/page/translation data + image bytes ใน MVP
- OpenAI Responses API — OCR/vision + contextual Thai translation (optional)
- OpenCV/Pillow — basic text removal/inpainting
- Vanilla HTML/CSS/JS — frontend ที่เสิร์ฟจาก FastAPI

OpenAI Responses API รองรับ image input และ Structured Outputs; โปรเจกต์นี้ใช้ทั้งสองอย่างใน provider ที่แยกโมดูลไว้ เพื่อเปลี่ยน provider ภายหลังได้ง่าย.

## Run locally

ต้องมี Python 3.11+ และ Node ไม่จำเป็น

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload --port 8000
```

เปิด `http://127.0.0.1:8000`

ถ้าไม่ได้เปิด Redis/Celery ระบบจะพยายาม fallback ไปประมวลผลแบบ synchronous เมื่อใช้ Mock Mode

## OpenAI mode

แก้ `backend/.env`:

```env
MOCK_MODE=false
OPENAI_API_KEY=your_key_here
OPENAI_MODEL=gpt-6-astra
```

## GitHub

```powershell
git init
git add .
git commit -m "Initial MangaThai AI Render MVP"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/manga-thai-ai.git
git push -u origin main
```

## Deploy to Render

มี `render.yaml` ที่ root repository แล้ว ใช้ Render Blueprint เพื่อสร้าง Web Service + Worker + Key Value + Postgres ได้จากไฟล์เดียว

1. Push repository ขึ้น GitHub
2. เข้า Render Dashboard
3. New → Blueprint
4. เลือก repository นี้
5. Render จะอ่าน `render.yaml`
6. ตั้งค่า `OPENAI_API_KEY` ใน Dashboard ถ้าจะใช้ AI จริง
7. ตอนเริ่มต้นใช้ `MOCK_MODE=true` เพื่อทดสอบ UI และ flow ก่อน
8. เมื่อพร้อมใช้ AI จริง ให้เปลี่ยน `MOCK_MODE=false`

## Important MVP limitation

ภาพต้นฉบับและภาพ processed ถูกเก็บใน PostgreSQL เป็น bytes เพื่อให้ MVP ทำงานได้โดยไม่ต้องมี object storage เพิ่ม แต่เมื่อมีผู้ใช้/ไฟล์จำนวนมาก ควรย้าย image storage ไป S3-compatible storage เช่น Cloudflare R2/Supabase Storage แล้วเก็บเฉพาะ object key ใน Postgres

Render services มี ephemeral filesystem เป็นค่าเริ่มต้น จึงไม่ควรพึ่งไฟล์ local เป็น storage ถาวร

## Features

- register/login
- upload multi-page JPG/PNG/WEBP
- source language / Thai settings
- context-aware translation provider
- character memory
- glossary
- OCR block coordinates
- text removal/inpainting MVP
- editable translation
- retranslate single text block
- reader แบบ vertical
- image zoom
- Render Blueprint
