import os
import sys
import subprocess
from datetime import datetime
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

class WatermarkCanvas:
    """Draws a subtle, angled background watermark on every generated page."""
    def __init__(self, watermark_text="CONFIDENTIAL"):
        self.watermark_text = watermark_text

    def __call__(self, canvas_obj, doc):
        canvas_obj.saveState()
        # Light slate gray with high transparency
        canvas_obj.setFont("Helvetica-Bold", 52)
        canvas_obj.setFillColor(colors.HexColor("#0f172a"), alpha=0.04)
        
        # Center of A4 (210mm x 297mm)
        cx = (210 * mm) / 2.0
        cy = (297 * mm) / 2.0
        
        canvas_obj.translate(cx, cy)
        canvas_obj.rotate(35)
        canvas_obj.drawCentredString(0, 0, self.watermark_text)
        canvas_obj.restoreState()

def generate_provisioning_pdf(output_path="ecu_provisioning_report.pdf", watermark_text="TATA MOTORS - INTERNAL"):
    # Standard A4 (210mm x 297mm) with 12mm margins -> 186mm printable width
    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        leftMargin=12 * mm,
        rightMargin=12 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm
    )

    elements = []
    styles = getSampleStyleSheet()

    # --- Typography Styles ---
    title_style = ParagraphStyle(
        "DocTitle",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=16,
        leading=20,
        textColor=colors.HexColor("#0f172a"),
        spaceAfter=2
    )
    subtitle_style = ParagraphStyle(
        "DocSub",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8.5,
        leading=12,
        textColor=colors.HexColor("#64748b"),
        spaceAfter=12
    )
    section_header_style = ParagraphStyle(
        "SectionH2",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=10.5,
        leading=14,
        textColor=colors.HexColor("#0369a1"),
        spaceBefore=8,
        spaceAfter=6
    )
    th_style = ParagraphStyle(
        "TH",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=8,
        leading=10,
        textColor=colors.HexColor("#1e293b")
    )
    cell_style = ParagraphStyle(
        "Cell",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=7.5,
        leading=10,
        textColor=colors.HexColor("#1e293b")
    )
    cell_bold = ParagraphStyle(
        "CellBold",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=7.5,
        leading=10,
        textColor=colors.HexColor("#334155")
    )
    kpi_style = ParagraphStyle(
        "KPICell",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=7.5,
        leading=11
    )

    # 1. Header
    elements.append(Paragraph("ECU Provisioning Automation Report", title_style))
    elements.append(Paragraph(
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  |  "
        "Target ADB Device: be859494  |  Target VIN: H1Y24N74A01NEWT55",
        subtitle_style
    ))
    elements.append(Spacer(1, 4 * mm))

    # 2. Executive KPI Summary Cards (4 across = 186mm / 4 = 46.5mm)
    mock_records = [
        {"iteration": 1, "flow": "Happy Flow (Matching Fuel)", "expected": "PV", "actual": "PV", "lcu": "PROVISION", "result": "PASS"},
        {"iteration": 1, "flow": "Negative Flow (Different Fuel)", "expected": "PV", "actual": "PV", "lcu": "PROVISION", "result": "PASS"},
        {"iteration": 2, "flow": "Happy Flow (Matching Fuel)", "expected": "PV", "actual": "PV", "lcu": "PROVISION", "result": "PASS"},
        {"iteration": 2, "flow": "Negative Flow (Different Fuel)", "expected": "PV", "actual": "EV", "lcu": "FACTORY", "result": "FAIL"},
        {"iteration": 3, "flow": "Happy Flow (Matching Fuel)", "expected": "PV", "actual": "PV", "lcu": "PROVISION", "result": "PASS"},
        {"iteration": 3, "flow": "Negative Flow (Different Fuel)", "expected": "PV", "actual": "PV", "lcu": "PROVISION", "result": "PASS"},
    ]
    total_runs = len(mock_records)
    passed_runs = sum(1 for r in mock_records if r["result"] == "PASS")
    pass_pct = (passed_runs / total_runs * 100) if total_runs else 0.0

    kpi_data = [[
        Paragraph(
            "<font color='#64748b' size=7.5><b>TOTAL RUNS</b></font>"
            f"<br/><font size=13 color='#0284c7'><b>{total_runs} Flows</b></font>"
            f"<br/><font color='#64748b' size=7.5>Passed: {passed_runs} / Failed: {total_runs - passed_runs}</font>",
            kpi_style
        ),
        Paragraph(
            "<font color='#64748b' size=7.5><b>OVERALL PASS RATE</b></font>"
            f"<br/><font size=13 color='{'#15803d' if pass_pct >= 80 else '#e11d48'}'><b>{pass_pct:.1f}%</b></font>"
            f"<br/><font color='#64748b' size=7.5>Nominal Threshold: 100%</font>",
            kpi_style
        ),
        Paragraph(
            "<font color='#64748b' size=7.5><b>TARGET FUEL (DID 5543)</b></font>"
            "<br/><font size=13 color='#475569'><b>PV (0x01)</b></font>"
            "<br/><font color='#64748b' size=7.5>Expected 5404: PV</font>",
            kpi_style
        ),
        Paragraph(
            "<font color='#64748b' size=7.5><b>LCM FINAL MODE</b></font>"
            "<br/><font size=13 color='#0284c7'><b>PROVISION</b></font>"
            "<br/><font color='#64748b' size=7.5>eSync / AWS: Active</font>",
            kpi_style
        ),
    ]]

    kpi_table = Table(kpi_data, colWidths=[46.5 * mm] * 4)
    kpi_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
        ("BOX", (0, 0), (-1, -1), 0.75, colors.HexColor("#cbd5e1")),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
        ("TOPPADDING", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    elements.append(kpi_table)
    elements.append(Spacer(1, 4 * mm))

    # 3. Target Hardware & Session Parameters (2 pairs across = 186mm)
    elements.append(Paragraph("Target Session & Configuration", section_header_style))
    session_rows = [
        [
            Paragraph("Target Device Serial", cell_bold),
            Paragraph("Test2624AS216001139", cell_style),
            Paragraph("ADB Device Identifier", cell_bold),
            Paragraph("be859494", cell_style)
        ],
        [
            Paragraph("Target VIN (DID F190)", cell_bold),
            Paragraph("H1Y24N74A01NEWT55", cell_style),
            Paragraph("Provisioning Endpoint", cell_bold),
            Paragraph("devicedata.upgbeta.tmpv.tatamotors.io", cell_style)
        ],
        [
            Paragraph("Configured Fuel", cell_bold),
            Paragraph("PV", cell_style),
            Paragraph("Secure Storage Claim ID", cell_bold),
            Paragraph("rw.fs.pv_claimcrt.*", cell_style)
        ]
    ]
    # 36 + 57 + 36 + 57 = 186 mm
    session_table = Table(session_rows, colWidths=[36 * mm, 57 * mm, 36 * mm, 57 * mm])
    session_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#ffffff")),
        ("LINEBELOW", (0, 0), (-1, -1), 0.5, colors.HexColor("#f1f5f9")),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ("TOPPADDING", (0, 0), (-1, -1), 3.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    elements.append(session_table)
    elements.append(Spacer(1, 4 * mm))

    # 4. Provisioning Flow Regression Matrix (Lighter Table Header)
    elements.append(Paragraph("Iteration Execution Log", section_header_style))

    table_headers = [
        Paragraph("Iter", th_style),
        Paragraph("Test Flow Sequence", th_style),
        Paragraph("Expected (5404)", th_style),
        Paragraph("Actual (5404)", th_style),
        Paragraph("LCU Mode", th_style),
        Paragraph("Verdict", th_style)
    ]
    results_data = [table_headers]
    row_styles = []

    for idx, r in enumerate(mock_records, start=1):
        verdict = r["result"]
        verdict_color = colors.HexColor("#15803d") if verdict == "PASS" else colors.HexColor("#b91c1c")

        results_data.append([
            Paragraph(f"#{r['iteration']}", cell_bold),
            Paragraph(r["flow"], cell_style),
            Paragraph(r["expected"], cell_style),
            Paragraph(r["actual"], cell_style),
            Paragraph(r["lcu"], cell_style),
            Paragraph(f"<b>{verdict}</b>", ParagraphStyle("VStyle", parent=cell_bold, textColor=verdict_color))
        ])

    # 14 + 76 + 24 + 24 + 26 + 22 = 186 mm
    col_widths = [14 * mm, 76 * mm, 24 * mm, 24 * mm, 26 * mm, 22 * mm]
    results_table = Table(results_data, colWidths=col_widths, repeatRows=1)
    results_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
        ("LINEBELOW", (0, 0), (-1, 0), 1.0, colors.HexColor("#cbd5e1")),
        ("TOPPADDING", (0, 0), (-1, 0), 5),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 5),
        ("LINEBELOW", (0, 1), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ("TOPPADDING", (0, 1), (-1, -1), 3.5),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 3.5),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    elements.append(results_table)

    # Build PDF with watermark callback on all pages
    watermark_fn = WatermarkCanvas(watermark_text=watermark_text)
    doc.build(elements, onFirstPage=watermark_fn, onLaterPages=watermark_fn)
    print(f"Generated ECU Provisioning PDF: {os.path.abspath(output_path)}")
    return output_path

if __name__ == "__main__":
    pdf_file = generate_provisioning_pdf()
    if sys.platform.startswith('darwin'):
        subprocess.run(['open', pdf_file])
    elif os.name == 'nt':
        os.startfile(pdf_file)
    elif os.name == 'posix':
        subprocess.run(['xdg-open', pdf_file])