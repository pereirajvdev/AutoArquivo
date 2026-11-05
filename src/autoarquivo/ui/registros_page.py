"""Página compartilhada por Ficha e Faltas (matrícula + anos).

Os dois módulos usam exatamente a mesma estrutura; só mudam o ``ModuleSpec``
(título, texto do botão e script de destino) recebido no construtor.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QRegularExpression, Qt
from PySide6.QtGui import QRegularExpressionValidator
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from ..commands import build_registros_args
from ..config import ModuleSpec
from ..launch import resolve_launch
from ..models import Periodo, Registro, combinar_registros
from ..spreadsheet import SpreadsheetError, read_registros
from ..table_model import ItemTableModel
from ..validators import (
    ValidationError,
    parse_matriculas,
    parse_period,
    validate_directory,
)
from .base_page import AppContext, ModulePage, column_layout, guarded, scroll_column
from .dialogs import confirm, edit_matricula, edit_periodo, edit_registro, show_error, show_warning
from .run_panel import RunPanel
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

_REG_HEADERS = ["Matrícula", "Ano inicial", "Ano final"]


def _reg_row(r: Registro) -> tuple:
    return (r.matricula, r.inicio, r.fim)


class RegistrosPage(ModulePage):
    def __init__(self, spec: ModuleSpec, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(spec, ctx, parent)
        self._planilha_atual = ""

        # --- dados (cada tabela impede duplicatas pelo seu próprio critério)
        self.m_matriculas = ItemTableModel(["Matrícula"], lambda m: (m,))
        self.m_periodos = ItemTableModel(["Ano inicial", "Ano final"], lambda p: (p.inicio, p.fim))
        self.m_importados = ItemTableModel(_REG_HEADERS, _reg_row, key=lambda r: r.chave)
        self.m_consolidado = ItemTableModel(_REG_HEADERS, _reg_row, key=lambda r: r.chave)

        self._build_ui()

        for model in (self.m_matriculas, self.m_periodos, self.m_importados):
            model.changed.connect(self._refresh_consolidado)
        self.run_panel.startRequested.connect(self._on_start)
        self.run_panel.runningChanged.connect(lambda running: self.inputs.setEnabled(not running))
        self._refresh_consolidado()

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        self.inputs = QWidget()
        col = column_layout(self.inputs)
        col.addWidget(self._card_matriculas())
        col.addWidget(self._card_periodos())
        col.addWidget(self._card_planilha())
        col.addWidget(self._card_pasta())
        col.addStretch(1)

        right = QWidget()
        right.setObjectName("pageBody")
        right_col = QVBoxLayout(right)
        right_col.setContentsMargins(8, 0, 0, 0)
        right_col.setSpacing(14)
        right_col.addWidget(self._card_consolidado(), 2)
        self.run_panel = RunPanel(self.spec.action_text)
        right_col.addWidget(self.run_panel, 3)

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

    def _card_matriculas(self) -> Card:
        card = Card("Matrículas", "Opcional. Aceita 1234 ou 1.234; várias de uma vez separadas por vírgula.",
                    "plus")
        self.ed_matricula = QLineEdit()
        self.ed_matricula.setPlaceholderText("Ex.: 1234 ou 1.234")
        btn = make_button("Adicionar", "plus", "primary")
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(self.ed_matricula, 1)
        row.addWidget(btn)
        card.add(row)
        self.fb_matricula = FeedbackLabel()
        card.add(self.fb_matricula)
        self.t_matriculas = ManagedTable(
            self.m_matriculas, ("matrícula", "matrículas"), edit_matricula,
            "Nenhuma matrícula adicionada.")
        card.add(self.t_matriculas)

        btn.clicked.connect(self._add_matriculas)
        self.ed_matricula.returnPressed.connect(self._add_matriculas)
        self.ed_matricula.textChanged.connect(lambda _t: set_prop(self.ed_matricula, "invalid", False))
        return card

    def _card_periodos(self) -> Card:
        card = Card("Anos", "Opcional. Informe um único ano (deixe o final em branco) ou um intervalo.",
                    "calendar")
        digits = QRegularExpressionValidator(QRegularExpression(r"\d{0,4}"))
        self.ed_inicio = QLineEdit()
        self.ed_inicio.setPlaceholderText("Ano inicial")
        self.ed_fim = QLineEdit()
        self.ed_fim.setPlaceholderText("Ano final (opcional)")
        for edit in (self.ed_inicio, self.ed_fim):
            edit.setValidator(digits)
            edit.setMaxLength(4)
        btn = make_button("Adicionar", "plus", "primary")
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(self.ed_inicio, 1)
        row.addWidget(QLabel("até"))
        row.addWidget(self.ed_fim, 1)
        row.addWidget(btn)
        card.add(row)
        self.fb_periodo = FeedbackLabel()
        card.add(self.fb_periodo)
        self.t_periodos = ManagedTable(
            self.m_periodos, ("período", "períodos"), edit_periodo, "Nenhum período adicionado.")
        card.add(self.t_periodos)

        btn.clicked.connect(self._add_periodo)
        self.ed_inicio.returnPressed.connect(self._add_periodo)
        self.ed_fim.returnPressed.connect(self._add_periodo)
        for edit in (self.ed_inicio, self.ed_fim):
            edit.textChanged.connect(lambda _t, e=edit: set_prop(e, "invalid", False))
        return card

    def _card_planilha(self) -> Card:
        card = Card("Planilha Excel",
                    "Colunas reconhecidas automaticamente: Matrícula, Ano inicial e Ano final.",
                    "sheet")
        self.sel_planilha = PathSelector(
            self.ctx.settings, f"{self.spec.key}_planilha", "file",
            "Nenhuma planilha selecionada", "Selecionar planilha Excel",
            "Planilhas Excel (*.xlsx *.xlsm);;Todos os arquivos (*)",
            editable=False, button_text="Selecionar planilha")
        card.add(self.sel_planilha)
        self.lbl_planilha = QLabel("")
        self.lbl_planilha.setObjectName("muted")
        self.lbl_planilha.setWordWrap(True)
        card.add(self.lbl_planilha)
        self.t_importados = ManagedTable(
            self.m_importados, ("registro", "registros"), edit_registro,
            "Os registros da planilha aparecerão aqui.")
        card.add(self.t_importados)
        self.sel_planilha.pathChanged.connect(self._on_planilha)
        return card

    def _card_pasta(self) -> Card:
        card = Card("Pasta específica", "Opcional. Enviada ao script no argumento --pasta.", "folder")
        self.sel_pasta = PathSelector(
            self.ctx.settings, f"{self.spec.key}_pasta", "dir", "Nenhuma pasta selecionada",
            "Selecionar pasta", clearable=True)
        card.add(self.sel_pasta)
        return card

    def _card_consolidado(self) -> Card:
        card = Card("Registros que serão enviados",
                    "Entrada manual (matrículas × períodos) somada à planilha, sem duplicatas.",
                    "file")
        self.t_consolidado = DataTable("Adicione matrículas e anos, ou importe uma planilha.")
        self.t_consolidado.setModel(self.m_consolidado)
        self.t_consolidado.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        card.add(self.t_consolidado, 1)
        self.lbl_consolidado = QLabel("")
        self.lbl_consolidado.setObjectName("muted")
        self.lbl_consolidado.setWordWrap(True)
        card.add(self.lbl_consolidado)
        return card

    # ------------------------------------------------------- entrada manual
    @guarded
    def _add_matriculas(self) -> None:
        try:
            valores = parse_matriculas(self.ed_matricula.text())
        except ValidationError as exc:
            set_prop(self.ed_matricula, "invalid", True)
            self.fb_matricula.show_message(str(exc), "error")
            return
        novos, repetidos = self.m_matriculas.add_many(valores)
        if novos == 0:
            set_prop(self.ed_matricula, "invalid", True)
            self.fb_matricula.show_message(
                "Matrícula já adicionada." if len(valores) == 1 else "Todas as matrículas já foram adicionadas.",
                "error")
            return
        msg = f"{plural(novos, 'matrícula adicionada', 'matrículas adicionadas')}."
        if repetidos:
            msg += f" {repetidos} já existente(s) ignorada(s)."
        self.fb_matricula.show_message(msg, "ok")
        self.ed_matricula.clear()
        self.ed_matricula.setFocus()

    @guarded
    def _add_periodo(self) -> None:
        try:
            inicio, fim = parse_period(self.ed_inicio.text(), self.ed_fim.text())
        except ValidationError as exc:
            target = self.ed_inicio if not self.ed_inicio.text().strip() else self.ed_fim
            set_prop(target, "invalid", True)
            self.fb_periodo.show_message(str(exc), "error")
            return
        if not self.m_periodos.add(Periodo(inicio, fim)):
            self.fb_periodo.show_message("Este período já foi adicionado.", "error")
            return
        rotulo = str(inicio) if inicio == fim else f"{inicio} a {fim}"
        self.fb_periodo.show_message(f"Período {rotulo} adicionado.", "ok")
        self.ed_inicio.clear()
        self.ed_fim.clear()
        self.ed_inicio.setFocus()

    # --------------------------------------------------------------- planilha
    def _on_planilha(self, path: str) -> None:
        if not path:
            return
        previous = self._planilha_atual
        try:
            result = read_registros(path)
        except SpreadsheetError as exc:
            show_error(self, "Não foi possível ler a planilha", str(exc))
            self.sel_planilha.set_path(previous)
            return
        except Exception as exc:  # noqa: BLE001
            show_error(self, "Erro inesperado", f"Falha ao interpretar a planilha:\n{exc}")
            self.sel_planilha.set_path(previous)
            return

        if len(self.m_importados) and not confirm(
                self, "Substituir registros importados",
                f"A tabela da planilha já possui {len(self.m_importados)} registro(s).\n"
                "Deseja substituí-los pelos da nova planilha? Edições feitas serão perdidas.",
                "Substituir"):
            self.sel_planilha.set_path(previous)
            return

        self._planilha_atual = path
        self.m_importados.set_items(result.registros)
        info = f"{plural(len(result.registros), 'registro carregado', 'registros carregados')} da aba '{result.planilha}'."
        if result.duplicados:
            info += f" {plural(result.duplicados, 'duplicado ignorado', 'duplicados ignorados')}."
        self.lbl_planilha.setText(info)
        self.ctx.notify(f"Planilha importada: {Path(path).name}")
        if result.avisos:
            show_warning(
                self, "Algumas linhas foram ignoradas",
                f"{plural(len(result.avisos), 'linha foi ignorada', 'linhas foram ignoradas')} por conter dados inválidos.",
                "\n".join(result.avisos))

    # ------------------------------------------------------------ consolidação
    def consolidado(self) -> list[Registro]:
        return combinar_registros(
            self.m_matriculas.items(), self.m_periodos.items(), self.m_importados.items())

    def _refresh_consolidado(self) -> None:
        registros = self.consolidado()
        self.m_consolidado.set_items(registros)
        if registros:
            self.lbl_consolidado.setText(f"{plural(len(registros), 'registro será enviado', 'registros serão enviados')} ao script.")
        elif len(self.m_matriculas) or len(self.m_periodos):
            self.lbl_consolidado.setText(
                "Para gerar registros é preciso ao menos uma matrícula e um período de anos.")
        else:
            self.lbl_consolidado.setText("")

    # ----------------------------------------------------------------- execução
    @guarded
    def _on_start(self) -> None:
        servidores = validate_directory(self.ctx.get_servidores(), "Diretório padrão (Servidores)")
        registros = self.consolidado()
        if not registros:
            raise ValidationError(
                "Informe ao menos uma matrícula e um ano válido (manualmente ou por planilha) "
                "antes de executar.")
        pasta_txt = self.sel_pasta.path()
        pasta = validate_directory(pasta_txt, "Pasta específica") if pasta_txt else None
        launch = resolve_launch(self.ctx.settings, self.spec.key)

        args = build_registros_args(servidores, registros, pasta)
        self.run_panel.log.append("info", f"Iniciando '{self.spec.title}' com {len(registros)} registro(s).")
        self.run_panel.execute(launch, args)
