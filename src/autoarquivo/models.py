"""Modelos de dados do domínio (sem dependência de Qt)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .validators import name_key


@dataclass(frozen=True)
class Registro:
    """Matrícula + intervalo de anos (um único ano => inicio == fim)."""

    matricula: str
    inicio: int
    fim: int

    @property
    def chave(self) -> tuple[str, int, int]:
        return (self.matricula, self.inicio, self.fim)

    def as_dict(self) -> dict[str, object]:
        return {"matricula": self.matricula, "inicio": self.inicio, "fim": self.fim}


@dataclass(frozen=True)
class Periodo:
    inicio: int
    fim: int


@dataclass(frozen=True)
class Nome:
    texto: str
    origem: str = "Manual"

    @property
    def chave(self) -> str:
        return name_key(self.texto)


def combinar_registros(
    matriculas: Iterable[str],
    periodos: Iterable[Periodo],
    importados: Iterable[Registro],
) -> list[Registro]:
    """Consolida a entrada manual (matrículas x períodos) com os registros importados.

    Registros idênticos (matrícula + início + fim) aparecem uma única vez.
    """
    periodos = list(periodos)
    vistos: set[tuple[str, int, int]] = set()
    resultado: list[Registro] = []

    def _add(reg: Registro) -> None:
        if reg.chave not in vistos:
            vistos.add(reg.chave)
            resultado.append(reg)

    for mat in matriculas:
        for per in periodos:
            _add(Registro(mat, per.inicio, per.fim))
    for reg in importados:
        _add(reg)
    return resultado
