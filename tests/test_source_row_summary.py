"""The new paired gate cannot hide regressions or change original sources."""
import copy
import unittest
from tests.test_zero_error_acceptance import example
from scripts.summarize_source_row_repair300 import summarize


def fixture():
    r=example()
    for c in r['results']:
        c.update(source_pdf_sha256='a'*64,ocr_cache_sha256='b'*64)
        for check in c['checks']:check['expected']=check['actual']
    return r


class PairedSourceGateTests(unittest.TestCase):
    def test_perfect_unchanged_source_can_pass(self):
        a=fixture();r=summarize([a],[copy.deepcopy(a)])
        self.assertEqual(r['regression_status'],'PASS')
        self.assertEqual(r['release_status'],'PASS')

    def test_partial_improvement_does_not_mean_absolute_acceptance(self):
        a=fixture();a['results'][0]['review_required']=True
        r=summarize([a],[copy.deepcopy(a)])
        self.assertEqual(r['regression_status'],'PASS')
        self.assertEqual(r['release_status'],'BLOCKED')

    def test_one_lost_field_blocks_even_if_no_referral(self):
        a=fixture();b=copy.deepcopy(a);c=b['results'][0]
        c['checks'][0].update(matched=False,actual=None);c['matched']-=1
        r=summarize([a],[b]);self.assertEqual(r['regression_status'],'BLOCKED')
        self.assertEqual(len(r['lost']),1)

    def test_changed_or_missing_source_fingerprints_rejected(self):
        for key in ('source_pdf_sha256','ocr_cache_sha256'):
            a=fixture();b=copy.deepcopy(a);b['results'][0][key]='c'*64
            with self.assertRaises(ValueError):summarize([a],[b])
            del b['results'][0][key]
            with self.assertRaises(ValueError):summarize([a],[b])

    def test_extra_row_blocks(self):
        a=fixture();b=copy.deepcopy(a);b['results'][0]['extra_item_rows']=1
        r=summarize([a],[b]);self.assertEqual(r['regression_status'],'BLOCKED')
        self.assertEqual(r['release_status'],'BLOCKED')

    def test_changed_reference_value_rejected(self):
        a=fixture();b=copy.deepcopy(a);b['results'][0]['checks'][0]['expected']='different'
        with self.assertRaises(ValueError):summarize([a],[b])


if __name__=='__main__':unittest.main()
