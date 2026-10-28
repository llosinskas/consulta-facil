"""
Configurações globais e endpoints do GeoSampa (Prefeitura de São Paulo).
"""

# Endpoints oficiais OGC do GeoSampa
GEOSAMPA_WFS_URLS = [
    "https://wfs.geosampa.prefeitura.sp.gov.br/geoserver/geoportal/wfs",
    "http://wfs.geosampa.prefeitura.sp.gov.br/geoserver/geoportal/wfs",
    "https://wfs.geosampa.prefeitura.sp.gov.br/geoserver/geoportal/ows",
]

GEOSAMPA_WMS_URL = "https://wms.geosampa.prefeitura.sp.gov.br/geoserver/geoportal/wms"
GEOSAMPA_WMS_URLS = [
    "https://wms.geosampa.prefeitura.sp.gov.br/geoserver/geoportal/wms",
    "http://wms.geosampa.prefeitura.sp.gov.br/geoserver/geoportal/wms",
    "https://wfs.geosampa.prefeitura.sp.gov.br/geoserver/geoportal/wms",
]

# Sistemas de Referência de Coordenadas (CRS)
CRS_UTM_SP = "EPSG:31983"  # SIRGAS 2000 / UTM zone 23S (em metros - oficial de SP)
CRS_WGS84 = "EPSG:4326"    # Latitude / Longitude para exibição web (Folium/Leaflet)

# Camadas WFS candidatas por tema (em ordem de prioridade para auto-descoberta)
# Nomes confirmados no GetCapabilities do GeoSampa em 28/10/2026.
# Observação: os NOMES DOS CAMPOS (atributos) de cada camada ainda não foram verificados.
LAYER_CANDIDATES = {
    "lote": [
        "geoportal:lote_cidadao",
    ],
    "quadra": [
        "geoportal:quadra_fiscal",
    ],
    "zoneamento": [
        # Mapa 1 da LPUOS 2016 (Lei 16.402/16). Pode não refletir a revisão da Lei 18.081/24.
        "geoportal:zoneamento_2016_map1",
    ],
    "curva_nivel": [
        "geoportal:curva_intermediaria",
        "geoportal:curva_mestra",
    ],
    "tombamento": [
        "geoportal:patrimonio_cultural_bem_tombado",
        "geoportal:patrimonio_cultural_area_envoltoria_CONPRESP",
        "geoportal:patrimonio_cultural_area_envoltoria_CONDEPHAAT",
        "geoportal:patrimonio_cultural_area_envoltoria_IPHAN",
    ],
    # Nomes NÃO confirmados: o cliente também procura automaticamente no GetCapabilities
    # usando as palavras-chave de LAYER_KEYWORDS abaixo.
    "macrozona": [
        "geoportal:macrozona",
        "geoportal:pde_macrozona",
        "geoportal:macrozona_pde",
        "geoportal:mapa_01_macrozona",
    ],
    "macroarea": [
        "geoportal:macroarea",
        "geoportal:pde_macroarea",
        "geoportal:macroarea_pde",
        "geoportal:mapa_02_macroarea",
    ],
    "qualificacao_ambiental": [
        "geoportal:perimetro_qualificacao_ambiental",
        "geoportal:qualificacao_ambiental",
        "geoportal:quota_ambiental",
        "geoportal:zoneamento_2016_map3",
        "geoportal:lpuos_qualificacao_ambiental",
    ],
}

# Palavras-chave (sem acento, minúsculas) buscadas tanto no <Name> quanto no <Title> do GetCapabilities
LAYER_KEYWORDS = {
    "macrozona": ["macrozona", "mapa 01 - macrozona", "mapa 1 - macrozona", "mcrz"],
    "macroarea": ["macroarea", "macro area", "mapa 02 - macroarea", "mapa 2 - macroarea"],
    "qualificacao_ambiental": [
        "qualificacao_ambiental",
        "qualificacao ambiental",
        "quota_ambiental",
        "quota ambiental",
        "qualif_amb",
        "zoneamento_2016_map3",
        "mapa 03",
        "mapa 3",
    ],
}

# Camadas com estes termos no nome são ignoradas (legislação revogada / antiga)
LAYER_EXCLUDE_TERMS = ["revogad", "13885", "13430", "2002", "2004"]

# Possíveis nomes de colunas para Setor, Quadra e Lote no WFS do GeoSampa
SQL_FIELD_VARIATIONS = [
    {
        "setor": "cd_setor_fiscal",
        "quadra": "cd_quadra_fiscal",
        "lote": "cd_lote",
    },
    {
        "setor": "cd_setor",
        "quadra": "cd_quadra",
        "lote": "cd_lote",
    },
    {
        "setor": "setor",
        "quadra": "quadra",
        "lote": "lote",
    },
]

# Centro padrão do mapa (Praça da Sé, São Paulo)
DEFAULT_MAP_CENTER = (-23.550520, -46.633308)
DEFAULT_MAP_ZOOM = 17
REQUEST_TIMEOUT = 15

