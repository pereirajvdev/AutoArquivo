"""Direcionamento dos registros por ano entre os scripts de ficha (sem Qt).

* ``ANO_CORTE`` em diante (2009+)  -> AutoFicha;
* anos anteriores ao corte (até 2008) -> JMSFicha.

Um vínculo que atravessa o corte é dividido: ``2007-2012`` vira ``2007-2008``
(JMSFicha) e ``2009-2012`` (AutoFicha). Em cada lado, intervalos da mesma
matrícula que se sobrepõem são unidos, para nenhum ano ser processado duas vezes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .models import Registro

ANO_CORTE = 2009


@dataclass(frozen=True)
class RegistrosDivididos:
    legado: tuple[Registro, ...]  # anos < corte (JMSFicha)
    atual: tuple[Registro, ...]   # anos >= corte (AutoFicha)


def mesclar_sobreposicoes(registros: Iterable[Registro]) -> list[Registro]:
    """Une intervalos sobrepostos de cada matrícula (mantém a ordem de 1ª aparição das matrículas)."""
    por_matricula: dict[str, list[Registro]] = {}
    for reg in registros:
        por_matricula.setdefault(reg.matricula, []).append(reg)

    resultado: list[Registro] = []
    for matricula, regs in por_matricula.items():
        regs.sort(key=lambda r: (r.inicio, r.fim))
        inicio, fim = regs[0].inicio, regs[0].fim
        for reg in regs[1:]:
            if reg.inicio <= fim:
                fim = max(fim, reg.fim)
            else:
                resultado.append(Registro(matricula, inicio, fim))
                inicio, fim = reg.inicio, reg.fim
        resultado.append(Registro(matricula, inicio, fim))
    return resultado


def dividir_por_ano(registros: Iterable[Registro], corte: int = ANO_CORTE) -> RegistrosDivididos:
    """Separa os registros pelo ano de corte, cortando os vínculos que o atravessam."""
    legado: list[Registro] = []
    atual: list[Registro] = []
    for reg in registros:
        if reg.inicio < corte:
            legado.append(Registro(reg.matricula, reg.inicio, min(reg.fim, corte - 1)))
        if reg.fim >= corte:
            atual.append(Registro(reg.matricula, max(reg.inicio, corte), reg.fim))
    return RegistrosDivididos(tuple(mesclar_sobreposicoes(legado)),
                              tuple(mesclar_sobreposicoes(atual)))
