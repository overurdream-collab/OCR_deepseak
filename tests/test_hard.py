"""Harder-layout regression tests. python -m unittest tests.test_hard -v"""
import json, os, sys, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
TMP = Path(tempfile.mkdtemp(prefix="mdia_hard_"))
os.environ["MDIA_DATA_DIR"] = str(TMP / "data")

from mdia.extract import ocr_digit_suggestion                # noqa: E402
from mdia.pipeline import process_job                        # noqa: E402
from mdia.store import Store                                 # noqa: E402
from mdia.textutil import last_amount                        # noqa: E402
from tests import hard_samples as H                          # noqa: E402

STORE, S, _C = Store(TMP / "store"), TMP / "samples", {}


def run(n):
    if n not in _C:
        jid = STORE.create(n + ".pdf", (S / f"{n}.pdf").read_bytes())
        _C[n] = (jid, process_job(STORE, jid))
    return _C[n]


def v(f):
    return None if f["status"] == "not_found" else (f["value"] if f["value"] is not None else f["raw"])


def items(d, *keys):
    return [tuple(v(i[k]) for k in keys) for i in d["invoice_items"]]


class Hard(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        H.build(S)

    def test_h1_columns_sections_wrap_discount(self):
        d = run("h1")[1]["documents"][0]
        self.assertEqual(d["document_type"], "clinic_invoice")
        inv = d["invoices"][0]
        self.assertEqual((v(inv["invoice_number"]), v(inv["invoice_date"]), v(inv["subtotal"]), v(inv["discount_total"]), v(inv["invoice_total"])),
                         ("H-778", "2024-03-25", 2241.0, 120.0, 2121.0))
        self.assertEqual(items(d, "service_name", "quantity", "unit_price", "discount", "line_total", "service_type"),
                         [("Complete Blood Count (CBC)", 1.0, 1200.0, 10.0, 1080.0, "LABORATORY"), ("Lipid Profile", 1.0, 950.5, 0.0, 950.5, "LABORATORY"),
                          ("Amoxicillin 500mg Capsules", 2.0, 45.25, 0.0, 90.5, "PHARMACY")])
        self.assertEqual(v(d["invoice_items"][0]["description"]), "with differential")
        self.assertEqual([(v(m["brand_name"]), v(m["strength"])) for m in d["medications"]], [("Amoxicillin 500mg Capsules", "500mg")])
        self.assertEqual([w for w in d["warnings"] if w["kind"].endswith("mismatch")], [])

    def test_h2_two_line_header_stacked_labels_negative_amounts(self):
        d = run("h2")[1]["documents"][0]
        self.assertEqual((v(d["invoices"][0]["invoice_number"]), v(d["patient"]["name"]), v(d["invoices"][0]["invoice_date"])),
                         ("RC-5521", "Nora Al Qahtani", "2024-08-09"))
        self.assertEqual(items(d, "service_name", "quantity", "unit_price", "line_total"),
                         [("Dental Scaling", 1.0, 300.0, 300.0), ("X-Ray Dental", 2.0, 40.0, 80.0), ("Loyalty Adjustment", 1.0, -20.0, -20.0)])
        self.assertEqual(v(d["invoices"][0]["invoice_total"]), 360.0)
        self.assertEqual([w for w in d["warnings"] if w["kind"].endswith("mismatch") or w["kind"].startswith("items_sum")], [])

    def test_negative_parentheses(self):
        self.assertEqual(float(last_amount("(20.00)")[1]), -20.0)
        self.assertEqual(float(last_amount("Discount (15%) 150.00")[1]), 150.0)

    def test_h3_ambiguous_dates_lists_and_no_duplicates(self):
        d = run("h3")[1]["documents"][0]
        h = d["hospitalization"]
        self.assertIsNone(h["admission_date"]["value"])
        self.assertEqual(h["admission_date"]["raw"], "03/09/2024")
        self.assertEqual(h["admission_date"]["verification"], "needs_review")
        self.assertEqual(h["discharge_date"]["value"], "2024-09-18")
        got = [(x["entry_type"], v(x["text"]), v(x["icd10"])) for x in d["diagnoses"]]
        self.assertEqual(got, [("diagnosis", "Acute appendicitis (K35.8)", "K35.8"), ("diagnosis", "Dehydration", None),
                               ("chronic_condition", "Hypertension", None), ("chronic_condition", "Asthma", None),
                               ("symptom", "Right lower quadrant pain", None), ("symptom", "Nausea and vomiting", None)])

    def test_h4_page_without_header_inherits_layout_safely(self):
        d = run("h4")[1]["documents"][0]
        self.assertEqual(d["pages"], [1, 2])
        self.assertEqual(items(d, "service_name", "quantity", "line_total", "service_type"),
                         [("Room Charges", 3.0, 600.0, None), ("Nursing Care", 3.0, 150.0, None), ("Surgical Supplies", 1.0, 340.0, None), ("Anesthesia", 1.0, 410.0, None)])
        self.assertEqual(v(d["invoices"][0]["invoice_total"]), 1725.0)
        self.assertTrue(any(w["kind"] == "table_layout_inherited" for w in d["warnings"]))
        self.assertEqual([w for w in d["warnings"] if w["kind"].endswith("mismatch") or w["kind"].startswith("items_sum")], [])
        self.assertTrue(all(i["quantity"]["confidence"] < 0.9 for i in d["invoice_items"][2:]))

    def test_h5_two_invoices_in_one_pdf(self):
        r = run("h5_two_invoices")[1]
        self.assertEqual([v(d["invoices"][0]["invoice_number"]) for d in r["documents"]], ["INV-A1", "INV-B2"])
        self.assertEqual([len(d["invoice_items"]) for d in r["documents"]], [4, 2])
        self.assertEqual([l["type"] for l in r["document_links"]], ["same_number_different_name"])
        self.assertTrue(r["document_links"][0]["needs_review"])

    def test_h6_pharmacy_items_become_medications(self):
        d = run("h6")[1]["documents"][0]
        self.assertEqual(d["document_type"], "pharmacy_invoice")
        self.assertEqual([(v(m["brand_name"]), v(m["strength"]), v(m["quantity_dispensed"]), v(m["total_price"])) for m in d["medications"]],
                         [("Metformin 850 mg Tablets", "850 mg", 2.0, 36.0), ("Insulin Glargine 100 IU/ml", "100 IU/ml", 1.0, 95.0),
                          ("Vitamin D3 1000 IU Capsules", "1000 IU", 3.0, 36.0)])
        self.assertTrue(all(m["invoice_item_id"] for m in d["medications"]))

    def test_h7_lab_sections_flags_and_ranges(self):
        d = run("h7")[1]["documents"][0]
        self.assertEqual([(v(x["test_name"]), v(x["result"]), v(x["unit"]), v(x["reference_range"]), v(x["flag"]), x["category"]) for x in d["laboratory_tests"]],
                         [("White Blood Cells", "11.8", "10^3/uL", "4.0 - 11.0", "H", "HEMATOLOGY"), ("Platelets", "250", "10^3/uL", "150 - 450", None, "HEMATOLOGY"),
                          ("C-Reactive Protein", "3.2", "mg/L", "< 5.0", None, "BIOCHEMISTRY"), ("Vitamin D", "18", "ng/mL", "30 - 100", "L", "BIOCHEMISTRY")])
        self.assertEqual(d["diagnoses"], [])

    def test_h8_stay_cost_from_explicit_room_charge_line(self):
        d = run("h8")[1]["documents"][0]
        c = d["hospitalization"]["accommodation_cost"]
        self.assertEqual((c["value"], c.get("derived_from_item") is not None), (1400.0, True))
        self.assertEqual(v(d["hospitalization"]["length_of_stay_days"]), 4.0)

    def test_h9_skewed_scan_is_deskewed_and_highlights_land_on_ink(self):
        from PIL import Image
        jid, r = run("h9_skew_scan")
        pi = r["page_info"][0]
        self.assertEqual(pi["method"], "ocr")
        d = r["documents"][0]
        self.assertTrue(STORE.path(jid, "pages", "1.json").exists())
        flags = json.loads(STORE.path(jid, "pages", "1.json").read_text("utf-8"))["flags"]
        self.assertGreater(abs(flags.get("deskew_deg", 0)), 1.0)
        inv = d["invoices"][0]
        self.assertEqual((v(inv["invoice_number"]), v(inv["invoice_total"])), ("H-778", 2121.0))
        names = [v(i["service_name"]) for i in d["invoice_items"]]
        self.assertGreaterEqual(sum(n in ("Complete Blood Count (CBC)", "Lipid Profile", "Amoxicillin 500mg Capsules") for n in names), 2)
        img = Image.open(STORE.path(jid, "pages", "1.png")).convert("L")
        W_, H_ = img.size
        hit = tot = 0
        for e in d["evidence"]:
            b = e["bbox"]
            crop = img.crop((int(b[0] * W_), int(b[1] * H_), max(int(b[2] * W_), int(b[0] * W_) + 2), max(int(b[3] * H_), int(b[1] * H_) + 2)))
            px = list(crop.tobytes())
            tot += 1
            hit += (sum(p < 140 for p in px) / len(px)) > 0.03
        self.assertGreater(hit / tot, 0.9, f"{hit}/{tot} evidence boxes contain ink")
        for i in d["invoice_items"]:
            for k in ("quantity", "unit_price", "line_total"):
                if i[k]["status"] == "unreadable":
                    self.assertEqual(i[k]["verification"], "needs_review")

    def test_ocr_digit_suggestions_are_suggestions_only(self):
        self.assertEqual(float(ocr_digit_suggestion("45:25")), 45.25)
        self.assertEqual(float(ocr_digit_suggestion("l,200.OO")), 1200.0)
        self.assertIsNone(ocr_digit_suggestion("abc"))

    def test_arithmetic_suggestion_names_single_digit_slip(self):
        from mdia.validate import _suggest
        from decimal import Decimal as D
        s = _suggest(D(2), D("12.50"), D("35.00"))
        self.assertEqual(s[0], {"field": "line_total", "stated": 35.0, "would_be_consistent_if": 25.0})
        self.assertEqual({x["field"] for x in s}, {"line_total", "unit_price"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
