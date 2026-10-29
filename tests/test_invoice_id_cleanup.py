"""Never drop an invoice digit except by exact standalone printed header word."""
import copy
import unittest
from mdia.extract import Ctx
from mdia.invoice_id_cleanup import repair_invoice_id
from mdia.model import Page, Line, Word


def sample(words,page_number=1,y=.12):
    p=Page(page_number,600,800,method="ocr",flags={"ocr_engine":"paddleocr-v5-arabic"})
    ww=[Word(text,.1+i*.16,y-.009,.23+i*.16,y+.009,.92,"ocr",
             geometry_source="line_interpolated") for i,text in enumerate(words)]
    p.lines=[Line(page_number,0,ww)]
    p.words=ww
    return p


def current(raw="INV-710159 9",page=1):
    return {"raw":raw,"value":raw,"page":page,"status":"extracted",
            "verification":"unverified","confidence":.75,
            "evidence_id":"original-evidence"}


class PrintedInvoiceIdTests(unittest.TestCase):
    def test_recovers_source_printed_exact_identifier_only(self):
        p=sample(["Invoice","No:","INV-710159","9"])
        ctx=Ctx("synthetic","invoice-test",{1:p})
        item=repair_invoice_id(current(),[p],ctx)
        self.assertEqual(item["value"],"INV-710159")
        self.assertEqual(item["raw"],"INV-710159")
        self.assertEqual(item["original_ocr_raw"],"INV-710159 9")
        self.assertEqual(item["original_ocr_evidence_id"],"original-evidence")
        self.assertEqual(ctx.evidence[-1]["matched_text"],"INV-710159")
        self.assertEqual(ctx.evidence[-1]["method"],"ocr")

    def test_multiple_invoice_identifiers_fails_closed(self):
        p=sample(["INV-710159","INV-710158","9"])
        ctx=Ctx("synthetic","test",{1:p})
        c=current(); self.assertIs(repair_invoice_id(c,[p],ctx),c)
        self.assertEqual(ctx.evidence,[])

    def test_merged_token_does_not_prove_boundary(self):
        p=sample(["No:INV-710159","9"])
        ctx=Ctx("synthetic","test",{1:p})
        c=current();self.assertIs(repair_invoice_id(c,[p],ctx),c)

    def test_different_printed_id_cannot_override(self):
        p=sample(["INV-710158","9"])
        ctx=Ctx("synthetic","test",{1:p})
        c=current();self.assertIs(repair_invoice_id(c,[p],ctx),c)

    def test_not_on_same_page_or_body_line(self):
        p=sample(["INV-710159","9"],2)
        ctx=Ctx("synthetic","test",{2:p})
        c=current();self.assertIs(repair_invoice_id(c,[p],ctx),c)
        p=sample(["INV-710159","9"],1,.65)
        ctx=Ctx("synthetic","test",{1:p})
        self.assertIs(repair_invoice_id(c,[p],ctx),c)

    def test_never_drop_nonone_digit_or_intended_suffix(self):
        p=sample(["INV-710159","9"])
        ctx=Ctx("synthetic","test",{1:p})
        for raw in ("INV-71015999","INV-710159 92","ABC-710159 9",
                    "INV-710159 9 0","INV-710159"):
            c=current(raw)
            self.assertIs(repair_invoice_id(c,[p],ctx),c)

    def test_missing_identifier_not_invented(self):
        p=sample(["INV-710159","9"])
        ctx=Ctx("synthetic","test",{1:p})
        c=current();c.update(status="not_found",raw=None,value=None)
        self.assertIs(repair_invoice_id(c,[p],ctx),c)

if __name__=="__main__":
    unittest.main()
