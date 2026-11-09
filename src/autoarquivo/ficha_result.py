"""Retorno estruturado do AutoFicha (arquivo JSON), sem dependência de Qt.

O AutoFicha grava, em ``--retorno``, quais pastas de servidores receberam ao
menos um PDF. O painel usa *somente* essa lista (nunca varre diretórios)::

    {"sucesso": true,
     "pastas_processadas": ["C:/Servidores/Servidor A", "C:/Servidores/Servidor B"],
     "total_pastas": 2, "total_fichas_salvas": 5, "falhas": [], "erro": ""}
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


class FichaResultError(Exception):
    """Retorno ausente, ilegível ou inconsistente (mensagem pronta para o log/usuário)."""


@dataclass(frozen=True)
class FichaResult:
    sucesso: bool
    pastas: tuple[Path, ...] = ()
    total_fichas: int = 0
    falhas: tuple[dict, ...] = field(default_factory=tuple)
    erro: str = ""


def new_return_file() -> Path:
    """Cria um arquivo temporário vazio para o retorno (pasta temporária do sistema)."""
    fd, name = tempfile.mkstemp(prefix="autoficha_retorno_", suffix=".json")
    os.close(fd)  # o Windows não deixa o outro processo substituir um arquivo aberto
    return Path(name)


def discard(path: Path | None) -> None:
    """Remove o arquivo (e o ``.tmp`` de gravação atômica). Nunca lança exceção."""
    if path is None:
        return
    for candidate in (path, path.with_name(path.name + ".tmp")):
        try:
            candidate.unlink(missing_ok=True)
        except OSError as exc:
            log.warning("Não foi possível remover o arquivo temporário %s: %s", candidate, exc)


def _as_int(value: Any, default: int = 0) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else default


def read_ficha_result(path: Path) -> FichaResult:
    """Lê e valida o JSON. Qualquer problema vira :class:`FichaResultError`."""
    try:
        text = path.read_text(encoding="utf-8-sig")  # tolera BOM
    except FileNotFoundError as exc:
        raise FichaResultError(f"O AutoFicha não gerou o arquivo de retorno:\n{path}") from exc
    except OSError as exc:
        raise FichaResultError(f"Não foi possível ler o retorno do AutoFicha:\n{path}\n{exc}") from exc

    if not text.strip():
        raise FichaResultError("O retorno do AutoFicha está vazio.")
    try:
        data = json.loads(text)
    except ValueError as exc:
        raise FichaResultError(f"O retorno do AutoFicha não é um JSON válido: {exc}") from exc
    if not isinstance(data, dict):
        raise FichaResultError("O retorno do AutoFicha tem formato inesperado (esperado um objeto JSON).")

    sucesso = data.get("sucesso")
    if not isinstance(sucesso, bool):
        raise FichaResultError("Retorno inválido: o campo 'sucesso' deve ser verdadeiro ou falso.")

    raw = data.get("pastas_processadas")
    if not isinstance(raw, list):
        raise FichaResultError("Retorno inválido: o campo 'pastas_processadas' deve ser uma lista.")

    pastas: list[Path] = []
    vistas: set[str] = set()
    for item in raw:
        if not isinstance(item, str) or not item.strip():
            raise FichaResultError(f"Retorno inválido: caminho de pasta inválido ({item!r}).")
        pasta = Path(item.strip())
        if not pasta.is_absolute():
            # O script roda em outra pasta de trabalho: um caminho relativo seria ambíguo.
            raise FichaResultError(f"Retorno inválido: o caminho não é absoluto ({item!r}).")
        key = os.path.normcase(str(pasta))
        if key in vistas:
            continue
        vistas.add(key)
        pastas.append(pasta)

    falhas = data.get("falhas")
    erro = data.get("erro")
    return FichaResult(
        sucesso=sucesso,
        pastas=tuple(pastas),
        total_fichas=_as_int(data.get("total_fichas_salvas")),
        falhas=tuple(f for f in falhas if isinstance(f, dict)) if isinstance(falhas, list) else (),
        erro=erro if isinstance(erro, str) else "",
    )
