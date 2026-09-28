"""Modelos de configuración de la aplicación y persistencia en disco."""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

APP_NAME = "ExtrusionMonitor"
CONFIG_VERSION = 1


class Rect(BaseModel):
    x: int
    y: int
    w: int
    h: int

    @field_validator("w", "h")
    @classmethod
    def _positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("el ancho y alto deben ser > 0")
        return v


class OcrOptions(BaseModel):
    # "auto" detecta si el texto es claro sobre fondo oscuro o al revés.
    invert: Literal["auto", "yes", "no"] = "auto"
    scale: float = Field(3.0, ge=1.0, le=8.0)
    # None = umbral automático (Otsu).
    threshold: Optional[int] = Field(None, ge=0, le=255)
    # Quita el marco del campo si la región lo incluye.
    clear_border: bool = True
    # Lectura robusta: prueba varias variantes de preprocesado y vota (sin umbral manual).
    auto: bool = True


class Page(BaseModel):
    """Nodo del árbol de pantallas del HMI (componente, pestaña o sub-pestaña).

    Con `anchor` se identifica por una imagen (p. ej. el botón de la pestaña resaltado);
    sin ancla es una carpeta que solo agrupa y es visible cuando lo es su padre.
    """

    id: str
    name: str
    parent: Optional[str] = None
    anchor: Optional[Rect] = None
    match_threshold: float = Field(0.85, ge=0.3, le=1.0)


VariableKind = Literal["actual", "setpoint", "text", "selector", "formula"]


class Variable(BaseModel):
    id: str
    name: str
    unit: str = ""
    group: str = "General"
    kind: VariableKind = "actual"
    page: Optional[str] = None
    region: Rect
    # Para variables "actual": id de la consigna asociada (valor real vs. consigna).
    setpoint_var: Optional[str] = None
    decimals: Optional[int] = Field(None, ge=0, le=6)
    decimal_separator: Literal["auto", ".", ","] = "auto"
    # Si el OCR pierde el punto decimal, se reinserta usando `decimals`.
    fix_missing_decimal: bool = False
    # Límites de plausibilidad: lecturas fuera se descartan como error de OCR.
    valid_min: Optional[float] = None
    valid_max: Optional[float] = None
    # Salto máximo entre lecturas; un salto mayor debe confirmarse en la siguiente lectura.
    max_step: Optional[float] = None
    ocr: OcrOptions = Field(default_factory=OcrOptions)
    trend: bool = True
    # Selector: estados reconocidos por imagen (p. ej. «ON», «OFF»); las imágenes se guardan aparte.
    states: list[str] = Field(default_factory=list)
    state_threshold: float = Field(0.8, ge=0.3, le=1.0)

    # Fórmula: variable calculada a partir de otras (p. ej. «vel / rpm»).
    formula: str = ""

    @property
    def numeric(self) -> bool:
        return self.kind in ("actual", "setpoint", "formula")

    @property
    def measured(self) -> bool:
        """Valor de proceso (medición o calculado): tendencias, estadística y comportamiento."""
        return self.kind in ("actual", "formula")

    @property
    def screen(self) -> bool:
        """Se lee de la pantalla (las fórmulas no)."""
        return self.kind != "formula"


OcrEngineName = Literal["windows", "template", "tesseract"]


class GeneralSettings(BaseModel):
    monitor: int = Field(1, ge=0)
    sample_interval_s: float = Field(2.0, ge=0.2, le=60)
    ocr_engine: OcrEngineName = "windows" if sys.platform == "win32" else "template"
    tesseract_path: Optional[str] = None
    # Número de ciclos consecutivos para activar/desactivar un hallazgo.
    debounce_samples: int = Field(3, ge=1, le=50)
    trend_window_min: float = Field(15.0, ge=1, le=240)
    trend_horizon_min: float = Field(10.0, ge=0.5, le=240)
    spc_subgroup_s: float = Field(30.0, ge=1, le=600)
    stale_after_s: float = Field(30.0, ge=1)
    read_fail_samples: int = Field(5, ge=1)
    # Variable de texto que muestra el nombre de la receta activa en el HMI.
    recipe_name_var: Optional[str] = None
    beep_on_alarm: bool = True


