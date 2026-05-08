@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul 2>&1

echo ========================================
echo   🚀 Subtitle AI Dashboard
echo ========================================
echo.

:: 1. ตรวจสอบ Python
echo 🔍 กำลังตรวจสอบ Python...
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ ERROR: ไม่พบ Python ในระบบ
    echo  แก้ไข: ดาวน์โหลด Python 3.10+ จาก python.org
    echo    ✅ สำคัญ: ตอนติดตั้งต้องติ๊ก "Add Python to PATH"
    pause
    exit /b 1
)

:: 2. สร้าง/ตรวจสอบ venv
if not exist "venv" (
    echo 📦 กำลังสร้าง Virtual Environment ครั้งแรก...
    python -m venv venv
    if !errorlevel! neq 0 (
        echo ❌ ERROR: สร้าง venv ล้มเหลว
        pause
        exit /b 1
    )
) else (
    echo ✅ พบ Virtual Environment เรียบร้อย
)

:: 3. ติดตั้ง Library
echo 📥 กำลังติดตั้ง/อัปเดต Library...
"venv\Scripts\python.exe" -m pip install --upgrade pip >nul 2>&1
"venv\Scripts\python.exe" -m pip install -r requirements.txt
if !errorlevel! neq 0 (
    echo ❌ ERROR: ติดตั้ง Library ไม่สำเร็จ
    echo 💡 ตรวจสอบ: การเชื่อมต่ออินเทอร์เน็ต หรือ ไฟล์ requirements.txt
    pause
    exit /b 1
)

:: 4. รันเซิร์ฟเวอร์
echo.
echo ✅ ระบบพร้อม! กำลังเปิด Dashboard...
echo  เปิดเบราว์เซอร์ไปที่: http://127.0.0.1:8000
echo 💡 กด Ctrl+C ในหน้าต่างนี้เพื่อปิดโปรแกรม
echo ========================================
echo.

"venv\Scripts\python.exe" -m uvicorn main:app --host 127.0.0.1 --port 8000 --log-level info
pause