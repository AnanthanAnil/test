import os
import re
import sys
import subprocess
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak

RAW_DIAGNOSTIC_DATA = """
Telematics Diagnostic Report
Generated: 2026-10-17 18:07:29
Device: be859494
ARCHITECTURE DETAILS
·        T.OS Version: 26.07.12
·        T.OS Core Version: TOS_5G_CORE_UNSIGNED_RELEASE_V26.2.5.8
·        Harman Version: ReadyConnect_EU_TML_R7.10.0
·        eSync Version: eSync_TML_TCU_2.4.36
·        Quectel Version: AG59XEBYJR01A06M8G_OCPU_BYJ_BETA20260611_01.001
·        IOC Version: 26252A
·        VIN: H1Y24N74A01NEWT55
·        VID: 12e04367-4994-4ba4-8c71-2076ad148713
·        IMEI: 357867140003543
·        ICCID: 8991922506995757815F
·        Serial Number: Test2624AS216001139
·        HABL System State: —
·        LCM Current Mode: AUTHORIZED_MODE
·        Fuel Type: PV
BOOT UP TIMING
·        Kernel: 10.594s
·        Userspace: 35.582s
·        Total Boot: 46.176s
·        Multi-User Target: 34.441s
SERVICE LEVEL BOOTUP TIMING
·        18.681s firmware-mount.service
·         6.473s firewall.service
·         5.456s seccrypt-manager.service
·         3.857s chronyd.service
·         2.991s busybox-syslog.service
·         2.638s emac_ioss.service
·         2.225s logd.service
·         2.218s firmware-mount-emmc.service
·         2.186s bluetooth_power.service
·         2.099s init-can.service
·         2.096s init_audio.service
·         2.001s ql_atfwd.service
·         1.941s init_qti_cnss2_auto.service
·         1.862s dataipa.service
·         1.798s ql_time_daemon.service
·         1.720s ql_audiod.service
·         1.700s ip6tables.service
·         1.692s iptables.service
·         1.675s mcm-core2.service
·         1.673s mcm-core.service
·         1.659s port_bridge.service
·         1.638s ql_netd.service
·         1.634s qcedev.service
·         1.509s systemd-udev-trigger.service
·         1.161s dev-ubi2_0.device
·         1.094s diag-reboot-app.service
·         1.063s adbd.service
·          993ms remote.service
·          992ms systemrw-data.service
·          960ms load_coresight-dlkm.service
·          843ms smcinvoke.service
·          808ms usb.service
·          802ms ssgtzd.service
·          788ms thermal-engine.service
·          783ms QCMAP_copybind.service
·          776ms init_post_boot.service
·          759ms sshdgenkeys.service
·          571ms QCMAP_ConnectionManagerd.service
·          557ms systemrw-resourcemanager.xml.service
·          537ms systemrw-sap.conf.service
·          536ms esync_start.service
·          536ms systemrw-data-ipa.service
·          529ms systemrw-gps.conf.service
·          522ms systemrw-izat.conf.service
·          521ms systemrw-data-usb.service
·          516ms systemrw-enable.service
·          515ms systemrw-sensors.conf.service
·          504ms systemrw-tel.conf.service
·          475ms systemrw-wifi.service
·          473ms dbus.service
·          457ms systemrw-data-adpl.service
·          436ms qseecomd_init.service
·          436ms systemrw-apdr.conf.service
·          424ms qtid.service
·          419ms systemd-journald.service
·          391ms rmnetcore.service
·          389ms rmnetsch.service
·          340ms systemd-udevd.service
·          321ms powermanager-daemon.service
·          274ms ql_rpcd.service
·          232ms systemd-tmpfiles-setup-dev.service
·          218ms var-volatile.mount
·          213ms sys-kernel-tracing.mount
·          202ms dev-mqueue.mount
·          201ms qwesd.service
·          153ms sys-fs-fuse-connections.mount
·          146ms modprobe@fuse.service
·          145ms modprobe@configfs.service
·          139ms systemd-sysctl.service
·          135ms sensor_hal_daemon.service
·          132ms sys-kernel-config.mount
·          123ms systemd-tmpfiles-clean.service
·          123ms sys-kernel-debug.mount
·          122ms systemd-random-seed.service
·          111ms ipacm.service
·           97ms tmp.mount
·           89ms thermal-eth-netlink.service
·           70ms sshd.socket
·           53ms systemd-tmpfiles-setup.service
·           50ms netmgrd.service
·           42ms earlyinit-logd.service
·           32ms alert.service
·           31ms diag-router.service
·           23ms systemd-journal-flush.service
·           22ms aws.service
·           19ms location_hal_daemon.service
·           13ms sam.service
·           10ms loc_launcher.service
·            9ms sdm.service
·            9ms hm.service
·            8ms vrm.service
·            8ms cms.service
·            5ms init_sys_mss.service
DEVICE VITALS
·        CPU Usage: 56.2%
·        RAM Usage: 67.7%
·        Peak CPU Usage: 96.2%
·        Avg CPU Usage: 26.0%
·        Peak RAM Usage: 68.3%
·        Avg RAM Usage: 67.0%
·        SoC Temperature (live): 47.1°C
·        Peak SoC Temp: 47.5°C
·        Peak CPU Core Temp: 47.5°C
·        Final Cooldown: 47.1°C
"""

