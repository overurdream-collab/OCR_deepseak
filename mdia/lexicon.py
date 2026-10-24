"""Bilingual (Arabic/English) vocabularies.

LABELS  -> key/value labels ("Invoice No: 123"), id -> phrases
COLUMNS -> table column headers, id -> phrases
Phrases are matched on canonical keys (see textutil.match_key); Arabic phrases are matched
right-to-left against visually ordered words, so they work for any page direction.
"""
from .textutil import match_key, has_ar

LABELS = {
    # --- patient / provider
    "patient.name": ["patient name", "name of patient", "customer", "name", "patient", "اسم المريض", "المريض", "اسم المراجع", "اسم الحالة"],
    "patient.file_no": ["file no", "file number", "mrn", "patient id", "medical record no", "medical record number",
                        "patient file no", "رقم الملف", "رقم ملف المريض", "رقم المريض", "رقم السجل الطبي", "رقم الملف الطبي"],
    "patient.insurance_no": ["insurance no", "insurance number", "policy no", "policy number", "member id", "member no",
                             "card no", "رقم التأمين", "رقم البوليصة", "رقم الوثيقة", "رقم العضوية", "رقم البطاقة التأمينية"],
    "patient.age": ["age", "العمر"],
    "patient.sex": ["gender", "sex", "الجنس"],
    "patient.dob": ["dob", "date of birth", "birth date", "تاريخ الميلاد"],
    "provider.facility": ["hospital name", "clinic name", "facility", "facility name", "provider name", "provider",
                          "hospital", "clinic", "اسم المستشفى", "اسم العيادة", "اسم المنشأة", "المنشأة", "المستشفى", "العيادة"],
    "provider.doctor": ["doctor name", "physician", "attending physician", "treating doctor", "consultant", "doctor",
                        "dr", "اسم الطبيب", "الطبيب المعالج", "الطبيب", "الدكتور", "الدكتوره", "د"],
    "provider.department": ["department", "dept", "specialty", "القسم", "التخصص"],
    # --- invoice header
    "invoice.number": ["invoice no", "invoice number", "invoice #", "inv no", "inv number", "bill no", "bill number",
                       "receipt no", "رقم الفاتورة", "فاتورة رقم", "رقم الايصال", "رقم السند"],
    "invoice.date": ["invoice date", "bill date", "date", "تاريخ الفاتورة", "التاريخ"],
    "invoice.service_date": ["service date", "date of service", "تاريخ الخدمة", "تاريخ تقديم الخدمة"],
    "invoice.currency": ["currency", "العملة"],
    # --- totals
    "fin.subtotal": ["subtotal", "sub total", "sub-total", "total before discount", "gross total", "gross amount",
                     "المجموع قبل الخصم", "الاجمالي قبل الخصم", "المجموع الفرعي", "اجمالي قبل الخصم"],
    "fin.discount": ["total discount", "discount", "discounts", "اجمالي الخصم", "الخصومات", "الخصم"],
    "fin.tax": ["vat", "tax", "total tax", "value added tax", "الضريبه", "ضريبه القيمه المضافه", "الضريبه المضافه"],
    "fin.fees": ["service charge", "additional fees", "other fees", "extra charges", "رسوم اضافيه", "رسوم الخدمه"],
    "fin.total": ["grand total", "total amount", "net total", "net amount", "invoice total", "total due", "total",
                  "اجمالي الفاتوره", "المجموع الكلي", "الاجمالي النهائي", "الصافي", "صافي المبلغ", "الاجمالي", "المجموع"],
    "fin.paid": ["total paid", "amount paid", "paid amount", "paid", "المبلغ المدفوع", "اجمالي المدفوع", "المدفوع"],
    "fin.balance": ["balance due", "amount due", "remaining", "balance", "outstanding", "المبلغ المتبقي", "المتبقي", "الرصيد"],
    "fin.patient_share": ["patient share", "patient responsibility", "co-pay", "copay", "حصه المريض", "نسبه المريض"],
    "fin.claimed": ["claimed amount", "claim amount", "total claimed", "المبلغ المطالب به", "المطالب به", "المطالبه"],
    # --- diagnoses & clinical
    "dx.principal": ["principal diagnosis", "primary diagnosis", "main diagnosis", "التشخيص الرئيسي", "التشخيص الاساسي"],
    "dx.secondary": ["secondary diagnosis", "secondary diagnoses", "other diagnosis", "التشخيص الثانوي", "تشخيصات ثانويه"],
    "dx.provisional": ["provisional diagnosis", "suspected diagnosis", "working diagnosis", "differential diagnosis",
                       "التشخيص المبدئي", "التشخيص المشتبه", "تشخيص مبدئي", "تشخيص مشتبه"],
    "dx.final": ["final diagnosis", "discharge diagnosis", "التشخيص النهائي"],
    "dx.generic": ["diagnosis", "diagnoses", "dx", "التشخيص", "التشخيصات"],
    "clin.symptoms": ["chief complaint", "presenting complaint", "symptoms", "complaint", "الشكوى", "الاعراض", "الشكوي الرئيسيه"],
    "clin.chronic": ["chronic diseases", "chronic conditions", "past medical history", "medical history", "pmh",
                     "الامراض المزمنه", "التاريخ المرضي", "السوابق المرضيه"],
    # --- imaging
    "img.exam": ["examination", "exam type", "exam", "study", "modality", "نوع الفحص", "الفحص", "نوع الاشعه"],
    "img.region": ["body part", "region", "area examined", "المنطقه المفحوصه", "المنطقه"],
    "img.findings": ["findings", "impression", "conclusion", "radiology report", "report", "النتائج", "الانطباع", "الخلاصه", "نتيجه الاشعه"],
    "img.date": ["exam date", "study date", "تاريخ الفحص", "تاريخ الاشعه"],
    # --- procedures
    "proc.name": ["operative procedure", "procedure name", "operation name", "operation", "procedure", "surgery",
                  "اسم العمليه", "العمليه الجراحيه", "العمليه", "الاجراء الطبي", "الاجراء"],
    "proc.surgeon": ["surgeon", "operating surgeon", "الجراح", "اسم الجراح"],
    "proc.date": ["date of operation", "operation date", "procedure date", "date of surgery", "تاريخ العمليه", "تاريخ الاجراء"],
    "proc.code": ["procedure code", "cpt", "cpt code", "رمز الاجراء", "كود الاجراء"],
    "proc.surgeon_fee": ["surgeon fee", "surgeon fees", "رسوم الجراح", "اتعاب الجراح"],
    "proc.anesthesia_fee": ["anesthesia fee", "anesthesia fees", "anaesthesia fee", "رسوم التخدير", "اتعاب التخدير"],
    "proc.or_fee": ["operating room fee", "theatre fee", "or fee", "رسوم غرفه العمليات", "رسوم العمليات"],
    "proc.supplies": ["medical supplies", "implants", "consumables", "المستلزمات الطبيه", "المستلزمات"],
    "proc.total": ["total procedure cost", "procedure total", "التكلفه الاجماليه للعمليه", "تكلفه العمليه"],
    # --- hospitalization
    "stay.admit": ["admission date", "date of admission", "admitted on", "تاريخ الدخول", "تاريخ التنويم", "تاريخ الدخول للمستشفى"],
    "stay.discharge": ["discharge date", "date of discharge", "discharged on", "تاريخ الخروج", "تاريخ الخروج من المستشفى"],
    "stay.days": ["length of stay", "number of days", "no of days", "los", "عدد الايام", "مده الاقامه", "عدد ايام الاقامه"],
    "stay.room": ["room type", "ward", "room", "نوع الغرفه", "الجناح", "الغرفه"],
    "stay.cost": ["accommodation cost", "room charges", "room cost", "تكلفه الاقامه", "رسوم الغرفه", "رسوم الاقامه"],
    # --- misc
    "doc.page_of": ["page", "صفحه"],
}