class Click(BaseModel):
    """Clic de navegación en coordenadas de la captura.

    Al grabarlo se guarda la imagen del botón (`patch`) y antes de cada clic se comprueba
    que el botón sigue ahí; si no coincide no se hace clic.
    """

    id: str
    x: int
    y: int
    patch: int = Field(36, ge=8, le=200)  # lado del recuadro verificado alrededor del punto
    match_threshold: float = Field(0.8, ge=0.3, le=1.0)


class TourStep(BaseModel):
    """Paso del recorrido: clics desde la pantalla anterior hasta `page`, donde se leen los datos."""

    id: str
    page: str
    clicks: list[Click] = Field(default_factory=list)
    settle_s: float = Field(1.5, ge=0.1, le=30)


class TourSettings(BaseModel):
    """Macro de navegación automática por las pestañas del HMI."""

    enabled: bool = False
    home_page: Optional[str] = None  # pantalla principal: condición de inicio y de regreso
    home_clicks: list[Click] = Field(default_factory=list)
    home_settle_s: float = Field(1.5, ge=0.1, le=30)
    steps: list[TourStep] = Field(default_factory=list)
    interval_s: float = Field(60.0, ge=5, le=3600)
    # Sin actividad del operador (mouse/teclado) durante este tiempo antes de iniciar.
    idle_required_s: float = Field(20.0, ge=0, le=3600)
    page_retries: int = Field(2, ge=0, le=10)

    def all_clicks(self) -> list[Click]:
        return [c for s in self.steps for c in s.clicks] + list(self.home_clicks)


class TourDef(BaseModel):
    """Recorrido definido por el usuario: uno o varios pasos de clics verificados y sus disparadores."""

    id: str
    name: str = "Recorrido"
    enabled: bool = True
    steps: list[TourStep] = Field(default_factory=list)
    # Pantalla en la que debe estar el HMI para empezar (None = cualquiera; los clics siguen verificados).
    start_page: Optional[str] = None
    # Regreso al terminar (p. ej. a la pantalla principal). Sin clics = no regresa.
    return_clicks: list[Click] = Field(default_factory=list)
    return_page: Optional[str] = None
    return_settle_s: float = Field(1.5, ge=0.1, le=30)
    read_data: bool = True  # leer las variables de cada pantalla visitada
    # --- disparadores ---
    interval_s: Optional[float] = Field(None, ge=5)  # cada X segundos
    off_page: Optional[str] = None  # si esta pantalla deja de verse…
    off_page_s: float = Field(120.0, ge=5)  # …durante X segundos
    selector_var: Optional[str] = None  # si el selector cambia de estado…
    selector_state: Optional[str] = None  # …(a este estado; None = cualquier cambio)
    zero_var: Optional[str] = None  # si el valor baja a ≤ umbral
    zero_threshold: float = 0.0
    # --- confirmación ---
    confirm: bool = False  # aviso con cuenta regresiva; si se ignora o se acepta, se ejecuta
    countdown_s: float = Field(15.0, ge=3, le=600)
    snooze_s: float = Field(300.0, ge=10, le=86400)  # «Posponer»: vuelve a aparecer tras este tiempo
    idle_required_s: float = Field(20.0, ge=0, le=3600)
    page_retries: int = Field(2, ge=0, le=10)

    def all_clicks(self) -> list[Click]:
        return [c for s in self.steps for c in s.clicks] + list(self.return_clicks)

    @property
    def has_trigger(self) -> bool:
        return bool(self.interval_s or self.off_page or self.selector_var or self.zero_var)


class OeeSettings(BaseModel):
    """Cálculo de OEE a partir de la velocidad de línea y de la conformidad del proceso."""

    enabled: bool = False
    speed_var: Optional[str] = None  # variable (medición) de velocidad de línea
    stop_threshold: float = Field(0.5, ge=0)  # velocidad ≤ umbral = línea detenida
    # Velocidad nominal: de la receta, de la consigna leída del HMI o un valor fijo.
    nominal_source: Literal["recipe", "setpoint", "fixed"] = "recipe"
    nominal_value: Optional[float] = None
    slow_pct: float = Field(90.0, ge=10, le=100)  # en marcha por debajo de este % = lento
    microstop_s: float = Field(120.0, ge=0)
    # Calidad: variables en especificación, indicador visual (selector) o ambos.
    quality_mode: Literal["spec", "selector", "both"] = "spec"
    quality_selector: Optional[str] = None
    quality_good_state: Optional[str] = None
    strict_quality: bool = False  # también los avisos (no solo alarmas) cuentan como no conforme
    length_factor: float = Field(1.0, gt=0)  # velocidad × factor = longitud por minuto (m/min → 1)
    length_unit: str = "m"
    shift_starts: list[str] = Field(default_factory=lambda: ["06:00", "14:00", "22:00"])
    # Hueco sin datos (app cerrada, pausa): si al volver la línea marcha y todo está en parámetros,
    # se cuenta como productivo hasta este límite; más largo queda como «Sin datos».
    gap_productive: bool = True
    gap_productive_max_s: float = Field(1800.0, ge=0)
    target_oee: float = Field(85.0, ge=0, le=100)


