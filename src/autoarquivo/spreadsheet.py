"""Leitura e interpretação de planilhas Excel (openpyxl), sem dependência de Qt.

O reconhecimento de colunas é tolerante: ignora acentos, caixa, espaços e
pontuação ("Matrícula", "MATRICULA", "Nº Matrícula", "Ano Inicial", "ano_fim"...).
Se mais de uma coluna puder representar o mesmo campo, a leitura é recusada
em vez de "chutar" - a identificação precisa ser segura.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable, Mapping
from zipfile import BadZipFile

from openpyxl import load_workbook
from openpyxl.utils.exceptions import InvalidFileException

from .models import Registro
from .validators import (
    ValidationError,
    name_key,
    normalize_matricula,
    normalize_name,
    parse_period,
    strip_accents,
)

SUPPORTED_SUFFIXES = {".xlsx", ".xlsm", ".xltx", ".xltm"}
HEADER_SEARCH_ROWS = 30
PREVIEW_MAX_ROWS = 2000


class SpreadsheetError(Exception):
    """Falha ao abrir ou interpretar uma planilha (mensagem pronta para o usuário)."""


@dataclass
class RegistrosImport:
    registros: list[Registro]
    avisos: list[str] = field(default_factory=list)
    duplicados: int = 0
    planilha: str = ""


@dataclass
class NomesImport:
    nomes: list[str]
    avisos: list[str] = field(default_factory=list)
    duplicados: int = 0
    planilha: str = ""


@dataclass
class SheetPreview:
    headers: list[str]
    rows: list[list[str]]
    sheet: str
    truncated: bool = False


# ------------------------------------------------------------------ abertura
def _open_sheets(path_like: str | Path) -> list[tuple[str, list[list[Any]]]]:
    """Lê todas as abas visíveis: ``[(nome_da_aba, linhas), ...]``."""
    path = Path(str(path_like).strip())
    try:
        exists = path.exists()
        is_file = path.is_file()
    except OSError as exc:
        raise SpreadsheetError(f"Planilha inacessível:\n{path}\n{exc}") from exc
    if not exists:
        raise SpreadsheetError(f"Planilha não encontrada:\n{path}")
    if not is_file:
        raise SpreadsheetError(f"O caminho informado não é um arquivo:\n{path}")
    suffix = path.suffix.lower()
    if suffix == ".xls":
        raise SpreadsheetError(
            "O formato .xls (Excel antigo) não é suportado.\n"
            "Abra o arquivo no Excel e salve como .xlsx."
        )
    if suffix not in SUPPORTED_SUFFIXES:
        raise SpreadsheetError(f"Formato não suportado ('{path.suffix}'). Selecione um arquivo .xlsx.")

    try:
        workbook = load_workbook(path, read_only=True, data_only=True)
    except PermissionError as exc:
        raise SpreadsheetError(
            f"Sem permissão para abrir a planilha:\n{path}\nFeche-a no Excel e tente novamente."
        ) from exc
    except (InvalidFileException, BadZipFile, KeyError) as exc:
        raise SpreadsheetError(f"A planilha está corrompida ou não é um arquivo Excel válido:\n{path}") from exc
    except OSError as exc:
        raise SpreadsheetError(f"Não foi possível ler a planilha:\n{path}\n{exc}") from exc
    except Exception as exc:  # noqa: BLE001 - openpyxl pode lançar vários tipos
        raise SpreadsheetError(f"Erro inesperado ao abrir a planilha:\n{path}\n{exc}") from exc

    sheets: list[tuple[str, list[list[Any]]]] = []
    try:
        for ws in workbook.worksheets:
            if getattr(ws, "sheet_state", "visible") != "visible":
                continue
            reset = getattr(ws, "reset_dimensions", None)
            if callable(reset):
                reset()  # corrige arquivos com dimensão declarada incorretamente
            sheets.append((ws.title, [list(r) for r in ws.iter_rows(values_only=True)]))
    except Exception as exc:  # noqa: BLE001
        raise SpreadsheetError(f"Erro ao ler o conteúdo da planilha:\n{path}\n{exc}") from exc
    finally:
        workbook.close()
    return sheets


# -------------------------------------------------------------- reconhecimento
def _norm_header(value: Any) -> str:
    if value is None:
        return ""
    return re.sub(r"[^a-z0-9]", "", strip_accents(str(value)).casefold())


def _blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _cell(row: list[Any], col: int | None) -> Any:
    return row[col] if col is not None and col < len(row) else None


Matcher = Callable[[str], bool]


def _is_matricula(h: str) -> bool:
    return bool(re.fullmatch(r"(n|no|nr|num|numero)?(matr|mat)", h)) or "matricula" in h


_IS_INICIO = re.compile(r"(ano)?(ini|inicio|inicial|de|desde)(ano)?")
_IS_FIM = re.compile(r"(ano)?(fim|final|fin|ate|termino)(ano)?")

REGISTRO_MATCHERS: Mapping[str, Matcher] = {
    "matricula": _is_matricula,
    "inicio": lambda h: bool(_IS_INICIO.fullmatch(h)),
    "fim": lambda h: bool(_IS_FIM.fullmatch(h)),
    "ano": lambda h: bool(re.fullmatch(r"anos?", h)),
}


def _find_header(
    rows: list[list[Any]],
    matchers: Mapping[str, Matcher],
    is_valid: Callable[[Mapping[str, list[int]]], bool],
) -> tuple[int, dict[str, list[int]]] | None:
    """Localiza a linha de cabeçalho com mais campos reconhecidos."""
    best: tuple[int, dict[str, list[int]]] | None = None
    for idx, row in enumerate(rows[:HEADER_SEARCH_ROWS]):
        found: dict[str, list[int]] = {}
        for col, value in enumerate(row):
            h = _norm_header(value)
            if not h:
                continue
            for name, matcher in matchers.items():
                if matcher(h):
                    found.setdefault(name, []).append(col)
                    break
        if found and is_valid(found) and (best is None or len(found) > len(best[1])):
            best = (idx, found)
    return best


def _single_column(found: Mapping[str, list[int]], name: str, rows: list[list[Any]], hdr: int) -> int:
    cols = found[name]
    if len(cols) > 1:
        titles = ", ".join(f"'{rows[hdr][c]}'" for c in cols)
        raise SpreadsheetError(
            f"Há mais de uma coluna que pode representar '{name}' ({titles}). "
            "Deixe apenas uma na planilha ou renomeie as demais."
        )
    return cols[0]


# ------------------------------------------------------------------ registros
def read_registros(path: str | Path) -> RegistrosImport:
    """Lê matrícula / ano inicial / ano final.

    Aceita também uma única coluna "Ano" (equivale a início = fim) e ano final
    em branco (ano único).
    """
    sheets = _open_sheets(path)

    def valid(found: Mapping[str, list[int]]) -> bool:
        return "matricula" in found and ("inicio" in found or "ano" in found)

    for title, rows in sheets:
        located = _find_header(rows, REGISTRO_MATCHERS, valid)
        if located is None:
            continue
        hdr, found = located
        col_mat = _single_column(found, "matricula", rows, hdr)
        if "inicio" in found:
            col_ini = _single_column(found, "inicio", rows, hdr)
            col_fim = _single_column(found, "fim", rows, hdr) if "fim" in found else None
        else:
            col_ini = _single_column(found, "ano", rows, hdr)
            col_fim = None

        registros: list[Registro] = []
        avisos: list[str] = []
        vistos: set[tuple[str, int, int]] = set()
        duplicados = 0
        for offset, row in enumerate(rows[hdr + 1:], start=hdr + 2):
            mat_raw, ini_raw, fim_raw = _cell(row, col_mat), _cell(row, col_ini), _cell(row, col_fim)
            if _blank(mat_raw) and _blank(ini_raw) and _blank(fim_raw):
                continue
            try:
                matricula = normalize_matricula(mat_raw)
                inicio, fim = parse_period(ini_raw, fim_raw)
            except ValidationError as exc:
                avisos.append(f"Linha {offset}: {str(exc).splitlines()[0]}")
                continue
            reg = Registro(matricula, inicio, fim)
            if reg.chave in vistos:
                duplicados += 1
                continue
            vistos.add(reg.chave)
            registros.append(reg)

        if not registros:
            detalhe = ("\n" + "\n".join(avisos[:5])) if avisos else ""
            raise SpreadsheetError(
                f"Nenhum registro válido encontrado na aba '{title}'.{detalhe}"
            )
        return RegistrosImport(registros, avisos, duplicados, title)

    raise SpreadsheetError(
        "Não foi possível identificar as colunas da planilha.\n"
        "Esperado: 'Matrícula', 'Ano inicial' e 'Ano final' "
        "(ou uma coluna 'Ano') nas primeiras linhas da planilha."
    )


# ---------------------------------------------------------------------- nomes
_NAME_EXACT = {"nome", "nomes"}
_NAME_COMMON = {
    "nomecompleto", "nomedoservidor", "nomeservidor", "nomefuncionario", "nomedofuncionario",
    "nomecolaborador", "servidor", "servidores", "funcionario", "funcionarios",
    "colaborador", "colaboradores",
}


def _name_rank(h: str) -> int | None:
    if h in _NAME_EXACT:
        return 0
    if h in _NAME_COMMON:
        return 1
    if h.startswith("nome") and not re.search(r"(mae|pai|social|conjuge|dependente)", h):
        return 2
    return None


def _find_name_column(rows: list[list[Any]]) -> tuple[int, int] | None:
    """Retorna (linha_do_cabeçalho, coluna) da coluna de nomes, ou None."""
    best: tuple[int, int, int] | None = None  # (rank, linha, coluna)
    for idx, row in enumerate(rows[:HEADER_SEARCH_ROWS]):
        ranked = [(r, c) for c, v in enumerate(row) if (r := _name_rank(_norm_header(v))) is not None]
        if not ranked:
            continue
        top = min(r for r, _ in ranked)
        cols = [c for r, c in ranked if r == top]
        if len(cols) > 1:
            titles = ", ".join(f"'{row[c]}'" for c in cols)
            raise SpreadsheetError(
                f"Há mais de uma coluna que pode conter nomes ({titles}). "
                "Deixe apenas uma na planilha ou renomeie as demais."
            )
        if best is None or top < best[0]:
            best = (top, idx, cols[0])
    return (best[1], best[2]) if best else None


def read_nomes(path: str | Path) -> NomesImport:
    """Lê a coluna de nomes (cabeçalho "Nome", "Servidor", "Nome completo"...)."""
    sheets = _open_sheets(path)
    for title, rows in sheets:
        located = _find_name_column(rows)
        if located is None:
            continue
        hdr, col = located
        nomes: list[str] = []
        vistos: set[str] = set()
        duplicados = 0
        for row in rows[hdr + 1:]:
            raw = _cell(row, col)
            if _blank(raw):
                continue
            nome = normalize_name(raw)
            if not any(c.isalpha() for c in nome):
                continue
            key = name_key(nome)
            if key in vistos:
                duplicados += 1
                continue
            vistos.add(key)
            nomes.append(nome)
        if not nomes:
            raise SpreadsheetError(f"A coluna de nomes da aba '{title}' está vazia.")
        return NomesImport(nomes, [], duplicados, title)
    raise SpreadsheetError(
        "Não foi possível identificar a coluna de nomes.\n"
        "Esperado um cabeçalho como 'Nome', 'Nome completo' ou 'Servidor'."
    )


# -------------------------------------------------------------------- prévia
def _cell_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.strftime("%d/%m/%Y") if value.time() == datetime.min.time() else value.strftime("%d/%m/%Y %H:%M")
    if isinstance(value, date):
        return value.strftime("%d/%m/%Y")
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def read_preview(path: str | Path) -> SheetPreview:
    """Conteúdo bruto da primeira aba com dados (primeira linha preenchida = cabeçalho)."""
    for title, rows in _open_sheets(path):
        start = next((i for i, r in enumerate(rows) if any(not _blank(v) for v in r)), None)
        if start is None:
            continue
        width = max(len(r) for r in rows[start:])
        header_row = rows[start] + [None] * (width - len(rows[start]))
        headers = [_cell_text(v) or f"Coluna {i + 1}" for i, v in enumerate(header_row)]
        body = [
            [_cell_text(_cell(r, c)) for c in range(width)]
            for r in rows[start + 1:]
            if any(not _blank(v) for v in r)
        ]
        return SheetPreview(headers, body[:PREVIEW_MAX_ROWS], title, len(body) > PREVIEW_MAX_ROWS)
    raise SpreadsheetError("A planilha está vazia.")
