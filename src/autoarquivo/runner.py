"""Execução assíncrona dos scripts externos com QProcess (não bloqueia a interface)."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from functools import partial
from pathlib import Path

from PySide6.QtCore import QObject, QProcess, QProcessEnvironment, QTimer, Signal

KILL_GRACE_MS = 3000


@dataclass(frozen=True)
class RunResult:
    """Resultado final de uma execução.

    ``status``: ``success`` | ``failed`` | ``cancelled`` | ``error`` (não iniciou/crash).
    """

    status: str
    exit_code: int | None
    message: str = ""


def _decode(raw: bytes) -> str:
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("cp1252", errors="replace")


class ScriptRunner(QObject):
    """Executa ``python script.py <args>`` e emite stdout/stderr linha a linha.

    Sinais:
      * ``output(kind, linha)``  - ``kind`` = ``"out"`` (stdout), ``"err"`` (stderr) ou ``"info"``;
      * ``completed(RunResult)`` - emitido exatamente uma vez por execução.
    """

    output = Signal(str, str)
    completed = Signal(object)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._process: QProcess | None = None
        self._buffers = {"out": b"", "err": b""}
        self._cancelled = False
        self._done = True

    @property
    def is_running(self) -> bool:
        return self._process is not None and self._process.state() != QProcess.ProcessState.NotRunning

    # ------------------------------------------------------------------ controle
    def start(self, python: str, script: Path, args: list[str]) -> None:
        if self.is_running:
            raise RuntimeError("Já existe uma execução em andamento neste módulo.")
        self._cancelled = False
        self._done = False
        self._buffers = {"out": b"", "err": b""}

        process = QProcess(self)
        self._process = process
        process.setProgram(python)
        process.setArguments([str(script), *args])
        process.setWorkingDirectory(str(script.parent))

        env = QProcessEnvironment.systemEnvironment()
        env.insert("PYTHONUNBUFFERED", "1")      # log em tempo real
        env.insert("PYTHONIOENCODING", "utf-8")  # acentos corretos em stdout/stderr
        process.setProcessEnvironment(env)

        process.readyReadStandardOutput.connect(partial(self._drain, "out"))
        process.readyReadStandardError.connect(partial(self._drain, "err"))
        process.finished.connect(self._on_finished)
        process.errorOccurred.connect(self._on_error)
        process.start()

    def cancel(self) -> None:
        """Pede o encerramento (terminate) e força (kill) após um prazo."""
        process = self._process
        if process is None or process.state() == QProcess.ProcessState.NotRunning:
            return
        self._cancelled = True
        self.output.emit("info", "Cancelamento solicitado…")
        process.terminate()
        QTimer.singleShot(KILL_GRACE_MS, partial(self._force_kill, process))

    def shutdown(self) -> None:
        """Encerra imediatamente (usado ao fechar a aplicação)."""
        process = self._process
        if process is None or process.state() == QProcess.ProcessState.NotRunning:
            return
        self._cancelled = True
        self._kill_tree(process)
        process.waitForFinished(2000)

    # ------------------------------------------------------------------ internos
    def _kill_tree(self, process: QProcess) -> None:
        pid = process.processId()
        if sys.platform == "win32" and pid:
            # Encerra também os processos filhos (ex.: navegador aberto pelo script).
            QProcess.startDetached("taskkill", ["/PID", str(pid), "/T", "/F"])
        else:
            process.kill()

    def _force_kill(self, process: QProcess) -> None:
        if process is not self._process or process.state() == QProcess.ProcessState.NotRunning:
            return
        self.output.emit("info", "O processo não respondeu; encerrando à força…")
        self._kill_tree(process)

    def _drain(self, kind: str) -> None:
        process = self._process
        if process is None:
            return
        chunk = process.readAllStandardOutput() if kind == "out" else process.readAllStandardError()
        data = self._buffers[kind] + bytes(chunk.data())
        *lines, rest = data.split(b"\n")
        self._buffers[kind] = rest
        for line in lines:
            self.output.emit(kind, _decode(line.rstrip(b"\r")))

    def _flush(self) -> None:
        for kind in ("out", "err"):
            self._drain(kind)
            rest = self._buffers[kind].rstrip(b"\r")
            self._buffers[kind] = b""
            if rest:
                self.output.emit(kind, _decode(rest))

    def _finish(self, result: RunResult) -> None:
        if self._done:
            return
        self._done = True
        process, self._process = self._process, None
        if process is not None:
            process.deleteLater()
        self.completed.emit(result)

    def _on_finished(self, exit_code: int, exit_status: QProcess.ExitStatus) -> None:
        self._flush()
        if self._cancelled:
            self._finish(RunResult("cancelled", exit_code, "Execução cancelada pelo usuário."))
        elif exit_status == QProcess.ExitStatus.CrashExit:
            self._finish(RunResult("error", exit_code, "O processo foi encerrado inesperadamente."))
        elif exit_code == 0:
            self._finish(RunResult("success", 0, "Execução concluída com sucesso."))
        else:
            self._finish(RunResult("failed", exit_code, f"O script terminou com erro (código {exit_code})."))

    def _on_error(self, error: QProcess.ProcessError) -> None:
        if error == QProcess.ProcessError.FailedToStart:
            program = self._process.program() if self._process else "python"
            self._finish(RunResult(
                "error", None,
                f"Não foi possível iniciar o interpretador Python:\n{program}\n"
                "Verifique o caminho em Configurações.",
            ))
        elif error != QProcess.ProcessError.Crashed:  # Crashed é tratado em finished()
            self.output.emit("err", f"Erro de processo: {error.name}")
