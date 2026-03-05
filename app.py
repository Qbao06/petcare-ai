import os
import json
from datetime import datetime

import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt

from excel_logger import append_log_row, ExcelLockedError
from gemini_vision import extract_signs_from_image
from rules import diagnose

APP_NAME = "PetCare AI"
EXCEL_PATH = "pet_ai_log.xlsx"

SYMPTOMS_GROUPS = {
    "Da/Lông": [
        ("ngứa_gãi_nhiều", "Ngứa, gãi nhiều"),
        ("rụng_lông", "Rụng lông"),
        ("mảng_tròn_rụng_lông", "Mảng tròn rụng lông"),
        ("đỏ_da", "Đỏ da"),
        ("có_vảy_gàu", "Có vảy/gàu"),
        ("ướt_da_mùi_hôi", "Da ướt, mùi hôi/rỉ dịch"),
    ],
    "Mắt": [
        ("mắt_đỏ", "Mắt đỏ"),
        ("chảy_ghèn", "Chảy ghèn/dịch"),
        ("nheo_mắt", "Nheo mắt"),
        ("dụi_mắt", "Dụi mắt"),
    ],
    "Toàn thân": [
        ("bỏ_ăn", "Bỏ ăn"),
        ("lờ_đờ", "Lờ đờ"),
    ],
}

def inject_css():
    st.markdown(
        """
<style>
.block-container { padding-top: 1.1rem; padding-bottom: 2.0rem; }
small, .small { color: rgba(49,51,63,0.65) !important; }
.hero {
  border-radius: 20px;
  padding: 18px 18px;
  border: 1px solid rgba(49,51,63,0.10);
  background: linear-gradient(135deg, rgba(99,102,241,0.12), rgba(16,185,129,0.10));
}
.hero .t { font-weight: 950; font-size: 1.5rem; margin: 0; }
.hero .s { margin-top: 6px; color: rgba(49,51,63,0.70); }
.card {
  border: 1px solid rgba(49,51,63,0.10);
  border-radius: 18px;
  padding: 14px 16px;
  background: rgba(255,255,255,0.92);
  box-shadow: 0 10px 28px rgba(17, 24, 39, 0.06);
}
.kpi {
  border: 1px solid rgba(49,51,63,0.10);
  border-radius: 16px;
  padding: 12px 14px;
  background: rgba(255,255,255,0.85);
}
.kpi .k { color: rgba(49,51,63,0.65); font-size: 0.88rem; }
.kpi .v { font-weight: 950; font-size: 1.25rem; margin-top: 2px; }
.badge {
  display: inline-block;
  padding: 4px 10px;
  border-radius: 999px;
  font-weight: 950;
  font-size: 0.82rem;
  border: 1px solid rgba(49,51,63,0.14);
}
.alert-green { border-left: 6px solid #16a34a; }
.alert-yellow { border-left: 6px solid #f59e0b; }
.alert-red { border-left: 6px solid #ef4444; }
.row { display:flex; justify-content:space-between; align-items:center; margin-top: 8px; }
.name { font-weight: 850; }
.pct { font-weight: 950; color: rgba(49,51,63,0.75); }
hr { border: none; height: 1px; background: rgba(49,51,63,0.10); margin: 14px 0; }
.step {
  display:flex; gap:10px; align-items:center;
  padding: 10px 12px;
  border-radius: 14px;
  border: 1px solid rgba(49,51,63,0.10);
  background: rgba(255,255,255,0.78);
}
.dot {
  width: 30px; height: 30px; border-radius: 999px;
  display:flex; align-items:center; justify-content:center;
  font-weight: 950;
  border: 1px solid rgba(49,51,63,0.12);
}
.step .tx .h { font-weight: 950; }
.step .tx .d { color: rgba(49,51,63,0.65); font-size: 0.9rem; margin-top: 2px; }
</style>
        """,
        unsafe_allow_html=True,
    )

