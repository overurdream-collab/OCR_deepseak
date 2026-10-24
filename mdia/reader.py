"""PDF -> Page objects with word-level geometry.

Per page: text layer via pdfplumber; OCR (Tesseract) when the page is scanned, the text layer is
garbage ((cid:..) / replacement chars), or the page is rotated. Each page is cached on disk as soon
as it is done, so a crash or a failing page never loses completed work."""
import hashlib
import json
import re
from pathlib import Path

from . import config
from .lexicon import COLUMN_TABLE, LABEL_TABLE, SECTION_WORDS
from .model import Page, Word, build_lines
from .textutil import has_ar, match_key, nfkc, reverse_ar_runs, visual_to_logical

_AR_LEXICON = {t for tab in (LABEL_TABLE, COLUMN_TABLE) for toks, _, rtl in tab if rtl for t in toks} | \
              {w for w in SECTION_WORDS if has_ar(w)}


class PdfError(Exception):
    pass


def check_pdf(path: Path):
    """Integrity check: magic bytes, parseable, not password protected. Returns page count."""
    with open(path, "rb") as f:
        head = f.read(1024)
    if b"%PDF-" not in head:
        raise PdfError("الملف ليس PDF صالحًا / not a valid PDF (missing %PDF header)")
    from pypdf import PdfReader
    try:
        r = PdfReader(str(path), strict=False)
        if r.is_encrypted and not r.decrypt(""):
            raise PdfError("الملف محمي بكلمة مرور / password-protected PDF")
        n = len(r.pages)
    except PdfError:
        raise
    except Exception as e:  # noqa
        raise PdfError(f"تعذر فتح الملف / cannot open PDF: {e}")
    if n == 0:
        raise PdfError("الملف لا يحتوي صفحات / PDF has no pages")
    return n


# ------------------------------------------------------------- text layer
def _fix_visual_arabic(words):
    """Many generators store Arabic in visual (reversed) order. Vote with the lexicon on whether
    reversing letter runs yields more known medical/financial terms. Returns True if flipped."""
    as_is = rev = 0
    for w in words:
        if not has_ar(w.text):
            continue
        k = match_key(w.text)
        if k in _AR_LEXICON:
            as_is += 1
        if match_key(reverse_ar_runs(w.text)) in _AR_LEXICON:
            rev += 1
    flipped = rev >= 2 and rev > as_is
    for w in words:
        if flipped and has_ar(w.text):
            w.text = visual_to_logical(w.text)     # reverse while ligatures/presentation forms are still single code points
        w.text = nfkc(w.text)                      # then expand to base letters
        w.key = match_key(w.text)
    return flipped


def _text_layer(pdf_page, number):
    W, H = float(pdf_page.width), float(pdf_page.height)
    raw = pdf_page.extract_words(x_tolerance=1.5, y_tolerance=3, keep_blank_chars=False, use_text_flow=False)
    words = []
    for r in raw:
        t = r["text"].strip()          # NOT normalised yet: lam-alef ligatures must survive until the order is fixed
        if not t:
            continue
        words.append(Word(t, r["x0"] / W, r["top"] / H, r["x1"] / W, r["bottom"] / H, 1.0, "text-layer"))
    return W, H, words


def _garbage(words):
    txt = " ".join(w.text for w in words)
    if not txt:
        return False
    bad = txt.count("(cid:") * 6 + txt.count("\ufffd")
    return bad / max(len(txt), 1) > 0.05


