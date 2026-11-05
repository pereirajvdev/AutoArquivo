"""Convenção de argumentos enviados aos scripts externos.

Ficha e Faltas::

    python main.py --servidores "<dir>" --registros "<json>" [--pasta "<dir>"]

Férias::

    python main.py --nomes "<json>" --saida "<dir>"

Os argumentos são passados como *lista* (nunca como uma string única de shell),
portanto aspas, acentos e espaços do JSON chegam intactos em ``sys.argv``.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Iterable

from .models import Registro

ARG_SERVIDORES = "--servidores"
ARG_REGISTROS = "--registros"
ARG_PASTA = "--pasta"
ARG_NOMES = "--nomes"
ARG_SAIDA = "--saida"


def _json(data: object) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def registros_to_json(registros: Iterable[Registro]) -> str:
    """``[{"matricula":"1234","inicio":2017,"fim":2019}, ...]``"""
    return _json([r.as_dict() for r in registros])


def nomes_to_json(nomes: Iterable[str]) -> str:
    """``["João Silva","Maria Souza"]``"""
    return _json(list(nomes))


def build_registros_args(
    servidores: Path, registros: Iterable[Registro], pasta: Path | None = None
) -> list[str]:
    """Argumentos de Ficha e Faltas. ``--pasta`` é omitido quando não informado."""
    args = [ARG_SERVIDORES, str(servidores), ARG_REGISTROS, registros_to_json(registros)]
    if pasta is not None:
        args += [ARG_PASTA, str(pasta)]
    return args


def build_ferias_args(nomes: Iterable[str], saida: Path) -> list[str]:
    return [ARG_NOMES, nomes_to_json(nomes), ARG_SAIDA, str(saida)]


def format_command(python: str, script: Path, args: list[str], max_arg: int = 400) -> str:
    """Linha de comando legível para o log (argumentos muito longos são abreviados)."""
    short = [
        a if len(a) <= max_arg else f"{a[:max_arg]}…(+{len(a) - max_arg} caracteres)"
        for a in args
    ]
    return subprocess.list2cmdline([python, str(script), *short])
