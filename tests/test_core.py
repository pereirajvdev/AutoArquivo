"""Testes do núcleo (sem Qt). Execute: python -m unittest discover -s tests"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from openpyxl import Workbook  # noqa: E402

from autoarquivo import commands, spreadsheet  # noqa: E402
from autoarquivo.models import Periodo, Registro, combinar_registros  # noqa: E402
from autoarquivo.validators import (  # noqa: E402
    ValidationError, name_key, normalize_matricula, parse_matriculas, parse_period, parse_year)


def make_xlsx(path, rows):
    wb = Workbook()
    ws = wb.active
    for r in rows:
        ws.append(r)
    wb.save(path)


class ValidatorTests(unittest.TestCase):
    def test_matricula(self):
        self.assertEqual(normalize_matricula("1.234"), "1234")
        self.assertEqual(normalize_matricula(" 1234 "), "1234")
        self.assertEqual(normalize_matricula(1234.0), "1234")
        self.assertEqual(normalize_matricula(1234), "1234")
        for bad in ("", "abc", "12a4", None, 12.5):
            with self.assertRaises(ValidationError):
                normalize_matricula(bad)

    def test_parse_matriculas(self):
        self.assertEqual(parse_matriculas("1.234, 1234; 55 66"), ["1234", "55", "66"])
        with self.assertRaises(ValidationError):
            parse_matriculas("12 xx")

    def test_years(self):
        self.assertEqual(parse_year("2019"), 2019)
        self.assertEqual(parse_period("2019", ""), (2019, 2019))
        self.assertEqual(parse_period(2017.0, 2019.0), (2017, 2019))
        for a, b in (("2020", "2019"), ("19", ""), ("abcd", ""), ("", "2019"), ("1800", "")):
            with self.assertRaises(ValidationError):
                parse_period(a, b)

    def test_name_key(self):
        self.assertEqual(name_key("  João   SILVA "), name_key("joao silva"))


class ModelTests(unittest.TestCase):
    def test_combinar(self):
        regs = combinar_registros(["1", "2"], [Periodo(2017, 2018)], [Registro("1", 2017, 2018), Registro("3", 2020, 2020)])
        self.assertEqual([r.chave for r in regs], [("1", 2017, 2018), ("2", 2017, 2018), ("3", 2020, 2020)])
        self.assertEqual(combinar_registros([], [Periodo(2017, 2018)], []), [])


class CommandTests(unittest.TestCase):
    def test_registros_args(self):
        regs = [Registro("1234", 2017, 2019)]
        args = commands.build_registros_args(Path("D:/RH/Servidores"), regs)
        self.assertEqual(args[0], "--servidores")
        self.assertNotIn("--pasta", args)
        self.assertEqual(json.loads(args[3]), [{"matricula": "1234", "inicio": 2017, "fim": 2019}])
        self.assertEqual(args[3], '[{"matricula":"1234","inicio":2017,"fim":2019}]')
        self.assertEqual(commands.build_registros_args(Path("a"), regs, Path("b"))[-2:], ["--pasta", str(Path("b"))])

    def test_ferias_args(self):
        args = commands.build_ferias_args(["João Silva", "Maria Souza"], Path("out"))
        self.assertEqual(args[0], "--nomes")
        self.assertEqual(args[1], '["João Silva","Maria Souza"]')
        self.assertEqual(args[2:], ["--saida", "out"])


class SpreadsheetTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_registros_variacoes_de_cabecalho(self):
        f = self.dir / "a.xlsx"
        make_xlsx(f, [["Relatório RH"], [], ["Nº Matrícula", "ANO INICIAL", "Ano_Final", "Obs"],
                      ["1.234", 2017, 2019, "x"], [1234, 2017, 2019, "dup"], [55.0, "2020", None, ""],
                      ["abc", 2020, 2020, ""], [None, None, None, None], ["77", 2021, 2019, ""]])
        res = spreadsheet.read_registros(f)
        self.assertEqual([r.chave for r in res.registros], [("1234", 2017, 2019), ("55", 2020, 2020)])
        self.assertEqual(res.duplicados, 1)
        self.assertEqual(len(res.avisos), 2)

    def test_registros_coluna_ano_unica(self):
        f = self.dir / "b.xlsx"
        make_xlsx(f, [["matricula", "ano"], [10, 2018]])
        self.assertEqual(spreadsheet.read_registros(f).registros, [Registro("10", 2018, 2018)])

    def test_registros_sem_colunas(self):
        f = self.dir / "c.xlsx"
        make_xlsx(f, [["Foo", "Bar"], [1, 2]])
        with self.assertRaises(spreadsheet.SpreadsheetError):
            spreadsheet.read_registros(f)

    def test_registros_ambiguo(self):
        f = self.dir / "d.xlsx"
        make_xlsx(f, [["Matrícula", "Mat", "Ano inicial", "Ano final"], [1, 1, 2017, 2018]])
        with self.assertRaises(spreadsheet.SpreadsheetError):
            spreadsheet.read_registros(f)

    def test_arquivo_invalido(self):
        with self.assertRaises(spreadsheet.SpreadsheetError):
            spreadsheet.read_registros(self.dir / "nao_existe.xlsx")
        bad = self.dir / "ruim.xlsx"
        bad.write_text("não sou excel")
        with self.assertRaises(spreadsheet.SpreadsheetError):
            spreadsheet.read_registros(bad)
        old = self.dir / "velho.xls"
        old.write_bytes(b"x")
        with self.assertRaises(spreadsheet.SpreadsheetError):
            spreadsheet.read_registros(old)

    def test_nomes(self):
        f = self.dir / "n.xlsx"
        make_xlsx(f, [["Matrícula", "Nome", "Nome da Mãe"], [1, "João  Silva", "Ana"], [2, "joao silva", "Bia"], [3, "Maria Souza", "C"]])
        res = spreadsheet.read_nomes(f)
        self.assertEqual(res.nomes, ["João Silva", "Maria Souza"])
        self.assertEqual(res.duplicados, 1)

    def test_nomes_sem_coluna(self):
        f = self.dir / "n2.xlsx"
        make_xlsx(f, [["A", "B"], [1, 2]])
        with self.assertRaises(spreadsheet.SpreadsheetError):
            spreadsheet.read_nomes(f)

    def test_preview(self):
        f = self.dir / "p.xlsx"
        make_xlsx(f, [["Nome", "Valor"], ["A", 1.0], ["B", 2.5]])
        pv = spreadsheet.read_preview(f)
        self.assertEqual(pv.headers, ["Nome", "Valor"])
        self.assertEqual(pv.rows, [["A", "1"], ["B", "2.5"]])


if __name__ == "__main__":
    unittest.main()
