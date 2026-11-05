"""Componentes visuais reutilizáveis."""

from __future__ import annotations

from datetime import datetime
from html import escape
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QDir, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QKeySequence, QPainter, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLayout,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from ..config import ModuleSpec, Settings
from ..table_model import ItemTableModel
from .dialogs import confirm, show_warning
from .icons import icon, pixmap

ICON_SIZE = QSize(18, 18)


def set_prop(widget: QWidget, name: str, value) -> None:
    """Altera uma propriedade usada pelo QSS e reaplica o estilo."""
    widget.setProperty(name, value)
    style = widget.style()
    style.unpolish(widget)
    style.polish(widget)


def plural(n: int, singular: str, plural_: str) -> str:
    return f"{n} {singular if n == 1 else plural_}"


def make_button(text: str = "", icon_name: str | None = None, kind: str = "default",
                tooltip: str = "") -> QPushButton:
    """Botão com ícone. ``kind``: default | primary | danger | ghost."""
    button = QPushButton(text)
    if kind != "default":
        button.setObjectName(kind)
    colors = {"primary": "#FFFFFF", "danger": "#B91C1C", "ghost": "#64748B"}
    if icon_name:
        button.setIcon(icon(icon_name, colors.get(kind, "#334155")))
        button.setIconSize(ICON_SIZE)
    if tooltip:
        button.setToolTip(tooltip)
    button.setCursor(Qt.CursorShape.PointingHandCursor)
    return button


