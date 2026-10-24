"""Text normalisation, Arabic handling, number and date parsing.
Nothing here ever invents data: parsers return None when the input is ambiguous."""
import re
import unicodedata
from decimal import Decimal, InvalidOperation

AR_LETTERS = "\u0621-\u065F\u0670-\u06D3\u06FA-\u06FF\u0750-\u077F\uFB50-\uFDFF\uFE70-\uFEFF"
AR_RE = re.compile(f"[{AR_LETTERS}]")
AR_RUN = re.compile(f"[{AR_LETTERS}]+")
LAT_RE = re.compile(r"[A-Za-z]")
_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
_STRIP = ".:;,،؛()[]{}|\"'«»*"


def nfkc(s: str) -> str:
    return unicodedata.normalize("NFKC", s)


def fix_digits(s: str) -> str:
    return s.translate(_DIGITS)


def has_ar(s: str) -> bool:
    return bool(AR_RE.search(s))


def ar_ratio(s: str) -> float:
    a = len(AR_RE.findall(s))
    l = len(LAT_RE.findall(s))
    return a / (a + l) if (a + l) else 0.0


def reverse_ar_runs(s: str) -> str:
    """Undo visual-order storage of Arabic letters (only letter runs are reversed)."""
    return AR_RUN.sub(lambda m: m.group(0)[::-1], s)


_LTR_RUN = re.compile(r"[A-Za-z0-9\u0660-\u0669\u06F0-\u06F9][A-Za-z0-9\u0660-\u0669\u06F0-\u06F9.,:/\-\u066B\u066C%]*")


def visual_to_logical(word: str) -> str:
    """Inverse of bidi display for ONE word stored in visual order: reverse the characters
    (letters, marks, attached punctuation) but keep embedded Latin/digit runs readable."""
    segs, pos = [], 0
    for m in _LTR_RUN.finditer(word):
        if m.start() > pos:
            segs.append((word[pos:m.start()], False))
        segs.append((m.group(0), True))
        pos = m.end()
    if pos < len(word):
        segs.append((word[pos:], False))
    return "".join(t if ltr else t[::-1] for t, ltr in reversed(segs))


def match_key(s: str) -> str:
    """Canonical form used ONLY for lexicon matching (never stored as a value)."""
    s = fix_digits(nfkc(s))
    s = re.sub("[\u064B-\u065F\u0640\u0670]", "", s)
    s = re.sub("[أإآٱ]", "ا", s).replace("ى", "ي").replace("ة", "ه")
    return s.lower().strip(_STRIP + " ")


# ----------------------------------------------------------------- numbers
_CUR = {
    "sar": "SAR", "usd": "USD", "yer": "YER", "aed": "AED", "kwd": "KWD", "qar": "QAR",
    "omr": "OMR", "bhd": "BHD", "egp": "EGP", "jod": "JOD", "eur": "EUR", "gbp": "GBP",
    "$": "USD", "ر.س": "SAR", "ر.ي": "YER", "ر.ق": "QAR", "د.إ": "AED", "د.ك": "KWD",
}
CUR_TOKEN_RE = re.compile(
    r"(?i)\b(sar|usd|yer|aed|kwd|qar|omr|bhd|egp|jod|eur|gbp)\b|\$|﷼|ر\.\s?[سيق]|د\.\s?[إك]|ريال|دينار|درهم|riyal|rial|dinar|dirham")


def detect_currency(s: str):
    """-> (raw_token, iso_or_None). Ambiguous words (e.g. 'ريال') return iso=None, never a guess."""
    m = CUR_TOKEN_RE.search(nfkc(s))
    if not m:
        return None, None
    raw = m.group(0)
    k = re.sub(r"\s", "", raw.lower())
    return raw, _CUR.get(k)


def is_numeric_token(t: str) -> bool:
    t = fix_digits(nfkc(t)).strip(_STRIP + " ")
    return bool(re.fullmatch(r"[-+]?\d[\d,.\u066B\u066C]*%?", t)) or t == "-"