def alert_block(level: str):
    if level == "GREEN":
        cls, badge, head, detail = "alert-green", "XANH", "Nguy cơ thấp hơn", "Theo dõi thêm. Nếu xấu đi, chụp lại ảnh và đánh giá lại."
    elif level == "YELLOW":
        cls, badge, head, detail = "alert-yellow", "VÀNG", "Cần theo dõi sát", "Nếu không cải thiện trong 24–48h hoặc lan nhanh → nên đi thú y."
    else:
        cls, badge, head, detail = "alert-red", "ĐỎ", "Nên đi thú y sớm", "Có dấu hiệu nặng/nguy cơ biến chứng hoặc nhiễm trùng."
    st.markdown(
        f"""
<div class="card {cls}">
  <div style="font-weight:950;">Cảnh báo: <span class="badge">{badge}</span></div>
  <div style="font-weight:950; margin-top:6px;">{head}</div>
  <div class="s" style="color:rgba(49,51,63,0.70); margin-top:6px;">{detail}</div>
</div>
        """,
        unsafe_allow_html=True,
    )

def score_row(name: str, conf: float):
    pct = int(round(float(conf) * 100))
    st.markdown(
        f"""
<div class="row">
  <div class="name">{name}</div>
  <div class="pct">{pct}%</div>
</div>
        """,
        unsafe_allow_html=True,
    )
    st.progress(pct)

def read_history(path: str):
    if not os.path.exists(path):
        return None
    try:
        df = pd.read_excel(path, sheet_name="LOG")
        return df
    except Exception:
        return None

def get_image_payload(uploaded, cam):
    if cam is not None:
        b = cam.getvalue()
        mime = cam.type or "image/jpeg"
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        name = f"webcam_{ts}.jpg" if "jpeg" in mime or "jpg" in mime else f"webcam_{ts}.png"
        return b, mime, name, "Webcam"
    if uploaded is not None:
        b = uploaded.getvalue()
        mime = uploaded.type or "image/jpeg"
        name = uploaded.name or "upload.jpg"
        return b, mime, name, "Upload"
    return None, None, None, None

def kpi_box(k, v):
    st.markdown(
        f"""
<div class="kpi">
  <div class="k">{k}</div>
  <div class="v">{v}</div>
</div>
        """,
        unsafe_allow_html=True,
    )

def plot_alert_counts(df):
    if df is None or df.empty or "alert" not in df.columns:
        return None
    s = df["alert"].fillna("UNKNOWN").astype(str).value_counts()
    labels = list(s.index)
    values = list(s.values)
    fig = plt.figure()
    plt.bar(labels, values)
    plt.title("Tần suất mức cảnh báo")
    plt.xlabel("Mức")
    plt.ylabel("Số lần")
    return fig

def plot_top_diseases(df, topn=8):
    if df is None or df.empty or "top1" not in df.columns:
        return None
    s = df["top1"].fillna("UNKNOWN").astype(str).value_counts().head(topn)
    labels = list(s.index)[::-1]
    values = list(s.values)[::-1]
    fig = plt.figure()
    plt.barh(labels, values)
    plt.title("Top bệnh nghi ngờ (top1)")
    plt.xlabel("Số lần")
    return fig

st.set_page_config(page_title=APP_NAME, page_icon="🐾", layout="wide")
inject_css()

api_key = os.getenv("GEMINI_API_KEY", "")
if not api_key:
    st.error("Thiếu GEMINI_API_KEY. Hãy set biến môi trường rồi chạy lại.")
    st.stop()

df_hist = read_history(EXCEL_PATH)
total_logs = 0 if (df_hist is None or df_hist.empty) else int(len(df_hist))
last_ts = "-"
if df_hist is not None and not df_hist.empty and "timestamp" in df_hist.columns:
    try:
        last_ts = str(pd.to_datetime(df_hist["timestamp"], errors="coerce").max())
    except Exception:
        last_ts = str(df_hist["timestamp"].iloc[-1])

