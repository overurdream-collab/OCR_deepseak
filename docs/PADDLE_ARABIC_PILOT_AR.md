# تجربة PaddleOCR PP-OCRv5 العربي — مستقلّة عن الإنتاج

**فرع التجربة:** `experiment/paddleocr-arabic`؛ متفرع من `feat/mdia-cloud2-fixes` SHA `a00a78c96467c9f58cd2c404853774678ed81e1c`.

## لماذا؟
مقارنة Tesseract (ara+eng) بمحرك PaddleOCR الفعلي باستخدام النموذج العربي الرسمي `arabic_PP-OCRv5_mobile_rec` مع كاشف النصوص `PP-OCRv5_mobile_det`، على **صور الصفحات الاصطناعية نفسها**، دون بيانات مرضى حقيقية.

## طريقة الاستخدام
- الأصل لا يتغير: `MDIA_OCR_ENGINE=tesseract`.
- التجربة فقط: `MDIA_OCR_ENGINE=paddle_arabic`، ومع الملفات النصية استخدم `ocr=force` إذا أردت تجربة OCR قسريًا.
- يعتمد على `PaddleOCR 3.x` و`PaddlePaddle 3.x`، ويُحمّل النموذج عند الاستدعاء الأول فقط. **أي فشل يبلّغ صراحةً ولا يحدث انتقال صامت إلى Tesseract**.
- الذاكرة المؤقتة منفصلة لكل محرك.
- **مهم جدًا للأدلة:** هندسة PaddleOCR هنا على مستوى السطر؛ مربعات الكلمات مشتقة تقديريًا، ليست مواضع مستقلة موثقة. يضيف النظام مراجعة بشرية إلزامية لكل مستند قرأه هذا المحرك.
- لم تتغير الفواتير والحقول وقواعد التحقق في المسار الافتراضي.

## التشغيل على CPU (بيئة اختبار معزولة Python 3.12)

```bash
python -m pip install -r requirements.txt
python -m pip install 'paddlepaddle==3.2.0' 'paddleocr>=3.2,<4'
python -m unittest discover -s tests -p 'test_*.py' -v
python -m scripts.compare_arabic_ocr --output results/paddle_arabic_vs_tesseract.json
```

## معيار المقارنة
- يولد النصوص الاصطناعية من `tests.arabic_samples`، ويعرضها كنفس صور البكسل لكل محرك.
- يكتب لكل PDF قيمة SHA-256، وأسماء المحركات، والنص الخام، ووجود العبارات المتوقعة، وزمن التنفيذ.
- **قياس وجود عبارات في OCR ليس دقة استخراج فاتورة ولا ربط سعر بعبارة أو تشخيص.**
- عند تعطل Paddle يكتب `status=failed`؛ لا يختلق نتيجة أو يدّعي فوز أي محرك.
- نتائج الـmock تقيس التوافق والأمان وعزل المحرك فقط؛ **ليست استدلالًا حقيقيًا**.
- يشغّل GitHub Actions على فرع التجربة اختبارات الوحدة وتجربة النموذج الحقيقي على CPU؛ يجب مراجعة السجلات قبل تقرير أي أرقام.

## قبول الإنتاج
لا يستبدل Tesseract تلقائيًا. يتطلب اعتماد النموذج اختبارات عربية على أنماط متنوعة، وضبط إحداثيات كل كلمة، ومراجعة بشرية لكميات وأسعار وأسماء أدوية وتواريخ التشخيصات، وفحص الخصوصية والأمن.

مصادر رسمية:
- https://github.com/PaddlePaddle/PaddleOCR
- https://huggingface.co/PaddlePaddle/arabic_PP-OCRv5_mobile_rec
- https://www.paddleocr.ai/main/en/version3.x/pipeline_usage/OCR.html

لا Merge إلى main، ولا Deploy، ولا بيانات إنتاج.
