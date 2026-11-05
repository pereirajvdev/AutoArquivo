"""Módulo Licenças: coleta de nomes e planilha. A execução será integrada futuramente.

A página já expõe os dados prontos para uso (``nomes()`` e ``planilha()``);
quando o script existir, basta criar um RunPanel e um ``build_*_args`` em
``commands.py``, como nos módulos Ficha/Faltas/Férias.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from ..config import ModuleSpec
from ..models import Nome
from ..spreadsheet import SheetPreview, SpreadsheetError, read_nomes, read_preview
from ..table_model import ItemTableModel
from ..validators import ValidationError, parse_name
from .base_page import AppContext, ModulePage, column_layout, guarded, scroll_column
from .dialogs import edit_nome, show_error
from .widgets import (
    Card,
    DataTable,
    FeedbackLabel,
    ManagedTable,
    PathSelector,
    make_button,
    plural,
    set_prop,
)


class LicencasPage(ModulePage):
    def __init__(self, spec: ModuleSpec, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(spec, ctx, parent)
        self.m_nomes = ItemTableModel(["Nome", "Origem"], lambda n: (n.texto, n.origem),
                                      key=lambda n: n.chave)
        self.m_planilha = ItemTableModel([], lambda row: row)  # recriado a cada planilha
        self._preview: SheetPreview | None = None
        self._build_ui()

    # --------------------------------------------------------------- dados
    def nomes(self) -> list[str]:
        """Nomes informados (manualmente ou da planilha)."""
        return [n.texto for n in self.m_nomes.items()]

    def planilha(self) -> SheetPreview | None:
        """Conteúdo da última planilha carregada (cabeçalhos + linhas)."""
        return self._preview

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        left = QWidget()
        col = column_layout(left)

        nomes = Card("Nomes", "Adicione nomes manualmente; a lista pode ser editada e filtrada depois.", "plus")
        self.ed_nome = QLineEdit()
        self.ed_nome.setPlaceholderText("Nome completo do servidor")
        btn = make_button("Adicionar nome", "plus", "primary")
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

        planilha = Card("Planilha Excel", "Os dados são interpretados e exibidos ao lado. "
                        "Se houver uma coluna de nomes, eles entram na lista.", "sheet")
        self.sel_planilha = PathSelector(
            self.ctx.settings, "licencas_planilha", "file", "Nenhuma planilha selecionada",
            "Selecionar planilha Excel", "Planilhas Excel (*.xlsx *.xlsm);;Todos os arquivos (*)",
            editable=False, button_text="Selecionar planilha")
        planilha.add(self.sel_planilha)
        self.lbl_planilha = QLabel("")
        self.lbl_planilha.setObjectName("muted")
        self.lbl_planilha.setWordWrap(True)
        planilha.add(self.lbl_planilha)
        self.sel_planilha.pathChanged.connect(self._on_planilha)
        col.addWidget(planilha)

        right = QWidget()
        right.setObjectName("pageBody")
        right_col = QVBoxLayout(right)
        right_col.setContentsMargins(8, 0, 0, 0)
        right_col.setSpacing(14)

        dados = Card("Dados da planilha", "Pré-visualização do conteúdo interpretado.", "file")
        self.t_planilha = DataTable("Selecione uma planilha para visualizar os dados.")
        self.t_planilha.setModel(self.m_planilha)
        self.t_planilha.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        dados.add(self.t_planilha, 1)
        right_col.addWidget(dados, 1)

        exec_card = Card("Execução", "", "play")
        note = QLabel("A integração com o script de licenças será definida posteriormente.")
        note.setObjectName("muted")
        note.setWordWrap(True)
        exec_card.add(note)
        run = make_button(self.spec.action_text, "play", "primary",
                          "Disponível quando o script de licenças for integrado")
        run.setEnabled(False)
        exec_card.add(run)
        right_col.addWidget(exec_card)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(scroll_column(left))
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 5)
        splitter.setStretchFactor(1, 6)
        splitter.setChildrenCollapsible(False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 16)
        layout.setSpacing(16)
        layout.addWidget(self.make_header())
        layout.addWidget(splitter, 1)

    # ------------------------------------------------------------------ ações
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
            preview = read_preview(path)
        except SpreadsheetError as exc:
            show_error(self, "Não foi possível ler a planilha", str(exc))
            self.sel_planilha.set_path("")
            return
        except Exception as exc:  # noqa: BLE001
            show_error(self, "Erro inesperado", f"Falha ao interpretar a planilha:\n{exc}")
            self.sel_planilha.set_path("")
            return

        self._preview = preview
        width = len(preview.headers)
        model = ItemTableModel(preview.headers, lambda row: row)
        model.set_items([tuple(r) for r in preview.rows])
        # Linhas idênticas são legítimas na prévia: o modelo é recriado sem filtro de duplicatas.
        self.m_planilha = model
        self.t_planilha.setModel(model)

        info = (f"{plural(len(preview.rows), 'linha', 'linhas')} e {plural(width, 'coluna', 'colunas')} "
                f"na aba '{preview.sheet}'.")
        if preview.truncated:
            info += " Exibindo apenas as primeiras linhas."
        try:
            nomes = read_nomes(path)
        except SpreadsheetError:
            info += " Nenhuma coluna de nomes identificada."
        else:
            novos, _ = self.m_nomes.add_many(Nome(n, "Planilha") for n in nomes.nomes)
            info += f" {plural(novos, 'nome adicionado', 'nomes adicionados')} à lista."
        self.lbl_planilha.setText(info)
        self.ctx.notify(f"Planilha importada: {Path(path).name}")
