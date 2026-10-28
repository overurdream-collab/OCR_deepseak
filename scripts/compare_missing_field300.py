"""Compare 300 actual OCR outputs against accepted PR #22 field-by-field."""
import argparse
import json
from pathlib import Path


def collect(paths):
    result = {}
    for path in paths:
        report = json.loads(Path(path).read_text("utf-8"))
        if report.get("status") != "completed_real_ocr":
            raise ValueError("missing or incomplete real OCR shard")
        for item in report.get("results", []):
            name = item["case"]
            if name in result:
                raise ValueError("duplicate case " + name)
            if not item.get("real_paddle_detected") or item.get("page_failures"):
                raise ValueError("not a clean real PaddleOCR run " + name)
            result[name] = item
    if len(result) != 300:
        raise ValueError("expected exactly 300 synthetic cases")
    return result


def compare(before_files, after_files):
    before, after = collect(before_files), collect(after_files)
    if before.keys() != after.keys():
        raise ValueError("changed test case IDs")
    gains, losses, new_rows, changes = [], [], [], []
    for case_id in sorted(before):
        b, a = before[case_id], after[case_id]
        bchecks = {x["field"]: x for x in b["checks"]}
        achecks = {x["field"]: x for x in a["checks"]}
        if bchecks.keys() != achecks.keys():
            raise ValueError("changed field identity " + case_id)
        if a["extra_item_rows"] > b["extra_item_rows"]:
            new_rows.append(case_id)
        for field, old in bchecks.items():
            new = achecks[field]
            if old["expected"] != new["expected"]:
                raise ValueError("synthetic truth changed")
            if old["matched"] and not new["matched"]:
                losses.append([case_id, field])
            if new["matched"] and not old["matched"]:
                gains.append([case_id, field])
            if new["matched"] and not new["linked_evidence"]:
                raise ValueError("missing linked evidence: " + case_id + " " + field)
        if a["matched"] != b["matched"]:
            changes.append({"case": case_id, "old": b["matched"], "new": a["matched"]})
    base = sum(x["matched"] for x in before.values())
    candidate = sum(x["matched"] for x in after.values())
    total = sum(x["total"] for x in after.values())
    if base != 5382 or total != 5776:
        raise ValueError("must compare to frozen PR22 5382/5776 baseline")
    return {"status": "PASS" if not losses and not new_rows and candidate >= base else "BLOCKED",
            "baseline": base, "candidate": candidate, "total": total,
            "gained": gains, "lost": losses, "new_extra_rows": new_rows,
            "changed_cases": changes}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--previous", nargs=6, required=True)
    p.add_argument("--current", nargs=6, required=True)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    report = compare(args.previous, args.current)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                           encoding="utf-8")
    print(json.dumps({k: len(v) if isinstance(v, list) else v for k, v in report.items()}))
    if report["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
