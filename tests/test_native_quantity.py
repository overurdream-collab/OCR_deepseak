"""Independent PDF text must literally contain the recovered OCR quantity.

No divide-and-guess: arithmetic is only a second independent check for a
source-observed single digit at the right spatial position.
"""
import copy
import unittest
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import patch

from mdia.native_quantity import _one_printed_qty, recover_native_quantities


def box(a,b,c,d=.20):
    return [a,d-.01,b,d+.01] if c is None else [a,d-.01,b,d+.01]


def native(text, x, y=.20):
    return {"text":text,"bbox":[x-.014,y-.007,x+.014,y+.007],
            "cx":x,"cy":y}


class NativeQuantityLogicTests(unittest.TestCase):
    def candidate(self, glyph="3", rtl=False):
        if rtl:
            name=[.79,.18,.96,.22]
            unit=[.35,.18,.43,.22]
            total=[.16,.18,.25,.22]
            words=[native("فحص",.86),native(glyph,.60),
                   native("59.25",.39),native("177.75",.20)]
        else:
            name=[.11,.18,.31,.22]
            unit=[.60,.18,.70,.22]
            total=[.79,.18,.90,.22]
            words=[native("Consultation",.20),native(glyph,.47),
                   native("59.25",.65),native("177.75",.84)]
        return words,name,unit,total

    def test_printed_digit_recovered_in_english_and_arabic(self):
        for rtl in (False,True):
            words,n,u,t=self.candidate(rtl=rtl)
            candidate=_one_printed_qty(words,n,u,t,Decimal("59.25"),Decimal("177.75"))
            self.assertIsNotNone(candidate)
            self.assertEqual(candidate[0],3)
            self.assertEqual(candidate[1]["text"],"3")

    def test_no_quantity_is_never_calculated_from_total(self):
        words,n,u,t=self.candidate("H")
        self.assertIsNone(_one_printed_qty(words,n,u,t,Decimal("59.25"),Decimal("177.75")))

    def test_wrong_printed_digit_cannot_be_repaired_by_arithmetic(self):
        words,n,u,t=self.candidate("2")
        self.assertIsNone(_one_printed_qty(words,n,u,t,Decimal("59.25"),Decimal("177.75")))

    def test_unmatched_printed_prices_cannot_create_quantity(self):
        words,n,u,t=self.candidate()
        self.assertIsNone(_one_printed_qty(words,n,u,t,Decimal("60.25"),Decimal("177.75")))
        self.assertIsNone(_one_printed_qty(words,n,u,t,Decimal("59.25"),Decimal("177.74")))

    def test_duplicate_digits_or_adjacent_row_rejected(self):
        words,n,u,t=self.candidate()
        words.append(native("3",.51))
        self.assertIsNone(_one_printed_qty(words,n,u,t,Decimal("59.25"),Decimal("177.75")))
        words,n,u,t=self.candidate()
        words[1]=native("3",.47,.27)
        self.assertIsNone(_one_printed_qty(words,n,u,t,Decimal("59.25"),Decimal("177.75")))

    def test_wide_printed_service_to_price_corridor(self):
        # Real en_compact_12 Creatinine Test: the gap is .45667,
        # just beyond the old arbitrary .45 limit. Digit is source-read.
        words,n,u,t=self.candidate()
        n[0],n[2]=.07336,.19105
        u[0],u[2]=.64772,.69528
        words[2]=native("59.25",.6715)
        candidate=_one_printed_qty(words,n,u,t,Decimal("59.25"),Decimal("177.75"))
        self.assertIsNotNone(candidate)
        self.assertEqual(candidate[0],3)

    def test_arithmetic_cannot_choose_between_two_printed_digits(self):
        words,n,u,t=self.candidate()
        words.append(native("2",.51))
        self.assertIsNone(_one_printed_qty(words,n,u,t,Decimal("59.25"),Decimal("177.75")))

    def test_misaligned_or_overlapping_row_rejected(self):
        words,n,u,t=self.candidate()
        t[1],t[3]=.38,.42
        self.assertIsNone(_one_printed_qty(words,n,u,t,Decimal("59.25"),Decimal("177.75")))
        words,n,u,t=self.candidate()
        n[2]=.64
        self.assertIsNone(_one_printed_qty(words,n,u,t,Decimal("59.25"),Decimal("177.75")))


class NativeQuantityIntegrationTests(unittest.TestCase):
    def document(self):
        return {
            "document_id":"synthetic-1",
            "evidence":[
                {"id":"name","bbox":[.11,.19,.31,.21]},
                {"id":"price","bbox":[.60,.19,.70,.21]},
                {"id":"total","bbox":[.79,.19,.90,.21]},
            ],
            "invoice_items":[{
                "id":"it1","page":1,
                "service_name":{"status":"extracted","value":"Consultation","evidence_id":"name"},
                "unit_price":{"status":"extracted","value":59.25,"evidence_id":"price"},
                "line_total":{"status":"extracted","value":177.75,"evidence_id":"total"},
                "quantity":{"status":"unreadable","raw":"H","value":None,
                            "evidence_id":"old-qty","review_reasons":["unparseable_number"]}
            }]
        }

    def test_source_linked_quantity_without_external_ocr(self):
        words,n,u,t=NativeQuantityLogicTests().candidate()
        class Page:
            width=1000
            height=1000
            def extract_words(self):
                return [dict(text=w["text"],x0=w["bbox"][0]*1000,
                            x1=w["bbox"][2]*1000,top=w["bbox"][1]*1000,
                            bottom=w["bbox"][3]*1000) for w in words]
        class PDF:
            pages=[Page()]
            def __enter__(self):return self
            def __exit__(self,*_):return False
        d=self.document()
        with patch("pdfplumber.open",return_value=PDF()):
            recover_native_quantities(d, "synthetic.pdf", [
                SimpleNamespace(number=1,flags={"ocr_engine":"paddleocr-v5-arabic"})])
        qty=d["invoice_items"][0]["quantity"]
        self.assertEqual(qty["value"],3.)
        self.assertEqual(qty["raw"],"3")
        self.assertEqual(qty["original_ocr_raw"],"H")
        self.assertEqual(d["evidence"][-1]["method"],"text-layer")
        self.assertEqual(d["evidence"][-1]["geometry_source"],"pdf_text")
        self.assertTrue(d["evidence"][-1]["word_box_verified"])
        self.assertEqual(d["evidence"][-1]["matched_text"],"3")

    def test_scanned_pdf_without_text_does_not_guess(self):
        class Page:
            width=1000
            height=1000
            def extract_words(self):return []
        class PDF:
            pages=[Page()]
            def __enter__(self):return self
            def __exit__(self,*_):return False
        d=self.document();old=copy.deepcopy(d)
        with patch("pdfplumber.open",return_value=PDF()):
            recover_native_quantities(d,"scan.pdf",[
                SimpleNamespace(number=1,flags={"ocr_engine":"paddleocr-v5-arabic"})])
        self.assertEqual(d,old)

    def test_without_original_paddle_source_does_nothing(self):
        d=self.document();old=copy.deepcopy(d)
        recover_native_quantities(d,"synthetic.pdf",[
            SimpleNamespace(number=1,flags={})])
        self.assertEqual(d,old)


if __name__=="__main__":
    unittest.main()
