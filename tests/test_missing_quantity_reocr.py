"""A missing OCR quantity needs a real header, row anchors and pixel evidence."""
import copy
import unittest
from mdia.model import Page,Word
from mdia.missing_quantity_reocr import recover_missing_quantities


def read(text='3',mode='original',box=None):
    return dict(text=text,mode=mode,confidence=.97,bbox=box or [.477,.173,.485,.183])


def fixture():
    fields={k:dict(status='extracted',page=1,evidence_id=k,value=v)
            for k,v in [('service_name','Lab Test'),('unit_price',59.25),('line_total',177.75)]}
    d={'document_id':'synthetic','evidence':[
        dict(id='service_name',bbox=[.10,.17,.30,.187]),
        dict(id='unit_price',bbox=[.60,.17,.70,.187]),
        dict(id='line_total',bbox=[.80,.17,.90,.187])],
        'invoice_items':[dict(id='row1',page=1,quantity=dict(status='not_found',value=None,raw=None),**fields)]}
    p=Page(1,600,800,'ocr',words=[Word('Qty',.47,.10,.49,.12)],flags={'ocr_engine':'paddleocr-v5-arabic'})
    return d,p


class MissingQuantityTests(unittest.TestCase):
    def run_read(self,d,p,reads):
        return recover_missing_quantities(d,'synthetic.pdf',[p],reader=lambda *args:reads)

    def test_source_read_with_explicit_quantity_column_is_linked(self):
        d,p=fixture();self.run_read(d,p,[read(),read(mode='contrast4x')])
        q=d['invoice_items'][0]['quantity']
        self.assertEqual(q['value'],3.)
        self.assertEqual(q['page'],1)
        e=d['evidence'][-1]
        self.assertEqual(q['evidence_id'],e['id'])
        self.assertEqual(e['matched_text'],'3')
        self.assertEqual(e['source_anchor_evidence_ids'],['service_name','unit_price','line_total'])
        self.assertFalse(e['word_box_verified'])

    def test_no_math_only_fill_and_no_single_preparation(self):
        for reads in ([],[read()], [read('2'),read('2',mode='contrast4x')]):
            d,p=fixture();old=copy.deepcopy(d);self.run_read(d,p,reads);self.assertEqual(d,old)

    def test_no_header_or_conflicting_columns(self):
        for header in ([],[Word('Qty',.47,.1,.49,.12),Word('Quantity',.35,.1,.37,.12)]):
            d,p=fixture();p.words=header;old=copy.deepcopy(d)
            self.run_read(d,p,[read(),read(mode='contrast4x')]);self.assertEqual(d,old)

    def test_adjacent_row_digit_cannot_be_borrowed(self):
        d,p=fixture();old=copy.deepcopy(d)
        self.run_read(d,p,[read(box=[.477,.21,.485,.23]),read(mode='contrast4x',box=[.477,.21,.485,.23])])
        self.assertEqual(d,old)

    def test_discount_unknown_amount_and_misaligned_rows_are_not_assumed(self):
        for change in ('discount','amount','row','source'):
            d,p=fixture()
            if change=='discount':d['invoice_items'][0]['discount']={'status':'extracted','value':10}
            if change=='amount':d['invoice_items'][0]['unit_price']['status']='not_found'
            if change=='row':d['evidence'][2]['bbox']=[.8,.3,.9,.32]
            if change=='source':p.flags={}
            old=copy.deepcopy(d);self.run_read(d,p,[read(),read(mode='contrast4x')]);self.assertEqual(d,old)

    def test_existing_quantity_is_never_replaced_by_missing_field_path(self):
        d,p=fixture();d['invoice_items'][0]['quantity'].update(status='extracted',raw='2',value=2.)
        old=copy.deepcopy(d);self.run_read(d,p,[read(),read(mode='contrast4x')]);self.assertEqual(d,old)

    def test_strong_conflicting_independent_reads_block(self):
        d,p=fixture();old=copy.deepcopy(d)
        self.run_read(d,p,[read(),read(mode='contrast4x'),read('4')]);self.assertEqual(d,old)


if __name__=='__main__':unittest.main()
