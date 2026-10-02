"""Configuración del dock: posición, tamaño, comportamiento e indicadores (mismo editor que el tablero de Inicio)."""
from __future__ import annotations

from PySide6.QtWidgets import (QCheckBox, QComboBox, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QPushButton,
                               QSpinBox)

from ..config import DOCK_CHART_MIN, KPI_KINDS, AppConfig, DockSettings, HomeSettings, default_dock_tiles
from ..i18n import tr
from .home_config_dialog import HomeConfigDialog

EDGES = [("top", "Superior"), ("bottom", "Inferior"), ("left", "Izquierda"), ("right", "Derecha")]
PRESETS = [("Delgado", 40), ("Chico", 96), ("Mediano", 132), ("Grande", 184)]
MAX_UNITS = 4


class DockConfigDialog(HomeConfigDialog):
    def __init__(self, config: AppConfig, parent=None):
        d = config.dock
        super().__init__(config, parent, home=HomeSettings(columns=MAX_UNITS, tiles=d.tiles),
                         kinds=KPI_KINDS + ("var",))
        self.setWindowTitle("Dock al minimizar")
        self.reset_position = False
        # del editor del tablero no aplican las columnas ni el alto: el dock es una sola fila (o columna)
        self.lbl_cols.hide()
        self.sp_cols.hide()
        self.sp_h.hide()
        self.sp_w.setMaximum(MAX_UNITS)
        self.lbl_tiles.setText("<b>Indicadores del dock</b> (en orden)")
        self.btn_reset.setText("Restablecer indicadores por defecto")

        box = QGroupBox("Dock")
        form = QFormLayout(box)
        intro = QLabel("Al minimizar el programa queda una barra compacta, siempre visible sobre el HMI, con el estado "
                       "de la máquina y los indicadores elegidos. No aparece en la lectura de pantalla ni estorba a "
                       "los recorridos. Se arrastra desde la agarradera (⠿); doble clic en ella restaura el programa.")
        intro.setWordWrap(True)
        form.addRow(intro)
        self.chk_enabled = QCheckBox("Mostrar el dock al minimizar")
        self.chk_enabled.setChecked(d.enabled)
        form.addRow(self.chk_enabled)
        row = QHBoxLayout()
        self.cmb_edge = QComboBox()
        for k, label in EDGES:
            self.cmb_edge.addItem(label, k)
        self.cmb_edge.setCurrentIndex(max(0, self.cmb_edge.findData(d.edge)))
        self.cmb_edge.currentIndexChanged.connect(self._edge_changed)
        row.addWidget(self.cmb_edge)
        self.btn_center = QPushButton("Volver a centrar en el borde")
        self.btn_center.setToolTip("Olvida la posición a la que se arrastró el dock")
        self.btn_center.clicked.connect(self._edge_changed)
        row.addWidget(self.btn_center)
        row.addStretch(1)
        form.addRow("Posición:", row)
        thick = QHBoxLayout()
        self.sp_thick = QSpinBox()
        self.sp_thick.setRange(28, 260)
        self.sp_thick.setSingleStep(4)
        self.sp_thick.setSuffix(" px")
        self.sp_thick.setValue(d.thickness)
        self.sp_thick.valueChanged.connect(self._thick_changed)
        thick.addWidget(self.sp_thick)
        for label, px in PRESETS:
            b = QPushButton(label)
            b.clicked.connect(lambda _=False, px=px: self.sp_thick.setValue(px))
            thick.addWidget(b)
        thick.addStretch(1)
        form.addRow("Grosor:", thick)
        self.lbl_thick = QLabel()
        self.lbl_thick.setWordWrap(True)
        form.addRow("", self.lbl_thick)
        self._thick_changed(d.thickness)
        self.chk_ghost = QCheckBox("Al acercar el mouse se desvanece y deja pasar los clics al HMI")
        self.chk_ghost.setChecked(d.ghost_on_hover)
        form.addRow(self.chk_ghost)
        self.chk_alert = QCheckBox("Parpadear y mostrar el mensaje al aparecer una alarma")
        self.chk_alert.setChecked(d.alarm_alert)
        form.addRow(self.chk_alert)
        self.root_layout.insertWidget(0, box)

    def _thick_changed(self, v: int) -> None:
        if v < DOCK_CHART_MIN:
            self.lbl_thick.setText(tr("Con este grosor no caben gráficas: cada indicador se muestra como nombre y "
                                      "valor, con color según su rango."))
        else:
            self.lbl_thick.setText(tr("Con menos de {n} px los indicadores pasan a solo valor con color.",
                                      n=DOCK_CHART_MIN))

    def _edge_changed(self, *_):
        self.reset_position = True  # al cambiar de borde (o pedirlo) vuelve al centro de ese borde

    def _default_home(self) -> HomeSettings:
        return HomeSettings(columns=MAX_UNITS, tiles=default_dock_tiles())

    @property
    def dock(self) -> DockSettings:
        tiles = [t.model_copy(update={"height": 1, "width": min(t.width, MAX_UNITS)}) for t in self.home.tiles]
        return DockSettings(enabled=self.chk_enabled.isChecked(), edge=self.cmb_edge.currentData(),
                            thickness=self.sp_thick.value(), tiles=tiles,
                            ghost_on_hover=self.chk_ghost.isChecked(), alarm_alert=self.chk_alert.isChecked())
