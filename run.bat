@echo off
cd /d %~dp0

echo === PetCare AI ===

IF EXIST ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate
) ELSE (
    echo Khong tim thay moi truong ao .venv
    echo Hay chay install.bat truoc.
    pause
    exit
)

python -m streamlit run app.py

pause