class WatermarkCanvas:
    """Draws a subtle, angled background watermark on every generated page."""
    def __init__(self, watermark_text="CONFIDENTIAL"):
        self.watermark_text = watermark_text

    def __call__(self, canvas_obj, doc):
        canvas_obj.saveState()
        canvas_obj.setFont("Helvetica-Bold", 52)
        canvas_obj.setFillColor(colors.HexColor("#0f172a"), alpha=0.04)
        
        cx = (210 * mm) / 2.0
        cy = (297 * mm) / 2.0
        
        canvas_obj.translate(cx, cy)
        canvas_obj.rotate(35)
        canvas_obj.drawCentredString(0, 0, self.watermark_text)
        canvas_obj.restoreState()

def parse_diagnostics(raw_text):
    parsed = {"meta": {}, "arch": {}, "boot_timing": {}, "services": [], "vitals": {}}
    lines = [line.strip() for line in raw_text.strip().split("\n") if line.strip()]
    current_section = "HEADER"
    for line in lines:
        if "ARCHITECTURE DETAILS" in line:
            current_section = "ARCH"
            continue
        elif "BOOT UP TIMING" in line:
            current_section = "BOOT"
            continue
        elif "SERVICE LEVEL BOOTUP TIMING" in line:
            current_section = "SERVICES"
            continue
        elif "DEVICE VITALS" in line:
            current_section = "VITALS"
            continue

        if current_section == "HEADER":
            if line.startswith("Generated:"):
                parsed["meta"]["generated"] = line.replace("Generated:", "").strip()
            elif line.startswith("Device:"):
                parsed["meta"]["device"] = line.replace("Device:", "").strip()
        elif current_section == "ARCH":
            clean = line.lstrip("·").strip()
            if ":" in clean:
                k, v = clean.split(":", 1)
                parsed["arch"][k.strip()] = v.strip()
        elif current_section == "BOOT":
            clean = line.lstrip("·").strip()
            if ":" in clean:
                k, v = clean.split(":", 1)
                parsed["boot_timing"][k.strip()] = v.strip()
        elif current_section == "SERVICES":
            clean = line.lstrip("·").strip()
            match = re.match(r"^([\d\.]+(?:s|ms))\s+(.*)$", clean)
            if match:
                dur, name = match.groups()
                parsed["services"].append((dur.strip(), name.strip()))
        elif current_section == "VITALS":
            clean = line.lstrip("·").strip()
            if ":" in clean:
                k, v = clean.split(":", 1)
                parsed["vitals"][k.strip()] = v.strip()
    return parsed

