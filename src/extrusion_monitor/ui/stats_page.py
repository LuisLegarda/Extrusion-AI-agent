"""Análisis estadístico: navegador de análisis (crear, abrir, cambiar, duplicar, eliminar) y su resultado.

Los análisis se guardan en `<datos>/analisis/analisis.json` (tipo, datos pedidos, opciones y estilo) y se
recalculan con el historial al abrirlos. Título del análisis y de cada gráfica y colores de las series se
pueden cambiar.
"""
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QDateTime, QSize, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QColorDialog, QComboBox, QDateTimeEdit, QDialog, QDialogButtonBox,
    QDoubleSpinBox, QFileDialog, QFormLayout, QFrame, QGridLayout, QGroupBox, QHBoxLayout, QInputDialog, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPushButton, QScrollArea, QSpinBox, QSplitter, QVBoxLayout,
    QWidget,
)

from ..analysis.dataset import GROUPS, DataRequest, fetch, problems_table
from ..i18n import tr
from . import icons, theme
from .stats_render import BAR_STATS, PARETO_BY, PARETO_MEASURES, PARETO_SOURCES, RENDERERS, Render

# tipo -> (nombre, grupo, descripción, ícono, variables: "multi" | "one" | "xyz" | "reg" | "none")
TYPES = {
    "describe": ("Estadística descriptiva", "Estadística básica",
                 "Media, desviación estándar, varianza, mínimo y máximo, rango, mediana, cuartiles, suma de "
                 "cuadrados, asimetría y curtosis, por variable y grupo.", "variables", "multi"),
    "compare": ("Comparar grupos (t / ANOVA)", "Estadística básica",
                "¿Hay diferencia real entre turnos, días, meses, operadores o recetas? Gráfica de intervalos, ANOVA "
                "de un factor y prueba t.", "spc", "multi"),
    "normality": ("Prueba de normalidad", "Estadística básica",
                  "Gráfica de probabilidad normal y prueba de Anderson-Darling.", "behavior", "one"),
    "histogram": ("Histograma", "Gráficas",
                  "Distribución con curva normal; varias variables o grupos superpuestos o en paneles.", "spc", "multi"),
    "boxplot": ("Gráfica de caja (boxplot)", "Gráficas", "Mediana, cuartiles y atípicos por variable o grupo.",
                "spc", "multi"),
    "timeseries": ("Gráfica de tiempo", "Gráficas", "Valores en el tiempo de una o varias variables.", "trends",
                   "multi"),
    "bar": ("Gráfica de barras", "Gráficas", "Media, mediana, suma, conteo o desviación por grupo.", "spc", "multi"),
    "capability": ("Análisis de capacidad", "Calidad",
                   "Cp, Cpk, Pp, Ppk, Cpm y PPM con histograma y curvas dentro y general.", "kpi", "one"),
    "sixpack": ("Capacidad Sixpack", "Calidad",
                "Cartas I y MR, últimas 25 observaciones, histograma, probabilidad normal y gráfica de capacidad.",
                "kpi", "one"),
    "control": ("Carta de control (I-MR / X̄-R)", "Calidad",
                "Límites de control y puntos fuera de control o corridas.", "trends", "one"),
    "pareto": ("Pareto de paros y defectos", "Paros y defectos",
               "Paros o defectos capturados por causa, categoría, operador, turno, día o mes.", "problems", "none"),
    "matrix": ("Multivariable (matriz y correlación)", "Relaciones",
               "Matriz de dispersión y correlación de Pearson entre varias variables.", "corr", "multi"),
    "contour": ("Gráfica de contorno", "Relaciones", "Cómo cambia una variable (Z) según otras dos (X, Y).",
                "corr", "xyz"),
    "regression": ("Regresión y simulación de respuesta", "Relaciones",
                   "Modelo de la respuesta según los factores (lineal, cuadrático, interacciones), significancia y "
                   "simulador: mueve los factores y ve la respuesta esperada.", "control", "reg"),
}
TYPE_GROUPS = ["Estadística básica", "Gráficas", "Calidad", "Paros y defectos", "Relaciones"]
PRESETS = [("Últimas 8 h", 8 * 3600), ("Últimas 24 h", 86400), ("Últimos 7 días", 7 * 86400),
           ("Últimos 30 días", 30 * 86400), ("Últimos 90 días", 90 * 86400), ("Personalizado", -1)]
MAX_VARS = 8
SCHEDULES = [("", "No programar"), ("shift", "Cada turno (turno anterior)"), ("day", "Cada día (día anterior)"),
             ("week", "Cada semana (semana anterior)")]


def project_file(home: Path) -> Path:
    return Path(home) / "analisis" / "analisis.json"


def load_project(home: Path) -> list[dict]:
    try:
        data = json.loads(project_file(home).read_text(encoding="utf-8"))
        return [r for r in data.get("analyses", []) if isinstance(r, dict) and r.get("type") in TYPES]
    except (OSError, ValueError, AttributeError):
        return []


def load_schedule_state(home: Path) -> dict:
    try:
        return dict(json.loads(project_file(home).read_text(encoding="utf-8")).get("schedule_state") or {})
    except (OSError, ValueError, AttributeError):
        return {}


