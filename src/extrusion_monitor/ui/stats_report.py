"""Reporte PDF de análisis estadísticos y análisis programados (cada turno, día o semana).

El reporte junta varios análisis del navegador (gráficas, tablas e interpretación) en un PDF para juntas o
auditorías. Los análisis programados se recalculan solos con el periodo que acaba de terminar (turno, día o
semana anterior) y su PDF se guarda en la carpeta de reportes; si está activado, también se envía por correo.
"""
from __future__ import annotations

import copy
import datetime as dt
import logging
import tempfile
import time
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication, QDialog, QDialogButtonBox, QFileDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QVBoxLayout,
)

from ..i18n import tr
from .stats_page import SCHEDULES, build_render, default_title, load_schedule_state, save_project, subtitle

log = logging.getLogger(__name__)
RENDER_W = 1100


def _latin(text: str) -> str:
    from ..reports import _latin as latin
    return latin(text)


def _esc(text: str) -> str:
    from ..reports import _esc as esc
    return esc(text)


def grab_widget(w, width: int = RENDER_W):
    """Imagen completa de un widget aunque no esté en pantalla."""
    w.setAttribute(Qt.WA_DontShowOnScreen, True)
    w.resize(width, max(400, w.sizeHint().height()))
    w.show()
    QApplication.processEvents()
    w.resize(width, max(400, w.sizeHint().height()))
    QApplication.processEvents()
    img = w.grab().toImage()
    w.hide()
    return img


