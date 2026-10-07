# MangaThai AI — Fix Notes (v1.0.1-fixed2)

แก้ปัญหาตามอาการที่พบ 4 เรื่องหลัก:

## 1) คำแปลตัวเล็กกว่าต้นฉบับ
**สาเหตุเดิม**
- `frontend/assets/app.js` ใช้ `Math.sqrt(width * height) / 7` แล้วล็อกสูงสุดไว้ 42px ซึ่งไม่สัมพันธ์กับจำนวนอักขระจริงและไม่รู้ว่าข้อความไทย wrap กี่บรรทัด
- เมื่อคำแปลภาษาไทยยาวกว่าต้นฉบับ ระบบจึงหดตัวอักษรมากเกินไป

**วิธีแก้**
- เพิ่มการคำนวณขนาดฟอนต์จากขนาดกล่องจริงบนหน้าจอ
- ใช้ binary search กับ DOM เพื่อเลือกขนาดฟอนต์ที่ใหญ่ที่สุดที่ยังอยู่ในกล่อง
- เพิ่ม `line-height`, `overflow-wrap`, และ padding ให้เหมาะกับภาษาไทย
- ปรับ prompt ให้คำแปลกระชับและพยายามให้พอดีกับ speech balloon เดิม

## 2) ตำแหน่งคำแปลไม่ตรงกับข้อความต้นฉบับ
**สาเหตุเดิม**
- OCR บังคับให้ตอบเป็น pixel แต่โค้ดเดิมไม่ได้ป้องกันกรณีโมเดลส่งพิกัดแบบ 0..1 หรือ 0..1000
- รูปที่มี EXIF orientation อาจมีขนาด/การหมุนไม่ตรงกับภาพที่ใช้แสดงจริง
- Reader มีปัญหาเรื่อง image load และ zoom ที่เปลี่ยนขนาด `<img>` ภายใน parent ทำให้ overlay กับภาพใช้ geometry คนละชุด

**วิธีแก้**
- Normalize EXIF orientation ตั้งแต่ตอน upload
- OCR image ถูกย่อให้ไม่เกิน 1800px และแปลงพิกัดกลับเป็นขนาดภาพต้นฉบับ
- รองรับและ normalize พิกัด 0..1 / 0..1000 แบบ fallback
- Reader ใช้ image เป็น reference geometry เดียวกันเสมอ และใช้ `loading="lazy"` เพื่อลดการโหลดภาพเต็มทุกหน้าพร้อมกัน
- รอ image `load` ก่อนวาง overlay
- Zoom ใหม่ด้วยการ render ทั้งหน้า แทนการขยายเฉพาะ `<img>`

## 3) ข้อความต้นฉบับยังติดอยู่บนภาพ
**สาเหตุเดิม**
- mask ของ inpaint ขยายจาก OCR box แค่ประมาณ 3% จึงอาจเหลือขอบ/anti-aliased glyph
- หากผู้ใช้ลาก text block ไปตำแหน่งใหม่ mask ใน `processed_image` ยังอยู่ตำแหน่งเดิม

**วิธีแก้**
- ขยาย mask 8–10% และ dilate เพิ่มอีกชั้นเพื่อเก็บขอบตัวอักษร
- ใช้ Telea inpainting radius ที่มากขึ้นสำหรับภาพใหญ่
- Normalize รูปก่อน OCR ทำให้พิกัด mask สอดคล้องกับภาพจริง
- เมื่อแก้ `x/y/width/height` ใน Editor ระบบจะสร้าง `processed_image` ใหม่ทันที โดยใช้ `source_box` เดิมสำหรับลบข้อความต้นฉบับ จึงลากคำแปลแล้วต้นฉบับไม่กลับมา

## 4) แปลได้เพียง 1–2 หน้าแล้วหยุด
**สาเหตุเดิม**
- `process_page()` จับ exception แล้วไม่ throw ต่อ ทำให้ Celery มอง task ว่าสำเร็จและระบบ retry ไม่ทำงานจริง
- Celery worker ไม่มี `acks_late`, `prefetch=1`, และการตั้งค่าช่วยรับมือ worker หลุด/เริ่ม broker ช้า
- รูปใหญ่ถูกส่งเข้า OCR เต็มขนาด ทำให้ payload และเวลาเรียก AI สูงมาก
- หน้าเดียวที่มี text block จำนวนมากถูกส่งแปลเป็น request เดียว

