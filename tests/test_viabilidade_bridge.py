"""
Testes unitários das Etapas 1 a 12 do plano de conexão GeoSampa → Planilha (`QUADRO_DE_ÁREAS-R01.xlsx`).
"""

import io
import unittest
import zipfile

from services.agua_elevador_engine import (
    calcular_agua_e_populacao,
    calcular_trafego_elevadores,
    gerar_populacao_padrao_pavimentos,
)
from services.desnivel_engine import calcular_desnivel_reservatorios
from services.excel_exporter import gerar_xlsx_bytes
from services.financeiro_cronograma_engine import calcular_retorno_financeiro_e_cronograma
from services.geosampa_client import LOTES_EXEMPLO_SP
from services.quadro_areas_engine import (
    calcular_anexos,
    calcular_quadro_areas,
    calcular_quadro_luops,
    distribuir_areas_automaticas_por_terreno,
    gerar_pavimentos_padrao,
)
from services.spatial_analyzer import processar_terreno_completo
from services.viabilidade_bridge import (
    calcular_indices_legais,
    extrair_entrada_geo,
    extrair_pa,
    normalizar_zona,
)


class TestViabilidadeBridgeETabelas(unittest.TestCase):
    """Testa a normalização GeoSampa (Etapa 2) e os lookups nos Quadros 2, 3 e 4 (Etapa 3)."""

    def test_normalizar_zona_e_pa(self) -> None:
        self.assertEqual(normalizar_zona("ZEUP (a)"), "ZEUP")
        self.assertEqual(normalizar_zona("ZEUPa\xa0(b)"), "ZEUPa")
        self.assertEqual(normalizar_zona("ZM-2"), "ZM")
        self.assertEqual(normalizar_zona("ZCOR 2"), "ZCOR-2")
        self.assertEqual(extrair_pa("PA\xa06 (Perímetro de Qualificação Ambiental 6)"), "PA 6")
        self.assertEqual(extrair_pa(None, macroarea="Macroárea de Contenção Urbana"), "PA 13")

    def test_caso_referencia_planilha_zm_pa6_menor_500(self) -> None:
        """
        Verifica se Zona ZM + PA 6 + Lote < 500 m² reproduz exatamente os valores da planilha:
        TO = 0,85 · CA básico = 1 · CA máx LPUOS = 2 · CA HIS = 3 · CA +20% = 3,6 · TP = 0,15 · Gabarito = 28 m.
        """
        exemplo = LOTES_EXEMPLO_SP["Vila Mariana - Zona Mista (ZM)"]
        res_terreno = processar_terreno_completo(
            features_lotes=exemplo["features_utm"],
            zona_forcada="ZM",
            valores_territoriais_iniciais={"qualificacao_ambiental": "PA 6"},
        )
        # Força área < 500 m² via doação para testar a faixa < 500 m² da célula C43/C47
        doacao = res_terreno.area_total_m2 - 400.0
        entrada = extrair_entrada_geo(res_terreno, area_doacao_m2=doacao)
        self.assertAlmostEqual(entrada.area_terreno_m2, 400.0, places=2)

        ind = calcular_indices_legais(entrada, modalidade="EHIS_COTA")
        self.assertAlmostEqual(ind.to_max or 0.0, 0.85, places=2)
        self.assertAlmostEqual(ind.ca_basico or 0.0, 1.0, places=2)
        self.assertAlmostEqual(ind.ca_maximo_lpuos or 0.0, 2.0, places=2)
        self.assertAlmostEqual(ind.ca_max_ehis or 0.0, 3.0, places=2)
        self.assertAlmostEqual(ind.ca_majorado or 0.0, 3.6, places=2)
        self.assertAlmostEqual(ind.tp_min or 0.0, 0.15, places=2)
        self.assertAlmostEqual(ind.gabarito_m or 0.0, 28.0, places=1)
        self.assertIsNone(ind.cota_parte_m2)

    def test_faixa_acima_500m2_e_regras_especiais_zcor_pa13_zeu(self) -> None:
        exemplo = LOTES_EXEMPLO_SP["Pinheiros (Unificação de 3 Lotes Contíguos) - ZEU"]
        res_terreno = processar_terreno_completo(
            features_lotes=exemplo["features_utm"],
            zona_forcada="ZEU",
            valores_territoriais_iniciais={"qualificacao_ambiental": "PA 4"},
        )
        entrada = extrair_entrada_geo(res_terreno)
        self.assertGreater(entrada.area_terreno_m2, 500.0)

        ind_zeu = calcular_indices_legais(entrada, modalidade="EHIS")
        self.assertAlmostEqual(ind_zeu.to_max or 0.0, 0.70, places=2)
        self.assertAlmostEqual(ind_zeu.tp_min or 0.0, 0.25, places=2)
        self.assertAlmostEqual(ind_zeu.ca_max_ehis or 0.0, 6.0, places=2)
        self.assertAlmostEqual(ind_zeu.cota_parte_m2 or 0.0, 20.0, places=1)
        self.assertAlmostEqual(ind_zeu.fachada_ativa_pct, 0.50, places=2)
        self.assertIsNone(ind_zeu.gabarito_m)

        # Nota (a) ZCOR -> TP = 0,30
        entrada_zcor = extrair_entrada_geo(res_terreno, zona_override="ZCOR-1", pa_override="PA 6")
        ind_zcor = calcular_indices_legais(entrada_zcor)
        self.assertAlmostEqual(ind_zcor.tp_min or 0.0, 0.30, places=2)

        # Nota (e) PA 13 -> TP = 0,0
        entrada_pa13 = extrair_entrada_geo(res_terreno, zona_override="ZM", pa_override="PA 13")
        ind_pa13 = calcular_indices_legais(entrada_pa13)
        self.assertAlmostEqual(ind_pa13.tp_min or 0.0, 0.0, places=2)