COLUMNS = {
    "no": ["#", "no", "sl", "sr no", "s.no", "م", "الرقم", "رقم", "ت"],
    "code": ["code", "item code", "service code", "cpt", "icd", "icd-10", "رمز", "الرمز", "كود", "الكود"],
    "name": ["description", "service name", "service", "item name", "item", "procedure", "medication", "medicine",
             "drug name", "brand name", "trade name", "drug", "test name", "test", "investigation", "analysis", "parameter", "name",
             "الخدمه", "اسم الخدمه", "البيان", "الوصف", "الصنف", "اسم الصنف", "الدواء", "اسم الدواء", "التحليل",
             "اسم التحليل", "الفحص", "الاسم", "الاجراء", "البند", "الاسم التجاري"],
    "generic": ["generic name", "generic", "scientific name", "الاسم العلمي"],
    "packs": ["packs", "pack", "no of packs", "عدد العبوات", "العبوات"],
    "type": ["type", "category", "النوع", "الفئه", "نوع الخدمه"],
    "date": ["date", "التاريخ"],
    "qty": ["qty", "quantity", "الكميه", "العدد", "كميه"],
    "dispensed": ["qty dispensed", "dispensed", "الكميه المصروفه", "المصروف"],
    "prescribed": ["qty prescribed", "prescribed", "الكميه الموصوفه", "الموصوف"],
    "unit": ["unit", "uom", "الوحده"],
    "unit_price": ["unit price", "price", "rate", "سعر الوحده", "السعر", "سعر"],
    "discount": ["discount", "disc", "الخصم"],
    "total": ["line total", "total", "amount", "net", "الاجمالي", "المبلغ", "القيمه", "المجموع", "الصافي"],
    "claimed": ["claimed", "claim", "المطالب", "المبلغ المطالب"],
    "paid": ["paid", "المدفوع"],
    "patient_share": ["patient share", "co-pay", "copay", "حصه المريض"],
    # medication specific
    "strength": ["strength", "concentration", "التركيز"],
    "form": ["form", "dosage form", "الشكل", "الشكل الدوائي"],
    "dose": ["dose", "dosage", "الجرعه"],
    "route": ["route", "طريقه الاعطاء", "طريقه الاستخدام", "الطريقه"],
    "frequency": ["frequency", "freq", "التكرار", "عدد المرات"],
    "duration": ["duration", "المده", "مده العلاج"],
    # lab specific
    "result": ["result", "value", "النتيجه", "القيمه المقاسه"],
    "ref_range": ["reference range", "ref range", "normal range", "reference", "range", "المجال المرجعي",
                  "المعدل الطبيعي", "القيم الطبيعيه", "المعدل", "المرجع"],
    "flag": ["flag", "h/l", "status", "الحاله"],
}


