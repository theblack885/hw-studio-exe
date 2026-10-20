"""AI helper: Anthropic ya Groq (key se khud pehchan leta hai). Sirf standard library."""
import json
import re
import urllib.error
import urllib.request

GROQ_DEFAULT_MODEL = "llama-3.3-70b-versatile"

SYSTEM = """Tum "Hardware Studio" ke andar built-in hardware coding assistant ho.
User Hindi/Hinglish me baat karta hai - usi bhasha me jawab do.
Jab user kisi bhi hardware (Arduino Uno/Nano/Mega, ESP32, ESP8266, Raspberry Pi Pico, STM32, ATtiny, etc.) ke liye code maange:
1. Poora, seedha compile hone wala code ek hi code block me do (```cpp ya ```python).
2. Code ke upar saaf batao: kaunsa board (FQBN), kaunsi library install karni hai, code kahan paste karna hai
   (Code tab me poora paste karo, ya 'Code editor me daalo' button dabao), aur wiring (kaunsa pin kahan).
3. Agar compile error aaye to poora error padho aur sudhaara hua POORA code do.
4. Galat pin ya khatarnak voltage ke baare me chetavni do. Chhota aur practical raho."""


def is_groq(key):
    return key.strip().startswith("gsk_")


def _post(url, headers, body):
    h = {"content-type": "application/json", "User-Agent": "HardwareStudio/1.0"}
    h.update(headers)
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), headers=h, method="POST")
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode("utf-8"))


_groq_cache = {}


def pick_groq_model(key):
    """Groq se pucho ki is account par kaunse models chalte hain, phir sabse achha chuno."""
    if "m" in _groq_cache:
        return _groq_cache["m"]
    try:
        req = urllib.request.Request(
            "https://api.groq.com/openai/v1/models",
            headers={"Authorization": "Bearer " + key, "User-Agent": "HardwareStudio/1.0"})
        with urllib.request.urlopen(req, timeout=30) as r:
            ids = [d["id"] for d in json.loads(r.read().decode("utf-8")).get("data", [])]
        prefer = ["openai/gpt-oss-120b", "llama-3.3-70b-versatile",
                  "openai/gpt-oss-20b", "llama-3.1-8b-instant"]
        pick = next((p for p in prefer if p in ids), None)
        if not pick:
            pick = next((i for i in ids if not any(x in i for x in ("whisper", "orpheus", "guard", "tts"))),
                        GROQ_DEFAULT_MODEL)
        _groq_cache["m"] = pick
        return pick
    except Exception:  # noqa: BLE001
        return GROQ_DEFAULT_MODEL


def ask(api_key, model, history, context=""):
    """history: [(role, text), ...]  role = 'user' | 'assistant'. Blocking call."""
    key = (api_key or "").strip()
    if not key:
        return "Settings me API key daalo."
    system = SYSTEM + (("\n\nContext:\n" + context) if context else "")
    msgs = [{"role": r, "content": t} for r, t in history]
    try:
        if is_groq(key):
            m = pick_groq_model(key) if (not model or model.startswith("claude")) else model
            data = _post(
                "https://api.groq.com/openai/v1/chat/completions",
                {"Authorization": "Bearer " + key},
                {"model": m, "max_tokens": 4096,
                 "messages": [{"role": "system", "content": system}] + msgs},
            )
            return data["choices"][0]["message"]["content"]
        data = _post(
            "https://api.anthropic.com/v1/messages",
            {"x-api-key": key, "anthropic-version": "2023-06-01"},
            {"model": model, "max_tokens": 4096, "system": system, "messages": msgs},
        )
        return "".join(b.get("text", "") for b in data.get("content", []))
    except urllib.error.HTTPError as e:
        return "Error %s: %s" % (e.code, e.read().decode("utf-8", "ignore")[:400])
    except Exception as e:  # noqa: BLE001
        return "Error: %s" % e


def extract_code(text):
    blocks = re.findall(r"```[a-zA-Z+]*\n(.*?)```", text, re.S)
    return max(blocks, key=len) if blocks else None


def extract_fqbn(text):
    m = re.search(r"\b([a-z0-9_]+:[a-z0-9_]+:[a-zA-Z0-9_\-]+)\b", text)
    return m.group(1) if m else None