def save_project(home: Path, records: list[dict], schedule_state: Optional[dict] = None) -> None:
    f = project_file(home)
    f.parent.mkdir(parents=True, exist_ok=True)
    state = load_schedule_state(home) if schedule_state is None else schedule_state
    tmp = f.with_suffix(".json.tmp")
    tmp.write_text(json.dumps({"analyses": records, "schedule_state": state}, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    tmp.replace(f)


def build_render(ctx, rec: dict) -> tuple[Render, int]:
    """Calcula un análisis con el historial y devuelve su área de resultados (y cuántos datos usó)."""
    cfg = ctx.engine.config
    p = rec.get("params", {})
    from ..personnel import Personnel
    shifts = Personnel.load(ctx.workspace.home).shifts
    req = DataRequest.from_dict(p)
    data = fetch(ctx.engine.historian, cfg, req, shifts) if rec["type"] != "pareto" else []
    extra = {}
    if rec["type"] == "pareto":
        recs = problems_table(ctx.engine.historian, req.since, req.until, p.get("source", "downtime"), shifts,
                              cfg.oee.shift_starts)
        if req.operator:
            recs = [r for r in recs if r.get("operator") == req.operator]
        if req.shift:
            recs = [r for r in recs if r.get("shift") == req.shift]
        if req.recipe:
            recs = [r for r in recs if r.get("recipe") == req.recipe]
        if req.line:
            recs = [r for r in recs if r.get("line") == req.line]
        extra["problems"] = recs
    R = Render(rec, data, ctx, extra)
    if rec["type"] != "pareto" and not any(len(v.y) for v in data):
        R.empty(tr("No hay datos de esas variables en el periodo elegido (con los filtros aplicados)."))
    else:
        try:
            RENDERERS[rec["type"]](R)
        except Exception as e:  # un análisis con datos raros no debe tumbar la página
            import logging
            logging.getLogger(__name__).exception("análisis %s", rec["type"])
            R.empty(tr("No se pudo calcular: {e}", e=e))
    return R, sum(len(v.y) for v in data)


def subtitle(rec: dict) -> str:
    p = rec.get("params", {})
    rng = time.strftime("%d/%m/%Y %H:%M", time.localtime(p.get("since", 0))) + " → " + \
        time.strftime("%d/%m/%Y %H:%M", time.localtime(p.get("until", 0)))
    filters = [f"{tr(lb)}: {p[k]}" for k, lb in (("line", "Línea"), ("shift", "Turno"), ("operator", "Operador"),
                                                 ("recipe", "Receta")) if p.get(k)]
    return f"{tr(TYPES[rec['type']][0])} · {rng}" + (" · " + " · ".join(filters) if filters else "")


def default_title(rec: dict, config) -> str:
    p = rec.get("params", {})
    name = TYPES[rec["type"]][0]
    if rec["type"] == "pareto":
        return f"{tr(name)} — {tr(dict(PARETO_SOURCES)[p.get('source', 'downtime')])}"
    ids = p.get("vars") or [x for x in (p.get("y"), p.get("z")) if x]
    labels = [config.variable(v).name for v in ids if config.variable(v)]
    by = f" · {tr('por')} {tr(GROUPS[p['group_by']]).lower()}" if p.get("group_by") else ""
    return f"{tr(name)} — {', '.join(labels[:3])}{'…' if len(labels) > 3 else ''}{by}"


# --- diálogo: nuevo análisis / cambiar el análisis --------------------------------------------------------


class AnalysisDialog(QDialog):
    def __init__(self, ctx, record: Optional[dict] = None, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.engine = ctx.engine
        self.cfg = ctx.engine.config
        self.setWindowTitle(tr("Cambiar el análisis") if record else tr("Nuevo análisis"))
        scr = QApplication.primaryScreen()
        avail = scr.availableGeometry() if scr is not None else None
        self.resize(min(1180, int(avail.width() * 0.92)) if avail else 1100,
                    min(760, int(avail.height() * 0.9)) if avail else 720)
        rec = record or {"type": "histogram", "params": {}}
        p = rec.get("params", {})
        root = QHBoxLayout(self)
        # tipos
        left = QVBoxLayout()
        left.addWidget(QLabel(f"<b>{tr('Tipo de análisis')}</b>"))
        self.lst_type = QListWidget()
        self.lst_type.setIconSize(QSize(18, 18))
        for g in TYPE_GROUPS:
            head = QListWidgetItem(tr(g).upper())
            head.setFlags(Qt.NoItemFlags)
            head.setForeground(QColor(theme.c("muted")))
            self.lst_type.addItem(head)
            for key, (name, grp, _d, ic, _v) in TYPES.items():
                if grp == g:
                    it = QListWidgetItem(icons.icon(ic, theme.c("nav_icon"), theme.c("accent_text")), "  " + tr(name))
                    it.setData(Qt.UserRole, key)
                    self.lst_type.addItem(it)
        self.lst_type.setMinimumWidth(230)
        self.lst_type.setMaximumWidth(300)
        self.lst_type.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.lst_type.setTextElideMode(Qt.ElideRight)
        self.lst_type.currentItemChanged.connect(lambda *_: self._type_changed())
        left.addWidget(self.lst_type, 1)
        self.lbl_desc = QLabel()
        self.lbl_desc.setWordWrap(True)
        self.lbl_desc.setStyleSheet(f"color:{theme.c('text2')};")
        left.addWidget(self.lbl_desc)
        root.addLayout(left, 1)
        # opciones
        right = QVBoxLayout()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)  # todo se acomoda a lo ancho
        body = QWidget()
        self.form = QVBoxLayout(body)
        scroll.setWidget(body)
        right.addWidget(scroll, 1)
        root.addLayout(right, 3)

        # datos
        box = QGroupBox(tr("Datos"))
        fl = QFormLayout(box)
        self.cmb_preset = QComboBox()
        for label, secs in PRESETS:
            self.cmb_preset.addItem(tr(label), secs)
        self.ed_from, self.ed_to = QDateTimeEdit(), QDateTimeEdit()
        for ed in (self.ed_from, self.ed_to):
            ed.setDisplayFormat("dd/MM/yyyy HH:mm")
            ed.setCalendarPopup(True)
        now = self.engine.clock()
        since, until = float(p.get("since") or now - 86400), float(p.get("until") or now)
        self.ed_from.setDateTime(QDateTime.fromSecsSinceEpoch(int(since)))
        self.ed_to.setDateTime(QDateTime.fromSecsSinceEpoch(int(until)))
        self.cmb_preset.setCurrentIndex(len(PRESETS) - 1 if record else 1)
        self.cmb_preset.currentIndexChanged.connect(self._preset)
        for ed in (self.ed_from, self.ed_to):
            ed.dateTimeChanged.connect(lambda _: self.cmb_preset.setCurrentIndex(len(PRESETS) - 1)
                                       if not self._presetting else None)
        self._presetting = False
        fl.addRow(tr("Periodo"), self.cmb_preset)
        rng = QHBoxLayout()
        rng.addWidget(self.ed_from)
        rng.addWidget(QLabel("→"))
        rng.addWidget(self.ed_to)
        fl.addRow(tr("Desde / hasta"), rng)
        self.fleet = bool(getattr(ctx, "fleet", False))  # dashboard global: datos de varias líneas
        self.cmb_group = QComboBox()
        for k, label in GROUPS.items():
            if k == "line" and not self.fleet:
                continue
            self.cmb_group.addItem(tr(label), k)
        self.cmb_group.setCurrentIndex(max(0, self.cmb_group.findData(p.get("group_by", ""))))
        fl.addRow(tr("Agrupar por"), self.cmb_group)
        from ..personnel import Personnel
        people = Personnel.load(ctx.workspace.home)
        self.cmb_shift = QComboBox()
        self.cmb_shift.addItem(tr("Todos"), "")
        shift_names = [s.name for s in people.shifts] or \
            [f"Turno {i + 1}" for i in range(len(self.cfg.oee.shift_starts or []))]
        for n in shift_names:
            self.cmb_shift.addItem(n, n)
        self.cmb_shift.setCurrentIndex(max(0, self.cmb_shift.findData(p.get("shift", ""))))
        self.cmb_op = QComboBox()
        self.cmb_op.addItem(tr("Todos"), "")
        for n in people.names():
            self.cmb_op.addItem(n, n)
        self.cmb_op.setCurrentIndex(max(0, self.cmb_op.findData(p.get("operator", ""))))
        self.cmb_recipe = QComboBox()
        self.cmb_recipe.addItem(tr("Todas"), "")
        for n in ctx.recipes.names():
            self.cmb_recipe.addItem(n, n)
        self.cmb_recipe.setCurrentIndex(max(0, self.cmb_recipe.findData(p.get("recipe", ""))))
        self.cmb_line = QComboBox()
        self.cmb_line.addItem(tr("Todas"), "")
        for n in (ctx.lines if self.fleet else []):
            self.cmb_line.addItem(n, n)
        self.cmb_line.setCurrentIndex(max(0, self.cmb_line.findData(p.get("line", ""))))
        # filtros en dos columnas: no se recortan en ventanas angostas
        filt = QGridLayout()
        pairs = [(tr("Turno"), self.cmb_shift), (tr("Operador"), self.cmb_op), (tr("Receta"), self.cmb_recipe)]
        if self.fleet:
            pairs.insert(0, (tr("Línea"), self.cmb_line))
        for k, (lb, w) in enumerate(pairs):  # un filtro por renglón: nunca se recortan
            w.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
            w.setMinimumContentsLength(10)
            filt.addWidget(QLabel(lb), k, 0)
            filt.addWidget(w, k, 1)
        filt.setColumnStretch(1, 1)
        fl.addRow(tr("Solo"), filt)
        self.form.addWidget(box)

        # variables
        self.box_vars = QGroupBox(tr("Variables"))
        vl = QVBoxLayout(self.box_vars)
        self.lst_vars = QListWidget()
        self.lst_vars.setSelectionMode(QAbstractItemView.NoSelection)
        self.lst_vars.setMinimumHeight(170)
        sel = set(p.get("vars") or [])
        self.numeric = [v for v in self.cfg.variables if v.numeric]
        for v in self.numeric:
            it = QListWidgetItem(self.cfg.var_label(v) + (f" [{v.unit}]" if v.unit else ""))
            it.setData(Qt.UserRole, v.id)
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Checked if v.id in sel else Qt.Unchecked)
            self.lst_vars.addItem(it)
        vl.addWidget(self.lst_vars)
        self.cmb_one = self._var_combo(p.get("vars", [None])[0] if p.get("vars") else None)
        self.row_one = self._row(tr("Variable"), self.cmb_one)
        vl.addWidget(self.row_one)
        self.cmb_x, self.cmb_y, self.cmb_z = (self._var_combo(p.get(k)) for k in ("x", "y", "z"))
        self.row_xyz = QWidget()
        xl = QFormLayout(self.row_xyz)
        xl.setContentsMargins(0, 0, 0, 0)
        for lb, w in (("X", self.cmb_x), ("Y", self.cmb_y), (tr("Z (respuesta)"), self.cmb_z)):
            xl.addRow(lb, w)
        vl.addWidget(self.row_xyz)
        self.cmb_resp = self._var_combo(p.get("y"))
        self.row_resp = self._row(tr("Respuesta (Y)"), self.cmb_resp)
        vl.addWidget(self.row_resp)
        self.lbl_vars = QLabel()
        self.lbl_vars.setStyleSheet(f"color:{theme.c('muted')};")
        vl.addWidget(self.lbl_vars)
        self.form.addWidget(self.box_vars)

        # opciones por tipo
        self.box_opt = QGroupBox(tr("Opciones"))
        ol = QFormLayout(self.box_opt)
        self.rows: dict[str, QWidget] = {}

        def opt(key, label, w):
            row = self._row("", w) if label is None else w
            ol.addRow(label or "", row)
            self.rows[key] = (ol.labelForField(row), row)
            return w

        self.sp_lsl, self.sp_usl, self.sp_target = (self._num(p.get(k)) for k in ("lsl", "usl", "target"))
        self.chk_lsl, self.chk_usl, self.chk_target = (QCheckBox() for _ in range(3))
        for chk, k in ((self.chk_lsl, "lsl"), (self.chk_usl, "usl"), (self.chk_target, "target")):
            chk.setChecked(p.get(k) is not None)
        spec = QWidget()
        sl = QGridLayout(spec)
        sl.setContentsMargins(0, 0, 0, 0)
        for k, (chk, lb, sp) in enumerate(((self.chk_lsl, "LIE", self.sp_lsl), (self.chk_target, tr("Objetivo"),
                                                                                 self.sp_target),
                                           (self.chk_usl, "LSE", self.sp_usl))):
            chk.setText(lb)
            sl.addWidget(chk, k, 0)
            sl.addWidget(sp, k, 1)
        btn_rec = QPushButton(tr("De la receta"))
        btn_rec.setToolTip(tr("Toma los límites de alarma de la receta activa"))
        btn_rec.clicked.connect(self._spec_from_recipe)
        btn_rec.setVisible(not getattr(ctx, "fleet", False))  # el dashboard no tiene receta activa
        sl.addWidget(btn_rec, 3, 0, 1, 2, Qt.AlignLeft)
        sl.setColumnStretch(1, 1)
        opt("spec", tr("Especificación"), spec)
        self.sp_bins = QSpinBox()
        self.sp_bins.setRange(0, 200)
        self.sp_bins.setSpecialValueText(tr("automático"))
        self.sp_bins.setValue(int(p.get("bins") or 0))
        opt("bins", tr("Barras del histograma"), self.sp_bins)
        self.chk_fit = QCheckBox(tr("Curva normal"))
        self.chk_fit.setChecked(p.get("fit", True))
        opt("fit", "", self.chk_fit)
        self.chk_panel = QCheckBox(tr("Un panel por grupo (en lugar de superponer)"))
        self.chk_panel.setChecked(bool(p.get("panel")))
        opt("panel", "", self.chk_panel)
        self.cmb_stat = QComboBox()
        for k, lb in BAR_STATS:
            self.cmb_stat.addItem(tr(lb), k)
        self.cmb_stat.setCurrentIndex(max(0, self.cmb_stat.findData(p.get("stat", "mean"))))
        opt("stat", tr("Valor de las barras"), self.cmb_stat)
        self.cmb_chart = QComboBox()
        self.cmb_chart.addItem(tr("Valores individuales y rango móvil (I-MR)"), "imr")
        self.cmb_chart.addItem(tr("Medias y rangos de subgrupos (X̄-R)"), "xbar_r")
        self.cmb_chart.setCurrentIndex(max(0, self.cmb_chart.findData(p.get("chart", "imr"))))
        opt("chart", tr("Carta"), self.cmb_chart)
        self.sp_sub = QSpinBox()
        self.sp_sub.setRange(2, 10)
        self.sp_sub.setValue(int(p.get("subgroup") or 5))
        opt("subgroup", tr("Tamaño de subgrupo"), self.sp_sub)
        self.sp_grid = QSpinBox()
        self.sp_grid.setRange(5, 80)
        self.sp_grid.setValue(int(p.get("grid") or 20))
        opt("grid", tr("Resolución de la cuadrícula"), self.sp_grid)
        self.sp_step = QDoubleSpinBox()
        self.sp_step.setRange(1, 3600)
        self.sp_step.setSuffix(" s")
        self.sp_step.setValue(float(p.get("step_s") or 5))
        self.sp_step.setToolTip(tr("Las variables se comparan en los mismos instantes, cada tantos segundos"))
        opt("step", tr("Emparejar datos cada"), self.sp_step)
        self.chk_quad = QCheckBox(tr("Términos cuadráticos (curvatura)"))
        self.chk_quad.setChecked(bool(p.get("quadratic")))
        opt("quadratic", "", self.chk_quad)
        self.chk_inter = QCheckBox(tr("Interacciones entre factores"))
        self.chk_inter.setChecked(bool(p.get("interactions")))
        opt("interactions", "", self.chk_inter)
        self.cmb_source = QComboBox()
        for k, lb in PARETO_SOURCES:
            self.cmb_source.addItem(tr(lb), k)
        self.cmb_source.setCurrentIndex(max(0, self.cmb_source.findData(p.get("source", "downtime"))))
        opt("source", tr("Capturas"), self.cmb_source)
        self.cmb_by = QComboBox()
        for k, lb in PARETO_BY:
            self.cmb_by.addItem(tr(lb), k)
        self.cmb_by.setCurrentIndex(max(0, self.cmb_by.findData(p.get("by", "reason"))))
        opt("by", tr("Agrupar capturas por"), self.cmb_by)
        self.cmb_measure = QComboBox()
        for k, lb in PARETO_MEASURES:
            self.cmb_measure.addItem(tr(lb), k)
        self.cmb_measure.setCurrentIndex(max(0, self.cmb_measure.findData(p.get("measure", "minutes"))))
        opt("measure", tr("Medir"), self.cmb_measure)
        self.form.addWidget(self.box_opt)
        self.cmb_sched = QComboBox()
        for k, lb in SCHEDULES:
            self.cmb_sched.addItem(tr(lb), k)
        self.cmb_sched.setCurrentIndex(max(0, self.cmb_sched.findData(rec.get("schedule", ""))))
        self.cmb_sched.setToolTip(tr("Se calcula solo con el periodo que terminó y se agrega al reporte PDF programado "
                                     "(carpeta de reportes; también por correo si está activado)"))
        self.form.addWidget(self._row(tr("Programar"), self.cmb_sched))
        self.ed_title = QLineEdit(rec.get("title", ""))
        self.ed_title.setPlaceholderText(tr("automático"))
        self.form.addWidget(self._row(tr("Título"), self.ed_title))
        self.form.addStretch(1)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText(tr("Calcular"))
        bb.button(QDialogButtonBox.Cancel).setText(tr("Cancelar"))
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        right.addWidget(bb)
        self._select_type(rec["type"])

    # --- piezas ---
    def _row(self, label: str, w: QWidget) -> QWidget:
        box = QWidget()
        lay = QHBoxLayout(box)
        lay.setContentsMargins(0, 0, 0, 0)
        if label:
            lay.addWidget(QLabel(label))
        lay.addWidget(w, 1)
        return box

    def _var_combo(self, current) -> QComboBox:
        c = QComboBox()
        c.setSizeAdjustPolicy(QComboBox.AdjustToMinimumContentsLengthWithIcon)
        c.setMinimumContentsLength(18)
        for v in self.cfg.variables:
            if v.numeric:
                c.addItem(self.cfg.var_label(v) + (f" [{v.unit}]" if v.unit else ""), v.id)
        c.setCurrentIndex(max(0, c.findData(current)))
        return c

    def _num(self, value) -> QDoubleSpinBox:
        sp = QDoubleSpinBox()
        sp.setDecimals(4)
        sp.setRange(-1e9, 1e9)
        if value is not None:
            sp.setValue(float(value))
        return sp

    def _select_type(self, key: str) -> None:
        for i in range(self.lst_type.count()):
            if self.lst_type.item(i).data(Qt.UserRole) == key:
                self.lst_type.setCurrentRow(i)
                return

    @property
    def type(self) -> str:
        it = self.lst_type.currentItem()
        return it.data(Qt.UserRole) if it is not None and it.data(Qt.UserRole) else "histogram"

    def _type_changed(self) -> None:
        t = self.type
        name, _g, desc, _ic, vars_kind = TYPES[t]
        self.lbl_desc.setText(f"<b>{tr(name)}</b><br>{tr(desc)}")
        self.lst_vars.setVisible(vars_kind in ("multi", "reg"))
        self.row_one.setVisible(vars_kind == "one")
        self.row_xyz.setVisible(vars_kind == "xyz")
        self.row_resp.setVisible(vars_kind == "reg")
        self.box_vars.setVisible(vars_kind != "none")
        self.lbl_vars.setText(tr("Factores (X): marca uno o varios") if vars_kind == "reg" else
                              (tr("Marca hasta {n} variables", n=MAX_VARS) if vars_kind == "multi" else ""))
        show = {
            "spec": t in ("capability", "sixpack", "histogram", "timeseries"), "bins": t in ("histogram", "capability",
                                                                                              "sixpack"),
            "fit": t == "histogram", "panel": t == "histogram", "stat": t == "bar", "chart": t == "control",
            "subgroup": t == "control", "grid": t == "contour", "step": t in ("matrix", "contour", "regression"),
            "quadratic": t == "regression", "interactions": t == "regression", "source": t == "pareto",
            "by": t == "pareto", "measure": t == "pareto"}
        for key, (lab, row) in self.rows.items():
            row.setVisible(show.get(key, False))
            if lab is not None:
                lab.setVisible(show.get(key, False))
        self.box_opt.setVisible(any(show.values()))
        self.cmb_group.setEnabled(t not in ("pareto", "matrix", "contour", "regression", "control", "sixpack",
                                            "capability", "normality"))
        if t in ("capability", "sixpack") and not (self.chk_lsl.isChecked() or self.chk_usl.isChecked()):
            self._spec_from_recipe()

    def _preset(self, _i) -> None:
        secs = self.cmb_preset.currentData()
        if secs is None or secs < 0:
            return
        now = self.engine.clock()
        self._presetting = True
        self.ed_to.setDateTime(QDateTime.fromSecsSinceEpoch(int(now)))
        self.ed_from.setDateTime(QDateTime.fromSecsSinceEpoch(int(now - secs)))
        self._presetting = False

    def _spec_from_recipe(self) -> None:
        vid = self.cmb_one.currentData()
        snap = self.engine.last
        st_ = snap.statuses.get(vid) if snap is not None else None
        if st_ is None:
            return
        b = st_.bounds
        for chk, sp, val in ((self.chk_lsl, self.sp_lsl, b.al), (self.chk_usl, self.sp_usl, b.ah),
                             (self.chk_target, self.sp_target, st_.reference)):
            chk.setChecked(val is not None)
            if val is not None:
                sp.setValue(float(val))

    def checked_vars(self) -> list[str]:
        return [self.lst_vars.item(i).data(Qt.UserRole) for i in range(self.lst_vars.count())
                if self.lst_vars.item(i).checkState() == Qt.Checked]

    # --- resultado ---
    def record(self, base: Optional[dict] = None) -> dict:
        t = self.type
        kind = TYPES[t][4]
        p: dict = {"since": float(self.ed_from.dateTime().toSecsSinceEpoch()),
                   "until": float(self.ed_to.dateTime().toSecsSinceEpoch()),
                   "group_by": self.cmb_group.currentData() if self.cmb_group.isEnabled() else "",
                   "shift": self.cmb_shift.currentData(), "operator": self.cmb_op.currentData(),
                   "recipe": self.cmb_recipe.currentData(), "line": self.cmb_line.currentData() if self.fleet else ""}
        if kind == "multi":
            p["vars"] = self.checked_vars()[:MAX_VARS]
        elif kind == "one":
            p["vars"] = [self.cmb_one.currentData()]
        elif kind == "xyz":
            p.update(x=self.cmb_x.currentData(), y=self.cmb_y.currentData(), z=self.cmb_z.currentData())
            p["vars"] = [p["x"], p["y"], p["z"]]
        elif kind == "reg":
            p["y"] = self.cmb_resp.currentData()
            p["xs"] = [v for v in self.checked_vars() if v != p["y"]][:MAX_VARS]
            p["vars"] = [p["y"]] + p["xs"]
        for chk, sp, k in ((self.chk_lsl, self.sp_lsl, "lsl"), (self.chk_usl, self.sp_usl, "usl"),
                           (self.chk_target, self.sp_target, "target")):
            p[k] = sp.value() if chk.isChecked() else None
        p.update(bins=self.sp_bins.value(), fit=self.chk_fit.isChecked(), panel=self.chk_panel.isChecked(),
                 stat=self.cmb_stat.currentData(), chart=self.cmb_chart.currentData(), subgroup=self.sp_sub.value(),
                 grid=self.sp_grid.value(), step_s=self.sp_step.value(), quadratic=self.chk_quad.isChecked(),
                 interactions=self.chk_inter.isChecked(), source=self.cmb_source.currentData(),
                 by=self.cmb_by.currentData(), measure=self.cmb_measure.currentData())
        rec = dict(base or {})
        rec.setdefault("id", uuid.uuid4().hex[:10])
        rec.setdefault("created", time.time())
        rec.setdefault("style", {})
        rec.update(type=t, params=p, title=self.ed_title.text().strip(), schedule=self.cmb_sched.currentData())
        return rec

    def problems(self) -> list[str]:
        r = self.record()
        p, kind = r["params"], TYPES[r["type"]][4]
        out = []
        if p["until"] <= p["since"]:
            out.append(tr("El fin del periodo debe ser posterior al inicio."))
        if kind == "multi" and not p["vars"]:
            out.append(tr("Marca al menos una variable."))
        if r["type"] == "matrix" and len(p.get("vars", [])) < 2:
            out.append(tr("Marca al menos dos variables."))
        if kind == "reg" and not p.get("xs"):
            out.append(tr("Marca al menos un factor (X) distinto de la respuesta."))
        if r["type"] in ("capability", "sixpack") and p["lsl"] is None and p["usl"] is None:
            out.append(tr("Indica al menos un límite de especificación (LIE o LSE)."))
        if r["type"] == "compare" and not p["group_by"] and len(p.get("vars", [])) < 2:
            out.append(tr("Para comparar, agrupa (turno, día, mes, operador…) o marca dos o más variables."))
        return out

    def accept(self) -> None:
        msgs = self.problems()
        if msgs:
            QMessageBox.information(self, tr("Análisis"), "\n".join(msgs))
            return
        super().accept()


# --- página -----------------------------------------------------------------------------------------------


class StatsPage(QWidget):
    """Página «Análisis estadístico»: navegador a la izquierda y el análisis elegido a la derecha."""

    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        self.engine = ctx.engine
        self.home = ctx.workspace.home
        self.records = load_project(self.home)
        self.current: Optional[Render] = None
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        split = QSplitter(Qt.Horizontal)
        nav = QFrame()
        nav.setObjectName("card")
        nl = QVBoxLayout(nav)
        nl.addWidget(QLabel(f"<b style='font-size:14px; color:{theme.c('title')}'>{tr('Navegador de análisis')}</b>"))
        self.btn_new = QPushButton(tr("＋ Nuevo análisis"))
        self.btn_new.setObjectName("primary")
        self.btn_new.setStyleSheet(f"QPushButton#primary {{ background:{theme.c('accent')}; color:{theme.c('accent_text')};"
                                   " font-weight:bold; padding:7px; border-radius:6px; }")
        self.btn_new.clicked.connect(self.new_analysis)
        nl.addWidget(self.btn_new)
        self.lst = QListWidget()
        self.lst.setIconSize(QSize(18, 18))
        self.lst.setWordWrap(True)
        self.lst.currentRowChanged.connect(self._selected)
        self.lst.itemDoubleClicked.connect(lambda _it: self.edit_analysis())
        nl.addWidget(self.lst, 1)
        row = QGridLayout()
        for i, (text, slot, tip) in enumerate((
                (tr("✎ Cambiar"), self.edit_analysis, tr("Cambiar datos, variables u opciones")),
                (tr("⧉ Duplicar"), self.duplicate, tr("Copia para probar otra variación")),
                (tr("Aa Renombrar"), self.rename, tr("Cambiar el título del análisis")),
                (tr("🗑 Eliminar"), self.delete, tr("Quitar el análisis del navegador")))):
            b = QPushButton(text)
            b.setToolTip(tip)
            b.clicked.connect(slot)
            row.addWidget(b, i // 2, i % 2)
        nl.addLayout(row)
        split.addWidget(nav)
        # resultado
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(6, 0, 0, 0)
        head = QHBoxLayout()
        self.lbl_title = QLabel()
        self.lbl_title.setWordWrap(True)
        self.lbl_title.setToolTip(tr("Doble clic para cambiar el título"))
        self.lbl_title.mouseDoubleClickEvent = lambda _e: self.rename()
        head.addWidget(self.lbl_title, 1)
        self.tool_btns = []
        for text, slot, tip in ((tr("📄 Reporte PDF"), self.export_pdf,
                                 tr("Junta varios análisis en un PDF para juntas o auditorías")),
                                (tr("🎨 Colores"), self.colors, tr("Color de barras y líneas")),
                                (tr("⟳ Recalcular"), lambda: self.show_record(self.lst.currentRow(), force=True),
                                 tr("Vuelve a leer el historial")),
                                (tr("⤓ Imagen"), self.export_png, tr("Guardar el análisis como imagen PNG")),
                                (tr("⤓ Exportar"), self.export_csv,
                                 tr("Guardar los datos del análisis o la tabla de resultados en CSV, Excel o para "
                                    "software estadístico (Minitab)"))):
            b = QPushButton(text)
            b.setToolTip(tip)
            b.clicked.connect(slot)
            head.addWidget(b)
            self.tool_btns.append(b)
        rl.addLayout(head)
        self.lbl_sub = QLabel()
        self.lbl_sub.setStyleSheet(f"color:{theme.c('muted')};")
        rl.addWidget(self.lbl_sub)
        self.area = QScrollArea()
        self.area.setWidgetResizable(True)
        self.area.setFrameShape(QFrame.NoFrame)
        rl.addWidget(self.area, 1)
        split.addWidget(right)
        split.setSizes([280, 1100])
        lay.addWidget(split)
        self._fill()
        if self.records:
            self.lst.setCurrentRow(0)
        else:
            self._welcome()
        from PySide6.QtCore import QTimer
        self.sched_timer = QTimer(self)
        self.sched_timer.timeout.connect(self.run_scheduled)
        self.sched_timer.start(60000)  # análisis programados: al terminar cada turno, día o semana
        QTimer.singleShot(5000, self.run_scheduled)

    def where(self) -> str:
        from .branding import Branding
        b = Branding.load(self.home)
        return " · ".join(x for x in (self.engine.config.machine_name, b.text, b.line) if x)

    def run_scheduled(self) -> list:
        from .stats_report import run_due
        try:
            return run_due(self)
        except Exception:
            import logging
            logging.getLogger(__name__).exception("análisis programados")
            return []

    def export_pdf(self) -> None:
        from .stats_report import export_dialog
        path = export_dialog(self)
        if path:
            QMessageBox.information(self, tr("Reporte PDF"), tr("Reporte guardado:\n{p}", p=path))

    # --- navegador ---
    def _fill(self, select: Optional[int] = None) -> None:
        self.lst.blockSignals(True)
        self.lst.clear()
        cfg = self.engine.config
        for r in self.records:
            name, _g, _d, ic, _v = TYPES[r["type"]]
            p = r.get("params", {})
            when = ""
            if p.get("since"):
                when = time.strftime("%d/%m", time.localtime(p["since"])) + "–" + \
                    time.strftime("%d/%m", time.localtime(p.get("until") or time.time()))
            title = r.get("title") or default_title(r, cfg)
            it = QListWidgetItem(icons.icon(ic, theme.c("nav_icon"), theme.c("accent_text")), f"{title}\n{when}")
            it.setToolTip(f"{title}\n{tr(name)} · {when}")
            self.lst.addItem(it)
        self.lst.blockSignals(False)
        if select is not None and 0 <= select < len(self.records):
            self.lst.setCurrentRow(select)
        for b in self.tool_btns:
            b.setEnabled(bool(self.records))

    def _save(self) -> None:
        try:
            save_project(self.home, self.records)
        except OSError as e:
            QMessageBox.warning(self, tr("Análisis"), tr("No se pudo guardar el navegador: {e}", e=e))

    def _welcome(self) -> None:
        self.lbl_title.setText(f"<span style='font-size:18px; color:{theme.c('title')}'><b>"
                               f"{tr('Análisis estadístico')}</b></span>")
        self.lbl_sub.setText("")
        w = QLabel(tr("Crea un análisis con «＋ Nuevo análisis»: estadística descriptiva, histogramas, cajas, gráficas "
                      "de tiempo y de barras, normalidad, capacidad y Sixpack, cartas de control, comparación de "
                      "turnos, días, meses u operadores, Pareto de paros y defectos, correlación, contorno y "
                      "regresión con simulación de respuesta.<br><br>Cada análisis queda en el navegador: clic para "
                      "verlo, doble clic para cambiarlo."))
        w.setWordWrap(True)
        w.setAlignment(Qt.AlignCenter)
        w.setStyleSheet(f"color:{theme.c('text2')}; padding: 60px; font-size: 14px;")
        self.area.setWidget(w)
        self.current = None

    def _selected(self, row: int) -> None:
        if 0 <= row < len(self.records):
            self.show_record(row)

    def new_analysis(self) -> None:
        dlg = AnalysisDialog(self.ctx, None, self)
        if dlg.exec():
            self.add(dlg.record())

    def add(self, rec: dict) -> None:
        self.records.insert(0, rec)
        self._save()
        self._fill(select=0)

    def edit_analysis(self) -> None:
        row = self.lst.currentRow()
        if not 0 <= row < len(self.records):
            return
        dlg = AnalysisDialog(self.ctx, self.records[row], self)
        if dlg.exec():
            self.records[row] = dlg.record(self.records[row])
            self._save()
            self._fill(select=row)
            self.show_record(row, force=True)

    def duplicate(self) -> None:
        row = self.lst.currentRow()
        if 0 <= row < len(self.records):
            rec = json.loads(json.dumps(self.records[row]))
            rec["id"] = uuid.uuid4().hex[:10]
            rec["title"] = (rec.get("title") or default_title(rec, self.engine.config)) + tr(" (copia)")
            self.add(rec)

    def rename(self) -> None:
        row = self.lst.currentRow()
        if not 0 <= row < len(self.records):
            return
        rec = self.records[row]
        text, ok = QInputDialog.getText(self, tr("Título del análisis"), tr("Título:"),
                                        text=rec.get("title") or default_title(rec, self.engine.config))
        if ok:
            rec["title"] = text.strip()
            self._save()
            self._fill(select=row)
            self.show_record(row)

    def delete(self, confirm: bool = True) -> None:
        row = self.lst.currentRow()
        if not 0 <= row < len(self.records):
            return
        if confirm and QMessageBox.question(self, tr("Eliminar"), tr("¿Quitar «{t}» del navegador?", t=self.records[row].get(
                "title") or default_title(self.records[row], self.engine.config))) != QMessageBox.Yes:
            return
        self.records.pop(row)
        self._save()
        self._fill(select=min(row, len(self.records) - 1))
        if not self.records:
            self._welcome()

    # --- resultado ---
    def show_record(self, row: int, force: bool = False) -> None:
        if not 0 <= row < len(self.records):
            return
        rec = self.records[row]
        cfg = self.engine.config
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            R, n = build_render(self.ctx, rec)
            R.titleEdited.connect(lambda k, t, row=row: self._chart_title(row, k, t))
        finally:
            QApplication.restoreOverrideCursor()
        self.current = R
        self.area.setWidget(R)
        self.lbl_title.setText(f"<span style='font-size:18px; color:{theme.c('title')}'><b>"
                               f"{rec.get('title') or default_title(rec, cfg)}</b></span>")
        self.lbl_sub.setText(subtitle(rec) + (f" · {n:,} {tr('datos')}" if n else "")
                             + (f" · ⏱ {tr(dict(SCHEDULES)[rec['schedule']])}" if rec.get("schedule") else ""))

    def _chart_title(self, row: int, key: str, text: str) -> None:
        rec = self.records[row]
        titles = rec.setdefault("style", {}).setdefault("titles", {})
        if text:
            titles[key] = text
        else:
            titles.pop(key, None)
        self._save()
        self.show_record(row)

    def colors(self) -> None:
        row = self.lst.currentRow()
        if self.current is None or not 0 <= row < len(self.records):
            return
        names = self.current.series or [tr("Serie 1")]
        rec = self.records[row]
        cols = list(rec.setdefault("style", {}).get("colors") or [])
        dlg = QDialog(self)
        dlg.setWindowTitle(tr("Colores de barras y líneas"))
        fl = QFormLayout(dlg)
        btns = []
        for i, name in enumerate(names):
            c = QColor(cols[i]) if i < len(cols) and cols[i] else QColor(theme.series(i))
            b = QPushButton()
            b.setFixedWidth(90)
            b.setProperty("color", c.name())
            b.setStyleSheet(f"background:{c.name()};")

            def pick(_=False, b=b):
                nc = QColorDialog.getColor(QColor(b.property("color")), dlg)
                if nc.isValid():
                    b.setProperty("color", nc.name())
                    b.setStyleSheet(f"background:{nc.name()};")
            b.clicked.connect(pick)
            fl.addRow(name, b)
            btns.append(b)
        reset = QPushButton(tr("Colores del tema"))
        reset.clicked.connect(lambda: [b.setProperty("color", theme.series(i)) or
                                       b.setStyleSheet(f"background:{theme.series(i)};") for i, b in enumerate(btns)])
        fl.addRow(reset)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        fl.addRow(bb)
        if dlg.exec():
            self.set_colors(row, [b.property("color") for b in btns])

    def set_colors(self, row: int, colors: list[str]) -> None:
        self.records[row].setdefault("style", {})["colors"] = colors
        self._save()
        self.show_record(row)

    def export_png(self, path: Optional[str] = None) -> Optional[str]:
        if self.current is None:
            return None
        if path is None:
            path, _ = QFileDialog.getSaveFileName(self, tr("Guardar imagen"), "analisis.png", "PNG (*.png)")
        if path:
            self.current.grab().save(path)
        return path or None

    def export_csv(self, path: Optional[str] = None, fmt: Optional[str] = None,
                   content: str = "data") -> Optional[str]:
        """Exporta los datos del análisis (para Minitab) o su tabla de resultados."""
        R = self.current
        if R is None:
            return None
        contents = [(k, lb) for k, lb, ok in (
            ("data", "Datos del análisis (una columna por variable)", bool(R.data_table()[1])),
            ("results", "Tabla de resultados", bool(R.csv_rows))) if ok]
        if not contents:
            return None
        if fmt is not None and content not in [k for k, _ in contents]:
            return None
        from .export_dialog import export_table

        def build(c: str):
            return (R.csv_header, R.csv_rows) if c == "results" else R.data_table()

        return export_table(self, "Exportar análisis", "analisis", build, contents, path=path, fmt=fmt,
                            content=content if fmt else None)
