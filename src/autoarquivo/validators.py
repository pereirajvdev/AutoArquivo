"""Validações e normalizações reutilizáveis (sem dependência de Qt)."""

from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime
from pathlib import Path
from typing import Any

YEAR_MIN = 1900
YEAR_MAX = 2100


class ValidationError(ValueError):
    """Erro de validação com mensagem pronta para o usuário."""


def strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))


# ------------------------------------------------------------------ matrículas
_MATRICULA_NOISE = re.compile(r"[.\s\-/_]")


def normalize_matricula(raw: Any) -> str:
    """Normaliza uma matrícula: ``'1.234'`` -> ``'1234'``.

    Aceita ``str``, ``int`` e ``float`` inteiro (valores vindos do Excel).
    """
    if raw is None or isinstance(raw, bool):
        raise ValidationError("Matrícula vazia.")
    if isinstance(raw, float):
        if not raw.is_integer():
            raise ValidationError(f"Matrícula inválida: '{raw}'.")
        raw = int(raw)
    text = str(raw).strip()
    if not text:
        raise ValidationError("Matrícula vazia.")
    cleaned = _MATRICULA_NOISE.sub("", text)
    if not re.fullmatch(r"[0-9]+", cleaned):
        raise ValidationError(
            f"Matrícula inválida: '{text}'. Use apenas números, como 1234 ou 1.234."
        )
    return cleaned


def parse_matriculas(text: str) -> list[str]:
    """Interpreta uma ou várias matrículas separadas por vírgula, ponto e vírgula ou espaço."""
    parts = [p for p in re.split(r"[;,\s]+", text.strip()) if p]
    if not parts:
        raise ValidationError("Informe ao menos uma matrícula.")
    result: list[str] = []
    invalid: list[str] = []
    for part in parts:
        try:
            value = normalize_matricula(part)
        except ValidationError:
            invalid.append(part)
            continue
        if value not in result:
            result.append(value)
    if invalid:
        raise ValidationError(
            "Matrícula(s) inválida(s): " + ", ".join(invalid)
            + ". Use apenas números, como 1234 ou 1.234."
        )
    return result


# ------------------------------------------------------------------------ anos
def parse_year(raw: Any, label: str = "Ano") -> int:
    if raw is None or isinstance(raw, bool):
        raise ValidationError(f"Informe o {label.lower()}.")
    if isinstance(raw, float):
        if not raw.is_integer():
            raise ValidationError(f"{label} inválido: '{raw}'.")
        raw = int(raw)
    text = str(raw).strip()
    if not text:
        raise ValidationError(f"Informe o {label.lower()}.")
    if not re.fullmatch(r"[0-9]{4}", text):
        raise ValidationError(f"{label} inválido: '{text}'. Informe 4 dígitos, como 2019.")
    year = int(text)
    if not YEAR_MIN <= year <= YEAR_MAX:
        raise ValidationError(f"{label} fora do intervalo permitido ({YEAR_MIN} a {YEAR_MAX}).")
    return year


def parse_period(inicio: Any, fim: Any) -> tuple[int, int]:
    """Valida um período. Ano final vazio significa ano único (fim = início)."""
    start = parse_year(inicio, "Ano inicial")
    blank_end = fim is None or (isinstance(fim, str) and not fim.strip())
    end = start if blank_end else parse_year(fim, "Ano final")
    if start > end:
        raise ValidationError(f"O ano inicial ({start}) não pode ser maior que o ano final ({end}).")
    return start, end


# ----------------------------------------------------------------------- datas
_DATE_FORMATS = ("%d/%m/%Y", "%d/%m/%y", "%d-%m-%Y", "%d.%m.%Y", "%Y-%m-%d", "%Y/%m/%d")


def parse_date(raw: Any, label: str = "Data") -> date:
    """Converte o conteúdo de uma célula em ``date``.

    Aceita células de data do Excel (``datetime``/``date``) e texto
    (``dd/mm/aaaa``, ``dd/mm/aa``, ``dd-mm-aaaa``, ``dd.mm.aaaa``, ``aaaa-mm-dd``),
    com ou sem hora. Números puros são recusados de propósito: um "2019"
    (formato antigo, só ano) seria lido como um dia qualquer de 1905.
    """
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        raise ValidationError(f"Informe a {label.lower()}.")
    result: date | None = None
    if isinstance(raw, datetime):
        result = raw.date()
    elif isinstance(raw, date):
        result = raw
    elif isinstance(raw, str):
        text = re.split(r"[ T]", raw.strip(), maxsplit=1)[0]
        for fmt in _DATE_FORMATS:
            try:
                result = datetime.strptime(text, fmt).date()
                break
            except ValueError:
                continue
    if result is None:
        raise ValidationError(
            f"{label} inválida: '{raw}'. Use uma data do Excel ou o formato dd/mm/aaaa."
        )
    if not YEAR_MIN <= result.year <= YEAR_MAX:
        raise ValidationError(
            f"{label} fora do intervalo permitido ({YEAR_MIN} a {YEAR_MAX}): "
            f"{result.strftime('%d/%m/%Y')}."
        )
    return result


# ----------------------------------------------------------------------- nomes
def normalize_name(raw: Any) -> str:
    return " ".join(str(raw).split()) if raw is not None else ""


def parse_name(raw: Any) -> str:
    name = normalize_name(raw)
    if not name:
        raise ValidationError("Informe um nome.")
    if not any(c.isalpha() for c in name):
        raise ValidationError(f"Nome inválido: '{name}'.")
    return name


def name_key(name: str) -> str:
    """Chave de comparação: ignora caixa, acentos e espaços repetidos."""
    return strip_accents(normalize_name(name)).casefold()


# ------------------------------------------------------------- arquivos/pastas
def validate_directory(raw: str | Path | None, label: str = "Diretório") -> Path:
    text = str(raw or "").strip()
    if not text:
        raise ValidationError(f"Selecione o {label.lower()}.")
    path = Path(text)
    try:
        if not path.exists():
            raise ValidationError(f"{label} não encontrado:\n{path}")
        if not path.is_dir():
            raise ValidationError(f"{label} não é uma pasta:\n{path}")
    except OSError as exc:
        raise ValidationError(f"{label} inacessível:\n{path}\n{exc}") from exc
    return path


def validate_file(raw: str | Path | None, label: str = "Arquivo") -> Path:
    text = str(raw or "").strip()
    if not text:
        raise ValidationError(f"Selecione o {label.lower()}.")
    path = Path(text)
    try:
        if not path.is_file():
            raise ValidationError(f"{label} não encontrado:\n{path}")
    except OSError as exc:
        raise ValidationError(f"{label} inacessível:\n{path}\n{exc}") from exc
    return path