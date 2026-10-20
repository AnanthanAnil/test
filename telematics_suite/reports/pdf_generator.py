import os
import re
import math
import subprocess
import sys
from datetime import datetime
from dataclasses import dataclass, field
from typing import Optional, Sequence
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

# ---------------------------------------------------------------------------
# CONSTANTS & SETUP
# ---------------------------------------------------------------------------
PAGE_W, PAGE_H = A4
MARGIN = 12 * mm
CONTENT_W = PAGE_W - 2 * MARGIN

HEADER_BG = colors.HexColor("#f1f5f9")
GRID = colors.HexColor("#cbd5e1")
TEXT = colors.HexColor("#0f172a")
MUTED = colors.HexColor("#64748b")
MUTED_HEX = "#64748b"
GREEN_HEX = "#15803d"
RED_HEX = "#b91c1c"
WATERMARK_TEXT = "UST-TML"
WATERMARK_ALPHA = 0.04

_CASCADIA_FILES = {"regular": "CascadiaCode-Regular.ttf", "bold": "CascadiaCode-Bold.ttf"}
_FONT_FOLDERS = (
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts"),
    os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "Windows", "Fonts"),
    os.path.join(os.environ.get("WINDIR", "C:\\Windows"), "Fonts"),
)

def _find_font(filename: str) -> Optional[str]:
    for folder in _FONT_FOLDERS:
        path = os.path.join(folder, filename)
        if os.path.isfile(path):
            return path
    return None

def _register_report_fonts() -> tuple[str, str]:
    regular_path = _find_font(_CASCADIA_FILES["regular"])
    bold_path = _find_font(_CASCADIA_FILES["bold"])
    if regular_path is None:
        return "Courier", "Courier-Bold"
    pdfmetrics.registerFont(TTFont("CascadiaCode", regular_path))
    bold_name = "CascadiaCode-Bold" if bold_path else "CascadiaCode"
    if bold_path:
        pdfmetrics.registerFont(TTFont(bold_name, bold_path))
    pdfmetrics.registerFontFamily("CascadiaCode", normal="CascadiaCode", bold=bold_name,
                                  italic="CascadiaCode", boldItalic=bold_name)
    return "CascadiaCode", bold_name

REPORT_FONT, REPORT_FONT_BOLD = _register_report_fonts()

_STYLES = {
    "title": ParagraphStyle("title", fontName=REPORT_FONT_BOLD, fontSize=17, leading=21, textColor=TEXT),
    "meta": ParagraphStyle("meta", fontName=REPORT_FONT, fontSize=8.5, leading=11, textColor=MUTED),
    "section": ParagraphStyle("section", fontName=REPORT_FONT_BOLD, fontSize=10, leading=13,
                              textColor=TEXT, spaceBefore=10, spaceAfter=4),
    "cell": ParagraphStyle("cell", fontName=REPORT_FONT, fontSize=8, leading=10, textColor=TEXT),
    "cell_bold": ParagraphStyle("cell_bold", fontName=REPORT_FONT_BOLD, fontSize=8, leading=10, textColor=TEXT),
    "head": ParagraphStyle("head", fontName=REPORT_FONT_BOLD, fontSize=8, leading=10, textColor=TEXT),
    "kpi_label": ParagraphStyle("kpi_label", fontName=REPORT_FONT_BOLD, fontSize=7, leading=9, textColor=MUTED),
    "kpi_value": ParagraphStyle("kpi_value", fontName=REPORT_FONT_BOLD, fontSize=14, leading=17, textColor=TEXT),
    "note": ParagraphStyle("note", fontName=REPORT_FONT, fontSize=8, leading=10, textColor=MUTED),
}

# ---------------------------------------------------------------------------
# DATA CONTAINERS
# ---------------------------------------------------------------------------
@dataclass
class ProvisioningReportData:
    device_id: str
    vin: str
    serial: str
    fuel_target: str
    rows: list[dict]
    total_elapsed_sec: float
    endpoint: str = "devicedata.upgbeta.tmpv.tatamotors.io"
    storage_ids: Sequence[str] = field(default_factory=lambda: ["rw.fs.pv_claimcrt.cert", "rw.fs.pv_claimcrt.rsa_key"])
    generated_at: datetime = field(default_factory=datetime.now)


