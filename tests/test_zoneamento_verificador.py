"""Testes da confirmação de zona pelo polígono do lote (sem rede: feições simuladas)."""

import unittest

from shapely.geometry import box, mapping

from config import MAPAS_ZONEAMENTO
from domain.legislacao_sp import QUADRO_3
from services.zoneamento_verificador import (
    STATUS_CONFIRMADA,
    STATUS_DIVIDIDA,
    STATUS_NAO_CONFIRMADA,
    analisar_mapas,
)

VIGENTE, CONTESTADO, HISTORICO = (m["camada"] for m in MAPAS_ZONEAMENTO)
LOTE = box(0, 0, 20, 50)  # 1.000 m²


def _zona(codigo, geometria):
    return {"type": "Feature", "properties": {"cd_zoneamento_perimetro": codigo,
                                              "tx_zoneamento_perimetro": f"Zona {codigo}"},
            "geometry": mapping(geometria)}


class TestConfirmacaoZona(unittest.TestCase):
    def test_lote_inteiro_em_uma_zona_e_confirmado(self):
        r = analisar_mapas(LOTE, {VIGENTE: ([_zona("ZM", box(-100, -100, 100, 100))], True)})
        self.assertEqual(r.zona, "ZM")
        self.assertEqual(r.status, STATUS_CONFIRMADA)
        self.assertAlmostEqual(r.percentual_zona, 100.0)
        self.assertIn(r.zona, QUADRO_3)
        self.assertEqual(r.lei_referencia, "Lei 18.081/2024")

    def test_lote_dividido_mostra_percentuais_e_usa_a_predominante(self):
        feicoes = [_zona("ZEU", box(-10, -10, 30, 35)), _zona("ZM", box(-10, 35, 30, 60))]
        r = analisar_mapas(LOTE, {VIGENTE: (feicoes, True)})
        self.assertEqual(r.zona, "ZEU")
        self.assertEqual(r.status, STATUS_DIVIDIDA)
        self.assertAlmostEqual(r.percentual_zona, 70.0)
        self.assertTrue(any("ZEU (70.0%)" in a and "ZM (30.0%)" in a for a in r.alertas))

    def test_mapa_contestado_e_original_viram_avisos_sem_trocar_a_zona(self):
        r = analisar_mapas(LOTE, {
            VIGENTE: ([_zona("ZC", box(-100, -100, 100, 100))], True),
            CONTESTADO: ([_zona("ZEU", box(-100, -100, 100, 100))], True),
            HISTORICO: ([_zona("ZM", box(-100, -100, 100, 100))], True),
        })
        self.assertEqual(r.zona, "ZC")
        self.assertEqual(r.status, STATUS_CONFIRMADA)
        self.assertTrue(any("18.177" in a and "ZEU" in a and "inconstitucional" in a for a in r.alertas))
        self.assertTrue(any("mudou na revisão de 2024" in a and "ZM" in a for a in r.alertas))

    def test_lote_quase_todo_em_praca_nao_e_confirmado(self):
        feicoes = [_zona("PRAÇA/CANTEIRO", box(-10, -10, 30, 45)), _zona("ZEU", box(-10, 45, 30, 60))]
        r = analisar_mapas(LOTE, {VIGENTE: (feicoes, True)})
        self.assertEqual(r.zona, "ZEU")
        self.assertEqual(r.status, STATUS_NAO_CONFIRMADA)
        self.assertTrue(any("não pode ser confirmada" in a for a in r.alertas))

    def test_mapa_vigente_fora_do_ar_usa_outro_sem_confirmar(self):
        r = analisar_mapas(LOTE, {
            VIGENTE: ([], False),
            HISTORICO: ([_zona("ZM", box(-100, -100, 100, 100))], True),
        })
        self.assertEqual(r.zona, "ZM")
        self.assertEqual(r.status, STATUS_NAO_CONFIRMADA)
        self.assertTrue(any("não respondeu" in a for a in r.alertas))

    def test_nenhum_mapa_respondeu(self):
        r = analisar_mapas(LOTE, {})
        self.assertIsNone(r.zona)
        self.assertEqual(r.status, STATUS_NAO_CONFIRMADA)

    def test_siglas_com_notas_e_variacoes_sao_normalizadas(self):
        r = analisar_mapas(LOTE, {VIGENTE: ([_zona("ZEIS 1", box(-100, -100, 100, 100))], True)})
        self.assertEqual(r.zona, "ZEIS-1")


if __name__ == "__main__":
    unittest.main()
