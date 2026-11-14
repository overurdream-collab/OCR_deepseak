"""Report every gained/lost field AND the unchanged absolute release gate."""
import argparse
import json
from pathlib import Path
from scripts.check_zero_error300 import evaluate_reports


def summarize(baselines,candidates):
    # Validate the frozen identity, counts, original OCR and all 300 cases.
    old_gate=evaluate_reports(baselines)
    gate=evaluate_reports(candidates)
    old={c['case']:c for r in baselines for c in r['results']}
    new={c['case']:c for r in candidates for c in r['results']}
    gained=[];lost=[];new_rows=[]
    for name in sorted(old):
        a,b=old[name],new[name]
        for key in ('source_pdf_sha256','ocr_cache_sha256'):
            if not isinstance(a.get(key),str) or len(a[key])!=64 or a[key]!=b.get(key):
                raise ValueError('original source/cache changed or missing: '+name)
        x={c['field']:c for c in a['checks']};y={c['field']:c for c in b['checks']}
        if x.keys()!=y.keys():raise ValueError('field identities changed: '+name)
        if b['extra_item_rows']>a['extra_item_rows']:new_rows.append(name)
        for field in x:
            if x[field]['expected']!=y[field]['expected']:raise ValueError('ground truth changed')
            if x[field]['matched'] and not y[field]['matched']:lost.append([name,field])
            if not x[field]['matched'] and y[field]['matched']:gained.append([name,field])
    regression_ok=not lost and not new_rows and gate['correct']>=old_gate['correct'] and gate['evidence_gaps']==0 and gate['failed_pages']==0
    return dict(regression_status='PASS' if regression_ok else 'BLOCKED',
                baseline=old_gate,candidate=gate,gained=gained,lost=lost,new_extra_rows=new_rows,
                release_status=gate['status'])


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--baseline',nargs='+',type=Path,required=True)
    p.add_argument('--candidate',nargs='+',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--require-perfect',action='store_true')
    args=p.parse_args()
    result=summarize([json.loads(p.read_text('utf-8')) for p in args.baseline],
                     [json.loads(p.read_text('utf-8')) for p in args.candidate])
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2),'utf-8')
    print(json.dumps({**{k:v for k,v in result.items() if k not in ('gained','lost','new_extra_rows')},
                      'gained':len(result['gained']),'lost':len(result['lost']),'new_extra_rows':len(result['new_extra_rows'])}))
    if result['regression_status']!='PASS' or (args.require_perfect and result['release_status']!='PASS'):
        raise SystemExit(1)
