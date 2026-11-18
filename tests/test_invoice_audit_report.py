"""Offline HTML report sanitization and read-only disclosure."""
import unittest

from invoice_audit.report import render_html


class HtmlReportTests(unittest.TestCase):
    def test_escapes_untrusted_item_and_rule(self):
        html = render_html({"status": "VERIFIED_EXCEPTION", "approval": False,
                            "findings": [{"rule": "<script>alert(1)</script>",
                                          "sku": '<img src=x onerror="alert(1)">',
                                          "difference": "5"}],
                            "reasons": ["<svg onload=alert(1)>"]})
        self.assertNotIn("<script>", html)
        self.assertNotIn("<img src=x", html)
        self.assertNotIn("<svg onload", html)
        self.assertIn("&lt;script&gt;", html)
        self.assertIn("لا يمثل هذا التقرير اعتماد دفع", html)

    def test_rejects_any_payment_approval(self):
        with self.assertRaises(ValueError):
            render_html({"approval": True})


if __name__ == "__main__":
    unittest.main()
