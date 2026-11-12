# enhancer.py
import re
import html

_BN_RANGE = re.compile(r"[\u0980-\u09FF]")

def _looks_bengali(text: str) -> bool:
    return bool(_BN_RANGE.search(text or ""))

def strip_ssml_like(text: str) -> str:
    if not text:
        return ""
    text = html.unescape(text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = text.replace("&lt;", " ").replace("&gt;", " ")
    return text

def basic_clean(text: str) -> str:
    text = strip_ssml_like(text)
    text = re.sub(r"[\t ]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text)
    text = "\n".join([ln.strip() for ln in text.splitlines()])
    return text.strip()

def enhance_text(text: str, mode: str = "lecture") -> str:
    text = basic_clean(text)
    if not text:
        return ""
    mode = (mode or "lecture").lower().strip()
    if mode not in ("lecture", "devotional", "documentary"):
        mode = "lecture"
    is_bn = _looks_bengali(text)
    if is_bn and ("।" not in text):
        text = re.sub(r"(?<=\w)\.(?=\s)", "।", text)
    if mode == "devotional":
        text = re.sub(r"([।.!?])", r"\1... ", text)
    else:
        text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\.\.\.(\s*\.\.\.)+", "...", text).strip()
    def _soft_break(s: str) -> str:
        if len(s) < 150:
            return s
        s = re.sub(r"\s+(and|but|so|because|therefore)\s+", r", \1 ", s, flags=re.IGNORECASE)
        s = re.sub(r"\s+(এবং|কিন্তু|তবে|কারণ|সুতরাং)\s+", r", \1 ", s)
        return s
    parts = re.split(r"(?<=[।.!?])\s+|\n+", text)
    parts = [_soft_break(p.strip()) for p in parts if p and p.strip()]
    return " ".join(parts).strip()