def build_telematics_pdf(report_data, output_path="telematics_diagnostic_report.pdf", watermark_text="TATA MOTORS - INTERNAL"):
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
        "CellText",
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

    # 1. Document Header
    elements.append(Paragraph("Automotive Telematics Diagnostic Report", title_style))
    elements.append(Paragraph(
        f"Generated: {report_data['meta'].get('generated', 'N/A')}  |  "
        f"Target ADB Device: {report_data['meta'].get('device', 'N/A')}  |  "
        f"Target VIN: {report_data['arch'].get('VIN', 'N/A')}",
        subtitle_style
    ))
    elements.append(Spacer(1, 4 * mm))

    # 2. Executive KPI Summary Cards (4 across = 186mm / 4 = 46.5mm)
    kpi_data = [[
        Paragraph(
            "<font color='#64748b' size=7.5><b>TOTAL BOOT TIME</b></font>"
            f"<br/><font size=13 color='#0284c7'><b>{report_data['boot_timing'].get('Total Boot', 'N/A')}</b></font>"
            f"<br/><font color='#64748b' size=7.5>Kernel: {report_data['boot_timing'].get('Kernel', 'N/A')}</font>",
            kpi_style
        ),
        Paragraph(
            "<font color='#64748b' size=7.5><b>PEAK CPU LOAD</b></font>"
            f"<br/><font size=13 color='#e11d48'><b>{report_data['vitals'].get('Peak CPU Usage', 'N/A')}</b></font>"
            f"<br/><font color='#64748b' size=7.5>Avg: {report_data['vitals'].get('Avg CPU Usage', 'N/A')}</font>",
            kpi_style
        ),
        Paragraph(
            "<font color='#64748b' size=7.5><b>MAX SOC TEMP</b></font>"
            f"<br/><font size=13 color='#ea580c'><b>{report_data['vitals'].get('Peak SoC Temp', 'N/A')}</b></font>"
            f"<br/><font color='#64748b' size=7.5>Live: {report_data['vitals'].get('SoC Temperature (live)', 'N/A')}</font>",
            kpi_style
        ),
        Paragraph(
            "<font color='#64748b' size=7.5><b>PEAK RAM USAGE</b></font>"
            f"<br/><font size=13 color='#475569'><b>{report_data['vitals'].get('Peak RAM Usage', 'N/A')}</b></font>"
            f"<br/><font color='#64748b' size=7.5>Avg: {report_data['vitals'].get('Avg RAM Usage', 'N/A')}</font>",
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

    # 3. Hardware & Firmware Specifications
    elements.append(Paragraph("Hardware & Firmware Specifications", section_header_style))
    arch_items = list(report_data["arch"].items())
    arch_rows = []
    for i in range(0, len(arch_items), 2):
        k1, v1 = arch_items[i]
        k2, v2 = arch_items[i + 1] if i + 1 < len(arch_items) else ("", "")
        arch_rows.append([
            Paragraph(k1, cell_bold),
            Paragraph(v1, cell_style),
            Paragraph(k2, cell_bold),
            Paragraph(v2, cell_style)
        ])

    arch_table = Table(arch_rows, colWidths=[36 * mm, 57 * mm, 36 * mm, 57 * mm])
    arch_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#ffffff")),
        ("LINEBELOW", (0, 0), (-1, -1), 0.5, colors.HexColor("#f1f5f9")),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ("TOPPADDING", (0, 0), (-1, -1), 3.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    elements.append(arch_table)
    elements.append(Spacer(1, 4 * mm))

    # 4. Top 10 Boot Delays Table (Lighter Header)
    elements.append(Paragraph("Top 10 Boot-Time Delay Services", section_header_style))
    top_services = report_data["services"][:10]
    top_rows = [[
        Paragraph("Rank", th_style),
        Paragraph("Duration", th_style),
        Paragraph("Systemd Service Unit", th_style)
    ]]
    for idx, (dur, srv) in enumerate(top_services, start=1):
        top_rows.append([
            Paragraph(f"#{idx}", cell_bold),
            Paragraph(f"<b>{dur}</b>", cell_style),
            Paragraph(srv, cell_style)
        ])

    # 16 + 28 + 142 = 186 mm
    top_table = Table(top_rows, colWidths=[16 * mm, 28 * mm, 142 * mm])
    top_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
        ("LINEBELOW", (0, 0), (-1, 0), 1.0, colors.HexColor("#cbd5e1")),
        ("TOPPADDING", (0, 0), (-1, 0), 5),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 5),
        ("LINEBELOW", (0, 1), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ("TOPPADDING", (0, 1), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 3),
    ]))
    elements.append(top_table)

    # 5. Page 2: Dual Column Full Trace
    elements.append(PageBreak())
    elements.append(Paragraph("Full Systemd Service Level Timing Trace", section_header_style))
    elements.append(Paragraph("Complete execution order and initialization duration across all boot stages.", subtitle_style))
    elements.append(Spacer(1, 3 * mm))

    all_srv = report_data["services"]
    half = (len(all_srv) + 1) // 2
    left_col = all_srv[:half]
    right_col = all_srv[half:]

    double_table_data = [[
        Paragraph("Duration", th_style),
        Paragraph("Service Unit", th_style),
        Paragraph("Duration", th_style),
        Paragraph("Service Unit", th_style)
    ]]

    for i in range(half):
        d_l, s_l = left_col[i] if i < len(left_col) else ("", "")
        d_r, s_r = right_col[i] if i < len(right_col) else ("", "")
        double_table_data.append([
            Paragraph(f"<b>{d_l}</b>", cell_style),
            Paragraph(s_l, cell_style),
            Paragraph(f"<b>{d_r}</b>", cell_style),
            Paragraph(s_r, cell_style)
        ])

    # 18 + 75 + 18 + 75 = 186 mm
    srv_table = Table(double_table_data, colWidths=[18 * mm, 75 * mm, 18 * mm, 75 * mm])
    srv_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f1f5f9")),
        ("LINEBELOW", (0, 0), (-1, 0), 1.0, colors.HexColor("#cbd5e1")),
        ("TOPPADDING", (0, 0), (-1, 0), 5),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 5),
        ("LINEBELOW", (0, 1), (-1, -1), 0.5, colors.HexColor("#f1f5f9")),
        ("LINEBEFORE", (2, 0), (2, -1), 0.5, colors.HexColor("#cbd5e1")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e1")),
        ("TOPPADDING", (0, 1), (-1, -1), 2.2),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 2.2),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    elements.append(srv_table)

    # Build PDF with watermark callback on all pages
    watermark_fn = WatermarkCanvas(watermark_text=watermark_text)
    doc.build(elements, onFirstPage=watermark_fn, onLaterPages=watermark_fn)
    print(f"Generated Diagnostic PDF: {os.path.abspath(output_path)}")
    return output_path

if __name__ == "__main__":
    parsed = parse_diagnostics(RAW_DIAGNOSTIC_DATA)
    pdf_file = build_telematics_pdf(parsed)
    if sys.platform.startswith('darwin'):
        subprocess.run(['open', pdf_file])
    elif os.name == 'nt':
        os.startfile(pdf_file)
    elif os.name == 'posix':
        subprocess.run(['xdg-open', pdf_file])