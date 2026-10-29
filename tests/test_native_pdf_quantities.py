"""Native PDF text rescue must not fabricate quantities or touch scans."""
import copy
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from mdia.native_pdf_quantities import recover_native_pdf_quantities


def field(raw, value, eid, box_y=.20, status="extracted"):
    return {"raw":raw,"value":value,"page":1,"evidence_id":eid,
            "status":status,"confidence":.9,"verification":"auto_verified"}


def fixture():
    p=SimpleNamespace(number=1,method="ocr",
                      words=[SimpleNamespace(text="الكمية",cx=.45,y0=.16)])
    doc={
        "document_id":"synthetic-no-patient",
        "invoice_items":[{
            "id":"it1","page":1,
            "service_name":field("تحليل دم شامل","تحليل دم شامل","n1"),
            "quantity":field("M",None,"q0",status="unreadable"),
            "unit_price":field("97.00",97,"p1"),
            "line_total":field("388.00",388,"t1"),
            "discount":{"status":"not_found"}
        }],
        "evidence":[
            {"id":"n1","bbox":[.81,.192,.93,.210]},
            {"id":"q0","bbox":[.45,.192,.49,.210]},
            {"id":"p1","bbox":[.30,.192,.36,.210]},
            {"id":"t1","bbox":[.11,.192,.18,.210]}
        ]
    }
    doc["invoice_items"][0]["quantity"]["verification"]="needs_review"
    doc["invoice_items"][0]["quantity"]["review_reasons"]=["unparseable_number"]
    return p,doc


def source_pdf(words):
    page=SimpleNamespace(width=600,height=800,extract_words=lambda **kw:words)
    return SimpleNamespace(pages=[page],close=lambda:None)


def native_word(text="4", x0=270,x1=288,top=155,bottom=168):
    return {"text":text,"x0":x0,"x1":x1,"top":top,"bottom":bottom}


class NativeQuantityEvidenceTests(unittest.TestCase):
    def test_exact_original_pdf_quantity_word_recovers_with_printed_arithmetic(self):
        page,doc=fixture()
        before=copy.deepcopy(doc)
        with patch("pdfplumber.open",return_value=source_pdf([native_word()])):
            recover_native_pdf_quantities(doc,"/tmp/synthetic.pdf",[page])
        q=doc["invoice_items"][0]["quantity"]
        self.assertEqual(q["value"],4)
        self.assertEqual(q["raw"],"4")
        self.assertEqual(q["original_ocr_raw"],"M")
        self.assertEqual(q["original_ocr_evidence_id"],"q0")
        self.assertEqual(q["recovery_method"],"direct_original_pdf_text_layer_word")
        self.assertEqual(doc["evidence"][:-1],before["evidence"])
        self.assertEqual(doc["evidence"][-1]["geometry_source"],"pdf_text")
        self.assertEqual(doc["evidence"][-1]["method"],"text-layer")
        self.assertEqual(doc["invoice_items"][0]["unit_price"],before["invoice_items"][0]["unit_price"])
        self.assertEqual(doc["invoice_items"][0]["line_total"],before["invoice_items"][0]["line_total"])
        self.assertEqual(len(doc["invoice_items"]),1)

    def test_no_pdf_text_layer_is_not_an_arithmetic_inference(self):
        page,doc=fixture(); before=copy.deepcopy(doc)
        with patch("pdfplumber.open",return_value=source_pdf([])):
            recover_native_pdf_quantities(doc,"/tmp/imageonly.pdf",[page])
        self.assertEqual(doc,before)

    def test_conflicting_or_two_numeric_words_cannot_choose(self):
        for words in ([native_word("4"),native_word("4",x0=273,x1=286)],
                      [native_word("5")], [native_word("4",x0=360,x1=380)],
                      [native_word("4",top=230,bottom=244)]):
            with self.subTest(words=words):
                page,doc=fixture();before=copy.deepcopy(doc)
                with patch("pdfplumber.open",return_value=source_pdf(words)):
                    recover_native_pdf_quantities(doc,"/tmp/synthetic.pdf",[page])
                self.assertEqual(doc,before)

    def test_missing_price_or_row_name_blocks(self):
        for key in ("unit_price","service_name","line_total"):
            with self.subTest(key=key):
                page,doc=fixture()
                doc["invoice_items"][0][key]["evidence_id"]=None
                before=copy.deepcopy(doc)
                with patch("pdfplumber.open",return_value=source_pdf([native_word()])):
                    recover_native_pdf_quantities(doc,"/tmp/synthetic.pdf",[page])
                self.assertEqual(doc,before)

    def test_discount_or_missing_header_blocks(self):
        page,doc=fixture(); doc["invoice_items"][0]["discount"]={"status":"extracted"}
        before=copy.deepcopy(doc)
        with patch("pdfplumber.open",return_value=source_pdf([native_word()])):
            recover_native_pdf_quantities(doc,"/tmp/synthetic.pdf",[page])
        self.assertEqual(doc,before)

        page,doc=fixture();page.words=[]
        before=copy.deepcopy(doc)
        with patch("pdfplumber.open",return_value=source_pdf([native_word()])):
            recover_native_pdf_quantities(doc,"/tmp/synthetic.pdf",[page])
        self.assertEqual(doc,before)

    def test_skips_text_layer_already_parsed_and_correct_quantity(self):
        page,doc=fixture()
        page.method="text-layer"
        before=copy.deepcopy(doc)
        with patch("pdfplumber.open",return_value=source_pdf([native_word()])):
            recover_native_pdf_quantities(doc,"/tmp/synthetic.pdf",[page])
        self.assertEqual(doc,before)
        page,doc=fixture()
        doc["invoice_items"][0]["quantity"].update(status="extracted",value=4)
        before=copy.deepcopy(doc)
        with patch("pdfplumber.open",return_value=source_pdf([native_word()])):
            recover_native_pdf_quantities(doc,"/tmp/synthetic.pdf",[page])
        self.assertEqual(doc,before)


if __name__=="__main__":
    unittest.main()
