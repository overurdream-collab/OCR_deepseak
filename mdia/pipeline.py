"""Orchestrates: integrity check -> read/OCR -> classify -> segment -> extract -> validate -> link."""
import time
import traceback
import os

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


def process_job(store: Store, job_id: str, ocr_mode="auto", lang=None, zero_human=None):
    # Explicit runtime opt-in, preserving legacy workflows until validated.
    if zero_human is None:
        zero_human = os.environ.get("MDIA_ZERO_HUMAN_MODE", "0") == "1"
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
                # Re-read OCR's literal M-shaped quantity from original local
                # PDF pixels with an independent model. Arithmetic corroborates
                # only a digit that Tesseract itself visibly recognized.
                from .quantity_reocr import recover_quantities
                recover_quantities(d, pdf, seg_pages)
                # Repair only missing/extraneous word boundaries in a
                # source-observed medical service label. Preserve raw OCR,
                # evidence linkage, financial fields and all review alerts.
                from .service_spacing import repair_document_service_names
                repair_document_service_names(d)
                if seg.confidence < 0.35 or seg.type == "unknown":
                    d["warnings"].append({"id": f"{doc_id}-wc", "kind": "low_classification_confidence", "severity": "warning",
                                          "message": f"نوع المستند غير مؤكد ({seg.type}, {seg.confidence}) / document type uncertain"})
                validate_document(d)
                # PaddleOCR returns detected LINE geometry. Token rectangles are
                # interpolated rather than independently localized. Do not call
                # the document fully verified even when text checks pass.
                uncertain = [p.number for p in seg_pages if p.flags.get("ocr_engine") == "paddleocr-v5-arabic"]
                if uncertain:
                    d["warnings"].append({"id": f"{doc_id}-wp", "kind": "paddle_line_geometry_only",
                        "severity": "warning", "message": "PaddleOCR token positions estimated from detected line boxes; verify evidence on original PDF",
                        "pages": uncertain})
                    d["requires_human_review"].append({"record_id": doc_id, "field": "ocr_word_bbox",
                        "raw": None, "evidence_id": None, "page": uncertain[0], "confidence": 0.0,
                        "reasons": ["paddle_line_geometry_only"]})
                    d["processing_status"] = "completed_with_review"
            except Exception as e:  # one failing document must not lose the others
                d = {"document_id": doc_id, "document_type": seg.type, "processing_status": "failed", "pages": seg.pages,
                     "patient": {}, "provider": {}, "invoices": [], "invoice_items": [], "medications": [], "diagnoses": [],
                     "laboratory_tests": [], "imaging": [], "procedures": [], "hospitalization": {}, "evidence": [],
                     "warnings": [{"id": f"{doc_id}-wf", "kind": "extraction_failed", "severity": "error", "message": f"{type(e).__name__}: {e}"}],
                     "requires_human_review": []}
            # In machine-only mode, never route exceptions to humans. Instead
            # preserve every unresolved check in a machine ledger and block
            # the extracted document from being treated as reliable output.
            if zero_human:
                from .zero_human import apply_zero_human_policy
                apply_zero_human_policy(d)
            else:
                from .review_triage import triage_document
                d["review_triage"] = triage_document(d)
            docs.append(d)
        failed_pages = [p.number for p in pages if any(w["kind"] == "page_failed" for w in p.warnings)]
        # Linking across documents may reveal inconsistent identities. Never
        # silently clear these when human handoff is disabled.
        links = _link_documents(docs)
        if zero_human:
            for link in links:
                if link.get("needs_review"):
                    link["original_review_reason"] = "cross_document_identity_conflict"
                    link["needs_review"] = False
                    link["machine_unresolved"] = True
                    for doc in docs:
                        if doc.get("document_id") in (link.get("from"), link.get("to")):
                            from .zero_human import record_machine_issue
                            record_machine_issue(doc, "cross_document_identity",
                                                 "cross_document_identity_conflict")
        result = {
            "schema_version": config.SCHEMA_VERSION, "job_id": job_id,
            "source": {"filename": st["filename"], "sha256": st["sha256"], "pages": len(pages)},
            "processing_status": (
                "completed_with_errors" if failed_pages or any(d["processing_status"] == "failed" for d in docs) else
                "blocked_unresolved" if zero_human and any(not d["extraction_ready"] for d in docs) else
                "completed" if zero_human else
                "completed_with_review" if any(d["requires_human_review"] for d in docs) else "completed"
            ),
            "automation_policy": "zero_human_fail_closed" if zero_human else "legacy_review",
            "documents": docs, "document_links": links,
            "page_info": [{"page": p.number, "method": p.method, "image": p.image, "width": p.width, "height": p.height,
                           "ocr_mean_conf": p.flags.get("ocr_mean_conf"),
                           "cross_engine_word_matches": p.flags.get("cross_engine_word_matches", 0),
                           "word_alignment_opt_in": p.flags.get("word_alignment_opt_in", False),
                           "warnings": p.warnings} for p in pages],
            "summary": {"documents": len(docs), "pages": len(pages),
                        "fields_needing_review": sum(len(d["requires_human_review"]) for d in docs),
                        "machine_unresolved_checks": sum(len(d.get("machine_unresolved_checks", [])) for d in docs),
                        "human_handoffs": 0 if zero_human else sum(len(d["requires_human_review"]) for d in docs),
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