**วิธีแก้**
- หลังบันทึก `failed` แล้ว `process_page()` re-raise exception เพื่อให้ Celery retry ได้
- เพิ่ม retry สูงสุด 3 ครั้ง + exponential backoff/jitter และระหว่างรอ retry เปลี่ยนสถานะกลับเป็น `queued` เพื่อไม่ให้หน้า Project เข้าใจว่าจบถาวร
- ตั้ง `worker_prefetch_multiplier=1` และ `task_acks_late=True`
- ย่อภาพสำหรับ OCR เหลือด้านยาวไม่เกิน 1800px และส่งเป็น JPEG คุณภาพ 88 พร้อมแปลงพิกัดกลับ
- แบ่ง translation ต่อหน้าเป็นครั้งละไม่เกิน 30 blocks เพื่อป้องกัน request ใหญ่เกินไป
- แก้ race condition ของ Celery โดย commit `queued` page/job ก่อน dispatch task เพื่อไม่ให้ worker เริ่มเร็วกว่าข้อมูลในฐานข้อมูล
- ใน local synchronous fallback ถ้าหน้าใดพัง จะบันทึก `failed` และเดินหน้าหน้าถัดไป ไม่หยุดทั้งโปรเจกต์
- endpoint แปลปกติจะไม่ queue หน้าที่เสร็จแล้วซ้ำ ส่วนปุ่ม “แปลใหม่ทั้งหมด” ส่ง `force=true` เพื่อบังคับประมวลผลใหม่ทุกหน้า
- หน้า `Project` หยุด polling เมื่อทุกหน้ากลายเป็นสถานะ terminal (`completed` หรือ `failed`)

## ไฟล์ที่แก้หลัก
- `backend/app/main.py`
- `backend/app/celery_app.py`
- `backend/app/services/ocr.py`
- `backend/app/services/translator.py`
- `backend/app/services/image_processor.py`
- `backend/app/services/pipeline.py`
- `frontend/assets/app.js`
- `frontend/assets/styles.css`

แพ็กเกจส่งมอบควรไม่รวม `.venv`, `__pycache__`, `.db`, และ `.env` เพราะเป็นไฟล์ runtime/ข้อมูลเครื่องของแต่ละคน


## v1.0.1-fixed3 — แก้จากภาพผลลัพธ์จริง

### 5) OCR coordinate bug สำหรับภาพแนวตั้งขนาดเล็ก
- โค้ดเดิมตรวจ 0..1000 coordinates เฉพาะกรณีภาพด้านใดด้านหนึ่ง > 1000px เท่านั้น
- มังงะแนวตั้ง 200–900px จึงมีโอกาสถูกตีความว่าเป็น pixel coordinate ทำให้ตำแหน่งผิดและลบข้อความผิดจุด
- เปลี่ยนมาตรฐาน prompt เป็น 0..1 normalized coordinates และเพิ่ม heuristic แปลง 0..1000 เมื่อค่ากล่องเกินขอบภาพอย่างชัดเจน

### 6) Overlay เดิมสร้างพื้นขาวใหม่และเล็กเกินไป
- เดิม overlay มี `background: rgba(255,255,255,.97)` ทำให้เกิดกล่องขาวซ้อนบนภาพ
- เปลี่ยนเป็นพื้นโปร่งใส ใช้พื้นกล่องเดิมจากภาพหลังลบข้อความ
- ขยาย render box ประมาณ 1.55x–1.75x จาก OCR box เพื่อให้ภาษาไทย wrap ได้โดยไม่หดตัวจนเล็ก

### 7) ค่าตั้งต้นเป็น Mock mode ทำให้เข้าใจว่าแปลจริง
- `.env.example` เดิมตั้ง `MOCK_MODE=true`
- เปลี่ยน default เป็น `false` และระบุชัดว่า mock ใช้ทดสอบ UI เท่านั้น

หมายเหตุ: คุณภาพสุดท้ายยังขึ้นกับความแม่นของ OCR จาก vision model และสภาพพื้นหลังของแต่ละหน้า แต่จุดผิดพลาดจาก coordinate normalization และ overlay ที่เห็นในภาพถูกแก้แล้ว
