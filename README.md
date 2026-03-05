# PetCare AI (Streamlit + Gemini + Excel)

## 1) Yêu cầu
- Python 3.10+ (khuyên 3.11)
- Có GEMINI_API_KEY (Gemini API key)

## 2) Cài đặt
pip install -r requirements.txt

## 3) Cấu hình API key
Windows PowerShell:
setx GEMINI_API_KEY "YOUR_KEY"
=> Mở terminal mới rồi chạy lại

macOS/Linux:
export GEMINI_API_KEY="YOUR_KEY"

## 4) Chạy
streamlit run app.py

## 5) Output
- Excel log: pet_ai_log.xlsx (sheet LOG)
- Download Excel ngay trên giao diện

## 6) Nếu lỗi thư viện Gemini (máy đã cài package cũ)
pip uninstall -y google-generativeai google-genai
pip install -r requirements.txt --upgrade

## 7) Lưu ý
Hệ thống sàng lọc tham khảo, không thay thế bác sĩ thú y và không kê thuốc.