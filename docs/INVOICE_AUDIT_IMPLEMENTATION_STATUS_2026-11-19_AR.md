# تقرير التنفيذ والتسليم — Invoice Audit Engine

**التاريخ:** 2026-11-19  
**المستودع:** `overurdream-collab/OCR_deepseak`  
**المرجع الرسمي على main:** [وثيقة الرؤية ومعايير القبول](INVOICE_AUDIT_VISION_PLAN_ACCEPTANCE_AR.md) — دُمجت بواسطة [PR #35](https://github.com/overurdream-collab/OCR_deepseak/pull/35)، commit `05568a7`.  
**فرع التنفيذ:** `feat/invoice-audit-core-2026-11-19` — [PR #36](https://github.com/overurdream-collab/OCR_deepseak/pull/36) (Draft، غير مدمج)  
**الحكم:** النموذج الأولي قابل للتشغيل محلياً ضمن النطاق الضيق المحدد، لكنه **غير جاهز للقبول المالي أو الإنتاج التجاري**. لا يجوز تحويل أي نتيجة منه إلى دفع مالي.

## ما نُفذ فعلياً
| المكون | الملف | الوظيفة |
|---|---|---|
| محرك محاسبي حتمي | `invoice_audit/core.py` | PO/GRN/Invoice، Decimal، فروق كمية/سعر/إجماليات، مراجع المستندات، وثلاث حالات قرار |
| مصدر JSON الأصلي | `invoice_audit/source.py` | قراءة bytes، SHA-256، JSON Pointer، منع الحقول الغريبة والصيغ الرقمية غير المصرح بها |
| مصدر Excel الصارم | `invoice_audit/xlsx_adapter.py` | قراءة قوالب XLSX الأصلية دون OCR، ربط البيانات بالخلية والبصمة، رفض الصيغ والخانات غير المتوقعة |
| جسر MDIA | `invoice_audit/mdia_bridge.py` | مطابقة SHA الأصلي وتقاطع الصفحة والنص، وإخراج عناصر للمراجعة فقط، دون ترقية OCR مالياً |
| التصديق المصدرّي المشروط | `invoice_audit/attestation.py` | HMAC مستقل لكل دور ومصدر؛ لا يعتبر توقيعاً رسمياً أو إثبات استلام فعلي |
| منع إعادة فحص الفاتورة بنفس المعرّف | `invoice_audit/registry.py` | SQLite محلي، uniqueness بحسب المستأجر/المورد/رقم الفاتورة، وسجل أحداث بسلسلة hash |
| تقرير مراجعة محلي | `invoice_audit/report.py` | HTML عربي RTL ثابت، يحمي من إدخال HTML/JavaScript ويلصق تحذير عدم اعتماد الدفع |
| أداة تشغيل | `invoice_audit/cli.py` | تدقيق JSON وتصدير HTML؛ أو مراجعة مخرجات MDIA |
| مثال مستقل | `examples/invoice_audit/*.json` | PO/GRN/Invoice اصطناعية بكميات وأسعار متعارضة |
| الاختبارات | `tests/test_invoice_audit*.py` | حالات حسابية ورفض غموض وأدلة وتواقيع وتلاعب وتكرار وExcel والتقرير |
| CI | `.github/workflows/invoice-audit.yml` | اختبارات النواة + 30 مجموعة اصطناعية + مثال CLI/HTML |

## الأدلة على التحقق
1. [Run 44420514752 — Invoice Audit prototype checks](https://github.com/overurdream-collab/OCR_deepseak/actions/runs/44420514752): **SUCCESS**، **77/77 اختباراً ناجحاً**، منها اختبار مجموعة **30 عملية / 90 مستنداً اصطناعياً**: 10 حالات MATCH، 17 EXCEPTION، 3 UNVERIFIABLE. توجد 30 subcases داخل اختبار واحد ولا ينبغي تسميتها «30 اختبار وحدة منفصل».
2. [Run 44420514697 — MDIA Cloud2+3 synthetic regressions](https://github.com/overurdream-collab/OCR_deepseak/actions/runs/44420514697): **SUCCESS**. لا يقيس هذا التشغيل بوابة 300 فاتورة الطبية الفاشلة تاريخياً.
3. تشغيل `python -m invoice_audit.cli structured --po examples/invoice_audit/po.json --grn examples/invoice_audit/grn.json --invoice examples/invoice_audit/invoice.json --html-out audit-example.html` ضمن CI نجح، وأعاد اختلاف سعر وكمية و`approval=false`.
4. كانت هناك تجربة CI فاشلة بسبب escaping في regex للأعداد العشرية، وتم إصلاحها دون إسقاط الاختبار؛ انظر نتائج التشغيل اللاحق أعلاه.

## لماذا لا يزال ممنوعاً إطلاقه؟
- **المستندات الحقيقية غير متوفرة للتقييم:** لا توجد 90 أو 300 وثيقة موردين حقيقية بمراجع بشرية مستقلة. الاختبارات الحالية اصطناعية.
- **OCR لا يثبت الأرقام:** جسر MDIA لا يصدر MATCH أبداً؛ يحيل الحقول للمراجعة حتى عندما يسميها MDIA `auto_verified`.
- **الإصدار/الاستلام غير مثبتين ميدانياً:** HMAC يفترض توزيع مفاتيح آمن على أدوار فعلية؛ لا يتحقق من صدق المورد أو حدوث الاستلام أو التفويض من تلقاء نفسه. لم يُبن نظام توزيع مفاتيح مؤسسي أو PKI.
- **المطابقة الحالية ضيقة:** أمر واحد/إشعار استلام كامل واحد/فاتورة واحدة بلا ضرائب أو شحن أو خصومات. لا توجد فواتير جزئية أو مرتجعات أو أرصدة سابقة أو فواتير متعددة أو دمج عملات. **كل هذه السيناريوهات تُرفض بدلاً من التعامل معها بالتخمين**.
- **سجل SQLite ليس دفتراً مالياً:** لا توجد إدارة وصول محمية ولا نسخ احتياطي واستعادة موثقان ولا توثيق لصلاحيات الموظفين؛ يمكن لمدير النظام المتحكم بالقرص العبث به ويحتاج إلى anchoring خارجي.
- **لا توجد واجهة مستخدم إنتاجية ولا API مؤمنة ولا تكامل ERP أو مدفوعات**؛ HTML تقرير قراءة فقط.
- **لا يُسمح بدمج PR #32** أو إعلان MDIA صالحاً لقرار طبي/مالي بناءً على هذه الاختبارات.

## التسليم الفعلي ومسار التشغيل
```bash
python -m unittest tests.test_invoice_audit tests.test_invoice_audit_source tests.test_invoice_audit_mdia_bridge tests.test_invoice_audit_attestation tests.test_invoice_audit_xlsx tests.test_invoice_audit_report tests.test_invoice_audit_registry tests.test_invoice_audit_acceptance -v

python -m invoice_audit.cli structured \
 --po examples/invoice_audit/po.json \
 --grn examples/invoice_audit/grn.json \
 --invoice examples/invoice_audit/invoice.json \
 --html-out invoice-audit-report.html

python -m invoice_audit.cli mdia-review \
 --pdf original.pdf --result mdia-result.json --html-out review.html
```
النسخة المحلية تتطلب Python 3.11+ و`openpyxl` لمسار Excel فقط. تُشغل بقية المكونات الأساسية بمكتبات Python القياسية.

## شروط قبول المنتج النهائي التي لم تُحقق
1. مصدر أصلي قابل للتحقق لكل حقل مالي، مع تحقق مستقل من النص/الخلية ومصدره وتفويض الموقع.
2. صفر أخطاء مالية صامتة على عينات حقيقية مستقلة متعددة الموردين والتنسيقات؛ الهدف الاختباري لا ضمانٌ مطلق.
3. معالجة أو رفض موثوق لكل نوع فاتورة مع تعريف دقيق لنطاق النتيجة.
4. دعم العمليات التجارية المتفق عليها: تسويات، مرتجعات، خصومات، ضرائب، تعدد الاستلامات/الفواتير، وحدات القياس المختلفة، وصلاحيات المؤسسة.
5. اختبار القبول الميداني بمستندات حقيقية مصرح بها، مراجعين اثنين، وتقارير دقيقة بأرقام صحيحة/خاطئة/ناقصة وfalse-match ونسبة المراجعة والكلفة.
6. أمن إنتاجي واختبار اختراق وعزل مستأجرين، ونسخ احتياطي واستعادة، ومراجعة ترخيص وعقود، وموافقة إطلاق صريحة.

## الخلاصة
**أنجزنا محركاً تجريبياً قابلاً لإعادة الإنتاج واختباراته، ولم نُنجز منتج تدقيق مالي إنتاجياً بالكامل.** الامتناع عن إعلان الجاهزية حتى تزول الشروط المفتوحة التزام أساسي بوعد الموثوقية، لا نقصٌ في توثيق العمل. المطلوب تالياً إكمال منظومة مصدر موثوق حقيقية وحالات المحاسبة المركبة وتجربة ميدانية؛ لا يجوز تصنيف `VERIFIED_MATCH` بأنه «فاتورة صحيحة تجارياً» دون هذه الضوابط.
