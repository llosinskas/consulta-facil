"""
Modelos de domínio para Lotes, Terrenos, Dimensões Geométricas e Estudo de Viabilidade.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class SegmentoAresta:
    """Representa uma aresta (lado) do polígono do terreno."""
    indice: int
    ponto_inicial_latlon: Tuple[float, float]
    ponto_final_latlon: Tuple[float, float]
    ponto_medio_latlon: Tuple[float, float]
    comprimento_m: float
    azimute_graus: float
    orientacao_cardeal: str


@dataclass
class DadosTopografia:
    """Resumo altimétrico e de declividade do terreno."""
    cota_min_m: Optional[float] = None
    cota_max_m: Optional[float] = None
    desnivel_m: Optional[float] = None
    declividade_media_pct: Optional[float] = None
    qtd_curvas_interceptadas: int = 0
    observacao: str = "Não consultado"


@dataclass
class InfoTerritorial:
    """Enquadramento do lote em uma camada territorial consultada pelo ponto geográfico do lote."""
    tema: str                       # ex.: "Macroárea"
    valor: Optional[str] = None     # ex.: "Macroárea de Estruturação Metropolitana (MEM)"
    camada: Optional[str] = None    # nome da camada WFS/WMS consultada
    atributos: Dict[str, Any] = field(default_factory=dict)
    observacao: str = "Não consultado"
    ponto_latlon: Optional[Tuple[float, float]] = None
    ponto_utm: Optional[Tuple[float, float]] = None

    @property
    def encontrado(self) -> bool:
        return bool(self.valor)


@dataclass
class ParametrosZoneamento:
    """Índices urbanísticos aplicáveis à zona do lote (LPUOS São Paulo)."""
    sigla_zona: str
    nome_zona: str
    ca_minimo: float
    ca_basico: float
    ca_maximo: float
    taxa_ocupacao_max: float         # Ex: 0.70 (70%)
    taxa_permeabilidade_min: float   # Ex: 0.15 (15%)
    gabarito_altura_max_m: Optional[float]  # None = Sem limite (NA)
    recuo_frontal_m: float
    recuo_lateral_fundo_m: str
    descricao_uso: str
    legislacao_ref: str = "Lei 16.402/2016 e Revisão Lei 18.081/2024"


@dataclass
class LoteIndividual:
    """Dados individuais (unitários) de um lote retornado pelo GeoSampa."""
    setor: str
    quadra: str
    lote: str
    sql_formatado: str
    area_cartografica_m2: float
    perimetro_m: float
    atributos_brutos: Dict[str, Any]
    geojson_wgs84: Dict[str, Any]
    zona_incidente: Optional[str] = None
    testada_estimada_m: float = 0.0
    profundidade_estimada_m: float = 0.0
    fator_regularidade: float = 1.0
    centroide_latlon: Tuple[float, float] = (0.0, 0.0)


@dataclass
class ResultadoTerreno:
    """
    Resultado consolidado da análise do terreno (pode ser 1 lote ou a unificação de vários lotes).
    """
    lotes: List[LoteIndividual]
    unificado: bool
    area_total_m2: float
    perimetro_total_m: float
    largura_estimada_m: float
    profundidade_estimada_m: float
    testada_principal_m: float
    fator_regularidade: float  # 0.0 a 1.0 (1.0 = retângulo perfeito)
    centroide_latlon: Tuple[float, float]
    bbox_latlon: Tuple[float, float, float, float]  # (min_lon, min_lat, max_lon, max_lat)
    geojson_unificado_wgs84: Dict[str, Any]
    ponto_utm: Tuple[float, float] = (0.0, 0.0)     # (E, N) em SIRGAS 2000 UTM 23S (EPSG:31983)
    arestas: List[SegmentoAresta] = field(default_factory=list)
    zoneamento: Optional[ParametrosZoneamento] = None
    zonas_detectadas: List[str] = field(default_factory=list)
    topografia: Optional[DadosTopografia] = None
    macrozona: Optional[InfoTerritorial] = None
    macroarea: Optional[InfoTerritorial] = None
    qualificacao_ambiental: Optional[InfoTerritorial] = None
    tombamento_detectado: bool = False
    detalhes_tombamento: List[str] = field(default_factory=list)
    endereco_aproximado: Optional[str] = None
    fonte_dados: str = "GeoSampa WFS Oficial"
    avisos: List[str] = field(default_factory=list)

    @property
    def potencial_construtivo_basico_m2(self) -> float:
        if not self.zoneamento:
            return 0.0
        return round(self.area_total_m2 * self.zoneamento.ca_basico, 2)

    @property
    def potencial_construtivo_maximo_m2(self) -> float:
        if not self.zoneamento:
            return 0.0
        return round(self.area_total_m2 * self.zoneamento.ca_maximo, 2)

    @property
    def projecao_maxima_m2(self) -> float:
        if not self.zoneamento:
            return 0.0
        return round(self.area_total_m2 * self.zoneamento.taxa_ocupacao_max, 2)

    @property
    def area_permeavel_minima_m2(self) -> float:
        if not self.zoneamento:
            return 0.0
        return round(self.area_total_m2 * self.zoneamento.taxa_permeabilidade_min, 2)

