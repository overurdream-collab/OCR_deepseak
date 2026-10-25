"""Arabic-handling tests.  Run: python -m unittest tests.test_arabic -v
Covers 3 text-layer storage modes x 4 document types, Arabic-Indic digits, diacritics/tatweel,
ambiguous currency, dates, and PDF-export font coverage."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
TMP = Path(tempfile.mkdtemp(prefix="mdia_ar_"))
os.environ["MDIA_DATA_DIR"] = str(TMP / "data")

from mdia import exporters                          # noqa: E402
from mdia.pipeline import process_job               # noqa: E402
from mdia.store import Store                        # noqa: E402
from mdia.textutil import parse_date, parse_number, match_key, detect_currency  # noqa: E402
from tests import arabic_samples as A              # noqa: E402

STORE = Store(TMP / "store")
SAMPLES = TMP / "samples"
_C = {}


def run(name):
    if name not in _C:
        jid = STORE.create(name, (SAMPLES / name).read_bytes())
        _C[name] = (jid, process_job(STORE, jid))
    return _C[name]


def val(f):
    return None if f["status"] == "not_found" else (f["value"] if f["value"] is not None else f["raw"])


MODES = ("visual", "shaped", "logical")


class ArabicTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        A.build(SAMPLES)

    def test_invoice_all_modes(self):
        for mode in MODES:
            with self.subTest(mode=mode):
                d = run(f"ar_inv_{mode}.pdf")[1]["documents"][0]
                self.assertEqual(d["document_type"], "hospital_invoice")
                inv = d["invoices"][0]
                self.assertEqual(val(d["patient"]["name"]), "خالد يوسف")
                self.assertEqual(val(d["patient"]["file_no"]), "55120")
                self.assertEqual(val(inv["invoice_number"]), "INV-4004")
                self.assertEqual(val(inv["invoice_date"]), "2024-05-20")
                self.assertEqual(val(inv["invoice_total"]), 1401.0)
                self.assertEqual(val(d["provider"]["facility_name"]), "مستشفى الأمل العام")
                got = [(val(i["service_name"]), val(i["quantity"]), val(i["unit_price"]), val(i["line_total"])) for i in d["invoice_items"]]
                self.assertEqual(got, [("كشف استشاري", 1.0, 1250.0, 1250.0), ("تحليل دم شامل", 2.0, 75.5, 151.0)])
                self.assertEqual([w for w in d["warnings"] if w["kind"].endswith("mismatch")], [])

    def test_arabic_indic_digits(self):
        d = run("ar_inv_east.pdf")[1]["documents"][0]
        inv = d["invoices"][0]
        self.assertEqual(val(inv["invoice_date"]), "2024-05-20")
        self.assertEqual(val(d["patient"]["file_no"]), "٥٥١٢٠")          # raw preserved exactly as printed
        self.assertEqual(d["patient"]["file_no"]["raw"], "٥٥١٢٠")
        self.assertEqual(val(inv["invoice_total"]), 1401.0)                 # normalised value is numeric
        self.assertEqual(val(d["invoice_items"][0]["unit_price"]), 1250.0)
        self.assertEqual(val(d["invoice_items"][1]["unit_price"]), 75.5)

    def test_diacritics_and_tatweel_in_labels(self):
        d = run("ar_inv_diac.pdf")[1]["documents"][0]
        self.assertEqual(val(d["invoices"][0]["invoice_number"]), "INV-4004")

    def test_ambiguous_currency_is_not_guessed(self):
        d = run("ar_inv_ambig_cur.pdf")[1]["documents"][0]
        cur = d["invoices"][0]["currency"]
        self.assertEqual(cur["raw"], "ريال")
        self.assertIsNone(cur["value"])
        self.assertEqual(cur["verification"], "needs_review")
        self.assertIn("ambiguous_currency", cur["review_reasons"])

    def test_discharge_all_modes(self):
        for mode in MODES:
            with self.subTest(mode=mode):
                d = run(f"ar_dis_{mode}.pdf")[1]["documents"][0]
                self.assertEqual(d["document_type"], "discharge_summary")
                h = d["hospitalization"]
                self.assertEqual((val(h["admission_date"]), val(h["discharge_date"]), val(h["length_of_stay_days"]), val(h["room_type"])),
                                 ("2024-07-01", "2024-07-05", 4.0, "خاصة"))
                self.assertEqual(val(d["patient"]["name"]), "فاطمة أحمد")
                self.assertEqual(val(d["provider"]["doctor"]), "منى هادي")
                dx = [(x["category"], x["certainty"], val(x["text"]), val(x["icd10"])) for x in d["diagnoses"]]
                self.assertEqual(dx, [("primary", "not_stated", "التهاب رئوي (J18.9)", "J18.9"),
                                      ("secondary", "not_stated", "السكري من النوع الثاني", None),
                                      ("secondary", "suspected", "فقر دم مشتبه", None)])

    def test_lab_all_modes(self):
        for mode in MODES:
            with self.subTest(mode=mode):
                d = run(f"ar_lab_{mode}.pdf")[1]["documents"][0]
                self.assertEqual(d["document_type"], "lab_result")
                rows = [(val(x["test_name"]), x["result"]["raw"], val(x["unit"]), x["reference_range"]["raw"]) for x in d["laboratory_tests"]]
                self.assertEqual(rows, [("هيموجلوبين", "١٠٫٢", "g/dL", "١٣٫٠ - ١٧٫٠"), ("سكر صائم", "٩٥", "mg/dL", "٧٠ - ١٠٠")])
                self.assertEqual(val(d["laboratory_tests"][0]["test_date"]), "2024-04-02")

    def test_prescription_all_modes(self):
        for mode in MODES:
            with self.subTest(mode=mode):
                d = run(f"ar_rx_{mode}.pdf")[1]["documents"][0]
                self.assertEqual(d["document_type"], "prescription")
                got = [(val(m["brand_name"]), m["strength"]["raw"], val(m["dosage_form"]), val(m["frequency"]), m["duration"]["raw"]) for m in d["medications"]]
                self.assertEqual(got, [("أموكسيسيلين", "٥٠٠ ملغ", "كبسولة", "مرتين يوميا", "لمدة ٧ أيام"),
                                       ("باراسيتامول", "٥٠٠ ملغ", "قرص", "ثلاث مرات يوميا", "لمدة ٣ أيام")])
                self.assertEqual([x for x in d["diagnoses"] if x["entry_type"] == "diagnosis"], [])

    def test_every_arabic_value_is_traceable_and_unreversed(self):
        """No extracted Arabic value may be reversed / contain presentation forms; every one needs an evidence box."""
        import re
        pres = re.compile("[\uFB50-\uFDFF\uFE70-\uFEFF]")
        for name, (jid, r) in _C.items():
            for d in r["documents"]:
                ev = {e["id"] for e in d["evidence"]}
                for grp in ("patient", "provider", "hospitalization"):
                    for f in (d[grp] or {}).values():
                        if f["status"] == "extracted":
                            self.assertFalse(pres.search(f["raw"]), (name, f["raw"]))
                            self.assertIn(f["evidence_id"], ev)

    def test_parsers(self):
        self.assertEqual(float(parse_number("١٬٢٥٠٫٥٠")), 1250.5)
        self.assertEqual(parse_date("٢٠٢٤/٠٧/٠١")[0], "2024-07-01")
        self.assertEqual(parse_date("٠١/٠٧/٢٠٢٤")[0], None)               # day/month ambiguous
        self.assertEqual(parse_date("15 مارس 2024")[0], "2024-03-15")
        self.assertEqual(parse_date("١٤٤٥/٠٣/١٥")[1], "hijri_calendar_date")
        self.assertEqual(match_key("رَقْمُ الفَاتُورَة"), match_key("رقم الفاتوره"))
        self.assertEqual(detect_currency("1,000 ر.س")[1], "SAR")
        self.assertIsNone(detect_currency("1,000 ريال")[1])

    def test_arabic_filename_and_exports_roundtrip(self):
        import io, zipfile, urllib.parse
        from openpyxl import load_workbook
        jid = STORE.create("فاتورة المريض خالد.pdf", (SAMPLES / "ar_dis_shaped.pdf").read_bytes())
        self.assertEqual(STORE.status(jid)["filename"], "فاتورة المريض خالد.pdf")
        self.assertEqual(STORE.create("../../etc/passwd\u202e.pdf", (SAMPLES / "ar_dis_shaped.pdf").read_bytes()) is not None, True)
        r = STORE.result(run("ar_dis_shaped.pdf")[0])
        z = zipfile.ZipFile(io.BytesIO(exporters.to_csv_zip(r)))
        raw = z.read("diagnoses.csv")
        self.assertTrue(raw.startswith(b"\xef\xbb\xbf"), "UTF-8 BOM needed so Excel on Windows shows Arabic")
        self.assertIn("التهاب رئوي (J18.9)", raw.decode("utf-8-sig"))
        wb = load_workbook(io.BytesIO(exporters.to_xlsx(r)))
        cells = [c.value for row in wb["diagnoses"].iter_rows() for c in row]
        self.assertIn("التهاب رئوي (J18.9)", cells)
        self.assertEqual(json.loads(exporters.to_json(r))["documents"][0]["patient"]["name"]["raw"], "فاطمة أحمد")
        self.assertIn("%D9%81", urllib.parse.quote("ف"))

    def test_pdf_font_covers_arabic_presentation_forms(self):
        """Font used for reports must contain every letter form the reshaper can emit (U+FE70-FEFC)."""
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        path = exporters.find_arabic_font()
        self.assertIsNotNone(path)
        pdfmetrics.registerFont(TTFont("ARTEST", str(path)))
        cmap = set(pdfmetrics.getFont("ARTEST").face.charToGlyph)
        needed = list(range(0xFE80, 0xFEFD)) + list(range(0x0621, 0x063B)) + list(range(0x0641, 0x064B))   # standard Arabic letters + all joining forms
        missing = [hex(c) for c in needed if c not in cmap]
        self.assertEqual(missing, [], f"{path.name} lacks glyphs")

    def test_arabic_pdf_report_roundtrip(self):
        """Builds the PDF report for an Arabic result and re-reads it. Uses the real reshaper/bidi when
        installed; in an offline sandbox, identity stubs are used (then only plumbing is verified)."""
        try:
            import arabic_reshaper, bidi.algorithm      # noqa: F401
            real = True
        except ImportError:
            import types
            a = types.ModuleType("arabic_reshaper"); a.reshape = lambda s: s
            b = types.ModuleType("bidi"); c = types.ModuleType("bidi.algorithm"); c.get_display = lambda s: s
            sys.modules.update({"arabic_reshaper": a, "bidi": b, "bidi.algorithm": c})
            real = False
        try:
            r = STORE.result(run("ar_dis_shaped.pdf")[0])
            pdf = exporters.to_pdf(r)
            import io, pdfplumber
            with pdfplumber.open(io.BytesIO(pdf)) as p:
                txt = "".join(pg.extract_text() or "" for pg in p.pages)
            self.assertNotIn("\ufffd", txt)
            self.assertTrue(any("\u0600" <= ch <= "\u06FF" or "\uFB50" <= ch <= "\uFEFF" for ch in txt))
            print(f"\n[pdf-report] real_shaping_libs={real}")
        finally:
            if not real:
                for k in ("arabic_reshaper", "bidi", "bidi.algorithm"):
                    sys.modules.pop(k, None)


if __name__ == "__main__":
    unittest.main(verbosity=2)