def _tok(phrase: str):
    return tuple(t for t in (match_key(w) for w in phrase.split()) if t)


def compile_table(vocab: dict):
    """-> list[(tokens, id, is_rtl)] sorted so longer phrases win."""
    seen, rows = set(), []
    for _id, phrases in vocab.items():
        for p in phrases:
            toks = _tok(p)
            if not toks or (toks, _id) in seen:
                continue
            seen.add((toks, _id))
            rows.append((toks, _id, has_ar(p)))
    rows.sort(key=lambda r: -len(r[0]))
    return rows


LABEL_TABLE = compile_table(LABELS)
COLUMN_TABLE = compile_table(COLUMNS)

SECTION_WORDS = {match_key(w) for w in (
    "pharmacy laboratory lab radiology room surgery consultation medications medicines services procedures "
    "physiotherapy emergency icu ward صيدليه مختبر اشعه غرفه عمليات استشاره ادويه خدمات علاج").split()}

TOTAL_IDS = {"fin.subtotal", "fin.discount", "fin.tax", "fin.fees", "fin.total", "fin.paid", "fin.balance",
             "fin.patient_share", "fin.claimed"}

# words that must never be treated as medical entity names
INJECTION_PATTERNS = [
    r"ignore (all |any )?(previous|prior|above) (instructions|prompts?)", r"disregard (the )?(previous|above|system)",
    r"system prompt", r"you are (now )?(an? )?(ai|assistant|chatbot|model)", r"as an ai", r"do not (report|flag|mention)",
    r"set (the )?total to", r"override", r"تجاهل (كل |جميع )?(التعليمات|الاوامر)", r"تعليمات النظام", r"لا تبلغ", r"غير (قيمه )?الاجمالي",
]
