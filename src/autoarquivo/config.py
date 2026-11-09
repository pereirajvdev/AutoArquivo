"""Configurações centralizadas: módulos, caminhos dos scripts e persistência.

Nenhum caminho de usuário é fixado no código. Os scripts externos são
localizados por convenção como *pastas irmãs* do projeto::

    <pasta pai>/AutoArquivo/src/main.py      (este painel)
    <pasta pai>/AutoFicha/src/main.py
    <pasta pai>/AutoFaltas/src/main.py
    <pasta pai>/AutoFérias/src/main.py
    <pasta pai>/FichaPDFToExcel/src/main.py  (etapa posterior ao AutoFicha)

Qualquer caminho pode ser sobrescrito em "Configurações" e fica salvo em
``settings.json`` (``%APPDATA%\\AutoArquivo`` no Windows).
"""

from __future__ import annotations

import json
import logging
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

APP_NAME = "AutoArquivo"
APP_VERSION = "1.0.0"

PROJECT_ROOT = Path(__file__).resolve().parents[2]
WORKSPACE_ROOT = PROJECT_ROOT.parent
SCRIPT_RELATIVE_PATH = Path("src") / "main.py"


@dataclass(frozen=True)
class ModuleSpec:
    """Descrição declarativa de um módulo do painel."""

    key: str
    title: str
    subtitle: str
    icon: str
    action_text: str = "Executar"
    script_folder: str | None = None  # pasta irmã que contém src/main.py
    export_excel: bool = False  # exibe "Gerar Excel das Fichas" após o sucesso do módulo


# Para incluir um novo módulo: adicione um ModuleSpec aqui e registre a
# página correspondente em ``ui/main_window.py`` (PAGE_FACTORIES).
MODULES: tuple[ModuleSpec, ...] = (
    ModuleSpec("ficha", "Ficha", "Geração de fichas financeiras", "file",
               "Gerar fichas", "AutoFicha", export_excel=True),
    ModuleSpec("faltas", "Faltas", "Levantamento de faltas por servidor", "calendar-x",
               "Processar faltas", "AutoFaltas"),
    ModuleSpec("licencas", "Licenças", "Automação de licenças", "clipboard",
               "Executar", None),
    ModuleSpec("ferias", "Férias", "Geração dos dados de férias", "sun",
               "Executar férias", "AutoFérias"),
)
MODULES_BY_KEY = {m.key: m for m in MODULES}

# Scripts auxiliares: não são módulos de navegação, mas também são executados
# pelo painel. ``chave -> (pasta irmã, rótulo em Configurações)``.
FICHA_EXCEL_KEY = "ficha_excel"
EXTRA_SCRIPTS: dict[str, tuple[str, str]] = {
    FICHA_EXCEL_KEY: ("FichaPDFToExcel", "Ficha → Excel"),
}


def _sibling_script(folder: str) -> Path:
    return WORKSPACE_ROOT / folder / SCRIPT_RELATIVE_PATH


def default_script_path(spec: ModuleSpec) -> Path | None:
    """Caminho padrão do script de um módulo (pasta irmã do projeto)."""
    if not spec.script_folder:
        return None
    return _sibling_script(spec.script_folder)


def default_extra_script_path(key: str) -> Path | None:
    """Caminho padrão de um script auxiliar (ver ``EXTRA_SCRIPTS``)."""
    extra = EXTRA_SCRIPTS.get(key)
    return _sibling_script(extra[0]) if extra else None


def settings_dir() -> Path:
    """Pasta onde as configurações e o log da aplicação são gravados."""
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return base / APP_NAME


class Settings:
    """Configurações persistentes (JSON). Tolerante a arquivo ausente/corrompido."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or settings_dir() / "settings.json"
        self.servidores_dir: str = ""
        self.python_interpreter: str = ""  # vazio = automático (ver launch.py)
        self.scripts: dict[str, str] = {}  # sobrescritas por módulo
        self.last_dirs: dict[str, str] = {}
        self.preferences: dict[str, Any] = {}
        self.load()

    # ------------------------------------------------------------ persistência
    def load(self) -> None:
        if not self.path.is_file():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("formato inesperado")
        except (OSError, ValueError) as exc:
            log.warning("Configurações ilegíveis (%s); usando padrões.", exc)
            try:
                self.path.replace(self.path.with_suffix(".json.bak"))
            except OSError:
                pass
            return
        self.servidores_dir = _as_str(data.get("servidores_dir"))
        self.python_interpreter = _as_str(data.get("python_interpreter"))
        self.scripts = _as_str_dict(data.get("scripts"))
        self.last_dirs = _as_str_dict(data.get("last_dirs"))
        prefs = data.get("preferences")
        self.preferences = prefs if isinstance(prefs, dict) else {}

    def save(self) -> None:
        payload = {
            "version": 1,
            "servidores_dir": self.servidores_dir,
            "python_interpreter": self.python_interpreter,
            "scripts": self.scripts,
            "last_dirs": self.last_dirs,
            "preferences": self.preferences,
        }
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(self.path)
        except OSError as exc:  # nunca derruba a aplicação
            log.error("Não foi possível salvar as configurações: %s", exc)

    # --------------------------------------------------------------- consultas
    def script_path(self, key: str) -> Path | None:
        """Script de um módulo/auxiliar: sobrescrita do usuário ou padrão por convenção."""
        override = self.scripts.get(key, "").strip()
        if override:
            return Path(override)
        spec = MODULES_BY_KEY.get(key)
        if spec:
            return default_script_path(spec)
        return default_extra_script_path(key)

    def last_dir(self, key: str) -> str:
        return self.last_dirs.get(key, "")

    def remember_dir(self, key: str, directory: str | Path) -> None:
        self.last_dirs[key] = str(directory)
        self.save()


def _as_str(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _as_str_dict(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {str(k): v for k, v in value.items() if isinstance(v, str)}