@dataclass
class DiagnosticReportData:
    device_id: str
    telemetry: dict[str, str]
    boot_total: str
    boot_kernel: str
    boot_userspace: str
    cpu_peak: str
    cpu_avg: str
    soc_max: str
    soc_live: str
    ram_peak: str
    specs: list[tuple[str, str]]
    blame_lines: list[str]
    generated_at: datetime = field(default_factory=datetime.now)
    failed_units: list[str] = field(default_factory=list)
    active_services: list[str] = field(default_factory=list)
    failed_reasons: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class BlameEntry:
    seconds: float
    duration_text: str
    unit: str

# ---------------------------------------------------------------------------
# PURE HELPERS
# ---------------------------------------------------------------------------
_DURATION_PART_RE = re.compile(r"([\d.]+)(min|ms|s)")

def format_duration(seconds: float) -> str:
    minutes, secs = divmod(seconds, 60)
    if minutes >= 1:
        return f"{int(minutes)}m {secs:04.1f}s"
    return f"{secs:.1f}s"

def duration_to_seconds(text: str) -> float:
    total = 0.0
    for number, unit in _DURATION_PART_RE.findall(text):
        value = float(number)
        if unit == "min": total += value * 60
        elif unit == "ms": total += value / 1000
        else: total += value
    return total

def parse_blame(lines: Sequence[str]) -> list[BlameEntry]:
    entries: list[BlameEntry] = []
    for line in lines:
        parts = line.strip().rsplit(None, 1)
        if len(parts) != 2 or not re.search(r"\d", parts[0]):
            continue
        entries.append(BlameEntry(duration_to_seconds(parts[0]), parts[0], parts[1]))
    return entries

def _p(text: str, style: str = "cell") -> Paragraph:
    return Paragraph(escape(str(text)), _STYLES[style])

def _colored(text: str, ok: Optional[bool]) -> str:
    if ok is None:
        return f"<font color='{MUTED_HEX}'>{escape(text)}</font>"
    color = GREEN_HEX if ok else RED_HEX
    return f"<font color='{color}'><b>{escape(text)}</b></font>"

# ---------------------------------------------------------------------------
# REPORTLAB DRAWING HELPERS
# ---------------------------------------------------------------------------
def _draw_page(canvas, doc) -> None:
    canvas.saveState()
    canvas.setFillColor(TEXT)
    canvas.setFillAlpha(WATERMARK_ALPHA)
    canvas.setFont(REPORT_FONT_BOLD, 54)
    canvas.translate(PAGE_W / 2, PAGE_H / 2)
    canvas.rotate(35)
    canvas.drawCentredString(0, 0, WATERMARK_TEXT)
    canvas.restoreState()

    canvas.saveState()
    canvas.setFont(REPORT_FONT, 7)
    canvas.setFillColor(MUTED)
    canvas.drawString(MARGIN, 7 * mm, doc.title)
    canvas.drawRightString(PAGE_W - MARGIN, 7 * mm, f"Page {doc.page}")
    canvas.restoreState()

def _new_doc(path: str, title: str) -> SimpleDocTemplate:
    return SimpleDocTemplate(
        path, pagesize=A4, title=title, author="Telematics Suite",
        leftMargin=MARGIN, rightMargin=MARGIN, topMargin=MARGIN, bottomMargin=MARGIN + 4 * mm,
    )

def _grid(rows: list[list], widths: list[float], header: bool = True) -> Table:
    table = Table(rows, colWidths=widths, repeatRows=1 if header else 0)
    style = [
        ("GRID", (0, 0), (-1, -1), 0.5, GRID),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]
    if header:
        style.append(("BACKGROUND", (0, 0), (-1, 0), HEADER_BG))
    table.setStyle(TableStyle(style))
    return table

def _kpi_grid(cards: list[tuple[str, str, Optional[str]]]) -> Table:
    cells = []
    for label, value, sub in cards:
        body = [Paragraph(escape(label.upper()), _STYLES["kpi_label"]), Paragraph(value, _STYLES["kpi_value"])]
        if sub:
            body.append(Paragraph(sub, _STYLES["meta"]))
        cells.append(body)
    width = CONTENT_W / len(cards)
    table = Table([cells], colWidths=[width] * len(cards))
    table.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.5, GRID),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, GRID),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
    ]))
    return table

def _kv_grid(pairs: list[tuple[str, str]]) -> Table:
    rows = []
    for i in range(0, len(pairs), 2):
        left = pairs[i]
        right = pairs[i + 1] if i + 1 < len(pairs) else ("", "")
        rows.append([_p(left[0], "cell_bold"), _p(left[1]), _p(right[0], "cell_bold"), _p(right[1])])
    return _grid(rows, [30 * mm, 63 * mm, 30 * mm, 63 * mm], header=False)

