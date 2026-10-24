"""Arabic PDFs that imitate how real generators store RTL text (test-only helper).

Modes (how the text layer is written):
  visual   - isolated letters, each word reversed (visual order)
  shaped   - joined presentation forms (U+FE70..), visual order  (what many exporters produce)
  logical  - one glyph at a time placed right->left, text stream in LOGICAL order (Word/Chrome style)
A tiny joining-aware shaper is implemented here from Unicode data, so no external library is needed."""
import re
import unicodedata
from pathlib import Path

from reportlab.pdfbase.pdfmetrics import stringWidth

from tests.make_samples import Doc, W, H  # noqa: F401  (registers DejaVu fonts)

_FORMS = {}
for _cp in list(range(0xFB50, 0xFDFF)) + list(range(0xFE70, 0xFEFF)):
    _d = unicodedata.decomposition(chr(_cp))
    if _d.startswith("<") and len(_d.split()) == 2:
        _tag, _base = _d.split()
        _FORMS.setdefault(chr(int(_base, 16)), {})[_tag.strip("<>")] = chr(_cp)
_LIGA = {"ا": ("\uFEFB", "\uFEFC"), "أ": ("\uFEF7", "\uFEF8"), "إ": ("\uFEF9", "\uFEFA"), "آ": ("\uFEF5", "\uFEF6")}
_RIGHT_ONLY = set("اأإآدذرزوؤةء")        # never connect to the following letter
_AR = re.compile("[\u0621-\u064A]")


_MARK = re.compile("[\u064B-\u065F]")


def shape_word(w: str) -> str:
    """logical Arabic word -> logical string of presentation forms (diacritics are transparent)."""
    marks = {}
    base = []
    for ch in w:
        if _MARK.match(ch) and base:
            marks[len(base) - 1] = marks.get(len(base) - 1, "") + ch
        else:
            base.append(ch)
    shaped = _shape_letters("".join(base))
    if not marks:
        return shaped
    # map marks back after the letter they follow (ligature = 1 glyph for 2 letters)
    out, bi = [], 0
    for glyph in shaped:
        out.append(glyph)
        span = 2 if glyph in "\uFEFB\uFEFC\uFEF5\uFEF6\uFEF7\uFEF8\uFEF9\uFEFA" else 1
        out.append("".join(marks.get(k, "") for k in range(bi, bi + span)))
        bi += span
    return "".join(out)


def _shape_letters(w: str) -> str:
    chars, out, i = list(w), [], 0
    n = len(chars)
    prev_connects = False
    while i < n:
        c = chars[i]
        if not _AR.match(c):
            out.append(c)
            prev_connects = False
            i += 1
            continue
        if c == "ل" and i + 1 < n and chars[i + 1] in _LIGA:
            iso, fin = _LIGA[chars[i + 1]]
            out.append(fin if prev_connects else iso)
            prev_connects = False
            i += 2
            continue
        nxt = chars[i + 1] if i + 1 < n else ""
        next_joins = bool(nxt) and bool(_AR.match(nxt)) and c not in _RIGHT_ONLY
        f = _FORMS.get(c, {})
        if prev_connects and next_joins:
            form = "medial"
        elif prev_connects:
            form = "final"
        elif next_joins:
            form = "initial"
        else:
            form = "isolated"
        out.append(f.get(form) or f.get("isolated") or c)
        prev_connects = next_joins
        i += 1
    return "".join(out)


def _is_ar(tok):
    return bool(_AR.search(tok))


def put(d: Doc, xr: float, y: float, text: str, mode: str, size=10, bold=False):
    """Draw logical Arabic/mixed text right-aligned at xr (tokens placed right->left). Returns left edge."""
    font = "DVB" if bold else "DV"
    d.c.setFont(font, size)
    x = xr
    for tok in text.split():
        if _is_ar(tok):
            if mode == "logical":
                g = shape_word(tok)
                widths = [stringWidth(ch, font, size) for ch in g]
                x0 = x - sum(widths)
                cx = x
                for ch, wd in zip(g, widths):            # glyphs in logical order, positions descending
                    cx -= wd
                    d.c.drawString(cx, y, ch)
                x = x0
            else:
                s = shape_word(tok) if mode == "shaped" else tok
                s = s[::-1]                                              # whole token reversed ...
                s = re.sub(r"[A-Za-z0-9\u0660-\u0669.,:/\-%]+", lambda m: m.group(0)[::-1], s)   # ... Latin/digit runs restored
                wd = stringWidth(s, font, size)
                d.c.drawString(x - wd, y, s)
                x -= wd
        else:
            wd = stringWidth(tok, font, size)
            d.c.drawString(x - wd, y, tok)
            x -= wd
        x -= stringWidth(" ", font, size) * 1.2
    return x


EAST = str.maketrans("0123456789.,", "٠١٢٣٤٥٦٧٨٩٫٬")


def ea(s):
    return str(s).translate(EAST)


