"""Diagnose independent re-reading of PaddleOCR M-shaped quantities.

Fully synthetic PDF generator; independent Tesseract OCR on a small original
PDF crop, never a guessed value. Results are research evidence, not corrections.
"""
import json
import os
from pathlib import Path
import tempfile

from scripts.benchmark_invoice300 import new_case, arabic_invoice
from mdia.pipeline import process_job
from mdia.store import Store


CASES = (("ar_shaped", 18), ("ar_mixed", 18), ("ar_visual", 48))


def ocr_single_crop(image, box):
    import pytesseract
    from pytesseract import Output
    from PIL import ImageOps, ImageEnhance
    W, H = image.size
    x0, y0, x1, y1 = box
    # Preserve source geometry; pad fractionally to avoid clipping the glyph.
    pad_x = max(.006, (x1-x0)*.5)
    pad_y = max(.003, (y1-y0)*.6)
    rect = (max(0, int((x0-pad_x)*W)), max(0,int((y0-pad_y)*H)),
            min(W,int((x1+pad_x)*W)), min(H,int((y1+pad_y)*H)))
    crop = image.crop(rect)
    result = []
    for prep in ("raw", "gray4x"):
        if prep == "gray4x":
            crop_ready = ImageOps.autocontrast(crop.convert("L"))
            crop_ready = crop_ready.resize((crop_ready.width*4,crop_ready.height*4))
        else:
            crop_ready = crop
        for lang in ("eng", "ara+eng"):
            for psm in (10, 7, 13):
                data = pytesseract.image_to_data(
                    crop_ready, lang=lang, config=f"--oem 1 --psm {psm}",
                    output_type=Output.DICT)
                tokens = [(str(t).strip(),float(conf)) for t,conf in zip(data["text"],data["conf"])
                          if str(t).strip()]
                result.append({"preprocess":prep,"lang":lang,"psm":psm,
                               "tokens":tokens})
    # The second pass is deliberately constrained to printed numerals.
    # Do not infer a value from prices or totals at this stage.
    for preprocess in ("raw", "gray4x"):
        base = (ImageOps.autocontrast(crop.convert("L")).resize(
            (crop.width*4,crop.height*4)) if preprocess=="gray4x" else crop)
        for lang in ("eng", "ara+eng"):
            for psm in (10,13):
                data=pytesseract.image_to_data(
                    base,lang=lang,
                    config=f"--oem 1 --psm {psm} -c tessedit_char_whitelist=0123456789٠١٢٣٤٥٦٧٨٩",
                    output_type=Output.DICT)
                tokens=[(str(t).strip(),float(cf)) for t,cf in zip(data["text"],data["conf"]) if str(t).strip()]
                result.append({"preprocess":preprocess,"lang":lang,"psm":psm,
                               "whitelist":True,"tokens":tokens})
    return {"original_pdf_crop":rect, "trials":result}


def run():
    import pypdfium2 as pdfium
    report = {"synthetic_only":True, "cases":[]}
    with tempfile.TemporaryDirectory() as tmp:
        root=Path(tmp)
        for layout,index in CASES:
            case = new_case(layout,index)
            pdf=root/(case["id"]+".pdf")
            arabic_invoice(pdf,case)
            store=Store(root/case["id"])
            jid=store.create(pdf.name,pdf.read_bytes())
            original=os.environ.get("MDIA_OCR_ENGINE")
            try:
                os.environ["MDIA_OCR_ENGINE"]="paddle_arabic"
                process_job(store,jid,ocr_mode="force")
            finally:
                if original is None: os.environ.pop("MDIA_OCR_ENGINE",None)
                else: os.environ["MDIA_OCR_ENGINE"]=original
            pages_dir=store.path(jid,"pages")
            cache=json.loads((pages_dir/"1.json").read_text(encoding="utf-8"))
            image=pdfium.PdfDocument(str(pdf))[0].render(scale=300/72).to_pil().convert("RGB")
            suspects=[]
            for w in cache["words"]:
                if w["text"] != "M": continue
                bounds=w.get("box") or [w[key] for key in ("x0","y0","x1","y1")]
                suspects.append({"paddle_token":w["text"],
                                 "paddle_confidence":w["conf"],
                                 "paddle_geometry":bounds,
                                 "secondary":ocr_single_crop(image,bounds)})
            report["cases"].append({"case":case["id"],"M_tokens":len(suspects),
                                    "source_rows":len(case["rows"]),"suspects":suspects})
            print(case["id"],len(suspects),"suspects",flush=True)
    return report


if __name__=="__main__":
    import argparse
    ap=argparse.ArgumentParser()
    ap.add_argument("--output",type=Path,required=True)
    args=ap.parse_args()
    args.output.parent.mkdir(parents=True,exist_ok=True)
    data=run()
    args.output.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")