def parse_number(s):
    """Decimal or None. Ambiguity stays explicit: unparseable -> None."""
    if s is None:
        return None
    t = fix_digits(nfkc(str(s))).replace("\u066B", ".").replace("\u066C", ",").strip()
    neg = (t.startswith("(") and t.endswith(")")) or t.startswith("-")
    t = re.sub(r"[^\d.,]", "", t)
    if not re.search(r"\d", t):
        return None
    if "," in t and "." in t:
        t = t.replace(".", "").replace(",", ".") if t.rfind(",") > t.rfind(".") else t.replace(",", "")
    elif "," in t:
        t = t.replace(",", "") if re.fullmatch(r"\d{1,3}(,\d{3})+", t) else t.replace(",", ".")
    elif t.count(".") > 1:
        if re.fullmatch(r"\d{1,3}(\.\d{3})+", t):
            t = t.replace(".", "")
        else:
            return None
    try:
        d = Decimal(t)
    except InvalidOperation:
        return None
    return -d if neg else d


def last_amount(s: str):
    """(raw_token, Decimal) of the last numeric token that is not a percentage, else (None, None)."""
    toks = fix_digits(nfkc(s)).split()
    for tok in reversed(toks):
        if "%" in tok or not re.search(r"\d", tok):
            continue
        clean = tok.strip("[]:؛;")                      # keep parentheses: "(20.00)" is a NEGATIVE amount
        if re.fullmatch(r"[-+]?\(?\d[\d,.\u066B\u066C]*\)?", clean):
            v = parse_number(clean)
            if v is not None:
                return tok, v
    return None, None


# ------------------------------------------------------------------- dates
_EN_MON = {m: i for i, m in enumerate("jan feb mar apr may jun jul aug sep oct nov dec".split(), 1)}
_AR_MON = {"يناير": 1, "فبراير": 2, "مارس": 3, "ابريل": 4, "أبريل": 4, "مايو": 5, "يونيو": 6, "يوليو": 7,
           "اغسطس": 8, "أغسطس": 8, "سبتمبر": 9, "اكتوبر": 10, "أكتوبر": 10, "نوفمبر": 11, "ديسمبر": 12}


def _iso(y, m, d):
    import datetime
    try:
        return datetime.date(y, m, d).isoformat()
    except ValueError:
        return None


def parse_date(raw):
    """-> (iso|None, note|None). Never guesses day/month order or calendar."""
    t = fix_digits(nfkc(raw or ""))
    m = re.search(r"(\d{4})\s*[-/.]\s*(\d{1,2})\s*[-/.]\s*(\d{1,2})", t)
    if m:
        y, a, b = map(int, m.groups())
        if 1300 <= y <= 1500:
            return None, "hijri_calendar_date"
        iso = _iso(y, a, b)
        return (iso, None) if iso else (None, "invalid_date")
    m = re.search(r"(\d{1,2})\s*[-/.]\s*(\d{1,2})\s*[-/.]\s*(\d{4})", t)
    if m:
        a, b, y = map(int, m.groups())
        if 1300 <= y <= 1500:
            return None, "hijri_calendar_date"
        if a > 12 and b <= 12:
            return _iso(y, b, a), None
        if b > 12 and a <= 12:
            return _iso(y, a, b), None
        if a == b:
            return _iso(y, a, b), None
        return None, "ambiguous_day_month_order"
    m = re.search(r"(\d{1,2})\s+([A-Za-z]{3,9})\.?,?\s+(\d{4})", t)
    if m and m.group(2)[:3].lower() in _EN_MON:
        return _iso(int(m.group(3)), _EN_MON[m.group(2)[:3].lower()], int(m.group(1))), None
    m = re.search(r"(\d{1,2})\s+([\u0600-\u06FF]+)\s+(\d{4})", t)
    if m and m.group(2) in _AR_MON:
        return _iso(int(m.group(3)), _AR_MON[m.group(2)], int(m.group(1))), None
    if re.search(r"\d{1,2}\s*[-/.]\s*\d{1,2}\s*[-/.]\s*\d{2}\b", t):
        return None, "two_digit_year"
    return None, "no_date_found"
