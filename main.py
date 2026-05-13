from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks, Form
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
import os
import tempfile
import gc
import torch
import asyncio
import subprocess
import time
from urllib.parse import urlparse
from faster_whisper import WhisperModel
from deep_translator import GoogleTranslator
import uuid
import sys

# ✅ สร้าง App Instance
app = FastAPI(title="Thai Subtitle AI Dashboard")

# ✅ เปิด CORS สำหรับ Localhost
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

model = None

def cleanup(paths):
    for p in paths:
        try: 
            if os.path.exists(p):
                os.remove(p)
        except Exception as e:
            print(f"Warning: Could not remove {p}: {e}")

def load_model():
    global model
    if model is None:
        device = "cuda" if torch.cuda.is_available() else "cpu"
        # ใช้ int8 เพื่อประหยัด VRAM และเร็วขึ้นสำหรับการ์ดจอทั่วไป
        model = WhisperModel("small", device=device, compute_type="int8")
    return model

def format_srt_time(seconds: float) -> str:
    h, m, s = int(seconds // 3600), int((seconds % 3600) // 60), seconds % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}".replace('.', ',')

def download_audio_from_url(url: str, output_dir: str) -> str:
    """
    ดาวน์โหลดเสียงจาก YouTube หรือ Direct URL โดยใช้ yt-dlp
    """
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        raise HTTPException(status_code=400, detail="URL ไม่ถูกต้อง")

    unique_id = uuid.uuid4().hex
    temp_filename = os.path.join(output_dir, f"audio_{unique_id}.m4a")
    
    # หา path ของ ffmpeg ในโฟลเดอร์ปัจจุบัน (ถ้ามี)
    ffmpeg_path = os.path.join(os.getcwd(), "ffmpeg.exe")
    ffmpeg_arg = []
    if os.path.exists(ffmpeg_path):
        ffmpeg_arg = ["--ffmpeg-location", ffmpeg_path]
    
    try:
        print(f"📥 [DEBUG] กำลังดาวน์โหลด: {url}")
        
        # คำสั่ง yt-dlp แบบปรับปรุง
        cmd = [
            sys.executable, 
            "-m", "yt_dlp", 
            "-x",                
            "--audio-format", "m4a", 
            "--output", temp_filename,
            "--no-playlist",     
            "--quiet",           
            "--user-agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "--socket-timeout", "10",
            # พยายามใช้ Node.js ถ้ามี (ปกติ Windows มักจะมีถ้าลง VS Code หรือ Node)
            "--js-runtimes", "node", 
            # ถ้าไม่มี node จะลอง deno หรือ quickjs อัตโนมัติตาม default ของ yt-dlp
        ] + ffmpeg_arg + [url]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=600) 
        
        if result.returncode != 0:
            error_msg = result.stderr.strip()
            print(f"❌ [ERROR] yt-dlp failed: {error_msg}")
            # ถ้ายัง error เรื่อง JS runtime ให้ลองลบ --js-runtimes ออกแล้วรันใหม่แบบ legacy (อาจได้เฉพาะบางคลิป)
            if "JavaScript runtime" in error_msg:
                print("⚠️ ลองดาวน์โหลดแบบไม่ใช้ JS Runtime (Legacy Mode)...")
                cmd_legacy = [
                    sys.executable, 
                    "-m", "yt_dlp", 
                    "-x",                
                    "--audio-format", "m4a", 
                    "--output", temp_filename,
                    "--no-playlist",     
                    "--quiet",           
                    "--user-agent", "Mozilla/5.0",
                    "--socket-timeout", "10",
                    "--extractor-args", "youtube:player_client=web_embedded" # บังคับใช้ player แบบเก่า
                ] + ffmpeg_arg + [url]
                result = subprocess.run(cmd_legacy, capture_output=True, text=True, timeout=600)
                if result.returncode != 0:
                    raise Exception(f"yt-dlp legacy error: {result.stderr.strip()}")

        if not os.path.exists(temp_filename):
             files = [f for f in os.listdir(output_dir) if f.startswith("audio_")]
             if files:
                 final_path = os.path.join(output_dir, files[0])
                 print(f"✅ [DEBUG] Found downloaded file: {final_path}")
                 return final_path
             else:
                 raise Exception("Downloaded file not found after yt-dlp execution")
                 
        print(f"✅ [DEBUG] Download success: {temp_filename}")
        return temp_filename

    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="ดาวน์โหลด超时 (Timeout)")
    except Exception as e:
        print(f"❌ [EXCEPTION] Download failed: {str(e)}")
        raise HTTPException(status_code=500, detail=f"ดาวน์โหลดล้มเหลว: {str(e)}")

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
    source_lang: str = Form("auto"),
    bg: BackgroundTasks = None
):
    try:
        m = load_model()
        suffix = os.path.splitext(file.filename)[1]
        
        tmp_audio = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
        tmp_audio.write(await file.read())
        tmp_audio.close()

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

        translate_source = info.language if source_lang == "auto" else source_lang
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
                        await asyncio.sleep(0.04)
                    except Exception:
                        final_text = txt

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

@app.post("/transcribe-url")
async def transcribe_url(
    url: str = Form(...),
    source_lang: str = Form("auto"),
    bg: BackgroundTasks = None
):
    try:
        m = load_model()
        
        # สร้างโฟลเดอร์ชั่วคราวสำหรับเก็บไฟล์ที่โหลดจากเน็ต
        temp_dir = tempfile.mkdtemp()
        
        print(f"📥 กำลังดาวน์โหลดจาก: {url}")
        audio_path = download_audio_from_url(url, temp_dir)
        
        whisper_lang = None if source_lang == "auto" else source_lang
        
        print(f"🔍 กำลังถอดความ (โหมด: {source_lang})...")
        segments, info = m.transcribe(
            audio_path, 
            language=whisper_lang, 
            task="transcribe",
            beam_size=5, 
            vad_filter=True
        )
        
        seg_list = list(segments)
        if not seg_list:
            raise HTTPException(status_code=400, detail="ไม่พบข้อความในไฟล์")

        translate_source = info.language if source_lang == "auto" else source_lang
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
                        await asyncio.sleep(0.04)
                    except Exception:
                        final_text = txt

            srt_lines.append(f"{i}\n{format_srt_time(seg.start)} --> {format_srt_time(seg.end)}\n{final_text}\n")

        tmp_srt = tempfile.NamedTemporaryFile(delete=False, suffix="_TH.srt", mode="w", encoding="utf-8")
        tmp_srt.write("\n".join(srt_lines))
        tmp_srt.close()

        # ลบไฟล์เสียงชั่วคราวและโฟลเดอร์หลังเสร็จ
        bg.add_task(cleanup, [audio_path, tmp_srt.name])
        try: os.rmdir(temp_dir)
        except: pass

        print(f"✅ เสร็จสิ้น! แปลจาก {translate_source.upper()} เป็น TH")

        return FileResponse(
            tmp_srt.name,
            filename="subtitle_TH.srt",
            media_type="application/x-subrip"
        )
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ Backend Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))