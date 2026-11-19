"""
Confere os parâmetros legais do código com o texto oficial vigente, transcrito em
tests/fixtures/legislacao_sp_oficial.json (LPUOS Quadros 3 e 3A com a redação da Lei 18.081/2024,
art. 62 e art. 66 da LPUOS e art. 108 do COE), conferido em 19/11/2026 no Catálogo de Legislação
Municipal (legislacao.prefeitura.sp.gov.br).

Se um destes testes falhar, o código divergiu da lei: corrija o código, não o fixture. O fixture
só muda quando a própria lei mudar (registre a fonte e a data no campo "_fonte").
"""

import json
import pathlib
import re
import unittest

import domain.legislacao_sp as lei
from domain.tabelas_dados import QUADRO_2_RAW, QUADRO_3_RAW, QUADRO_4_RAW
from services.viabilidade_bridge import normalizar_zona as normalizar_zona_planilha
from services.viabilidade_bridge import parse_numero_tabela

OFICIAL = json.loads(
    (pathlib.Path(__file__).parent / "fixtures" / "legislacao_sp_oficial.json").read_text(encoding="utf-8")
)


def _num(texto):
    """'0,85' → 0.85 · '2 (d)' → 2.0 · 'NA' / '(k)' → None."""
    texto = str(texto).strip()
    if texto in ("NA", "") or texto.startswith("("):
        return None
    m = re.match(r"([\d,]+)", texto)
    return float(m.group(1).replace(",", ".")) if m else None


def _diferentes(a, b):
    return (a is None) != (b is None) or (a is not None and abs(a - b) > 1e-9)


class TestQuadro3(unittest.TestCase):
    """LPUOS, Quadro 3 — parâmetros de ocupação por zona (redação da Lei 18.081/2024)."""

    MAPA_CODIGO = {
        "ca_minimo": "ca_minimo", "ca_basico": "ca_basico", "ca_maximo": "ca_maximo",
        "to_lote_ate_500": "to_lote_menor_500", "to_lote_500_ou_mais": "to_lote_500_ou_mais",
        "gabarito_m": "gabarito_m", "recuo_frente": "recuo_frente_m",
        "recuo_lateral_fundo_ate_10m": "recuo_ate_10m", "recuo_lateral_fundo_acima_10m": "recuo_acima_10m",
        "cota_parte_m2": "cota_parte_m2",
    }
    MAPA_PLANILHA = {
        "ca_minimo": "ca_minimo", "ca_basico": "ca_basico", "ca_maximo": "ca_maximo",
        "to_lote_ate_500": "to_ate_500", "to_lote_500_ou_mais": "to_acima_500", "gabarito_m": "gabarito_m",
        "recuo_frente": "recuo_frente", "recuo_lateral_fundo_ate_10m": "recuo_ate_10m",
        "recuo_lateral_fundo_acima_10m": "recuo_acima_10m", "cota_parte_m2": "cota_parte",
    }

    def test_legislacao_sp_tem_as_mesmas_zonas(self):
        self.assertEqual(set(lei.QUADRO_3), set(OFICIAL["quadro_3"]))

    def test_legislacao_sp_igual_ao_quadro_oficial(self):
        erros = []
        for zona, campos in OFICIAL["quadro_3"].items():
            params = lei.QUADRO_3[zona]
            for campo_oficial, campo_codigo in self.MAPA_CODIGO.items():
                oficial = _num(campos[campo_oficial])
                if campo_codigo.startswith("recuo") and oficial is None:
                    oficial = 0.0  # no código, recuo 0 = NA
                if _diferentes(getattr(params, campo_codigo), oficial):
                    erros.append(f"{zona}.{campo_codigo}: código={getattr(params, campo_codigo)} lei={campos[campo_oficial]!r}")
        self.assertEqual(erros, [])

    def test_tabela_da_planilha_igual_ao_quadro_oficial(self):
        planilha = {normalizar_zona_planilha(k) or k: v for k, v in QUADRO_3_RAW.items()}
        erros = []
        for zona, campos in OFICIAL["quadro_3"].items():
            self.assertIn(zona, planilha, f"zona {zona} ausente em tabelas_dados.QUADRO_3_RAW")
            for campo_oficial, campo_planilha in self.MAPA_PLANILHA.items():
                valor, _ = parse_numero_tabela(planilha[zona].get(campo_planilha))
                if _diferentes(valor, _num(campos[campo_oficial])):
                    erros.append(f"{zona}.{campo_planilha}: planilha={planilha[zona].get(campo_planilha)!r} lei={campos[campo_oficial]!r}")
        self.assertEqual(erros, [])

    def test_colunas_de_ocupacao_do_quadro_2_da_planilha_seguem_o_quadro_3(self):
        erros = []
        for chave, linha in QUADRO_2_RAW.items():
            zona = normalizar_zona_planilha(chave) or chave
            for campo_oficial, campo_planilha in self.MAPA_PLANILHA.items():
                if campo_planilha == "ca_maximo":
                    continue  # no Quadro 2 o C.A. máximo é o de EHIS/EHMP (Decreto HIS), não o do Quadro 3
                valor, _ = parse_numero_tabela(linha.get(campo_planilha))
                if _diferentes(valor, _num(OFICIAL["quadro_3"][zona][campo_oficial])):
                    erros.append(f"{zona}.{campo_planilha}")
        self.assertEqual(erros, [])

    def test_zpi_2_usa_a_alteracao_I_da_lei_18081(self):
        self.assertEqual(lei.QUADRO_3["ZPI-2"].to_lote_500_ou_mais, 0.5)


