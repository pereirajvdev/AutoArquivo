"""Diálogos de confirmação, mensagens e edição de registros."""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import QRegularExpression
from PySide6.QtGui import QRegularExpressionValidator
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from ..models import Nome, Periodo, Registro
from ..validators import (
    ValidationError,
    normalize_matricula,
    parse_name,
    parse_period,
)


# ------------------------------------------------------------------ mensagens
def confirm(parent: QWidget | None, title: str, text: str,
            confirm_text: str = "Confirmar", danger: bool = False) -> bool:
    """Pergunta de confirmação; o botão padrão é sempre 'Voltar' (mais seguro)."""
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Warning if danger else QMessageBox.Icon.Question)
    box.setWindowTitle(title)
    box.setText(text)
    yes = box.addButton(confirm_text, QMessageBox.ButtonRole.AcceptRole)
    no = box.addButton("Voltar", QMessageBox.ButtonRole.RejectRole)
    box.setDefaultButton(no)
    box.exec()
    return box.clickedButton() is yes


def show_error(parent: QWidget | None, title: str, text: str, details: str = "") -> None:
    box = QMessageBox(QMessageBox.Icon.Critical, title, text, QMessageBox.StandardButton.Ok, parent)
    if details:
        box.setDetailedText(details)
    box.exec()


def show_warning(parent: QWidget | None, title: str, text: str, details: str = "") -> None:
    box = QMessageBox(QMessageBox.Icon.Warning, title, text, QMessageBox.StandardButton.Ok, parent)
    if details:
        box.setDetailedText(details)
    box.exec()


def show_info(parent: QWidget | None, title: str, text: str) -> None:
    QMessageBox(QMessageBox.Icon.Information, title, text, QMessageBox.StandardButton.Ok, parent).exec()


# ------------------------------------------------------------------ edição
class _BaseEditDialog(QDialog):
    """Diálogo de edição com validação inline (o erro aparece sem fechar a janela)."""

    def __init__(self, title: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setMinimumWidth(360)
        self.value = None

        self.form = QFormLayout()
        self.form.setSpacing(10)
        self.error = QLabel()
        self.error.setObjectName("feedback")
        self.error.setProperty("kind", "error")
        self.error.setWordWrap(True)
        self.error.hide()

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Salvar")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("Cancelar")
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(12)
        layout.addLayout(self.form)
        layout.addWidget(self.error)
        layout.addWidget(buttons)

    def collect(self):  # pragma: no cover - implementado nas subclasses
        raise NotImplementedError

    def _on_accept(self) -> None:
        try:
            self.value = self.collect()
        except ValidationError as exc:
            self.error.setText(str(exc))
            self.error.show()
            return
        self.accept()


def _line(text: str = "", digits_only: int = 0) -> QLineEdit:
    edit = QLineEdit(text)
    if digits_only:
        edit.setMaxLength(digits_only)
        edit.setValidator(QRegularExpressionValidator(QRegularExpression(rf"\d{{0,{digits_only}}}")))
    return edit


class _MatriculaDialog(_BaseEditDialog):
    def __init__(self, parent, current: str) -> None:
        super().__init__("Editar matrícula", parent)
        self.edit = _line(current)
        self.form.addRow("Matrícula", self.edit)
        self.edit.setFocus()

    def collect(self) -> str:
        return normalize_matricula(self.edit.text())


class _PeriodoDialog(_BaseEditDialog):
    """Edita (matrícula opcional +) ano inicial e final."""

    def __init__(self, parent, title: str, matricula: str | None, inicio: int, fim: int) -> None:
        super().__init__(title, parent)
        self.ed_mat = _line(matricula) if matricula is not None else None
        self.ed_ini = _line(str(inicio), digits_only=4)
        self.ed_fim = _line(str(fim), digits_only=4)
        if self.ed_mat is not None:
            self.form.addRow("Matrícula", self.ed_mat)
        self.form.addRow("Ano inicial", self.ed_ini)
        self.form.addRow("Ano final", self.ed_fim)

    def collect(self):
        inicio, fim = parse_period(self.ed_ini.text(), self.ed_fim.text())
        if self.ed_mat is not None:
            return Registro(normalize_matricula(self.ed_mat.text()), inicio, fim)
        return Periodo(inicio, fim)


class _NomeDialog(_BaseEditDialog):
    def __init__(self, parent, current: str) -> None:
        super().__init__("Editar nome", parent)
        self.edit = _line(current)
        self.edit.setMinimumWidth(320)
        self.form.addRow("Nome", self.edit)
        self.edit.setFocus()

    def collect(self) -> str:
        return parse_name(self.edit.text())


# Editores usados pelas tabelas: recebem (parent, item) e devolvem o novo item ou None.
def edit_matricula(parent: QWidget, current: str) -> str | None:
    dialog = _MatriculaDialog(parent, current)
    return dialog.value if dialog.exec() == QDialog.DialogCode.Accepted else None


def edit_periodo(parent: QWidget, current: Periodo) -> Periodo | None:
    dialog = _PeriodoDialog(parent, "Editar período", None, current.inicio, current.fim)
    return dialog.value if dialog.exec() == QDialog.DialogCode.Accepted else None


def edit_registro(parent: QWidget, current: Registro) -> Registro | None:
    dialog = _PeriodoDialog(parent, "Editar registro", current.matricula, current.inicio, current.fim)
    return dialog.value if dialog.exec() == QDialog.DialogCode.Accepted else None


def edit_nome(parent: QWidget, current: Nome) -> Nome | None:
    dialog = _NomeDialog(parent, current.texto)
    if dialog.exec() != QDialog.DialogCode.Accepted:
        return None
    return Nome(dialog.value, current.origem)


Editor = Callable[[QWidget, object], object]
