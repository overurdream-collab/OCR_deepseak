"""Lightweight PaddleOCR PP-DocLayout-S TABLE region candidates.

Uses Apache 2.0 PaddleOCR (already the project's OCR provider), downloads
public model weights only when explicitly run. Never changes invoice fields.
"""
from mdia.table_ai import region

MODEL_NAME = "PP-DocLayout-S"


def normalized_tables(prediction, image_size, confidence_threshold=.35):
    w,h = image_size
    if not isinstance(prediction, dict):
        raise ValueError("layout result must be dict")
    payload = prediction.get("res", prediction)
    if not isinstance(payload, dict) or not isinstance(payload.get("boxes"), list):
        raise ValueError("layout boxes missing")
    tables = []
    for candidate in payload["boxes"]:
        if str(candidate.get("label", "")).lower() != "table":
            continue
        score = float(candidate.get("score", -1))
        if score < confidence_threshold:
            continue
        bbox = candidate.get("coordinate")
        try:
            obj = region("table", score, bbox, w,h,MODEL_NAME)
        except (ValueError, TypeError):
            continue
        tables.append(obj.as_dict())
    return tables


class PaddleLayoutPilot:
    def __init__(self):
        from paddleocr import LayoutDetection
        self.model = LayoutDetection(model_name=MODEL_NAME)

    def analyze(self, image_path, image_size):
        results = self.model.predict(str(image_path), batch_size=1, layout_nms=True)
        tables = []
        for res in results:
            obj = res.json
            obj = obj() if callable(obj) else obj
            tables.extend(normalized_tables(obj, image_size))
        return {"engine": MODEL_NAME, "table_count": len(tables),
                "table_regions": tables, "image_size": list(image_size),
                "recognizes_arabic_text": False, "changes_to_financial_fields": 0,
                "human_review_required": True}
