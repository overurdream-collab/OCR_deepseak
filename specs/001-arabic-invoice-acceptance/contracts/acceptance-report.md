# Contract: Synthetic 300-Invoice Acceptance

## Invocation

```bash
python -m scripts.check_invoice300_acceptance path/to/shard0/results.json path/to/shard1/results.json path/to/shard2/results.json path/to/shard3/results.json path/to/shard4/results.json path/to/shard5/results.json
```

The six positional paths may be in any order. This command does not run OCR or load original PDFs.

## Output

- Stdout: one formatted JSON object with `status`, `dataset`, `totals`, `by_layout`, and `reasons`.
- Exit code `0`: `status=PASS`, all completeness and per-layout thresholds pass.
- Exit code `1`: `status=BLOCKED`, invalid/missing data, failures, or regression.
- A passing report explicitly states `synthetic_only=true` and `production_ready=false`.
- No patient names, individual OCR text, or medical documents may appear in the report.

## Invariants

- Exactly six shards with 50 reports each and exactly 300 expected case IDs.
- Only `paddle_arabic` counts; must have executed the actual model.
- Correct counts MUST be checked against each case's field-check details and shard summary.
- For each layout: `matched >= baseline.matched`, `expected == baseline.expected`, and `extra_item_rows <= baseline.extra_item_rows`.
- For every case, no field which was correct in frozen run `40180808910` may become incorrect, and no additional unmatched extracted row may appear. Gains in different fields never cancel this requirement.
- `scripts/baselines/invoice300_paddle_v1.json` is a frozen synthetic correctness mask, not a source document or a replacement for independent real-world evidence. Baseline updates require separate owner approval.
- Missing or inconsistent information MUST NOT produce PASS.

## Example result fragment (illustrative, not a measured new run)

```json
{
  "status": "BLOCKED",
  "synthetic_only": true,
  "production_ready": false,
  "reasons": ["ar_mixed: matched 668 < baseline 669"]
}
```
