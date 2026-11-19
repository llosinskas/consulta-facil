"""
Testes de arquitetura: garantem que as camadas e os contratos públicos descritos em CLAUDE.md
não sejam quebrados por alterações (humanas ou de IA).
"""

import ast
import importlib
import inspect
import pathlib
import unittest

RAIZ = pathlib.Path(__file__).resolve().parent.parent

PROIBIDOS_POR_CAMADA = {
    "domain": {"services", "ui", "streamlit", "streamlit_folium", "folium", "altair", "app"},
    "services": {"ui", "streamlit", "streamlit_folium", "folium", "altair", "app"},
}

# Funções públicas usadas entre camadas e os parâmetros que os chamadores usam.
CONTRATOS = {
    "services.spatial_analyzer": {
        "processar_terreno_completo": ["features_lotes", "client", "endereco_referencia", "zona_forcada"],
        "alternar_lote_na_selecao": ["lotes_atuais", "novas_features"],
        "consultar_enquadramento_pelo_ponto_do_lote": ["resultado", "client"],
    },
    "services.viabilidade_bridge": {
        "extrair_entrada_geo": ["resultado", "area_doacao_m2", "zona_override", "pa_override"],
        "calcular_indices_legais": ["entrada", "modalidade", "ca_customizado"],
    },
    "services.quadro_areas_engine": {
        "gerar_pavimentos_padrao": ["cota_terreno_m", "qtd_pavimentos_tipo"],
        "distribuir_areas_automaticas_por_terreno": ["indices", "cota_terreno_m", "qtd_pav_tipo"],
        "calcular_quadro_areas": ["pavimentos", "indices", "cota_terreno_m"],
        "calcular_quadro_luops": ["indices", "quadro_areas"],
        "calcular_anexos": ["indices", "quadro_areas"],
    },
    "services.agua_elevador_engine": {
        "calcular_agua_e_populacao": ["pavimentos_pop"],
        "calcular_trafego_elevadores": ["populacao_predio"],
    },
    "services.desnivel_engine": {"calcular_desnivel_reservatorios": []},
    "services.financeiro_cronograma_engine": {
        "calcular_retorno_financeiro_e_cronograma": ["entrada", "indices", "quadro", "sistema_construtivo"],
        "estimar_prazo_obra_meses": ["area_construida_m2", "num_pavimentos", "sistema_construtivo"],
    },
    "services.eletrica_engine": {"calcular_previa_eletrica": ["quadro"]},
    "services.aproveitamento": {"calcular_aproveitamento": ["ent"]},
    "services.payback": {"calcular_payback": ["e"], "sensibilidade_payback": ["e"]},
    "services.excel_exporter": {"gerar_xlsx_bytes": ["abas"]},
    "services.geocoder": {"geocodificar_endereco_sp": ["endereco_ou_cep"]},
    "domain.zoning_rules": {"obter_parametros_zoneamento": ["sigla_bruta"]},
}


def _modulos_importados(arquivo: pathlib.Path) -> set:
    arvore = ast.parse(arquivo.read_text(encoding="utf-8"))
    nomes = set()
    for no in ast.walk(arvore):
        if isinstance(no, ast.Import):
            nomes.update(a.name.split(".")[0] for a in no.names)
        elif isinstance(no, ast.ImportFrom) and no.module and no.level == 0:
            nomes.add(no.module.split(".")[0])
    return nomes


class TestCamadas(unittest.TestCase):
    def test_camadas_nao_importam_camadas_superiores(self) -> None:
        violacoes = []
        for camada, proibidos in PROIBIDOS_POR_CAMADA.items():
            for arquivo in sorted((RAIZ / camada).glob("*.py")):
                usados = _modulos_importados(arquivo) & proibidos
                if usados:
                    violacoes.append(f"{arquivo.relative_to(RAIZ)} importa {sorted(usados)}")
        self.assertEqual(violacoes, [], "Quebra de camadas (ver CLAUDE.md, seção 2)")


class TestContratosPublicos(unittest.TestCase):
    def test_funcoes_publicas_e_parametros_existem(self) -> None:
        faltando = []
        for nome_mod, funcoes in CONTRATOS.items():
            mod = importlib.import_module(nome_mod)
            for nome_fn, params in funcoes.items():
                fn = getattr(mod, nome_fn, None)
                if not callable(fn):
                    faltando.append(f"{nome_mod}.{nome_fn} não existe")
                    continue
                assinatura = inspect.signature(fn).parameters
                for p in params:
                    if p not in assinatura:
                        faltando.append(f"{nome_mod}.{nome_fn} perdeu o parâmetro '{p}'")
        self.assertEqual(faltando, [], "Contrato público alterado (ver CLAUDE.md, seção 3)")


if __name__ == "__main__":
    unittest.main()
