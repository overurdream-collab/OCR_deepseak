"""Model-free guards for the optional Table Transformer experiment."""
import unittest
from mdia.table_ai import Region, crop_box, region, remap_crop, DETECTION_MODEL, STRUCTURE_MODEL


class TableAIGeometryTests(unittest.TestCase):
    def test_normalization(self):
        x = region("table row", .93, [50, 200, 450, 240], 1000, 500, STRUCTURE_MODEL)
        self.assertEqual(x.box, (.05, .4, .45, .48))
        self.assertFalse(x.as_dict()["pixel_ground_truth"])

    def test_crop_mapping(self):
        tab = region("table", .9, [100, 150, 600, 400], 1000, 600, DETECTION_MODEL)
        crop = crop_box(tab, 1000, 600)
        self.assertEqual(crop, (100, 150, 600, 400))
        row = region("table row", .95, [10, 20, 300, 65], 500, 250, STRUCTURE_MODEL)
        remapped = remap_crop(row, crop, (1000, 600))
        self.assertEqual([round(x, 4) for x in remapped.box],
                         [.11, .2833, .40, .3917])

    def test_offpage_box_rejected(self):
        for bbox in ([10, 10, 101, 50], [-1, 5, 20, 35],
                     [10, 10, 10, 50], [20, 40, 10, 50],
                     [float('nan'), 1, 10, 20]):
            with self.subTest(bbox=bbox), self.assertRaises(ValueError):
                region("table", .9, bbox, 100, 100, DETECTION_MODEL)

    def test_score_must_be_finite_and_valid(self):
        for score in (-.1, 1.2, float("nan")):
            with self.subTest(score=score), self.assertRaises(ValueError):
                region("table", score, [1, 2, 20, 30], 50, 50, DETECTION_MODEL)

    def test_coordinates_must_remain_source_based(self):
        # A hallucinated extra row must never change the printed amount.
        r = Region("table row", 0.81, (.1, .2, .4, .3), STRUCTURE_MODEL)
        value = r.as_dict()
        self.assertNotIn("quantity", value)
        self.assertNotIn("unit_price", value)
        self.assertNotIn("line_total", value)


if __name__ == "__main__":
    unittest.main()
