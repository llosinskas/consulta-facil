"""
Testes unitários para validação de inputs (SQL, múltiplos SQLs, endereço/CEP, coordenadas),
clique interativo no mapa e segunda consulta espacial pelo ponto geográfico do lote
(Macrozona, Macroárea, Qualificação Ambiental e Zoneamento).

Execute com:
    .venv\\Scripts\\python.exe -m unittest discover -s tests -v
"""

import unittest
from unittest.mock import MagicMock

from pyproj import Transformer

from config import CRS_UTM_SP, CRS_WGS84
from services.geocoder import geocodificar_endereco_sp, validar_endereco_input
from services.geosampa_client import (
    LOTES_EXEMPLO_SP,
    GeoSampaWFSClient,
    buscar_lote_local_por_ponto_utm,
    criar_feicao_referencia_coordenada,
    extrair_multiplos_sqls,
    normalizar_sql_input,
    validar_coordenadas_sp,
    validar_sql_input,
)
from services.spatial_analyzer import (
    alternar_lote_na_selecao,
    consultar_enquadramento_pelo_ponto_do_lote,
    processar_terreno_completo,
)
from ui.dashboard_cards import gerar_dataframe_unitario_vs_unificado
from ui.map_component import construir_mapa_terreno

_UTM_TO_WGS84 = Transformer.from_crs(CRS_UTM_SP, CRS_WGS84, always_xy=True)


class TestSQLInputs(unittest.TestCase):
    """Testes unitários para entradas de SQL (Setor, Quadra e Lote)."""

    def test_normalizar_sql_padrao_e_zeros_a_esquerda(self) -> None:
        self.assertEqual(normalizar_sql_input("9", "74", "15"), ("009", "074", "0015"))
        self.assertEqual(normalizar_sql_input("083", "112", "0021"), ("083", "112", "0021"))

    def test_normalizar_sql_remove_digito_verificador(self) -> None:
        self.assertEqual(normalizar_sql_input("009", "074", "0015-8"), ("009", "074", "0015"))
        self.assertEqual(normalizar_sql_input("009", "074", "0015-X"), ("009", "074", "0015"))

    def test_validar_sql_input_valido(self) -> None:
        sql, erro = validar_sql_input("09", "74", "15-2")
        self.assertIsNone(erro)
        self.assertEqual(sql, ("009", "074", "0015"))

    def test_validar_sql_input_rejeita_vazios_ou_zeros(self) -> None:
        sql, erro = validar_sql_input("", "074", "0015")
        self.assertIsNone(sql)
        self.assertIsNotNone(erro)

        sql_zero, erro_zero = validar_sql_input("000", "074", "0015")
        self.assertIsNone(sql_zero)
        self.assertIn("maiores que zero", erro_zero or "")

        sql_letras, erro_letras = validar_sql_input("abc", "def", "ghi")
        self.assertIsNone(sql_letras)
        self.assertIsNotNone(erro_letras)

    def test_extrair_multiplos_sqls_formatos_variados_e_sem_duplicatas(self) -> None:
        texto = """
        083.112.0021,
        083/112/0022-5;
        SQL: 083-112-0023-X
        0831120024
        08311200259
        083.112.0021
        000.000.0000
        invalido
        """
        extraidos = extrair_multiplos_sqls(texto)
        self.assertEqual(
            extraidos,
            [
                ("083", "112", "0021"),
                ("083", "112", "0022"),
                ("083", "112", "0023"),
                ("083", "112", "0024"),
                ("083", "112", "0025"),
            ],
        )

    def test_extrair_multiplos_sqls_vazio(self) -> None:
        self.assertEqual(extrair_multiplos_sqls(""), [])
        self.assertEqual(extrair_multiplos_sqls("   \n , ; "), [])


