"""Asistente de configuración: árbol de pestañas del HMI, variables, regiones y OCR."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

import numpy as np
from PySide6.QtCore import Qt, QTimer
from PySide6.QtCore import QSize
from PySide6.QtGui import QBrush, QColor, QFont, QIcon
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
    QFileDialog, QFormLayout, QGroupBox, QHBoxLayout, QInputDialog, QLabel, QLineEdit, QMessageBox,
    QListWidget, QListWidgetItem, QPushButton, QScrollArea, QSpinBox, QSplitter, QStackedWidget, QTabWidget, QTreeWidget,
    QTreeWidgetItem, QVBoxLayout, QWidget,
)

from ..bootstrap import AppContext
from ..capture import ImageFileSource, ScreenSource, crop, load_png, save_png
from ..config import AppConfig, OcrOptions, Page, Rect, Variable
from ..ocr import OcrUnavailable, TemplateOcr, create_engine, parse_number, preprocess
from ..pages import PageDetector
from .common import to_pixmap
from .region_view import RegionView

KIND_COLORS = {"actual": "#43a047", "setpoint": "#1e88e5", "text": "#8e24aa", "selector": "#00897b"}
PAGE_COLOR = "#fb8c00"
KINDS = [("actual", "Medición (valor real)"), ("setpoint", "Consigna (parámetro establecido)"),
         ("text", "Texto (p. ej. nombre de receta)"), ("selector", "Selector / indicador (estado por imagen)")]
KIND_SHORT = {"actual": "medición", "setpoint": "consigna", "text": "texto", "selector": "selector"}
ROLE = Qt.UserRole
NO_PAGE = "__none__"


def _opt_float(text: str) -> Optional[float]:
    text = text.strip().replace(",", ".")
    return float(text) if text else None


def _slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9_]+", "_", text.lower()).strip("_")
    return s or "var"


def _unique(base: str, existing: set[str]) -> str:
    if base not in existing:
        return base
    i = 2
    while f"{base}_{i}" in existing:
        i += 1
    return f"{base}_{i}"


class SeriesDialog(QDialog):
    """Replica variables seleccionadas (p. ej. Cylinder 1 → Cylinder 2..5) con un desplazamiento."""

    def __init__(self, first_name: str, dx: int, dy: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Crear serie")
        f = QFormLayout(self)
        f.addRow(QLabel("Se copian las variables seleccionadas desplazando sus regiones.\n"
                        "Consejo: marca en la captura la posición del segundo elemento antes de abrir este "
                        "diálogo y el desplazamiento se calcula solo."))
        self.sp_count = QSpinBox()
        self.sp_count.setRange(1, 100)
        self.sp_count.setValue(4)
        self.sp_dx = QSpinBox()
        self.sp_dy = QSpinBox()
        for s, v in ((self.sp_dx, dx), (self.sp_dy, dy)):
            s.setRange(-5000, 5000)
            s.setSuffix(" px")
            s.setValue(v)
        m = re.search(r"\d+", first_name)
        self.ed_find = QLineEdit(m.group(0) if m else "")
        self.sp_start = QSpinBox()
        self.sp_start.setRange(-1000, 100000)
        self.sp_start.setValue(int(m.group(0)) + 1 if m else 2)
        f.addRow("Copias a crear", self.sp_count)
        f.addRow("Desplazamiento X por copia", self.sp_dx)
        f.addRow("Desplazamiento Y por copia", self.sp_dy)
        f.addRow("Texto del nombre a numerar", self.ed_find)
        f.addRow("Primer número", self.sp_start)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText("Crear")
        bb.button(QDialogButtonBox.Cancel).setText("Cancelar")
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        f.addRow(bb)


class SetupDialog(QDialog):
    def __init__(self, ctx: AppContext, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Configuración de variables y lectura del HMI")
        self.resize(1600, 940)
        self.ctx = ctx
        self.config: AppConfig = ctx.config.model_copy(deep=True)
        self.frame: Optional[np.ndarray] = None
        self.anchors: dict[str, np.ndarray] = {}
        for p in self.config.pages:
            img = load_png(ctx.workspace.page_anchor_file(p.id))
            if img is not None and p.anchor is not None:
                self.anchors[p.id] = img
        self.removed_pages: set[str] = set()
        self.selector_images: dict[str, dict[str, np.ndarray]] = {}
        for v in self.config.variables:
            if v.kind == "selector":
                imgs = {st: load_png(ctx.workspace.selector_state_file(v.id, st)) for st in v.states}
                self.selector_images[v.id] = {k: i for k, i in imgs.items() if i is not None}
        self._loading = False
        self._current_var: Optional[str] = None
        self._current_page: Optional[str] = None
        self._ocr_cache = None
        # Asistente de par consigna/real: None | ("sp", nombre, página) | ("pv", nombre, página, rect_sp)
        self._pair: Optional[tuple] = None
        self._build()
        self._load_general()
        self._refresh_tree()
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
        for text, slot in (("📷 Capturar pantalla del HMI", self.capture_hmi), ("Abrir imagen…", self.load_image),
                           ("Guardar captura…", self.save_image), ("Ajustar vista", lambda: self.view.fit())):
            b = QPushButton(text)
            b.clicked.connect(slot)
            bar.addWidget(b)
        bar.addStretch()
        ll.addLayout(bar)
        self.lbl_hint = QLabel()
        self._hint()
        ll.addWidget(self.lbl_hint)
        self.view = RegionView()
        self.view.rectDrawn.connect(self._rect_drawn)
        self.view.regionClicked.connect(self._region_clicked)
        ll.addWidget(self.view)
        legend = QLabel(" ".join(f"<span style='color:{c}'>■</span> {KIND_SHORT[k]}" for k, c in KIND_COLORS.items())
                        + f" <span style='color:{PAGE_COLOR}'>■</span> ancla de pestaña")
        ll.addWidget(legend)
        split.addWidget(left)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_tree_tab(), "Pestañas y variables")
        from .tour_tab import TourTab
        self.tour_tab = TourTab(self)
        self.tabs.addTab(self.tour_tab, "Recorrido automático")
        self.tabs.addTab(self._build_general_tab(), "General")
        self.tabs.currentChanged.connect(self._tab_changed)
        split.addWidget(self.tabs)
        split.setSizes([950, 650])
        root.addWidget(split)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Save).setText("Guardar")
        buttons.button(QDialogButtonBox.Cancel).setText("Cancelar")
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def _tab_changed(self, index: int) -> None:
        if self.tabs.widget(index) is self.tour_tab:
            self.tour_tab.refresh()
        else:
            if self.tour_tab.recording is not None:
                self.tour_tab.stop_recording()
            self.view.set_markers([])

    def _hint(self, text: Optional[str] = None, strong: bool = False) -> None:
        default = ("Arrastra con el botón izquierdo para marcar una región · rueda = zoom · "
                   "botón central = desplazar · clic en una región para seleccionarla")
        style = "color:#fff; background:#e65100; padding:4px; font-weight:bold;" if strong else "color:#9e9e9e;"
        self.lbl_hint.setStyleSheet(style)
        self.lbl_hint.setText(text or default)

    def _build_tree_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Nombre", "Tipo", "ID"])
        self.tree.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.tree.itemSelectionChanged.connect(self._tree_selected)
        self.tree.setColumnWidth(0, 300)
        lay.addWidget(self.tree, 3)

        r1 = QHBoxLayout()
        for text, slot, tip in (
                ("+ Pestaña / componente", self._new_root_page, "Nuevo nodo raíz (p. ej. EXT1, GAS, MEAS)"),
                ("+ Sub-pestaña", self._new_child_page, "Nodo dentro de la pestaña seleccionada (p. ej. Overview)")):
            b = QPushButton(text)
            b.setToolTip(tip)
            b.clicked.connect(slot)
            r1.addWidget(b)
        lay.addLayout(r1)
        r2 = QHBoxLayout()
        for text, slot, tip in (
                ("+ Par consigna / medición", self._start_pair,
                 "Marca primero la consigna y después el valor medido; quedan vinculados"),
                ("+ Medición", lambda: self._new_var("actual"), "Variable medida sin consigna"),
                ("+ Consigna", lambda: self._new_var("setpoint"), "Parámetro establecido sin medición"),
                ("+ Texto", lambda: self._new_var("text"), "Texto, p. ej. el nombre de la receta"),
                ("+ Selector", lambda: self._new_var("selector"),
                 "Selector, interruptor o indicador: se reconoce su estado por imagen (ON/OFF, AUTO/MAN…)")):
            b = QPushButton(text)
            b.setToolTip(tip)
            b.clicked.connect(slot)
            r2.addWidget(b)
        lay.addLayout(r2)
        r3 = QHBoxLayout()
        for text, slot in (("Crear serie…", self._series), ("Duplicar", self._duplicate), ("Eliminar", self._delete),
                           ("🧠 Entrenar comportamiento…", self._train_behavior)):
            b = QPushButton(text)
            b.clicked.connect(slot)
            r3.addWidget(b)
        lay.addLayout(r3)

        self.stack = QStackedWidget()
        self.stack.addWidget(QLabel("Selecciona una pestaña o una variable del árbol."))
        self.stack.addWidget(self._build_page_form())
        self.stack.addWidget(self._build_var_form())
        lay.addWidget(self.stack, 4)
        return w

    def _build_page_form(self) -> QWidget:
        box = QGroupBox("Pestaña seleccionada")
        f = QFormLayout(box)
        self.ed_page_name = QLineEdit()
        self.ed_page_name.editingFinished.connect(self._commit_page)
        f.addRow("Nombre", self.ed_page_name)
        self.lbl_page_id = QLabel()
        f.addRow("ID", self.lbl_page_id)
        self.cmb_page_parent = QComboBox()
        self.cmb_page_parent.currentIndexChanged.connect(self._commit_page)
        f.addRow("Dentro de", self.cmb_page_parent)
        f.addRow(QLabel("El ancla es una parte de la pantalla que solo se ve cuando la pestaña está activa,\n"
                        "p. ej. el botón de la pestaña resaltado o el título. Sin ancla, el nodo solo agrupa."))
        self.lbl_page_anchor = QLabel("sin ancla (carpeta: visible si su padre lo es)")
        f.addRow("Ancla", self.lbl_page_anchor)
        row = QHBoxLayout()
        b = QPushButton("Usar selección como ancla")
        b.clicked.connect(self._set_anchor)
        row.addWidget(b)
        b = QPushButton("Quitar ancla")
        b.clicked.connect(self._clear_anchor)
        row.addWidget(b)
        f.addRow("", row)
        self.sp_page_thr = QDoubleSpinBox()
        self.sp_page_thr.setRange(0.3, 1.0)
        self.sp_page_thr.setSingleStep(0.05)
        self.sp_page_thr.valueChanged.connect(self._commit_page)
        f.addRow("Umbral de coincidencia", self.sp_page_thr)
        self.lbl_page_score = QLabel()
        b = QPushButton("Probar en la captura")
        b.clicked.connect(self._test_page)
        f.addRow(b, self.lbl_page_score)
        return box

    def _build_var_form(self) -> QWidget:
        outer = QWidget()
        lay = QVBoxLayout(outer)
        lay.setContentsMargins(0, 0, 0, 0)
        box = QGroupBox("Variable seleccionada")
        f = QFormLayout(box)
        self.ed_id = QLineEdit()
        self.ed_name = QLineEdit()
        self.ed_unit = QLineEdit()
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
        self.chk_border = QCheckBox("Quitar marco del campo")
        self.chk_trend = QCheckBox("Analizar tendencia")
        self.lbl_region = QLabel()
        for label, wdg in (("ID", self.ed_id), ("Nombre", self.ed_name), ("Unidad", self.ed_unit),
                           ("Tipo", self.cmb_kind), ("Pestaña", self.cmb_page),
                           ("Consigna vinculada", self.cmb_sp), ("Decimales", self.sp_dec),
                           ("Separador decimal", self.cmb_sep), ("", self.chk_fixdec),
                           ("Valor mínimo válido", self.ed_vmin), ("Valor máximo válido", self.ed_vmax),
                           ("Salto máx. entre lecturas", self.ed_step), ("Contraste", self.cmb_invert),
                           ("Escala OCR", self.sp_scale), ("Umbral binario", self.sp_thr), ("", self.chk_border),
                           ("", self.chk_trend), ("Región", self.lbl_region)):
            f.addRow(label, wdg)
        for wdg in (self.ed_id, self.ed_name, self.ed_unit, self.ed_vmin, self.ed_vmax, self.ed_step):
            wdg.editingFinished.connect(self._commit_var)
        for wdg in (self.cmb_kind, self.cmb_page, self.cmb_sp, self.cmb_sep, self.cmb_invert):
            wdg.currentIndexChanged.connect(self._commit_var)
        for wdg in (self.sp_dec, self.sp_scale, self.sp_thr):
            wdg.valueChanged.connect(self._commit_var)
        for wdg in (self.chk_fixdec, self.chk_trend, self.chk_border):
            wdg.toggled.connect(self._commit_var)
        self.sel_box = QGroupBox("Estados del selector")
        sl = QVBoxLayout(self.sel_box)
        sl.addWidget(QLabel("Pon el selector en cada estado en el HMI, captura la pantalla y pulsa "
                            "«Capturar estado actual». Se reconoce por imagen: sirve para cualquier color o forma."))
        self.lst_states = QListWidget()
        self.lst_states.setMaximumHeight(110)
        sl.addWidget(self.lst_states)
        row = QHBoxLayout()
        b = QPushButton("Capturar estado actual como…")
        b.clicked.connect(self._capture_state)
        row.addWidget(b)
        b = QPushButton("Eliminar estado")
        b.clicked.connect(self._delete_state)
        row.addWidget(b)
        sl.addLayout(row)
        form2 = QFormLayout()
        self.sp_state_thr = QDoubleSpinBox()
        self.sp_state_thr.setRange(0.3, 1.0)
        self.sp_state_thr.setSingleStep(0.05)
        self.sp_state_thr.valueChanged.connect(self._commit_var)
        form2.addRow("Coincidencia mínima", self.sp_state_thr)
        sl.addLayout(form2)
        f.addRow(self.sel_box)
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
        return outer

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

    # --- imagen -------------------------------------------------------------------
    def _set_frame(self, frame: np.ndarray, fit: bool = True) -> None:
        self.frame = frame
        self.view.set_image(frame)
        self._redraw()
        if fit:
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
        path, _ = QFileDialog.getOpenFileName(self, "Abrir captura del HMI", "",
                                              "Imágenes (*.png *.jpg *.jpeg *.bmp *.webp)")
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
            save_png(Path(path), self.frame)

    def _visible_pages(self) -> set[str]:
        if self.frame is None:
            return set()
        return PageDetector(self.config, self.anchors).visible_pages(self.frame)

    def _redraw(self) -> None:
        """Dibuja las regiones de las pestañas visibles en la captura (o todas si no hay captura)."""
        visible = self._visible_pages() if self.frame is not None else None
        show = lambda pid: pid is None or visible is None or pid in visible or pid == self._current_page  # noqa: E731
        regions = []
        for p in self.config.pages:
            if p.anchor is not None and (show(p.parent) or p.id == self._current_page):
                regions.append((f"page:{p.id}", f"[{p.name}]", p.anchor, PAGE_COLOR))
        selected_vars = set(self._selected("var")) | {self._current_var}
        for v in self.config.variables:
            if show(v.page) or v.id in selected_vars:
                # Solo se rotula la selección: en HMI densos las etiquetas se encimarían.
                label = v.name if v.id in selected_vars else ""
                regions.append((v.id, label, v.region, KIND_COLORS[v.kind]))
        sel = self._current_var or (f"page:{self._current_page}" if self._current_page else None)
        self.view.set_regions(regions, sel)

    def _rect_drawn(self, rect: Rect) -> None:
        if self._pair is not None:
            self._pair_step(rect)
            return
        self.lbl_result.setText(f"Selección: x={rect.x} y={rect.y} {rect.w}×{rect.h}")

    def _region_clicked(self, rid: str) -> None:
        key = ("page", rid[5:]) if rid.startswith("page:") else ("var", rid)
        self._select_key(key)

    # --- árbol ----------------------------------------------------------------------
    def _refresh_tree(self, select: Optional[tuple[str, str]] = None) -> None:
        self.tree.blockSignals(True)
        first = self.tree.topLevelItemCount() == 0
        expanded = {it.data(0, ROLE) for it in self._all_items() if it.isExpanded()}
        self.tree.clear()
        bold = QFont()
        bold.setBold(True)
        nodes: dict[Optional[str], QTreeWidgetItem] = {}
        none = QTreeWidgetItem(["Siempre visible (sin pestaña)", "", ""])
        none.setData(0, ROLE, ("page", NO_PAGE))
        none.setFont(0, bold)
        self.tree.addTopLevelItem(none)
        nodes[None] = none

        def add_page(p: Page, parent_item: Optional[QTreeWidgetItem]):
            it = QTreeWidgetItem([p.name, "pestaña" if p.anchor else "carpeta", p.id])
            it.setData(0, ROLE, ("page", p.id))
            it.setFont(0, bold)
            it.setForeground(0, QBrush(QColor(PAGE_COLOR)))
            (parent_item.addChild(it) if parent_item else self.tree.addTopLevelItem(it))
            nodes[p.id] = it
            for c in self.config.children(p.id):
                add_page(c, it)

        for p in self.config.children(None):
            add_page(p, None)
        linked_sp = {v.setpoint_var for v in self.config.variables if v.setpoint_var}
        for v in self.config.variables:
            if v.kind == "setpoint" and v.id in linked_sp:
                continue  # se muestra bajo su medición
            parent = nodes.get(v.page, none)
            it = self._var_item(v)
            parent.addChild(it)
            if v.kind == "actual" and v.setpoint_var:
                sp = self.config.variable(v.setpoint_var)
                if sp:
                    it.addChild(self._var_item(sp))
                    it.setExpanded(True)
        for it in self._all_items():
            key = it.data(0, ROLE)
            if key[0] == "page":
                it.setExpanded(first or key in expanded)
        self.tree.blockSignals(False)
        self._refresh_combos()
        if select:
            self._select_key(select)
        else:
            self._redraw()

    def _var_item(self, v: Variable) -> QTreeWidgetItem:
        kind = KIND_SHORT[v.kind]
        if v.kind == "actual" and v.setpoint_var:
            kind = "medición + consigna"
        it = QTreeWidgetItem([f"{v.name}" + (f" [{v.unit}]" if v.unit else ""), kind, v.id])
        it.setData(0, ROLE, ("var", v.id))
        it.setForeground(1, QBrush(QColor(KIND_COLORS[v.kind])))
        return it

    def _all_items(self) -> list[QTreeWidgetItem]:
        out = []
        stack = [self.tree.topLevelItem(i) for i in range(self.tree.topLevelItemCount())]
        while stack:
            it = stack.pop()
            out.append(it)
            stack.extend(it.child(i) for i in range(it.childCount()))
        return out

    def _select_key(self, key: tuple[str, str]) -> None:
        for it in self._all_items():
            if it.data(0, ROLE) == key:
                self.tree.setCurrentItem(it)
                self.tree.scrollToItem(it)
                return

    def _selected(self, kind: str) -> list[str]:
        return [it.data(0, ROLE)[1] for it in self.tree.selectedItems() if it.data(0, ROLE)[0] == kind]

    def _tree_selected(self) -> None:
        item = self.tree.currentItem()
        key = item.data(0, ROLE) if item else None
        self._current_var = self._current_page = None
        if key and key[0] == "var":
            self._current_var = key[1]
            self._load_var()
            self.stack.setCurrentIndex(2)
        elif key and key[0] == "page" and key[1] != NO_PAGE:
            self._current_page = key[1]
            self._load_page()
            self.stack.setCurrentIndex(1)
        else:
            self.stack.setCurrentIndex(0)
        self._redraw()

    def _context_page(self) -> Optional[str]:
        """Pestaña donde crear elementos nuevos: la seleccionada, la de la variable o la visible más profunda."""
        if self._current_page:
            return self._current_page
        item = self.tree.currentItem()
        if item and item.data(0, ROLE) == ("page", NO_PAGE):
            return None
        if self._current_var:
            v = self.config.variable(self._current_var)
            return v.page if v else None
        visible = self._visible_pages()
        if visible:
            return max(visible, key=lambda pid: len(self.config.page_path(pid)))
        return None

    def _refresh_combos(self) -> None:
        self._loading = True
        labels = [(p.id, self.config.page_label(p.id)) for p in self.config.pages]
        labels.sort(key=lambda x: x[1])
        cur = self.cmb_page.currentData()
        self.cmb_page.clear()
        self.cmb_page.addItem("— siempre visible —", None)
        for pid, label in labels:
            self.cmb_page.addItem(label, pid)
        self.cmb_page.setCurrentIndex(max(0, self.cmb_page.findData(cur)))
        cur = self.cmb_sp.currentData()
        self.cmb_sp.clear()
        self.cmb_sp.addItem("— ninguna —", None)
        for v in self.config.variables:
            if v.kind == "setpoint":
                self.cmb_sp.addItem(self.config.var_label(v), v.id)
        self.cmb_sp.setCurrentIndex(max(0, self.cmb_sp.findData(cur)))
        self._loading = False
        self._refresh_recipe_var_combo()

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
                self.cmb_recipe_var.addItem(self.config.var_label(v), v.id)
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

    # --- pestañas ------------------------------------------------------------------------
    def _new_root_page(self) -> None:
        self._new_page(None)

    def _new_child_page(self) -> None:
        parent = self._context_page()
        if parent is None:
            QMessageBox.information(self, "Sub-pestaña", "Selecciona primero la pestaña o componente padre.")
            return
        self._new_page(parent)

    def _new_page(self, parent: Optional[str]) -> None:
        where = f" dentro de «{self.config.page_label(parent)}»" if parent else ""
        name, ok = QInputDialog.getText(self, "Nueva pestaña", f"Nombre de la pestaña{where}:")
        if not ok or not name.strip():
            return
        base = f"{parent}_{_slug(name)}" if parent else _slug(name)
        pid = _unique(base, {p.id for p in self.config.pages})
        page = Page(id=pid, name=name.strip(), parent=parent)
        if self.frame is not None and self.view.selection is not None:
            if QMessageBox.question(self, "Ancla", "¿Usar la región marcada como ancla de la pestaña?\n"
                                    "(Debe verse solo cuando la pestaña está activa, p. ej. su botón resaltado)"
                                    ) == QMessageBox.Yes:
                page.anchor = self.view.selection
                self.anchors[pid] = crop(self.frame, page.anchor).copy()
        self.config.pages.append(page)
        self.removed_pages.discard(pid)
        self._refresh_tree(("page", pid))

    def _load_page(self) -> None:
        page = self.config.page(self._current_page)
        if page is None:
            return
        self._loading = True
        self.ed_page_name.setText(page.name)
        self.lbl_page_id.setText(page.id)
        self.cmb_page_parent.clear()
        self.cmb_page_parent.addItem("— raíz —", None)
        forbidden = self.config.descendants(page.id) | {page.id}
        for p in sorted(self.config.pages, key=lambda x: self.config.page_label(x.id)):
            if p.id not in forbidden:
                self.cmb_page_parent.addItem(self.config.page_label(p.id), p.id)
        self.cmb_page_parent.setCurrentIndex(max(0, self.cmb_page_parent.findData(page.parent)))
        self.sp_page_thr.setValue(page.match_threshold)
        anchor = self.anchors.get(page.id) if page.anchor else None
        if anchor is not None:
            self.lbl_page_anchor.setPixmap(to_pixmap(anchor))
        else:
            self.lbl_page_anchor.setPixmap(to_pixmap(np.full((1, 1), 255, np.uint8)))
            self.lbl_page_anchor.setText("sin ancla (carpeta: visible si su padre lo es)")
        self.lbl_page_score.setText("")
        self._loading = False

    def _commit_page(self) -> None:
        if self._loading or not self._current_page:
            return
        page = self.config.page(self._current_page)
        if page is None:
            return
        page.name = self.ed_page_name.text().strip() or page.name
        page.match_threshold = self.sp_page_thr.value()
        new_parent = self.cmb_page_parent.currentData()
        changed = new_parent != page.parent
        page.parent = new_parent
        item = self.tree.currentItem()
        if changed:
            self._refresh_tree(("page", page.id))
        elif item:
            item.setText(0, page.name)
            self._refresh_combos()

    def _need_selection(self) -> Optional[Rect]:
        if self.frame is None or self.view.selection is None:
            QMessageBox.information(self, "Selección", "Primero captura la pantalla y marca una región.")
            return None
        return self.view.selection

    def _set_anchor(self) -> None:
        page = self.config.page(self._current_page) if self._current_page else None
        r = self._need_selection()
        if page is None or r is None:
            return
        page.anchor = r
        self.anchors[page.id] = crop(self.frame, r).copy()
        self._refresh_tree(("page", page.id))

    def _clear_anchor(self) -> None:
        page = self.config.page(self._current_page) if self._current_page else None
        if page is None:
            return
        page.anchor = None
        self.anchors.pop(page.id, None)
        self.removed_pages.add(page.id)
        self._refresh_tree(("page", page.id))

    def _test_page(self) -> None:
        if self.frame is None or not self._current_page:
            return
        page = self.config.page(self._current_page)
        det = PageDetector(self.config, self.anchors)
        visible = self._current_page in det.visible_pages(self.frame)
        score = det.score(self.frame, page.id) if page.anchor else None
        s = f"coincidencia {score:.2f} · " if score is not None else ""
        self.lbl_page_score.setText(f"{s}{'VISIBLE' if visible else 'no visible'}")

    # --- variables -----------------------------------------------------------------------
    def _load_var(self) -> None:
        v = self.config.variable(self._current_var)
        if v is None:
            return
        self._loading = True
        self.ed_id.setText(v.id)
        self.ed_name.setText(v.name)
        self.ed_unit.setText(v.unit)
        self.cmb_kind.setCurrentIndex(max(0, self.cmb_kind.findData(v.kind)))
        self.cmb_page.setCurrentIndex(max(0, self.cmb_page.findData(v.page)))
        self.cmb_sp.setCurrentIndex(max(0, self.cmb_sp.findData(v.setpoint_var)))
        self.cmb_sp.setEnabled(v.kind == "actual")
        self.sp_dec.setValue(-1 if v.decimals is None else v.decimals)
        self.cmb_sep.setCurrentIndex(max(0, self.cmb_sep.findData(v.decimal_separator)))
        self.chk_fixdec.setChecked(v.fix_missing_decimal)
        self.ed_vmin.setText("" if v.valid_min is None else f"{v.valid_min:g}")
        self.ed_vmax.setText("" if v.valid_max is None else f"{v.valid_max:g}")
        self.ed_step.setText("" if v.max_step is None else f"{v.max_step:g}")
        self.cmb_invert.setCurrentIndex(max(0, self.cmb_invert.findData(v.ocr.invert)))
        self.sp_scale.setValue(v.ocr.scale)
        self.sp_thr.setValue(-1 if v.ocr.threshold is None else v.ocr.threshold)
        self.chk_border.setChecked(v.ocr.clear_border)
        self.chk_trend.setChecked(v.trend)
        self.sp_state_thr.setValue(v.state_threshold)
        self._refresh_states(v)
        r = v.region
        self.lbl_region.setText(f"x={r.x} y={r.y} {r.w}×{r.h}")
        self._loading = False
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
        kind = self.cmb_kind.currentData()
        try:
            var = Variable(
                id=new_id, name=self.ed_name.text().strip() or new_id, unit=self.ed_unit.text().strip(),
                group=old.group, kind=kind, page=self.cmb_page.currentData(), region=old.region,
                setpoint_var=self.cmb_sp.currentData() if kind == "actual" else None,
                decimals=None if self.sp_dec.value() < 0 else self.sp_dec.value(),
                decimal_separator=self.cmb_sep.currentData(), fix_missing_decimal=self.chk_fixdec.isChecked(),
                valid_min=_opt_float(self.ed_vmin.text()), valid_max=_opt_float(self.ed_vmax.text()),
                max_step=_opt_float(self.ed_step.text()),
                ocr=OcrOptions(invert=self.cmb_invert.currentData(), scale=self.sp_scale.value(),
                               threshold=None if self.sp_thr.value() < 0 else self.sp_thr.value(),
                               clear_border=self.chk_border.isChecked()),
                trend=self.chk_trend.isChecked(), states=list(old.states),
                state_threshold=self.sp_state_thr.value())
        except ValueError as exc:
            self.lbl_result.setText(f"<span style='color:#e53935'>Valor inválido: {exc}</span>")
            return
        self.config.variables[idx] = var
        if new_id != old.id:
            self._rename_refs(old.id, new_id)
            self._current_var = new_id
        if kind != "setpoint":
            # Si dejó de ser consigna, se desvincula de las mediciones que la usaban.
            for v in self.config.variables:
                if v.setpoint_var == var.id:
                    v.setpoint_var = None
        structural = (old.kind, old.page, old.setpoint_var, old.id) != (var.kind, var.page, var.setpoint_var, var.id)
        if structural:
            self._refresh_tree(("var", var.id))
        else:
            item = self.tree.currentItem()
            if item:
                fresh = self._var_item(var)
                for c in range(3):
                    item.setText(c, fresh.text(c))
            self._redraw()
        self.cmb_sp.setEnabled(kind == "actual")

    def _rename_refs(self, old: str, new: str) -> None:
        for v in self.config.variables:
            if v.setpoint_var == old:
                v.setpoint_var = new
        if self.config.general.recipe_name_var == old:
            self.config.general.recipe_name_var = new

    def _make_var(self, kind: str, name: str, region: Rect, page: Optional[str]) -> Variable:
        base = f"{page}_{_slug(name)}" if page else _slug(name)
        if kind == "setpoint":
            base += "_sp"
        vid = _unique(base, {v.id for v in self.config.variables})
        return Variable(id=vid, name=name, kind=kind, region=region, page=page, trend=kind == "actual")

    def _new_var(self, kind: str) -> None:
        r = self._need_selection()
        if r is None:
            return
        page = self._context_page()
        where = f" en «{self.config.page_label(page)}»" if page else " (siempre visible)"
        name, ok = QInputDialog.getText(self, f"Nueva {KIND_SHORT[kind]}", f"Nombre{where}:")
        if not ok or not name.strip():
            return
        var = self._make_var(kind, name.strip(), r, page)
        self.config.variables.append(var)
        self._refresh_tree(("var", var.id))

    # Par consigna / medición: dos regiones marcadas en secuencia.
    def _start_pair(self) -> None:
        if self.frame is None:
            QMessageBox.information(self, "Captura", "Primero captura la pantalla del HMI.")
            return
        page = self._context_page()
        where = f" en «{self.config.page_label(page)}»" if page else " (siempre visible)"
        name, ok = QInputDialog.getText(self, "Nuevo par consigna / medición",
                                        f"Nombre de la variable{where} (p. ej. «Cylinder 1»):")
        if not ok or not name.strip():
            return
        self._pair = ("sp", name.strip(), page)
        self._hint(f"① Marca la región de la CONSIGNA de «{name.strip()}» (Esc para cancelar)", strong=True)

    def _pair_step(self, rect: Rect) -> None:
        if self._pair[0] == "sp":
            _, name, page = self._pair
            self._pair = ("pv", name, page, rect)
            self._hint(f"② Ahora marca la región de la MEDICIÓN (valor real) de «{name}»", strong=True)
            return
        _, name, page, sp_rect = self._pair
        self._pair = None
        self._hint()
        sp = self._make_var("setpoint", name, sp_rect, page)
        sp.name = f"{name} consigna"
        self.config.variables.append(sp)
        pv = self._make_var("actual", name, rect, page)
        pv.setpoint_var = sp.id
        self.config.variables.append(pv)
        self._refresh_tree(("var", pv.id))

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key_Escape and self._pair is not None:
            self._pair = None
            self._hint()
            return
        if event.key() == Qt.Key_Escape and self.tour_tab.recording is not None:
            self.tour_tab.stop_recording()
            return
        super().keyPressEvent(event)

    def _group_for_copy(self) -> list[Variable]:
        """Variables seleccionadas; al elegir una medición se incluye su consigna vinculada."""
        ids = list(dict.fromkeys(self._selected("var")))
        for vid in list(ids):
            v = self.config.variable(vid)
            if v and v.setpoint_var and v.setpoint_var not in ids:
                ids.append(v.setpoint_var)
        return [v for v in (self.config.variable(i) for i in ids) if v]

    def _clone_group(self, group: list[Variable], dx: int, dy: int, rename) -> list[Variable]:
        existing = {v.id for v in self.config.variables}
        mapping: dict[str, str] = {}
        clones = []
        for v in group:
            c = v.model_copy(deep=True)
            c.name = rename(v.name)
            base = f"{v.page}_{_slug(c.name)}" if v.page else _slug(c.name)
            if c.kind == "setpoint" and not base.endswith("_sp"):
                base += "_sp"
            c.id = _unique(base, existing)
            existing.add(c.id)
            c.region = Rect(x=v.region.x + dx, y=v.region.y + dy, w=v.region.w, h=v.region.h)
            mapping[v.id] = c.id
            if c.kind == "selector" and v.id in self.selector_images:
                self.selector_images[c.id] = dict(self.selector_images[v.id])
            clones.append(c)
        for c in clones:
            if c.setpoint_var in mapping:
                c.setpoint_var = mapping[c.setpoint_var]
        return clones

    def _duplicate(self) -> None:
        group = self._group_for_copy()
        if not group:
            return
        dx = dy = 0
        if self.view.selection is not None:
            dx = self.view.selection.x - min(v.region.x for v in group)
            dy = self.view.selection.y - min(v.region.y for v in group)
        clones = self._clone_group(group, dx, dy, lambda n: n + " (copia)")
        self.config.variables.extend(clones)
        self._refresh_tree(("var", clones[0].id))

    def _series(self) -> None:
        group = self._group_for_copy()
        if not group:
            QMessageBox.information(self, "Crear serie", "Selecciona en el árbol las variables a replicar.")
            return
        dx = dy = 0
        if self.view.selection is not None:
            dx = self.view.selection.x - min(v.region.x for v in group)
            dy = self.view.selection.y - min(v.region.y for v in group)
        dlg = SeriesDialog(group[0].name, dx, dy, self)
        if not dlg.exec():
            return
        find = dlg.ed_find.text()
        created = []
        for k in range(dlg.sp_count.value()):
            number = str(dlg.sp_start.value() + k)

            def rename(n: str, number=number, k=k) -> str:
                if find and find in n:
                    return n.replace(find, number, 1)
                return f"{n} {k + 2}"

            clones = self._clone_group(group, dlg.sp_dx.value() * (k + 1), dlg.sp_dy.value() * (k + 1), rename)
            self.config.variables.extend(clones)
            created += clones
        self._refresh_tree(("var", created[0].id) if created else None)
        self.lbl_result.setText(f"Se crearon {len(created)} variables.")

    def _delete(self) -> None:
        var_ids = set(self._selected("var"))
        page_ids = {p for p in self._selected("page") if p != NO_PAGE}
        for pid in list(page_ids):
            page_ids |= self.config.descendants(pid)
        in_pages = {v.id for v in self.config.variables if v.page in page_ids}
        # Al borrar una medición también se borra su consigna vinculada.
        for vid in list(var_ids):
            v = self.config.variable(vid)
            if v and v.setpoint_var:
                var_ids.add(v.setpoint_var)
        all_vars = var_ids | in_pages
        if not all_vars and not page_ids:
            return
        msg = []
        if page_ids:
            msg.append(f"{len(page_ids)} pestañas")
        if all_vars:
            msg.append(f"{len(all_vars)} variables")
        if QMessageBox.question(self, "Eliminar", f"¿Eliminar {' y '.join(msg)}?") != QMessageBox.Yes:
            return
        self.config.variables = [v for v in self.config.variables if v.id not in all_vars]
        for v in self.config.variables:
            if v.setpoint_var in all_vars:
                v.setpoint_var = None
        if self.config.general.recipe_name_var in all_vars:
            self.config.general.recipe_name_var = None
        self.config.pages = [p for p in self.config.pages if p.id not in page_ids]
        self.config.tour.steps = [st for st in self.config.tour.steps if st.page not in page_ids]
        if self.config.tour.home_page in page_ids:
            self.config.tour.home_page = None
        for pid in page_ids:
            self.anchors.pop(pid, None)
        self.removed_pages |= page_ids
        self._current_var = self._current_page = None
        self._refresh_tree()
        self.stack.setCurrentIndex(0)

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

    # --- selectores ------------------------------------------------------------------
    def _refresh_states(self, v: Variable) -> None:
        self.sel_box.setVisible(v.kind == "selector")
        self.lst_states.clear()
        for st in v.states:
            it = QListWidgetItem(st)
            img = self.selector_images.get(v.id, {}).get(st)
            if img is not None:
                it.setIcon(QIcon(to_pixmap(img)))
            self.lst_states.addItem(it)
        self.lst_states.setIconSize(QSize(96, 32))

    def _capture_state(self) -> None:
        v = self.config.variable(self._current_var) if self._current_var else None
        if v is None or self.frame is None:
            return
        name, ok = QInputDialog.getText(self, "Estado del selector",
                                        "Nombre del estado que se ve ahora (p. ej. ON, OFF, AUTO, MAN):")
        name = name.strip()
        if not ok or not name:
            return
        if name not in v.states:
            v.states.append(name)
        self.selector_images.setdefault(v.id, {})[name] = crop(self.frame, v.region).copy()
        self._refresh_states(v)
        self._test_ocr()

    def _delete_state(self) -> None:
        v = self.config.variable(self._current_var) if self._current_var else None
        it = self.lst_states.currentItem()
        if v is None or it is None:
            return
        v.states = [s for s in v.states if s != it.text()]
        self.selector_images.get(v.id, {}).pop(it.text(), None)
        self._refresh_states(v)

    def _train_behavior(self) -> None:
        from .behavior_dialog import BehaviorDialog
        pre = [vid for vid in self._selected("var") if (v := self.config.variable(vid)) and v.numeric]
        BehaviorDialog(self.ctx, self, preselect=pre, config=self.config).exec()

    def _test_ocr(self) -> None:
        v = self.config.variable(self._current_var) if self._current_var else None
        if v is None or self.frame is None:
            return
        img = crop(self.frame, v.region)
        if v.kind == "selector":
            from ..acquisition import match_state
            self.lbl_crop.setPixmap(to_pixmap(img).scaledToHeight(min(80, max(20, img.shape[0] * 2))))
            self.lbl_bin.clear()
            states = self.selector_images.get(v.id, {})
            if not states:
                self.lbl_result.setText("Captura al menos un estado del selector.")
                return
            from ..capture import similarity
            import cv2 as _cv2
            scores = []
            for name, ref in states.items():
                cur = img if img.shape == ref.shape else _cv2.resize(img, (ref.shape[1], ref.shape[0]))
                scores.append(f"{name}: {similarity(cur, ref):.2f}")
            state, score = match_state(img, states)
            ok = score >= v.state_threshold
            color = "#43a047" if ok else "#e53935"
            self.lbl_result.setText(f"Estado detectado: <b style='color:{color}'>{state if ok else 'no reconocido'}"
                                    f"</b> · coincidencias: {', '.join(scores)}")
            return
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
            from .. import ocr as ocr_mod
            why = f": {ocr_mod.last_error}" if ocr_mod.last_error else ""
            note = f" (motor «{self.config.general.ocr_engine}» no disponible{why}; se usa «{engine.name}»)"
        if v.kind == "text":
            self.lbl_result.setText(f"Motor {engine.name}{note}: texto «{res.text}» · confianza {res.confidence:.2f}")
            return
        value = parse_number(res.text, v)
        color = "#43a047" if value is not None else "#e53935"
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
        missing = [p.name for p in self.config.pages if p.anchor is not None and p.id not in self.anchors]
        if missing:
            problems.append(f"Pestañas sin imagen ancla: {', '.join(missing)}")
        no_patch = [c for c in self.config.tour.all_clicks() if c.id not in self.tour_tab.patches]
        if no_patch:
            problems.append(f"Recorrido: {len(no_patch)} clics sin imagen del botón; vuelve a grabarlos")
        if problems:
            QMessageBox.warning(self, "Revisa la configuración", "\n".join(problems))
            return
        ws = self.ctx.workspace
        for pid in self.removed_pages:
            f = ws.page_anchor_file(pid)
            if f.exists() and pid not in self.anchors:
                f.unlink()
        for pid, img in self.anchors.items():
            save_png(ws.page_anchor_file(pid), img)
        keep = set()
        for v in self.config.variables:
            if v.kind == "selector":
                for st in v.states:
                    img = self.selector_images.get(v.id, {}).get(st)
                    if img is not None:
                        f = ws.selector_state_file(v.id, st)
                        save_png(f, img)
                        keep.add(f.name)
        for f in ws.selectors_dir.glob("*.png"):
            if f.name not in keep:
                f.unlink()
        used = {c.id for c in self.config.tour.all_clicks()}
        for cid, img in self.tour_tab.patches.items():
            if cid in used:
                save_png(ws.click_patch_file(cid), img)
        for f in ws.clicks_dir.glob("*.png"):
            if f.stem not in used:
                f.unlink()
        ws.save_config(self.config)
        self.accept()
