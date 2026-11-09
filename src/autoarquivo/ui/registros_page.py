"""Página compartilhada por Ficha e Faltas (matrícula + anos).

Os dois módulos usam exatamente a mesma estrutura; só mudam o ``ModuleSpec``
(título, texto do botão e script de destino) recebido no construtor.

Quando ``spec.export_excel`` é verdadeiro (Ficha), o AutoFicha recebe
``--retorno <json temporário>`` e informa em quais pastas de servidores salvou
fichas. O cabeçalho mostra o estado do fluxo (``FichaState``) e o botão
"Gerar Excel das Fichas", que só é habilitado com um retorno válido e ao menos
uma pasta. Ao clicar, o FichaPDFToExcel roda UMA VEZ POR PASTA retornada (nunca
por varredura), em fila, reutilizando o mesmo painel de execução (log, progresso,
cancelamento e trava de execução simultânea). A falha de uma pasta não interrompe
as demais; ao final é exibido um resumo.
"""

from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QRegularExpression, Qt, QTimer
from PySide6.QtGui import QRegularExpressionValidator
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from ..commands import build_ficha_excel_args, build_registros_args
from ..config import FICHA_EXCEL_KEY, ModuleSpec
from ..ficha_flow import EXCEL_ENABLED_STATES, ExcelBatch, FichaState
from ..ficha_result import (
    FichaResult,
    FichaResultError,
    discard,
    new_return_file,
    read_ficha_result,
)
from ..launch import Launch, resolve_launch
from ..models import Periodo, Registro, combinar_registros
from ..runner import RunResult
from ..spreadsheet import SpreadsheetError, read_registros
from ..table_model import ItemTableModel
from ..validators import (
    ValidationError,
    parse_matriculas,
    parse_period,
    validate_directory,
)
from .base_page import AppContext, ModulePage, column_layout, guarded, scroll_column
from .dialogs import (
    confirm,
    edit_matricula,
    edit_periodo,
    edit_registro,
    show_error,
    show_info,
    show_warning,
)
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

log = logging.getLogger(__name__)

_REG_HEADERS = ["Matrícula", "Ano inicial", "Ano final"]

_TASK_FICHA = "ficha"
_TASK_EXCEL = "excel"
_EXCEL_TASK_NAME = "Gerar Excel das Fichas"


def _reg_row(r: Registro) -> tuple:
    return (r.matricula, r.inicio, r.fim)


