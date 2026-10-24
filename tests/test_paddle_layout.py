import unittest
from mdia.paddle_layout import normalized_tables


class PaddleLayoutTest(unittest.TestCase):
    def test_table_only_filters(self):
        pred={"res":{"boxes":[
            {"label":"table","score":.89,"coordinate":[10,20,200,160]},
            {"label":"text","score":.99,"coordinate":[12,30,50,60]},
            {"label":"table","score":.25,"coordinate":[10,20,210,165]}
        ]}}
        out=normalized_tables(pred,(400,400),confidence_threshold=.35)
        self.assertEqual(len(out),1)
        self.assertEqual(out[0]["bbox"],[.025,.05,.5,.4])
        self.assertIs(out[0]["pixel_ground_truth"],False)

    def test_wrong_page_box_rejected(self):
        self.assertEqual(normalized_tables({"res":{"boxes":[
            {"label":"table","score":.99,"coordinate":[-3,20,500,200]}
        ]}},(400,400)),[])

    def test_missing_predictions_not_accepted(self):
        with self.assertRaises(ValueError):
            normalized_tables({"res":{}},(400,400))

if __name__=="__main__":
    unittest.main()
