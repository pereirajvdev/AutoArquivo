"""Janela principal: navegação lateral, diretório padrão e páginas dos módulos."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ..config import APP_NAME, APP_VERSION, MODULES, ModuleSpec, Settings
from .base_page import AppContext, ModulePage
from .dialogs import confirm
from .ferias_page import FeriasPage
from .icons import icon, pixmap, toggle_icon
from .licencas_page import LicencasPage
from .registros_page import RegistrosPage
from .settings_dialog import SettingsDialog
from .widgets import ICON_SIZE, PathSelector

log = logging.getLogger(__name__)

# Para registrar um novo módulo: ModuleSpec em config.MODULES + fábrica aqui.
PAGE_FACTORIES: dict[str, Callable[[ModuleSpec, AppContext], ModulePage]] = {
    "ficha": RegistrosPage,
    "faltas": RegistrosPage,
    "licencas": LicencasPage,
    "ferias": FeriasPage,
}


class MainWindow(QMainWindow):
    def __init__(self, settings: Settings) -> None:
        super().__init__()
        self.settings = settings
        self.setWindowTitle(f"{APP_NAME} — Painel de Automações de RH")
        self.setWindowIcon(icon("clipboard", "#1D4ED8"))
        self.setMinimumSize(1040, 680)
        self.resize(1280, 800)

        self.pages: dict[str, ModulePage] = {}
        self.nav_buttons: dict[str, QPushButton] = {}

        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        outer = QHBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        outer.addWidget(self._build_sidebar())
        content = QVBoxLayout()
        content.setContentsMargins(0, 0, 0, 0)
        content.setSpacing(0)
        content.addWidget(self._build_topbar())
        self.stack = QStackedWidget()
        content.addWidget(self.stack, 1)
        outer.addLayout(content, 1)

        ctx = AppContext(settings, lambda: self.servidores.path(),
                         lambda text: self.statusBar().showMessage(text, 6000))
        for spec in MODULES:
            factory = PAGE_FACTORIES.get(spec.key)
            if factory is None:
                log.warning("Módulo '%s' sem página registrada.", spec.key)
                continue
            page = factory(spec, ctx)
            self.pages[spec.key] = page
            self.stack.addWidget(page)
        self._build_nav()

        self.statusBar().showMessage("Pronto.")
        self._restore_state()

    # ------------------------------------------------------------ construção
    def _build_sidebar(self) -> QFrame:
        self.sidebar = QFrame()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setFixedWidth(224)
        self.side_layout = QVBoxLayout(self.sidebar)
        self.side_layout.setContentsMargins(0, 0, 0, 0)
        self.side_layout.setSpacing(2)

        brand_box = QWidget()
        brand_layout = QHBoxLayout(brand_box)
        brand_layout.setContentsMargins(18, 22, 18, 22)
        brand_layout.setSpacing(10)
        glyph = QLabel()
        glyph.setPixmap(pixmap("clipboard", "#FFFFFF", 64).scaled(
            28, 28, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        names = QVBoxLayout()
        names.setSpacing(0)
        title = QLabel(APP_NAME)
        title.setObjectName("brand")
        sub = QLabel("Automações de RH")
        sub.setObjectName("brandSub")
        names.addWidget(title)
        names.addWidget(sub)
        brand_layout.addWidget(glyph)
        brand_layout.addLayout(names, 1)
        self.side_layout.addWidget(brand_box)
        return self.sidebar

    def _build_nav(self) -> None:
        group = QButtonGroup(self)
        group.setExclusive(True)
        for spec in MODULES:
            page = self.pages.get(spec.key)
            if page is None:
                continue
            button = QPushButton(spec.title)
            button.setObjectName("nav")
            button.setCheckable(True)
            button.setIcon(toggle_icon(spec.icon, "#B6C2D9", "#FFFFFF"))
            button.setIconSize(ICON_SIZE)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setToolTip(spec.subtitle)
            button.clicked.connect(lambda _checked=False, k=spec.key: self.show_module(k))
            group.addButton(button)
            self.side_layout.addWidget(button)
            self.nav_buttons[spec.key] = button

        self.side_layout.addStretch(1)
        settings_btn = QPushButton("  Configurações")
        settings_btn.setObjectName("navFooter")
        settings_btn.setIcon(icon("settings", "#B6C2D9"))
        settings_btn.setIconSize(ICON_SIZE)
        settings_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        settings_btn.clicked.connect(self._open_settings)
        self.side_layout.addWidget(settings_btn)
        version = QLabel(f"  v{APP_VERSION}")
        version.setObjectName("version")
        version.setContentsMargins(18, 4, 0, 14)
        self.side_layout.addWidget(version)

    def _build_topbar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("topbar")
        row = QHBoxLayout(bar)
        row.setContentsMargins(24, 12, 24, 12)
        row.setSpacing(12)

        caption = QVBoxLayout()
        caption.setSpacing(0)
        label = QLabel("DIRETÓRIO PADRÃO")
        label.setObjectName("sectionLabel")
        hint = QLabel("Pasta “Servidores” usada pelos scripts")
        hint.setObjectName("muted")
        caption.addWidget(label)
        caption.addWidget(hint)
        row.addLayout(caption)

        self.servidores = PathSelector(
            self.settings, "servidores", "dir", r"Selecione a pasta Servidores (ex.: D:\RH\Servidores)",
            "Selecionar a pasta Servidores", button_text="Localizar diretório")
        self.servidores.set_path(self.settings.servidores_dir)
        self.servidores.pathChanged.connect(self._on_servidores_changed)
        row.addWidget(self.servidores, 1)

        self.servidores_status = QLabel()
        self.servidores_status.setFixedWidth(24)
        row.addWidget(self.servidores_status)
        self.servidores.edit.textChanged.connect(lambda _t: self._update_servidores_status())
        self._update_servidores_status()
        return bar

    # -------------------------------------------------------------- comportamento
    def _on_servidores_changed(self, path: str) -> None:
        self.settings.servidores_dir = path
        self.settings.save()
        self.statusBar().showMessage("Diretório padrão atualizado.", 4000)

    def _update_servidores_status(self) -> None:
        text = self.servidores.path()
        if not text:
            self.servidores_status.clear()
            self.servidores_status.setToolTip("")
            return
        try:
            ok = Path(text).is_dir()
        except OSError:
            ok = False
        name, color = ("check", "#15803D") if ok else ("alert", "#B91C1C")
        self.servidores_status.setPixmap(pixmap(name, color, 64).scaled(
            18, 18, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        self.servidores_status.setToolTip("Diretório encontrado." if ok else "Diretório não encontrado.")

    def show_module(self, key: str) -> None:
        page = self.pages.get(key)
        if page is None:
            return
        self.stack.setCurrentWidget(page)
        self.nav_buttons[key].setChecked(True)
        self.settings.preferences["last_module"] = key

    def _open_settings(self) -> None:
        SettingsDialog(self.settings, self).exec()

    # ------------------------------------------------------------ estado/ciclo de vida
    def _restore_state(self) -> None:
        geometry = self.settings.preferences.get("window_geometry")
        if isinstance(geometry, str) and geometry:
            try:
                self.restoreGeometry(QByteArray.fromBase64(geometry.encode("ascii")))
            except Exception:  # noqa: BLE001 - geometria inválida é irrelevante
                log.debug("Geometria da janela inválida; ignorando.")
        last = self.settings.preferences.get("last_module")
        self.show_module(last if last in self.pages else next(iter(self.pages)))

    def closeEvent(self, event) -> None:  # noqa: N802 - API do Qt
        running = [p for p in self.pages.values() if p.is_running]
        if running:
            names = ", ".join(p.spec.title for p in running)
            if not confirm(
                    self, "Automação em andamento",
                    f"Há automação em execução ({names}).\n"
                    "Fechar o painel interromperá o processamento. Deseja continuar?",
                    "Fechar e interromper", danger=True):
                event.ignore()
                return
            for page in running:
                page.shutdown()
        self.settings.preferences["window_geometry"] = self.saveGeometry().toBase64().data().decode("ascii")
        self.settings.save()
        event.accept()