with st.sidebar:
    st.markdown("## 🐾 PetCare AI")
    page = st.radio("Điều hướng", ["🔎 Chẩn đoán", "📚 Lịch sử", "🧭 Hướng dẫn"], index=0)
    st.markdown("---")
    species = st.selectbox("Loài", ["Chó", "Mèo", "Không rõ"], index=0)
    age_months = st.number_input("Tuổi (tháng)", min_value=0, max_value=360, value=12, step=1)
    show_ai_details = st.toggle("Hiện JSON dấu hiệu", value=False)
    st.markdown("---")
    st.caption("Lưu ý: Đây là sàng lọc tham khảo, không thay thế bác sĩ thú y.")

st.markdown(
    f"""
<div class="hero">
  <div class="t">🐾 {APP_NAME}</div>
  <div class="s">Chụp ảnh (webcam) hoặc upload → chọn triệu chứng → hệ thống gợi ý khả năng & mức cảnh báo.</div>
</div>
    """,
    unsafe_allow_html=True,
)
st.write("")

k1, k2, k3 = st.columns(3)
with k1:
    kpi_box("Tổng lượt chẩn đoán (log)", total_logs)
with k2:
    kpi_box("Lần gần nhất", last_ts)
with k3:
    kpi_box("Nguồn ảnh", "Upload / Webcam")

st.write("")

if page == "🧭 Hướng dẫn":
    c1, c2 = st.columns([1.2, 1])
    with c1:
        st.markdown("### 3 bước nhanh")
        st.markdown(
            """
<div class="step"><div class="dot">1</div><div class="tx"><div class="h">Chọn ảnh</div><div class="d">Chụp webcam hoặc upload, ưu tiên cận cảnh và đủ sáng.</div></div></div>
<br/>
<div class="step"><div class="dot">2</div><div class="tx"><div class="h">Chọn triệu chứng</div><div class="d">Tick những dấu hiệu bạn quan sát được.</div></div></div>
<br/>
<div class="step"><div class="dot">3</div><div class="tx"><div class="h">Chẩn đoán</div><div class="d">Xem top nghi ngờ, mức cảnh báo và khuyến nghị.</div></div></div>
            """,
            unsafe_allow_html=True,
        )
    with c2:
        st.markdown("### Mẹo chụp")
        st.markdown(
            """
<div class="card">
• Lau sạch ống kính camera<br/>
• Đủ sáng, tránh ngược sáng<br/>
• Chụp sát vùng da/mắt, ảnh không rung<br/>
• Nếu có rỉ dịch/mùi hôi, ghi chú thêm triệu chứng<br/>
</div>
            """,
            unsafe_allow_html=True,
        )
    st.stop()

if page == "📚 Lịch sử":
    st.markdown("### Lịch sử chẩn đoán")
    if df_hist is None or df_hist.empty:
        st.info("Chưa có log.")
        st.stop()

    c1, c2 = st.columns(2)
    with c1:
        fig1 = plot_alert_counts(df_hist)
        if fig1 is not None:
            st.pyplot(fig1, clear_figure=True, use_container_width=True)
    with c2:
        fig2 = plot_top_diseases(df_hist, topn=10)
        if fig2 is not None:
            st.pyplot(fig2, clear_figure=True, use_container_width=True)

    st.write("")
    cols_show = [c for c in ["timestamp","species","age_months","top1","conf1","alert","image_name"] if c in df_hist.columns]
    st.dataframe(df_hist.sort_values(by="timestamp", ascending=False) if "timestamp" in df_hist.columns else df_hist,
                 use_container_width=True, hide_index=True)

    if os.path.exists(EXCEL_PATH):
        with open(EXCEL_PATH, "rb") as f:
            st.download_button(
                "⬇️ Tải Excel log",
                data=f,
                file_name=EXCEL_PATH,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )
    st.stop()

st.markdown("### 🔎 Chẩn đoán")
left, right = st.columns([1, 1])

