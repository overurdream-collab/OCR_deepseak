# MDIA — تقييم شرط حماية خلايا الفاتورة

التاريخ: 2026-10-28

القرار: **REJECTED FOR ADOPTION — لا دمج في main**. هدف دقة 100% لم يتحقق.

## الأدلة

- مرجع المقارنة: https://github.com/overurdream-collab/OCR_deepseak/actions/runs/40229802617
- تشغيل التجربة: https://github.com/overurdream-collab/OCR_deepseak/actions/runs/40680625226
- Commit تقييم التجربة: `3a6f0def8e66fc45deceffc9628ac4f7eee7f12c`.
- مجموعة القياس: SYNTHETIC-INVOICE-300-HOLDOUT-v1، seed 20261026، 300 فاتورة اصطناعية، 5776 حقلًا، ستة تخطيطات.
- اكتملت المجموعات الست دون أخطاء تشغيل. نجاح workflow يثبت اكتمال التشغيل، وليس صحة كل قيمة.

| المقياس | المرجع | شرط الحماية بعد إصلاح العملة |
|---|---:|---:|
| الحقول الصحيحة | 4895 | 4612 |
| دقة الحقول | 84.75% | 79.85% |
| الصفوف الزائدة غير المطابقة | 99 | 76 |
| أخطاء التشغيل | 0 | 0 |

تراجع صافٍ قدره 283 حقلًا صحيحًا (نحو 4.90 نقطة مئوية)، مقابل خفض 23 صفًا زائدًا. لذلك لا يصح اعتماد التجربة كتحسين للدقة. المقارنة مقابل التشغيل المرجعي المسجل، وليست إعادة تشغيل مضبوطة لكل إصدارات التبعيات على main.

## ما تم إصلاحه وما لم يتحقق

أُصلح استبعاد الصفوف الصحيحة التي تحتوي رمز عملة مستقلًا مثل SAR بجوار المبلغ. نجح اختبار الترويسة المزدوجة الذي فشل في PR #13. لكن شرط استبعاد الصف كاملًا عند تعدد كلمات الخلية ما زال يفقد بيانات صحيحة.

أضيفت أداة `scripts/summarize_invoice300.py` لتجميع تقارير النتائج الفعلية، والتحقق من جميع معرفات الفواتير والحقول، ورفض التقارير الناقصة أو المكررة. خيار `--require-perfect` يفشل إن بقي أي حقل غير صحيح أو بلا دليل أو أي صف زائد أو فشل تشغيل. هذا معيار للمجموعة الاصطناعية، وليس شهادة إنتاج أو إثباتًا لاستقلال مواقع الكلمات المقدرة.

الفحص المحلي بعد استكمال pytesseract وبيانات العربية وخط Amiri: 119 اختبارًا، ناجح مع تجاوز اختبار واحد لأن مكتبات تشكيل العربية مثبتة. فحص GitHub على Commit إضافة أداة التجميع نجح: https://github.com/overurdream-collab/OCR_deepseak/actions/runs/40681022283

## الخطوة الهندسية التالية

استبدال حذف الصف الغامض بالحفاظ على الخدمة ودليلها، وإظهار الخلية الغامضة للمراجعة، دون اختراع قيمة أو تعديل مبلغ أو إعادة توزيع أرقام بلا دليل مستقل. تُقارن التجربة الجديدة بالمرجع على الحقول الصحيحة والصفوف المفقودة والزائدة معًا قبل أي دمج. أكبر مشكلات القراءة المتبقية تشمل التخطيط العربي والأرقام والكميات؛ لا يكفي نجاح اختبارات الوحدة.

## الملخص المرجعي المجمّع من artifacts

```json
{
  "documents": 300,
  "correct": 4895,
  "expected": 5776,
  "field_accuracy": 0.847472299168975,
  "with_evidence": 4895,
  "extra_item_rows": 99,
  "failures": 0,
  "accepted_100_percent": false,
  "errors_by_field": {
    "invoice.number": 26,
    "invoice.total": 69,
    "item.qty": 241,
    "item.name": 105,
    "item.price": 215,
    "item.total": 180,
    "patient.name": 45
  },
  "by_layout": {
    "en_standard": {
      "documents": 50,
      "correct": 910,
      "expected": 942
    },
    "en_reordered": {
      "documents": 50,
      "correct": 927,
      "expected": 970
    },
    "en_compact": {
      "documents": 50,
      "correct": 921,
      "expected": 958
    },
    "ar_shaped": {
      "documents": 50,
      "correct": 758,
      "expected": 1018
    },
    "ar_visual": {
      "documents": 50,
      "correct": 710,
      "expected": 930
    },
    "ar_mixed": {
      "documents": 50,
      "correct": 669,
      "expected": 958
    }
  }
}
```

## ملخص التجربة المجمّع من artifacts

```json
{
  "documents": 300,
  "correct": 4612,
  "expected": 5776,
  "field_accuracy": 0.7984764542936288,
  "with_evidence": 4612,
  "extra_item_rows": 76,
  "failures": 0,
  "accepted_100_percent": false,
  "errors_by_field": {
    "item.name": 220,
    "item.qty": 231,
    "item.price": 301,
    "item.total": 272,
    "invoice.number": 26,
    "invoice.total": 69,
    "patient.name": 45
  },
  "by_layout": {
    "en_standard": {
      "documents": 50,
      "correct": 877,
      "expected": 942
    },
    "en_reordered": {
      "documents": 50,
      "correct": 882,
      "expected": 970
    },
    "en_compact": {
      "documents": 50,
      "correct": 885,
      "expected": 958
    },
    "ar_shaped": {
      "documents": 50,
      "correct": 702,
      "expected": 1018
    },
    "ar_visual": {
      "documents": 50,
      "correct": 658,
      "expected": 930
    },
    "ar_mixed": {
      "documents": 50,
      "correct": 608,
      "expected": 958
    }
  }
}
```
