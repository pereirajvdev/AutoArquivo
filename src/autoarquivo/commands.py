"""Convenção de argumentos enviados aos scripts externos.

Ficha e Faltas::

    python main.py --servidores "<dir>" --registros "<json>" [--pasta "<dir>"]

Somente Ficha aceita, além disso, ``--retorno "<arquivo.json>"``: o AutoFicha grava
ali as pastas que receberam PDFs (ver ``ficha_result.py``).

Férias::

    python main.py --nomes "<json>" --saida "<dir>"

FichaPDFToExcel (executado depois do AutoFicha)::

    python main.py "<pasta dos PDFs>"

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
ARG_RETORNO = "--retorno"
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
    servidores: Path,
    registros: Iterable[Registro],
    pasta: Path | None = None,
    retorno: Path | None = None,
) -> list[str]:
    """Argumentos de Ficha e Faltas. ``--pasta`` e ``--retorno`` são omitidos quando não informados."""
    args = [ARG_SERVIDORES, str(servidores), ARG_REGISTROS, registros_to_json(registros)]
    if pasta is not None:
        args += [ARG_PASTA, str(pasta)]
    if retorno is not None:
        args += [ARG_RETORNO, str(retorno)]
    return args


def build_ferias_args(nomes: Iterable[str], saida: Path) -> list[str]:
    return [ARG_NOMES, nomes_to_json(nomes), ARG_SAIDA, str(saida)]


def resolve_pdf_dir(pasta: str | Path | None, planilha: str | Path | None) -> Path | None:
    """Pasta dos PDFs gerados pelo AutoFicha (regra única, usada por todo o painel).

    1. pasta informada explicitamente (campo "Pasta específica") tem prioridade;
    2. senão, a pasta onde está a planilha de entrada;
    3. senão, ``None`` — nenhuma pasta é inventada.

    Não verifica se o caminho existe; use ``validate_directory`` antes de executar.
    """
    explicit = str(pasta or "").strip()
    if explicit:
        return Path(explicit)
    sheet = str(planilha or "").strip()
    if sheet:
        return Path(sheet).parent
    return None


def build_ficha_excel_args(pasta_pdfs: Path) -> list[str]:
    """Argumento posicional único: a pasta com os PDFs das fichas."""
    return [str(pasta_pdfs)]


def format_command(python: str, script: Path, args: list[str], max_arg: int = 400) -> str:
    """Linha de comando legível para o log (argumentos muito longos são abreviados)."""
    short = [
        a if len(a) <= max_arg else f"{a[:max_arg]}…(+{len(a) - max_arg} caracteres)"
        for a in args
    ]
    return subprocess.list2cmdline([python, str(script), *short])
