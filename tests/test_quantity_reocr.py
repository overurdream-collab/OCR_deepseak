"""Independent original-PDF OCR is required before a misread M can become 3."""
import copy
import unittest

from mdia.model import Page
from mdia.quantity_reocr import choose_digit, recover_quantities


SOURCE_BOX=[.474,.170,.488,.187]
TBOX=[.477,.173,.485,.183]


def read(token="3",conf=.96,bbox=None,mode="original"):
    return {"text":token,"confidence":conf,"bbox":list(bbox or TBOX),
            "mode":mode,"lang":"ara+eng","psm":10}


def doc():
    return {
        "document_id":"synth-d1",
        "evidence":[{"id":"synth-d1-ev1","page":1,"text":"M","matched_text":"M",
                     "bbox":list(SOURCE_BOX),"geometry_source":"line_interpolated",
                     "method":"ocr","confidence":.96}],
        "warnings":[],
        "invoice_items":[{
            "id":"synthetic-row","page":1,
            "quantity":{"raw":"M","value":None,"page":1,
                        "status":"unreadable","evidence_id":"synth-d1-ev1",
                        "verification":"needs_review","review_reasons":["unparseable_number"]},
            "unit_price":{"raw":"59.25","value":59.25,"page":1,
                          "status":"extracted","evidence_id":"price-source"},
            "line_total":{"raw":"177.75","value":177.75,"page":1,
                          "status":"extracted","evidence_id":"total-source"},
            "discount":{"status":"not_found"}
        }]
    }


def pages(backend="paddleocr-v5-arabic"):
    return [Page(1,600,800,method="ocr",flags={"ocr_engine":backend})]


def run(reads,document=None):
    d=document if document is not None else doc()
    return recover_quantities(d,"synthetic.pdf",pages(),reader=lambda *args: reads)


