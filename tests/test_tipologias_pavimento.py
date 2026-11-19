"""
Testes das Etapas 5/6 por tipologia: quantas unidades cabem por pavimento-tipo e a área de
cada tipologia, aplicadas à matriz do Quadro de Áreas.
"""

import unittest

from domain.viabilidade_models import TipologiaPavimento
from services.geosampa_client import LOTES_EXEMPLO_SP
from services.quadro_areas_engine import (
    aplicar_tipologias_aos_pavimentos,
    calcular_capacidade_pavimentos,
    calcular_quadro_areas,
    distribuir_areas_automaticas_por_terreno,
    limites_pavimento_tipo,
    maximo_unidades_por_pavimento,
    tipologias_padrao,
    validar_tipologias,
)
from services.spatial_analyzer import processar_terreno_completo
from services.viabilidade_bridge import calcular_indices_legais, extrair_entrada_geo

EX_VM_3_LOTES = "Vila Mariana · R. Dr. Pinto Ferraz, 285 a 299 · 3 lotes unificados"


def _indices():
    ex = LOTES_EXEMPLO_SP[EX_VM_3_LOTES]
    res = processar_terreno_completo(
        ex["features_utm"], zona_forcada="ZM", valores_territoriais_iniciais={"qualificacao_ambiental": "PA 6"}
    )
    return calcular_indices_legais(extrair_entrada_geo(res), modalidade="EHIS_COTA")


class TestTipologiasPorPavimento(unittest.TestCase):
    def setUp(self) -> None:
        self.indices = _indices()
        self.base = distribuir_areas_automaticas_por_terreno(self.indices, cota_terreno_m=790.0, qtd_pav_tipo=9)

    def test_aplica_unidades_e_area_de_cada_tipologia_por_faixa_de_pavimentos(self) -> None:
        tipologias = [
            TipologiaPavimento("HIS-2", "STUDIO", 24.5, 6),
            TipologiaPavimento("HIS-2", "1 DORM", 32.0, 2, pavimento_inicial=1, pavimento_final=4),
            TipologiaPavimento("R2V-1", "1 DORM", 30.0, 2, pavimento_inicial=5),
        ]
        pavs = aplicar_tipologias_aos_pavimentos(self.base, tipologias, pct_circ_comp=0.10, pct_circ_nao_comp=0.20)
        tipos = [p for p in pavs if p.tipo == "tipo"]
        # 1º ao 4º: 6 studios + 2 de 1 dorm em HIS-2; nenhum R2V-1
        self.assertEqual(tipos[0].unidades["u_his2"], 8)
        self.assertAlmostEqual(tipos[0].areas["c_his2"], 6 * 24.5 + 2 * 32.0, places=2)
        self.assertEqual(tipos[0].unidades["u_r2v1"], 0)
        # 5º em diante: só os studios em HIS-2 e 2 R2V-1
        self.assertEqual(tipos[4].unidades["u_his2"], 6)
        self.assertEqual(tipos[4].unidades["u_r2v1"], 2)
        self.assertAlmostEqual(tipos[4].areas["c_r2v1"], 60.0, places=2)
        # Circulação proporcional à área privativa do pavimento
        priv = 6 * 24.5 + 60.0
        self.assertAlmostEqual(tipos[4].areas["c_circ"], round(priv * 0.10, 2), places=2)
        self.assertAlmostEqual(tipos[4].areas["nc_circ"], round(priv * 0.20, 2), places=2)
        # Térreo não muda e a lista original não é alterada
        self.assertEqual(pavs[0].areas, self.base[0].areas)
        self.assertNotEqual(self.base[1].unidades["u_his2"], 8)

        quadro = calcular_quadro_areas(pavs, self.indices)
        self.assertEqual(quadro.subtotal_unidades["u_his2"], 4 * 8 + 5 * 6)
        self.assertEqual(quadro.subtotal_unidades["u_r2v1"], 5 * 2)
        self.assertEqual(quadro.verificacao_soma, 0.0)

    def test_maximo_por_pavimento_respeita_potencial_e_laje(self) -> None:
        limite_comp, limite_laje = limites_pavimento_tipo(self.indices, 9)
        self.assertGreater(limite_comp, 0)
        self.assertGreater(limite_laje, 0)
        maximo = maximo_unidades_por_pavimento(self.indices, 9, "HIS-2", 25.0, 0.14, 0.20)
        self.assertGreater(maximo, 0)
        # Com o máximo, o pavimento cabe; com uma unidade a mais, deixa de caber em algum limite
        for qtd, deve_caber in ((maximo, True), (maximo + 1, False)):
            pavs = aplicar_tipologias_aos_pavimentos(
                self.base, [TipologiaPavimento("HIS-2", "STUDIO", 25.0, qtd)], 0.14, 0.20
            )
            cap = calcular_capacidade_pavimentos(pavs, self.indices)
            self.assertEqual(len(cap), 9)
            self.assertEqual(cap[0].unidades, qtd)
            self.assertEqual(cap[0].atende, deve_caber, f"qtd={qtd}")

    def test_unidade_nao_computavel_so_limitada_pela_laje(self) -> None:
        comp = maximo_unidades_por_pavimento(self.indices, 9, "HIS-2", 25.0)
        nao_comp = maximo_unidades_por_pavimento(self.indices, 9, "HIS-2 (Cota Solid.)", 25.0)
        self.assertGreaterEqual(nao_comp, comp)

    def test_padrao_cabe_e_valida(self) -> None:
        padrao = tipologias_padrao(self.indices, 9)
        self.assertEqual(validar_tipologias(padrao, 9), [])
        pavs = aplicar_tipologias_aos_pavimentos(self.base, padrao)
        self.assertTrue(all(c.atende for c in calcular_capacidade_pavimentos(pavs, self.indices)))

    def test_validacao_aponta_erros(self) -> None:
        erros = validar_tipologias(
            [
                TipologiaPavimento("XYZ", "?", 25.0, 2),
                TipologiaPavimento("HIS-2", "A", 0.0, 2),
                TipologiaPavimento("HIS-2", "B", 25.0, 2, pavimento_inicial=3, pavimento_final=20),
            ],
            9,
        )
        self.assertEqual(len(erros), 3)


