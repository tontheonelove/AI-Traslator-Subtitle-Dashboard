@echo off
title Project Updater
chcp 65001 >nul 2>&1

echo ==========================
echo   🔄 Updating Project Source...
echo ==========================
echo.

:: 1. ตรวจสอบ Git
git --version >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ ERROR: ไม่พบ Git ในระบบ
    pause
    exit /b 1
)

:: 2. ดึงข้อมูลล่าสุดจาก Remote (Fetch)
echo 📥 กำลังตรวจสอบข้อมูลล่าสุดจาก GitHub...
git fetch origin

:: 3. บังคับให้ไฟล์ในเครื่องตรงกับ GitHub เป๊ะๆ (Hard Reset)
:: คำสั่งนี้จะลบการแก้ไขใดๆ ในเครื่องทิ้ง แล้วเอาไฟล์จาก GitHub มาแทนที่ทั้งหมด
echo 🧹 กำลังล้างการแก้ไขในเครื่องและอัปเดตไฟล์...
git reset --hard origin/main

:: 4. ลบไฟล์ขยะที่ไม่มีใน GitHub (เช่น ไฟล์ temp, venv เก่าๆ ที่ไม่ได้ ignore)
echo 🗑️ กำลังทำความสะอาดไฟล์ส่วนเกิน...
git clean -fd

echo.
echo ==========================
echo   ✅ Update Complete!
echo ==========================
echo.
echo 💡 ไฟล์ในเครื่องถูกแทนที่ด้วยเวอร์ชันล่าสุดจาก GitHub แล้ว
echo    กรุณาปิดโปรแกรมเก่าแล้วรัน run.bat ใหม่เสมอ
echo.
pause >null