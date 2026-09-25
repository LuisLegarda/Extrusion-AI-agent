"""HMI simulado de una línea de extrusión de cable (modo demo y pruebas).

Dibuja una pantalla tipo HMI con consignas y valores reales que evolucionan
en el tiempo, e inyecta fallas típicas para mostrar la detección.
"""
from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass
from typing import Callable, Optional

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from .config import AppConfig, GeneralSettings, OcrOptions, Page, Rect, Variable
from .recipes import Limit, Recipe

W, H = 1280, 800
FONT_SIZE = 22
BG = (38, 42, 48)
BOX_BG = (12, 14, 16)
FG = (230, 230, 230)
VAL = (90, 230, 120)
SPC = (120, 190, 255)

RECIPE_NAME = "THHN-12AWG-NEGRO"
TITLE = "EXTRUSORA PRINCIPAL"


@dataclass
class SimVar:
    id: str
    name: str
    unit: str
    nominal: float
    decimals: int
    noise: float
    has_sp: bool = True
    warn: float = 0.0
    alarm: float = 0.0
    sp_tol: float = 0.0
    lag: float = 0.15


SIM_VARS = [
    SimVar("z1", "Zona 1", "°C", 160, 0, 0.3, warn=3, alarm=6, sp_tol=1),
    SimVar("z2", "Zona 2", "°C", 170, 0, 0.3, warn=3, alarm=6, sp_tol=1),
    SimVar("z3", "Zona 3", "°C", 180, 0, 0.3, warn=3, alarm=6, sp_tol=1),
    SimVar("z4", "Zona 4", "°C", 190, 0, 0.3, warn=3, alarm=6, sp_tol=1),
    SimVar("z5", "Zona 5", "°C", 195, 0, 0.3, warn=3, alarm=6, sp_tol=1),
    SimVar("cuello", "Cuello", "°C", 200, 0, 0.3, warn=3, alarm=6, sp_tol=1),
    SimVar("cabezal", "Cabezal", "°C", 205, 0, 0.3, warn=3, alarm=6, sp_tol=1),
    SimVar("dado", "Dado", "°C", 210, 0, 0.3, warn=3, alarm=6, sp_tol=1),
    SimVar("rpm", "Husillo", "rpm", 45.0, 1, 0.15, warn=1.5, alarm=3, sp_tol=0.5, lag=0.3),
    SimVar("vel", "Velocidad linea", "m/min", 350.0, 1, 0.8, warn=5, alarm=10, sp_tol=2, lag=0.3),
    SimVar("presion", "Presion fundido", "bar", 250, 0, 2.0, has_sp=False, warn=20, alarm=35),
    SimVar("carga", "Carga motor", "%", 65, 0, 0.8, has_sp=False, warn=10, alarm=15),
    SimVar("diam", "Diametro ext.", "mm", 3.20, 2, 0.004, has_sp=False, warn=0.03, alarm=0.05),
    SimVar("exc", "Excentricidad", "%", 5.0, 1, 0.3, has_sp=False, warn=3, alarm=5),
    SimVar("agua", "Agua enfriam.", "°C", 25.0, 1, 0.15, has_sp=False, warn=3, alarm=5),
]

COL_LABEL, COL_SP, COL_ACT = 60, 420, 640
BOX_W, BOX_H = 180, 36
ROW_Y0, ROW_DY = 150, 42
TITLE_RECT = Rect(x=40, y=20, w=420, h=44)
RECIPE_RECT = Rect(x=880, y=24, w=360, h=36)


def _font(size: int = FONT_SIZE) -> ImageFont.ImageFont:
    try:
        return ImageFont.truetype("DejaVuSansMono.ttf", size)
    except OSError:
        return ImageFont.load_default(size=size)


def _row_y(i: int) -> int:
    return ROW_Y0 + i * ROW_DY


def _box(col: int, i: int) -> Rect:
    return Rect(x=col, y=_row_y(i), w=BOX_W, h=BOX_H)


class Scenario:
    """Guion de fallas que se repite cada `period` segundos."""

    def __init__(self, period: float = 600.0):
        self.period = period

    def apply(self, t: float, sp: dict[str, float], disturb: dict[str, float]) -> None:
        phase = t % self.period
        # 60-180 s: operador ajusta Zona 3 fuera de receta.
        if 60 <= phase < 180:
            sp["z3"] = 188
        # 200-400 s: el diámetro deriva lentamente hacia arriba.
        if 200 <= phase < 400:
            disturb["diam"] = (phase - 200) / 60 * 0.012
        # 420-500 s: pico de presión de fundido (filtro tapándose).
        if 420 <= phase < 500:
            disturb["presion"] = 45 * math.sin((phase - 420) / 80 * math.pi)


