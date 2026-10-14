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
from ..config import (SCREEN, AppConfig, BarOptions, ColorState, GaugeOptions, OcrOptions, Page, Rect,
                      SevenSegOptions, Variable)
from ..ocr import OcrUnavailable, TemplateOcr, create_engine, parse_number, preprocess
from ..pages import PageDetector
from ..i18n import tr, translate_widget
from .common import to_pixmap
from .region_view import RegionView

KIND_COLORS = {"actual": "#43a047", "setpoint": "#1e88e5", "text": "#8e24aa", "selector": "#00897b",
               "formula": "#6d4c41"}
PAGE_COLOR = "#fb8c00"
KINDS = [("actual", "Medición (valor real)"), ("setpoint", "Consigna (parámetro establecido)"),
         ("text", "Texto (p. ej. nombre de receta)"), ("selector", "Selector / indicador (estado por imagen)"),
         ("formula", "Fórmula (calculada de otras variables)")]
KIND_SHORT = {"actual": "medición", "setpoint": "consigna", "text": "texto", "selector": "selector",
              "formula": "fórmula"}
ROLE = Qt.UserRole
NO_PAGE = "__none__"
READERS = [("ocr", "Texto / números (OCR)"), ("sevenseg", "Display de 7 segmentos (LED o LCD)"),
           ("gauge", "Aguja (manómetro, carátula)"), ("bar", "Barra de nivel / bargraph")]
READER_SHORT = {"sevenseg": "display 7 seg.", "gauge": "aguja", "bar": "barra de nivel"}
CAMERA_COLOR = "#5c6bc0"


def lab_to_bgr(lab) -> tuple[int, int, int]:
    import cv2
    px = np.uint8([[[int(round(c)) for c in lab]]])
    return tuple(int(c) for c in cv2.cvtColor(px, cv2.COLOR_LAB2BGR)[0, 0])


