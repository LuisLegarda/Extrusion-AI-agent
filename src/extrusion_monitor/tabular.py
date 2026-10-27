"""Exportación de tablas: CSV, Excel (.xlsx) y texto para software estadístico (Minitab y similares).

Las filas llevan valores nativos (texto, número, `datetime` o `None`) y cada formato los escribe a su manera:

* **CSV**: separado por «;» con coma decimal (como lo abre Excel en español); en inglés «,» y punto decimal.
* **Excel**: un .xlsx con números y fechas reales, encabezado en negrita, fila fija y filtro. Se escribe aquí
  mismo (es un ZIP con XML), sin dependencias adicionales.
* **Software estadístico**: texto separado por tabulaciones, punto decimal y sin separador de miles, «*» para
  los datos faltantes y nombres de columna válidos para Minitab (únicos, de hasta 31 caracteres, sin
  apóstrofos). Se pega directo en la hoja de Minitab (Ctrl+V) o se abre con Archivo › Abrir.
"""
from __future__ import annotations

import csv
import datetime as dt
import math
import re
import zipfile
from pathlib import Path
from typing import Iterable, Optional, Sequence
from xml.sax.saxutils import escape

FORMATS = {"csv": ("CSV", ".csv", "CSV (*.csv)"),
           "xlsx": ("Excel", ".xlsx", "Excel (*.xlsx)"),
           "stat": ("CSV para software estadístico (Minitab)", ".txt", "Texto separado por tabulaciones (*.txt)")}
MISSING_STAT = "*"  # dato faltante en Minitab
MAX_NAME = 31  # largo máximo de un nombre de columna en Minitab
_NUM = re.compile(r"^[-+]?\d+(\.\d+)?([eE][-+]?\d+)?$")


def _is_num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(float(v))


def _is_missing(v) -> bool:
    return v is None or v == "" or v == "—" or (isinstance(v, float) and not math.isfinite(v))


def _num_text(v, decimal: str = ".") -> str:
    if isinstance(v, int):
        return str(v)
    s = repr(float(v))
    if s.endswith(".0"):
        s = s[:-2]
    return s.replace(".", decimal) if decimal != "." else s


def _date_text(v: dt.datetime) -> str:
    return v.strftime("%Y-%m-%d %H:%M:%S")


def coerce(v):
    """Convierte valores de numpy y textos numéricos con punto («3.25») a números nativos."""
    if hasattr(v, "item") and not isinstance(v, (str, bytes)):  # numpy
        v = v.item()
    if isinstance(v, str):
        s = v.strip()
        if _NUM.match(s) and not re.match(r"[-+]?0\d", s):  # «007» es un código, no un número
            return int(s) if re.fullmatch(r"[-+]?\d+", s) else float(s)
    return v


# --- CSV ----------------------------------------------------------------------------------------------
def write_csv(path, header: Sequence[str], rows: Iterable[Sequence], lang: str = "es") -> int:
    delim, decimal = (";", ",") if lang == "es" else (",", ".")
    n = 0
    with open(path, "w", newline="", encoding="utf-8-sig") as f:  # con BOM: Excel abre bien los acentos
        w = csv.writer(f, delimiter=delim)
        w.writerow(list(header))
        for r in rows:
            out = []
            for v in r:
                v = coerce(v)
                if _is_missing(v):
                    out.append("")
                elif isinstance(v, dt.datetime):
                    out.append(_date_text(v))
                elif _is_num(v):
                    out.append(_num_text(v, decimal))
                else:
                    out.append(str(v))
            w.writerow(out)
            n += 1
    return n


# --- software estadístico (Minitab) -------------------------------------------------------------------
def stat_names(header: Sequence[str]) -> list[str]:
    """Nombres de columna válidos y únicos para Minitab."""
    out: list[str] = []
    seen: set[str] = set()
    for i, h in enumerate(header):
        name = re.sub(r"[\t\r\n']", " ", str(h)).replace("#", "No.").strip().lstrip("*").strip()
        name = re.sub(r"\s+", " ", name)[:MAX_NAME].strip() or f"C{i + 1}"
        base, k = name, 2
        while name.lower() in seen:
            suffix = f"_{k}"
            name = base[:MAX_NAME - len(suffix)] + suffix
            k += 1
        seen.add(name.lower())
        out.append(name)
    return out


def stat_text(header: Sequence[str], rows: Iterable[Sequence]) -> str:
    lines = ["\t".join(stat_names(header))]
    for r in rows:
        out = []
        for v in r:
            v = coerce(v)
            if _is_missing(v):
                out.append(MISSING_STAT)
            elif isinstance(v, dt.datetime):
                out.append(_date_text(v))
            elif _is_num(v):
                out.append(_num_text(v))
            else:
                out.append(re.sub(r"[\t\r\n]+", " ", str(v)).strip())
        lines.append("\t".join(out))
    return "\r\n".join(lines) + "\r\n"


def write_stat(path, header: Sequence[str], rows: Iterable[Sequence]) -> int:
    text = stat_text(header, rows)
    Path(path).write_text(text, encoding="utf-8-sig", newline="")
    return text.count("\r\n") - 1


