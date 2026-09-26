"""Comportamiento aprendido: variación normal de cada variable y relación entre varias.

Se entrena con un periodo del historial en que el proceso estuvo bien. En vivo se calcula
la distancia de Mahalanobis (D²) del vector actual contra lo aprendido: si una variable se
sale de su variación normal o si dejan de cumplirse las relaciones habituales entre ellas
(p. ej. la presión sube sin que suban las rpm), D² supera el umbral aprendido.
"""
from __future__ import annotations

import json
import os
import time
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

import numpy as np
from pydantic import BaseModel, Field

from .statistics import align, correlation

MIN_ROWS = 30
STRONG_CORR = 0.6


class BehaviorModel(BaseModel):
    id: str
    name: str
    variables: list[str]
    enabled: bool = True
    # Solo se evalúa con esta receta activa (None = siempre).
    recipe: Optional[str] = None
    sensitivity: float = Field(1.0, ge=0.3, le=5.0)  # >1 = menos sensible
    z_limit: float = Field(4.0, ge=1.5, le=10.0)  # variación normal por variable (σ)
    # Resultado del entrenamiento
    trained_from: float = 0.0
    trained_to: float = 0.0
    trained_at: float = 0.0
    step_s: float = 10.0
    n_samples: int = 0
    mean: list[float] = Field(default_factory=list)
    std: list[float] = Field(default_factory=list)
    minimum: list[float] = Field(default_factory=list)
    maximum: list[float] = Field(default_factory=list)
    cov_inv: list[list[float]] = Field(default_factory=list)
    corr: list[list[float]] = Field(default_factory=list)
    d2_threshold: float = 0.0

    @property
    def trained(self) -> bool:
        return self.n_samples > 0 and len(self.mean) == len(self.variables)


class TrainingError(ValueError):
    pass


def train(model: BehaviorModel, series: dict[str, tuple[np.ndarray, np.ndarray]], start: float, end: float,
          step_s: float, max_gap_s: float) -> BehaviorModel:
    """Entrena `model` con las series del historial entre `start` y `end`."""
    sub = {v: series.get(v, (np.empty(0), np.empty(0))) for v in model.variables}
    missing = [v for v, (t, _) in sub.items() if len(t) == 0]
    if missing:
        raise TrainingError(f"Sin datos en el periodo para: {', '.join(missing)}")
    _, m, names = align(sub, step_s, max_gap_s, start, end)
    if names != model.variables:
        m = m[:, [names.index(v) for v in model.variables]]
    if m.shape[0] < MIN_ROWS:
        raise TrainingError(f"Solo hay {m.shape[0]} muestras alineadas; se necesitan al menos {MIN_ROWS}. "
                            "Amplía el periodo o reduce la resolución.")
    mean = m.mean(axis=0)
    std = m.std(axis=0, ddof=1)
    # Piso de σ: una variable casi constante (resolución del HMI) no debe volverse hipersensible.
    resolution = np.array([_resolution(m[:, i]) for i in range(m.shape[1])])
    std = np.maximum(std, resolution)
    cov = np.cov(m, rowvar=False) if m.shape[1] > 1 else np.array([[std[0] ** 2]])
    cov = np.atleast_2d(cov)
    cov = cov + np.diag(np.maximum(std ** 2 * 0.01, resolution ** 2))  # regularización
    cov_inv = np.linalg.pinv(cov)
    d = m - mean
    d2 = np.einsum("ij,jk,ik->i", d, cov_inv, d)
    # Umbral empírico: percentil 99.5 del entrenamiento con margen, nunca menor al χ² aproximado.
    k = m.shape[1]
    chi_like = k + 3 * np.sqrt(2 * k)
    threshold = max(float(np.percentile(d2, 99.5)) * 1.3, chi_like)
    model.trained_from, model.trained_to, model.trained_at = start, end, time.time()
    model.step_s, model.n_samples = step_s, int(m.shape[0])
    model.mean, model.std = mean.tolist(), std.tolist()
    model.minimum, model.maximum = m.min(axis=0).tolist(), m.max(axis=0).tolist()
    model.cov_inv = cov_inv.tolist()
    model.corr = np.nan_to_num(correlation(m)).tolist()
    model.d2_threshold = threshold
    return model


def _resolution(col: np.ndarray) -> float:
    vals = np.unique(np.round(col, 6))
    if len(vals) < 2:
        return max(abs(float(col[0])) * 1e-3, 1e-6) if len(col) else 1e-6
    return float(np.min(np.diff(vals)))


@dataclass
class BehaviorResult:
    model_id: str
    ts: float
    d2: float
    threshold: float
    z: dict[str, float]
    contributions: dict[str, float]  # porcentaje de D² atribuible a cada variable
    broken_pairs: list[tuple[str, str, float]] = field(default_factory=list)  # (a, b, desviación en σ)

    @property
    def ratio(self) -> float:
        return self.d2 / self.threshold if self.threshold > 0 else 0.0


