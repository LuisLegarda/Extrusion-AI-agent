"""Página «Control»: activar y vigilar los lazos PID, aplicar propuestas (modo asistido) y ver lo aprendido."""
from __future__ import annotations

import time
from typing import Optional

import pyqtgraph as pg
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QDialog, QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

from ..control import MODE_LABELS
from ..i18n import tr, translate_text
from . import theme

LEVEL_COLORS = {0: "good_text", 1: "warning_text", 2: "critical"}
PLOT_S = 1800.0


def _f(v: Optional[float], dec: int = 3) -> str:
    return "—" if v is None else f"{v:.{dec}f}"


class LoopCard(QFrame):
    def __init__(self, page: "ControlPage", loop_id: str):
        super().__init__()
        self.page, self.loop_id = page, loop_id
        self.setObjectName("card")
        self.setFrameShape(QFrame.StyledPanel)
        lay = QVBoxLayout(self)
        top = QHBoxLayout()
        self.lbl_name = QLabel()
        top.addWidget(self.lbl_name, 1)
        top.addWidget(QLabel(tr("Modo:")))
        self.cmb_mode = QComboBox()
        for k, label in MODE_LABELS.items():
            self.cmb_mode.addItem(tr(label), k)
        self.cmb_mode.activated.connect(self._mode_changed)
        top.addWidget(self.cmb_mode)
        self.btn = QPushButton()
        self.btn.setMinimumWidth(150)
        self.btn.clicked.connect(self._toggle)
        top.addWidget(self.btn)
        lay.addLayout(top)
        self.lbl_status = QLabel()
        self.lbl_status.setWordWrap(True)
        lay.addWidget(self.lbl_status)
        grid = QGridLayout()
        self.vals = {}
        for col, (key, label) in enumerate((("pv", "Medición"), ("target", "Objetivo"), ("u", "Input en el HMI"))):
            t = QLabel(tr(label))
            t.setStyleSheet(f"color:{theme.c('muted')};")
            v = QLabel("—")
            v.setStyleSheet("font-size:20px; font-weight:bold;")
            grid.addWidget(t, 0, col)
            grid.addWidget(v, 1, col)
            self.vals[key] = v
        lay.addLayout(grid)
        self.prop = QWidget()
        pl = QHBoxLayout(self.prop)
        pl.setContentsMargins(0, 0, 0, 0)
        self.lbl_prop = QLabel()
        pl.addWidget(self.lbl_prop, 1)
        b = QPushButton(tr("✔ Aplicar"))
        b.clicked.connect(lambda: self.page.engine.control.accept_proposal(self.loop_id))
        pl.addWidget(b)
        b = QPushButton(tr("✗ Ignorar"))
        b.clicked.connect(lambda: self.page.engine.control.reject_proposal(self.loop_id))
        pl.addWidget(b)
        lay.addWidget(self.prop)
        self.plot = pg.PlotWidget(axisItems={"bottom": pg.DateAxisItem()})
        self.plot.setMinimumHeight(170)
        self.plot.showGrid(x=True, y=True, alpha=0.2)
        self.plot.addLegend(offset=(8, 8))
        self.c_pv = self.plot.plot(pen=pg.mkPen(theme.series(0), width=2),
                                   name=tr("Medición"))
        self.c_target = self.plot.plot(pen=pg.mkPen(theme.c("good_text"), width=1, style=Qt.DashLine), name=tr("Objetivo"))
        self.p2 = pg.ViewBox()
        self.plot.plotItem.showAxis("right")
        self.plot.plotItem.scene().addItem(self.p2)
        self.plot.plotItem.getAxis("right").linkToView(self.p2)
        self.p2.setXLink(self.plot.plotItem)
        self.c_u = pg.PlotCurveItem(pen=pg.mkPen(theme.series(1), width=2), stepMode=None)
        self.p2.addItem(self.c_u)
        self.plot.plotItem.legend.addItem(self.c_u, tr("Input (eje derecho)"))
        self.plot.plotItem.vb.sigResized.connect(lambda: self.p2.setGeometry(self.plot.plotItem.vb.sceneBoundingRect()))
        lay.addWidget(self.plot)
        self.lbl_model = QLabel()
        self.lbl_model.setWordWrap(True)
        self.lbl_model.setStyleSheet(f"color:{theme.c('muted')};")
        lay.addWidget(self.lbl_model)

    def _toggle(self) -> None:
        ctl = self.page.engine.control
        on = not ctl.state(self.loop_id).active
        lp = self.page.engine.config.control(self.loop_id)
        if on and lp is not None and lp.mode == "auto":
            from PySide6.QtWidgets import QMessageBox
            if QMessageBox.question(
                    self, tr("Activar control automático"),
                    tr("El programa va a cambiar «{i}» en el HMI dentro de los límites configurados "
                       "({lo} – {hi}).\n\n¿Activar?", i=lp.input_var, lo=_f(lp.u_min), hi=_f(lp.u_max))
            ) != QMessageBox.Yes:
                return
        ctl.set_active(self.loop_id, on)
        self.page.refresh()

    def _mode_changed(self) -> None:
        eng = self.page.engine
        lp = eng.config.control(self.loop_id)
        mode = self.cmb_mode.currentData()
        if lp is None or mode == lp.mode:
            return
        lp.mode = mode
        eng.control.set_active(self.loop_id, False)  # cambiar de modo desactiva: se vuelve a activar a propósito
        eng.workspace.save_config(eng.config)
        if self.page.on_config_changed:
            self.page.on_config_changed()
        self.page.refresh()

    def update(self, info: dict, now: float) -> None:
        eng = self.page.engine
        lp = eng.config.control(self.loop_id)
        if lp is None:
            return
        cfg = eng.config
        pv_var, in_var = cfg.variable(lp.pv_var or ""), cfg.variable(lp.input_var or "")
        self.lbl_name.setText(f"<b style='font-size:15px'>🎛 {lp.name}</b><br><span style='color:{theme.c('muted')}'>"
                              f"{cfg.var_label(pv_var) if pv_var else '—'} → {cfg.var_label(in_var) if in_var else '—'}"
                              f"</span>")
        self.cmb_mode.blockSignals(True)
        self.cmb_mode.setCurrentIndex(max(0, self.cmb_mode.findData(lp.mode)))
        self.cmb_mode.blockSignals(False)
        active = bool(info.get("active"))
        self.btn.setText(tr("■ Desactivar") if active else tr("▶ Activar"))
        self.btn.setStyleSheet("font-weight:bold;" + (f"background:{theme.c('critical')}; color:white;" if active else ""))
        color = theme.c(LEVEL_COLORS.get(info.get("level", 0), "muted")) if active else theme.c("muted")
        detail = info.get("detail") or ""
        self.lbl_status.setText(f"<b style='color:{color}'>{tr(info.get('status', ''))}</b>"
                                + (f" · {translate_text(detail)}" if detail else ""))
        dp = pv_var.decimals if pv_var and pv_var.decimals is not None else 3
        du = in_var.decimals if in_var and in_var.decimals is not None else 2
        self.vals["pv"].setText(_f(info.get("pv"), dp))
        self.vals["target"].setText(_f(info.get("target"), dp))
        self.vals["u"].setText(_f(info.get("u"), du))
        prop = info.get("proposal")
        self.prop.setVisible(bool(prop) and lp.mode == "assist")
        if prop:
            self.lbl_prop.setText(f"<b>{tr('Propuesta')}:</b> {_f(prop[0], du)} → <b>{_f(prop[1], du)}</b>")
        m = eng.control.model(eng.state.recipe, lp.id)
        s = m.summary()
        if s is None:
            self.lbl_model.setText(tr("Comportamiento aprendido: aún sin cambios del operador observados."))
        else:
            k, th, tau = s
            self.lbl_model.setText(tr("Comportamiento aprendido ({n} cambios): {k} por unidad de input · retardo "
                                      "{th} s · constante {tau} s", n=m.n, k=f"{k:+.4g}", th=f"{th:.0f}",
                                      tau=f"{tau:.0f}"))
        if self.isVisible():
            self._plot(lp, info, now)

    def _plot(self, lp, info, now) -> None:
        eng = self.page.engine
        for curve, vid in ((self.c_pv, lp.pv_var), (self.c_u, lp.input_var)):
            t, y = [], []
            if vid:
                try:
                    ts, ys = eng.series(vid)
                    pairs = [(a, b) for a, b in zip(ts, ys) if a >= now - PLOT_S]
                    t, y = [a for a, _ in pairs], [b for _, b in pairs]
                except Exception:
                    t, y = [], []
            curve.setData(t, y)
        tgt = info.get("target")
        self.c_target.setData([now - PLOT_S, now], [tgt, tgt] if tgt is not None else [None, None]) \
            if tgt is not None else self.c_target.setData([], [])


