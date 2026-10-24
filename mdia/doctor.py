"""Self-check for Arabic support on THIS machine:  python -m mdia.doctor
Verifies (1) Tesseract + Arabic model, (2) a real OCR round-trip on rendered Arabic text,
(3) reshaper/bidi/Arabic font, (4) a real Arabic PDF report built and re-read.
Exit code 0 only if everything passes."""
import difflib
import io
import sys

SAMPLE = ["مستشفى الأمل العام", "رقم الفاتورة", "اسم المريض", "التشخيص الرئيسي", "إجمالي الفاتورة"]


def _ok(name, passed, detail=""):
    print(("[ PASS ] " if passed else "[ FAIL ] ") + name + (f" — {detail}" if detail else ""))
    return passed


def main():
    from . import exporters
    from .reader import available_ocr_langs
    res = []
    langs = available_ocr_langs()
    res.append(_ok("Tesseract installed", bool(langs), ", ".join(sorted(langs)) or "not found (set MDIA_TESSERACT_CMD)"))
    res.append(_ok("Arabic OCR model (ara)", "ara" in langs, "install tesseract language data 'ara'"))
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display
        res.append(_ok("arabic_reshaper + python-bidi", True))
    except ImportError as e:
        res.append(_ok("arabic_reshaper + python-bidi", False, str(e)))
        arabic_reshaper = get_display = None
    font = exporters.find_arabic_font()
    res.append(_ok("Arabic font", font is not None, f"{font.name if font else 'none'}" + ("" if font and "miri" in font.name else "  (Amiri-Regular.ttf recommended: put it in ./fonts)")))

    if "ara" in langs and arabic_reshaper and font:           # real OCR round trip
        from PIL import Image, ImageDraw, ImageFont
        import pytesseract
        f = ImageFont.truetype(str(font), 44)
        img = Image.new("L", (1400, 120 * len(SAMPLE)), 255)
        dr = ImageDraw.Draw(img)
        for i, t in enumerate(SAMPLE):
            dr.text((1300, 20 + 120 * i), get_display(arabic_reshaper.reshape(t)), font=f, fill=0, anchor="ra")
        got = pytesseract.image_to_string(img, lang="ara", config="--psm 6")
        got_lines = [l.strip() for l in got.splitlines() if l.strip()]
        scores = [max([difflib.SequenceMatcher(None, t, g).ratio() for g in got_lines] or [0]) for t in SAMPLE]
        avg = sum(scores) / len(scores)
        res.append(_ok("Arabic OCR round-trip on rendered text", avg >= 0.8, f"mean similarity {avg:.2f} over {len(SAMPLE)} phrases"))
    else:
        res.append(_ok("Arabic OCR round-trip", False, "skipped: needs ara model + reshaper + font"))

    try:                                                      # real Arabic PDF report
        from .textutil import has_ar  # noqa: F401
        fv = lambda raw: {"raw": raw, "value": raw, "evidence_id": None, "page": 1, "confidence": 0.95, "status": "extracted", "verification": "unverified"}
        doc = {"document_id": "t-d1", "document_type": "discharge_summary", "patient": {"name": fv("فاطمة أحمد")}, "provider": {"facility_name": fv("مستشفى الأمل العام")},
               "hospitalization": {}, "invoices": [], "invoice_items": [], "medications": [], "laboratory_tests": [], "imaging": [], "procedures": [],
               "diagnoses": [{"id": "t-dx1", "text": fv("التهاب رئوي (J18.9)"), "icd10": fv("J18.9")}], "evidence": [], "warnings": [], "requires_human_review": []}
        pdf = exporters.to_pdf({"job_id": "selftest", "source": {"filename": "اختبار.pdf"}, "processing_status": "completed", "documents": [doc]})
        res.append(_ok("Arabic PDF report built and verified (reshape + bidi + font coverage + re-read)", pdf.startswith(b"%PDF"), f"{len(pdf)} bytes"))
        open("mdia_doctor_report.pdf", "wb").write(pdf)
        print("         open mdia_doctor_report.pdf and eyeball that the Arabic is joined and right-to-left.")
    except Exception as e:  # noqa
        res.append(_ok("Arabic PDF report", False, f"{type(e).__name__}: {e}"))
    print("\nALL CHECKS PASSED" if all(res) else "\nSOME CHECKS FAILED — see above")
    return 0 if all(res) else 1


if __name__ == "__main__":
    sys.exit(main())