def write_images_pdf(sections: list[tuple[str, str, object]], path: Path, title: str, where: str = "") -> Path:
    """PDF A4 con un título y, por sección, su encabezado, subtítulo y la imagen a lo ancho (partida por página)."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Image, PageBreak, Paragraph, SimpleDocTemplate, Spacer

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    styles = getSampleStyleSheet()
    h1, h2 = styles["Title"], styles["Heading2"]
    small = styles["BodyText"].clone("small", fontSize=8, leading=10, textColor=colors.HexColor("#52514e"))
    page_w, page_h = A4
    margin = 14 * mm
    avail_w, avail_h = page_w - 2 * margin, page_h - 2 * margin - 30 * mm
    story = [Paragraph(_esc(title), h1),
             Paragraph(_esc(" · ".join(x for x in (where, time.strftime("%d/%m/%Y %H:%M")) if x)), small),
             Spacer(1, 6 * mm)]
    tmp = Path(tempfile.mkdtemp(prefix="reporte_"))
    for k, (head, sub, img) in enumerate(sections):
        if head:
            story.append(Paragraph(_esc(head), h2))
        if sub:
            story.append(Paragraph(_esc(sub), small))
        story.append(Spacer(1, 2 * mm))
        scale = avail_w / img.width()
        chunk = int(avail_h / scale)
        y = part = 0
        while y < img.height():
            h = min(chunk, img.height() - y)
            f = tmp / f"s{k}_{part}.png"
            img.copy(0, y, img.width(), h).save(str(f))
            story.append(Image(str(f), width=avail_w, height=h * scale))
            y += h
            part += 1
            if y < img.height():
                story.append(PageBreak())
        if k < len(sections) - 1:
            story.append(PageBreak())
    SimpleDocTemplate(str(path), pagesize=A4, leftMargin=margin, rightMargin=margin, topMargin=margin,
                      bottomMargin=margin, title=_latin(title)).build(story)
    return path


def write_pdf(ctx, records: list[dict], path: Path, title: str, where: str = "") -> Path:
    """Calcula cada análisis y lo pone en el PDF (imagen de gráficas y tablas, a lo ancho de la hoja)."""
    sections = []
    for rec in records:
        R, n = build_render(ctx, rec)
        img = grab_widget(R)
        R.deleteLater()
        sections.append((rec.get("title") or default_title(rec, ctx.engine.config),
                         subtitle(rec) + (f" · {n:,} {tr('datos')}" if n else ""), img))
    return write_images_pdf(sections, path, title, where)


class ReportDialog(QDialog):
    """Elegir qué análisis van en el reporte PDF."""

    def __init__(self, records: list[dict], config, selected: Optional[int] = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Reporte PDF de análisis"))
        self.resize(560, 520)
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(tr("Análisis que van en el reporte (en este orden):")))
        self.lst = QListWidget()
        for i, r in enumerate(records):
            it = QListWidgetItem(r.get("title") or default_title(r, config))
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Checked if selected is None or i == selected else Qt.Unchecked)
            it.setData(Qt.UserRole, i)
            self.lst.addItem(it)
        lay.addWidget(self.lst, 1)
        lay.addWidget(QLabel(tr("Título del reporte")))
        self.ed_title = QLineEdit(tr("Reporte de análisis estadístico"))
        lay.addWidget(self.ed_title)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText(tr("Generar PDF"))
        bb.button(QDialogButtonBox.Cancel).setText(tr("Cancelar"))
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def chosen(self) -> list[int]:
        return [self.lst.item(i).data(Qt.UserRole) for i in range(self.lst.count())
                if self.lst.item(i).checkState() == Qt.Checked]


def export_dialog(page) -> Optional[Path]:
    if not page.records:
        return None
    dlg = ReportDialog(page.records, page.engine.config, page.lst.currentRow() if page.lst.currentRow() >= 0 else None,
                       page)
    if not dlg.exec() or not dlg.chosen():
        return None
    name = time.strftime("Analisis_%Y%m%d_%H%M.pdf")
    path, _ = QFileDialog.getSaveFileName(page, tr("Guardar reporte PDF"),
                                          str(page.ctx.workspace.default_reports_dir() / name), "PDF (*.pdf)")
    if not path:
        return None
    QApplication.setOverrideCursor(Qt.WaitCursor)
    try:
        out = write_pdf(page.ctx, [page.records[i] for i in dlg.chosen()], Path(path), dlg.ed_title.text().strip()
                        or tr("Reporte de análisis estadístico"), page.where())
    finally:
        QApplication.restoreOverrideCursor()
    return out


# --- análisis programados --------------------------------------------------------------------------


def period_start(freq: str, now: float, shift_starts: list[str]) -> float:
    from ..analysis.oee import shift_start
    if freq == "shift":
        return shift_start(now, shift_starts)
    d = dt.datetime.fromtimestamp(now).replace(hour=0, minute=0, second=0, microsecond=0)
    if freq == "week":
        d -= dt.timedelta(days=d.weekday())
    return d.timestamp()


def shift_starts_for(ctx) -> list[str]:
    """Inicios de turno: los de Configuración → Personal (si hay) o los del OEE."""
    from ..personnel import Personnel
    shifts = Personnel.load(ctx.workspace.home).shifts
    return [s.start for s in shifts] if shifts else list(ctx.engine.config.oee.shift_starts)


def run_due(page, now: Optional[float] = None) -> list[Path]:
    """Genera los reportes programados cuyo periodo acaba de terminar. Devuelve los PDF creados."""
    ctx = page.ctx
    now = now if now is not None else ctx.engine.clock()
    state = load_schedule_state(page.home)
    starts = shift_starts_for(ctx)
    made = []
    changed = False
    for freq, label in SCHEDULES[1:]:
        recs = [r for r in page.records if r.get("schedule") == freq]
        cur = period_start(freq, now, starts)
        last = state.get(freq)
        if last is None or not recs:
            if state.get(freq) != cur:
                state[freq] = cur  # sin generar hacia atrás la primera vez
                changed = True
            continue
        if float(last) >= cur:
            continue
        prev = period_start(freq, cur - 1, starts)
        state[freq] = cur
        changed = True
        jobs = []
        for r in recs:
            r2 = copy.deepcopy(r)
            r2["params"]["since"], r2["params"]["until"] = prev, cur
            jobs.append(r2)
        stamp = time.strftime("%Y%m%d_%H%M", time.localtime(prev))
        title = tr("Análisis programado — {f}", f=tr(label).split(" (")[0].lower()) + " · " + \
            time.strftime("%d/%m/%Y %H:%M", time.localtime(prev)) + " → " + time.strftime("%d/%m %H:%M", time.localtime(cur))
        out_dir = ctx.workspace.default_reports_dir() / "analisis"
        try:
            path = write_pdf(ctx, jobs, out_dir / f"Analisis_{freq}_{stamp}.pdf", title, page.where())
        except Exception:
            log.exception("reporte de análisis programado")
            continue
        made.append(path)
        if ctx.engine.historian is not None:
            from ..analysis.rules import Level
            ctx.engine.historian.write_events([(time.time(), "report", int(Level.INFO), "ANÁLISIS", "",
                                                f"Reporte de análisis programado: {path.name}",
                                                ctx.engine.state.recipe)])
        notifier = getattr(ctx, "notifier", None)
        if notifier is not None:
            notifier.report_ready(path, title)
    if changed:
        save_project(page.home, page.records, state)
    return made