def kind_label(v: Variable) -> str:
    if v.kind == "selector" and v.state_method == "color":
        return "luz / andon"
    if v.kind in ("actual", "setpoint") and v.reader != "ocr":
        return READER_SHORT[v.reader]
    return KIND_SHORT[v.kind]


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
        self.source = SCREEN  # imagen mostrada: pantalla del HMI o id de una cámara
        self.frames: dict[str, np.ndarray] = {}
        self._gauge_cal: Optional[list] = None
        self._gauge_marks = False  # clics de calibración de la aguja (centro, mínimo, máximo)
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
        self._refresh_sources()
        self._refresh_tree()
        try:
            if self.config.needs_screen:
                self._set_frame(ctx.engine.grab_frame())
        except Exception:
            pass
        if self.config.cameras and not self.config.needs_screen:
            self.set_source(self.config.cameras[0].id)  # equipo sin pantalla: se abre en su cámara
        self._commit_all()
        self._baseline = self._fingerprint()  # para avisar al salir con cambios sin guardar

    # --- construcción ----------------------------------------------------------
    def _build(self) -> None:
        root = QVBoxLayout(self)
        split = QSplitter(Qt.Horizontal)
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(0, 0, 0, 0)
        bar = QHBoxLayout()
        bar.addWidget(QLabel("Fuente:"))
        self.cmb_source = QComboBox()
        self.cmb_source.setToolTip("Pantalla del HMI o una cámara que mira el tablero del equipo")
        self.cmb_source.currentIndexChanged.connect(self._source_changed)
        bar.addWidget(self.cmb_source)
        b = QPushButton("📹 Cámaras…")
        b.setToolTip("Agregar o ajustar cámaras (USB o IP) para equipos sin pantalla legible")
        b.clicked.connect(self._open_cameras)
        bar.addWidget(b)
        for text, slot in (("📷 Capturar", self.capture_hmi), ("Abrir imagen…", self.load_image),
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
        self.view.pointClicked.connect(self._gauge_point)
        legend = QLabel(" ".join(f"<span style='color:{c}'>■</span> {tr(KIND_SHORT[k])}" for k, c in KIND_COLORS.items())
                        + f" <span style='color:{PAGE_COLOR}'>■</span> {tr('ancla de pestaña')}")
        ll.addWidget(legend)
        split.addWidget(left)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_tree_tab(), "Pestañas y variables")
        from .tour_tab import TourTab
        self.tour_tab = TourTab(self)
        self.tabs.addTab(self.tour_tab, "Recorrido automático")
        from .oee_tab import OeeTab
        self.oee_tab = OeeTab(self)
        self.tabs.addTab(self.oee_tab, "KPI / OEE")
        from .report_tab import ReportTab
        self.report_tab = ReportTab(self)
        self.tabs.addTab(self.report_tab, "Reportes")
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
        elif self.tabs.widget(index) is getattr(self, "oee_tab", None):
            self.oee_tab.commit()
            self.oee_tab.load()
        elif self.tabs.widget(index) is getattr(self, "report_tab", None):
            self.report_tab.refresh()  # variables y recorridos nuevos
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
                ("+ Fórmula", self._new_formula, "Variable calculada con otras, p. ej. «vel / rpm» o "
                 "«max(z1, z2, z3) - min(z1, z2, z3)»"),
                ("+ Selector", lambda: self._new_var("selector"),
                 "Selector, interruptor o indicador: se reconoce su estado por imagen (ON/OFF, AUTO/MAN…)")):
            b = QPushButton(text)
            b.setToolTip(tip)
            b.clicked.connect(slot)
            r2.addWidget(b)
        lay.addLayout(r2)
        r2b = QHBoxLayout()
        r2b.addWidget(QLabel("Indicadores físicos:"))
        for text, slot, tip in (
                ("+ Luz / LED", lambda: self._new_indicator("lamp"),
                 "Luz piloto, LED o una luz de torre andon: se reconoce por su color (y si parpadea)"),
                ("+ Torre andon…", self._new_andon, "Marca toda la torre: se crea una luz por cada color"),
                ("+ Display 7 seg.", lambda: self._new_indicator("sevenseg"),
                 "Display de 7 segmentos de un controlador, sensor o contador (LED o LCD)"),
                ("+ Aguja", lambda: self._new_indicator("gauge"), "Manómetro, termómetro de carátula o tacómetro"),
                ("+ Barra de nivel", lambda: self._new_indicator("bar"), "Bargraph de LED o indicador de nivel")):
            b = QPushButton(text)
            b.setToolTip(tip)
            b.clicked.connect(slot)
            r2b.addWidget(b)
        lay.addLayout(r2b)
        r3 = QHBoxLayout()
        for text, slot in (("Crear serie…", self._series), ("Duplicar", self._duplicate), ("Eliminar", self._delete),
                           ("🧠 Entrenar comportamiento…", self._train_behavior),
                           ("🩺 Diagnóstico de lectura", self._diagnose)):
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
        self.chk_auto = QCheckBox("Lectura automática robusta (recomendado: sin umbral manual)")
        self.chk_auto.setToolTip("Prueba varias formas de preparar la imagen y acepta el valor cuando coinciden. "
                                 "Recuerda la que funciona para esta variable.")
        self.chk_trend = QCheckBox("Analizar tendencia")
        self.cmb_var_source = QComboBox()
        self.cmb_reader = QComboBox()
        for k, label in READERS:
            self.cmb_reader.addItem(label, k)
        self.lbl_region = QLabel()
        self.ed_formula = QLineEdit()
        self.ed_formula.setPlaceholderText("p. ej. vel / rpm   ·   {z1} - {z1_sp}   ·   max(z1, z2) - min(z1, z2)")
        self.ed_formula.setToolTip("Usa los ID de las variables. Funciones: abs, min, max, avg, round, sqrt, log, "
                                   "exp, pow, clamp, si(cond, a, b). Operadores + - * / ** % y comparaciones.")
        self.ed_formula.editingFinished.connect(self._commit_var)
        for label, wdg in (("ID", self.ed_id), ("Nombre", self.ed_name), ("Unidad", self.ed_unit),
                           ("Tipo", self.cmb_kind), ("Fuente", self.cmb_var_source),
                           ("Lectura", self.cmb_reader), ("Pestaña", self.cmb_page),
                           ("Consigna vinculada", self.cmb_sp), ("Decimales", self.sp_dec),
                           ("Separador decimal", self.cmb_sep), ("", self.chk_fixdec),
                           ("Valor mínimo válido", self.ed_vmin), ("Valor máximo válido", self.ed_vmax),
                           ("Salto máx. entre lecturas", self.ed_step), ("Contraste", self.cmb_invert),
                           ("", self.chk_auto), ("Escala OCR", self.sp_scale), ("Umbral binario", self.sp_thr),
                           ("", self.chk_border),
                           ("", self.chk_trend), ("Región", self.lbl_region), ("Fórmula", self.ed_formula)):
            f.addRow(label, wdg)
        for wdg in (self.ed_id, self.ed_name, self.ed_unit, self.ed_vmin, self.ed_vmax, self.ed_step):
            wdg.editingFinished.connect(self._commit_var)
        for wdg in (self.cmb_kind, self.cmb_page, self.cmb_sp, self.cmb_sep, self.cmb_invert, self.cmb_var_source,
                    self.cmb_reader):
            wdg.currentIndexChanged.connect(self._commit_var)
        for wdg in (self.sp_dec, self.sp_scale, self.sp_thr):
            wdg.valueChanged.connect(self._commit_var)
        for wdg in (self.chk_fixdec, self.chk_trend, self.chk_border, self.chk_auto):
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
        self.cmb_state_method = QComboBox()
        self.cmb_state_method.addItem("Por imagen (forma y color)", "image")
        self.cmb_state_method.addItem("Por color (luz, LED, andon)", "color")
        self.cmb_state_method.setToolTip("Por color tolera mejor los cambios de luz de una cámara y detecta el parpadeo")
        self.cmb_state_method.currentIndexChanged.connect(self._commit_var)
        form2.addRow("Reconocer", self.cmb_state_method)
        self.chk_blink = QCheckBox("Detectar parpadeo (agrega «… parpadeando»)")
        self.chk_blink.toggled.connect(self._commit_var)
        form2.addRow("", self.chk_blink)
        self.sp_blink = QDoubleSpinBox()
        self.sp_blink.setRange(1, 30)
        self.sp_blink.setSuffix(" s")
        self.sp_blink.setToolTip("Ventana para decidir si parpadea (al menos dos encendidos y apagados)")
        self.sp_blink.valueChanged.connect(self._commit_var)
        form2.addRow("Ventana de parpadeo", self.sp_blink)
        self.sp_state_thr = QDoubleSpinBox()
        self.sp_state_thr.setRange(0.3, 1.0)
        self.sp_state_thr.setSingleStep(0.05)
        self.sp_state_thr.valueChanged.connect(self._commit_var)
        form2.addRow("Coincidencia mínima", self.sp_state_thr)
        sl.addLayout(form2)
        f.addRow(self.sel_box)
        f.addRow(self._build_reader_boxes())
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(box)
        lay.addWidget(scroll, 3)

        test = QGroupBox("Prueba de lectura")
        tl = QVBoxLayout(test)
        row = QHBoxLayout()
        for text, slot in (("Asignar selección como región", self._assign_region),
                           ("Probar lectura", self._test_ocr), ("Enseñar caracteres…", self._teach)):
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

    def _build_reader_boxes(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        self.seg_box = QGroupBox("Display de 7 segmentos")
        f = QFormLayout(self.seg_box)
        self.sp_seg_digits = QSpinBox()
        self.sp_seg_digits.setRange(0, 12)
        self.sp_seg_digits.setSpecialValueText("automático")
        self.cmb_seg_pol = QComboBox()
        for k, label in (("auto", "automático"), ("light", "segmentos encendidos (LED)"),
                         ("dark", "segmentos oscuros (LCD)")):
            self.cmb_seg_pol.addItem(label, k)
        self.sp_seg_slant = QDoubleSpinBox()
        self.sp_seg_slant.setRange(-31, 30)
        self.sp_seg_slant.setSpecialValueText("automática")
        self.sp_seg_slant.setSuffix("°")
        f.addRow("Dígitos", self.sp_seg_digits)
        f.addRow("Tipo de display", self.cmb_seg_pol)
        f.addRow("Inclinación", self.sp_seg_slant)
        f.addRow(QLabel("Marca solo los dígitos (sin unidades ni marco). Si el punto decimal no se ve, indica "
                        "los decimales y activa «Reinsertar punto decimal»."))
        self.gauge_box = QGroupBox("Aguja")
        f = QFormLayout(self.gauge_box)
        self.lbl_gauge = QLabel()
        b = QPushButton("🎯 Calibrar: centro, mínimo y máximo (3 clics)")
        b.clicked.connect(self._start_gauge_cal)
        self.ed_g_min = QLineEdit()
        self.ed_g_max = QLineEdit()
        self.cmb_needle = QComboBox()
        for k, label in (("auto", "automático"), ("dark", "aguja oscura"), ("light", "aguja clara")):
            self.cmb_needle.addItem(label, k)
        f.addRow(b)
        f.addRow("Calibración", self.lbl_gauge)
        f.addRow("Valor en la marca mínima", self.ed_g_min)
        f.addRow("Valor en la marca máxima", self.ed_g_max)
        f.addRow("Aguja", self.cmb_needle)
        self.bar_box = QGroupBox("Barra de nivel")
        f = QFormLayout(self.bar_box)
        self.cmb_bar_dir = QComboBox()
        for k, label in (("up", "sube (de abajo hacia arriba)"), ("down", "baja"), ("right", "hacia la derecha"),
                         ("left", "hacia la izquierda")):
            self.cmb_bar_dir.addItem(label, k)
        self.ed_b_min = QLineEdit()
        self.ed_b_max = QLineEdit()
        self.cmb_bar_pol = QComboBox()
        for k, label in (("auto", "lo lleno es claro / encendido"), ("dark", "lo lleno es oscuro")):
            self.cmb_bar_pol.addItem(label, k)
        f.addRow("Dirección", self.cmb_bar_dir)
        f.addRow("Valor vacío", self.ed_b_min)
        f.addRow("Valor lleno", self.ed_b_max)
        f.addRow("Relleno", self.cmb_bar_pol)
        for wdg in (self.cmb_seg_pol, self.cmb_needle, self.cmb_bar_dir, self.cmb_bar_pol):
            wdg.currentIndexChanged.connect(self._commit_var)
        for wdg in (self.sp_seg_digits, self.sp_seg_slant):
            wdg.valueChanged.connect(self._commit_var)
        for wdg in (self.ed_g_min, self.ed_g_max, self.ed_b_min, self.ed_b_max):
            wdg.editingFinished.connect(self._commit_var)
        for box in (self.seg_box, self.gauge_box, self.bar_box):
            lay.addWidget(box)
        return w

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
        self.frames[self.source] = frame
        self.view.set_image(frame)
        self._redraw()
        if fit:
            QTimer.singleShot(0, self.view.fit)

    # --- fuentes: pantalla del HMI o cámaras ---------------------------------------------------------------
    def _refresh_sources(self) -> None:
        self.cmb_source.blockSignals(True)
        self.cmb_source.clear()
        self.cmb_source.addItem("🖥 Pantalla del HMI", SCREEN)
        for c in self.config.cameras:
            self.cmb_source.addItem(f"📹 {c.name}", c.id)
        idx = self.cmb_source.findData(self.source)
        if idx < 0:
            self.source, idx = SCREEN, 0
        self.cmb_source.setCurrentIndex(idx)
        self.cmb_source.blockSignals(False)
        self._loading = True
        cur = self.cmb_var_source.currentData()
        self.cmb_var_source.clear()
        for i in range(self.cmb_source.count()):
            self.cmb_var_source.addItem(self.cmb_source.itemText(i), self.cmb_source.itemData(i))
        self.cmb_var_source.setCurrentIndex(max(0, self.cmb_var_source.findData(cur)))
        self._loading = False

    def _source_changed(self) -> None:
        src = self.cmb_source.currentData() or SCREEN
        self.set_source(src)

    def set_source(self, src: str, capture: bool = True) -> None:
        if src == self.source and self.frame is not None:
            return
        self.source = src
        idx = self.cmb_source.findData(src)
        if idx >= 0 and self.cmb_source.currentIndex() != idx:
            self.cmb_source.blockSignals(True)
            self.cmb_source.setCurrentIndex(idx)
            self.cmb_source.blockSignals(False)
        self.view.selection = None
        frame = self.frames.get(src)
        if frame is None and capture and src != SCREEN:
            frame = self._grab_camera(src)
        if frame is None:
            self.frame = None
            self.view.set_image(np.full((480, 640, 3), 40, np.uint8))
            self._redraw()
            return
        self._set_frame(frame)

    def _grab_camera(self, cam_id: str) -> Optional[np.ndarray]:
        from ..camera import grab_for_setup
        cam = self.config.camera(cam_id)
        if cam is None:
            return None
        try:
            return grab_for_setup(self.ctx.engine.cameras, cam)
        except Exception as exc:
            self._hint(f"{tr('Cámara sin imagen')}: {exc}", strong=True)
            return None

    def _open_cameras(self) -> None:
        from .camera_dialog import CamerasDialog
        before = self.config.model_copy(deep=True)
        dlg = CamerasDialog(self.config, self.ctx, self, select=None if self.source == SCREEN else self.source)
        if not dlg.exec():
            return
        changed = {c.id for c in self.config.cameras if before.camera(c.id) != c}
        for cid in changed | ({c.id for c in before.cameras} - {c.id for c in self.config.cameras}):
            self.frames.pop(cid, None)  # la imagen cambió (rotación, perspectiva…)
        target = self.source if self.source == SCREEN or self.config.camera(self.source) else SCREEN
        if not before.cameras and self.config.cameras:
            target = self.config.cameras[0].id  # primera cámara: se muestra de una vez
        self._refresh_sources()
        self._refresh_tree()
        if target != self.source or target in changed:
            self.frame = None
            self.set_source(target)

    def capture_hmi(self) -> None:
        if self.source != SCREEN:
            frame = self._grab_camera(self.source)
            if frame is not None:
                self._hint()
                self._set_frame(frame, fit=self.frames.get(self.source) is None)
            return
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
        gauge_marks = False
        for p in (self.config.pages if self.source == SCREEN else []):
            if p.anchor is not None and (show(p.parent) or p.id == self._current_page):
                regions.append((f"page:{p.id}", f"[{p.name}]", p.anchor, PAGE_COLOR))
        selected_vars = set(self._selected("var")) | {self._current_var}
        for v in self.config.variables:
            if not v.screen or v.source != self.source:
                continue
            if show(v.page) or v.id in selected_vars:
                # Solo se rotula la selección: en HMI densos las etiquetas se encimarían.
                label = v.name if v.id in selected_vars else ""
                regions.append((v.id, label, v.region, KIND_COLORS[v.kind]))
                if v.reader == "gauge" and v.kind != "selector" and v.gauge.calibrated and v.id in selected_vars:
                    g, r = v.gauge, v.region
                    import math
                    cx, cy = r.x + g.cx * r.w, r.y + g.cy * r.h
                    rad = g.radius * min(r.w, r.h)
                    pts = [(int(cx), int(cy), "●")]
                    for a, lab in ((g.angle_min, "min"), (g.angle_max, "máx")):
                        pts.append((int(cx + rad * math.cos(math.radians(a))), int(cy + rad * math.sin(math.radians(a))),
                                    lab))
                    self.view.set_markers(pts)
                    gauge_marks = True
        if self._gauge_marks and not gauge_marks:
            self.view.set_markers([])
        self._gauge_marks = gauge_marks
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
            it = QTreeWidgetItem([p.name, tr("pestaña") if p.anchor else tr("carpeta"), p.id])
            it.setData(0, ROLE, ("page", p.id))
            it.setFont(0, bold)
            it.setForeground(0, QBrush(QColor(PAGE_COLOR)))
            (parent_item.addChild(it) if parent_item else self.tree.addTopLevelItem(it))
            nodes[p.id] = it
            for c in self.config.children(p.id):
                add_page(c, it)

        for p in self.config.children(None):
            add_page(p, None)
        for c in self.config.cameras:
            it = QTreeWidgetItem([f"📹 {c.name}", tr("cámara"), c.id])
            it.setData(0, ROLE, ("cam", c.id))
            it.setFont(0, bold)
            it.setForeground(0, QBrush(QColor(CAMERA_COLOR)))
            self.tree.addTopLevelItem(it)
            nodes[("cam", c.id)] = it
        linked_sp = {v.setpoint_var for v in self.config.variables if v.setpoint_var}
        for v in self.config.variables:
            if v.kind == "setpoint" and v.id in linked_sp:
                continue  # se muestra bajo su medición
            parent = nodes.get(("cam", v.source), none) if v.on_camera else nodes.get(v.page, none)
            it = self._var_item(v)
            parent.addChild(it)
            if v.kind == "actual" and v.setpoint_var:
                sp = self.config.variable(v.setpoint_var)
                if sp:
                    it.addChild(self._var_item(sp))
                    it.setExpanded(True)
        for it in self._all_items():
            key = it.data(0, ROLE)
            if key[0] in ("page", "cam"):
                it.setExpanded(first or key in expanded)
        self.tree.blockSignals(False)
        self._refresh_combos()
        if select:
            self._select_key(select)
        else:
            self._redraw()

    def _var_item(self, v: Variable) -> QTreeWidgetItem:
        kind = tr(kind_label(v))
        if v.kind == "actual" and v.setpoint_var:
            kind = tr("medición + consigna")
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
        if key and key[0] == "cam":
            self.set_source(key[1])
            self.stack.setCurrentIndex(0)
        elif key and key[0] == "var":
            self._current_var = key[1]
            v = self.config.variable(key[1])
            if v is not None and v.screen and v.source != self.source:
                self.set_source(v.source)
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
        if self.source != SCREEN:
            return None  # en una cámara no hay pestañas: todo está siempre a la vista
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
        self.chk_auto.setChecked(v.ocr.auto)
        self._auto_widgets(v.ocr.auto)
        self.chk_trend.setChecked(v.trend)
        self.sp_state_thr.setValue(v.state_threshold)
        self.cmb_state_method.setCurrentIndex(max(0, self.cmb_state_method.findData(v.state_method)))
        self.chk_blink.setChecked(v.blink)
        self.sp_blink.setValue(v.blink_window_s)
        self.cmb_var_source.setCurrentIndex(max(0, self.cmb_var_source.findData(v.source)))
        self.cmb_reader.setCurrentIndex(max(0, self.cmb_reader.findData(v.reader)))
        self.sp_seg_digits.setValue(v.seg.digits or 0)
        self.cmb_seg_pol.setCurrentIndex(max(0, self.cmb_seg_pol.findData(v.seg.polarity)))
        self.sp_seg_slant.setValue(-31 if v.seg.slant is None else v.seg.slant)
        self.ed_g_min.setText(f"{v.gauge.value_min:g}")
        self.ed_g_max.setText(f"{v.gauge.value_max:g}")
        self.cmb_needle.setCurrentIndex(max(0, self.cmb_needle.findData(v.gauge.needle)))
        self.cmb_bar_dir.setCurrentIndex(max(0, self.cmb_bar_dir.findData(v.bar.direction)))
        self.ed_b_min.setText(f"{v.bar.value_min:g}")
        self.ed_b_max.setText(f"{v.bar.value_max:g}")
        self.cmb_bar_pol.setCurrentIndex(max(0, self.cmb_bar_pol.findData(v.bar.polarity)))
        self._reader_widgets(v)
        self._refresh_states(v)
        self.ed_formula.setText(v.formula)
        self.ed_formula.setEnabled(v.kind == "formula")
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
        source = self.cmb_var_source.currentData() or SCREEN
        reader = self.cmb_reader.currentData() if kind in ("actual", "setpoint") else "ocr"
        try:
            g_min = _opt_float(self.ed_g_min.text())
            g_max = _opt_float(self.ed_g_max.text())
            b_min = _opt_float(self.ed_b_min.text())
            b_max = _opt_float(self.ed_b_max.text())
            gauge = old.gauge.model_copy(update=dict(
                value_min=old.gauge.value_min if g_min is None else g_min,
                value_max=old.gauge.value_max if g_max is None else g_max, needle=self.cmb_needle.currentData()))
            bar = BarOptions(direction=self.cmb_bar_dir.currentData(),
                             value_min=old.bar.value_min if b_min is None else b_min,
                             value_max=old.bar.value_max if b_max is None else b_max,
                             polarity=self.cmb_bar_pol.currentData())
            seg = SevenSegOptions(digits=self.sp_seg_digits.value() or None, polarity=self.cmb_seg_pol.currentData(),
                                  slant=None if self.sp_seg_slant.value() < -30 else self.sp_seg_slant.value())
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
                               clear_border=self.chk_border.isChecked(), auto=self.chk_auto.isChecked()),
                trend=self.chk_trend.isChecked(), states=list(old.states), formula=self.ed_formula.text().strip(),
                state_threshold=self.sp_state_thr.value(), state_method=self.cmb_state_method.currentData(),
                color_states=[c.model_copy() for c in old.color_states], blink=self.chk_blink.isChecked(),
                blink_window_s=self.sp_blink.value(), source=source, reader=reader, seg=seg, gauge=gauge, bar=bar)
            if var.on_camera:
                var.page = None  # en una cámara no hay pestañas
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
        structural = (old.kind, old.page, old.setpoint_var, old.id, old.source, old.reader, old.state_method) != \
            (var.kind, var.page, var.setpoint_var, var.id, var.source, var.reader, var.state_method)
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
        self._auto_widgets(self.chk_auto.isChecked())
        self._reader_widgets(var)
        if (old.reader, old.state_method, old.blink, old.seg, old.bar, old.gauge) != \
                (var.reader, var.state_method, var.blink, var.seg, var.bar, var.gauge):
            self._refresh_states(var)
            self._test_ocr()

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
        source = self.source if kind != "formula" else SCREEN
        return Variable(id=vid, name=name, kind=kind, region=region, page=None if source != SCREEN else page,
                        source=source, trend=kind in ("actual", "formula"))

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

    # --- indicadores físicos --------------------------------------------------------------------------
    def _new_indicator(self, what: str) -> None:
        r = self._need_selection()
        if r is None:
            return
        titles = {"lamp": "Nueva luz / LED", "sevenseg": "Nuevo display de 7 segmentos", "gauge": "Nueva aguja",
                  "bar": "Nueva barra de nivel"}
        name, ok = QInputDialog.getText(self, tr(titles[what]), tr("Nombre:"))
        if not ok or not name.strip():
            return
        page = self._context_page()
        if what == "lamp":
            var = self._make_var("selector", name.strip(), r, page)
            var.state_method, var.blink, var.trend = "color", True, False
        else:
            var = self._make_var("actual", name.strip(), r, page)
            var.reader = what
        self.config.variables.append(var)
        self._refresh_tree(("var", var.id))
        if what == "lamp":
            self._hint("Ahora enseña sus colores: con la luz apagada pulsa «Capturar estado actual como…» → "
                       "«Apagado»; enciéndela y repite con su color.", strong=True)
        elif what == "gauge":
            self._start_gauge_cal()

    def _new_andon(self) -> None:
        r = self._need_selection()
        if r is None:
            return
        names, ok = QInputDialog.getText(
            self, tr("Torre andon"), tr("Colores de arriba hacia abajo, separados por coma:"),
            text=tr("Rojo, Ámbar, Verde"))
        colors = [c.strip() for c in names.split(",") if c.strip()] if ok else []
        if not colors:
            return
        vertical = r.h >= r.w
        n = len(colors)
        created = []
        for i, color in enumerate(colors):
            if vertical:
                sub = Rect(x=r.x, y=r.y + int(i * r.h / n), w=r.w, h=max(4, int(r.h / n)))
            else:
                sub = Rect(x=r.x + int(i * r.w / n), y=r.y, w=max(4, int(r.w / n)), h=r.h)
            var = self._make_var("selector", f"Andon {color.lower()}", sub, self._context_page())
            var.state_method, var.blink, var.trend = "color", True, False
            img = crop(self.frame, sub)
            from ..vision.indicators import lamp_feature
            var.color_states = [ColorState(name="Apagado", lab=[40.0, 128.0, 128.0])]
            if img.size > 4:
                feat = lamp_feature(img)
                if feat[0] > 120:  # la luz se ve encendida: su color queda enseñado
                    var.color_states.append(ColorState(name=color, lab=feat))
                else:
                    var.color_states[0].lab = feat
            self.config.variables.append(var)
            created.append(var)
        self._refresh_tree(("var", created[0].id))
        self._hint("Torre creada. Enseña cada luz: «Capturar estado actual como…» con la luz apagada («Apagado») "
                   "y encendida (su color).", strong=True)

    def _reader_widgets(self, v: Variable) -> None:
        numeric = v.kind in ("actual", "setpoint")
        self.cmb_reader.setEnabled(numeric)
        self.seg_box.setVisible(numeric and v.reader == "sevenseg")
        self.gauge_box.setVisible(numeric and v.reader == "gauge")
        self.bar_box.setVisible(numeric and v.reader == "bar")
        for w, show in ((self.cmb_page, not v.on_camera), (self.cmb_var_source, v.kind != "formula"),
                        (self.cmb_reader, numeric)):
            w.setVisible(show)
            lbl = w.parentWidget().layout().labelForField(w) if w.parentWidget() and \
                isinstance(w.parentWidget().layout(), QFormLayout) else None
            if lbl is not None:
                lbl.setVisible(show)
        ocr_opts = v.reader == "ocr" or not numeric
        for w in (self.cmb_invert, self.sp_scale, self.sp_thr, self.chk_border, self.chk_auto):
            w.setVisible(ocr_opts)
            lbl = w.parentWidget().layout().labelForField(w) if w.parentWidget() and \
                isinstance(w.parentWidget().layout(), QFormLayout) else None
            if lbl is not None:
                lbl.setVisible(ocr_opts)
        color = v.kind == "selector" and v.state_method == "color"
        self.chk_blink.setEnabled(color)
        self.sp_blink.setEnabled(color and v.blink)
        self.sp_state_thr.setEnabled(not color)
        g = v.gauge
        self.lbl_gauge.setText(tr("lista") + f" · {g.angle_min:.0f}° → {g.angle_max:.0f}°" if g.calibrated
                               else "<span style='color:#e53935'>" + tr("sin calibrar") + "</span>")

    def _start_gauge_cal(self) -> None:
        v = self.config.variable(self._current_var) if self._current_var else None
        if v is None or v.reader != "gauge" or self.frame is None:
            return
        self._gauge_cal = []
        self.view.point_mode = True
        self._hint("① Clic en el CENTRO (eje) de la aguja · Esc para cancelar", strong=True)

    def _gauge_point(self, x: int, y: int) -> None:
        if self._gauge_cal is None:
            return
        self._gauge_cal.append((x, y))
        steps = ["② Clic en la marca del valor MÍNIMO de la escala", "③ Clic en la marca del valor MÁXIMO"]
        if len(self._gauge_cal) < 3:
            self._hint(steps[len(self._gauge_cal) - 1], strong=True)
            return
        pts, self._gauge_cal = self._gauge_cal, None
        self.view.point_mode = False
        self._hint()
        v = self.config.variable(self._current_var) if self._current_var else None
        if v is None:
            return
        from ..vision.indicators import calibrate_gauge
        r = v.region
        rel = [(px - r.x, py - r.y) for px, py in pts]
        v.gauge = calibrate_gauge(rel[0], rel[1], rel[2], (r.w, r.h), v.gauge)
        self._reader_widgets(v)
        self._redraw()
        self._test_ocr()

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
        if event.key() == Qt.Key_Escape and self._gauge_cal is not None:
            self._gauge_cal = None
            self.view.point_mode = False
            self._hint()
            return
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
        for t in self.config.tours:
            t.steps = [st for st in t.steps if st.page not in page_ids]
            for attr in ("start_page", "return_page", "off_page"):
                if getattr(t, attr) in page_ids:
                    setattr(t, attr, None)
        self.tour_tab.reload()
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
        if v.state_method == "color":
            from PySide6.QtGui import QPixmap
            for cs in v.color_states:
                it = QListWidgetItem(cs.name)
                pm = QPixmap(48, 24)
                b, g, r = lab_to_bgr(cs.lab)
                pm.fill(QColor(r, g, b))
                it.setIcon(QIcon(pm))
                self.lst_states.addItem(it)
            self.lst_states.setIconSize(QSize(48, 24))
            return
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
        if v.state_method == "color":
            from ..vision.indicators import lamp_feature
            feat = lamp_feature(crop(self.frame, v.region))
            v.color_states = [c for c in v.color_states if c.name != name] + [ColorState(name=name, lab=feat)]
            self._refresh_states(v)
            self._test_ocr()
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
        v.color_states = [c for c in v.color_states if c.name != it.text()]
        self.selector_images.get(v.id, {}).pop(it.text(), None)
        self._refresh_states(v)

    def _train_behavior(self) -> None:
        from .behavior_dialog import BehaviorDialog
        pre = [vid for vid in self._selected("var") if (v := self.config.variable(vid)) and v.numeric]
        BehaviorDialog(self.ctx, self, preselect=pre, config=self.config).exec()
        self.ctx.engine.save_profile()

    def _new_formula(self) -> None:
        page = self._context_page()
        name, ok = QInputDialog.getText(self, "Nueva fórmula", "Nombre de la variable calculada:")
        if not ok or not name.strip():
            return
        ids = ", ".join(v.id for v in self.config.variables if v.numeric)
        expr, ok = QInputDialog.getText(self, "Fórmula", f"Expresión (usa los ID):\n{ids[:600]}")
        if not ok or not expr.strip():
            return
        var = self._make_var("formula", name.strip(), Rect(x=0, y=0, w=1, h=1), page)
        var.formula = expr.strip()
        self.config.variables.append(var)
        self._refresh_tree(("var", var.id))

    def _test_formula(self, v: Variable) -> None:
        from ..analysis.formula import FormulaError, compile_formula
        self.lbl_crop.clear()
        self.lbl_bin.clear()
        try:
            f = compile_formula(v.formula, {x.id for x in self.config.variables} - {v.id})
        except FormulaError as exc:
            self.lbl_result.setText(f"<span style='color:#e53935'>{exc}</span>")
            return
        snap = self.ctx.engine.last
        values = {}
        if snap is not None:
            values = {k: st.reading.value for k, st in snap.statuses.items() if st.reading.value is not None}
        missing = [d for d in f.deps if d not in values]
        if missing:
            self.lbl_result.setText(f"Fórmula válida. Usa: {', '.join(f.deps)}. Para ver el resultado "
                                    f"inicia el monitoreo (faltan: {', '.join(missing)}).")
            return
        res = f.evaluate(values)
        self.lbl_result.setText(f"Fórmula válida → <b>{'no válido' if res is None else f'{res:.6g}'}</b> "
                                f"con los valores actuales ({', '.join(f'{d}={values[d]:g}' for d in f.deps)})")

    def _test_ocr(self) -> None:
        v = self.config.variable(self._current_var) if self._current_var else None
        if v is not None and v.kind == "formula":
            self._test_formula(v)
            return
        if v is None or self.frame is None:
            return
        img = crop(self.frame, v.region)
        if v.kind == "selector" and v.state_method == "color":
            from ..vision.indicators import classify_color, color_distance, lamp_feature
            self.lbl_crop.setPixmap(to_pixmap(img).scaledToHeight(min(80, max(20, img.shape[0] * 2))))
            self.lbl_bin.clear()
            if not v.color_states:
                self.lbl_result.setText(tr("Enseña al menos dos estados: apagado y encendido."))
                return
            feat = lamp_feature(img)
            state, score = classify_color(feat, v.color_states)
            dists = ", ".join(f"{c.name}: {color_distance(feat, c.lab):.0f}" for c in v.color_states)
            color = "#43a047" if score >= 0.35 else "#e53935"
            extra = "<br>" + tr("El parpadeo se detecta durante el monitoreo (varios cuadros por segundo).") \
                if v.blink else ""
            self.lbl_result.setText(f"{tr('Estado detectado')}: <b style='color:{color}'>{state}</b> · "
                                    f"{tr('distancia de color')}: {dists}{extra}")
            return
        if v.kind in ("actual", "setpoint") and v.reader != "ocr":
            self._test_indicator(v, img)
            return
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
        if v.ocr.auto:
            self._test_robust(v, img)
            return
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

    def _test_indicator(self, v: Variable, img: np.ndarray) -> None:
        from ..vision import indicators, sevenseg
        self.lbl_crop.setPixmap(to_pixmap(img).scaledToHeight(min(90, max(20, img.shape[0] * 2))))
        self.lbl_bin.clear()
        if v.reader == "sevenseg":
            r = sevenseg.decode(img, v.seg.polarity, v.seg.slant, v.seg.digits, debug=True)
            if r.debug is not None:
                self.lbl_bin.setPixmap(to_pixmap(r.debug).scaledToHeight(min(90, max(20, r.debug.shape[0]))))
            value = parse_number(r.text, v) if r.text else None
            ok = value is not None and r.confidence >= 0.55
            color = "#43a047" if ok else "#e53935"
            shown = "—" if value is None else f"{value:g}"
            self.lbl_result.setText(
                f"{tr('Display')}: «{r.text}» → <b style='color:{color}'>{shown}</b> · {tr('confianza')} "
                f"{r.confidence:.2f} · {tr('inclinación')} {r.slant:.0f}° · "
                f"{tr('segmentos encendidos') if r.polarity == 'light' else tr('segmentos oscuros')}"
                + ("" if ok else "<br>" + tr("Ajusta la región para que cubra solo los dígitos, con poco margen.")))
            return
        if v.reader == "gauge":
            if not v.gauge.calibrated:
                self.lbl_result.setText(tr("Calibra la aguja: centro, marca mínima y marca máxima."))
                return
            r = indicators.gauge_value(img, v.gauge)
            color = "#43a047" if r.confidence >= 0.3 else "#e53935"
            self.lbl_result.setText(f"{tr('Aguja')} {r.angle:.0f}° → <b style='color:{color}'>{r.value:.4g}</b> "
                                    f"{v.unit} · {tr('confianza')} {r.confidence:.2f}")
            return
        r = indicators.bar_value(img, v.bar)
        if r.value is None:
            self.lbl_result.setText(f"<b style='color:#e53935'>{tr('Nivel no distinguible')}</b>")
            return
        color = "#43a047" if r.confidence >= 0.3 else "#e53935"
        self.lbl_result.setText(f"{tr('Nivel')} {100 * r.fraction:.0f} % → <b style='color:{color}'>{r.value:.4g}</b> "
                                f"{v.unit} · {tr('confianza')} {r.confidence:.2f}")

    def _auto_widgets(self, auto: bool) -> None:
        for w in (self.cmb_invert, self.sp_scale, self.sp_thr):
            w.setEnabled(not auto)

    def _test_robust(self, v: Variable, img: np.ndarray) -> None:
        from ..ocr.robust import RobustReader, prepare
        engine = self._ocr()
        reader = RobustReader(engine)
        try:
            if v.kind == "text":
                res = reader.read_text(img, v)
            else:
                res = reader.read_number(img, v, None, lambda _: True, exhaustive=True)
        except Exception as exc:
            self.lbl_result.setText(f"<span style='color:#e53935'>Error OCR: {exc}</span>")
            return
        if res.variant is not None:
            prep = prepare(img, res.variant[0], res.variant[1], clear=v.ocr.clear_border, smooth=res.variant[2])
            if prep is not None:
                self.lbl_bin.setPixmap(to_pixmap(prep).scaledToHeight(min(80, max(20, prep.shape[0]))))
        if v.kind == "text":
            self.lbl_result.setText(f"Motor {engine.name} (automático): texto «{res.text}»")
            return
        if res.value is None:
            self.lbl_result.setText(f"<b style='color:#e53935'>Sin lectura válida</b> en {res.tried} variantes. "
                                    "Ajusta la región para que cubra solo el número.")
            return
        total = sum(res.candidates.values())
        agree = res.candidates.get(res.value, 0)
        pct = 100 * agree / max(total, 1)
        color = "#43a047" if pct >= 60 else ("#f9a825" if pct >= 35 else "#e53935")
        others = ", ".join(f"{k:g}×{n}" for k, n in res.candidates.items() if k != res.value)
        self.lbl_result.setText(
            f"Motor {engine.name} (automático): <b style='color:{color}'>{res.value:g}</b> · "
            f"{agree} de {res.tried} variantes coinciden ({pct:.0f} %)"
            + (f" · otras lecturas: {others}" if others else "")
            + ("" if pct >= 35 else "<br>Lectura débil: ajusta la región (solo el número, sin la unidad)."))

    def _diagnose(self) -> None:
        from .ocr_diagnosis import DiagnosisDialog
        if self.frame is None:
            QMessageBox.information(self, "Captura", "Primero captura la pantalla del HMI.")
            return
        DiagnosisDialog(self.config, self.frame, self._ocr(), self._visible_pages(), self).exec()

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
    def _commit_all(self) -> list[str]:
        """Pasa a la configuración lo que está en los formularios; devuelve los problemas de las pestañas."""
        self._commit_general()
        return self.tour_tab.commit() + self.oee_tab.commit() + self.report_tab.commit()

    def _fingerprint(self) -> tuple:
        return (self.config.model_dump_json(), sorted(self.tour_tab.patches), sorted(self.anchors),
                sorted((vid, tuple(sorted(imgs))) for vid, imgs in self.selector_images.items()),
                sorted(self.removed_pages))

    def has_changes(self) -> bool:
        self._commit_all()
        return self._fingerprint() != self._baseline

    def reject(self) -> None:
        """Cancelar / cerrar la ventana: si hay cambios sin guardar se pregunta antes de descartarlos."""
        if self.tour_tab.recording is not None:
            self.tour_tab.stop_recording()
        if self.has_changes():
            ans = QMessageBox.question(
                self, tr("Cambios sin guardar"),
                tr("Hay cambios sin guardar (recorridos, variables u otros ajustes).\n\n"
                   "¿Salir sin guardar? Se perderán los cambios."),
                QMessageBox.Discard | QMessageBox.Cancel, QMessageBox.Cancel)
            if ans != QMessageBox.Discard:
                return
        super().reject()

    def _save(self) -> None:
        problems = self._commit_all()
        problems = self.config.validate_references() + problems
        missing = [p.name for p in self.config.pages if p.anchor is not None and p.id not in self.anchors]
        if missing:
            problems.append(f"Pestañas sin imagen ancla: {', '.join(missing)}")
        no_patch = [c for c in self.config.all_tour_clicks() if c.id not in self.tour_tab.patches]
        if no_patch:
            problems.append(f"Recorrido: {len(no_patch)} clics sin imagen del botón; vuelve a grabarlos")
        critical = self.config.critical_problems()
        if critical:
            # Con estos errores el monitoreo no puede funcionar: hay que corregirlos antes de guardar.
            QMessageBox.warning(self, tr("No se puede guardar"), tr("Corrige primero:") + "\n\n" + "\n".join(critical))
            return
        if problems:
            # El resto no impide guardar: lo incompleto (p. ej. un recorrido sin regreso) no funciona
            # hasta corregirlo, pero no se pierde el trabajo.
            ans = QMessageBox.question(
                self, tr("Revisa la configuración"),
                tr("Se encontraron estos puntos pendientes:") + "\n\n• " + "\n• ".join(problems) + "\n\n" +
                tr("¿Guardar de todos modos? Lo que esté incompleto no funcionará hasta corregirlo."),
                QMessageBox.Save | QMessageBox.Cancel, QMessageBox.Save)
            if ans != QMessageBox.Save:
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
        used = {c.id for c in self.config.all_tour_clicks()}
        for cid, img in self.tour_tab.patches.items():
            if cid in used:
                save_png(ws.click_patch_file(cid), img)
        for f in ws.clicks_dir.glob("*.png"):
            if f.stem not in used:
                f.unlink()
        screen = self.frames.get(SCREEN)
        if screen is not None:
            h, w = screen.shape[:2]
            self.config.general.screen_size = [int(w), int(h)]  # resolución con la que se marcaron las regiones
        ws.save_config(self.config)
        self.accept()