class RegistrosPage(ModulePage):
    def __init__(self, spec: ModuleSpec, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(spec, ctx, parent)
        self._planilha_atual = ""

        # --- estado da etapa "Gerar Excel das Fichas" (só usado quando spec.export_excel)
        self.btn_excel: QPushButton | None = None
        self.lbl_estado: QLabel | None = None
        self._task = ""                        # etapa em execução: _TASK_FICHA | _TASK_EXCEL | ""
        self._busy = False                     # há um processo em andamento neste módulo
        self._closing = False                  # painel sendo fechado: ignora retornos tardios
        self._state = FichaState.AGUARDANDO
        self._state_detail = ""
        self._return_file: Path | None = None  # JSON temporário do AutoFicha (execução atual)
        self._pastas: list[Path] = []          # pastas validadas do último retorno
        self._batch: ExcelBatch | None = None  # fila do "Gerar Excel" em andamento
        self._excel_launch: Launch | None = None

        # --- dados (cada tabela impede duplicatas pelo seu próprio critério)
        self.m_matriculas = ItemTableModel(["Matrícula"], lambda m: (m,))
        self.m_periodos = ItemTableModel(["Ano inicial", "Ano final"], lambda p: (p.inicio, p.fim))
        self.m_importados = ItemTableModel(_REG_HEADERS, _reg_row, key=lambda r: r.chave)
        self.m_consolidado = ItemTableModel(_REG_HEADERS, _reg_row, key=lambda r: r.chave)

        self._build_ui()

        for model in (self.m_matriculas, self.m_periodos, self.m_importados):
            model.changed.connect(self._refresh_consolidado)
        self.run_panel.startRequested.connect(self._on_start)
        self.run_panel.runningChanged.connect(self._on_running_changed)
        self.run_panel.finished.connect(self._on_run_finished)
        self._refresh_consolidado()
        self._sync_ui()

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
        layout.addLayout(self._header_row())
        layout.addWidget(splitter, 1)

    def _header_row(self) -> QHBoxLayout:
        """Cabeçalho padrão; em Ficha, com o botão de exportação à direita."""
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(12)
        row.addWidget(self.make_header(), 1)
        if self.spec.export_excel:
            self.lbl_estado = QLabel()
            self.lbl_estado.setObjectName("chip")  # reaproveita o estilo do chip do painel de execução
            row.addWidget(self.lbl_estado, 0, Qt.AlignmentFlag.AlignVCenter)
            self.btn_excel = make_button(_EXCEL_TASK_NAME, "sheet")
            self.btn_excel.setEnabled(False)  # habilitado só com retorno válido do AutoFicha
            self.btn_excel.clicked.connect(self._on_excel)
            row.addWidget(self.btn_excel, 0, Qt.AlignmentFlag.AlignVCenter)
        return row

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

    # ----------------------------------------------------------------- ciclo de vida
    @property
    def is_running(self) -> bool:
        # Também vale entre duas pastas da fila, quando nenhum processo está ativo.
        return super().is_running or self._batch is not None

    def shutdown(self) -> None:
        self._closing = True
        self._batch = None
        discard(self._return_file)
        self._return_file = None
        super().shutdown()

    # ----------------------------------------------------------------- execução
    @guarded
    def _on_start(self) -> None:
        if self._batch is not None:
            raise ValidationError("A geração do Excel das fichas está em andamento. Aguarde o término.")
        servidores = validate_directory(self.ctx.get_servidores(), "Diretório padrão (Servidores)")
        registros = self.consolidado()
        if not registros:
            raise ValidationError(
                "Informe ao menos uma matrícula e um ano válido (manualmente ou por planilha) "
                "antes de executar.")
        pasta_txt = self.sel_pasta.path()
        pasta = validate_directory(pasta_txt, "Pasta específica") if pasta_txt else None
        launch = resolve_launch(self.ctx.settings, self.spec.key)

        if self.btn_excel is None:  # Faltas: fluxo inalterado
            args = build_registros_args(servidores, registros, pasta)
            self._task = _TASK_FICHA
            self.run_panel.log.append("info", f"Iniciando '{self.spec.title}' com {len(registros)} registro(s).")
            self.run_panel.execute(launch, args)
            return

        # Ficha: nova execução descarta o resultado anterior e bloqueia o botão até
        # que um novo retorno válido seja recebido.
        discard(self._return_file)
        self._return_file = None
        self._pastas = []
        try:
            retorno = new_return_file()
        except OSError as exc:
            raise ValidationError(f"Não foi possível criar o arquivo temporário de retorno:\n{exc}") from exc
        self._return_file = retorno

        args = build_registros_args(servidores, registros, pasta, retorno=retorno)
        self._task = _TASK_FICHA
        self._set_state(FichaState.PROCESSANDO)
        self.run_panel.log.append("info", f"Iniciando '{self.spec.title}' com {len(registros)} registro(s).")
        # quiet: o diálogo final depende do conteúdo do retorno, então é exibido por esta página.
        self.run_panel.execute(launch, args, quiet=True)

        if self._state is FichaState.PROCESSANDO and not self.run_panel.is_running:
            # O processo não iniciou e nenhum "finished" foi emitido (o RunPanel já avisou o erro).
            discard(self._return_file)
            self._return_file = None
            self._task = ""
            self._set_state(FichaState.ERRO, "Não foi possível iniciar o AutoFicha.")

    def _on_running_changed(self, running: bool) -> None:
        self._busy = running
        self._sync_ui()

    def _on_run_finished(self, result: RunResult) -> None:
        task, self._task = self._task, ""
        if self._closing:
            return
        if task == _TASK_FICHA and self.btn_excel is not None:
            self._on_ficha_finished(result)
        elif task == _TASK_EXCEL:
            self._on_excel_item_finished(result)

    # ------------------------------------------- etapa 1: retorno do AutoFicha
    def _on_ficha_finished(self, result: RunResult) -> None:
        retorno, self._return_file = self._return_file, None
        try:
            state, detail, pastas = self._avaliar_ficha(result, retorno)
        finally:
            discard(retorno)  # o arquivo temporário não sobrevive ao processamento, nem a exceções

        self._pastas = pastas
        self._set_state(state, detail)
        log_ = self.run_panel.log.append
        if state is FichaState.PRONTO:
            log_("info", f"{plural(len(pastas), 'pasta recebeu', 'pastas receberam')} fichas. "
                         f"'{_EXCEL_TASK_NAME}' está disponível no topo da página.")
        elif detail:
            log_("err" if state is FichaState.ERRO else "info", detail)

        QApplication.alert(self.window())
        if state is FichaState.PRONTO:
            show_info(self, "Automação concluída",
                      f"{plural(len(pastas), 'pasta recebeu', 'pastas receberam')} fichas.\n"
                      f"Use '{_EXCEL_TASK_NAME}' para gerar o Excel dessas pastas.")
        elif state is FichaState.SEM_FICHAS:
            show_warning(self, "Nenhuma ficha gerada", detail)
        elif result.status == "cancelled":
            show_warning(self, "Execução cancelada", detail)
        else:
            show_error(self, "Falha na automação", detail,
                       "Consulte a área de log para ver as mensagens do script (stderr).")

    def _avaliar_ficha(self, result: RunResult, retorno: Path | None) -> tuple[FichaState, str, list[Path]]:
        """Decide o estado a partir do código de saída E do JSON. Só devolve PRONTO com retorno válido."""
        parsed: FichaResult | None = None
        read_error = "O arquivo de retorno não foi criado."
        if retorno is not None:
            try:
                parsed = read_ficha_result(retorno)
            except FichaResultError as exc:
                read_error = str(exc)

        if parsed is not None:
            for falha in parsed.falhas:
                self.run_panel.log.append("err", f"Falha informada pelo AutoFicha: {falha}")

        if result.status == "cancelled":
            return FichaState.ERRO, "Execução cancelada pelo usuário.", []
        if result.status != "success":
            detail = result.message
            if parsed is not None and parsed.erro:
                detail += f"\nAutoFicha: {parsed.erro}"
            return FichaState.ERRO, detail, []
        if parsed is None:
            return FichaState.ERRO, (
                "O AutoFicha terminou, mas o retorno é inválido; "
                f"o botão '{_EXCEL_TASK_NAME}' permanece bloqueado.\n{read_error}"), []
        if not parsed.sucesso:
            return FichaState.ERRO, parsed.erro or "O AutoFicha informou falha no retorno.", []
        if not parsed.pastas:
            return FichaState.SEM_FICHAS, "O AutoFicha terminou, mas nenhuma ficha foi salva.", []
        return FichaState.PRONTO, "", list(parsed.pastas)

    # --------------------------------------------- etapa 2: Gerar Excel das Fichas
    @guarded
    def _on_excel(self) -> None:
        if self._busy or self._batch is not None:
            return  # nunca duas execuções simultâneas neste módulo
        if self._state not in EXCEL_ENABLED_STATES or not self._pastas:
            raise ValidationError("Execute o AutoFicha com sucesso (ao menos uma ficha salva) "
                                  "antes de gerar o Excel das fichas.")
        self._excel_launch = resolve_launch(self.ctx.settings, FICHA_EXCEL_KEY)
        self._batch = ExcelBatch(list(self._pastas))
        self._set_state(FichaState.GERANDO)
        self.run_panel.log.append(
            "info", f"Iniciando '{_EXCEL_TASK_NAME}' em {plural(len(self._pastas), 'pasta', 'pastas')}.")
        self._run_next_excel()

    def _run_next_excel(self) -> None:
        batch = self._batch
        if batch is None or self._closing:
            return
        try:
            self._advance_excel(batch)
        except Exception as exc:  # noqa: BLE001 - a fila nunca pode travar a interface
            log.exception("Erro inesperado na fila do Excel")
            self.run_panel.log.append("err", f"Erro inesperado: {exc}")
            self._end_batch(batch, forced_error=str(exc))

    def _advance_excel(self, batch: ExcelBatch) -> None:
        """Inicia a próxima pasta; falhas de validação/início passam direto para a seguinte."""
        while True:
            if batch.current is not None:
                return
            pasta = batch.begin_next()
            if pasta is None:
                self._end_batch(batch)
                return
            prefix = f"[{batch.position}/{batch.total}]"
            try:
                validate_directory(pasta, "Pasta das fichas")
            except ValidationError as exc:
                motivo = " ".join(str(exc).split())
                batch.finish_current(False, motivo)
                self.run_panel.log.append("err", f"{prefix} {motivo}")
                continue

            self.run_panel.log.append("info", f"{prefix} Gerando Excel: {pasta}")
            self._task = _TASK_EXCEL
            self.run_panel.execute(self._excel_launch, build_ficha_excel_args(pasta),
                                   _EXCEL_TASK_NAME, quiet=True)
            if batch.current is None:
                return  # um "finished" síncrono já tratou e agendou a próxima
            if self.run_panel.is_running:
                return  # segue; o "finished" chamará _on_excel_item_finished
            self._task = ""
            batch.finish_current(False, "Não foi possível iniciar a automação.")
            self.run_panel.log.append("err", f"{prefix} Não foi possível iniciar a automação: {pasta}")

    def _on_excel_item_finished(self, result: RunResult) -> None:
        batch = self._batch
        if batch is None or batch.current is None:
            return
        pasta = batch.current
        prefix = f"[{batch.position}/{batch.total}]"
        if result.status == "success":
            batch.finish_current(True)
            self.run_panel.log.append("ok", f"{prefix} Excel gerado: {pasta}")
        else:
            motivo = result.message
            batch.finish_current(False, motivo)
            self.run_panel.log.append("err", f"{prefix} Falha: {pasta} — {motivo}")
            if result.status == "cancelled":
                batch.cancel()  # o usuário pediu para parar: as pastas restantes não são iniciadas
        # Adiado para fora do slot do QProcess: evita reentrância ao iniciar o próximo processo.
        QTimer.singleShot(0, self._run_next_excel)

    def _end_batch(self, batch: ExcelBatch, forced_error: str = "") -> None:
        self._batch = None
        self._excel_launch = None
        state = FichaState.ERRO if forced_error else batch.final_state()
        summary = batch.summary()
        if forced_error:
            summary += f"\nErro inesperado: {forced_error}"
        self._set_state(state, summary)
        self.run_panel.log.append("ok" if state is FichaState.CONCLUIDO else "err",
                                  "Resumo — " + summary.replace("\n", " | "))
        QApplication.alert(self.window())
        details = batch.failure_details()
        if state is FichaState.CONCLUIDO:
            show_info(self, "Excel das fichas concluído", summary)
        elif state is FichaState.PARCIAL:
            show_warning(self, "Concluído parcialmente", summary, details)
        else:
            show_error(self, "Falha ao gerar o Excel das fichas", summary, details)

    # ---------------------------------------------------------------- estado/UI
    def _set_state(self, state: FichaState, detail: str = "") -> None:
        self._state = state
        self._state_detail = detail
        self._sync_ui()

    def _sync_ui(self) -> None:
        """Reflete estado + execução na interface (campos, chip e botão do Excel)."""
        locked = self._busy or self._batch is not None
        self.inputs.setEnabled(not locked)
        if self.btn_excel is None or self.lbl_estado is None:
            return
        self.lbl_estado.setText(self._state.label)
        set_prop(self.lbl_estado, "state", self._state.chip)
        self.lbl_estado.setToolTip(self._state_detail)
        self.btn_excel.setEnabled(not locked and self._state in EXCEL_ENABLED_STATES and bool(self._pastas))
        if locked:
            tip = "Aguarde o término da execução em andamento."
        elif self._pastas and self._state in EXCEL_ENABLED_STATES:
            tip = (f"Gera o Excel em {plural(len(self._pastas), 'pasta retornada', 'pastas retornadas')} "
                   "pelo AutoFicha.")
        else:
            tip = "Disponível após o AutoFicha salvar ao menos uma ficha."
        self.btn_excel.setToolTip(tip)