class TestQuadroAreasLUOPSEAnexos(unittest.TestCase):
    """Testa as Etapas 6, 7 e 8 (Quadro de Áreas, Q. LUOPS e Q. ANEXOS)."""

    def test_cotas_pavimentos_padrao_iguais_a_planilha(self) -> None:
        pavs = gerar_pavimentos_padrao(cota_terreno_m=784.40, qtd_pavimentos_tipo=18, incluir_atico=True)
        # Na planilha: A5=784.40 (Térreo), A6=787.25 (1º), A7=790.10 (2º), A8=793.60 (3º), A23=834.40 (18º), A24=837.32 (Ático)
        self.assertAlmostEqual(pavs[0].cota_m, 784.40, places=2)
        self.assertAlmostEqual(pavs[1].cota_m, 787.25, places=2)
        self.assertAlmostEqual(pavs[2].cota_m, 790.10, places=2)
        self.assertAlmostEqual(pavs[3].cota_m, 793.60, places=2)
        self.assertAlmostEqual(pavs[18].cota_m, 834.40, places=2)
        self.assertAlmostEqual(pavs[19].cota_m, 837.32, places=2)

    def test_autopreenchimento_fechamento_luops_e_anexos(self) -> None:
        exemplo = LOTES_EXEMPLO_SP["Vila Mariana - Zona Mista (ZM)"]
        res_terreno = processar_terreno_completo(
            features_lotes=exemplo["features_utm"],
            zona_forcada="ZM",
            cota_min_forcada=788.0,
            cota_max_forcada=792.0,
            valores_territoriais_iniciais={"qualificacao_ambiental": "PA 6"},
        )
        entrada = extrair_entrada_geo(res_terreno)
        indices = calcular_indices_legais(entrada, modalidade="EHIS_COTA")

        pavs = distribuir_areas_automaticas_por_terreno(indices, cota_terreno_m=entrada.cota_terreno_m or 790.0, qtd_pav_tipo=9)
        quadro = calcular_quadro_areas(pavs, indices)

        self.assertEqual(quadro.verificacao_soma, 0.0)
        self.assertGreater(quadro.area_computavel_m2, 0.0)
        self.assertGreater(quadro.area_construida_m2, quadro.area_computavel_m2)
        self.assertTrue(quadro.atende_proporcao_ehis)
        self.assertTrue(quadro.atende_gabarito)

        luops = calcular_quadro_luops(indices, quadro)
        self.assertGreater(len(luops), 15)

        anexos = calcular_anexos(indices, quadro, vagas_automoveis_livres=20)
        self.assertAlmostEqual(anexos.retardo_exigido_l, round(indices.area_terreno_m2 * 6.3, 2), places=2)
        self.assertGreaterEqual(anexos.retardo_projetado_l, anexos.retardo_exigido_l)
        self.assertEqual(len(anexos.acessibilidade), 11)
        self.assertEqual(len(anexos.vagas), 4)