def evaluate(model: BehaviorModel, values: dict[str, float], ts: float) -> Optional[BehaviorResult]:
    if not model.trained or any(v not in values for v in model.variables):
        return None
    x = np.array([values[v] for v in model.variables])
    mean, std = np.array(model.mean), np.array(model.std)
    d = x - mean
    inv = np.array(model.cov_inv)
    w = inv @ d
    d2 = float(d @ w)
    parts = d * w
    pos = np.clip(parts, 0, None)
    total = float(pos.sum()) or 1.0
    z = d / std
    res = BehaviorResult(
        model.id, ts, d2, model.d2_threshold * model.sensitivity,
        z={v: float(z[i]) for i, v in enumerate(model.variables)},
        contributions={v: float(100 * pos[i] / total) for i, v in enumerate(model.variables)})
    corr = np.array(model.corr)
    for i in range(len(x)):
        for j in range(i + 1, len(x)):
            r = corr[i, j]
            if abs(r) < STRONG_CORR:
                continue
            # Residuo de la relación estandarizada: z_j debería ≈ r·z_i.
            resid = (z[j] - r * z[i]) / np.sqrt(max(1 - r * r, 0.05))
            if abs(resid) > 3.5 * model.sensitivity:
                res.broken_pairs.append((model.variables[i], model.variables[j], float(resid)))
    return res


class BehaviorStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.models: list[BehaviorModel] = []
        self.load()

    def load(self) -> None:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            self.models = [BehaviorModel.model_validate(m) for m in raw]
        except (OSError, ValueError):
            self.models = []

    def save(self) -> None:
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps([m.model_dump() for m in self.models], indent=1), encoding="utf-8")
        os.replace(tmp, self.path)

    def get(self, model_id: str) -> Optional[BehaviorModel]:
        return next((m for m in self.models if m.id == model_id), None)

    def upsert(self, model: BehaviorModel) -> None:
        self.models = [m for m in self.models if m.id != model.id] + [model]
        self.save()

    def delete(self, model_id: str) -> None:
        self.models = [m for m in self.models if m.id != model_id]
        self.save()


class BehaviorMonitor:
    """Evalúa los modelos activos en cada ciclo y guarda la historia de D² para graficar."""

    def __init__(self, store: BehaviorStore, history_len: int = 1800):
        self.store = store
        self.history: dict[str, deque[tuple[float, float, float]]] = {}
        self.last: dict[str, BehaviorResult] = {}
        self.history_len = history_len

    def active(self, recipe: Optional[str]) -> list[BehaviorModel]:
        return [m for m in self.store.models
                if m.enabled and m.trained and (m.recipe is None or m.recipe == recipe)]

    def evaluate(self, now: float, values: dict[str, float], recipe: Optional[str],
                 label: Callable[[str], str]) -> tuple[dict, set]:
        """Devuelve (condiciones {clave: (nivel, mensaje)}, claves evaluadas)."""
        from .rules import Level  # import tardío: rules importa este módulo
        conds: dict[tuple[str, str], tuple[Level, str]] = {}
        evaluated: set[str] = set()
        for m in self.active(recipe):
            key = f"@{m.id}"
            res = evaluate(m, values, now)
            if res is None:
                continue  # faltan datos frescos: se mantiene el estado del hallazgo
            evaluated.add(key)
            self.last[m.id] = res
            h = self.history.setdefault(m.id, deque(maxlen=self.history_len))
            h.append((now, res.d2, res.threshold))
            out_z = [(v, z) for v, z in res.z.items() if abs(z) > m.z_limit * m.sensitivity]
            if res.d2 <= res.threshold and not out_z:
                continue
            level = Level.ALARM if res.d2 > 2 * res.threshold else Level.WARN
            parts = []
            top = sorted(res.contributions.items(), key=lambda kv: -kv[1])[:2]
            if res.d2 > res.threshold:
                parts.append(f"desviación {res.ratio:.1f}× lo normal; principal: " +
                             ", ".join(f"{label(v)} ({c:.0f} %, z={res.z[v]:+.1f})" for v, c in top if c > 5))
            for v, z in out_z:
                parts.append(f"{label(v)} fuera de su variación normal (z={z:+.1f})")
            for a, b, r in res.broken_pairs[:2]:
                parts.append(f"se rompió la relación {label(a)} ↔ {label(b)} ({r:+.1f}σ)")
            conds[("COMPORTAMIENTO", key)] = (level, f"Comportamiento «{m.name}»: " + "; ".join(parts))
        return conds, evaluated