class HmiSimulator:
    def __init__(self, scenario: Optional[Scenario] = None, seed: int = 1,
                 clock: Callable[[], float] = time.monotonic):
        self.clock = clock
        self.t0 = clock()
        self.scenario = scenario if scenario is not None else Scenario()
        self.rng = random.Random(seed)
        self.sp = {v.id: v.nominal for v in SIM_VARS}
        self.act = {v.id: v.nominal for v in SIM_VARS}
        self.overrides: dict[str, float] = {}
        self.recipe_name = RECIPE_NAME
        self.font = _font()
        self.title_font = _font(30)

    def set_setpoint(self, var_id: str, value: float) -> None:
        self.overrides[var_id] = value

    def update(self) -> None:
        t = self.clock() - self.t0
        sp = {v.id: v.nominal for v in SIM_VARS}
        disturb: dict[str, float] = {}
        if self.scenario:
            self.scenario.apply(t, sp, disturb)
        sp.update(self.overrides)
        self.sp = sp
        for v in SIM_VARS:
            target = sp[v.id] + disturb.get(v.id, 0.0)
            self.act[v.id] += (target - self.act[v.id]) * v.lag + self.rng.gauss(0, v.noise)

    def displayed(self, var_id: str, kind: str) -> str:
        v = next(x for x in SIM_VARS if x.id == var_id)
        value = self.sp[var_id] if kind == "sp" else self.act[var_id]
        return f"{value:.{v.decimals}f}"

    def render(self) -> np.ndarray:
        img = Image.new("RGB", (W, H), BG)
        d = ImageDraw.Draw(img)
        d.text((TITLE_RECT.x + 6, TITLE_RECT.y + 4), TITLE, font=self.title_font, fill=FG)
        d.rectangle(_xy(RECIPE_RECT), fill=BOX_BG)
        d.text((RECIPE_RECT.x + 10, RECIPE_RECT.y + 6), self.recipe_name, font=self.font, fill=FG)
        d.text((COL_SP + 40, ROW_Y0 - 40), "CONSIGNA", font=self.font, fill=FG)
        d.text((COL_ACT + 50, ROW_Y0 - 40), "REAL", font=self.font, fill=FG)
        for i, v in enumerate(SIM_VARS):
            y = _row_y(i)
            d.text((COL_LABEL, y + 6), f"{v.name} [{v.unit}]", font=self.font, fill=FG)
            if v.has_sp:
                self._value(d, _box(COL_SP, i), self.displayed(v.id, "sp"), SPC)
            self._value(d, _box(COL_ACT, i), self.displayed(v.id, "act"), VAL)
        return np.asarray(img)[:, :, ::-1].copy()

    def _value(self, d: ImageDraw.ImageDraw, r: Rect, text: str, color) -> None:
        d.rectangle(_xy(r), fill=BOX_BG)
        tw = d.textlength(text, font=self.font)
        d.text((r.x + r.w - 12 - tw, r.y + 6), text, font=self.font, fill=color)

    def render_text_sample(self, text: str) -> np.ndarray:
        """Imagen de una caja de valor con `text`, para enseñar el OCR de plantillas."""
        w = int(self.font.getlength(text)) + 40
        img = Image.new("RGB", (w, BOX_H), BOX_BG)
        ImageDraw.Draw(img).text((20, 6), text, font=self.font, fill=VAL)
        return np.asarray(img)[:, :, ::-1].copy()


def _xy(r: Rect) -> tuple[int, int, int, int]:
    return r.x, r.y, r.x + r.w - 1, r.y + r.h - 1


class SimulatorSource:
    def __init__(self, sim: Optional[HmiSimulator] = None):
        self.sim = sim or HmiSimulator()

    def grab(self) -> np.ndarray:
        self.sim.update()
        return self.sim.render()


def demo_config() -> AppConfig:
    ocr = OcrOptions(invert="auto", scale=2.0)
    variables: list[Variable] = [
        Variable(id="receta_hmi", name="Receta en HMI", kind="text", group="Receta", page="principal",
                 region=RECIPE_RECT, ocr=ocr, trend=False),
    ]
    for i, v in enumerate(SIM_VARS):
        group = "Temperaturas" if v.unit == "°C" and v.id != "agua" else (
            "Calidad" if v.id in ("diam", "exc") else "Proceso")
        if v.has_sp:
            variables.append(Variable(
                id=f"{v.id}_sp", name=f"{v.name} consigna", unit=v.unit, group=group, kind="setpoint",
                page="principal", region=_box(COL_SP, i), decimals=v.decimals, ocr=ocr, trend=False,
                valid_min=0, valid_max=v.nominal * 3))
        variables.append(Variable(
            id=v.id, name=v.name, unit=v.unit, group=group, kind="actual", page="principal",
            region=_box(COL_ACT, i), setpoint_var=f"{v.id}_sp" if v.has_sp else None,
            decimals=v.decimals, ocr=ocr, valid_min=0, valid_max=v.nominal * 3,
            max_step=max(v.alarm * 4, v.nominal * 0.2)))
    return AppConfig(
        machine_name="Demo línea de cable",
        general=GeneralSettings(ocr_engine="template", sample_interval_s=1.0, recipe_name_var="receta_hmi",
                                trend_window_min=5, trend_horizon_min=5, spc_subgroup_s=10,
                                debounce_samples=2),
        pages=[Page(id="principal", name="Principal", anchor=TITLE_RECT, match_threshold=0.8)],
        variables=variables,
    )


def demo_recipe() -> Recipe:
    limits: dict[str, Limit] = {}
    for v in SIM_VARS:
        if v.has_sp:
            limits[f"{v.id}_sp"] = Limit(nominal=v.nominal, warn=v.sp_tol, alarm=v.sp_tol * 3)
        limits[v.id] = Limit(nominal=v.nominal, warn=v.warn, alarm=v.alarm)
    return Recipe(name=RECIPE_NAME, description="Cable THHN 12 AWG, aislamiento PVC negro",
                  meta={"calibre": "12 AWG", "material": "PVC"}, limits=limits)


TEACH_STRINGS = ["0123456789", "-.5", "THHN-12AWG-NEGRO", "ABCDEFGHIJKLM", "NOPQRSTUV", "WXYZ", "45.0 3.20"]


def teach_template(ocr, sim: HmiSimulator, opts: OcrOptions) -> None:
    for s in TEACH_STRINGS:
        ocr.teach(sim.render_text_sample(s), s, opts)
