# AutoArquivo — Painel de Automações de RH

Interface desktop (PySide6) que centraliza as automações **Ficha**, **Faltas**, **Licenças** e **Férias**.

## Estrutura

```
AutoArquivo/
├── iniciar.bat              # ativa a .venv (cria se não existir) e abre o painel
├── requirements.txt
├── README.md
├── src/
│   ├── main.py              # ponto de entrada
│   └── autoarquivo/
│       ├── config.py        # módulos, caminhos padrão dos scripts, Settings (JSON)
│       ├── validators.py    # matrícula, anos, nomes, pastas/arquivos
│       ├── models.py        # Registro, Periodo, Nome, combinar_registros()
│       ├── table_model.py   # ItemTableModel (modelo genérico, sem duplicatas)
│       ├── spreadsheet.py   # leitura/interpretação de planilhas (openpyxl)
│       ├── commands.py      # convenção de argumentos enviados aos scripts
│       ├── launch.py        # escolha do interpretador Python e do script
│       ├── runner.py        # ScriptRunner (QProcess: stdout/stderr, cancelar, código)
│       └── ui/
│           ├── main_window.py   # navegação lateral + diretório Servidores
│           ├── registros_page.py# página compartilhada Ficha/Faltas
│           ├── ferias_page.py, licencas_page.py
│           ├── run_panel.py     # iniciar/cancelar/progresso/log
│           ├── widgets.py, dialogs.py, icons.py, styles.py, settings_dialog.py
└── tests/test_core.py
```

## Instalação

1. Python 3.10+ instalado.
2. Dê dois cliques em `iniciar.bat`: ele cria a `.venv` e instala as dependências na primeira vez.

Manualmente:

```bat
py -3 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Execução

`iniciar.bat` ou, com a `.venv` ativa, `python src\main.py`.

## Como os scripts são chamados

Cada execução roda `python <script> <argumentos>` via `QProcess`, com a pasta do script como diretório de trabalho,
`PYTHONUNBUFFERED=1` e `PYTHONIOENCODING=utf-8`. Os argumentos são passados como lista (sem shell), então o JSON chega intacto em `sys.argv`.

**Ficha** e **Faltas** (mesmo padrão):

```
python main.py --servidores "D:\RH\Servidores" --registros "[{\"matricula\":\"1234\",\"inicio\":2017,\"fim\":2019}]" [--pasta "D:\Documentos"]
```

* `--registros`: JSON com **todos** os registros consolidados (matrícula normalizada, `inicio`, `fim`; ano único ⇒ `inicio == fim`).
* A entrada manual gera o produto *matrículas × períodos*; a ele se somam os registros da planilha. Duplicatas são removidas.
* `--pasta` é omitido quando não informado.

**Férias**:

```
python main.py --nomes "[\"João Silva\",\"Maria Souza\"]" --saida "D:\RH\Resultado"
```

Exemplo mínimo para o lado do script:

```python
import argparse, json
p = argparse.ArgumentParser()
p.add_argument("--servidores", required=True)
p.add_argument("--registros", required=True, type=json.loads)
p.add_argument("--pasta")
args = p.parse_args()
```

## Configuração dos scripts e do Python

Padrão por convenção (pastas **irmãs** de `AutoArquivo`, sem nome de usuário no código):

```
Documents\AutoFicha\src\main.py    Documents\AutoFaltas\src\main.py    Documents\AutoFérias\src\main.py
```

Tudo pode ser alterado em **Configurações** (menu lateral). Interpretador: o configurado → `.venv` do projeto do script
(ex.: `AutoFicha\.venv`) → `python` do PATH → o Python do próprio painel.
As configurações ficam em `%APPDATA%\AutoArquivo\settings.json`; o log técnico em `%APPDATA%\AutoArquivo\autoarquivo.log`.

## Planilhas

Cabeçalhos tolerantes (acentos/caixa/pontuação ignorados): `Matrícula`, `Nº Matrícula`, `Ano inicial`, `Ano_Final`, `Início`, `Fim`, ou uma única coluna `Ano`.
Férias/Licenças: `Nome`, `Nome completo`, `Servidor`... Se houver colunas ambíguas, a leitura é recusada com mensagem explicando o motivo.
Formato suportado: `.xlsx` / `.xlsm`.

## Novos módulos

Adicione um `ModuleSpec` em `config.MODULES`, uma função `build_*_args` em `commands.py` e registre a página em `PAGE_FACTORIES` (`ui/main_window.py`).

## Testes

`python -m unittest discover -s tests` (núcleo, sem interface).
