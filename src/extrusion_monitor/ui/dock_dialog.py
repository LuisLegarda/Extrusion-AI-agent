"""Configuración del dock: posición, tamaño, comportamiento e indicadores (mismo editor que el tablero de Inicio)."""
from __future__ import annotations

from PySide6.QtWidgets import QCheckBox, QComboBox, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QPushButton

from ..config import KPI_KINDS, AppConfig, DockSettings, HomeSettings, default_dock_tiles
from .home_config_dialog import HomeConfigDialog

EDGES = [("top", "Superior"), ("bottom", "Inferior"), ("left", "Izquierda"), ("right", "Derecha")]
SIZES = [("small", "Chico"), ("medium", "Mediano"), ("large", "Grande")]
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
        self.cmb_size = QComboBox()
        for k, label in SIZES:
            self.cmb_size.addItem(label, k)
        self.cmb_size.setCurrentIndex(max(0, self.cmb_size.findData(d.size)))
        form.addRow("Tamaño:", self.cmb_size)
        self.chk_ghost = QCheckBox("Al acercar el mouse se desvanece y deja pasar los clics al HMI")
        self.chk_ghost.setChecked(d.ghost_on_hover)
        form.addRow(self.chk_ghost)
        self.chk_alert = QCheckBox("Parpadear y mostrar el mensaje al aparecer una alarma")
        self.chk_alert.setChecked(d.alarm_alert)
        form.addRow(self.chk_alert)
        self.root_layout.insertWidget(0, box)

    def _edge_changed(self, *_):
        self.reset_position = True  # al cambiar de borde (o pedirlo) vuelve al centro de ese borde

    def _default_home(self) -> HomeSettings:
        return HomeSettings(columns=MAX_UNITS, tiles=default_dock_tiles())

    @property
    def dock(self) -> DockSettings:
        tiles = [t.model_copy(update={"height": 1, "width": min(t.width, MAX_UNITS)}) for t in self.home.tiles]
        return DockSettings(enabled=self.chk_enabled.isChecked(), edge=self.cmb_edge.currentData(),
                            size=self.cmb_size.currentData(), tiles=tiles,
                            ghost_on_hover=self.chk_ghost.isChecked(), alarm_alert=self.chk_alert.isChecked())
