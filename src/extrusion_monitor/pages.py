"""Identifica qué pantalla del HMI está visible mediante imágenes ancla."""
from __future__ import annotations

import cv2
import numpy as np

from .capture import crop, load_png
from .config import AppConfig, Rect, Workspace

SEARCH_MARGIN = 12  # px de tolerancia a desplazamientos de la ventana


class PageDetector:
    def __init__(self, config: AppConfig, workspace: Workspace):
        self.config = config
        self._anchors: dict[str, np.ndarray] = {}
        for p in config.pages:
            img = load_png(workspace.page_anchor_file(p.id))
            if img is not None:
                self._anchors[p.id] = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    def score(self, frame: np.ndarray, page_id: str) -> float:
        page = self.config.page(page_id)
        anchor = self._anchors.get(page_id)
        if page is None or anchor is None:
            return 0.0
        r = page.anchor
        area = Rect(x=r.x - SEARCH_MARGIN, y=r.y - SEARCH_MARGIN,
                    w=r.w + 2 * SEARCH_MARGIN, h=r.h + 2 * SEARCH_MARGIN)
        region = cv2.cvtColor(crop(frame, area), cv2.COLOR_BGR2GRAY)
        if region.shape[0] < anchor.shape[0] or region.shape[1] < anchor.shape[1]:
            return 0.0
        if float(anchor.std()) < 1.0:
            # Ancla uniforme: la correlación normalizada no está definida; compara diferencia media.
            diff = np.abs(region.astype(np.float32).mean() - anchor.astype(np.float32).mean())
            return float(max(0.0, 1.0 - diff / 64.0))
        res = cv2.matchTemplate(region, anchor, cv2.TM_CCOEFF_NORMED)
        return float(np.nan_to_num(res.max()))

    def visible_pages(self, frame: np.ndarray) -> set[str]:
        return {p.id for p in self.config.pages if self.score(frame, p.id) >= p.match_threshold}
