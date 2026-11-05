"""AutoArquivo - painel central de automações de RH.

Execute com:  python src\\main.py   (ou use o iniciar.bat na raiz do projeto)
"""

from __future__ import annotations

import logging
import sys
import traceback
from logging.handlers import RotatingFileHandler
from pathlib import Path

# Permite executar de qualquer diretório de trabalho.
SRC_DIR = Path(__file__).resolve().parent
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from autoarquivo.config import APP_NAME, Settings, settings_dir  # noqa: E402


def _setup_logging() -> None:
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    try:
        folder = settings_dir()
        folder.mkdir(parents=True, exist_ok=True)
        handlers.append(RotatingFileHandler(folder / "autoarquivo.log", maxBytes=512_000,
                                            backupCount=2, encoding="utf-8"))
    except OSError:
        pass
    logging.basicConfig(level=logging.INFO, handlers=handlers,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def _install_excepthook() -> None:
    """Exceções não tratadas são registradas e exibidas, sem encerrar a aplicação."""

    def hook(exc_type, exc, tb) -> None:
        logging.getLogger("autoarquivo").error(
            "Exceção não tratada:\n%s", "".join(traceback.format_exception(exc_type, exc, tb)))
        try:
            from PySide6.QtWidgets import QApplication, QMessageBox

            if QApplication.instance() is not None:
                QMessageBox.critical(
                    None, "Erro inesperado",
                    f"Ocorreu um erro inesperado, mas a aplicação continua aberta.\n\n{exc}")
        except Exception:  # noqa: BLE001
            pass

    sys.excepthook = hook


def main() -> int:
    _setup_logging()
    _install_excepthook()

    from PySide6.QtGui import QFont
    from PySide6.QtWidgets import QApplication

    from autoarquivo.ui.main_window import MainWindow
    from autoarquivo.ui.styles import build_stylesheet

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setStyle("Fusion")
    font = QFont("Segoe UI", 10)
    font.setStyleHint(QFont.StyleHint.SansSerif)
    app.setFont(font)
    app.setStyleSheet(build_stylesheet())

    window = MainWindow(Settings())
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
