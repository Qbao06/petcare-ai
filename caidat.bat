@echo off
title Installing Dependencies + Starting Violence Detection System
color 0a

echo ================================================
echo  KIEM TRA PYTHON
echo ================================================
python --version >nul 2>&1
IF %ERRORLEVEL% NEQ 0 (
    echo Python CHUA DUOC CAI!
    echo Vui long cai Python 3.10+ roi chay lai file BAT.
    pause
    exit /b
)

echo.
echo ================================================
echo  CAI DAT CAC THU VIEN CAN THIET
echo ================================================
echo (Qua trinh nay co the mat 3-5 phut...)
echo.

pip install --upgrade pip
pip install ultralytics
pip install opencv-python
pip install numpy
pip install requests
pip install pyserial
pip install sounddevice
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu118

echo.
echo ================================================
echo  CAI DAT HOAN TAT
echo ================================================
echo.

echo ================================================
echo  KHOI DONG CHUONG TRINH NHAN DIEN (AI)
echo ================================================
start "" python violence_detect.py

echo ================================================
echo  KHOI DONG BOT THONG KE LOG TELEGRAM
echo ================================================
start "" python violence_log_bot_multi.py

echo.
echo ================================================
echo  HE THONG DA CHAY TOAN BO!
echo  KHONG DONG CUA SO NAY DE TRÁNH TAT CHUONG TRINH.
echo ================================================
pause
