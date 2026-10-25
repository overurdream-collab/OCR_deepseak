# MDIA — 300-Invoice Release Field Audit (2026-10-25)

Source: [GitHub Actions real PaddleOCR run #40180808910](https://github.com/overurdream-collab/OCR_deepseak/actions/runs/40180808910). Aggregated all six artifacts (`results.json` per shard); 300 unique synthetic PDF invoices.

## Observed metrics

- **4895/5776 exact fields = 84.75%**. This is NOT an accuracy improvement over the earlier PaddleOCR benchmark.
- **300/300** completed OCR without runtime failures; **300/300** marked for human review.
- **99 extra extracted invoice rows** not matched to the known printed item list. These must not be approved as valid charges.
- Source provenance and row geometry checks only flag discrepancies; they do not correct OCR amounts.
- PaddleOCR per-word positions derived from line boxes are **estimated**, not independent word-localization proof.

| Layout | Exact fields | Accuracy | Extra rows |
| --- | ---: | ---: | ---: |
| English standard | 910/942 | 96.60% | 3 |
| English reordered | 927/970 | 95.57% | 5 |
| English compact | 921/958 | 96.14% | 4 |
| Arabic shaped | 758/1018 | 74.46% | 30 |
| Arabic visual | 710/930 | 76.34% | 20 |
| Arabic mixed | 669/958 | 69.83% | 37 |

| Field | Exact matches |
| --- | ---: |
| Patient name | 255/300 |
| Invoice number | 274/300 |
| Invoice total | 231/300 |
| Item description | 1114/1219 |
| Item quantity | 978/1219 |
| Item unit price | 1004/1219 |
| Item line total | 1039/1219 |

## Engineering conclusion

The highest-priority defect is **Arabic table row-to-column association**: Arabic mixed has only 69.83% exact fields and 37 spurious rows; all Arabic layouts together account for 87 of 99 extra rows. Improving English OCR will not solve this.

The program can be used as a **local human-reviewed extraction tool**, not an automatic claim authorization or financial rejection engine. Next improvement must be tested on **new, independent** Arabic invoice holdouts and show reduced spurious rows without decreasing correct item/amount matches. Any field lacking source evidence must remain pending human review.

Verification of the shipped distribution: [Docker and Windows smoke run #40181347754](https://github.com/overurdream-collab/OCR_deepseak/actions/runs/40181347754).