class ControlPage(QWidget):
    def __init__(self, ctx, on_config_changed=None):
        super().__init__()
        self.ctx = ctx
        self.engine = ctx.engine
        self.on_config_changed = on_config_changed
        lay = QVBoxLayout(self)
        top = QHBoxLayout()
        info = QLabel(tr("El control ajusta inputs del HMI con límites y paros de seguridad. Al abrir el programa "
                         "queda desactivado. Configura los lazos en Receta → Configurar receta → Control."))
        info.setWordWrap(True)
        top.addWidget(info, 1)
        b = QPushButton(tr("■ Detener todo el control"))
        b.setStyleSheet(f"background:{theme.c('critical')}; color:white; font-weight:bold; padding:8px 14px;")
        b.clicked.connect(self.stop_all)
        top.addWidget(b)
        lay.addLayout(top)
        self.empty = QLabel(tr("No hay lazos de control configurados."))
        self.empty.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.empty)
        self.area = QScrollArea()
        self.area.setWidgetResizable(True)
        self.inner = QWidget()
        self.inner_lay = QVBoxLayout(self.inner)
        self.inner_lay.addStretch()
        self.area.setWidget(self.inner)
        lay.addWidget(self.area, 1)
        self.cards: dict[str, LoopCard] = {}
        self.refresh()

    def stop_all(self) -> None:
        self.engine.control.stop_all()
        self.refresh()

    def rebuild(self) -> None:
        for c in self.cards.values():
            c.setParent(None)
            c.deleteLater()
        self.cards.clear()
        for lp in self.engine.config.controls:
            card = LoopCard(self, lp.id)
            self.inner_lay.insertWidget(self.inner_lay.count() - 1, card)
            self.cards[lp.id] = card
        self.empty.setVisible(not self.cards)
        self.area.setVisible(bool(self.cards))

    def refresh(self, snap=None) -> None:
        ids = [lp.id for lp in self.engine.config.controls]
        if ids != list(self.cards):
            self.rebuild()
        info = (snap.control if snap is not None else None) or self.engine.control.snapshot(self.engine.config)
        now = snap.ts if snap is not None else time.time()
        for lid, card in self.cards.items():
            card.update(info.get(lid, {}), now)


class ProposalPrompt(QDialog):
    """Aviso del modo asistido (aunque la ventana esté minimizada): aplicar o ignorar el ajuste propuesto."""

    def __init__(self, name: str, u_from: str, u_to: str, on_apply, on_ignore):
        super().__init__(None, Qt.Tool | Qt.WindowStaysOnTopHint)
        self.setWindowTitle(tr("Control: ajuste propuesto"))
        self.setAttribute(Qt.WA_DeleteOnClose)
        lay = QVBoxLayout(self)
        lbl = QLabel(tr("«{n}» propone cambiar el input<br><b>{a} → {b}</b>", n=name, a=u_from, b=u_to))
        lbl.setTextFormat(Qt.RichText)
        lay.addWidget(lbl)
        row = QHBoxLayout()
        ok = QPushButton(tr("✔ Aplicar"))
        ok.setDefault(True)
        ok.clicked.connect(lambda: (on_apply(), self.close()))
        no = QPushButton(tr("✗ Ignorar"))
        no.clicked.connect(lambda: (on_ignore(), self.close()))
        row.addWidget(ok)
        row.addWidget(no)
        lay.addLayout(row)
