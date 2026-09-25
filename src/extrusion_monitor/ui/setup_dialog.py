"""Asistente de configuración: páginas del HMI, variables, regiones y OCR."""
from __future__ import annotations

import re
from typing import Optional

import numpy as np
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFileDialog,
    QFormLayout, QGroupBox, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QMessageBox, QPushButton, QScrollArea, QSpinBox, QSplitter, QTabWidget, QVBoxLayout, QWidget,
)

from ..bootstrap import AppContext
from ..capture import ImageFileSource, ScreenSource, crop, load_png, save_png
from ..config import AppConfig, OcrOptions, Page, Rect, Variable
from ..ocr import OcrUnavailable, TemplateOcr, create_engine, parse_number, preprocess
from ..pages import PageDetector
from .common import to_pixmap
from .region_view import RegionView

KIND_COLORS = {"actual": "#66bb6a", "setpoint": "#42a5f5", "text": "#ab47bc"}
PAGE_COLOR = "#ffa726"
KINDS = [("actual", "Valor real"), ("setpoint", "Consigna / ajuste"), ("text", "Texto (p. ej. nombre de receta)")]


def _opt_float(text: str) -> Optional[float]:
    text = text.strip().replace(",", ".")
    return float(text) if text else None


def _slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9_]+", "_", text.lower()).strip("_")
    return s or "var"