# ---------------------------------------------------------------------------
# REPORT 1: PROVISIONING
# ---------------------------------------------------------------------------
def build_provisioning_report(path: str, data: ProvisioningReportData) -> str:
    title = "ECU Provisioning Automation Report"
    doc = _new_doc(path, title)
    story: list = [
        Paragraph(escape(title), _STYLES["title"]),
        Spacer(1, 3 * mm),
        Paragraph(
            f"Generated: {escape(data.generated_at.strftime('%Y-%m-%d %H:%M:%S'))} &nbsp;|&nbsp; "
            f"Target ADB device: {escape(data.device_id)} &nbsp;|&nbsp; Target VIN: {escape(data.vin)}",
            _STYLES["meta"],
        ),
    ]

    total = len(data.rows)
    passes = sum(1 for r in data.rows if r["verdict"] == "PASS")
    if total:
        rate = passes / total * 100
        rate_markup = _colored(f"{rate:.1f}%", passes == total)
        rate_sub = f"{passes} of {total} flows passed"
    else:
        rate_markup = _colored("N/A", None)
        rate_sub = "No flows executed"
    
    story.append(Spacer(1, 4 * mm))
    story.append(_kpi_grid([
        ("Total Execution Time", escape(format_duration(data.total_elapsed_sec)), None),
        ("Overall Pass Rate", rate_markup, rate_sub),
        ("Target Fuel", escape(data.fuel_target), None),
        ("LCU Mode Policy", '<font size="8"><b>PROVISION / AUTHORIZED_MODE</b><br/>permitted</font>', "FACTORY prohibited"),
    ]))

    story.append(Paragraph("Target Session &amp; Configuration", _STYLES["section"]))
    story.append(_kv_grid([
        ("Serial", data.serial),
        ("Device ID", data.device_id),
        ("VIN", data.vin),
        ("Provisioning Endpoint", data.endpoint),
        ("Fuel", data.fuel_target),
        ("Storage IDs", ", ".join(data.storage_ids)),
    ]))

    story.append(Paragraph("Iteration Execution Log", _STYLES["section"]))
    header = [_p(h, "head") for h in ("Iter", "Test Flow Sequence", "Duration", "Expected (5404)", "Actual (5404)", "LCU Mode", "Verdict")]
    body: list[list] = [header]
    for row in data.rows:
        ok = row["verdict"] == "PASS"
        body.append([
            _p(row["iteration"]),
            _p(f"{row['flow']} | write {row.get('written', row['expected'])}"),
            _p(format_duration(row["duration_sec"])),
            _p(row["expected"]),
            _p(row["actual"]),
            _p(row["lcu"]),
            Paragraph(_colored(row["verdict"], ok), _STYLES["cell"]),
        ])
    if not data.rows:
        body.append([_p("—"), _p("No iterations were executed."), "", "", "", "", ""])
    story.append(_grid(body, [14 * mm, 56 * mm, 22 * mm, 24 * mm, 24 * mm, 30 * mm, 16 * mm]))

    doc.build(story, onFirstPage=_draw_page, onLaterPages=_draw_page)
    return path

# ---------------------------------------------------------------------------
# REPORT 2: DIAGNOSTICS
# ---------------------------------------------------------------------------
_TELEMETRY_ORDER = ("T.OS", "Quectel", "Harman", "eSync", "VID", "IMEI", "ICCID")
_UNIT_HEADERS = ("Unit", "Load", "Active", "Sub", "Description")
_CODE_RE = re.compile(r"\((code=[^)]*)\)")
_RESULT_RE = re.compile(r"\(([^)]*Result:[^)]*)\)")
_MANIFEST_FONT_SIZES = (7.0, 6.5, 6.0, 5.5, 5.0, 4.5)
_MANIFEST_HEADER_SPACE = 115  

def _trace_table(entries: list[BlameEntry]) -> Table:
    header_row = [_p("Duration", "head"), _p("Unit", "head"), _p("Duration", "head"), _p("Unit", "head")]
    rows: list[list] = [header_row]
    half = math.ceil(len(entries) / 2)
    for i in range(half):
        left = entries[i]
        right = entries[i + half] if (i + half) < len(entries) else None
        rows.append([
            _p(left.duration_text, "cell_bold"), _p(left.unit),
            _p(right.duration_text, "cell_bold") if right else "", _p(right.unit) if right else "",
        ])
    table = _grid(rows, [22 * mm, 71 * mm, 22 * mm, 71 * mm], header=True)
    table.setStyle(TableStyle([("TOPPADDING", (0, 0), (-1, -1), 1.2), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.2), ("VALIGN", (0, 0), (-1, -1), "MIDDLE")]))
    return table

