"""Orchestrates: integrity check -> read/OCR -> classify -> segment -> extract -> validate -> link."""
import time
import traceback

from . import config
from .classify import classify_page, segment
from .extract import extract_document
from .reader import PdfError, read_document
from .store import Store
from .textutil import match_key
from .validate import validate_document


def _link_documents(docs):
    links = []
    for i, a in enumerate(docs):
        for b in docs[i + 1:]:
            for key, basis in (("file_no", "patient_file_no"), ("insurance_no", "insurance_no")):
                fa, fb = a["patient"][key], b["patient"][key]
                if fa["raw"] and fb["raw"] and match_key(fa["raw"]) == match_key(fb["raw"]):
                    na, nb = a["patient"]["name"], b["patient"]["name"]
                    clash = na["raw"] and nb["raw"] and match_key(na["raw"]) != match_key(nb["raw"])
                    links.append({"from": a["document_id"], "to": b["document_id"],
                                  "type": "same_number_different_name" if clash else "same_patient", "basis": basis,
                                  "needs_review": bool(clash), "evidence_ids": [fa["evidence_id"], fb["evidence_id"], na["evidence_id"], nb["evidence_id"]] if clash else [fa["evidence_id"], fb["evidence_id"]]})
                    break
            else:
                na, nb = a["patient"]["name"], b["patient"]["name"]
                fa, fb = a["patient"]["file_no"], b["patient"]["file_no"]
                conflict = fa["raw"] and fb["raw"] and match_key(fa["raw"]) != match_key(fb["raw"])
                if na["raw"] and nb["raw"] and match_key(na["raw"]) == match_key(nb["raw"]) and not conflict:
                    links.append({"from": a["document_id"], "to": b["document_id"], "type": "possible_same_patient",
                                  "basis": "patient_name_only", "evidence_ids": [na["evidence_id"], nb["evidence_id"]]})
    return links


def process_job(store: Store, job_id: str, ocr_mode="auto", lang=None):
    st = store.status(job_id)
    store.set_status(job_id, state="processing", progress=0.02, stage="reading", error=None, ocr_mode=ocr_mode)
    t0 = time.time()
    try:
        pdf = store.path(job_id, "original.pdf")
        work = store.path(job_id)

        def prog(i, n):
            store.set_status(job_id, progress=round(0.05 + 0.55 * i / n, 3), stage=f"reading page {i}/{n}")

        pages = read_document(pdf, work, ocr_mode=ocr_mode, lang=lang, progress=prog)
        store.set_status(job_id, progress=0.65, stage="classifying")
        classes = [classify_page(p) for p in pages]
        segs = segment(pages, classes)
        docs = []
        for n, seg in enumerate(segs, 1):
            doc_id = f"{job_id}-d{n}"
            store.set_status(job_id, progress=round(0.65 + 0.3 * n / len(segs), 3), stage=f"extracting document {n}/{len(segs)}")
            try:
                seg_pages = [p for p in pages if p.number in seg.pages]
                seg_classes = [c for p, c in zip(pages, classes) if p.number in seg.pages]
                d = extract_document(job_id, doc_id, seg, seg_pages, seg_classes)
                if seg.confidence < 0.35 or seg.type == "unknown":
                    d["warnings"].append({"id": f"{doc_id}-wc", "kind": "low_classification_confidence", "severity": "warning",
                                          "message": f"نوع المستند غير مؤكد ({seg.type}, {seg.confidence}) / document type uncertain"})
                validate_document(d)
            except Exception as e:  # one failing document must not lose the others
                d = {"document_id": doc_id, "document_type": seg.type, "processing_status": "failed", "pages": seg.pages,
                     "patient": {}, "provider": {}, "invoices": [], "invoice_items": [], "medications": [], "diagnoses": [],
                     "laboratory_tests": [], "imaging": [], "procedures": [], "hospitalization": {}, "evidence": [],
                     "warnings": [{"id": f"{doc_id}-wf", "kind": "extraction_failed", "severity": "error", "message": f"{type(e).__name__}: {e}"}],
                     "requires_human_review": []}
            docs.append(d)
        failed_pages = [p.number for p in pages if any(w["kind"] == "page_failed" for w in p.warnings)]
        result = {
            "schema_version": config.SCHEMA_VERSION, "job_id": job_id,
            "source": {"filename": st["filename"], "sha256": st["sha256"], "pages": len(pages)},
            "processing_status": "completed_with_errors" if failed_pages or any(d["processing_status"] == "failed" for d in docs) else
                                 ("completed_with_review" if any(d["requires_human_review"] for d in docs) else "completed"),
            "documents": docs, "document_links": _link_documents(docs),
            "page_info": [{"page": p.number, "method": p.method, "image": p.image, "width": p.width, "height": p.height,
                           "ocr_mean_conf": p.flags.get("ocr_mean_conf"), "warnings": p.warnings} for p in pages],
            "summary": {"documents": len(docs), "pages": len(pages),
                        "fields_needing_review": sum(len(d["requires_human_review"]) for d in docs),
                        "warnings": sum(len(d["warnings"]) for d in docs), "seconds": round(time.time() - t0, 2)},
        }
        store.save_result(job_id, result)
        store.set_status(job_id, state="done", progress=1.0, stage="done", result_status=result["processing_status"])
        return result
    except PdfError as e:
        store.set_status(job_id, state="failed", error=str(e), stage="integrity check")
    except Exception as e:  # noqa
        store.set_status(job_id, state="failed", error=f"{type(e).__name__}: {e}", trace=traceback.format_exc()[-1500:])
    return None