# --- Excel (.xlsx) ------------------------------------------------------------------------------------
_EPOCH = dt.datetime(1899, 12, 30)
_XML_BAD = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f]")


def _col(i: int) -> str:
    s = ""
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


def _cell(ref: str, v, header: bool = False) -> str:
    v = coerce(v)
    if _is_missing(v):
        return ""
    if isinstance(v, dt.datetime):
        serial = (v.replace(tzinfo=None) - _EPOCH).total_seconds() / 86400
        return f'<c r="{ref}" s="2"><v>{serial:.8f}</v></c>'
    if _is_num(v) and not header:
        return f'<c r="{ref}"><v>{_num_text(v)}</v></c>'
    text = escape(_XML_BAD.sub("", str(v)))
    style = ' s="1"' if header else ""
    return f'<c r="{ref}" t="inlineStr"{style}><is><t xml:space="preserve">{text}</t></is></c>'


def write_xlsx(path, header: Sequence[str], rows: Iterable[Sequence], sheet: str = "Datos") -> int:
    rows = [list(r) for r in rows]
    ncols = max([len(header)] + [len(r) for r in rows]) if (rows or header) else 1
    widths = [len(str(h)) for h in header] + [0] * (ncols - len(header))
    body = []
    for ri, r in enumerate([list(header)] + rows):
        cells = []
        for ci, v in enumerate(r):
            cells.append(_cell(f"{_col(ci)}{ri + 1}", v, header=ri == 0))
            if ri and ri <= 200:  # ancho de columna según las primeras filas
                widths[ci] = max(widths[ci], 19 if isinstance(v, dt.datetime) else len(str(v)))
        body.append(f'<row r="{ri + 1}">{"".join(cells)}</row>')
    cols = "".join(f'<col min="{i + 1}" max="{i + 1}" width="{min(60, max(8, w + 2))}" customWidth="1"/>'
                   for i, w in enumerate(widths))
    last = f"{_col(ncols - 1)}{len(rows) + 1}"
    ws = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
          '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
          '<sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" '
          'state="frozen"/></sheetView></sheetViews>'
          f'<cols>{cols}</cols><sheetData>{"".join(body)}</sheetData>'
          f'<autoFilter ref="A1:{last}"/></worksheet>')
    name = escape(re.sub(r"[\[\]:*?/\\]", " ", sheet)[:31] or "Datos")
    files = {
        "[Content_Types].xml":
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            '<Override PartName="/xl/worksheets/sheet1.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            '<Override PartName="/xl/styles.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/></Types>',
        "_rels/.rels":
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/'
            'officeDocument" Target="xl/workbook.xml"/></Relationships>',
        "xl/workbook.xml":
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            f'<sheets><sheet name="{name}" sheetId="1" r:id="rId1"/></sheets>'
            '<definedNames><definedName name="_xlnm._FilterDatabase" localSheetId="0" hidden="1">'
            f"'{name}'!$A$1:${_col(ncols - 1)}${len(rows) + 1}</definedName></definedNames></workbook>",
        "xl/_rels/workbook.xml.rels":
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/'
            'worksheet" Target="worksheets/sheet1.xml"/>'
            '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/'
            'styles" Target="styles.xml"/></Relationships>',
        "xl/styles.xml":
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            '<numFmts count="1"><numFmt numFmtId="164" formatCode="yyyy\\-mm\\-dd hh:mm:ss"/></numFmts>'
            '<fonts count="2"><font><sz val="11"/><name val="Calibri"/></font>'
            '<font><b/><sz val="11"/><name val="Calibri"/></font></fonts>'
            '<fills count="2"><fill><patternFill patternType="none"/></fill>'
            '<fill><patternFill patternType="gray125"/></fill></fills>'
            '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
            '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
            '<cellXfs count="3"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
            '<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/>'
            '<xf numFmtId="164" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/></cellXfs>'
            '</styleSheet>',
        "xl/worksheets/sheet1.xml": ws,
    }
    tmp = Path(str(path) + ".tmp")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        for arc, data in files.items():
            z.writestr(arc, data)
    tmp.replace(path)
    return len(rows)


# --- entrada única ------------------------------------------------------------------------------------
def write_table(path, header: Sequence[str], rows: Iterable[Sequence], fmt: str = "csv", lang: str = "es",
                sheet: str = "Datos") -> int:
    """Escribe la tabla en el formato pedido («csv», «xlsx» o «stat») y devuelve cuántas filas escribió."""
    if fmt == "xlsx":
        return write_xlsx(path, header, rows, sheet)
    if fmt == "stat":
        return write_stat(path, header, rows)
    return write_csv(path, header, rows, lang)


def with_suffix(path: str, fmt: str) -> str:
    ext = FORMATS[fmt][1]
    p = Path(path)
    return str(p if p.suffix.lower() == ext else p.with_suffix(ext))


def epoch(ts: Optional[float]) -> Optional[dt.datetime]:
    """Fecha y hora local de un instante (para las columnas de fecha)."""
    return dt.datetime.fromtimestamp(ts).replace(microsecond=0) if ts else None