class ReportTrigger(BaseModel):
    """Evento que genera el reporte."""

    kind: Literal["cross", "change", "selector", "tour"] = "cross"
    var_id: Optional[str] = None  # cross / change / selector
    op: Literal[">", ">=", "<", "<="] = ">"  # cross: la condición pasa de falsa a verdadera
    value: float = 0.0  # cross: umbral; change: cambio mínimo (0 = cualquier cambio)
    state: Optional[str] = None  # selector: solo al cambiar a este estado (None = cualquiera)
    tour_id: Optional[str] = None  # tour: recorrido ejecutado (None = cualquiera)


class ReportVar(BaseModel):
    var_id: str
    # Evaluación: dentro de especificación (todas las lecturas) o Cpk mínimo.
    criterion: Literal["spec", "cpk"] = "spec"
    cpk_min: float = Field(1.33, ge=0, le=10)
    chart: bool = True  # gráfica de tendencia con límites
    events: bool = True  # lista de eventos de la variable
    csv: bool = True  # datos en el CSV


class ReportDef(BaseModel):
    """Reporte PDF automático: abarca desde el fin del reporte anterior hasta el momento del disparo."""

    id: str
    name: str = "Reporte"
    enabled: bool = True
    triggers: list[ReportTrigger] = Field(default_factory=list)
    variables: list[ReportVar] = Field(default_factory=list)
    behavior_models: list[str] = Field(default_factory=list)  # gráfica de comportamiento (D²/umbral)
    include_general_events: bool = False  # también eventos sin variable (recetas, recorridos)
    export_csv: bool = True
    name_var: Optional[str] = None  # nombre del archivo: valor de esta variable (None = fecha y hora)
    output_dir: Optional[str] = None  # None = <carpeta del programa>/data/reports
    reset_analysis: bool = False  # reiniciar tendencias, estadística y comportamiento al generarlo
    min_interval_s: float = Field(60.0, ge=0)  # tiempo mínimo entre dos reportes
    max_period_h: float = Field(24.0, gt=0, le=24 * 31)  # primer reporte / periodo máximo


