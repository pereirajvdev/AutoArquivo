"""Resolução do interpretador Python e do script de cada módulo."""

from __future__ import annotations

import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

from .config import Settings
from .validators import ValidationError


@dataclass(frozen=True)
class Launch:
    python: str
    script: Path


def _venv_python(script: Path) -> Path:
    """Python do ambiente virtual do próprio projeto do script (``<projeto>/.venv``)."""
    if sys.platform == "win32":
        return script.parent.parent / ".venv" / "Scripts" / "python.exe"
    return script.parent.parent / ".venv" / "bin" / "python"


def resolve_launch(settings: Settings, module_key: str) -> Launch:
    """Define qual interpretador executará qual script.

    Ordem de escolha do interpretador:
      1. o configurado em Configurações (se preenchido);
      2. ``.venv`` do projeto do script (ex.: AutoFicha/.venv);
      3. ``python`` do PATH;
      4. o interpretador que executa este painel.
    """
    script = settings.script_path(module_key)
    if script is None:
        raise ValidationError("Este módulo ainda não possui um script configurado.")
    if not script.is_file():
        raise ValidationError(
            f"Script Python não encontrado:\n{script}\n\n"
            "Ajuste o caminho em Configurações (ícone no menu lateral)."
        )

    configured = settings.python_interpreter.strip()
    if configured:
        if not (Path(configured).is_file() or shutil.which(configured)):
            raise ValidationError(
                f"Interpretador Python não encontrado:\n{configured}\n\n"
                "Corrija em Configurações ou deixe em branco para detecção automática."
            )
        return Launch(configured, script)

    venv = _venv_python(script)
    if venv.is_file():
        return Launch(str(venv), script)
    found = shutil.which("python") or shutil.which("python3")
    return Launch(found or sys.executable, script)