class TestCoordenadasEEnderecoInputs(unittest.TestCase):
    """Testes unitários para validação de coordenadas geográficas e endereços/CEPs."""

    def test_validar_coordenadas_sp_validas_com_ponto_e_virgula(self) -> None:
        coord, erro = validar_coordenadas_sp(-23.561414, -46.655881)
        self.assertIsNone(erro)
        self.assertEqual(coord, (-23.561414, -46.655881))

        coord_str, erro_str = validar_coordenadas_sp("-23,550520", "-46,633308")
        self.assertIsNone(erro_str)
        self.assertEqual(coord_str, (-23.550520, -46.633308))

    def test_validar_coordenadas_sp_fora_do_municipio_ou_invertidas(self) -> None:
        # Coordenada invertida (lon no lugar de lat)
        coord_inv, erro_inv = validar_coordenadas_sp(-46.655881, -23.561414)
        self.assertIsNone(coord_inv)
        self.assertIn("fora dos limites", erro_inv or "")

        # Rio de Janeiro
        coord_rj, erro_rj = validar_coordenadas_sp(-22.9068, -43.1729)
        self.assertIsNone(coord_rj)
        self.assertIsNotNone(erro_rj)

    def test_validar_coordenadas_sp_nao_numericas_ou_nan(self) -> None:
        coord, erro = validar_coordenadas_sp("abc", "-46.65")
        self.assertIsNone(coord)
        self.assertIsNotNone(erro)

        coord_nan, erro_nan = validar_coordenadas_sp(float("nan"), -46.65)
        self.assertIsNone(coord_nan)
        self.assertIsNotNone(erro_nan)

    def test_validar_endereco_e_cep(self) -> None:
        # CEP válido de São Paulo
        termo, erro = validar_endereco_input("01310-200")
        self.assertIsNone(erro)
        self.assertEqual(termo, "01310200")

        # CEP inválido (menos de 8 dígitos)
        termo_curto, erro_curto = validar_endereco_input("01310-20")
        self.assertIsNone(termo_curto)
        self.assertIn("8 dígitos", erro_curto or "")

        # CEP fora de São Paulo (ex: RJ 20040-002)
        termo_rj, erro_rj = validar_endereco_input("20040-002")
        self.assertIsNone(termo_rj)
        self.assertIn("não pertence ao município de São Paulo", erro_rj or "")

        # Endereço válido
        end_ok, erro_end = validar_endereco_input("Av. Paulista, 1578")
        self.assertIsNone(erro_end)
        self.assertEqual(end_ok, "Av. Paulista, 1578")

        # Endereço vazio ou curto demais
        end_vazio, erro_vazio = validar_endereco_input("   ")
        self.assertIsNone(end_vazio)
        self.assertIsNotNone(erro_vazio)

        latlon, fmt, err_geo = geocodificar_endereco_sp("")
        self.assertIsNone(latlon)
        self.assertIsNone(fmt)
        self.assertIsNotNone(err_geo)


