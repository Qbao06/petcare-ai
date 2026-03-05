import time
import requests
from datetime import datetime, timedelta
import os

# ============== CẤU HÌNH ==============

BOT_TOKEN = "8543773794:AAGKKREdGX0MTwnVyjDPM962NyqVBPQS9BI"
API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}/"   # ⚠️ CÓ DẤU / Ở CUỐI

# 🔹 Danh sách người nhận báo cáo
CHAT_IDS = [5901770735, 8026663270]

LOG_FILE = "violence_log.txt"
offset = None


# ============== GỬI TIN ==============

def broadcast(text: str):
    """Gửi text đến tất cả chat id."""
    for cid in CHAT_IDS:
        try:
            r = requests.post(
                API_URL + "sendMessage",
                data={"chat_id": cid, "text": text},
                timeout=10
            )
            print(f"Sent to {cid}: {r.status_code}, {r.text}")
        except Exception as e:
            print(f"Lỗi gửi tới {cid}: {e}")


def send_file(file_path: str, caption: str = ""):
    """Gửi file kèm caption (nếu báo cáo quá dài)."""
    for cid in CHAT_IDS:
        try:
            with open(file_path, "rb") as f:
                r = requests.post(
                    API_URL + "sendDocument",
                    data={"chat_id": cid, "caption": caption},
                    files={"document": f},
                    timeout=20
                )
            print(f"send_file -> {cid}: {r.status_code}, {r.text}")
        except Exception as e:
            print(f"Lỗi gửi file tới {cid}: {e}")


# ============== LỌC DÒNG CẢNH BÁO ==============

def is_alert_line(msg: str) -> bool:
    """Chỉ nhận những dòng có chữ alert hoặc cảnh báo."""
    m = msg.lower()
    return ("alert" in m) or ("cảnh báo" in m) or ("canh bao" in m)


def read_alert_list(days: int):
    """
    Trả về DANH SÁCH ĐẦY ĐỦ thời điểm cảnh báo trong N ngày gần nhất.
    """
    if not os.path.exists(LOG_FILE):
        return "Không có dữ liệu log.", None

    cutoff = datetime.now() - timedelta(days=days)
    alert_times = []

    with open(LOG_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if len(line) < 20:
                continue

            # Tách timestamp và nội dung
            parts = line.split(" - ", 1)
            if len(parts) < 2:
                continue

            ts_str, msg = parts[0], parts[1]

            # Không phải cảnh báo → bỏ qua
            if not is_alert_line(msg):
                continue

            # Parse thời gian
            try:
                ts = datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                continue

            # Chỉ lấy trong khoảng thời gian yêu cầu
            if ts >= cutoff:
                alert_times.append(ts)

    if not alert_times:
        return f"Không có cảnh báo nào trong {days} ngày gần nhất.", None

    # Sắp xếp tăng dần (cũ → mới)
    alert_times.sort()

    # Chuẩn bị output
    header = f"Danh sách NGÀY GIỜ cảnh báo trong {days} ngày:\n\n"
    body = "\n".join(ts.strftime("%Y-%m-%d %H:%M:%S") for ts in alert_times)
    report = header + body

    # Nếu quá dài → gửi file
    if len(report) > 3500:
        file_path = "alert_list.txt"
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(report)
        return "Danh sách dài → gửi file alert_list.txt", file_path

    return report, None


# ============== XỬ LÝ LỆNH ==============

def handle_command(text: str):
    text = text.strip().lower()

    if text in ("/start", "/help"):
        broadcast(
            "🤖 Bot thống kê NGÀY GIỜ CẢNH BÁO\n"
            "/today  - danh sách cảnh báo hôm nay\n"
            "/week   - danh sách cảnh báo 7 ngày gần nhất\n"
            "/month  - danh sách cảnh báo 30 ngày gần nhất"
        )
        return

    if text == "/today":
        msg, fp = read_alert_list(1)
    elif text == "/week":
        msg, fp = read_alert_list(7)
    elif text == "/month":
        msg, fp = read_alert_list(30)
    else:
        broadcast("Lệnh không hợp lệ. Gõ /help.")
        return

    if fp:
        send_file(fp, caption=msg)
    else:
        broadcast(msg)


# ============== MAIN LOOP ==============

def main():
    global offset
    broadcast("Bot thống kê cảnh báo đã khởi động.")
    print("Bot is running...")

    while True:
        try:
            resp = requests.get(
                API_URL + "getUpdates",
                params={"timeout": 20, "offset": offset},
                timeout=25,
            )

            try:
                data = resp.json()
            except Exception as e:
                print("Không parse được JSON từ Telegram:", e, resp.text)
                time.sleep(3)
                continue

            if not data.get("ok", False):
                print("Lỗi Telegram:", data)
                time.sleep(3)
                continue

            results = data.get("result", [])

            for update in results:
                offset = update["update_id"] + 1

                msg = update.get("message")
                if not msg:
                    continue

                text = msg.get("text", "")
                if text:
                    print("Nhận lệnh:", text)
                    handle_command(text)

        except Exception as e:
            print("Lỗi getUpdates:", e)
            time.sleep(3)


if __name__ == "__main__":
    main()
