"""Leitura e interpretação de planilhas Excel (openpyxl), sem dependência de Qt.

Planilha de vínculos (``read_registros``) - formato fixo, primeira aba::

    | A: Matrícula | B: Data inicial | C: Data final |
    | 22057        | 02/10/2017      | 16/06/2018    |

O cabeçalho e as linhas sem matrícula numérica são ignorados; linhas vazias
também. A leitura é em fluxo (somente colunas A a C, linha a linha).

Planilha de nomes (``read_nomes``): o reconhecimento da coluna é tolerante a
acentos, caixa e pontuação; se houver ambiguidade, a leitura é recusada em vez
de "chutar".
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any
from zipfile import BadZipFile

from openpyxl import load_workbook
from openpyxl.utils.exceptions import InvalidFileException

from .models import Registro
from .validators import (
    ValidationError,
    name_key,
    normalize_name,
    parse_date,
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
def _open_workbook(path_like: str | Path):
    """Valida o caminho e abre o arquivo em modo leitura (o chamador deve fechá-lo)."""
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
    return workbook


def _open_sheets(path_like: str | Path) -> list[tuple[str, list[list[Any]]]]:
    """Lê todas as abas visíveis: ``[(nome_da_aba, linhas), ...]``."""
    path = Path(str(path_like).strip())
    workbook = _open_workbook(path)
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


# ------------------------------------------------------------------ registros
def _matricula_int(raw: Any) -> int | None:
    """Matrícula como inteiro (como ``int(...)`` da leitura de referência) ou None."""
    if isinstance(raw, bool):
        return None
    if isinstance(raw, float) and not raw.is_integer():
        return None
    try:
        return int(raw)
    except (TypeError, ValueError, OverflowError):
        return None


def read_registros(path: str | Path) -> RegistrosImport:
    """Lê os vínculos: matrícula (A), data inicial (B) e data final (C).

    Usa a primeira aba. Os scripts externos trabalham com anos, então cada
    vínculo vira ``Registro(matrícula, ano_inicial, ano_final)``.

    * linha vazia: ignorada; sem matrícula numérica (inclui o cabeçalho): ignorada;
    * data ausente/inválida ou início posterior ao fim: erro com o número da linha.
    """
    workbook = _open_workbook(path)
    try:
        ws = workbook.worksheets[0]
        reset = getattr(ws, "reset_dimensions", None)
        if callable(reset):
            reset()  # corrige arquivos com dimensão declarada incorretamente

        registros: list[Registro] = []
        avisos: list[str] = []
        vistos: set[tuple[str, int, int]] = set()
        duplicados = 0
        for numero_linha, linha in enumerate(
            ws.iter_rows(min_col=1, max_col=3, values_only=True), start=1
        ):
            mat_raw, ini_raw, fim_raw = (tuple(linha) + (None,) * 3)[:3]
            if _blank(mat_raw) and _blank(ini_raw) and _blank(fim_raw):
                continue

            matricula = _matricula_int(mat_raw)
            if matricula is None:
                if numero_linha > 1 and not _blank(mat_raw):  # linha 1 = cabeçalho
                    avisos.append(f"Linha {numero_linha} ignorada: matrícula inválida ('{mat_raw}').")
                continue

            try:
                data_ini = parse_date(ini_raw, "Data inicial")
                data_fim = parse_date(fim_raw, "Data final")
            except ValidationError as exc:
                raise SpreadsheetError(f"Linha {numero_linha}: {exc}") from exc
            if data_ini > data_fim:
                raise SpreadsheetError(
                    f"Data inicial ({data_ini:%d/%m/%Y}) posterior à data final "
                    f"({data_fim:%d/%m/%Y}) na linha {numero_linha}."
                )

            reg = Registro(str(matricula), data_ini.year, data_fim.year)
            if reg.chave in vistos:
                duplicados += 1
                continue
            vistos.add(reg.chave)
            registros.append(reg)

        if not registros:
            detalhe = ("\n" + "\n".join(avisos[:5])) if avisos else ""
            raise SpreadsheetError(
                "Nenhum vínculo válido encontrado nas colunas A, B e C da aba "
                f"'{ws.title}'.\nEsperado: Matrícula | Data inicial | Data final.{detalhe}"
            )
        return RegistrosImport(registros, avisos, duplicados, ws.title)
    except SpreadsheetError:
        raise
    except Exception as exc:  # noqa: BLE001 - erro de leitura no meio do arquivo
        raise SpreadsheetError(f"Erro ao ler o conteúdo da planilha:\n{exc}") from exc
    finally:
        workbook.close()


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