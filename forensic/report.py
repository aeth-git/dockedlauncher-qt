"""Report generator — HTML and PDF (via weasyprint or browser print)."""
import datetime
import os
from pathlib import Path
from typing import Dict, List, Optional

from .logger import get_logger

_log = get_logger("report")


def generate_html_report(
    device_info: dict,
    source_path: str,
    manifest_hash: Optional[str],
    sections: Dict[str, List[dict]],
    examiner: str = "",
    case_number: str = "",
    notes: str = "",
) -> str:
    """Return a full HTML report string."""
    now = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    examiner = examiner or os.environ.get("USER", os.environ.get("USERNAME", "Unknown"))

    rows_html = _device_table(device_info, source_path, manifest_hash,
                              now, examiner, case_number)
    sections_html = ""
    for section_name, records in sections.items():
        if not records:
            continue
        sections_html += _section_table(section_name, records)

    return _HTML_TEMPLATE.format(
        title="iForensic Examination Report",
        generated=now,
        case_number=case_number or "—",
        device_rows=rows_html,
        sections=sections_html,
        notes=_escape(notes) if notes else "",
    )


def _device_table(device_info, source_path, manifest_hash,
                  now, examiner, case_number) -> str:
    rows = [
        ("Examiner", _escape(examiner)),
        ("Case Number", _escape(case_number or "—")),
        ("Report Generated", now),
        ("Source Path", _escape(source_path)),
        ("Manifest SHA256", _escape(manifest_hash or "N/A")),
        ("Device Name", _escape(device_info.get("name", ""))),
        ("iOS Version", _escape(device_info.get("ios_version", ""))),
        ("Serial Number", _escape(device_info.get("serial", ""))),
        ("IMEI", _escape(device_info.get("imei", ""))),
        ("UDID", _escape(device_info.get("udid", ""))),
    ]
    return "".join(
        f"<tr><th>{k}</th><td>{v}</td></tr>" for k, v in rows
    )


def _section_table(name: str, records: List[dict]) -> str:
    if not records:
        return ""
    keys = list(records[0].keys())
    # Skip internal keys
    keys = [k for k in keys if not k.startswith("_")]

    header = "".join(f"<th>{_escape(k)}</th>" for k in keys)
    body_rows = []
    for rec in records[:5000]:   # cap per section for HTML size
        cells = "".join(
            f"<td>{_escape(str(rec.get(k, '') or ''))}</td>" for k in keys
        )
        body_rows.append(f"<tr>{cells}</tr>")

    count = len(records)
    note = f" <span class='count'>({count:,} records{', showing first 5,000' if count > 5000 else ''})</span>"
    return f"""
<section>
  <h2>{_escape(name)}{note}</h2>
  <table>
    <thead><tr>{header}</tr></thead>
    <tbody>{"".join(body_rows)}</tbody>
  </table>
</section>
"""


def _escape(text: str) -> str:
    return (text
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;"))


_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>{title}</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: "Helvetica Neue", Helvetica, Arial, sans-serif;
    font-size: 11px;
    color: #0a0a0a;
    background: #fff;
    padding: 32px 40px;
  }}
  h1 {{ font-size: 18px; font-weight: 300; margin-bottom: 4px; }}
  h2 {{ font-size: 12px; font-weight: 600; text-transform: uppercase;
        letter-spacing: 0.08em; color: #8a8a8a; margin: 28px 0 8px; }}
  .meta {{ color: #8a8a8a; font-size: 10px; margin-bottom: 24px; }}
  .red {{ color: #e30613; }}
  .count {{ font-weight: 400; color: #8a8a8a; font-size: 10px; }}
  table {{ width: 100%; border-collapse: collapse; margin-bottom: 16px; }}
  th, td {{ padding: 6px 10px; text-align: left;
            border-bottom: 1px solid #e5e5e5; vertical-align: top; }}
  th {{ background: #fafafa; color: #8a8a8a; font-size: 9px;
        font-weight: 600; text-transform: uppercase; letter-spacing: 0.08em; }}
  tr:hover td {{ background: #f2f2f2; }}
  .device-table th {{ width: 180px; }}
  section {{ page-break-inside: avoid; }}
  .notes {{ background: #fafafa; border: 1px solid #e5e5e5;
            padding: 12px 16px; margin-top: 24px; white-space: pre-wrap; }}
  @media print {{
    body {{ padding: 16px; }}
    h2 {{ page-break-after: avoid; }}
    table {{ page-break-inside: auto; }}
    tr {{ page-break-inside: avoid; page-break-after: auto; }}
  }}
</style>
</head>
<body>
<h1>iForensic <span class="red">·</span> Examination Report</h1>
<p class="meta">Case: {case_number} &nbsp;·&nbsp; Generated: {generated}</p>

<h2>Device &amp; Case Information</h2>
<table class="device-table">
  <tbody>{device_rows}</tbody>
</table>

{sections}

{notes_block}
</body>
</html>
""".replace("{notes_block}",
            '<div class="notes"><strong>Examiner Notes</strong><br>{notes}</div>'
            if "{notes}" else "")


def export_html(path: str, **kwargs) -> None:
    html = generate_html_report(**kwargs)
    Path(path).write_text(html, encoding="utf-8")
    _log.info("HTML report written to %s", path)


def export_pdf(path: str, **kwargs) -> None:
    """Export PDF via weasyprint if available, otherwise open HTML in browser."""
    html = generate_html_report(**kwargs)
    tmp_html = path.replace(".pdf", "_report_tmp.html")
    Path(tmp_html).write_text(html, encoding="utf-8")
    try:
        from weasyprint import HTML
        HTML(filename=tmp_html).write_pdf(path)
        os.unlink(tmp_html)
        _log.info("PDF report written to %s", path)
    except ImportError:
        _log.info("weasyprint not installed — opening HTML in browser instead")
        import webbrowser
        webbrowser.open(f"file://{os.path.abspath(tmp_html)}")
