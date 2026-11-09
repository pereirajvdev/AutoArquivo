"""Estado da integração Ficha → Excel e fila de execução por pasta (sem Qt).

``FichaState`` descreve em que ponto do fluxo a página está; ``ExcelBatch``
controla a fila "uma pasta por vez", acumulando sucessos e falhas sem nunca
interromper as demais pastas quando uma falha.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class FichaState(Enum):
    # (rótulo exibido, estado visual do chip: idle | running | success | error | cancelled)
    AGUARDANDO = ("Aguardando", "idle")
    PROCESSANDO = ("Processando fichas", "running")
    PRONTO = ("Pronto para gerar Excel", "success")
    GERANDO = ("Gerando Excel", "running")
    CONCLUIDO = ("Concluído", "success")
    PARCIAL = ("Concluído parcialmente", "cancelled")
    SEM_FICHAS = ("Sem fichas", "cancelled")
    ERRO = ("Erro", "error")

    @property
    def label(self) -> str:
        return self.value[0]

    @property
    def chip(self) -> str:
        return self.value[1]


# Estados em que "Gerar Excel das Fichas" pode ser acionado (desde que haja pastas retornadas).
EXCEL_ENABLED_STATES = frozenset({FichaState.PRONTO, FichaState.CONCLUIDO,
                                  FichaState.PARCIAL, FichaState.ERRO})


@dataclass
class ExcelBatch:
    """Fila sequencial de pastas. Cada pasta termina em sucesso, falha ou "não processada"."""

    pastas: list[Path]
    sucessos: list[Path] = field(default_factory=list)
    falhas: list[tuple[Path, str]] = field(default_factory=list)
    current: Path | None = None
    cancelled: bool = False
    _next: int = 0

    @property
    def recebidas(self) -> int:
        return len(self.pastas)

    @property
    def processadas(self) -> int:
        return len(self.sucessos) + len(self.falhas)

    @property
    def total(self) -> int:
        return len(self.pastas)

    @property
    def position(self) -> int:
        """Posição (1-based) da pasta atual/última iniciada."""
        return self._next

    def begin_next(self) -> Path | None:
        """Passa para a próxima pasta e a devolve; ``None`` quando acabou ou foi cancelado."""
        if self.current is not None:
            raise RuntimeError("Há uma pasta em andamento.")
        if self.cancelled or self._next >= len(self.pastas):
            return None
        self.current = self.pastas[self._next]
        self._next += 1
        return self.current

    def finish_current(self, ok: bool, message: str = "") -> Path:
        if self.current is None:
            raise RuntimeError("Nenhuma pasta em andamento.")
        pasta, self.current = self.current, None
        if ok:
            self.sucessos.append(pasta)
        else:
            self.falhas.append((pasta, message or "Falha sem detalhes."))
        return pasta

    def cancel(self) -> None:
        """Interrompe a fila (ação do usuário); as pastas restantes ficam como não processadas."""
        self.cancelled = True

    @property
    def nao_processadas(self) -> list[Path]:
        return self.pastas[self._next:] if self.cancelled else []

    @property
    def done(self) -> bool:
        return self.current is None and (self.cancelled or self._next >= len(self.pastas))

    # ------------------------------------------------------------------ relatório
    def final_state(self) -> FichaState:
        if not self.falhas and not self.nao_processadas:
            return FichaState.CONCLUIDO
        if not self.sucessos:
            return FichaState.ERRO
        return FichaState.PARCIAL

    def summary(self) -> str:
        lines = [
            f"Pastas recebidas do AutoFicha: {self.recebidas}",
            f"Pastas processadas: {self.processadas}",
            f"Sucessos: {len(self.sucessos)}",
            f"Falhas: {len(self.falhas)}",
        ]
        if self.nao_processadas:
            lines.append(f"Não processadas (execução cancelada): {len(self.nao_processadas)}")
        return "\n".join(lines)

    def failure_details(self) -> str:
        parts = [f"{pasta}\n    {motivo}" for pasta, motivo in self.falhas]
        parts += [f"{pasta}\n    Não processada (execução cancelada)." for pasta in self.nao_processadas]
        return "\n".join(parts)
