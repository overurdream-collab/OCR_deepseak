"""Offline read-only HTML audit report with safe escaping.

Not a payment dashboard. No network calls, scripts, or dynamic contents.
"""
from __future__ import annotations

from html import escape
from typing import Mapping


def render_html(report: Mapping) -> str:
    status = escape(str(report.get("status", "UNVERIFIABLE")))
    approval = report.get("approval", False)
    # UI should never communicate that it authorizes payment.
    if approval is not False:
        raise ValueError("unexpected payment approval")
    source_auth = escape(str(report.get("source_authenticity", "not_authenticated")))
    items = []
    for entry in report.get("findings", []):
        if not isinstance(entry, Mapping):
            continue
        items.append(
            "<tr><td>" + escape(str(entry.get("rule", ""))) + "</td><td>"
            + escape(str(entry.get("sku", ""))) + "</td><td>"
            + escape(str(entry.get("difference", ""))) + "</td><td>"
            + escape(str(entry.get("message", ""))) + "</td></tr>"
        )
    reasons = "".join("<li>" + escape(str(reason)) + "</li>"
                      for reason in report.get("reasons", []))
    rows = "".join(items) or '<tr><td colspan="4">No reported discrepancies</td></tr>'
    return f"""<!doctype html>
<html lang="ar" dir="rtl"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'">
<title>تقرير تدقيق الفواتير</title>
<style>
body{{font:16px system-ui,sans-serif;background:#f5f7fa;color:#17233b;max-width:1050px;margin:2rem auto;padding:1rem}}
header,.panel{{background:#fff;border:1px solid #dce3e9;border-radius:14px;padding:1.4rem;margin-bottom:1rem}}
h1{{margin:0 0 1rem}} .sub{{color:#56627a}} .status{{font-size:1.4rem;font-weight:700}}
table{{width:100%;border-collapse:collapse;direction:ltr;text-align:left}}th,td{{padding:.7rem;border-bottom:1px solid #dce3e9}}
.warn{{color:#a03b14;font-weight:700}} .notice{{background:#fff7ed;padding:1rem;border-radius:8px}}
</style></head><body><header><h1>تقرير مطابقة الفواتير</h1>
<div class="status">{status}</div><p class="sub">إثبات مصدر البيانات: {source_auth}</p>
<p class="warn">لا يمثل هذا التقرير اعتماد دفع أو إثبات استلام فعلي أو تصديقاً قانونياً للمصدر.</p>
</header><section class="panel"><h2>الاختلافات</h2><table><thead><tr><th>Rule</th><th>Item</th><th>Difference</th><th>Details</th></tr></thead>
<tbody>{rows}</tbody></table></section>
<section class="panel"><h2>أسباب تعذر التحقق</h2><ul>{reasons or '<li>لا توجد أسباب مسجلة</li>'}</ul>
<p class="notice">كل مبلغ يحتاج دليلاً من المصدر الأصلي، ومراجعة صلاحية المورد والاستلام والعقد قبل أي قرار مالي.</p>
</section></body></html>"""
