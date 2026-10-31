"""Compare baseline and candidate extraction on IDENTICAL cached real OCR.

The old native-quantity module is loaded from an explicit git commit. Original
PDFs are rendered/OCRed once per case, then both complete extraction pipelines
run against those same cached pages. Ground truth is only used by the scorer.
"""
import argparse
import hashlib
import importlib.util
import json
import os
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch

from scripts import benchmark_invoice300 as benchmark
from mdia import native_quantity, quantity_reocr, missing_quantity_reocr, paddle_arabic, pipeline

BASELINE = '5fbf98f51a2ac0b1df5f609a18743849faa6fe5a'


def run(output, shard=0, shards=6):
    source = subprocess.check_output(['git', 'show', BASELINE + ':mdia/native_quantity.py'])
    crop_source = subprocess.check_output(['git', 'show', BASELINE + ':mdia/quantity_reocr.py'])
    extract_source = subprocess.check_output(['git', 'show', BASELINE + ':mdia/extract.py'])
    tables_source = subprocess.check_output(['git', 'show', BASELINE + ':mdia/tables.py'])
    baseline_records = []
    cases = {c['id'] + '.pdf': c for c in benchmark.all_cases()}
    # Bound inference threads so paired shards do not oversubscribe a CPU host.
    from paddleocr import PaddleOCR
    from mdia.paddle_arabic import _load_model
    with patch('paddleocr.PaddleOCR', lambda **kw: PaddleOCR(cpu_threads=2, **kw)):
        _load_model()
    original_process = benchmark.process_job
    original_score = benchmark.score_record
    original_ocr = paddle_arabic.ocr_image
    fingerprints = {}
    ocr_calls = []
    def tracked_ocr(image):
        ocr_calls.append(1)
        return original_ocr(image)
    def source_score(case,*args,**kwargs):
        rec=original_score(case,*args,**kwargs)
        rec.update(fingerprints.get(case['id'],{}))
        return rec
    with tempfile.TemporaryDirectory() as tmp:
        module_path = Path(tmp) / 'old_native_quantity.py'
        module_path.write_bytes(source)
        spec = importlib.util.spec_from_file_location('mdia._baseline_native_quantity', module_path)
        old = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(old)
        crop_path = Path(tmp) / 'old_quantity_reocr.py'
        crop_path.write_bytes(crop_source)
        crop_spec = importlib.util.spec_from_file_location('mdia._baseline_quantity_reocr', crop_path)
        old_crop = importlib.util.module_from_spec(crop_spec)
        crop_spec.loader.exec_module(old_crop)
        extract_path=Path(tmp)/'old_extract.py'
        extract_path.write_bytes(extract_source)
        extract_spec=importlib.util.spec_from_file_location('mdia._baseline_extract',extract_path)
        old_extract=importlib.util.module_from_spec(extract_spec)
        extract_spec.loader.exec_module(old_extract)
        tables_path=Path(tmp)/'old_tables.py'
        tables_path.write_bytes(tables_source)
        tables_spec=importlib.util.spec_from_file_location('mdia._baseline_tables',tables_path)
        old_tables=importlib.util.module_from_spec(tables_spec)
        # dataclasses resolves the defining module through sys.modules.
        import sys
        sys.modules[tables_spec.name]=old_tables
        tables_spec.loader.exec_module(old_tables)
        for name in ('find_tables','header_columns','unheaded_arabic_invoice_rows'):
            setattr(old_extract,name,getattr(old_tables,name))

        def compare_process(store, jid, **kwargs):
            with patch.object(native_quantity, 'recover_native_quantities', old.recover_native_quantities), \
                    patch.object(quantity_reocr, 'recover_quantities', old_crop.recover_quantities), \
                    patch.object(missing_quantity_reocr, 'recover_missing_quantities', lambda doc,*args: doc), \
                    patch.object(pipeline, 'extract_document', old_extract.extract_document):
                baseline = original_process(store, jid, **kwargs)
            flags = [json.loads(p.read_text('utf-8'))['flags']
                     for p in store.path(jid, 'pages').glob('*.json')]
            if os.environ.get('MDIA_OCR_IMAGE_ENHANCE', '0') == '1':
                if not flags or any(f.get('ocr_image_enhanced') is not True for f in flags):
                    raise RuntimeError('image enhancement requested but not applied to every OCR page')
            case = cases[store.status(jid)['filename']]
            page_files=sorted(store.path(jid,'pages').glob('*.json'))
            cache_hash=hashlib.sha256(b''.join(p.read_bytes() for p in page_files)).hexdigest()
            fingerprints[case['id']]={'source_pdf_sha256':store.status(jid)['sha256'],
                                      'ocr_cache_sha256':cache_hash}
            record = benchmark.score_record(case, baseline, 'paddle_arabic', flags)
            if baseline is None or record['page_failures']:
                raise RuntimeError('baseline failed: ' + case['id'])
            baseline_records.append(record)
            # Cache option signature remains unchanged: no new OCR invocation.
            calls_before=len(ocr_calls)
            candidate_result = original_process(store, jid, **kwargs)
            if len(ocr_calls)!=calls_before:
                raise RuntimeError('candidate unexpectedly reran OCR: '+case['id'])
            if hashlib.sha256(b''.join(p.read_bytes() for p in page_files)).hexdigest()!=cache_hash:
                raise RuntimeError('original OCR cache changed: '+case['id'])
            candidate_record = benchmark.score_record(case, candidate_result, 'paddle_arabic', flags)
            checkpoint = output / 'case_proofs' / (case['id'] + '.json')
            checkpoint.parent.mkdir(parents=True, exist_ok=True)
            checkpoint.write_text(json.dumps({'baseline': record, 'candidate': candidate_record}, ensure_ascii=False, indent=2), 'utf-8')
            return candidate_result

        with patch.object(benchmark, 'process_job', compare_process), \
                patch.object(benchmark, 'score_record', source_score), \
                patch.object(paddle_arabic, 'ocr_image', tracked_ocr):
            candidate = benchmark.run(output / 'candidate', shard=shard, shards=shards, engines=('paddle_arabic',))
    baseline_report = {k: candidate[k] for k in ('status', 'seed', 'version', 'cases', 'shard', 'shards', 'engines')}
    baseline_report.update(results=baseline_records, failure_records=[], baseline_commit=BASELINE)
    path = output / 'baseline' / 'results.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(baseline_report, ensure_ascii=False, indent=2), 'utf-8')


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--shard', type=int, default=0)
    p.add_argument('--shards', type=int, default=6)
    args = p.parse_args()
    run(args.output, args.shard, args.shards)
