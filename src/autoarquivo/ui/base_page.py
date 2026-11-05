"""Base comum das páginas de módulo."""

from __future__ import annotations

import functools
import logging
from dataclasses import dataclass
from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QScrollArea, QVBoxLayout, QWidget

from ..config import ModuleSpec, Settings
from ..validators import ValidationError
from .dialogs import show_error, show_warning
from .run_panel import RunPanel
from .widgets import PageHeader

log = logging.getLogger(__name__)


@dataclass
class AppContext:
    """O que as páginas recebem da janela principal."""

    settings: Settings
    get_servidores: Callable[[], str]
    notify: Callable[[str], None]


def guarded(method: Callable[[QWidget], None]) -> Callable[..., None]:
    """Decorador para slots sem argumentos: nenhuma exceção derruba a aplicação.

    Erros de validação viram aviso; qualquer outro erro é registrado em log e
    mostrado ao usuário. Ignora os argumentos extras enviados pelos sinais do Qt.
    """

    @functools.wraps(method)
    def wrapper(self: QWidget, *_args) -> None:
        try:
            method(self)
        except ValidationError as exc:
            show_warning(self, "Verifique os dados", str(exc))
        except Exception as exc:  # noqa: BLE001
            log.exception("Erro inesperado em %s", method.__name__)
            show_error(self, "Erro inesperado", f"Ocorreu um erro inesperado:\n{exc}")

    return wrapper


class ModulePage(QWidget):
    """Página de um módulo: cabeçalho padrão e ciclo de vida da execução."""

    def __init__(self, spec: ModuleSpec, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("page")
        self.spec = spec
        self.ctx = ctx
        self.run_panel: RunPanel | None = None

    def make_header(self) -> PageHeader:
        return PageHeader(self.spec)

    @property
    def is_running(self) -> bool:
        return self.run_panel is not None and self.run_panel.is_running

    def shutdown(self) -> None:
        if self.run_panel is not None:
            self.run_panel.shutdown()


def scroll_column(inner: QWidget) -> QScrollArea:
    """Envolve uma coluna de cards numa área rolável que acompanha a largura."""
    inner.setObjectName("pageBody")
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setFrameShape(QScrollArea.Shape.NoFrame)
    area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    area.setWidget(inner)
    area.viewport().setAutoFillBackground(False)
    return area


def column_layout(widget: QWidget, spacing: int = 14) -> QVBoxLayout:
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(0, 0, 8, 0)
    layout.setSpacing(spacing)
    return layout
