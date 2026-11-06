"""Contas de aproveitamento conferidas à mão contra os quadros da LPUOS e do PDE."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from domain.legislacao_sp import QUADRO_3, extrair_pa, identificar_macroarea_fp, normalizar_zona, taxa_permeabilidade
from domain.zoning_rules import ZONING_DATABASE, obter_parametros_zoneamento
from services.aproveitamento import (
    EHIS,
    EntradaAproveitamento,
    calcular_aproveitamento,
    quota_ambiental_minima,
    taxa_ocupacao_tabela,
)


def calc(**kw):
    base = dict(area_terreno_m2=1000.0, zona="ZM", pa="PA 6")
    base.update(kw)
    return calcular_aproveitamento(EntradaAproveitamento(**base))


class TestTabelas(unittest.TestCase):
    def test_normalizacao_nao_confunde_zonas_parecidas(self):
        casos = {"ZEUPa": "ZEUPa", "ZEUPA": "ZEUPa", "ZEUP (b)": "ZEUP", "ZEIS 1": "ZEIS-1", "ZM-a": "ZMa",
                 "ZCa": "ZCa", "ZC-ZEIS": "ZC-ZEIS", "ZCORa": "ZCORa", "ZOE": None, "": None}
        for bruto, esperado in casos.items():
            self.assertEqual(normalizar_zona(bruto), esperado, bruto)

    def test_zoning_rules_usa_valores_do_quadro_3(self):
        self.assertEqual(obter_parametros_zoneamento("ZEUPa").ca_maximo, 1)
        self.assertEqual(obter_parametros_zoneamento("ZCa").ca_maximo, 1)
        self.assertEqual(obter_parametros_zoneamento("ZEPAM").ca_maximo, 0.1)
        self.assertEqual(obter_parametros_zoneamento("ZCOR-2").gabarito_altura_max_m, 10)
        self.assertEqual(obter_parametros_zoneamento("ZPI-2").taxa_ocupacao_max, 0.5)
        self.assertIsNone(obter_parametros_zoneamento("ZEIS-1").gabarito_altura_max_m)
        self.assertEqual(len(ZONING_DATABASE), len(QUADRO_3) - 1)  # AVP-1 não tem índices

    def test_extrair_pa(self):
        self.assertEqual(extrair_pa("PA 6 (Perímetro de Qualificação)"), "PA 6")
        self.assertEqual(extrair_pa("PA-06"), "PA 6")
        self.assertEqual(extrair_pa("PA\xa013"), "PA 13")
        self.assertIsNone(extrair_pa("PA 14"))
        self.assertIsNone(extrair_pa("Empresa"))

    def test_macroarea_para_quadro_6(self):
        self.assertEqual(identificar_macroarea_fp("Macroárea de Urbanização Consolidada"), "Urbanização Consolidada")
        self.assertEqual(identificar_macroarea_fp("Macroárea de Qualificação da Urbanização"), "Qualificação Urbana")
        self.assertEqual(
            identificar_macroarea_fp("Macroárea de Redução da Vulnerabilidade Urbana e Recuperação Ambiental"),
            "Redução da Vulnerabilidade Urbana e Recuperação Ambiental",
        )
        self.assertEqual(identificar_macroarea_fp("Estruturação Metropolitana - Arco Tietê"), "MEM - Arco Tietê")
        self.assertIsNone(identificar_macroarea_fp("Macroárea de Estruturação Metropolitana"))


class TestLimites500m2(unittest.TestCase):
    def test_exatamente_500_m2_muda_to_mas_nao_tp(self):
        zm = QUADRO_3["ZM"]
        self.assertEqual(taxa_ocupacao_tabela(zm, 499.99), 0.85)
        self.assertEqual(taxa_ocupacao_tabela(zm, 500), 0.70)
        self.assertEqual(taxa_permeabilidade("ZM", "PA 6", 500), 0.15)
        self.assertEqual(taxa_permeabilidade("ZM", "PA 6", 500.01), 0.20)

    def test_nota_a_tp_fixa_e_pa13(self):
        self.assertEqual(taxa_permeabilidade("ZEPAM", "PA 1", 100), 0.90)
        self.assertEqual(taxa_permeabilidade("ZER-1", None, 2000), 0.30)
        self.assertIsNone(taxa_permeabilidade("ZM", "PA 13", 2000))

    def test_quota_ambiental_por_faixa(self):
        self.assertIsNone(quota_ambiental_minima("PA 1", 500))
        self.assertEqual(quota_ambiental_minima("PA 1", 1000), 0.45)
        self.assertEqual(quota_ambiental_minima("PA 1", 2500), 0.60)
        self.assertEqual(quota_ambiental_minima("PA 1", 10001), 1.00)


class TestContas(unittest.TestCase):
    def test_caso_planilha_zm_pa6_menor_500(self):
        r = calc(area_terreno_m2=400.0)
        self.assertEqual(r.to_aplicada, 0.85)
        self.assertEqual(r.tp_aplicada, 0.15)
        self.assertEqual(r.ca_basico, 1)
        self.assertEqual(r.ca_final, 2)
        self.assertEqual(r.gabarito_m, 28)
        self.assertAlmostEqual(r.projecao_max_m2, 340)
        self.assertAlmostEqual(r.computavel_maxima_m2, 800)

    def test_ehis_e_cota_de_solidariedade_em_zm(self):
        self.assertEqual(calc(modalidade=EHIS).ca_final, 3)
        self.assertAlmostEqual(calc(modalidade=EHIS, cota_solidariedade=True).ca_final, 3.6)

    def test_nota_b_reduz_to_em_lote_pequeno_pa10(self):
        r = calc(area_terreno_m2=400.0, pa="PA 10")
        self.assertAlmostEqual(r.to_aplicada, 0.80)
        self.assertTrue(any("nota b" in a for a in r.alertas))

    def test_notas_f_g_h_em_lote_pequeno_de_zeis(self):
        self.assertEqual(calc(zona="ZEIS-2", area_terreno_m2=999).ca_maximo, 2)
        self.assertEqual(calc(zona="ZEIS-2", area_terreno_m2=1000).ca_maximo, 4)
        self.assertEqual(calc(zona="ZEIS-3", area_terreno_m2=499).ca_maximo, 2)
        self.assertEqual(calc(zona="ZEIS-3", area_terreno_m2=500).ca_maximo, 4)
        self.assertEqual(calc(zona="ZEIS-4", area_terreno_m2=999).ca_maximo, 1)

    def test_eixos_ativados(self):
        self.assertEqual(calc(zona="ZEUP").ca_final, 2)
        self.assertEqual(calc(zona="ZEUP", eixo_ativado=True).ca_final, 4)
        zem = calc(zona="ZEM", eixo_ativado=True)
        self.assertEqual(zem.ca_final, 4)
        self.assertIsNone(zem.gabarito_m)

    def test_outorga_formula_do_art_117(self):
        # C = (1000/4000) × 3000 × 0,8 × 0,7 = 420; adicional = 4000 − 1000 = 3000; total = 1.260.000
        r = calc(zona="ZEU", valor_m2_quadro14=3000.0, fs=0.8, linha_quadro_6="Urbanização Consolidada")
        self.assertAlmostEqual(r.contrapartida_m2, 420)
        self.assertAlmostEqual(r.adicional_a_pagar_m2, 3000)
        self.assertAlmostEqual(r.outorga_total, 1260000)

    def test_fp_2_em_zem_e_fp_nr_diferente(self):
        self.assertEqual(calc(zona="ZEM", valor_m2_quadro14=1000.0, linha_quadro_6="Urbanização Consolidada").fp, 2)
        r = calc(valor_m2_quadro14=1000.0, linha_quadro_6="Qualificação Urbana", uso_residencial=False)
        self.assertEqual(r.fp, 0.5)

    def test_outorga_sem_valor_v_fica_vazia_e_avisa(self):
        r = calc()
        self.assertIsNone(r.outorga_total)
        self.assertTrue(any("Outorga não calculada" in a for a in r.alertas))

    def test_doacao_em_eixo_mantem_potencial_e_isenta_outorga(self):
        # 1000 m² em ZEU com 100 m² doados: potencial sobre 1000; ocupação sobre 900; isento (4−1) × 100 = 300
        r = calc(zona="ZEU", area_doacao_m2=100.0)
        self.assertAlmostEqual(r.computavel_maxima_m2, 4000)
        self.assertAlmostEqual(r.projecao_max_m2, 0.7 * 900)
        self.assertAlmostEqual(r.adicional_a_pagar_m2, 2700)

    def test_doacao_fora_do_eixo_usa_remanescente_e_avisa(self):
        r = calc(zona="ZM", area_doacao_m2=100.0)
        self.assertAlmostEqual(r.computavel_maxima_m2, 1800)
        self.assertTrue(any("fora de zona de eixo" in a for a in r.alertas))

    def test_cota_parte_art_79(self):
        self.assertEqual(calc(zona="ZEU").unidades_minimas, 50)         # 1000 / 20
        self.assertEqual(calc(zona="ZEU", ca_utilizado=2.0).unidades_minimas, 25)
        self.assertEqual(calc(zona="ZEUa").unidades_minimas, 25)        # 1000 / 40
        self.assertIsNone(calc(zona="ZM").unidades_minimas)

    def test_limite_59_por_cento(self):
        r = calc(zona="ZM")
        self.assertAlmostEqual(r.area_total_max_m2, 2000 / 0.41)
        self.assertAlmostEqual(r.nao_computavel_max_m2 / r.area_total_max_m2, 0.59)

    def test_fachada_ativa_por_zona(self):
        self.assertAlmostEqual(calc(zona="ZCa").fachada_ativa_max_m2, 500)
        self.assertAlmostEqual(calc(zona="ZEUP").fachada_ativa_max_m2, 500)
        self.assertAlmostEqual(calc(zona="ZM").fachada_ativa_max_m2, 200)

    def _projecao_util(self, r):
        return [l.valor for l in r.memoria if l.item == "Projeção útil por pavimento"][0]

    def test_ate_10_m_nao_ha_recuo_lateral(self):
        # ZM, 20 × 50 m: 2000 / 700 = 3 pav = 9 m, então recuo só de frente: 20 × 45 = 900 > T.O. 700
        r = calc(testada_m=20.0, profundidade_m=50.0)
        self.assertAlmostEqual(self._projecao_util(r), 700)
        self.assertEqual(r.pavimentos_necessarios, 3)
        self.assertEqual(r.pavimentos_max_gabarito, 9)

    def test_acima_de_10_m_recuo_reduz_a_projecao(self):
        # ZEU, 20 × 50 m: 4000 / 700 = 6 pav = 18 m; (20 − 6) × (50 − 0 − 3) = 658; 4000 / 658 → 7 pav
        r = calc(zona="ZEU", testada_m=20.0, profundidade_m=50.0)
        self.assertAlmostEqual(self._projecao_util(r), 658)
        self.assertEqual(r.pavimentos_necessarios, 7)
        self.assertIsNone(r.pavimentos_max_gabarito)

    def test_gabarito_limita_o_ca(self):
        # ZM EHIS +20%, 12 × 25 m = 300 m²: C.A. 3,6; (12 − 6) × (25 − 5 − 3) = 102; 28 / 3 = 9 pav → C.A. 3,06
        r = calc(area_terreno_m2=300.0, testada_m=12.0, profundidade_m=25.0, modalidade=EHIS, cota_solidariedade=True)
        self.assertAlmostEqual(r.ca_atingivel_gabarito, 9 * 102 / 300)
        self.assertTrue(any("gabarito de 28 m" in a for a in r.alertas))

    def test_cota_solidariedade_obrigatoria_acima_de_20_mil(self):
        r = calc(zona="ZEU", area_terreno_m2=6000.0)
        self.assertTrue(any("cota de solidariedade é obrigatória" in a for a in r.alertas))

    def test_entradas_invalidas(self):
        with self.assertRaises(ValueError):
            calc(zona="ZOE")
        with self.assertRaises(ValueError):
            calc(zona="AVP-1")
        with self.assertRaises(ValueError):
            calc(area_terreno_m2=0)
        with self.assertRaises(ValueError):
            calc(area_doacao_m2=2000.0)


if __name__ == "__main__":
    unittest.main()