with left:
    st.markdown("#### 1) Chọn ảnh")
    tab_up, tab_cam = st.tabs(["📤 Upload", "📷 Webcam"])
    uploaded = None
    cam = None

    with tab_up:
        uploaded = st.file_uploader(
            "Upload ảnh",
            type=["jpg", "jpeg", "png", "webp"],
            label_visibility="collapsed",
        )
        if uploaded:
            st.image(uploaded, use_container_width=True)
            st.caption("Gợi ý: cận cảnh, đủ sáng, không mờ.")
    with tab_cam:
        cam = st.camera_input("Chụp ảnh từ webcam", label_visibility="collapsed")
        if cam:
            st.image(cam, use_container_width=True)
            st.caption("Đưa vùng cần xem vào gần rồi bấm chụp.")

    if not uploaded and not cam:
        st.markdown(
            """
<div class="card">
  <div style="font-weight:950;">Chưa có ảnh</div>
  <div style="color:rgba(49,51,63,0.70); margin-top:6px;">Chọn Upload hoặc Webcam để chụp trực tiếp.</div>
</div>
            """,
            unsafe_allow_html=True,
        )

with right:
    st.markdown("#### 2) Chọn triệu chứng")
    selected = []
    for gname, items in SYMPTOMS_GROUPS.items():
        with st.expander(gname, expanded=(gname != "Toàn thân")):
            for key, label in items:
                if st.checkbox(label, key=f"sym_{key}", value=False):
                    selected.append(key)

    st.write("")
    img_bytes, mime, image_name, source_name = get_image_payload(uploaded, cam)
    run = st.button("🚀 3) Chẩn đoán ngay", type="primary", use_container_width=True, disabled=(img_bytes is None))

if run:
    with st.spinner("Đang phân tích ảnh..."):
        try:
            signs = extract_signs_from_image(img_bytes, mime)
        except Exception as e:
            st.error(f"Lỗi Gemini: {e}")
            st.stop()

    result = diagnose(set(selected), signs)
    top = result["top"]
    level = result["alert_level"]
    note = (signs.get("notes") or "").strip()

    st.write("")
    cA, cB = st.columns([1.2, 1])

    with cA:
        alert_block(level)
        if note:
            st.info(note)

        st.write("")
        st.markdown("#### Kết quả nghi ngờ (Top 3)")
        for item in top:
            score_row(item["disease"], item["confidence"])

        st.write("")
        st.markdown("#### Khuyến nghị")
        st.markdown(
            f"<div class='card'><pre style='margin:0;white-space:pre-wrap'>{result['recommendation']}</pre></div>",
            unsafe_allow_html=True,
        )

    with cB:
        st.markdown("#### Thông tin ca")
        st.markdown(
            f"""
<div class="card">
<b>Loài:</b> {species}<br/>
<b>Tuổi:</b> {int(age_months)} tháng<br/>
<b>Nguồn ảnh:</b> {source_name}<br/>
<b>Ảnh:</b> {image_name}<br/>
<b>Triệu chứng chọn:</b> {(", ".join(selected) if selected else "Không chọn")}<br/>
</div>
            """,
            unsafe_allow_html=True,
        )

        st.write("")
        st.markdown("#### Chi tiết AI")
        if show_ai_details:
            st.json(signs)
        else:
            st.caption("Bật “Hiện JSON dấu hiệu” ở thanh bên để xem.")

    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    row_dict = {
        "timestamp": ts,
        "species": species,
        "age_months": age_months,
        "symptoms": ",".join(selected),
        "signs_json": json.dumps(signs, ensure_ascii=False),
        "top1": top[0]["disease"],
        "conf1": top[0]["confidence"],
        "top2": top[1]["disease"],
        "conf2": top[1]["confidence"],
        "top3": top[2]["disease"],
        "conf3": top[2]["confidence"],
        "alert": level,
        "recommendation": result["recommendation"],
        "image_name": f"{source_name}:{image_name}",
    }

    st.write("")
    try:
        append_log_row(EXCEL_PATH, row_dict)
        st.success("Đã lưu log vào Excel.")
    except ExcelLockedError:
        st.warning("Không thể lưu vì file Excel đang mở. Hãy đóng Excel rồi thử lại.")
    except Exception as e:
        st.error(f"Lỗi lưu Excel: {e}")

    if os.path.exists(EXCEL_PATH):
        with open(EXCEL_PATH, "rb") as f:
            st.download_button(
                "⬇️ Tải Excel log",
                data=f,
                file_name=EXCEL_PATH,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )