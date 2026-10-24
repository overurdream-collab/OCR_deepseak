"""Harder, more realistic layouts used to stress the extractor (all synthetic / anonymous)."""
from pathlib import Path

from tests.make_samples import Doc, W, H, to_scanned, merge, invoice_en, ITEMS_EN, TOTALS_EN  # noqa: F401


def _hdr(d, hospital, title, lines):
    d.line(hospital, size=15, bold=True, gap=22)
    d.line(title, size=12, bold=True, gap=20)
    for l in lines:
        d.line(l, gap=14)
    d.y -= 8


def hard1(path):
    """Different column order, section headers, wrapped description, % discount, dd/mm/yyyy, thousands."""
    d = Doc(path)
    _hdr(d, "Green Valley Medical Center", "Invoice", ["Invoice No: H-778      Date: 25/03/2024", "Patient Name: Layla Mansour",
                                                       "MRN: 88123", "Currency: SAR"])
    X = [40, 100, 150, 320, 365, 425, 490]
    for x, t in zip(X, ["Date", "Code", "Description", "Qty", "Price", "Disc %", "Net"]):
        d.t(x, d.y, t, bold=True)
    d.y -= 16
    def row(vals, wrap=None):
        for x, v in zip(X, vals):
            d.t(x, d.y, v)
        d.y -= 14
        if wrap:
            d.t(X[2], d.y, wrap)
            d.y -= 14
    d.t(40, d.y, "LABORATORY", bold=True); d.y -= 15
    row(["25/03/2024", "L101", "Complete Blood Count (CBC)", "1", "1,200.00", "10", "1,080.00"], wrap="with differential")
    row(["25/03/2024", "L205", "Lipid Profile", "1", "950.50", "0", "950.50"])
    d.t(40, d.y, "PHARMACY", bold=True); d.y -= 15
    row(["26/03/2024", "P330", "Amoxicillin 500mg Capsules", "2", "45.25", "0", "90.50"])
    d.y -= 6
    for lab, v in (("Subtotal", "2,241.00"), ("Discount", "120.00"), ("Total", "2,121.00")):
        d.t(380, d.y, lab); d.t(480, d.y, v); d.y -= 14
    d.save()


def hard2(path):
    """Two-line header, stacked label/value, negative in parentheses, currency inside cells."""
    d = Doc(path)
    d.line("Riyadh Care Clinic", size=15, bold=True, gap=22)
    d.line("Invoice", size=12, bold=True, gap=22)
    for lab, v in (("Invoice No", "RC-5521"), ("Patient Name", "Nora Al Qahtani"), ("Invoice Date", "2024-08-09")):
        d.t(40, d.y, lab, size=8); d.y -= 11
        d.t(40, d.y, v, size=11); d.y -= 18
    d.y -= 6
    X = [40, 300, 360, 440]
    d.t(X[0], d.y, "Description", bold=True); d.t(X[1], d.y, "Qty", bold=True); d.t(X[2], d.y, "Unit", bold=True); d.t(X[3], d.y, "Line", bold=True)
    d.y -= 11
    d.t(X[2], d.y, "Price", bold=True); d.t(X[3], d.y, "Total", bold=True)
    d.y -= 16
    for nm, q, up, tt in (("Dental Scaling", "1", "SAR 300.00", "SAR 300.00"), ("X-Ray Dental", "2", "SAR 40.00", "SAR 80.00"),
                          ("Loyalty Adjustment", "1", "(20.00)", "(20.00)")):
        d.t(X[0], d.y, nm); d.t(X[1], d.y, q); d.t(X[2], d.y, up); d.t(X[3], d.y, tt); d.y -= 15
    d.y -= 8
    d.t(380, d.y, "Total", bold=True); d.t(450, d.y, "SAR 360.00", bold=True)
    d.save()


def hard3(path):
    """Bilingual form lines 'English / عربي : value' and Latin digits."""
    d = Doc(path)
    d.line("Al Salam Hospital", size=15, bold=True, gap=22)
    d.line("Discharge Summary", size=12, bold=True, gap=22)
    d.line("Patient Name: Yusuf Ibrahim", gap=14)
    d.line("Admission Date: 03/09/2024", gap=14)
    d.line("Discharge Date: 18/09/2024", gap=14)
    d.line("Final Diagnosis: Acute appendicitis (K35.8); Dehydration", gap=14)
    d.line("Chronic Diseases: Hypertension; Asthma", gap=14)
    d.line("Symptoms:", gap=14)
    d.line("- Right lower quadrant pain", x=60, gap=14)
    d.line("- Nausea and vomiting", x=60, gap=14)
    d.save()


def hard4(path):
    """Page 2 has NO table header and carries the totals."""
    d = Doc(path)
    d.line("North Gate Hospital", size=15, bold=True, gap=22)
    d.line("Tax Invoice", size=12, bold=True, gap=20)
    d.line("Invoice No: NG-9001      Invoice Date: 2024-11-02", gap=14)
    d.line("Patient Name: Omar Rashid", gap=14)
    d.line("Currency: USD", gap=22)
    X = [40, 70, 330, 390, 480]
    for x, t in zip(X, ["#", "Description", "Qty", "Unit Price", "Total"]):
        d.t(x, d.y, t, bold=True)
    d.y -= 16
    rows = [("Room Charges", 3, 200.00, 600.00), ("Nursing Care", 3, 50.00, 150.00)]
    n = 0
    for nm, q, p, t in rows:
        n += 1
        for x, v in zip(X, [str(n), nm, str(q), f"{p:,.2f}", f"{t:,.2f}"]):
            d.t(x, d.y, v)
        d.y -= 15
    d.t(40, d.y - 10, "continued on next page", size=8)
    d.page_break()
    d.line("North Gate Hospital", size=12, bold=True, gap=16)
    d.line("Invoice No: NG-9001      Page 2 of 2", gap=22)
    for nm, q, p, t in (("Surgical Supplies", 1, 340.00, 340.00), ("Anesthesia", 1, 410.00, 410.00)):
        n += 1
        for x, v in zip(X, [str(n), nm, str(q), f"{p:,.2f}", f"{t:,.2f}"]):
            d.t(x, d.y, v)
        d.y -= 15
    d.y -= 8
    for lab, v in (("Subtotal", "1,500.00"), ("VAT", "225.00"), ("Total", "1,725.00")):
        d.t(380, d.y, lab); d.t(480, d.y, v); d.y -= 14
    d.save()


def hard6_pharmacy(path):
    d = Doc(path)
    d.line("Hope Pharmacy", size=15, bold=True, gap=22)
    d.line("Pharmacy Invoice", size=12, bold=True, gap=20)
    d.line("Invoice No: PH-300      Date: 2024-10-01", gap=14)
    d.line("Patient Name: Majed Saleh", gap=18)
    X = [40, 300, 350, 410, 480]
    for x, t in zip(X, ["Item", "Qty", "Price", "Total", "Pack"]):
        d.t(x, d.y, t, bold=True)
    d.y -= 16
    for r in (("Metformin 850 mg Tablets", "2", "18.00", "36.00", "Box"), ("Insulin Glargine 100 IU/ml", "1", "95.00", "95.00", "Pen"),
              ("Vitamin D3 1000 IU Capsules", "3", "12.00", "36.00", "Box")):
        for x, v in zip(X, r):
            d.t(x, d.y, v)
        d.y -= 15
    d.y -= 8
    d.t(380, d.y, "Total"); d.t(480, d.y, "167.00")
    d.save()


def hard7_lab(path):
    d = Doc(path)
    d.line("Precision Diagnostics Laboratory", size=15, bold=True, gap=22)
    d.line("Lab Result Report", size=12, bold=True, gap=20)
    d.line("Patient Name: Rana Khalid      Date: 2024-09-14", gap=18)
    X = [40, 250, 320, 390, 520]
    for x, t in zip(X, ["Test Name", "Result", "Unit", "Reference Range", "Flag"]):
        d.t(x, d.y, t, bold=True)
    d.y -= 16
    d.t(40, d.y, "HEMATOLOGY", bold=True); d.y -= 15
    for r in (("White Blood Cells", "11.8", "10^3/uL", "4.0 - 11.0", "H"), ("Platelets", "250", "10^3/uL", "150 - 450", "")):
        for x, v in zip(X, r):
            d.t(x, d.y, v)
        d.y -= 15
    d.t(40, d.y, "BIOCHEMISTRY", bold=True); d.y -= 15
    for r in (("C-Reactive Protein", "3.2", "mg/L", "< 5.0", ""), ("Vitamin D", "18", "ng/mL", "30 - 100", "L")):
        for x, v in zip(X, r):
            d.t(x, d.y, v)
        d.y -= 15
    d.save()


def hard8_stay(path):
    d = Doc(path)
    d.line("Al Wafa Hospital", size=15, bold=True, gap=22)
    d.line("Hospital Invoice", size=12, bold=True, gap=20)
    d.line("Invoice No: WF-12      Invoice Date: 2024-12-11", gap=14)
    d.line("Patient Name: Tariq Anwar", gap=14)
    d.line("Admission Date: 2024-12-05", gap=14)
    d.line("Discharge Date: 2024-12-09", gap=14)
    d.line("Room Type: Semi-private      Number of Days: 4", gap=18)
    X = [40, 330, 390, 480]
    for x, t in zip(X, ["Description", "Qty", "Unit Price", "Total"]):
        d.t(x, d.y, t, bold=True)
    d.y -= 16
    for r in (("Room Charges", "4", "350.00", "1,400.00"), ("Operating Room Fee", "1", "900.00", "900.00")):
        for x, v in zip(X, r):
            d.t(x, d.y, v)
        d.y -= 15
    d.y -= 8
    d.t(380, d.y, "Total"); d.t(480, d.y, "2,300.00")
    d.save()


def build(out: Path):
    out.mkdir(parents=True, exist_ok=True)
    hard1(out / "h1.pdf"); hard2(out / "h2.pdf"); hard3(out / "h3.pdf"); hard4(out / "h4.pdf")
    hard6_pharmacy(out / "h6.pdf"); hard7_lab(out / "h7.pdf"); hard8_stay(out / "h8.pdf")
    invoice_en(out / "_a.pdf", ITEMS_EN, totals=TOTALS_EN, invoice_no="INV-A1")
    invoice_en(out / "_b.pdf", ITEMS_EN[:2], totals={"subtotal": 230.0, "total": 230.0}, invoice_no="INV-B2", patient="Salem Nasser")
    merge([out / "_a.pdf", out / "_b.pdf"], out / "h5_two_invoices.pdf")
    import pypdfium2 as pdfium
    from PIL import Image
    pg = pdfium.PdfDocument(str(out / "h1.pdf"))[0].render(scale=200 / 72).to_pil().convert("L").rotate(1.6, expand=False, fillcolor=255)
    pg.convert("RGB").save(out / "h9_skew_scan.pdf", resolution=200)
    return out
