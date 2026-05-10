from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
import os, tempfile, gc, torch, asyncio
from faster_whisper import WhisperModel
from deep_translator import GoogleTranslator
from fastapi import Form

app = FastAPI(title="Thai Subtitle AI Dashboard")

# ✅ เปิด CORS สำหรับ Localhost
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # อนุญาตทุก origin (ปลอดภัยสำหรับ dev)
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

model = None

def cleanup(paths):
    for p in paths:
        try: os.remove(p)
        except: pass

def load_model():
    global model
    if model is None:
        device = "cuda" if torch.cuda.is_available() else "cpu"
        model = WhisperModel("small", device=device, compute_type="int8")
    return model

def format_srt_time(seconds: float) -> str:
    h, m, s = int(seconds // 3600), int((seconds % 3600) // 60), seconds % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}".replace('.', ',')

@app.get("/", response_class=HTMLResponse)
async def index():
    with open("index.html", encoding="utf-8") as f:
        return f.read()


@app.get("/favicon.ico")
async def favicon():
    return FileResponse("favicon.ico", media_type="image/x-icon")

@app.post("/transcribe")
async def transcribe(
    file: UploadFile = File(...),
    source_lang: str = Form("auto"),  # รับค่าภาษาจาก UI
    bg: BackgroundTasks = None
):
    try:
        m = load_model()
        suffix = os.path.splitext(file.filename)[1]
        
        tmp_audio = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        tmp_audio.write(await file.read())
        tmp_audio.close()

        # 1. กำหนดภาษาให้ Whisper
        whisper_lang = None if source_lang == "auto" else source_lang
        
        print(f"🔍 กำลังถอดความ (โหมด: {source_lang})...")
        segments, info = m.transcribe(
            tmp_audio.name, 
            language=whisper_lang, 
            task="transcribe",
            beam_size=5, 
            vad_filter=True
        )
        seg_list = list(segments)
        if not seg_list:
            raise HTTPException(status_code=400, detail="ไม่พบข้อความในไฟล์")

        # 2. กำหนดภาษาต้นทางสำหรับการแปล
        # ถ้าเลือก Auto ให้ใช้ภาษาที่ Whisper ตรวจจับได้
        translate_source = info.language if source_lang == "auto" else source_lang
        
        # ถ้าเป็นภาษาไทย ให้ข้ามขั้นตอนแปล (ถอดความตรงๆ)
        is_thai_source = translate_source == "th"
        translator = None if is_thai_source else GoogleTranslator(source=translate_source, target='th')
        
        cache = {}
        srt_lines = []

        for i, seg in enumerate(seg_list, 1):
            txt = seg.text.strip()
            if not txt: continue

            if is_thai_source:
                final_text = txt
            else:
                if txt in cache:
                    final_text = cache[txt]
                else:
                    try:
                        final_text = translator.translate(txt)
                        cache[txt] = final_text
                        await asyncio.sleep(0.04)  # ป้องกัน Rate Limit
                    except Exception:
                        final_text = txt  # แปลไม่สำเร็จให้ใช้ต้นฉบับแทน

            srt_lines.append(f"{i}\n{format_srt_time(seg.start)} --> {format_srt_time(seg.end)}\n{final_text}\n")

        tmp_srt = tempfile.NamedTemporaryFile(delete=False, suffix="_TH.srt", mode="w", encoding="utf-8")
        tmp_srt.write("\n".join(srt_lines))
        tmp_srt.close()

        bg.add_task(cleanup, [tmp_audio.name, tmp_srt.name])
        print(f"✅ เสร็จสิ้น! แปลจาก {translate_source.upper()} เป็น TH")

        return FileResponse(
            tmp_srt.name,
            filename=f"{os.path.splitext(file.filename)[0]}_TH.srt",
            media_type="application/x-subrip"
        )
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Backend Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))