if __name__ == "__main__":
    unittest.main()


class TestCoresPorTipologiaNoExcel(unittest.TestCase):
    def test_colunas_e_linhas_de_cada_tipologia_tem_cor_propria(self) -> None:
        import re
        import zipfile
        from io import BytesIO

        from services.excel_exporter import CORES_TIPOLOGIA, estilo_tipologia, familia_tipologia, gerar_xlsx_bytes

        self.assertEqual(familia_tipologia("COMP. Terraço HIS-2"), familia_tipologia("HIS-2"))
        self.assertNotEqual(familia_tipologia("N.COMP. HIS-2 (Cota Solid.)"), familia_tipologia("HIS-2"))
        self.assertNotEqual(familia_tipologia("HIS-1"), familia_tipologia("HIS-2"))
        self.assertIsNone(familia_tipologia("Circulação"))
        cores = {forte for _, _, forte, _ in CORES_TIPOLOGIA}
        self.assertEqual(len(cores), len(CORES_TIPOLOGIA))  # uma cor por tipologia

        linhas = [
            ["QUADRO DE ÁREAS"],
            ["NÍVEL", "PAVIMENTO", "HIS-2", "R2V-1", "COMP. HIS-2", "COMP. Circulação"],
            [800.0, "1º Pavimento", 8, 2, 200.5, 30.25],
            ["", "SUBTOTAL", 8, 2, 200.5, 30.25],
            [],
            ["MIX DE TIPOLOGIAS"],
            ["CATEGORIA", "TIPOLOGIA", "ÁREA"],
            ["R2V-1", "STUDIO", 25.5],
        ]
        with zipfile.ZipFile(BytesIO(gerar_xlsx_bytes([("Q. ÁREAS", linhas)]))) as zf:
            xml = zf.read("xl/worksheets/sheet1.xml").decode()
        estilo = dict(re.findall(r'<c r="([A-Z]+\d+)" s="(\d+)"', xml))
        his2, r2v1 = familia_tipologia("HIS-2"), familia_tipologia("R2V-1")
        self.assertEqual(int(estilo["C2"]), estilo_tipologia(his2, "header"))
        self.assertEqual(int(estilo["D2"]), estilo_tipologia(r2v1, "header"))
        self.assertEqual(int(estilo["E2"]), estilo_tipologia(his2, "header"))
        self.assertEqual(int(estilo["E3"]), estilo_tipologia(his2, "num"))
        self.assertEqual(int(estilo["C4"]), estilo_tipologia(his2, "total"))
        self.assertLess(int(estilo["F3"]), 18)  # circulação não é tipologia: estilo padrão
        self.assertEqual(int(estilo["B8"]), estilo_tipologia(r2v1, "text"))  # linha do mix pela categoria
