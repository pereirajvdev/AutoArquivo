"""Módulo Férias: nomes (manual ou planilha) + diretório de saída."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QSplitter, QVBoxLayout, QWidget

from ..commands import build_ferias_args
from ..config import ModuleSpec
from ..launch import resolve_launch
from ..models import Nome
from ..spreadsheet import SpreadsheetError, read_nomes
from ..table_model import ItemTableModel
from ..validators import ValidationError, parse_name, validate_directory
from .base_page import AppContext, ModulePage, column_layout, guarded, scroll_column
from .dialogs import edit_nome, show_error
from .run_panel import RunPanel
from .widgets import Card, FeedbackLabel, ManagedTable, PathSelector, make_button, plural, set_prop


class FeriasPage(ModulePage):
    def __init__(self, spec: ModuleSpec, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(spec, ctx, parent)
        self.m_nomes = ItemTableModel(["Nome", "Origem"], lambda n: (n.texto, n.origem),
                                      key=lambda n: n.chave)
        self._build_ui()
        self.m_nomes.changed.connect(self._refresh_resumo)
        self.run_panel.startRequested.connect(self._on_start)
        self.run_panel.runningChanged.connect(lambda running: self.inputs.setEnabled(not running))
        self._refresh_resumo()

    def _build_ui(self) -> None:
        self.inputs = QWidget()
        col = column_layout(self.inputs)

        # --- nomes
        nomes = Card("Nomes", "Adicione manualmente ou importe de uma planilha. Duplicatas são ignoradas.",
                     "plus")
        self.ed_nome = QLineEdit()
        self.ed_nome.setPlaceholderText("Nome completo do servidor")
        btn = make_button("Adicionar", "plus", "primary")
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(self.ed_nome, 1)
        row.addWidget(btn)
        nomes.add(row)
        self.fb_nome = FeedbackLabel()
        nomes.add(self.fb_nome)
        self.t_nomes = ManagedTable(self.m_nomes, ("nome", "nomes"), edit_nome, "Nenhum nome adicionado.")
        nomes.add(self.t_nomes)
        btn.clicked.connect(self._add_nome)
        self.ed_nome.returnPressed.connect(self._add_nome)
        self.ed_nome.textChanged.connect(lambda _t: set_prop(self.ed_nome, "invalid", False))
        col.addWidget(nomes, 1)

        # --- planilha
        planilha = Card("Planilha Excel", "A coluna de nomes é identificada automaticamente (ex.: 'Nome').",
                        "sheet")
        self.sel_planilha = PathSelector(
            self.ctx.settings, "ferias_planilha", "file", "Nenhuma planilha selecionada",
            "Selecionar planilha Excel", "Planilhas Excel (*.xlsx *.xlsm);;Todos os arquivos (*)",
            editable=False, button_text="Selecionar planilha")
        planilha.add(self.sel_planilha)
        self.lbl_planilha = QLabel("")
        self.lbl_planilha.setObjectName("muted")
        self.lbl_planilha.setWordWrap(True)
        planilha.add(self.lbl_planilha)
        self.sel_planilha.pathChanged.connect(self._on_planilha)
        col.addWidget(planilha)

        # --- saída
        saida = Card("Diretório de saída", "Onde os dados gerados serão salvos (argumento --saida).", "folder")
        self.sel_saida = PathSelector(
            self.ctx.settings, "ferias_saida", "dir", "Nenhum diretório selecionado",
            "Selecionar diretório de saída")
        saida.add(self.sel_saida)
        col.addWidget(saida)

        right = QWidget()
        right.setObjectName("pageBody")
        right_col = QVBoxLayout(right)
        right_col.setContentsMargins(8, 0, 0, 0)
        right_col.setSpacing(14)
        resumo = Card("Resumo", "Dados que serão enviados ao script.", "file")
        self.lbl_resumo = QLabel("")
        self.lbl_resumo.setWordWrap(True)
        resumo.add(self.lbl_resumo)
        right_col.addWidget(resumo)
        self.run_panel = RunPanel(self.spec.action_text)
        right_col.addWidget(self.run_panel, 1)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(scroll_column(self.inputs))
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 5)
        splitter.setStretchFactor(1, 6)
        splitter.setChildrenCollapsible(False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 16)
        layout.setSpacing(16)
        layout.addWidget(self.make_header())
        layout.addWidget(splitter, 1)

    # ------------------------------------------------------------------ nomes
    @guarded
    def _add_nome(self) -> None:
        try:
            texto = parse_name(self.ed_nome.text())
        except ValidationError as exc:
            set_prop(self.ed_nome, "invalid", True)
            self.fb_nome.show_message(str(exc), "error")
            return
        if not self.m_nomes.add(Nome(texto, "Manual")):
            set_prop(self.ed_nome, "invalid", True)
            self.fb_nome.show_message("Este nome já foi adicionado.", "error")
            return
        self.fb_nome.show_message(f"'{texto}' adicionado.", "ok")
        self.ed_nome.clear()
        self.ed_nome.setFocus()

    def _on_planilha(self, path: str) -> None:
        if not path:
            return
        try:
            result = read_nomes(path)
        except SpreadsheetError as exc:
            show_error(self, "Não foi possível ler a planilha", str(exc))
            self.sel_planilha.set_path("")
            return
        except Exception as exc:  # noqa: BLE001
            show_error(self, "Erro inesperado", f"Falha ao interpretar a planilha:\n{exc}")
            self.sel_planilha.set_path("")
            return
        novos, ja_existentes = self.m_nomes.add_many(Nome(n, "Planilha") for n in result.nomes)
        info = f"{plural(novos, 'nome adicionado', 'nomes adicionados')} da aba '{result.planilha}'."
        duplicados = ja_existentes + result.duplicados
        if duplicados:
            info += f" {plural(duplicados, 'duplicado ignorado', 'duplicados ignorados')}."
        self.lbl_planilha.setText(info)
        self.ctx.notify(f"Planilha importada: {Path(path).name}")

    def _refresh_resumo(self) -> None:
        total = len(self.m_nomes)
        self.lbl_resumo.setText(
            f"{plural(total, 'nome será enviado', 'nomes serão enviados')} ao script."
            if total else "Nenhum nome informado ainda.")

    # --------------------------------------------------------------- execução
    @guarded
    def _on_start(self) -> None:
        nomes = [n.texto for n in self.m_nomes.items()]
        if not nomes:
            raise ValidationError("Adicione ao menos um nome (manualmente ou por planilha) antes de executar.")
        saida = validate_directory(self.sel_saida.path(), "Diretório de saída")
        launch = resolve_launch(self.ctx.settings, self.spec.key)

        args = build_ferias_args(nomes, saida)
        self.run_panel.log.append("info", f"Iniciando '{self.spec.title}' com {len(nomes)} nome(s).")
        self.run_panel.execute(launch, args)