def invoice(path, mode, eastern=False, currency="SAR", diacritics=False):
    d = Doc(path)
    R = W - 40
    n = (lambda s: ea(s)) if eastern else (lambda s: str(s))
    put(d, R, d.y, "مستشفى الأمل العام", mode, 15, True); d.y -= 24
    put(d, R, d.y, "فاتورة ضريبية", mode, 12, True); d.y -= 22
    lab = "رَقم الفاتـورة:" if diacritics else "رقم الفاتورة:"            # fatha + tatweel
    x = put(d, R, d.y, lab, mode); put(d, x - 4, d.y, "INV-4004", mode)
    d.y -= 16
    put(d, R, d.y, "تاريخ الفاتورة:", mode)
    put(d, R - 95, d.y, n("2024/05/20").replace("/", "/"), mode); d.y -= 16
    put(d, R, d.y, "اسم المريض:", mode); put(d, R - 75, d.y, "خالد يوسف", mode); d.y -= 16
    put(d, R, d.y, "رقم الملف:", mode); put(d, R - 65, d.y, n("55120"), mode); d.y -= 16
    put(d, R, d.y, "العملة:", mode); put(d, R - 50, d.y, currency, mode); d.y -= 24
    heads = [("م", R), ("البيان", R - 40), ("الكمية", R - 270), ("السعر", R - 340), ("الإجمالي", R - 420)]
    for h, x in heads:
        put(d, x, d.y, h, mode, bold=True)
    d.y -= 16
    rows = [("كشف استشاري", 1, 1250.00, 1250.00), ("تحليل دم شامل", 2, 75.50, 151.00)]
    for i, (nm, q, p, t) in enumerate(rows, 1):
        put(d, R, d.y, n(i), mode)
        put(d, R - 40, d.y, nm, mode)
        put(d, R - 270, d.y, n(q), mode)
        put(d, R - 340, d.y, n(f"{p:,.2f}"), mode)
        put(d, R - 420, d.y, n(f"{t:,.2f}"), mode)
        d.y -= 15
    d.y -= 8
    put(d, R - 300, d.y, "إجمالي الفاتورة", mode, bold=True); put(d, R - 420, d.y, n("1,401.00"), mode, bold=True)
    d.save()


def discharge(path, mode):
    d = Doc(path)
    R = W - 40
    L = [("مستشفى الأمل العام", None, 15), ("ملخص الخروج", None, 12)]
    put(d, R, d.y, "مستشفى الأمل العام", mode, 15, True); d.y -= 24
    put(d, R, d.y, "ملخص الخروج", mode, 12, True); d.y -= 22
    rows = [("اسم المريض:", "فاطمة أحمد"), ("رقم الملف:", ea("330012")), ("تاريخ الدخول:", ea("2024/07/01")),
            ("تاريخ الخروج:", ea("2024/07/05")), ("عدد الأيام:", ea("4")), ("نوع الغرفة:", "خاصة"),
            ("التشخيص الرئيسي:", "التهاب رئوي (J18.9)"), ("التشخيص الثانوي:", "السكري من النوع الثاني؛ فقر دم مشتبه"),
            ("الطبيب:", "منى هادي")]
    for lab, v in rows:
        x = put(d, R, d.y, lab, mode)
        put(d, x - 4, d.y, v, mode)
        d.y -= 16
    d.save()


def lab(path, mode):
    d = Doc(path)
    R = W - 40
    put(d, R, d.y, "المختبر المركزي", mode, 15, True); d.y -= 24
    put(d, R, d.y, "تقرير نتائج المختبر", mode, 12, True); d.y -= 22
    put(d, R, d.y, "اسم المريض:", mode); put(d, R - 75, d.y, "علي ناصر", mode); d.y -= 16
    put(d, R, d.y, "التاريخ:", mode); put(d, R - 55, d.y, ea("2024/04/02"), mode); d.y -= 24
    for h, x in (("التحليل", R), ("النتيجة", R - 170), ("الوحدة", R - 260), ("المعدل الطبيعي", R - 340)):
        put(d, x, d.y, h, mode, bold=True)
    d.y -= 16
    for nm, res, unit, ref in (("هيموجلوبين", "10.2", "g/dL", "13.0 - 17.0"), ("سكر صائم", "95", "mg/dL", "70 - 100")):
        put(d, R, d.y, nm, mode); put(d, R - 170, d.y, ea(res), mode); put(d, R - 260, d.y, unit, mode)
        put(d, R - 340, d.y, ea(ref), mode); d.y -= 15
    d.save()


def prescription(path, mode):
    d = Doc(path)
    R = W - 40
    put(d, R, d.y, "عيادة النور", mode, 15, True); d.y -= 24
    put(d, R, d.y, "وصفة طبية", mode, 12, True); d.y -= 22
    put(d, R, d.y, "اسم المريض:", mode); put(d, R - 75, d.y, "سارة عمر", mode); d.y -= 16
    put(d, R, d.y, "الطبيب:", mode); put(d, R - 55, d.y, "ليلى ناصر", mode); d.y -= 22
    for line in ("١. أموكسيسيلين ٥٠٠ ملغ كبسولة مرتين يوميا لمدة ٧ أيام", "٢. باراسيتامول ٥٠٠ ملغ قرص ثلاث مرات يوميا لمدة ٣ أيام"):
        put(d, R, d.y, line, mode); d.y -= 16
    d.save()


def build(out: Path):
    out.mkdir(parents=True, exist_ok=True)
    for mode in ("visual", "shaped", "logical"):
        invoice(out / f"ar_inv_{mode}.pdf", mode)
        discharge(out / f"ar_dis_{mode}.pdf", mode)
        lab(out / f"ar_lab_{mode}.pdf", mode)
        prescription(out / f"ar_rx_{mode}.pdf", mode)
    invoice(out / "ar_inv_east.pdf", "shaped", eastern=True)
    invoice(out / "ar_inv_diac.pdf", "shaped", diacritics=True)
    invoice(out / "ar_inv_ambig_cur.pdf", "shaped", currency="ريال")
    return out