# ------------------------------------------------------------------------ Card
class Card(QFrame):
    """Painel branco com título; o conteúdo vai em ``body`` (QVBoxLayout)."""

    def __init__(self, title: str, subtitle: str = "", icon_name: str | None = None,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("card")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 14, 16, 16)
        outer.setSpacing(12)

        head = QHBoxLayout()
        head.setSpacing(8)
        if icon_name:
            glyph = QLabel()
            glyph.setPixmap(pixmap(icon_name, "#1D4ED8", 64).scaled(
                18, 18, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            head.addWidget(glyph)
        titles = QVBoxLayout()
        titles.setSpacing(1)
        label = QLabel(title)
        label.setObjectName("cardTitle")
        titles.addWidget(label)
        if subtitle:
            sub = QLabel(subtitle)
            sub.setObjectName("muted")
            sub.setWordWrap(True)
            titles.addWidget(sub)
        head.addLayout(titles, 1)
        self.header_extra = QHBoxLayout()
        head.addLayout(self.header_extra)
        outer.addLayout(head)

        self.body = QVBoxLayout()
        self.body.setSpacing(10)
        outer.addLayout(self.body, 1)

    def add(self, item: QWidget | QLayout, stretch: int = 0) -> None:
        if isinstance(item, QLayout):
            self.body.addLayout(item, stretch)
        else:
            self.body.addWidget(item, stretch)


class PageHeader(QWidget):
    """Cabeçalho de página: ícone do módulo, título e descrição."""

    def __init__(self, spec: ModuleSpec, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(14)
        badge = QLabel()
        badge.setObjectName("iconBadge")
        badge.setFixedSize(46, 46)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setPixmap(pixmap(spec.icon, "#1D4ED8", 64).scaled(
            24, 24, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        titles = QVBoxLayout()
        titles.setSpacing(0)
        title = QLabel(spec.title)
        title.setObjectName("pageTitle")
        sub = QLabel(spec.subtitle)
        sub.setObjectName("muted")
        titles.addWidget(title)
        titles.addWidget(sub)
        row.addWidget(badge)
        row.addLayout(titles, 1)


class FeedbackLabel(QLabel):
    """Mensagem curta de feedback (sucesso/erro) que some sozinha."""

    def __init__(self, parent: QWidget | None = None, timeout_ms: int = 7000) -> None:
        super().__init__(parent)
        self.setObjectName("feedback")
        self.setWordWrap(True)
        self.hide()
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(timeout_ms)
        self._timer.timeout.connect(self.hide)

    def show_message(self, text: str, kind: str = "ok") -> None:
        self.setText(text)
        set_prop(self, "kind", kind)
        self.show()
        self._timer.start()

    def clear_message(self) -> None:
        self._timer.stop()
        self.hide()


# ---------------------------------------------------------------- PathSelector
class PathSelector(QWidget):
    """Campo de caminho + botão de busca, com memória do último diretório usado.

    ``pathChanged`` é emitido ao escolher no diálogo ou ao concluir a digitação.
    """

    pathChanged = Signal(str)

    def __init__(
        self,
        settings: Settings,
        key: str,
        mode: str = "dir",  # "dir" | "file"
        placeholder: str = "",
        dialog_title: str = "Selecionar",
        file_filter: str = "",
        editable: bool = True,
        clearable: bool = False,
        button_text: str = "Procurar…",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._settings = settings
        self._key = key
        self._mode = mode
        self._title = dialog_title
        self._filter = file_filter

        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)
        self.edit = QLineEdit()
        self.edit.setPlaceholderText(placeholder)
        self.edit.setReadOnly(not editable)
        self.edit.setClearButtonEnabled(False)
        row.addWidget(self.edit, 1)

        self.btn_browse = make_button(
            button_text, "folder" if mode == "dir" else "sheet", tooltip=dialog_title)
        row.addWidget(self.btn_browse)
        self.btn_clear: QPushButton | None = None
        if clearable:
            self.btn_clear = make_button("", "x", "ghost", "Limpar seleção")
            row.addWidget(self.btn_clear)
            self.btn_clear.clicked.connect(lambda: self.set_path("", emit=True))

        self.btn_browse.clicked.connect(self._browse)
        self.edit.editingFinished.connect(lambda: self.pathChanged.emit(self.path()))
        self.edit.textChanged.connect(self._refresh_state)

    # -- API
    def path(self) -> str:
        return self.edit.text().strip()

    def set_path(self, value: str, emit: bool = False) -> None:
        self.edit.setText(QDir.toNativeSeparators(value) if value else "")
        if emit:
            self.pathChanged.emit(self.path())

    # -- internos
    def _exists(self, text: str) -> bool:
        try:
            p = Path(text)
            return p.is_dir() if self._mode == "dir" else p.is_file()
        except OSError:
            return False

    def _refresh_state(self) -> None:
        text = self.path()
        set_prop(self.edit, "invalid", bool(text) and not self._exists(text))
        if self.btn_clear is not None:
            self.btn_clear.setEnabled(bool(text))

    def _start_dir(self) -> str:
        text = self.path()
        if text:
            p = Path(text)
            try:
                if p.is_dir():
                    return str(p)
                if p.parent.is_dir():
                    return str(p.parent)
            except OSError:
                pass
        remembered = self._settings.last_dir(self._key)
        if remembered and Path(remembered).is_dir():
            return remembered
        return str(Path.home())

    def _browse(self) -> None:
        start = self._start_dir()
        if self._mode == "dir":
            chosen = QFileDialog.getExistingDirectory(self, self._title, start)
        else:
            chosen, _ = QFileDialog.getOpenFileName(self, self._title, start, self._filter)
        if not chosen:
            return
        folder = chosen if self._mode == "dir" else str(Path(chosen).parent)
        self._settings.remember_dir(self._key, folder)
        self.set_path(chosen, emit=True)


# ------------------------------------------------------------------- Tabelas
class DataTable(QTableView):
    """QTableView configurada para listas, com texto de "lista vazia"."""

    def __init__(self, empty_text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._empty_text = empty_text
        self.setAlternatingRowColors(True)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setShowGrid(False)
        self.setWordWrap(False)
        self.verticalHeader().hide()
        self.verticalHeader().setDefaultSectionSize(32)
        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.horizontalHeader().setHighlightSections(False)
        self.setMinimumHeight(130)

    def paintEvent(self, event) -> None:  # noqa: N802 - API do Qt
        super().paintEvent(event)
        model = self.model()
        if self._empty_text and model is not None and model.rowCount() == 0:
            painter = QPainter(self.viewport())
            painter.setPen(QColor("#94A3B8"))
            painter.drawText(
                self.viewport().rect().adjusted(0, 28, 0, 0),
                Qt.AlignmentFlag.AlignHCenter.value | Qt.AlignmentFlag.AlignTop.value | Qt.TextFlag.TextWordWrap.value,
                self._empty_text,
            )
            painter.end()


class ManagedTable(QWidget):
    """Tabela com Editar / Remover / Limpar, confirmações e atalhos (duplo clique, Delete)."""

    def __init__(
        self,
        model: ItemTableModel,
        nouns: tuple[str, str],
        editor: Callable[[QWidget, object], object | None] | None = None,
        empty_text: str = "Nenhum item adicionado.",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.model = model
        self._nouns = nouns
        self._editor = editor

        self.table = DataTable(empty_text)
        self.table.setModel(model)

        self.btn_edit = make_button("Editar", "edit", tooltip="Editar o item selecionado")
        self.btn_remove = make_button("Remover", "trash", "danger", "Remover os itens selecionados (Delete)")
        self.btn_clear = make_button("Limpar tudo", None, "ghost", "Remover todos os itens")
        self.count = QLabel()
        self.count.setObjectName("muted")

        bar = QHBoxLayout()
        bar.setSpacing(8)
        if editor is not None:
            bar.addWidget(self.btn_edit)
        bar.addWidget(self.btn_remove)
        bar.addWidget(self.btn_clear)
        bar.addStretch(1)
        bar.addWidget(self.count)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(self.table, 1)
        layout.addLayout(bar)

        self.btn_edit.clicked.connect(self.edit_selected)
        self.btn_remove.clicked.connect(self.remove_selected)
        self.btn_clear.clicked.connect(self.clear_all)
        self.table.doubleClicked.connect(lambda _index: self.edit_selected())
        self.table.selectionModel().selectionChanged.connect(lambda *_: self._refresh())
        model.changed.connect(self._refresh)
        delete = QShortcut(QKeySequence(Qt.Key.Key_Delete), self.table)
        delete.setContext(Qt.ShortcutContext.WidgetShortcut)
        delete.activated.connect(self.remove_selected)
        self._refresh()

    def _rows(self) -> list[int]:
        return sorted({i.row() for i in self.table.selectionModel().selectedRows()})

    def _refresh(self) -> None:
        selected = len(self._rows())
        self.btn_edit.setEnabled(selected == 1)
        self.btn_remove.setEnabled(selected >= 1)
        self.btn_clear.setEnabled(len(self.model) > 0)
        self.count.setText(plural(len(self.model), *self._nouns))

    def edit_selected(self) -> None:
        rows = self._rows()
        if len(rows) != 1 or self._editor is None:
            return
        row = rows[0]
        current = self.model.item_at(row)
        new = self._editor(self, current)
        if new is None or new == current:
            return
        if not self.model.replace(row, new):
            show_warning(self, "Registro duplicado", "Já existe um item igual a este na lista.")

    def remove_selected(self) -> None:
        rows = self._rows()
        if not rows:
            return
        noun = self._nouns[0] if len(rows) == 1 else self._nouns[1]
        if confirm(self, "Remover", f"Deseja remover {len(rows)} {noun} da lista?",
                   "Remover", danger=True):
            self.model.remove_rows(rows)

    def clear_all(self) -> None:
        if len(self.model) and confirm(
                self, "Limpar lista",
                f"Deseja remover todos os {len(self.model)} {self._nouns[1]} da lista?",
                "Limpar tudo", danger=True):
            self.model.clear()


# ------------------------------------------------------------------------ Log
class LogPanel(QWidget):
    """Área de log em tempo real, colorida por tipo de mensagem."""

    _COLORS = {"out": "#E2E8F0", "err": "#FCA5A5", "info": "#93C5FD", "ok": "#86EFAC"}
    _TAGS = {"out": "", "err": "[stderr] ", "info": "» ", "ok": "✔ "}

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.view = QPlainTextEdit()
        self.view.setObjectName("log")
        self.view.setReadOnly(True)
        self.view.setMaximumBlockCount(10000)
        self.view.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.view.setPlaceholderText("O andamento da automação aparecerá aqui em tempo real.")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.view)

    def append(self, kind: str, text: str) -> None:
        stamp = datetime.now().strftime("%H:%M:%S")
        color = self._COLORS.get(kind, self._COLORS["out"])
        body = escape(self._TAGS.get(kind, "") + text)
        self.view.appendHtml(
            f'<span style="color:#64748B">[{stamp}]</span> '
            f'<span style="color:{color}; white-space:pre-wrap">{body}</span>'
        )

    def clear(self) -> None:
        self.view.clear()
