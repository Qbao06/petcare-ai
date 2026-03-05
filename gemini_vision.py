import json
import re
from google import genai
from google.genai import types

MODEL_ID = "gemini-2.5-flash"

SIGNS_SCHEMA = {
    "circular_hair_loss": bool,
    "scaly_skin": bool,
    "general_hair_loss": bool,
    "red_skin": bool,
    "wet_infected_skin": bool,
    "eye_redness": bool,
    "eye_discharge": bool,
    "squinting": bool,
    "notes": str,
}

def _extract_json_balanced(text: str) -> str:
    """
    Extract first JSON object by scanning + balancing braces.
    If missing closing braces, auto-append required number of '}'.
    """
    if not text:
        raise ValueError("Empty response text")

    t = text.strip()
    # strip markdown fences
    t = re.sub(r"^```(?:json)?\s*", "", t, flags=re.IGNORECASE)
    t = re.sub(r"\s*```$", "", t)

    start = t.find("{")
    if start == -1:
        raise ValueError(f"No JSON start found. Head={t[:200]!r}")

    s = t[start:]

    depth = 0
    in_str = False
    esc = False

    for i, ch in enumerate(s):
        if in_str:
            if esc:
                esc = False
                continue
            if ch == "\\":
                esc = True
                continue
            if ch == '"':
                in_str = False
            continue

        # not in string
        if ch == '"':
            in_str = True
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return s[: i + 1]

    # If we reached end and still inside object -> auto-close
    if depth > 0:
        return s + ("}" * depth)

    raise ValueError(f"No JSON object found. Head={t[:200]!r}")

def _safe_load_json(text: str) -> dict:
    raw = _extract_json_balanced(text)

    # cleanup common issues
    raw2 = re.sub(r",\s*([}\]])", r"\1", raw)  # trailing commas
    raw2 = raw2.replace("“", "\"").replace("”", "\"").replace("’", "'")

    try:
        return json.loads(raw2)
    except json.JSONDecodeError:
        # last resort: replace single quotes
        raw3 = raw2.replace("'", "\"")
        raw3 = re.sub(r",\s*([}\]])", r"\1", raw3)
        return json.loads(raw3)

def _normalize_signs(obj: dict) -> dict:
    out = {}
    for k, tp in SIGNS_SCHEMA.items():
        v = obj.get(k, False if tp is bool else "")
        if tp is bool:
            if isinstance(v, bool):
                out[k] = v
            elif isinstance(v, (int, float)):
                out[k] = bool(v)
            elif isinstance(v, str):
                vv = v.strip().lower()
                out[k] = vv in ("true", "1", "yes", "y", "đúng", "co", "có")
            else:
                out[k] = False
        else:
            out[k] = "" if v is None else str(v)
    out["notes"] = out["notes"][:500]
    return out

def _build_prompt() -> str:
    return (
        "Bạn là trợ lý thú y hỗ trợ SÀNG LỌC (triage) cho CHÓ/MÈO.\n"
        "NHIỆM VỤ: Nhìn ảnh và xuất ra CHỈ MỘT JSON object, KHÔNG markdown, KHÔNG giải thích.\n"
        "Nếu ảnh không liên quan hoặc không đủ rõ: đặt tất cả boolean=false và notes=\"không đủ rõ\".\n"
        "BẮT BUỘC trả đủ dấu ngoặc JSON mở/đóng.\n\n"
        "Schema:\n"
        "{\n"
        "  \"circular_hair_loss\": boolean,\n"
        "  \"scaly_skin\": boolean,\n"
        "  \"general_hair_loss\": boolean,\n"
        "  \"red_skin\": boolean,\n"
        "  \"wet_infected_skin\": boolean,\n"
        "  \"eye_redness\": boolean,\n"
        "  \"eye_discharge\": boolean,\n"
        "  \"squinting\": boolean,\n"
        "  \"notes\": string\n"
        "}\n"
    )

def extract_signs_from_image(image_bytes: bytes, mime_type: str) -> dict:
    client = genai.Client()
    prompt = _build_prompt()

    def _call(json_mode: bool, max_tokens: int) -> str:
        cfg = types.GenerateContentConfig(
            temperature=0,
            max_output_tokens=max_tokens,
        )
        if json_mode:
            cfg.response_mime_type = "application/json"

        resp = client.models.generate_content(
            model=MODEL_ID,
            contents=[{
                "role": "user",
                "parts": [
                    {"text": prompt},
                    {"inline_data": {"mime_type": mime_type, "data": image_bytes}},
                ],
            }],
            config=cfg,
        )
        return (resp.text or "").strip()

    # Retry plan (ăn chắc)
    attempts = [
        (True, 600),
        (True, 900),
        (False, 900),
    ]

    last_err = None
    for json_mode, max_tokens in attempts:
        try:
            text = _call(json_mode=json_mode, max_tokens=max_tokens)
            obj = _safe_load_json(text)
            return _normalize_signs(obj)
        except Exception as e:
            last_err = e
            continue

    raise RuntimeError(f"Gemini parse failed after retries: {last_err}")