# START HERE — MangaThai AI บน VS Code + GitHub + Render (v1.0.1-fixed2)

## 1) เปิดโปรเจกต์

แตก ZIP แล้วเปิดโฟลเดอร์ `manga-thai-ai-render` ใน VS Code

## 2) รันบนเครื่องก่อน

PowerShell:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload --port 8000
```

เข้า:

`http://127.0.0.1:8000`

## 3) ทดสอบโดยไม่ใช้ API Key

ใน `.env` คงไว้:

```env
MOCK_MODE=true
```

ระบบจะสร้าง OCR/คำแปลตัวอย่างเพื่อทดสอบหน้าต่าง ๆ

## 4) ใช้ AI จริง

ใส่:

```env
MOCK_MODE=false
OPENAI_API_KEY=...
OPENAI_MODEL=gpt-6-astra
```

## 5) Push GitHub

```powershell
git init
git add .
git commit -m "MangaThai AI Render MVP"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/manga-thai-ai.git
git push -u origin main
```

## 6) Deploy Render

Render → New → Blueprint → เลือก repo นี้

ไฟล์ `render.yaml` จะสร้าง:

- manga-thai-ai-web
- manga-thai-ai-worker
- manga-thai-ai-queue
- manga-thai-ai-db

เริ่มต้นให้ `MOCK_MODE=true` ก่อน จากนั้นเมื่อเว็บออนไลน์และทดสอบ flow สำเร็จ ค่อยตั้ง `OPENAI_API_KEY` และเปลี่ยน `MOCK_MODE=false`