class IndependentQuantityTests(unittest.TestCase):
    def test_high_confidence_source_ocr_plus_arithmetic_fixes_field(self):
        d=run([read(),read(conf=.91,mode="contrast4x")])
        f=d["invoice_items"][0]["quantity"]
        self.assertEqual(f["raw"],"3")
        self.assertEqual(f["value"],3.0)
        self.assertEqual(f["status"],"extracted")
        self.assertEqual(f["verification"],"auto_verified")
        self.assertEqual(f["original_ocr_raw"],"M")
        self.assertEqual(f["original_ocr_evidence_id"],"synth-d1-ev1")
        self.assertEqual(len(d["evidence"]),2)
        self.assertEqual(d["evidence"][0]["matched_text"],"M")
        self.assertEqual(d["evidence"][1]["matched_text"],"3")
        self.assertEqual(d["evidence"][1]["bbox"],TBOX)
        self.assertEqual(d["evidence"][1]["geometry_source"],"tesseract_word")

    def test_no_math_only_guessing(self):
        d=run([])
        self.assertEqual(d["invoice_items"][0]["quantity"]["raw"],"M")
        self.assertIsNone(d["invoice_items"][0]["quantity"]["value"])
        self.assertEqual(len(d["evidence"]),1)

    def test_misread_digit_with_matching_price_is_not_enough(self):
        d=run([read("5",.99),read("5",.91,mode="contrast4x")])
        self.assertIsNone(d["invoice_items"][0]["quantity"]["value"])

    def test_weak_ocr_cannot_override_original_m(self):
        d=run([read(conf=.62),read(conf=.67,mode="contrast4x")])
        self.assertEqual(d["invoice_items"][0]["quantity"]["status"],"unreadable")

    def test_different_high_confidence_numerals_block(self):
        d=run([read("3",.99),read("5",.9)])
        self.assertEqual(d["invoice_items"][0]["quantity"]["raw"],"M")

    def test_unrelated_original_text_does_not_get_rewritten(self):
        for raw in ("N","٣","3",""):
            with self.subTest(raw=raw):
                d=doc()
                d["invoice_items"][0]["quantity"]["raw"]=raw
                before=copy.deepcopy(d)
                run([read(),read(mode="contrast4x")],d)
                self.assertEqual(d,before)

    def test_wrong_numeric_quantity_requires_independent_source_reread(self):
        for raw in ("2", "m2"):
            d=doc(); q=d["invoice_items"][0]["quantity"]
            q.update(raw=raw,value=2.,status="extracted")
            d["evidence"][0]["matched_text"]=raw
            run([read("3",.96),read("3",.96,mode="contrast4x")],d)
            self.assertEqual(q["value"],3.)
            self.assertEqual(q["original_ocr_raw"],raw)
            self.assertEqual(d["evidence"][0]["matched_text"],raw)

    def test_numeric_mismatch_without_source_read_is_not_corrected(self):
        d=doc();q=d["invoice_items"][0]["quantity"]
        q.update(raw="2",value=2.,status="extracted")
        d["evidence"][0]["matched_text"]="2"
        run([],d)
        self.assertEqual(q["value"],2.)

    def test_correct_numeric_quantity_does_not_trigger_secondary_ocr(self):
        d=doc();q=d["invoice_items"][0]["quantity"]
        q.update(raw="3",value=3.,status="extracted")
        d["evidence"][0]["matched_text"]="3"
        calls=[]
        def observed(*args):
            calls.append(args)
            return [read(),read(mode="contrast4x")]
        before=copy.deepcopy(d)
        recover_quantities(d,"synthetic.pdf",pages(),reader=observed)
        self.assertEqual(calls,[])
        self.assertEqual(d,before)

    def test_no_discount_assumption(self):
        d=doc()
        d["invoice_items"][0]["discount"]={"status":"extracted","value":4}
        run([read()],d)
        self.assertEqual(d["invoice_items"][0]["quantity"]["status"],"unreadable")

    def test_not_paddle_source(self):
        d=doc()
        recover_quantities(d,"synthetic.pdf",pages("tesseract"),lambda *args:[read()])
        self.assertEqual(d["invoice_items"][0]["quantity"]["status"],"unreadable")

    def test_no_geometry_if_secondary_token_outside_original_line(self):
        d=run([read(bbox=[.47,.25,.48,.26]),read(bbox=[.47,.25,.48,.26],mode="contrast4x")])
        self.assertEqual(d["invoice_items"][0]["quantity"]["status"],"unreadable")

    def test_ocr_failure_is_local_not_document_failure(self):
        d=doc()
        def broken(*args):
            raise OSError("Tesseract unavailable")
        recover_quantities(d,"synthetic.pdf",pages(),reader=broken)
        self.assertIsNone(d["invoice_items"][0]["quantity"]["value"])

    def test_price_or_total_missing_blocks(self):
        for key in ("unit_price","line_total"):
            d=doc()
            d["invoice_items"][0][key]["status"]="not_found"
            run([read()],d)
            self.assertEqual(d["invoice_items"][0]["quantity"]["status"],"unreadable")

    def test_arabic_digits_from_second_ocr_are_accepted_when_confident(self):
        d=run([read("٣",.98),read("٣",.77,mode="contrast4x")])
        self.assertEqual(d["invoice_items"][0]["quantity"]["value"],3.0)
        self.assertEqual(d["invoice_items"][0]["quantity"]["raw"],"٣")

    def test_repeated_ocr_on_same_preprocessing_is_not_independent_confirmation(self):
        d=run([read("3",.99),read("3",.97)])
        self.assertEqual(d["invoice_items"][0]["quantity"]["status"],"unreadable")

    def test_source_observation_can_be_recovered_at_moderate_confidence_if_reproducible(self):
        d=run([read("3",.70),read("3",.72,mode="contrast4x")])
        self.assertEqual(d["invoice_items"][0]["quantity"]["value"],3.0)

    def test_source_seen_w_h_r_i_letters_are_reread_not_mapped(self):
        examples=(("w","4"),("H","3"),("R","3"),("I","1"))
        for original,digit in examples:
            with self.subTest(source_ocr=original):
                d=doc()
                d["invoice_items"][0]["quantity"]["raw"]=original
                d["evidence"][0]["matched_text"]=original
                d["evidence"][0]["text"]=original
                d["invoice_items"][0]["line_total"]["value"]=float(
                    int(digit)*59.25)
                result=run([read(digit,.96),read(digit,.9,mode="contrast4x")],d)
                qty=result["invoice_items"][0]["quantity"]
                self.assertEqual(qty["raw"],digit)
                self.assertEqual(qty["value"],float(digit))
                self.assertEqual(qty["original_ocr_raw"],original)
                self.assertEqual(result["evidence"][0]["matched_text"],original)

    def test_punctuation_glyphs_are_never_rewritten(self):
        for glyph in ("-","–","\\\\","°","/"):
            with self.subTest(glyph=glyph):
                d=doc()
                d["invoice_items"][0]["quantity"]["raw"]=glyph
                d["evidence"][0]["matched_text"]=glyph
                result=run([read(),read(mode="contrast4x")],d)
                self.assertEqual(result["invoice_items"][0]["quantity"]["status"],"unreadable")
                self.assertEqual(len(result["evidence"]),1)

    def test_secondary_ocr_still_needs_source_and_independent_arithmetic(self):
        d=doc()
        d["invoice_items"][0]["quantity"]["raw"]="w"
        d["evidence"][0]["matched_text"]="w"
        d["invoice_items"][0]["line_total"]["value"]=190.25
        out=run([read("4",.99),read("4",.99,mode="contrast4x")],d)
        self.assertIsNone(out["invoice_items"][0]["quantity"]["value"])

    def test_multiple_rows_cannot_borrow_another_quantity(self):
        d=doc()
        wrong=copy.deepcopy(d["invoice_items"][0])
        wrong["id"]="synthetic-other-row"
        wrong["quantity"]["evidence_id"]="missing-ev"
        d["invoice_items"].append(wrong)
        run([read()],d)
        self.assertEqual(d["invoice_items"][1]["quantity"]["status"],"unreadable")



class OriginalPixelRowIsolationTests(unittest.TestCase):
    def test_adjacent_quantities_cannot_contaminate_the_source_digit(self):
        import shutil
        import tempfile
        from pathlib import Path
        from mdia.quantity_reocr import numeric_reocr_crop, choose_digit
        from scripts.benchmark_invoice300 import new_case, english_invoice
        if not shutil.which("tesseract"):
            self.skipTest("real local Tesseract unavailable")
        # Actual source coordinates from real Paddle's en_compact_12 trace.
        # The old padded crop also included part of the preceding digit and
        # the next row's 1; this must read the middle printed 3 independently.
        with tempfile.TemporaryDirectory() as tmp:
            pdf=Path(tmp)/"adjacent_quantities.pdf"
            english_invoice(pdf,new_case("en_compact",12))
            reads=numeric_reocr_crop(pdf,1,[.53245,.23888,.54615,.25741])
            selected=choose_digit(reads,94,282)
        self.assertIsNotNone(selected)
        self.assertEqual(selected["text"],"3")
        self.assertGreaterEqual(selected["confidence"],.70)
        self.assertTrue(.23888 <= selected["bbox"][1] < selected["bbox"][3] <= .25741)

if __name__=="__main__":
    unittest.main()