def parse_systemctl_units(lines: Sequence[str]) -> list[list[str]]:
    rows: list[list[str]] = []
    for line in lines:
        parts = line.strip().lstrip("●*").strip().split(None, 4)
        if len(parts) < 4 or "." not in parts[0]: continue
        parts += [""] * (5 - len(parts))
        rows.append(parts)
    return rows

def parse_failure_reason(status_text: str) -> str:
    lines = [line.strip() for line in status_text.splitlines() if line.strip()]
    if not lines: return "Status not available"
    found: list[str] = []
    for line in lines:
        if line.startswith("Active:"):
            match = _RESULT_RE.search(line)
            if match: found.append(match.group(1))
        elif line.startswith(("Process:", "Main PID:")):
            match = _CODE_RE.search(line)
            if match: found.append(match.group(1))
    last_log = lines[-1]
    if not last_log.startswith(("Active:", "Process:", "Main PID:", "Loaded:")) and last_log not in found:
        found.append(f"Last log: {last_log[:160]}")
    return " | ".join(dict.fromkeys(found)) or "No failure reason in status output"

def unit_status_text(device: str, unit: str) -> str:
    try:
        res = subprocess.run(f'adb -s {device} shell "systemctl status {unit} --no-pager -l"', shell=True, capture_output=True, text=True, timeout=20, creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0)
        return re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", res.stdout)
    except subprocess.TimeoutExpired:
        return ""

def _unit_table(rows: list[list[str]], empty_text: str):
    if not rows: return _p(empty_text, "note")
    body: list[list] = [[_p(h, "head") for h in _UNIT_HEADERS]]
    for row in rows: body.append([_p(cell) for cell in row])
    return _grid(body, [60 * mm, 16 * mm, 18 * mm, 18 * mm, 74 * mm])

def _diagnostic_sections(data: DiagnosticReportData) -> tuple[list, list]:
    entries = parse_blame(data.blame_lines)
    top10 = sorted(entries, key=lambda e: e.seconds, reverse=True)[:10]

    summary: list = [
        Paragraph("System Telemetry", _STYLES["section"]),
        _kv_grid([(key, data.telemetry.get(key, "N/A")) for key in _TELEMETRY_ORDER]),
        Paragraph("System Vitals", _STYLES["section"]),
        _kpi_grid([
            ("Total Boot Time", escape(data.boot_total), escape(f"Kernel {data.boot_kernel} | Userspace {data.boot_userspace}")),
            ("Peak CPU Load", escape(data.cpu_peak), escape(f"Avg {data.cpu_avg}")),
            ("Max SoC Temp", escape(data.soc_max), escape(f"Live {data.soc_live}")),
            ("Peak RAM Usage", escape(data.ram_peak), None),
        ]),
        Paragraph("Hardware &amp; Firmware Specifications", _STYLES["section"]),
        _kv_grid(data.specs) if data.specs else _p("No specification data available.", "note"),
        Paragraph("Top 10 Boot-Time Delay Services", _STYLES["section"]),
    ]
    if top10:
        top_rows: list[list] = [[_p("Rank", "head"), _p("Unit", "head"), _p("Duration", "head")]]
        for rank, entry in enumerate(top10, start=1):
            top_rows.append([_p(rank), _p(entry.unit), _p(entry.duration_text)])
        summary.append(_grid(top_rows, [14 * mm, 120 * mm, 52 * mm]))
    else:
        summary.append(_p("No systemd-analyze blame data available.", "note"))
        
    failed_rows = [[unit, load, active, sub, data.failed_reasons.get(unit, desc)] for unit, load, active, sub, desc in parse_systemctl_units(data.failed_units)]
    summary += [
        Paragraph(f"Failed Units ({len(failed_rows)})", _STYLES["section"]),
        _unit_table(failed_rows, "No failed units reported."),
    ]

    trace: list = [Paragraph(f"Systemd Service Timing Trace ({len(entries)} units)", _STYLES["section"])]
    trace.append(_trace_table(entries) if entries else _p("No timing trace available.", "note"))
    return summary, trace

def _manifest_units(lines: Sequence[str]) -> list[tuple[str, str]]:
    return [(row[0], row[3] or row[2]) for row in parse_systemctl_units(lines)]

