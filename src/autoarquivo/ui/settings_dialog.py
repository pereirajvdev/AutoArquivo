"""Diálogo de configurações: interpretador Python e caminhos dos scripts."""

from __future__ import annotations

from PySide6.QtWidgets import QDialog, QDialogButtonBox, QFormLayout, QLabel, QVBoxLayout, QWidget

from ..config import (
    EXTRA_SCRIPTS,
    MODULES,
    Settings,
    default_extra_script_path,
    default_script_path,
)
from .widgets import PathSelector


class SettingsDialog(QDialog):
    def __init__(self, settings: Settings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._settings = settings
        self.setWindowTitle("Configurações")
        self.setModal(True)
        self.setMinimumWidth(760)

        intro = QLabel(
            "Deixe um campo em branco para usar o padrão. Interpretador automático: "
            "usa a .venv do projeto do script, se existir; senão, o Python do PATH."
        )
        intro.setObjectName("muted")
        intro.setWordWrap(True)

        form = QFormLayout()
        form.setSpacing(12)

        self.python = PathSelector(
            settings, "python", "file", "Automático", "Selecionar interpretador Python",
            "Executáveis (*.exe);;Todos os arquivos (*)", clearable=True, button_text="Procurar")
        self.python.set_path(settings.python_interpreter)
        form.addRow("Interpretador Python", self.python)

        # (chave, rótulo, caminho padrão) de cada script configurável
        entries: list[tuple[str, str, object]] = [
            (spec.key, spec.title, default_script_path(spec))
            for spec in MODULES if spec.script_folder
        ]
        entries += [
            (key, label, default_extra_script_path(key))
            for key, (_folder, label) in EXTRA_SCRIPTS.items()
        ]

        self.scripts: dict[str, PathSelector] = {}
        for key, title, default in entries:
            selector = PathSelector(
                settings, f"script_{key}", "file", str(default) if default else "",
                f"Selecionar script do módulo {title}",
                "Scripts Python (*.py);;Todos os arquivos (*)", clearable=True, button_text="Procurar")
            selector.set_path(settings.scripts.get(key, ""))
            self.scripts[key] = selector
            form.addRow(f"Script — {title}", selector)

        buttons = QDialogButtonBox()
        save = buttons.addButton("Salvar", QDialogButtonBox.ButtonRole.AcceptRole)
        save.setObjectName("primary")
        buttons.addButton("Cancelar", QDialogButtonBox.ButtonRole.RejectRole)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 16)
        layout.setSpacing(16)
        layout.addWidget(intro)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def _save(self) -> None:
        self._settings.python_interpreter = self.python.path()
        for key, selector in self.scripts.items():
            value = selector.path()
            if value:
                self._settings.scripts[key] = value
            else:
                self._settings.scripts.pop(key, None)
        self._settings.save()
        self.accept()
