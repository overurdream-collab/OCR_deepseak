"""EVIDENCE-01 synthetic-only tests. No model download or clinical information."""
import unittest

from mdia.extract import Ctx
from mdia.model import Page, Word
from mdia.reader import _to_original_space
from mdia.word_localization import align_from_tesseract_data


def source(*rows):
    return {key: [row[key] for row in rows]
            for key in ("text", "conf", "left", "top", "width", "height")}


def row(text="أموكسيسيلين", conf="94", left=640, top=205, width=88, height=35):
    return dict(text=text, conf=conf, left=left, top=top, width=width, height=height)


def word(text="أموكسيسيلين"):
    return Word(text, .60, .20, .74, .25, .97, "ocr",
                geometry_source="line_interpolated")


class TestEvidence01(unittest.TestCase):
    def test_positive_unique_second_engine_match(self):
        w = word()
        align_from_tesseract_data([w], source(row()), (1000, 1000))
        self.assertEqual(w.geometry_source, "cross_engine_word_match")
        self.assertEqual(w.box, [.64, .205, .728, .24])
        self.assertEqual(w.text, "أموكسيسيلين")
        self.assertEqual(w.conf, .97)

    def test_wrong_token_does_not_create_a_box(self):
        w = word()
        align_from_tesseract_data([w], source(row(text="باراسيتامول")), (1000, 1000))
        self.assertEqual(w.geometry_source, "line_interpolated")
        self.assertIsNone(w.box)

    def test_wrong_row_is_rejected(self):
        w = word()
        align_from_tesseract_data([w], source(row(top=400)), (1000, 1000))
        self.assertIsNone(w.box)

    def test_low_confidence_is_rejected(self):
        w = word()
        align_from_tesseract_data([w], source(row(conf="40")), (1000, 1000))
        self.assertIsNone(w.box)

    def test_duplicate_word_candidates_are_not_guessed(self):
        w = word()
        align_from_tesseract_data([w], source(row(), row()), (1000, 1000))
        self.assertIsNone(w.box)

    def test_wrong_column_is_rejected(self):
        w = word()
        align_from_tesseract_data([w], source(row(left=100)), (1000, 1000))
        self.assertIsNone(w.box)

    def test_short_list_number_is_not_claimed_as_word_geometry(self):
        w = word("١")
        align_from_tesseract_data([w], source(row(text="1", width=10)), (1000, 1000))
        self.assertIsNone(w.box)

    def test_malformed_secondary_ocr_data_rejected(self):
        with self.assertRaisesRegex(ValueError, "misaligned"):
            align_from_tesseract_data([word()], {"text": ["a"], "conf": [],
                "left": [], "top": [], "width": [], "height": []}, (1000, 1000))

    def test_exact_field_annotated_but_not_ground_truth(self):
        w = word()
        align_from_tesseract_data([w], source(row()), (1000, 1000))
        p = Page(1, 1000, 1000, "ocr", words=[w],
                 flags={"ocr_engine": "paddleocr-v5-arabic"})
        ctx = Ctx("job", "doc", {1: p})
        ctx.evidence_for(p, [w], w.text, w.text)
        self.assertEqual(ctx.evidence[0]["geometry_source"], "cross_engine_word_match")
        self.assertIs(ctx.evidence[0]["word_box_verified"], False)

    def test_substring_from_whole_line_is_not_word_precise(self):
        w = word()
        align_from_tesseract_data([w], source(row()), (1000, 1000))
        p = Page(1, 1000, 1000, "ocr", words=[w],
                 flags={"ocr_engine": "paddleocr-v5-arabic"})
        ctx = Ctx("job", "doc", {1: p})
        ctx.evidence_for(p, [w], "اسم آخر", w.text)
        self.assertEqual(ctx.evidence[0]["geometry_source"], "line_interpolated")

    def test_box_preserved_through_deskew_mapping(self):
        w = word()
        align_from_tesseract_data([w], source(row()), (1000, 1000))
        _to_original_space([w], 0, 1000, 1000)
        self.assertEqual([round(v, 3) for v in w.box], [.64, .205, .728, .24])

    def test_cached_geometry_source_remains_explicit(self):
        w = word()
        p = Page(1, 1000, 1000, "ocr", words=[w])
        restored = Page.from_cache(p.to_cache())
        self.assertEqual(restored.words[0].geometry_source, "line_interpolated")


if __name__ == "__main__":
    unittest.main()
