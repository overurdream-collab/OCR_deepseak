"""Optional, isolated vision-only table detector for Arabic/English medical PDFs.

Free pretrained weights from microsoft/table-transformer-{detection,structure-recognition}
(MIT); models are downloaded ONLY when this optional experiment is explicitly
called. No remote inference or patient data is sent anywhere by this code.
Never edits amounts, recognized OCR text, or evidence references.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

DETECTION_MODEL = "microsoft/table-transformer-detection"
STRUCTURE_MODEL = "microsoft/table-transformer-structure-recognition"
MAX_IMAGE_EDGE = 1800

@dataclass(frozen=True)
class Region:
    label: str
    confidence: float
    box: tuple[float, float, float, float]  # [0..1], original page image coordinates
    model: str

    def as_dict(self):
        return {"label": self.label, "confidence": self.confidence,
                "bbox": list(self.box), "model": self.model,
                "pixel_ground_truth": False}


def region(label: str, confidence: float, box: list, width: int, height: int, model: str) -> Region:
    """Fail closed on any geometry outside page or malformed confidence."""
    from math import isfinite
    if not isinstance(label, str) or not label.strip() or width <= 0 or height <= 0:
        raise ValueError("invalid region")
    if not (isinstance(box, (tuple, list)) and len(box) == 4):
        raise ValueError("malformed bbox")
    values = [float(v) for v in box]
    score = float(confidence)
    if not all(isfinite(v) for v in values) or not isfinite(score) or not 0 <= score <= 1:
        raise ValueError("invalid coordinates/confidence")
    x0, y0, x1, y1 = values
    if not (0 <= x0 < x1 <= width and 0 <= y0 < y1 <= height):
        raise ValueError("out of page bbox")
    return Region(label, round(score, 4),
                  (x0 / width, y0 / height, x1 / width, y1 / height), model)


def crop_box(region_: Region, width: int, height: int) -> tuple[int, int, int, int]:
    """Convert normalized bbox to PIL crop, with NO unbounded margins."""
    import math
    box = region_.box
    v = (max(0, math.floor(box[0]*width)), max(0, math.floor(box[1]*height)),
         min(width, math.ceil(box[2]*width)), min(height, math.ceil(box[3]*height)))
    if v[2] <= v[0] or v[3] <= v[1]:
        raise ValueError("empty crop")
    return v


def remap_crop(region_: Region, crop: tuple, page_size: tuple) -> Region:
    """Map a structure bbox from crop coordinates back to full PDF page."""
    px0, py0, px1, py1 = crop
    width, height = page_size
    if not (0 <= px0 < px1 <= width and 0 <= py0 < py1 <= height):
        raise ValueError("invalid page crop")
    cw, ch = px1-px0, py1-py0
    b = region_.box
    return region(region_.label, region_.confidence,
                  [px0+b[0]*cw, py0+b[1]*ch, px0+b[2]*cw, py0+b[3]*ch],
                  width, height, region_.model)


def _predict(model, processor, image, threshold, name: str):
    import torch
    pixels = processor(images=image, return_tensors="pt")
    with torch.inference_mode():
        outputs = model(**pixels)
    predictions = processor.post_process_object_detection(
        outputs, threshold=threshold, target_sizes=torch.tensor([[image.height, image.width]]))[0]
    detected = []
    for label, score, box in zip(predictions["labels"], predictions["scores"], predictions["boxes"]):
        label_id = int(label.item())
        label_text = str(model.config.id2label[label_id]).lower()
        try:
            detected.append(region(label_text, score.item(), box.tolist(),
                                   image.width, image.height, name))
        except ValueError:
            continue
    return detected


class TableVision:
    def __init__(self, device="cpu"):
        if device != "cpu":
            raise ValueError("Pilot is CPU only; do not allocate paid/GPU services")
        from transformers import AutoImageProcessor, AutoModelForObjectDetection
        self.det_processor = AutoImageProcessor.from_pretrained(
            DETECTION_MODEL, use_fast=False, trust_remote_code=False)
        self.det_model = AutoModelForObjectDetection.from_pretrained(
            DETECTION_MODEL, use_safetensors=True, trust_remote_code=False)
        self.det_model.eval()
        self.structure_processor = AutoImageProcessor.from_pretrained(
            STRUCTURE_MODEL, use_fast=False, trust_remote_code=False)
        self.structure_model = AutoModelForObjectDetection.from_pretrained(
            STRUCTURE_MODEL, use_safetensors=True, trust_remote_code=False)
        self.structure_model.eval()

    def analyze(self, image, table_threshold=0.65, structure_threshold=0.50):
        """Independent visual *suggestions*. No guessed OCR text or invoice amounts."""
        if image.width <= 0 or image.height <= 0:
            raise ValueError("invalid image")
        page_size = image.size
        # Inference uses resized image; positions are returned in original coordinates.
        if max(page_size) > MAX_IMAGE_EDGE:
            ratio = MAX_IMAGE_EDGE/max(page_size)
            small = image.resize((int(image.width*ratio), int(image.height*ratio)))
        else:
            small = image
        tables = _predict(self.det_model, self.det_processor, small,
                          table_threshold, DETECTION_MODEL)
        # Remap normalized boxes (coordinates are relative to the image).
        proposals = []
        for table in tables:
            if table.label not in ("table", "table rotated"):
                continue
            crop = crop_box(table, image.width, image.height)
            cut = image.crop(crop)
            if cut.width < 32 or cut.height < 32:
                continue
            structures = _predict(self.structure_model, self.structure_processor, cut,
                                  structure_threshold, STRUCTURE_MODEL)
            mapped = [remap_crop(s, crop, page_size) for s in structures]
            rows = [x for x in mapped if x.label == "table row"]
            cols = [x for x in mapped if x.label == "table column"]
            proposals.append({"table": table.as_dict(),
                              "rows": [x.as_dict() for x in sorted(rows, key=lambda z: z.box[1])],
                              "columns": [x.as_dict() for x in sorted(cols, key=lambda z: z.box[0])],
                              "structure": [x.as_dict() for x in mapped],
                              "note": "proposals_only_not_ocr_and_not_ground_truth"})
        return {"engine": "table-transformer", "image_size": list(page_size),
                "table_count": len(proposals),
                "row_count": sum(len(x["rows"]) for x in proposals),
                "column_count": sum(len(x["columns"]) for x in proposals),
                "proposals": proposals,
                "changes_to_financial_fields": 0,
                "human_review_required": True}
