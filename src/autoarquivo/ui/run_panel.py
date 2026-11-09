"""Painel de execução: iniciar/cancelar, indicador de progresso, status e log."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QApplication, QHBoxLayout, QLabel, QProgressBar, QWidget

from ..commands import format_command
from ..launch import Launch
from ..runner import RunResult, ScriptRunner
from .dialogs import confirm, show_error, show_info, show_warning
from .widgets import Card, LogPanel, make_button, set_prop


class RunPanel(Card):
    """Encapsula um :class:`ScriptRunner` e toda a apresentação da execução.

    A página dona decide *quando* executar (``startRequested``) e chama
    :meth:`execute` depois de validar os dados. Ao terminar, ``finished`` entrega
    o :class:`RunResult` para que a página reaja ao resultado.
    """

    startRequested = Signal()
    runningChanged = Signal(bool)
    finished = Signal(object)  # RunResult

    def __init__(self, start_text: str = "Iniciar", parent: QWidget | None = None) -> None:
        super().__init__("Execução", "Acompanhe o andamento e o resultado da automação.",
                         "play", parent)
        self.runner = ScriptRunner(self)
        self._task = ""
        self._quiet = False

        self.btn_start = make_button(start_text, "play", "primary")
        self.btn_cancel = make_button("Cancelar", "stop", "danger", "Interromper a execução")
        self.btn_cancel.setEnabled(False)
        self.chip = QLabel("Aguardando")
        self.chip.setObjectName("chip")
        set_prop(self.chip, "state", "idle")
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setRange(0, 1)
        self.progress.setValue(0)
        self.btn_clear_log = make_button("Limpar log", None, "ghost")

        bar = QHBoxLayout()
        bar.setSpacing(8)
        bar.addWidget(self.btn_start)
        bar.addWidget(self.btn_cancel)
        bar.addSpacing(6)
        bar.addWidget(self.progress, 1)
        bar.addWidget(self.chip)
        self.add(bar)

        self.log = LogPanel()
        self.add(self.log, 1)
        foot = QHBoxLayout()
        foot.addStretch(1)
        foot.addWidget(self.btn_clear_log)
        self.add(foot)

        self.btn_start.clicked.connect(self._on_start_clicked)
        self.btn_cancel.clicked.connect(self._on_cancel_clicked)
        self.btn_clear_log.clicked.connect(self.log.clear)
        self.runner.output.connect(self.log.append)
        self.runner.completed.connect(self._on_completed)

    # ---------------------------------------------------------------- API
    @property
    def is_running(self) -> bool:
        return self.runner.is_running

    def execute(self, launch: Launch, args: list[str], task: str = "", quiet: bool = False) -> None:
        """Inicia o script. Nunca permite duas execuções simultâneas do módulo.

        ``task`` (opcional) nomeia a etapa nas mensagens ao usuário, para
        distinguir execuções diferentes que compartilham este painel.
        ``quiet`` suprime os diálogos de fim de execução (a página dona passa a
        mostrar o seu próprio, p.ex. um resumo único após várias execuções em fila).
        """
        if self.is_running:
            show_warning(self, "Execução em andamento", "Este módulo já está em execução.")
            return
        self._task = task
        self._quiet = quiet
        self.log.append("info", "Comando: " + format_command(launch.python, launch.script, args))
        self._set_running(True)
        try:
            self.runner.start(launch.python, launch.script, args)
        except Exception as exc:  # noqa: BLE001 - a UI não pode cair
            self._set_running(False)
            self.log.append("err", str(exc))
            show_error(self, "Falha ao iniciar", str(exc))

    def shutdown(self) -> None:
        self.runner.shutdown()

    # ------------------------------------------------------------- slots
    def _on_start_clicked(self) -> None:
        if not self.is_running:
            self.startRequested.emit()

    def _on_cancel_clicked(self) -> None:
        if self.is_running and confirm(
                self, "Cancelar execução",
                "Deseja realmente cancelar a automação em andamento?\n"
                "O processamento será interrompido e o resultado poderá ficar incompleto.",
                "Cancelar execução", danger=True):
            self.btn_cancel.setEnabled(False)
            self.runner.cancel()

    def _set_running(self, running: bool) -> None:
        self.btn_start.setEnabled(not running)
        self.btn_cancel.setEnabled(running)
        if running:
            self.progress.setRange(0, 0)  # indicador animado "ocupado"
            self._set_chip("Em execução", "running")
        else:
            self.progress.setRange(0, 1)
            self.progress.setValue(0)
        self.runningChanged.emit(running)

    def _set_chip(self, text: str, state: str) -> None:
        self.chip.setText(text)
        set_prop(self.chip, "state", state)

    def _on_completed(self, result: RunResult) -> None:
        self._set_running(False)
        code = "-" if result.exit_code is None else str(result.exit_code)
        if result.status == "success":
            self._set_chip("Concluído", "success")
            self.log.append("ok", f"Processo finalizado com código de retorno {code}. {result.message}")
        elif result.status == "cancelled":
            self._set_chip("Cancelado", "cancelled")
            self.log.append("info", f"{result.message} (código de retorno {code})")
        else:
            self._set_chip("Falhou", "error")
            self.log.append("err", f"{result.message} (código de retorno {code})")

        # A página pode iniciar uma nova execução ao receber o sinal; por isso o
        # modo e a tarefa desta execução são lidos ANTES de emitir.
        quiet, task = self._quiet, self._task

        # Avisa a página antes dos diálogos modais, para que ela atualize seus controles.
        self.finished.emit(result)

        if quiet:
            return
        QApplication.alert(self.window())  # pisca a barra de tarefas se estiver em segundo plano
        subject = f"A etapa '{task}'" if task else "A automação"
        if result.status == "success":
            show_info(self, "Automação concluída", f"{subject} foi concluída com sucesso.\n"
                      f"Código de retorno: {code}.")
        elif result.status == "cancelled":
            show_warning(self, "Execução cancelada", result.message)
        else:
            show_error(self, "Falha na automação", result.message,
                       "Consulte a área de log para ver as mensagens do script (stderr).")
