"""Identifica qué pantallas del HMI están visibles mediante imágenes ancla (árbol de páginas)."""
from __future__ import annotations

import cv2
import numpy as np

from .capture import crop, load_png
from .config import AppConfig, Rect, Workspace

SEARCH_MARGIN = 12  # px de tolerancia a desplazamientos de la ventana
# Diferencia media de color (0-255) a partir de la cual el ancla se considera distinta.
# Distingue una pestaña seleccionada (resaltada) de la misma pestaña sin seleccionar.
COLOR_SCALE = 80.0


class PageDetector:
    def __init__(self, config: AppConfig, anchors: dict[str, np.ndarray]):
        self.config = config
        self._anchors = {k: v for k, v in anchors.items() if v is not None}

    @classmethod
    def from_workspace(cls, config: AppConfig, workspace: Workspace) -> "PageDetector":
        anchors = {}
        for p in config.pages:
            if p.anchor is not None:
                img = load_png(workspace.page_anchor_file(p.id))
                if img is not None:
                    anchors[p.id] = img
        return cls(config, anchors)

    def score(self, frame: np.ndarray, page_id: str) -> float:
        """Coincidencia 0..1 del ancla de la página (forma y color)."""
        page = self.config.page(page_id)
        anchor = self._anchors.get(page_id)
        if page is None or page.anchor is None or anchor is None:
            return 0.0
        r = page.anchor
        area = Rect(x=r.x - SEARCH_MARGIN, y=r.y - SEARCH_MARGIN,
                    w=r.w + 2 * SEARCH_MARGIN, h=r.h + 2 * SEARCH_MARGIN)
        region = crop(frame, area)
        ah, aw = anchor.shape[:2]
        if region.shape[0] < ah or region.shape[1] < aw:
            return 0.0
        g_region = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)
        g_anchor = cv2.cvtColor(anchor, cv2.COLOR_BGR2GRAY)
        if float(g_anchor.std()) < 1.0:
            res = -cv2.matchTemplate(region, anchor, cv2.TM_SQDIFF_NORMED)
            shape = 1.0
        else:
            res = cv2.matchTemplate(g_region, g_anchor, cv2.TM_CCOEFF_NORMED)
            shape = None
        _, best, _, (bx, by) = cv2.minMaxLoc(np.nan_to_num(res))
        if shape is None:
            shape = float(best)
        match = region[by:by + ah, bx:bx + aw].astype(np.float32)
        mad = float(np.abs(match - anchor.astype(np.float32)).mean())
        color = max(0.0, 1.0 - mad / COLOR_SCALE)
        return max(0.0, min(shape, color))

    def visible_pages(self, frame: np.ndarray) -> set[str]:
        """Una página es visible si su ancla coincide (o no tiene ancla) y su padre es visible."""
        cache: dict[str, bool] = {}

        def visible(pid: str, depth: int = 0) -> bool:
            if pid in cache:
                return cache[pid]
            page = self.config.page(pid)
            if page is None or depth > 32:
                return False
            ok = page.parent is None or visible(page.parent, depth + 1)
            if ok and page.anchor is not None:
                ok = self.score(frame, pid) >= page.match_threshold
            cache[pid] = ok
            return ok

        return {p.id for p in self.config.pages if visible(p.id)}