class TestQuadro3A(unittest.TestCase):
    """LPUOS, Quadro 3A — taxa de permeabilidade e Quota Ambiental mínima por PA."""

    def test_taxas_e_pontuacao_por_pa(self):
        for pa, valores in OFICIAL["quadro_3a"].items():
            menor, maior, faixas = lei.QUADRO_3A[pa]
            self.assertEqual((menor, maior), (_num(valores[0]), _num(valores[1])), pa)
            self.assertEqual(tuple(faixas), tuple(_num(v) for v in valores[2:]), pa)

    def test_nota_a_taxa_fixa_por_zona(self):
        for prefixo, taxa in OFICIAL["quadro_3a_nota_a_tp_fixa"].items():
            zonas = [z for z in lei.QUADRO_3 if z == prefixo or z.startswith(prefixo + "-") or
                     (z.startswith(prefixo) and z[len(prefixo):] in ("a", "r"))]
            if prefixo == "ZPDS":
                zonas = ["ZPDS"]
            for zona in zonas:
                self.assertEqual(lei.TP_FIXA_POR_ZONA.get(zona), _num(taxa), zona)

    def test_planilha_quadro_4_igual_ao_3a(self):
        for chave, linha in QUADRO_4_RAW.items():
            pa = lei.extrair_pa(chave)
            if pa not in OFICIAL["quadro_3a"]:
                continue
            self.assertEqual(parse_numero_tabela(linha["ate_500"])[0], _num(OFICIAL["quadro_3a"][pa][0]), pa)
            self.assertEqual(parse_numero_tabela(linha["acima_500"])[0], _num(OFICIAL["quadro_3a"][pa][1]), pa)


class TestCoeELpuosArtigos(unittest.TestCase):
    """COE art. 108 e LPUOS arts. 62 e 66 — números usados nas contas de áreas não computáveis e recuos."""

    def test_coe_art_108(self):
        coe = OFICIAL["coe_art_108"]
        self.assertEqual(lei.TERRACO_NAO_COMPUTAVEL_FRACAO_TERRENO, _num(coe["I_terraco_aberto_fracao_terreno_por_pavimento"]))
        self.assertEqual(lei.AREA_COMUM_NAO_COMPUTAVEL_M2_POR_UH, _num(coe["VII_b_area_comum_m2_por_habitacao"]))

    def test_lpuos_art_62(self):
        a62 = OFICIAL["lpuos_art_62"]
        self.assertEqual(lei.LIMITE_NAO_COMPUTAVEL, _num(a62["par2_limite_nao_computavel_incisos_I_a_VI"]))
        self.assertEqual(lei.COTA_GARAGEM_M2_POR_VAGA, _num(a62["I_a_cota_garagem_m2_por_vaga"]))
        self.assertEqual(lei.AREA_MINIMA_UH_PARA_VAGA_M2, _num(a62["I_a_1_unidade_minima_m2_para_vaga"]))
        self.assertEqual(lei.AREA_PRIVATIVA_POR_VAGA_M2, _num(a62["I_a_2_m2_privativos_por_vaga"]))
        self.assertEqual(lei.FACHADA_ATIVA_FRACAO_LOTE[True], _num(a62["VII_a_fachada_ativa_fracao_lote_eixos_e_ZC"]))
        self.assertEqual(lei.FACHADA_ATIVA_FRACAO_LOTE[False], _num(a62["VII_b_fachada_ativa_fracao_lote_demais"]))
        self.assertEqual(lei.NR_MISTO_FRACAO_COMPUTAVEL, _num(a62["VIII_nr_misto_fracao_computavel"]))
        self.assertEqual(lei.ZONAS_FACHADA_ATIVA_50, {"ZEU", "ZEUa", "ZEUP", "ZEUPa", "ZEM", "ZEMP", "ZC", "ZCa"})

    def test_lpuos_art_66(self):
        a66 = OFICIAL["lpuos_art_66"]
        self.assertEqual(lei.ALTURA_SEM_RECUO_LATERAL_M, _num(a66["I_altura_sem_recuo_lateral_m"]))
        self.assertEqual(lei.AREA_TERRENO_DISPENSA_RECUO_M2, _num(a66["III_area_terreno_dispensa_m2"]))
        self.assertEqual(lei.FRENTE_DISPENSA_RECUO_M, _num(a66["III_frente_dispensa_m"]))
        self.assertEqual(lei.ZONAS_SEM_DISPENSA_ATE_10M, set(a66["excecoes_I"]))
        self.assertTrue(lei.recuo_lateral_dispensado(250.0, 20.0))
        self.assertTrue(lei.recuo_lateral_dispensado(800.0, 10.0))
        self.assertFalse(lei.recuo_lateral_dispensado(800.0, 10.5))
        # As zonas sem dispensa até 10 m são exatamente as que têm recuo até 10 m no Quadro 3 (exceto clubes)
        com_recuo_ate_10 = {z for z, p in lei.QUADRO_3.items() if p.recuo_ate_10m > 0 and not z.startswith("AC-")}
        self.assertEqual(com_recuo_ate_10, set(a66["excecoes_I"]))


if __name__ == "__main__":
    unittest.main()
