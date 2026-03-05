import cv2
from ultralytics import YOLO
import numpy as np
import time
import os
from datetime import datetime
import requests
import serial
from serial.tools import list_ports   # Dò COM
import torch
import sounddevice as sd              # MIC
import sys

# ===== CHỐNG LỖI UNICODE TRÊN WINDOWS =====
try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    pass

# ================== CẤU HÌNH ==================

ESP32_PORT = None         # None -> tự dò; hoặc đặt "COM5" đúng cổng ESP32
ESP32_BAUD = 115200

# ===== TELEGRAM =====
# ⚠️ THAY TOKEN NÀY BẰNG TOKEN MỚI LẤY TỪ BOTFATHER
TELEGRAM_BOT_TOKEN = "8543773794:AAGKKREdGX0MTwnVyjDPM962NyqVBPQS9BI"

TELEGRAM_PHOTO_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
TELEGRAM_SESSION = requests.Session()

# 🔹 DANH SÁCH CÁC CHAT ID CẦN GỬI ẢNH
TELEGRAM_CHAT_IDS = [
    5901770735,   # tài khoản 1
    8026663270,   # tài khoản 2 (Steam)
]

SAVE_FOLDER = "captures"
os.makedirs(SAVE_FOLDER, exist_ok=True)

LOG_FILE = "violence_log.txt"

ALERT_COOLDOWN = 10       # giây
IMG_SIZE       = 384
DETECT_EVERY   = 2        # chỉ detect mỗi 2 frame

# ====== CẤU HÌNH MIC ======
MIC_DURATION     = 0.10
MIC_SAMPLE_RATE  = 44100
NOISE_EVERY      = 5      # đo tiếng ồn mỗi 5 frame
NOISE_THRESHOLD  = 0.25   # 25%

MIC_DEVICE_INDEX = None

# Để giảm spam log UART
UART_LOG_INTERVAL = 1.0   # giây


# ================== HÀM PHỤ ==================

