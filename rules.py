def _clamp01(x: float) -> float:
    return 0.0 if x < 0 else 1.0 if x > 1 else x

def diagnose(symptoms: set[str], signs: dict) -> dict:
    s = symptoms

    # 1) NẤM DA (Ringworm)
    score_ring = 0
    score_ring += 4 if signs.get("circular_hair_loss") else 0
    score_ring += 2 if signs.get("scaly_skin") else 0
    score_ring += 2 if "mảng_tròn_rụng_lông" in s else 0
    score_ring += 1 if "có_vảy_gàu" in s else 0
    score_ring += 1 if "rụng_lông" in s else 0

    # 2) VIÊM DA / DỊ ỨNG DA
    score_derm = 0
    score_derm += 3 if signs.get("red_skin") else 0
    score_derm += 2 if signs.get("general_hair_loss") else 0
    score_derm += 2 if "ngứa_gãi_nhiều" in s else 0
    score_derm += 2 if "đỏ_da" in s else 0
    score_derm += 2 if "rụng_lông" in s else 0
    score_derm += 2 if signs.get("wet_infected_skin") else 0
    score_derm += 2 if "ướt_da_mùi_hôi" in s else 0

    # 3) VIÊM KẾT MẠC / KÍCH ỨNG MẮT
    score_eye = 0
    score_eye += 3 if signs.get("eye_redness") else 0
    score_eye += 3 if signs.get("eye_discharge") else 0
    score_eye += 2 if signs.get("squinting") else 0
    score_eye += 2 if "mắt_đỏ" in s else 0
    score_eye += 2 if "chảy_ghèn" in s else 0
    score_eye += 1 if ("dụi_mắt" in s or "nheo_mắt" in s) else 0

    conf_ring = _clamp01(score_ring / 10)
    conf_derm = _clamp01(score_derm / 12)
    conf_eye  = _clamp01(score_eye / 10)

    ranking = [
        {"disease": "NẤM DA (Ringworm)", "confidence": round(conf_ring, 2), "score": score_ring},
        {"disease": "VIÊM DA / DỊ ỨNG DA (Dermatitis/Allergy)", "confidence": round(conf_derm, 2), "score": score_derm},
        {"disease": "VIÊM KẾT MẠC / KÍCH ỨNG MẮT (Conjunctivitis)", "confidence": round(conf_eye, 2), "score": score_eye},
    ]
    ranking.sort(key=lambda x: x["confidence"], reverse=True)

    # Alert
    alert = "GREEN"
    if signs.get("wet_infected_skin") or (signs.get("squinting") and signs.get("eye_discharge")) or ("bỏ_ăn" in s and "lờ_đờ" in s):
        alert = "RED"
    elif ranking[0]["confidence"] >= 0.65:
        alert = "YELLOW"

    top1 = ranking[0]["disease"]
    if "NẤM DA" in top1:
        rec = (
            "- Cách ly thú nghi nấm (có thể lây sang thú khác và người).\n"
            "- Vệ sinh ổ nằm/chăn nệm, hút lông; rửa tay sau khi tiếp xúc.\n"
            "- Nếu mảng lan nhanh/rụng lông nhiều/gãi dữ: đưa đi thú y để soi nấm và điều trị đúng."
        )
    elif "VIÊM DA" in top1:
        rec = (
            "- Đeo vòng chống liếm/gãi, giữ vùng da khô sạch.\n"
            "- Rà soát nguyên nhân: ve/rận, thức ăn mới, tắm sai cách, môi trường.\n"
            "- Nếu da ướt rỉ dịch, mùi hôi, có mủ hoặc thú bỏ ăn: nên đi thú y sớm."
        )
    else:
        rec = (
            "- Lau sạch ghèn bằng gạc sạch + nước muối sinh lý, tránh để thú dụi mắt.\n"
            "- Tránh bụi/gió/khói; theo dõi đỏ mắt, nheo mắt.\n"
            "- Nếu nheo mắt nhiều/đau rõ/giác mạc đục: đi thú y ngay (nguy cơ loét giác mạc)."
        )

    return {"alert_level": alert, "top": ranking, "recommendation": rec}