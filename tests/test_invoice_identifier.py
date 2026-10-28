"""No guessed digits: recover exactly printed invoice IDs from OCR headers."""
import unittest
from mdia.invoice_identifier import observed_invoice_id
from mdia.extract import Ctx
from mdia.model import Line, Page, Word


def token(text,x0,x1,y=.10):
    return Word(text,x0,y-.006,x1,y+.006,.95,"ocr",
                geometry_source="line_interpolated")


def page(words,number=1,method="ocr"):
    p=Page(number,600,800,method=method,
           flags={"ocr_engine":"paddleocr-v5-arabic"} if method=="ocr" else {})
    p.lines=[Line(number,0,words)]
    p.words=words
    return p


class InvoiceIdentifierTests(unittest.TestCase):
    def test_ocr_merged_label_and_identifier_read_as_printed(self):
        p=page([token("Invoice",.05,.17),token("No:INV-710114",.18,.39)])
        hit=observed_invoice_id([p])
        self.assertIsNotNone(hit)
        src,line,word,number=hit
        self.assertEqual(number,"INV-710114")
        self.assertEqual(word.text,"No:INV-710114")
        ctx=Ctx("synthetic","synthetic-doc",{1:p})
        f=ctx.field(src,[word],raw=number,source=line.text)
        self.assertEqual(f["value"],"INV-710114")
        self.assertEqual(ctx.evidence[0]["text"],line.text)
        self.assertEqual(ctx.evidence[0]["matched_text"],number)

    def test_ocr_arabic_label_adjacent_to_standalone_number(self):
        p=page([token("INV-710520",.14,.34),token("رقم",.65,.72),
                token("الفاتورة:",.74,.89)])
        self.assertEqual(observed_invoice_id([p])[3],"INV-710520")

    def test_duplicate_same_id_on_two_pages_is_safe(self):
        p1=page([token("INV-710115",.22,.35)],1)
        p2=page([token("INV-710115",.22,.35)],2)
        self.assertEqual(observed_invoice_id([p1,p2])[3],"INV-710115")

    def test_conflicting_identifiers_are_not_resolved(self):
        p1=page([token("INV-710115",.22,.35)],1)
        p2=page([token("INV-710116",.22,.35)],2)
        self.assertIsNone(observed_invoice_id([p1,p2]))

    def test_never_invent_missing_identifier(self):
        p=page([token("Invoice",.10,.2),token("No:",.20,.25)])
        self.assertIsNone(observed_invoice_id([p]))
        self.assertIsNone(observed_invoice_id([page([token("INV-12",.1,.3)])]))

    def test_not_from_body_or_non_ocr_source(self):
        self.assertIsNone(observed_invoice_id([page([token("INV-710111",.1,.3,.51)])]))
        self.assertIsNone(observed_invoice_id([page([token("INV-710111",.1,.3)],method="text-layer")]))

    def test_do_not_take_embedded_suffix_after_id(self):
        p=page([token("No:INV-710159",.15,.36),token("9",.37,.39)])
        self.assertEqual(observed_invoice_id([p])[3],"INV-710159")


if __name__ == "__main__":
    unittest.main()