class AppConfig(BaseModel):
    version: int = CONFIG_VERSION
    machine_name: str = "Línea de extrusión"
    general: GeneralSettings = Field(default_factory=GeneralSettings)
    pages: list[Page] = Field(default_factory=list)
    variables: list[Variable] = Field(default_factory=list)
    tour: TourSettings = Field(default_factory=TourSettings)  # formato anterior (se migra a `tours`)
    tours: list[TourDef] = Field(default_factory=list)
    tours_paused: bool = False
    oee: OeeSettings = Field(default_factory=OeeSettings)
    reports: list[ReportDef] = Field(default_factory=list)

    @model_validator(mode="after")
    def _migrate_tour(self) -> "AppConfig":
        t = self.tour
        if t.steps and not self.tours:
            self.tours = [TourDef(
                id="lectura", name="Lectura de pestañas", enabled=t.enabled, steps=list(t.steps),
                start_page=t.home_page, return_clicks=list(t.home_clicks), return_page=t.home_page,
                return_settle_s=t.home_settle_s, read_data=True, interval_s=t.interval_s,
                idle_required_s=t.idle_required_s, page_retries=t.page_retries)]
            self.tour = TourSettings()
        return self

    def get_tour(self, tour_id: str) -> Optional[TourDef]:
        return next((t for t in self.tours if t.id == tour_id), None)

    def all_tour_clicks(self) -> list[Click]:
        return [c for t in self.tours for c in t.all_clicks()]

    def toured_pages(self) -> set[str]:
        """Páginas que se leen durante recorridos (con sus ancestros): su dato vale hasta el siguiente."""
        out: set[str] = set()
        for t in self.tours:
            if t.enabled and t.read_data:
                for step in t.steps:
                    out |= {p.id for p in self.page_path(step.page)}
        return out

    def tour_stale_s(self) -> float:
        """Vigencia de los datos leídos en recorridos: 2.5 × el intervalo más largo entre lecturas."""
        ints = [t.interval_s for t in self.tours if t.enabled and t.read_data and t.interval_s]
        return 2.5 * max(ints) if ints else 3600.0

    def variable(self, var_id: str) -> Optional[Variable]:
        return next((v for v in self.variables if v.id == var_id), None)

    def page(self, page_id: str) -> Optional[Page]:
        return next((p for p in self.pages if p.id == page_id), None)

    def page_path(self, page_id: Optional[str]) -> list[Page]:
        """Cadena de páginas desde la raíz hasta `page_id`."""
        path: list[Page] = []
        seen: set[str] = set()
        while page_id and page_id not in seen:
            seen.add(page_id)
            p = self.page(page_id)
            if p is None:
                break
            path.append(p)
            page_id = p.parent
        return path[::-1]

    def page_label(self, page_id: Optional[str]) -> str:
        return " › ".join(p.name for p in self.page_path(page_id))

    def var_label(self, var: "Variable") -> str:
        """Nombre completo para mensajes: «EXT1 › Overview › Cylinder 1»."""
        prefix = self.page_label(var.page)
        return f"{prefix} › {var.name}" if prefix else var.name

    def children(self, page_id: Optional[str]) -> list[Page]:
        return [p for p in self.pages if p.parent == page_id]

    def descendants(self, page_id: str) -> set[str]:
        out: set[str] = set()
        stack = [page_id]
        while stack:
            for c in self.children(stack.pop()):
                if c.id not in out:
                    out.add(c.id)
                    stack.append(c.id)
        return out

    def validate_references(self) -> list[str]:
        """Devuelve una lista de problemas de coherencia (vacía si todo está bien)."""
        problems: list[str] = []
        pids = [p.id for p in self.pages]
        dup_p = {i for i in pids if pids.count(i) > 1}
        if dup_p:
            problems.append(f"IDs de página duplicados: {', '.join(sorted(dup_p))}")
        for p in self.pages:
            if p.parent and self.page(p.parent) is None:
                problems.append(f"Página «{p.name}»: el padre '{p.parent}' no existe")
            if p.id in self.descendants(p.id):
                problems.append(f"Página «{p.name}»: el árbol tiene un ciclo")
        ids = [v.id for v in self.variables]
        dup = {i for i in ids if ids.count(i) > 1}
        if dup:
            problems.append(f"IDs de variable duplicados: {', '.join(sorted(dup))}")
        page_ids = {p.id for p in self.pages}
        for v in self.variables:
            if v.page and v.page not in page_ids:
                problems.append(f"{v.id}: la página '{v.page}' no existe")
            if v.setpoint_var:
                sp = self.variable(v.setpoint_var)
                if sp is None:
                    problems.append(f"{v.id}: la consigna '{v.setpoint_var}' no existe")
                elif sp.kind != "setpoint":
                    problems.append(f"{v.id}: '{v.setpoint_var}' no es de tipo consigna")
        for t in self.tours:
            name = f"Recorrido «{t.name}»"
            for pid in (t.start_page, t.return_page, t.off_page):
                if pid and self.page(pid) is None:
                    problems.append(f"{name}: la pestaña '{pid}' no existe")
            if t.enabled and not t.steps:
                problems.append(f"{name}: no tiene pasos")
            for i, st in enumerate(t.steps, 1):
                page = self.page(st.page)
                if page is None:
                    problems.append(f"{name} paso {i}: la pestaña '{st.page}' no existe")
                elif not any(p.anchor for p in self.page_path(st.page)):
                    problems.append(f"{name} paso {i}: «{page.name}» necesita un ancla para verificar la llegada")
                if not st.clicks:
                    problems.append(f"{name} paso {i}: no tiene clics grabados")
            if t.return_page and not t.return_clicks:
                problems.append(f"{name}: graba los clics de regreso")
            for vid in (t.selector_var, t.zero_var):
                if vid and self.variable(vid) is None:
                    problems.append(f"{name}: la variable '{vid}' no existe")
        for r in self.reports:
            name = f"Reporte «{r.name}»"
            for tr in r.triggers:
                if tr.kind in ("cross", "change", "selector") and (not tr.var_id or self.variable(tr.var_id) is None):
                    problems.append(f"{name}: el disparador necesita una variable existente")
                if tr.kind == "tour" and tr.tour_id and self.get_tour(tr.tour_id) is None:
                    problems.append(f"{name}: el recorrido '{tr.tour_id}' no existe")
            for rv in r.variables:
                if self.variable(rv.var_id) is None:
                    problems.append(f"{name}: la variable '{rv.var_id}' no existe")
            if r.name_var and self.variable(r.name_var) is None:
                problems.append(f"{name}: la variable del nombre de archivo no existe")
        formulas = {}
        from .analysis.formula import FormulaError, compile_formula, evaluation_order
        known = {v.id for v in self.variables}
        for v in self.variables:
            if v.kind == "formula":
                try:
                    formulas[v.id] = compile_formula(v.formula, known - {v.id})
                except FormulaError as exc:
                    problems.append(f"Fórmula «{v.name}»: {exc}")
        try:
            evaluation_order(formulas)
        except FormulaError as exc:
            problems.append(str(exc))
        rn = self.general.recipe_name_var
        if rn:
            var = self.variable(rn)
            if var is None or var.kind != "text":
                problems.append(f"La variable de nombre de receta '{rn}' debe existir y ser de tipo texto")
        return problems