class TestAguaElevadorEDesnivel(unittest.TestCase):
    """Testa as Etapas 9, 10, 11 e 12 (Água/População, Elevador NBR 5665, Desnível A/B/C e Exportação .xlsx)."""

    def test_calculo_agua_e_elevador_nbr5665(self) -> None:
        pavs_pop = gerar_populacao_padrao_pavimentos(
            qtd_pav_tipo=9,
            unidades_1dorm_por_andar=3,
            unidades_2dorm_por_andar=8,
            unidades_3dorm_por_andar=0,
        )
        agua = calcular_agua_e_populacao(pavs_pop, litros_per_capita=125.0, reserva_incendio_l=25000.0)
        # Por andar: 3*2 + 8*4 = 38 pessoas -> 9 andares = 342 pessoas
        self.assertEqual(agua.pop_elevador, 342)
        self.assertEqual(agua.pop_agua, 342)
        self.assertAlmostEqual(agua.consumo_diario_l, 342 * 125.0, places=1)
        self.assertAlmostEqual(
            agua.total_recomendado_l,
            agua.superior_recomendado_l + agua.inferior_recomendado_l,
            places=1,
        )

        # Elevador: verifica também a distância mínima D57 = V*(V/0.9 + 0.9/1.5) = 1.7111 m para V=1.0 m/s
        elev = calcular_trafego_elevadores(
            populacao_predio=agua.pop_elevador,
            unidades_no_grupo=2,
            capac_nominal_pass=8,
            capac_calculo_pass=8,
            numero_paradas=11,
            percurso_m=27.0,
            velocidade_m_s=1.0,
            tipo_porta="AC",
            abertura_porta_m=0.80,
            codigo_destinacao=7,
        )
        self.assertAlmostEqual(elev.distancia_min_m, 1.71, places=2)
        self.assertAlmostEqual(elev.populacao_5min, 34.2, places=2)
        self.assertGreater(elev.ttv, 0.0)
        self.assertGreater(elev.capac_trafego, 0.0)

    def test_desnivel_reservatorios_e_exportacao_xlsx(self) -> None:
        desn = calcular_desnivel_reservatorios(
            cota_sarjeta_m=768.31,
            cota_terreno_arquitetura_m=769.00,
            comprimento_trecho_a_m=30.0,
            comprimento_trecho_b_m=20.0,
            comprimento_trecho_c_m=10.0,
        )
        self.assertTrue(desn.adequado)
        self.assertIn("ADEQUADA", desn.resultado)

        xlsx_bytes = gerar_xlsx_bytes(
            [
                ("Q. ÁREAS", [["Col1", "Col2"], ["Teste", 123.45]]),
                ("Q. LUOPS", [["Parâmetro", "Valor"], ["Área", 500]]),
            ]
        )
        with zipfile.ZipFile(io.BytesIO(xlsx_bytes), "r") as zf:
            names = zf.namelist()
            self.assertIn("xl/workbook.xml", names)
            self.assertIn("xl/worksheets/sheet1.xml", names)
            self.assertIn("xl/worksheets/sheet2.xml", names)

    def test_retorno_financeiro_e_cronograma_de_obra(self) -> None:
        exemplo = LOTES_EXEMPLO_SP["Vila Mariana - Zona Mista (ZM)"]
        res_terreno = processar_terreno_completo(
            features_lotes=exemplo["features_utm"],
            zona_forcada="ZM",
            cota_min_forcada=788.0,
            cota_max_forcada=792.0,
            valores_territoriais_iniciais={"qualificacao_ambiental": "PA 6"},
        )
        entrada = extrair_entrada_geo(res_terreno)
        indices = calcular_indices_legais(entrada, modalidade="EHIS_COTA")
        pavs = distribuir_areas_automaticas_por_terreno(indices, cota_terreno_m=790.0, qtd_pav_tipo=9)
        quadro = calcular_quadro_areas(pavs, indices)

        fin_cron = calcular_retorno_financeiro_e_cronograma(
            entrada=entrada,
            indices=indices,
            quadro=quadro,
            sistema_construtivo="Alvenaria Estrutural",
        )
        self.assertGreater(fin_cron.vgv_bruto_rs, 0.0)
        self.assertGreater(fin_cron.custo_total_empreendimento_rs, 0.0)
        self.assertAlmostEqual(
            fin_cron.lucro_liquido_rs,
            round(fin_cron.vgv_bruto_rs - fin_cron.custo_total_empreendimento_rs, 2),
            places=2,
        )
        self.assertEqual(len(fin_cron.etapas_cronograma), 10)
        self.assertEqual(
            fin_cron.prazo_total_meses,
            fin_cron.prazo_pre_obra_meses + fin_cron.prazo_obra_meses,
        )
        self.assertGreater(len(fin_cron.fluxo_trimestral), 0)
        self.assertAlmostEqual(fin_cron.fluxo_trimestral[-1].avanco_acumulado_pct, 100.0, places=1)


if __name__ == "__main__":
    unittest.main()