def _manifest_summary(units: list[tuple[str, str]], device_id: str) -> str:
    running = sum(1 for _, state in units if state == "running")
    exited = sum(1 for _, state in units if state == "exited")
    parts = [f"Device: {device_id}", f"Total Units: {len(units)}", f"Active Running: {running}", f"Active Exited (One-shot/DLKM): {exited}"]
    other = len(units) - running - exited
    if other: parts.append(f"Other: {other}")
    return "  |  ".join(parts)

def _manifest_table(units: list[tuple[str, str]], font_size: float) -> Table:
    body_style = ParagraphStyle("mf_body", fontName=REPORT_FONT, fontSize=font_size, leading=font_size * 1.2, textColor=TEXT)
    head_style = ParagraphStyle("mf_head", fontName=REPORT_FONT_BOLD, fontSize=font_size, leading=font_size * 1.2, textColor=TEXT)
    body: list[list] = [[Paragraph(h, head_style) for _ in range(3) for h in ("Service Unit", "State")]]
    for start in range(0, len(units), 3):
        cells: list = []
        for unit, state in units[start:start + 3]:
            cells += [Paragraph(escape(unit), body_style), Paragraph(escape(state), body_style)]
        cells += [""] * (6 - len(cells))
        body.append(cells)
    table = _grid(body, [46 * mm, 16 * mm] * 3)
    table.setStyle(TableStyle([("TOPPADDING", (0, 0), (-1, -1), 1.2), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.2)]))
    return table

def _fit_manifest(units: list[tuple[str, str]]) -> tuple[Table, int]:
    avail_h = PAGE_H - 2 * MARGIN - 4 * mm - _MANIFEST_HEADER_SPACE
    for font_size in _MANIFEST_FONT_SIZES:
        table = _manifest_table(units, font_size)
        if table.wrap(CONTENT_W, avail_h)[1] <= avail_h:
            return table, len(units)
    best, best_count = _manifest_table([], _MANIFEST_FONT_SIZES[-1]), 0
    lo, hi = 0, len(units) - 1
    while lo <= hi:
        mid = (lo + hi) // 2
        candidate = _manifest_table(units[:mid], _MANIFEST_FONT_SIZES[-1])
        if candidate.wrap(CONTENT_W, avail_h)[1] <= avail_h:
            best, best_count = candidate, mid
            lo = mid + 1
        else:
            hi = mid - 1
    return best, best_count

def _services_manifest_flowables(lines: Sequence[str], device_id: str = "N/A") -> list:
    units = _manifest_units(lines)
    flowables: list = [
        Paragraph(f"Active Services Manifest ({len(units)} Units)", _STYLES["section"]),
        Paragraph(escape(_manifest_summary(units, device_id)), _STYLES["meta"]),
        Spacer(1, 2 * mm),
    ]
    if not units:
        flowables.append(_p("No active services reported.", "note"))
        return flowables
    table, shown = _fit_manifest(units)
    flowables.append(table)
    if shown < len(units):
        flowables.append(Spacer(1, 2 * mm))
        flowables.append(_p(f"{len(units) - shown} more units not shown on this page.", "note"))
    return flowables

def build_single_page_services_pdf(raw_services_text: str, output_path: str = "active_services_a4.pdf", device_id: str = "N/A") -> str:
    doc = _new_doc(output_path, "Active Services Manifest")
    story: list = [
        Paragraph(f"Generated: {escape(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))}", _STYLES["meta"]),
        Spacer(1, 3 * mm),
    ]
    story += _services_manifest_flowables(raw_services_text.splitlines(), device_id)
    doc.build(story, onFirstPage=_draw_page, onLaterPages=_draw_page)
    return output_path

def build_diagnostic_report(path: str, data: DiagnosticReportData) -> str:
    title = "Automotive Telematics Diagnostic Snapshot"
    doc = _new_doc(path, title)
    summary, trace = _diagnostic_sections(data)
    story: list = [
        Paragraph(escape(title), _STYLES["title"]),
        Spacer(1, 3 * mm),
        Paragraph(
            f"Generated: {escape(data.generated_at.strftime('%Y-%m-%d %H:%M:%S'))} &nbsp;|&nbsp; "
            f"Device: {escape(data.device_id)}",
            _STYLES["meta"],
        ),
        *summary,
        PageBreak(),
        *_services_manifest_flowables(data.active_services, data.device_id),
        PageBreak(),
        *trace,
    ]
    doc.build(story, onFirstPage=_draw_page, onLaterPages=_draw_page)
    return path