def log_event(msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"{ts} - {msg}"
    try:
        print(line)
    except UnicodeEncodeError:
        safe = line.encode("utf-8", errors="replace").decode("utf-8", errors="replace")
        print(safe)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def save_frame(frame, prefix="capture"):
    now = datetime.now()
    ts_file = now.strftime("%Y%m%d_%H%M%S")
    ts_human = now.strftime("%Y-%m-%d %H:%M:%S")
    img_name = f"{prefix}_{ts_file}.jpg"
    img_path = os.path.join(SAVE_FOLDER, img_name)

    if cv2.imwrite(img_path, frame):
        log_event(f"Đã lưu ảnh: {img_path}")
    else:
        log_event(f"LỖI khi lưu ảnh: {img_path}")

    return img_path, ts_human


def send_telegram_photo(image_path: str, caption: str | None = None) -> bool:
    """
    Gửi 1 ảnh cho TẤT CẢ chat id trong TELEGRAM_CHAT_IDS.
    Trả về True nếu gửi thành công cho ít nhất 1 người.
    Ghi log chi tiết để dễ debug.
    """
    if caption is None:
        caption = f"Ảnh gửi lúc {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

    ok_any = False

    for chat_id in TELEGRAM_CHAT_IDS:
        try:
            with open(image_path, "rb") as f:
                files = {"photo": f}
                data = {"chat_id": chat_id, "caption": caption}
                r = TELEGRAM_SESSION.post(
                    TELEGRAM_PHOTO_URL,
                    files=files,
                    data=data,
                    timeout=10
                )

            if r.status_code == 200:
                log_event(f"[TELEGRAM] Đã gửi ảnh OK cho chat_id={chat_id}: {image_path}")
                ok_any = True
            else:
                log_event(
                    f"[TELEGRAM] LỖI gửi ảnh cho chat_id={chat_id}: "
                    f"status={r.status_code}, resp={r.text}"
                )

        except Exception as e:
            log_event(f"[TELEGRAM] EXCEPTION khi gửi ảnh cho chat_id={chat_id}: {e}")

    return ok_any


# ====== UART ESP32 ======

def find_esp32_port(preferred: str | None = None) -> str | None:
    ports = list(list_ports.comports())
    if not ports:
        log_event("KHÔNG tìm thấy cổng COM nào trên máy!")
        return None

    log_event("Danh sách cổng COM phát hiện được:")
    for p in ports:
        log_event(f" - {p.device}: {p.description} | {p.hwid}")

    if preferred:
        pref_upper = preferred.upper()
        for p in ports:
            if p.device.upper() == pref_upper:
                log_event(f"Ưu tiên dùng cổng cấu hình sẵn: {p.device}")
                return p.device

    candidates = []
    for p in ports:
        desc = (p.description or "").lower()
        hwid = (p.hwid or "").lower()
        if ("usb" in desc or "uart" in desc or "ch340" in desc or
            "cp210" in desc or "silicon labs" in desc or "jtag/serial" in desc or
            "cdc" in desc or "esp" in desc or
            "1a86:" in hwid or "10c4:" in hwid or "303a:" in hwid):
            candidates.append(p.device)

    if len(candidates) == 1:
        log_event(f"Tự nhận diện được 1 cổng phù hợp: {candidates[0]}")
        return candidates[0]
    elif len(candidates) > 1:
        log_event("Nhiều cổng có vẻ là USB-serial, chọn tạm cổng đầu tiên:")
        for c in candidates:
            log_event(f"  + {c}")
        return candidates[0]

    first_port = ports[0].device
    log_event(f"Không nhận diện được cổng nào rõ ràng là ESP32, dùng tạm cổng đầu tiên: {first_port}")
    return first_port


def open_serial():
    try:
        port = find_esp32_port(preferred=ESP32_PORT)
        if port is None:
            log_event("Không có cổng nào để mở UART, bỏ qua kết nối ESP32.")
            return None
        ser = serial.Serial(port, ESP32_BAUD, timeout=0.1)
        log_event(f"Kết nối ESP32 qua {port} OK")
        return ser
    except Exception as e:
        log_event(f"KHÔNG MỞ ĐƯỢC CỔNG ESP32: {e}")
        return None


def read_esp32_logs(ser):
    if ser is None or not ser.is_open:
        return
    try:
        for _ in range(10):
            if ser.in_waiting <= 0:
                break
            line = ser.readline().decode(errors="ignore").strip()
            if line:
                log_event(f"[ESP32] {line}")
    except Exception:
        pass


def uart_send(ser, data: str, log_msg: str | None = None):
    if ser is None or not ser.is_open:
        if log_msg:
            log_event(log_msg + " (UART chưa mở)")
        return
    try:
        ser.write((data + "\n").encode())
        if log_msg:
            log_event(log_msg)
    except Exception as e:
        if log_msg:
            log_event(f"{log_msg} | LỖI UART: {e}")
        else:
            log_event(f"[UART] LỖI gửi '{data}': {e}")


def do_full_alert(frame, ser, reason="AUTO_RULE"):
    if ser is not None and ser.is_open:
        try:
            ser.write(b'A')
            log_event(f"[{reason}] Đã gửi 'A' cho ESP32 qua UART")
        except Exception as e:
            log_event(f"[{reason}] LỖI khi gửi UART: {e}")
    else:
        log_event(f"[{reason}] UART chưa mở, không gửi được cho ESP32")

    img_path, ts_human = save_frame(frame, prefix=reason.lower())
    caption = f"{reason}: Cảnh báo lúc {ts_human}"
    send_telegram_photo(img_path, caption)


# ====== TỰ DÒ WEBCAM (ƯU TIÊN USB CAMERA) ======

def find_camera_index(max_index=5):
    log_event("Đang dò webcam...")

    usb_cam = None
    fallback_cam = None

    for idx in range(max_index):
        cap = cv2.VideoCapture(idx, cv2.CAP_DSHOW)
        if not cap.isOpened():
            cap.release()
            continue
        ret, _ = cap.read()
        cap.release()

        if ret:
            log_event(f"Phát hiện camera hoạt động: index {idx}")
            if idx > 0 and usb_cam is None:
                usb_cam = idx
            if fallback_cam is None:
                fallback_cam = idx

    if usb_cam is not None:
        log_event(f"Ưu tiên dùng USB Camera tại index {usb_cam}")
        return usb_cam
    if fallback_cam is not None:
        log_event(f"Dùng tạm camera đầu tiên: index {fallback_cam}")
        return fallback_cam

    log_event("KHÔNG tìm thấy webcam!!!")
    return None


# ====== TỰ DÒ MICRO (ƯU TIÊN MIC WEBCAM) ======

def find_microphone_device():
    try:
        devices = sd.query_devices()
    except Exception as e:
        log_event(f"LỖI liệt kê thiết bị âm thanh: {e}")
        return None

    log_event("Danh sách thiết bị âm thanh (input):")
    webcam_candidates = []
    first_input = None

    for idx, dev in enumerate(devices):
        if dev['max_input_channels'] > 0:
            if first_input is None:
                first_input = idx
            name = dev['name']
            log_event(f" - #{idx}: {name} (in={dev['max_input_channels']}, out={dev['max_output_channels']})")
            low = name.lower()
            if any(s in low for s in ["webcam", "camera", "usb"]):
                webcam_candidates.append(idx)

    if webcam_candidates:
        chosen = webcam_candidates[0]
        log_event(f"Ưu tiên chọn MIC webcam: device #{chosen}")
        return chosen

    default_dev = sd.default.device
    default_input = None
    if isinstance(default_dev, (list, tuple)):
        default_input = default_dev[0]
    else:
        default_input = default_dev

    if default_input is not None and default_input != -1:
        log_event(f"Dùng MIC default của hệ thống: device #{default_input}")
        return default_input

    if first_input is not None:
        log_event(f"Dùng đại MIC đầu tiên: device #{first_input}")
        return first_input

    log_event("KHÔNG tìm thấy MIC nào có input_channels > 0!")
    return None


# ===== SKELETON (người que) =====
SKELETON_PAIRS = [
    (5, 7), (7, 9),
    (6, 8), (8,10),
    (11,13), (13,15),
    (12,14), (14,16),
    (5, 6),
    (11,12),
    (5,11), (6,12),
    (0, 5), (0, 6)
]

def draw_skeleton(img, kpts, raised=False):
    for (i1, i2) in SKELETON_PAIRS:
        x1, y1, c1 = kpts[i1]
        x2, y2, c2 = kpts[i2]
        if c1 > 0.2 and c2 > 0.2:
            cv2.line(img, (int(x1), int(y1)), (int(x2), int(y2)), (0, 255, 255), 2)

    for i, (x, y, c) in enumerate(kpts):
        if c < 0.2:
            continue
        center = (int(x), int(y))
        if i in (9, 10):
            color = (0, 0, 255) if raised else (255, 0, 0)
            radius = 6
        else:
            color = (0, 255, 0)
            radius = 4
        cv2.circle(img, center, radius, color, -1)


def has_raised_hand(person_kpts):
    def get_point(idx):
        return person_kpts[idx]
    try:
        _, nose_y, nose_c = get_point(0)
        _, ls_y, ls_c    = get_point(5)
        _, rs_y, rs_c    = get_point(6)
        _, lw_y, lw_c    = get_point(9)
        _, rw_y, rw_c    = get_point(10)
    except Exception:
        return False

    if nose_c < 0.2 or ls_c < 0.2 or rs_c < 0.2:
        return False

    shoulder_y = min(ls_y, rs_y)
    left_up  = (lw_c > 0.2) and (lw_y < nose_y or lw_y < shoulder_y)
    right_up = (rw_c > 0.2) and (rw_y < nose_y or rw_y < shoulder_y)
    return left_up or right_up


# ====== ĐỌC MỨC TIẾNG ỒN TỪ MIC ======

def get_noise_level():
    global MIC_DEVICE_INDEX
    try:
        audio = sd.rec(
            int(MIC_DURATION * MIC_SAMPLE_RATE),
            samplerate=MIC_SAMPLE_RATE,
            channels=1,
            dtype='float32',
            device=MIC_DEVICE_INDEX
        )
        sd.wait()
        rms = float(np.sqrt(np.mean(audio ** 2)))
        return max(0.0, min(rms, 1.0))
    except Exception as e:
        log_event(f"LỖI MICRO: {e}")
        return 0.0


def draw_help_panel(frame, show_help, auto_alert, noise_threshold):
    if not show_help:
        return

    h, w = frame.shape[:2]
    x0, y0 = 10, h - 170
    overlay = frame.copy()
    cv2.rectangle(overlay, (x0, y0 - 90), (x0 + 460, y0 + 60), (0, 0, 0), -1)
    frame[:] = cv2.addWeighted(overlay, 0.4, frame, 0.6, 0)

    noise_th_percent = int(noise_threshold * 100)

    lines = [
        f"[AUTO ALERT]: {'ON' if auto_alert else 'OFF'} (phím 'a' bật/tắt)",
        f"[NOISE THRESH]: {noise_th_percent}% (z/x giảm/tăng)",
        "Phím: ESC/q = Thoát",
        "      1 = Test UART 'A' -> ESP32",
        "      2 = Test chụp & lưu ảnh",
        "      3 = Test chụp & gửi Telegram (kèm thời gian)",
        "      4 = FULL TEST (UART + ảnh + Telegram + thời gian)",
        "      h = Bật/tắt bảng hướng dẫn"
    ]
    dy = 20
    for i, text in enumerate(lines):
        cv2.putText(frame, text, (x0 + 10, y0 - 70 + i * dy),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)


# ================== MAIN ==================

def main():
    global NOISE_THRESHOLD, MIC_DEVICE_INDEX

    ser = open_serial()

    MIC_DEVICE_INDEX = find_microphone_device()
    if MIC_DEVICE_INDEX is not None:
        log_event(f"MIC được chọn: device #{MIC_DEVICE_INDEX}")
    else:
        log_event("Không chọn được MIC cụ thể, dùng default của hệ thống.")

    cam_index = find_camera_index()
    if cam_index is None:
        log_event("Không tìm được webcam để mở, dừng chương trình.")
        return
    log_event(f"Dùng webcam index: {cam_index}")

    device = "cuda" if torch.cuda.is_available() else "cpu"
    log_event(f"Dùng device: {device}")

    model = YOLO("yolov8n-pose.pt")
    model.to(device)
    try:
        model.fuse()
        log_event("Đã fuse model để tăng tốc.")
    except Exception:
        pass

    cap = cv2.VideoCapture(cam_index, cv2.CAP_DSHOW)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

    prev_time = time.time()
    last_alert_time = 0.0
    frame_idx = 0

    last_boxes = []
    last_kpts  = []

    auto_alert_enabled = True
    show_help = True

    last_noise = 0.0

    last_sent_noise = -1
    last_sent_th    = -1
    last_uart_log   = 0.0

    if ser is not None and ser.is_open:
        try:
            th_percent = int(NOISE_THRESHOLD * 100)
            ser.write(f"T{th_percent:03d}\n".encode())
            log_event(f"[UART] Gửi ngưỡng ban đầu T{th_percent:03d}")
            last_sent_th = th_percent
        except Exception as e:
            log_event(f"[UART] Lỗi gửi ngưỡng ban đầu: {e}")

    with torch.inference_mode():
        while True:
            ret, frame = cap.read()
            if not ret:
                log_event("Không đọc được frame từ camera, dừng.")
                break

            frame_idx += 1
            run_detect = (frame_idx % DETECT_EVERY == 0)

            noise_updated = False
            if frame_idx % NOISE_EVERY == 0:
                last_noise = get_noise_level()
                noise_updated = True

            noise = last_noise
            noise_percent = int(noise * 100)
            noise_th_percent = int(NOISE_THRESHOLD * 100)

            if ser is not None and ser.is_open and noise_updated:
                try:
                    now = time.time()
                    ser.write(f"N{noise_percent:03d}\n".encode())
                    if noise_th_percent != last_sent_th:
                        ser.write(f"T{noise_th_percent:03d}\n".encode())
                        last_sent_th = noise_th_percent

                    if now - last_uart_log > UART_LOG_INTERVAL:
                        log_event(f"[UART] Gui N{noise_percent:03d}, T{noise_th_percent:03d}")
                        last_uart_log = now

                    last_sent_noise = noise_percent
                except Exception as e:
                    log_event(f"[UART] Lỗi gửi N/T: {e}")

                read_esp32_logs(ser)

            if run_detect:
                results = model(
                    frame,
                    imgsz=IMG_SIZE,
                    conf=0.4,
                    verbose=False,
                    device=device,
                    classes=[0]
                )

                last_boxes.clear()
                last_kpts.clear()
                num_person = 0
                has_any_raised_hand = False

                for r in results:
                    kpts_tensor = r.keypoints
                    if kpts_tensor is None:
                        continue

                    boxes = r.boxes.xyxy.cpu().numpy()
                    kpts  = kpts_tensor.data.cpu().numpy()

                    for i in range(len(boxes)):
                        x1, y1, x2, y2 = boxes[i].astype(int)
                        person_kpts = kpts[i]

                        num_person += 1
                        raised = has_raised_hand(person_kpts)
                        if raised:
                            has_any_raised_hand = True

                        last_boxes.append((x1, y1, x2, y2, raised))
                        last_kpts.append(person_kpts)

                pose_alert = has_any_raised_hand and num_person >= 2
            else:
                num_person = len(last_boxes)
                has_any_raised_hand = any(b[4] for b in last_boxes)
                pose_alert = has_any_raised_hand and num_person >= 2

            for (x1, y1, x2, y2, raised), kpts in zip(last_boxes, last_kpts):
                box_color = (0, 255, 0) if not raised else (0, 0, 255)
                cv2.rectangle(frame, (x1, y1), (x2, y2), box_color, 2)
                draw_skeleton(frame, kpts, raised=raised)
                label = "Person"
                if raised:
                    label += " - RAISED HAND"
                cv2.putText(frame, label, (x1, max(y1 - 10, 20)),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, box_color, 2)

            noise_alert = noise > NOISE_THRESHOLD

            info_text = f"Persons: {num_person}"
            if pose_alert:
                info_text += " | POSE ALERT!"
            if noise_alert:
                info_text += " | NOISE ALERT!"

            info_color = (0, 0, 255) if (pose_alert or noise_alert) else (255, 255, 255)

            cur_time = time.time()
            fps = 1.0 / max(cur_time - prev_time, 1e-6)
            prev_time = cur_time

            cv2.putText(frame, info_text, (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, info_color, 2)
            cv2.putText(frame, f"FPS: {fps:.1f}", (10, 60),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)

            cv2.putText(frame, f"Noise: {noise_percent}% (TH: {noise_th_percent}%)", (10, 90),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 200, 255), 2)

            auto_rule_ok = pose_alert and noise_alert

            if auto_alert_enabled and auto_rule_ok and run_detect:
                if cur_time - last_alert_time > ALERT_COOLDOWN:
                    last_alert_time = cur_time
                    reason = "AUTO_POSE+NOISE"
                    log_event(f"[{reason}] Kích hoạt cảnh báo tự động")
                    do_full_alert(frame, ser, reason=reason)

            draw_help_panel(frame, show_help, auto_alert_enabled, NOISE_THRESHOLD)
            cv2.imshow("School Violence Pose + Sound (Multi Telegram)", frame)

            key = cv2.waitKey(1) & 0xFF

            if key == 27 or key == ord('q'):
                log_event("Nhấn ESC/q -> thoát chương trình.")
                break

            elif key == ord('1'):
                if ser is not None and ser.is_open:
                    try:
                        ser.write(b'A')
                        log_event("[TEST_1] Gửi 'A' cho ESP32 (test UART)")
                    except Exception as e:
                        log_event(f"[TEST_1] Lỗi UART: {e}")
                else:
                    log_event("[TEST_1] UART chưa mở, không gửi được")

            elif key == ord('2'):
                log_event("[TEST_2] Lưu ảnh test (chỉ lưu, không gửi Telegram)")
                save_frame(frame, prefix="TEST_ONLY_SAVE")

            elif key == ord('3'):
                log_event("[TEST_3] Lưu ảnh + gửi Telegram (test bot)")
                img_path, ts_human = save_frame(frame, prefix="TEST_TELEGRAM")
                caption = f"TEST_3: Ảnh test gửi lúc {ts_human}"
                send_telegram_photo(img_path, caption)

            elif key == ord('4'):
                log_event("[TEST_4] FULL TEST: UART + Lưu ảnh + Telegram")
                do_full_alert(frame, ser, reason="MANUAL_TEST")

            elif key == ord('a'):
                auto_alert_enabled = not auto_alert_enabled
                log_event(f"[TOGGLE] AUTO ALERT = {auto_alert_enabled}")

            elif key == ord('h'):
                show_help = not show_help
                log_event(f"[TOGGLE] SHOW_HELP = {show_help}")

            elif key == ord('z'):
                NOISE_THRESHOLD = max(0.0, NOISE_THRESHOLD - 0.05)
                log_event(f"[NOISE] Giảm ngưỡng: {NOISE_THRESHOLD:.2f} (~{int(NOISE_THRESHOLD*100)}%)")
                if ser is not None and ser.is_open:
                    try:
                        th_percent = int(NOISE_THRESHOLD * 100)
                        ser.write(f"T{th_percent:03d}\n".encode())
                        last_sent_th = th_percent
                    except Exception:
                        pass

            elif key == ord('x'):
                NOISE_THRESHOLD = min(1.0, NOISE_THRESHOLD + 0.05)
                log_event(f"[NOISE] Tăng ngưỡng: {NOISE_THRESHOLD:.2f} (~{int(NOISE_THRESHOLD*100)}%)")
                if ser is not None and ser.is_open:
                    try:
                        th_percent = int(NOISE_THRESHOLD * 100)
                        ser.write(f"T{th_percent:03d}\n".encode())
                        last_sent_th = th_percent
                    except Exception:
                        pass

    cap.release()
    cv2.destroyAllWindows()
    if ser is not None and ser.is_open:
        ser.close()
        log_event("Đã đóng cổng UART.")


if __name__ == "__main__":
    main()