class TestCliqueMapaEConsultaPeloPonto(unittest.TestCase):
    """Testes para o clique interativo no terreno e 2ª consulta espacial pelo ponto geográfico."""

    def test_clique_no_terreno_retorna_lote_correto(self) -> None:
        # Ponto no interior do lote 083.112.0022 (Pinheiros: X entre 328120 e 328130, Y entre 7392815 e 7392850)
        x_utm, y_utm = 328125.0, 7392830.0
        lote_local = buscar_lote_local_por_ponto_utm(x_utm, y_utm)
        self.assertIsNotNone(lote_local)
        self.assertEqual(lote_local["properties"]["cd_lote"], "0022")

        # Testando via GeoSampaWFSClient.consultar_lote_por_coordenada (com sessão sem rede -> usa fallback local)
        lon, lat = _UTM_TO_WGS84.transform(x_utm, y_utm)
        client = GeoSampaWFSClient()
        client._request_wfs = MagicMock(return_value=None)  # simula servidor offline
        feats, erro = client.consultar_lote_por_coordenada(lat, lon)
        self.assertIsNone(erro)
        self.assertEqual(len(feats), 1)
        self.assertEqual(feats[0]["properties"]["cd_lote"], "0022")

    def test_segunda_consulta_pelo_ponto_geografico_do_lote(self) -> None:
        exemplo = LOTES_EXEMPLO_SP["Av. Paulista (Bela Vista) - ZEU (Lote Comercial)"]
        resultado = processar_terreno_completo(features_lotes=exemplo["features_utm"])

        # Simula o GeoSampa respondendo à 2ª consulta pelo ponto geográfico do lote
        client_mock = MagicMock()
        respostas_ponto = {
            "macrozona": (
                [{"properties": {"nm_macrozona": "Macrozona de Estruturação e Qualificação Urbana"}}],
                "geoportal:macrozona",
            ),
            "macroarea": (
                [{"properties": {"sg_macroarea": "MEM", "nm_macroarea": "Macroárea de Estruturação Metropolitana"}}],
                "geoportal:macroarea",
            ),
            "qualificacao_ambiental": (
                [{"properties": {"cd_perimetro": "PA 5", "ds_qualificacao": "Perímetro de Qualificação Ambiental PA 5"}}],
                "geoportal:perimetro_qualificacao_ambiental",
            ),
            "zoneamento": (
                [{"properties": {"cd_zona": "ZEU"}}],
                "geoportal:zoneamento_2016_map1",
            ),
        }
        client_mock.consultar_camada_no_ponto.side_effect = lambda tema, x, y: respostas_ponto.get(tema, ([], None))

        atualizado = consultar_enquadramento_pelo_ponto_do_lote(resultado, client_mock)
        self.assertEqual(atualizado.macrozona.valor, "Macrozona de Estruturação e Qualificação Urbana")
        self.assertEqual(atualizado.macroarea.valor, "Macroárea de Estruturação Metropolitana (MEM)")
        self.assertIn("PA 5", atualizado.qualificacao_ambiental.valor or "")
        self.assertEqual(atualizado.zoneamento.sigla_zona, "ZEU")
        self.assertIsNotNone(atualizado.macrozona.ponto_latlon)
        self.assertEqual(atualizado.macrozona.ponto_utm, atualizado.ponto_utm)

    def test_mapa_interativo_renderiza_popup_e_ponto_clicado(self) -> None:
        exemplo = LOTES_EXEMPLO_SP["Pinheiros (Unificação de 3 Lotes Contíguos) - ZEU"]
        resultado = processar_terreno_completo(
            features_lotes=exemplo["features_utm"],
            zona_forcada="ZEU",
            valores_territoriais_iniciais={
                "macrozona": exemplo["macrozona"],
                "macroarea": exemplo["macroarea"],
                "qualificacao_ambiental": exemplo["qualificacao_ambiental"],
            },
        )
        mapa = construir_mapa_terreno(
            resultado=resultado,
            ponto_clicado_latlon=resultado.centroide_latlon,
        )
        html = mapa.get_root().render()
        self.assertIn("Ficha do Terreno Selecionado", html)
        self.assertIn("083.112.0021", html)
        self.assertIn("Ponto clicado:", html)
        self.assertIn("Macrozona:", html)
        self.assertIn("Qualificação ambiental:", html)

    def test_endereco_coordenada_atualiza_mapa_com_feicao_referencia(self) -> None:
        # Coordenada real em São Paulo (-23.564005, -46.538457) quando geocodificada no eixo da via
        lat, lon = -23.564005, -46.538457
        feat_ref = criar_feicao_referencia_coordenada(lat, lon, endereco="Endereço Teste SP")
        res = processar_terreno_completo([feat_ref], endereco_referencia="Endereço Teste SP")
        self.assertAlmostEqual(res.centroide_latlon[0], lat, places=4)
        self.assertAlmostEqual(res.centroide_latlon[1], lon, places=4)
        self.assertAlmostEqual(res.area_total_m2, 250.0, places=1)

    def test_selecao_multiplos_lotes_no_mapa_e_tabela_unitario_vs_unificado(self) -> None:
        # Inicia com 1 lote na Av. Paulista (009.074.0015)
        exemplo = LOTES_EXEMPLO_SP["Av. Paulista (Bela Vista) - ZEU (Lote Comercial)"]
        res_1 = processar_terreno_completo(features_lotes=exemplo["features_utm"], zona_forcada="ZEU")
        self.assertFalse(res_1.unificado)
        self.assertEqual(len(res_1.lotes), 1)

        # Clica no lote vizinho contíguo 009.074.0016 (X=331005, Y=7393360)
        vizinho = buscar_lote_local_por_ponto_utm(331005.0, 7393360.0)
        self.assertIsNotNone(vizinho)
        self.assertEqual(vizinho["properties"]["cd_lote"], "0016")

        # 1º clique no vizinho -> adiciona à seleção (2 lotes)
        feats_2, acao_add = alternar_lote_na_selecao(res_1.lotes, [vizinho])
        self.assertEqual(acao_add, "adicionado")
        self.assertEqual(len(feats_2), 2)

        res_2 = processar_terreno_completo(features_lotes=feats_2, zona_forcada="ZEU")
        self.assertTrue(res_2.unificado)
        self.assertEqual(len(res_2.lotes), 2)
        self.assertAlmostEqual(
            res_2.area_total_m2,
            res_2.lotes[0].area_cartografica_m2 + res_2.lotes[1].area_cartografica_m2,
            places=1,
        )

        # Gera a tabela comparativa Unitário vs. Unificado
        df = gerar_dataframe_unitario_vs_unificado(res_2)
        self.assertEqual(len(df), 3)  # Unitário #1, Unitário #2 e UNIFICADO (2 lotes)
        self.assertEqual(df.iloc[0]["SQL"], "009.074.0015")
        self.assertEqual(df.iloc[1]["SQL"], "009.074.0016")
        self.assertEqual(df.iloc[2]["SQL"], "009.074.0015 + 009.074.0016")
        self.assertAlmostEqual(
            float(df.iloc[0]["Potencial_Maximo_m2"]) + float(df.iloc[1]["Potencial_Maximo_m2"]),
            float(df.iloc[2]["Potencial_Maximo_m2"]),
            places=1,
        )

        # 2º clique no mesmo lote vizinho -> remove da seleção (volta para 1 lote)
        feats_1_novamente, acao_rem = alternar_lote_na_selecao(res_2.lotes, [vizinho])
        self.assertEqual(acao_rem, "removido")
        self.assertEqual(len(feats_1_novamente), 1)


if __name__ == "__main__":
    unittest.main()

