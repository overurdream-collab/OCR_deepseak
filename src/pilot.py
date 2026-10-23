"""Compare raw OCR coverage on synthetic medical PDFs.

DeepSeek-OCR2 is only invoked when explicitly requested; never replaced silently.
"""
import argparse
import hashlib
import io
import json
import sys
from pathlib import Path

import fitz
from PIL import Image

MODEL_ID = 'deepseek-ai/DeepSeek-OCR-2'
PROMPT = '<image>\n<|grounding|>Convert the document to markdown. '


def normalize(value):
    return ' '.join(str(value).casefold().split())


def render(page, scale=2.0):
    pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
    return Image.open(io.BytesIO(pix.tobytes('png'))).convert('RGB')


def cpu_baseline(pdf_path):
    import pytesseract
    texts = []
    with fitz.open(str(pdf_path)) as doc:
        for page in doc:
            direct = page.get_text('text').strip()
            if len(direct) >= 20:
                texts.append(direct)
            else:
                texts.append(pytesseract.image_to_string(render(page), lang='eng+ara', config='--psm 6'))
    return '\n'.join(texts)


class DeepSeekOCR2:
    def __init__(self):
        try:
            import torch
        except ImportError as exc:
            raise RuntimeError('PyTorch not installed. See official DeepSeek-OCR-2 README.') from exc
        if not torch.cuda.is_available():
            raise RuntimeError('DeepSeek-OCR 2 NOT RUN: no CUDA GPU available (explicitly no CPU fallback).')
        try:
            from transformers import AutoModel, AutoTokenizer
        except ImportError as exc:
            raise RuntimeError('Transformers not installed. Follow the upstream GPU setup instructions.') from exc
        self.tokenizer = AutoTokenizer.from_pretrained(MODEL_ID, trust_remote_code=True)
        self.model = AutoModel.from_pretrained(MODEL_ID,
            _attn_implementation='flash_attention_2', trust_remote_code=True,
            use_safetensors=True).eval().cuda().to(torch.bfloat16)

    def extract(self, pdf_path, output_dir):
        result_texts = []
        with fitz.open(str(pdf_path)) as doc:
            for page_num, page in enumerate(doc, start=1):
                page_dir = output_dir / f'page-{page_num:03d}'
                page_dir.mkdir(parents=True, exist_ok=True)
                image_file = page_dir / 'input.png'
                render(page).save(image_file)
                result = self.model.infer(self.tokenizer, prompt=PROMPT,
                    image_file=str(image_file), output_path=str(page_dir),
                    base_size=1024, image_size=768, crop_mode=True,
                    save_results=True)
                md_files = list(page_dir.rglob('*.md'))
                if md_files:
                    result_texts.append('\n'.join(p.read_text(encoding='utf-8') for p in md_files))
                else:
                    result_texts.append(str(result) if result is not None else '')
        return '\n'.join(result_texts)


def evaluate(text, expected):
    norm = normalize(text)
    per_field = {field: normalize(value) in norm for field, value in expected.items()}
    return {'matched': sum(per_field.values()), 'expected': len(per_field), 'per_field': per_field}


def run(samples, output, engine):
    truth = json.loads((samples / 'ground_truth.json').read_text(encoding='utf-8'))
    model = DeepSeekOCR2() if engine == 'deepseek-ocr2' else None
    output.parent.mkdir(parents=True, exist_ok=True)
    records = []
    for filename, expected in truth.items():
        src = samples / filename
        raw = model.extract(src, output.parent / 'deepseek_raw' / src.stem) if model else cpu_baseline(src)
        score = evaluate(raw, expected)
        records.append({
            'filename': filename, 'sha256': hashlib.sha256(src.read_bytes()).hexdigest(),
            'field_checks': score, 'raw_text': raw, 'engine': engine,
        })
        print(f'{filename}: {score["matched"]}/{score["expected"]} raw-text field checks matched')
    passed = sum(x['field_checks']['matched'] for x in records)
    checks = sum(x['field_checks']['expected'] for x in records)
    result = {
        'actual_engine': engine,
        'deepseek_model_executed': engine == 'deepseek-ocr2',
        'model_id': MODEL_ID if engine == 'deepseek-ocr2' else None,
        'metric': 'expected raw substring presence, NOT semantic field accuracy',
        'fields_matched': passed,
        'fields_expected': checks,
        'hit_rate': round(passed / checks, 4) if checks else None,
        'documents': records,
    }
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print('Saved', output)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--engine', choices=['hybrid', 'deepseek-ocr2'], default='hybrid')
    parser.add_argument('--samples', type=Path, default=Path('samples'))
    parser.add_argument('--output', type=Path, default=Path('results/hybrid.json'))
    args = parser.parse_args()
    try:
        run(args.samples, args.output, args.engine)
    except (RuntimeError, OSError) as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        sys.exit(2)


if __name__ == '__main__':
    main()