def default_home() -> Path:
    """Carpeta de datos: EXTRUMON_HOME, carpeta 'data' junto al .exe (modo portátil) o LOCALAPPDATA."""
    env = os.environ.get("EXTRUMON_HOME")
    if env:
        return Path(env)
    if getattr(sys, "frozen", False):
        portable = Path(sys.executable).parent / "data"
        if portable.is_dir():
            return portable
    base = os.environ.get("LOCALAPPDATA") or os.path.join(Path.home(), ".local", "share")
    return Path(base) / APP_NAME


class Workspace:
    """Rutas de todos los archivos que la aplicación guarda."""

    def __init__(self, home: Path | str | None = None):
        self.home = Path(home) if home else default_home()
        self.home.mkdir(parents=True, exist_ok=True)
        self.pages_dir.mkdir(exist_ok=True)
        self.recipes_dir.mkdir(exist_ok=True)

    @property
    def config_file(self) -> Path:
        return self.home / "config.json"

    @property
    def pages_dir(self) -> Path:
        return self.home / "pages"

    @property
    def recipes_dir(self) -> Path:
        return self.home / "recipes"

    @property
    def glyphs_file(self) -> Path:
        return self.home / "glyphs.json"

    @property
    def history_db(self) -> Path:
        return self.home / "history.sqlite"

    @property
    def state_file(self) -> Path:
        return self.home / "state.json"

    def page_anchor_file(self, page_id: str) -> Path:
        return self.pages_dir / f"{page_id}.png"

    @property
    def clicks_dir(self) -> Path:
        d = self.home / "clicks"
        d.mkdir(exist_ok=True)
        return d

    def click_patch_file(self, click_id: str) -> Path:
        return self.clicks_dir / f"{click_id}.png"

    @property
    def selectors_dir(self) -> Path:
        d = self.home / "selectors"
        d.mkdir(exist_ok=True)
        return d

    def selector_state_file(self, var_id: str, state: str) -> Path:
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in state)
        return self.selectors_dir / f"{var_id}__{safe}.png"

    @property
    def reports_state_file(self) -> Path:
        return self.home / "reports_state.json"

    def default_reports_dir(self) -> Path:
        """<carpeta del programa>/data/reports (o la carpeta de datos si no es posible escribir ahí)."""
        if getattr(sys, "frozen", False):
            d = Path(sys.executable).parent / "data" / "reports"
            try:
                d.mkdir(parents=True, exist_ok=True)
                return d
            except OSError:
                pass
        return self.home / "reports"

    @property
    def behaviors_file(self) -> Path:
        return self.home / "behaviors.json"

    def load_config(self) -> AppConfig:
        if not self.config_file.exists():
            return AppConfig()
        return AppConfig.model_validate_json(self.config_file.read_text(encoding="utf-8"))

    def save_config(self, config: AppConfig) -> None:
        _atomic_write(self.config_file, config.model_dump_json(indent=2))

    def load_state(self) -> dict:
        try:
            return json.loads(self.state_file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def save_state(self, state: dict) -> None:
        _atomic_write(self.state_file, json.dumps(state, indent=2, ensure_ascii=False))


def _atomic_write(path: Path, text: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)