class SetupDialog(QDialog):
    def __init__(self, ctx: AppContext, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Configuración de variables y lectura del HMI")
        self.resize(1500, 900)
        self.ctx = ctx
        self.config: AppConfig = ctx.config.model_copy(deep=True)
        self.frame: Optional[np.ndarray] = None
        self.anchors: dict[str, np.ndarray] = {}
        for p in self.config.pages:
            img = load_png(ctx.workspace.page_anchor_file(p.id))
            if img is not None:
                self.anchors[p.id] = img
        self.removed_pages: set[str] = set()
        self._loading = False
        self._current_var: Optional[str] = None
        self._current_page: Optional[str] = None
        self._ocr_cache = None
        self._build()
        self._load_general()
        self._refresh_pages()
        self._refresh_vars()
        try:
            self._set_frame(ctx.engine.grab_frame())
        except Exception:
            pass

    # --- construcción ----------------------------------------------------------
    def _build(self) -> None:
        root = QVBoxLayout(self)
        split = QSplitter(Qt.Horizontal)
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        bar = QHBoxLayout()
        b = QPushButton("📷 Capturar pantalla del HMI")
        b.clicked.connect(self.capture_hmi)
        bar.addWidget(b)
        b = QPushButton("Abrir imagen…")
        b.clicked.connect(self.load_image)
        bar.addWidget(b)
        b = QPushButton("Guardar captura…")
        b.clicked.connect(self.save_image)
        bar.addWidget(b)
        b = QPushButton("Ajustar vista")
        b.clicked.connect(lambda: self.view.fit())
        bar.addWidget(b)
        bar.addStretch()
        ll.addLayout(bar)
        hint = QLabel("Arrastra con el botón izquierdo para marcar una región · rueda = zoom · "
                      "botón central = desplazar · clic en una región para seleccionarla")
        hint.setStyleSheet("color:#9e9e9e;")
        ll.addWidget(hint)
        self.view = RegionView()
        self.view.rectDrawn.connect(self._rect_drawn)
        self.view.regionClicked.connect(self._region_clicked)
        ll.addWidget(self.view)
        split.addWidget(left)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_vars_tab(), "Variables")
        self.tabs.addTab(self._build_pages_tab(), "Páginas del HMI")
        self.tabs.addTab(self._build_general_tab(), "General")
        split.addWidget(self.tabs)
        split.setSizes([950, 550])
        root.addWidget(split)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText("Guardar")
        buttons.button(QDialogButtonBox.Cancel).setText("Cancelar")
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _build_general_tab(self) -> QWidget:
        w = QWidget()
        f = QFormLayout(w)
        self.ed_machine = QLineEdit()
        f.addRow("Nombre de la máquina", self.ed_machine)
        self.sp_monitor = QSpinBox()
        self.sp_monitor.setRange(0, 8)
        self.sp_monitor.setToolTip("1 = monitor principal, 0 = todos los monitores")
        f.addRow("Monitor a capturar", self.sp_monitor)
        self.sp_interval = QDoubleSpinBox()
        self.sp_interval.setRange(0.2, 60)
        self.sp_interval.setSuffix(" s")
        f.addRow("Intervalo de muestreo", self.sp_interval)
        self.cmb_engine = QComboBox()
        for key, label in (("windows", "OCR de Windows (recomendado)"),
                           ("template", "Plantillas enseñadas (más preciso para fuentes fijas)"),
                           ("tesseract", "Tesseract (requiere tesseract.exe)")):
            self.cmb_engine.addItem(label, key)
        self.cmb_engine.currentIndexChanged.connect(lambda _: setattr(self, "_ocr_cache", None))
        f.addRow("Motor OCR", self.cmb_engine)
        self.ed_tess = QLineEdit()
        self.ed_tess.setPlaceholderText("Ruta a tesseract.exe (opcional)")
        f.addRow("Tesseract", self.ed_tess)
        self.sp_debounce = QSpinBox()
        self.sp_debounce.setRange(1, 50)
        self.sp_debounce.setSuffix(" ciclos")
        f.addRow("Confirmación de hallazgos", self.sp_debounce)
        self.sp_readfail = QSpinBox()
        self.sp_readfail.setRange(1, 100)
        self.sp_readfail.setSuffix(" ciclos")
        f.addRow("Fallos de lectura para avisar", self.sp_readfail)
        self.sp_stale = QDoubleSpinBox()
        self.sp_stale.setRange(1, 3600)
        self.sp_stale.setSuffix(" s")
        f.addRow("Dato viejo después de", self.sp_stale)
        self.sp_window = QDoubleSpinBox()
        self.sp_window.setRange(1, 240)
        self.sp_window.setSuffix(" min")
        f.addRow("Ventana de tendencia", self.sp_window)
        self.sp_horizon = QDoubleSpinBox()
        self.sp_horizon.setRange(0.5, 240)
        self.sp_horizon.setSuffix(" min")
        f.addRow("Horizonte de predicción", self.sp_horizon)
        self.sp_subgroup = QDoubleSpinBox()
        self.sp_subgroup.setRange(1, 600)
        self.sp_subgroup.setSuffix(" s")
        f.addRow("Subgrupo SPC", self.sp_subgroup)
        self.cmb_recipe_var = QComboBox()
        f.addRow("Variable con nombre de receta", self.cmb_recipe_var)
        self.chk_beep = QCheckBox("Sonido al activarse una alarma")
        f.addRow("", self.chk_beep)
        return w

    def _build_pages_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.addWidget(QLabel("Si el HMI tiene varias pantallas, define una imagen ancla (p. ej. el título) "
                             "para cada una. Las variables de una página solo se leen cuando está visible."))
        self.lst_pages = QListWidget()
        self.lst_pages.currentItemChanged.connect(self._page_selected)
        lay.addWidget(self.lst_pages)
        row = QHBoxLayout()
        for text, slot in (("Nueva desde selección", self._new_page), ("Eliminar", self._delete_page)):
            b = QPushButton(text)
            b.clicked.connect(slot)
            row.addWidget(b)
        lay.addLayout(row)
        box = QGroupBox("Página seleccionada")
        f = QFormLayout(box)
        self.ed_page_name = QLineEdit()
        self.ed_page_name.editingFinished.connect(self._commit_page)
        f.addRow("Nombre", self.ed_page_name)
        self.sp_page_thr = QDoubleSpinBox()
        self.sp_page_thr.setRange(0.3, 1.0)
        self.sp_page_thr.setSingleStep(0.05)
        self.sp_page_thr.valueChanged.connect(self._commit_page)
        f.addRow("Umbral de coincidencia", self.sp_page_thr)
        self.lbl_page_anchor = QLabel()
        f.addRow("Ancla", self.lbl_page_anchor)
        b = QPushButton("Reemplazar ancla con la selección")
        b.clicked.connect(self._replace_anchor)
        f.addRow("", b)
        self.lbl_page_score = QLabel()
        b = QPushButton("Probar en la captura")
        b.clicked.connect(self._test_page)
        f.addRow(b, self.lbl_page_score)
        lay.addWidget(box)
        return w

    def _build_vars_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        self.lst_vars = QListWidget()
        self.lst_vars.currentItemChanged.connect(self._var_selected)
        lay.addWidget(self.lst_vars, 2)
        row = QHBoxLayout()
        for text, slot in (("Nueva desde selección", self._new_var), ("Duplicar", self._dup_var),
                           ("Eliminar", self._delete_var)):
            b = QPushButton(text)
            b.clicked.connect(slot)
            row.addWidget(b)
        lay.addLayout(row)

        box = QGroupBox("Variable seleccionada")
        f = QFormLayout(box)
        self.ed_id = QLineEdit()
        self.ed_name = QLineEdit()
        self.ed_unit = QLineEdit()
        self.ed_group = QLineEdit()
        self.cmb_kind = QComboBox()
        for k, label in KINDS:
            self.cmb_kind.addItem(label, k)
        self.cmb_page = QComboBox()
        self.cmb_sp = QComboBox()
        self.sp_dec = QSpinBox()
        self.sp_dec.setRange(-1, 6)
        self.sp_dec.setSpecialValueText("libre")
        self.cmb_sep = QComboBox()
        for k, label in (("auto", "automático"), (".", "punto"), (",", "coma")):
            self.cmb_sep.addItem(label, k)
        self.chk_fixdec = QCheckBox("Reinsertar punto decimal si el OCR lo pierde")
        self.ed_vmin = QLineEdit()
        self.ed_vmax = QLineEdit()
        self.ed_step = QLineEdit()
        for e in (self.ed_vmin, self.ed_vmax, self.ed_step):
            e.setPlaceholderText("sin límite")
        self.cmb_invert = QComboBox()
        for k, label in (("auto", "automático"), ("yes", "texto claro sobre fondo oscuro"),
                         ("no", "texto oscuro sobre fondo claro")):
            self.cmb_invert.addItem(label, k)
        self.sp_scale = QDoubleSpinBox()
        self.sp_scale.setRange(1, 8)
        self.sp_scale.setSingleStep(0.5)
        self.sp_thr = QSpinBox()
        self.sp_thr.setRange(-1, 255)
        self.sp_thr.setSpecialValueText("auto")
        self.chk_trend = QCheckBox("Analizar tendencia")
        self.lbl_region = QLabel()
        f.addRow("ID", self.ed_id)
        f.addRow("Nombre", self.ed_name)
        f.addRow("Unidad", self.ed_unit)
        f.addRow("Grupo", self.ed_group)
        f.addRow("Tipo", self.cmb_kind)
        f.addRow("Página", self.cmb_page)
        f.addRow("Consigna asociada", self.cmb_sp)
        f.addRow("Decimales", self.sp_dec)
        f.addRow("Separador decimal", self.cmb_sep)
        f.addRow("", self.chk_fixdec)
        f.addRow("Valor mínimo válido", self.ed_vmin)
        f.addRow("Valor máximo válido", self.ed_vmax)
        f.addRow("Salto máx. entre lecturas", self.ed_step)
        f.addRow("Contraste", self.cmb_invert)
        f.addRow("Escala OCR", self.sp_scale)
        f.addRow("Umbral binario", self.sp_thr)
        f.addRow("", self.chk_trend)
        f.addRow("Región", self.lbl_region)
        for wdg in (self.ed_id, self.ed_name, self.ed_unit, self.ed_group, self.ed_vmin, self.ed_vmax,
                    self.ed_step):
            wdg.editingFinished.connect(self._commit_var)
        for wdg in (self.cmb_kind, self.cmb_page, self.cmb_sp, self.cmb_sep, self.cmb_invert):
            wdg.currentIndexChanged.connect(self._commit_var)
        for wdg in (self.sp_dec, self.sp_scale, self.sp_thr):
            wdg.valueChanged.connect(self._commit_var)
        for wdg in (self.chk_fixdec, self.chk_trend):
            wdg.toggled.connect(self._commit_var)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(box)
        lay.addWidget(scroll, 3)

        test = QGroupBox("Prueba de lectura")
        tl = QVBoxLayout(test)
        row = QHBoxLayout()
        for text, slot in (("Asignar selección como región", self._assign_region),
                           ("Probar OCR", self._test_ocr), ("Enseñar caracteres…", self._teach)):
            b = QPushButton(text)
            b.clicked.connect(slot)
            row.addWidget(b)
        tl.addLayout(row)
        prev = QHBoxLayout()
        self.lbl_crop = QLabel()
        self.lbl_bin = QLabel()
        for lbl in (self.lbl_crop, self.lbl_bin):
            lbl.setMinimumHeight(50)
            lbl.setAlignment(Qt.AlignCenter)
            lbl.setStyleSheet("border:1px solid #555;")
            prev.addWidget(lbl)
        tl.addLayout(prev)
        self.lbl_result = QLabel()
        self.lbl_result.setWordWrap(True)
        tl.addWidget(self.lbl_result)
        lay.addWidget(test, 1)
        return w

    # --- imagen -------------------------------------------------------------------
    def _set_frame(self, frame: np.ndarray) -> None:
        self.frame = frame
        self.view.set_image(frame)
        self._redraw()
        QTimer.singleShot(0, self.view.fit)

    def capture_hmi(self) -> None:
        if self.ctx.demo:
            self._set_frame(self.ctx.engine.grab_frame())
            return
        tops = [w for w in QApplication.topLevelWidgets() if w.isVisible()]
        for w in tops:
            w.hide()

        def grab():
            try:
                frame = ScreenSource(self.sp_monitor.value()).grab()
            finally:
                for w in tops:
                    w.show()
            self._set_frame(frame)

        QTimer.singleShot(800, grab)

    def load_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Abrir captura del HMI", "", "Imágenes (*.png *.jpg *.bmp)")
        if path:
            try:
                self._set_frame(ImageFileSource(path).grab())
            except ValueError as exc:
                QMessageBox.warning(self, "Error", str(exc))

    def save_image(self) -> None:
        if self.frame is None:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Guardar captura", "captura_hmi.png", "PNG (*.png)")
        if path:
            from pathlib import Path
            save_png(Path(path), self.frame)

    def _redraw(self) -> None:
        regions = []
        for p in self.config.pages:
            regions.append((f"page:{p.id}", f"[{p.name}]", p.anchor, PAGE_COLOR))
        for v in self.config.variables:
            regions.append((v.id, v.name, v.region, KIND_COLORS[v.kind]))
        sel = self._current_var if self.tabs.currentIndex() == 0 else (
            f"page:{self._current_page}" if self._current_page else None)
        self.view.set_regions(regions, sel)

    def _rect_drawn(self, rect: Rect) -> None:
        self.lbl_result.setText(f"Selección: x={rect.x} y={rect.y} {rect.w}×{rect.h}")

    def _region_clicked(self, rid: str) -> None:
        if rid.startswith("page:"):
            self.tabs.setCurrentIndex(1)
            self._select_in(self.lst_pages, rid[5:])
        else:
            self.tabs.setCurrentIndex(0)
            self._select_in(self.lst_vars, rid)

    @staticmethod
    def _select_in(lst: QListWidget, key: str) -> None:
        for i in range(lst.count()):
            if lst.item(i).data(Qt.UserRole) == key:
                lst.setCurrentRow(i)
                return

    # --- general ----------------------------------------------------------------
    def _load_general(self) -> None:
        g = self.config.general
        self.ed_machine.setText(self.config.machine_name)
        self.sp_monitor.setValue(g.monitor)
        self.sp_interval.setValue(g.sample_interval_s)
        self.cmb_engine.setCurrentIndex(max(0, self.cmb_engine.findData(g.ocr_engine)))
        self.ed_tess.setText(g.tesseract_path or "")
        self.sp_debounce.setValue(g.debounce_samples)
        self.sp_readfail.setValue(g.read_fail_samples)
        self.sp_stale.setValue(g.stale_after_s)
        self.sp_window.setValue(g.trend_window_min)
        self.sp_horizon.setValue(g.trend_horizon_min)
        self.sp_subgroup.setValue(g.spc_subgroup_s)
        self.chk_beep.setChecked(g.beep_on_alarm)

    def _refresh_recipe_var_combo(self) -> None:
        current = self.cmb_recipe_var.currentData() if self.cmb_recipe_var.count() else \
            self.config.general.recipe_name_var
        self.cmb_recipe_var.clear()
        self.cmb_recipe_var.addItem("— ninguna —", None)
        for v in self.config.variables:
            if v.kind == "text":
                self.cmb_recipe_var.addItem(v.name, v.id)
        self.cmb_recipe_var.setCurrentIndex(max(0, self.cmb_recipe_var.findData(current)))

    def _commit_general(self) -> None:
        g = self.config.general
        self.config.machine_name = self.ed_machine.text().strip() or self.config.machine_name
        g.monitor = self.sp_monitor.value()
        g.sample_interval_s = self.sp_interval.value()
        g.ocr_engine = self.cmb_engine.currentData()
        g.tesseract_path = self.ed_tess.text().strip() or None
        g.debounce_samples = self.sp_debounce.value()
        g.read_fail_samples = self.sp_readfail.value()
        g.stale_after_s = self.sp_stale.value()
        g.trend_window_min = self.sp_window.value()
        g.trend_horizon_min = self.sp_horizon.value()
        g.spc_subgroup_s = self.sp_subgroup.value()
        g.recipe_name_var = self.cmb_recipe_var.currentData()
        g.beep_on_alarm = self.chk_beep.isChecked()

    # --- páginas ---------------------------------------------------------------------
    def _refresh_pages(self, select: Optional[str] = None) -> None:
        self.lst_pages.blockSignals(True)
        self.lst_pages.clear()
        for p in self.config.pages:
            it = QListWidgetItem(f"{p.name}  ({p.id})")
            it.setData(Qt.UserRole, p.id)
            self.lst_pages.addItem(it)
        self.lst_pages.blockSignals(False)
        if select:
            self._select_in(self.lst_pages, select)
        self._refresh_page_combo()
        self._redraw()

    def _refresh_page_combo(self) -> None:
        self._loading = True
        cur = self.cmb_page.currentData()
        self.cmb_page.clear()
        self.cmb_page.addItem("— siempre visible —", None)
        for p in self.config.pages:
            self.cmb_page.addItem(p.name, p.id)
        self.cmb_page.setCurrentIndex(max(0, self.cmb_page.findData(cur)))
        self._loading = False

    def _page_selected(self, item: Optional[QListWidgetItem], _prev=None) -> None:
        self._current_page = item.data(Qt.UserRole) if item else None
        page = self.config.page(self._current_page) if self._current_page else None
        self._loading = True
        self.ed_page_name.setText(page.name if page else "")
        self.sp_page_thr.setValue(page.match_threshold if page else 0.85)
        anchor = self.anchors.get(self._current_page) if page else None
        self.lbl_page_anchor.setPixmap(to_pixmap(anchor) if anchor is not None else to_pixmap(
            np.zeros((1, 1), np.uint8)))
        self.lbl_page_score.setText("")
        self._loading = False
        self._redraw()

    def _need_selection(self) -> Optional[Rect]:
        if self.frame is None or self.view.selection is None:
            QMessageBox.information(self, "Selección", "Primero captura la pantalla y marca una región.")
            return None
        return self.view.selection

    def _new_page(self) -> None:
        r = self._need_selection()
        if r is None:
            return
        name, ok = QInputDialog.getText(self, "Nueva página", "Nombre de la pantalla del HMI:")
        if not ok or not name.strip():
            return
        pid = self._unique(_slug(name), {p.id for p in self.config.pages})
        self.config.pages.append(Page(id=pid, name=name.strip(), anchor=r))
        self.anchors[pid] = crop(self.frame, r).copy()
        self.removed_pages.discard(pid)
        self._refresh_pages(pid)

    def _replace_anchor(self) -> None:
        page = self.config.page(self._current_page) if self._current_page else None
        r = self._need_selection()
        if page is None or r is None:
            return
        page.anchor = r
        self.anchors[page.id] = crop(self.frame, r).copy()
        self._page_selected(self.lst_pages.currentItem())

    def _delete_page(self) -> None:
        pid = self._current_page
        if not pid:
            return
        used = [v.name for v in self.config.variables if v.page == pid]
        if used and QMessageBox.question(
                self, "Eliminar página",
                f"{len(used)} variables usan esta página y pasarán a «siempre visible». ¿Continuar?") \
                != QMessageBox.Yes:
            return
        for v in self.config.variables:
            if v.page == pid:
                v.page = None
        self.config.pages = [p for p in self.config.pages if p.id != pid]
        self.anchors.pop(pid, None)
        self.removed_pages.add(pid)
        self._current_page = None
        self._refresh_pages()

    def _commit_page(self) -> None:
        if self._loading or not self._current_page:
            return
        page = self.config.page(self._current_page)
        if page is None:
            return
        page.name = self.ed_page_name.text().strip() or page.name
        page.match_threshold = self.sp_page_thr.value()
        item = self.lst_pages.currentItem()
        if item:
            item.setText(f"{page.name}  ({page.id})")
        self._refresh_page_combo()

    def _test_page(self) -> None:
        if self.frame is None or not self._current_page:
            return
        det = _MemoryPageDetector(self.config, self.anchors)
        score = det.score(self.frame, self._current_page)
        page = self.config.page(self._current_page)
        verdict = "VISIBLE" if score >= page.match_threshold else "no visible"
        self.lbl_page_score.setText(f"Coincidencia {score:.2f} → {verdict}")

    # --- variables -----------------------------------------------------------------------
    def _refresh_vars(self, select: Optional[str] = None) -> None:
        self.lst_vars.blockSignals(True)
        self.lst_vars.clear()
        for v in self.config.variables:
            it = QListWidgetItem(f"{v.name}  [{v.id}]  · {dict(KINDS)[v.kind].split(' ')[0].lower()}")
            it.setData(Qt.UserRole, v.id)
            self.lst_vars.addItem(it)
        self.lst_vars.blockSignals(False)
        self._refresh_sp_combo()
        self._refresh_recipe_var_combo()
        if select:
            self._select_in(self.lst_vars, select)
        self._redraw()

    def _refresh_sp_combo(self) -> None:
        self._loading = True
        cur = self.cmb_sp.currentData()
        self.cmb_sp.clear()
        self.cmb_sp.addItem("— ninguna —", None)
        for v in self.config.variables:
            if v.kind == "setpoint":
                self.cmb_sp.addItem(v.name, v.id)
        self.cmb_sp.setCurrentIndex(max(0, self.cmb_sp.findData(cur)))
        self._loading = False

    def _var_selected(self, item: Optional[QListWidgetItem], _prev=None) -> None:
        self._current_var = item.data(Qt.UserRole) if item else None
        v = self.config.variable(self._current_var) if self._current_var else None
        if v is None:
            return
        self._loading = True
        self.ed_id.setText(v.id)
        self.ed_name.setText(v.name)
        self.ed_unit.setText(v.unit)
        self.ed_group.setText(v.group)
        self.cmb_kind.setCurrentIndex(max(0, self.cmb_kind.findData(v.kind)))
        self.cmb_page.setCurrentIndex(max(0, self.cmb_page.findData(v.page)))
        self.cmb_sp.setCurrentIndex(max(0, self.cmb_sp.findData(v.setpoint_var)))
        self.sp_dec.setValue(-1 if v.decimals is None else v.decimals)
        self.cmb_sep.setCurrentIndex(max(0, self.cmb_sep.findData(v.decimal_separator)))
        self.chk_fixdec.setChecked(v.fix_missing_decimal)
        self.ed_vmin.setText("" if v.valid_min is None else f"{v.valid_min:g}")
        self.ed_vmax.setText("" if v.valid_max is None else f"{v.valid_max:g}")
        self.ed_step.setText("" if v.max_step is None else f"{v.max_step:g}")
        self.cmb_invert.setCurrentIndex(max(0, self.cmb_invert.findData(v.ocr.invert)))
        self.sp_scale.setValue(v.ocr.scale)
        self.sp_thr.setValue(-1 if v.ocr.threshold is None else v.ocr.threshold)
        self.chk_trend.setChecked(v.trend)
        r = v.region
        self.lbl_region.setText(f"x={r.x} y={r.y} {r.w}×{r.h}")
        self._loading = False
        self._redraw()
        self._test_ocr()

    def _commit_var(self) -> None:
        if self._loading or not self._current_var:
            return
        idx = next((i for i, v in enumerate(self.config.variables) if v.id == self._current_var), None)
        if idx is None:
            return
        old = self.config.variables[idx]
        new_id = _slug(self.ed_id.text()) if self.ed_id.text().strip() else old.id
        if new_id != old.id and self.config.variable(new_id):
            QMessageBox.warning(self, "ID duplicado", f"Ya existe una variable con ID «{new_id}».")
            self.ed_id.setText(old.id)
            new_id = old.id
        try:
            var = Variable(
                id=new_id, name=self.ed_name.text().strip() or new_id, unit=self.ed_unit.text().strip(),
                group=self.ed_group.text().strip() or "General", kind=self.cmb_kind.currentData(),
                page=self.cmb_page.currentData(), region=old.region,
                setpoint_var=self.cmb_sp.currentData() if self.cmb_kind.currentData() == "actual" else None,
                decimals=None if self.sp_dec.value() < 0 else self.sp_dec.value(),
                decimal_separator=self.cmb_sep.currentData(), fix_missing_decimal=self.chk_fixdec.isChecked(),
                valid_min=_opt_float(self.ed_vmin.text()), valid_max=_opt_float(self.ed_vmax.text()),
                max_step=_opt_float(self.ed_step.text()),
                ocr=OcrOptions(invert=self.cmb_invert.currentData(), scale=self.sp_scale.value(),
                               threshold=None if self.sp_thr.value() < 0 else self.sp_thr.value()),
                trend=self.chk_trend.isChecked())
        except ValueError as exc:
            self.lbl_result.setText(f"<span style='color:#e53935'>Valor inválido: {exc}</span>")
            return
        self.config.variables[idx] = var
        if new_id != old.id:
            for v in self.config.variables:
                if v.setpoint_var == old.id:
                    v.setpoint_var = new_id
            if self.config.general.recipe_name_var == old.id:
                self.config.general.recipe_name_var = new_id
            self._current_var = new_id
        item = self.lst_vars.currentItem()
        if item:
            item.setData(Qt.UserRole, var.id)
            item.setText(f"{var.name}  [{var.id}]  · {dict(KINDS)[var.kind].split(' ')[0].lower()}")
        if old.kind != var.kind or new_id != old.id or old.name != var.name:
            self._refresh_sp_combo()
            self._refresh_recipe_var_combo()
        self._redraw()

    @staticmethod
    def _unique(base: str, existing: set[str]) -> str:
        if base not in existing:
            return base
        i = 2
        while f"{base}_{i}" in existing:
            i += 1
        return f"{base}_{i}"

    def _new_var(self) -> None:
        r = self._need_selection()
        if r is None:
            return
        name, ok = QInputDialog.getText(self, "Nueva variable", "Nombre (p. ej. «Zona 3 real»):")
        if not ok or not name.strip():
            return
        vid = self._unique(_slug(name), {v.id for v in self.config.variables})
        page = self._guess_page()
        self.config.variables.append(Variable(id=vid, name=name.strip(), region=r, page=page))
        self._refresh_vars(vid)

    def _guess_page(self) -> Optional[str]:
        if self.frame is None or not self.config.pages:
            return None
        det = _MemoryPageDetector(self.config, self.anchors)
        visible = det.visible_pages(self.frame)
        return next(iter(sorted(visible)), None)

    def _dup_var(self) -> None:
        v = self.config.variable(self._current_var) if self._current_var else None
        if v is None:
            return
        copy = v.model_copy(deep=True)
        copy.id = self._unique(v.id, {x.id for x in self.config.variables})
        copy.name = v.name + " (copia)"
        if self.view.selection is not None:
            copy.region = self.view.selection
        self.config.variables.append(copy)
        self._refresh_vars(copy.id)

    def _delete_var(self) -> None:
        vid = self._current_var
        if not vid:
            return
        self.config.variables = [v for v in self.config.variables if v.id != vid]
        for v in self.config.variables:
            if v.setpoint_var == vid:
                v.setpoint_var = None
        if self.config.general.recipe_name_var == vid:
            self.config.general.recipe_name_var = None
        self._current_var = None
        self._refresh_vars()

    def _assign_region(self) -> None:
        v = self.config.variable(self._current_var) if self._current_var else None
        r = self._need_selection()
        if v is None or r is None:
            return
        v.region = r
        self.lbl_region.setText(f"x={r.x} y={r.y} {r.w}×{r.h}")
        self._redraw()
        self._test_ocr()

    # --- OCR ---------------------------------------------------------------------------
    def _ocr(self):
        if self._ocr_cache is None:
            self._commit_general()
            if self.config.general.ocr_engine == "template":
                self._ocr_cache = self.ctx.template_ocr
            else:
                self._ocr_cache = create_engine(self.config.general, self.ctx.workspace.glyphs_file)
                if isinstance(self._ocr_cache, TemplateOcr):
                    self._ocr_cache = self.ctx.template_ocr
        return self._ocr_cache

    def _test_ocr(self) -> None:
        v = self.config.variable(self._current_var) if self._current_var else None
        if v is None or self.frame is None:
            return
        img = crop(self.frame, v.region)
        self.lbl_crop.setPixmap(to_pixmap(img).scaledToHeight(min(80, max(20, img.shape[0] * 2))))
        binary = preprocess(img, v.ocr)
        self.lbl_bin.setPixmap(to_pixmap(binary).scaledToHeight(min(80, max(20, binary.shape[0]))))
        engine = self._ocr()
        try:
            res = engine.read(img, v.kind != "text", v.ocr)
        except (OcrUnavailable, Exception) as exc:
            self.lbl_result.setText(f"<span style='color:#e53935'>Error OCR: {exc}</span>")
            return
        note = ""
        if engine.name != self.config.general.ocr_engine:
            note = f" (motor «{self.config.general.ocr_engine}» no disponible, se usa «{engine.name}»)"
        if v.kind == "text":
            self.lbl_result.setText(f"Motor {engine.name}{note}: texto «{res.text}» · confianza {res.confidence:.2f}")
            return
        value = parse_number(res.text, v)
        color = "#66bb6a" if value is not None else "#e53935"
        extra = ""
        if isinstance(engine, TemplateOcr) and not engine.known_chars:
            extra = "<br>El motor de plantillas aún no conoce caracteres: usa «Enseñar caracteres…»."
        self.lbl_result.setText(
            f"Motor {engine.name}{note}: texto «{res.text}» → <b style='color:{color}'>"
            f"{'no numérico' if value is None else f'{value:g}'}</b> · confianza {res.confidence:.2f}{extra}")

    def _teach(self) -> None:
        v = self.config.variable(self._current_var) if self._current_var else None
        if v is None or self.frame is None:
            return
        img = crop(self.frame, v.region)
        try:
            guess = self.ctx.template_ocr.read(img, v.kind != "text", v.ocr).text
        except Exception:
            guess = ""
        text, ok = QInputDialog.getText(self, "Enseñar caracteres",
                                        "Escribe exactamente lo que muestra la región:", text=guess.replace("?", ""))
        if not ok or not text.strip():
            return
        try:
            n = self.ctx.template_ocr.teach(img, text, v.ocr)
        except ValueError as exc:
            QMessageBox.warning(self, "No se pudo enseñar", str(exc))
            return
        self.lbl_result.setText(f"Se aprendieron {n} caracteres. Conocidos: {self.ctx.template_ocr.known_chars}")

    # --- guardar -------------------------------------------------------------------------
    def _save(self) -> None:
        self._commit_general()
        problems = self.config.validate_references()
        missing = [p.name for p in self.config.pages if p.id not in self.anchors]
        if missing:
            problems.append(f"Páginas sin imagen ancla: {', '.join(missing)}")
        if problems:
            QMessageBox.warning(self, "Revisa la configuración", "\n".join(problems))
            return
        ws = self.ctx.workspace
        for pid in self.removed_pages:
            f = ws.page_anchor_file(pid)
            if f.exists():
                f.unlink()
        for pid, img in self.anchors.items():
            save_png(ws.page_anchor_file(pid), img)
        ws.save_config(self.config)
        self.accept()


class _MemoryPageDetector(PageDetector):
    """Detector que usa las anclas en memoria (aún no guardadas)."""

    def __init__(self, config: AppConfig, anchors: dict[str, np.ndarray]):
        import cv2
        self.config = config
        self._anchors = {k: cv2.cvtColor(v, cv2.COLOR_BGR2GRAY) for k, v in anchors.items()}