# -------------------------------------------------------------------- OCR
def _configure_tesseract():
    import os
    import shutil
    import pytesseract
    cmd = os.environ.get("MDIA_TESSERACT_CMD")
    if not cmd and not shutil.which("tesseract"):
        for guess in (r"C:\Program Files\Tesseract-OCR\tesseract.exe", r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"):
            if os.path.exists(guess):
                cmd = guess
    if cmd:
        pytesseract.pytesseract.tesseract_cmd = cmd


def available_ocr_langs():
    try:
        import pytesseract
        _configure_tesseract()
        return set(pytesseract.get_languages(config=""))
    except Exception:
        return set()


def _ocr_image(img, lang, psm=6):
    import pytesseract
    from pytesseract import Output
    d = pytesseract.image_to_data(img, lang=lang, config=f"--oem 1 --psm {psm}", output_type=Output.DICT)
    iw, ih = img.size
    words = []
    for i, t in enumerate(d["text"]):
        t = nfkc(t).strip()
        try:
            c = float(d["conf"][i])
        except (TypeError, ValueError):
            c = -1
        if not t or c < 0:
            continue
        l, tp, w, h = d["left"][i], d["top"][i], d["width"][i], d["height"][i]
        words.append(Word(t, l / iw, tp / ih, (l + w) / iw, (tp + h) / ih, min(c / 100.0, 1.0), "ocr"))
    return words


def estimate_skew(img, limit=4.0):
    """Skew angle in degrees (rotate(angle) straightens the page). Projection-profile search, pure PIL."""
    from PIL import Image, ImageOps
    small = ImageOps.autocontrast(img.convert("L"))
    small.thumbnail((800, 800))
    ink = ImageOps.invert(small).point(lambda p: 255 if p > 110 else 0)

    def score(a):
        r = ink.rotate(a, resample=Image.BILINEAR, fillcolor=0) if a else ink
        prof = list(r.resize((1, r.height), Image.BOX).tobytes())
        return sum(v * v for v in prof)

    best = max((score(a / 4.0), a / 4.0) for a in range(int(-limit * 4), int(limit * 4) + 1))[1]
    fine = max((score(best + k / 20.0), best + k / 20.0) for k in range(-5, 6))[1]
    return round(fine, 2)


def _to_original_space(words, angle, iw, ih):
    """Map word boxes from the rotated (deskewed) image back to the original image."""
    import math
    c, s = math.cos(math.radians(angle)), math.sin(math.radians(angle))
    cx, cy = iw / 2.0, ih / 2.0
    for w in words:
        pts = []
        # Preserve secondary Tesseract word boxes through deskew rotation.
        # Never replace them with Paddle's interpolated token rectangle.
        bx = w.box if getattr(w, "geometry_source", "") == "cross_engine_word_match" and w.box else [w.x0, w.y0, w.x1, w.y1]
        for xd, yd in ((bx[0], bx[1]), (bx[2], bx[1]), (bx[0], bx[3]), (bx[2], bx[3])):
            dx, dy = xd * iw - cx, yd * ih - cy
            pts.append(((dx * c - dy * s + cx) / iw, (dx * s + dy * c + cy) / ih))
        w.box = [min(p[0] for p in pts), min(p[1] for p in pts), max(p[0] for p in pts), max(p[1] for p in pts)]


def ocr_page(pil_img, lang):
    """OCR with a retry on a binarised image when confidence is poor; keeps the better result."""
    from PIL import ImageOps
    g = ImageOps.autocontrast(pil_img.convert("L"))
    best = _ocr_image(g, lang)
    mean = sum(w.conf for w in best) / len(best) if best else 0
    if mean < 0.65:
        alt = _ocr_image(g.point(lambda p: 255 if p > 150 else 0), lang)
        m2 = sum(w.conf for w in alt) / len(alt) if alt else 0
        if m2 > mean:
            best, mean = alt, m2
    return best


# ------------------------------------------------------------------- main
def read_document(pdf_path: Path, work_dir: Path, ocr_mode="auto", lang=None, progress=None):
    """-> list[Page]. ocr_mode: auto | force | off. Cached per page under work_dir/pages."""
    import pdfplumber
    import pypdfium2 as pdfium
    lang = lang or config.OCR_LANG
    import os
    engine = os.environ.get("MDIA_OCR_ENGINE", "tesseract").strip().lower()
    if engine not in ("tesseract", "paddle_arabic"):
        raise ValueError(f"Unsupported MDIA_OCR_ENGINE: {engine}")
    use_paddle = engine == "paddle_arabic"
    align_words = use_paddle and os.environ.get("MDIA_PADDLE_WORD_ALIGN", "0") == "1"
    n_pages = check_pdf(pdf_path)
    pages_dir = work_dir / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)
    langs = available_ocr_langs()
    use_lang = "+".join(l for l in lang.split("+") if l in langs) or ("eng" if "eng" in langs else lang)
    ar_missing = "ara" in lang and "ara" not in langs
    # Avoid cross-engine cache pollution when switching OCR engines.
    opt_sig = hashlib.sha1(f"{ocr_mode}|{use_lang}|{engine}|{('arabic_PP-OCRv5_mobile_rec' if use_paddle else 'tesseract')}|align={int(align_words)}".encode()).hexdigest()[:8]
    pages = []
    pdfium_doc = pdfium.PdfDocument(str(pdf_path))
    with pdfplumber.open(str(pdf_path)) as plumb:
        for i in range(n_pages):
            num = i + 1
            cache = pages_dir / f"{num}.json"
            if cache.exists():
                try:
                    d = json.loads(cache.read_text("utf-8"))
                    if d.get("opt_sig") == opt_sig:
                        pages.append(Page.from_cache(d))
                        if progress:
                            progress(num, n_pages)
                        continue
                except Exception:
                    pass
            page = Page(num, 0, 0, "none")
            try:
                pp = plumb.pages[i]
                W, H, words = _text_layer(pp, num)
                page.width, page.height = W, H
                chars = sum(len(w.text) for w in words)
                has_images = bool(pp.images)
                need_ocr = ocr_mode == "force" or (ocr_mode == "auto" and (
                    chars < config.MIN_TEXT_CHARS or _garbage(words) or (pp.rotation or 0) % 180 != 0
                    or (has_images and chars < 80)))
                pil_prev = pdfium_doc[i].render(scale=config.PREVIEW_SCALE).to_pil()
                img_path = pages_dir / f"{num}.png"
                pil_prev.save(img_path)
                page.image = img_path.name
                if need_ocr:
                    if not langs and not use_paddle:
                        page.warnings.append({"kind": "ocr_unavailable", "message": "Tesseract غير مثبت / not installed"})
                        page.method, page.words = "none", []
                    else:
                        if ar_missing and not use_paddle:
                            page.warnings.append({"kind": "ocr_arabic_model_missing",
                                                  "message": "نموذج OCR العربي (ara) غير مثبت؛ استُخدمت الإنجليزية فقط / Arabic OCR model not installed"})
                        if use_paddle:
                            from .paddle_arabic import ocr_image as selected_ocr
                            page.flags["ocr_engine"] = "paddleocr-v5-arabic"
                            page.warnings.append({"kind": "paddle_line_geometry_only", "message":
                                                  "PaddleOCR word boxes are estimated from text-line rectangles; verify all highlighted values manually"})
                        else:
                            selected_ocr = lambda image: ocr_page(image, use_lang)
                        big = pdfium_doc[i].render(scale=config.OCR_DPI / 72.0).to_pil()
                        angle = estimate_skew(big)
                        if abs(angle) >= 0.4:
                            from PIL import Image
                            rot = big.convert("L").rotate(angle, resample=Image.BICUBIC, fillcolor=255)
                            page.words, page.method = selected_ocr(rot), "ocr"
                            _to_original_space(page.words, angle, *rot.size)
                            page.flags["deskew_deg"] = angle
                        else:
                            page.words, page.method = selected_ocr(big), "ocr"
                        page.flags["ocr_lang"] = "arabic+english (Paddle PP-OCRv5)" if use_paddle else use_lang
                        if use_paddle:
                            page.flags["word_alignment_opt_in"] = align_words
                            page.flags["cross_engine_word_matches"] = sum(
                                w.geometry_source == "cross_engine_word_match" for w in page.words)
                        if page.words:
                            page.flags["ocr_mean_conf"] = round(sum(w.conf for w in page.words) / len(page.words), 3)
                        else:
                            page.warnings.append({"kind": "unreadable_page", "message": "OCR لم يجد نصًا / OCR found no text"})
                else:
                    page.method, page.words = "text-layer", words
                    if _fix_visual_arabic(page.words):
                        page.flags["arabic_visual_order_fixed"] = True
                page.lines = build_lines(page.words, num)
                page.text_hash = hashlib.sha1(re.sub(r"\s+", " ", page.text).strip().encode()).hexdigest()
            except Exception as e:  # page-level failure must not lose the other pages
                page.warnings.append({"kind": "page_failed", "message": f"{type(e).__name__}: {e}"})
            d = page.to_cache()
            d["opt_sig"] = opt_sig
            tmp = cache.with_suffix(".tmp")
            tmp.write_text(json.dumps(d, ensure_ascii=False), "utf-8")
            tmp.replace(cache)
            pages.append(page)
            if progress:
                progress(num, n_pages)
    return pages
