"""
Modelos de domínio para Lotes, Terrenos, Dimensões Geométricas e Estudo de Viabilidade.
"""

from dataclasses import MISSING, dataclass, field, fields, is_dataclass
from typing import Any, Dict, List, Optional, Tuple

from domain.legislacao_sp import extrair_pa, taxa_permeabilidade


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
    taxa_ocupacao_lote_menor_500: Optional[float] = None  # Quadro 3: lotes abaixo de 500 m²

    def taxa_ocupacao_para_area(self, area_m2: float) -> float:
        if area_m2 < 500 and self.taxa_ocupacao_lote_menor_500 is not None:
            return self.taxa_ocupacao_lote_menor_500
        return self.taxa_ocupacao_max


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
class ParticipacaoZona:
    """Quanto do lote cai em uma zona de um mapa de zoneamento."""
    sigla: Optional[str]          # sigla oficial do Quadro 3 (None = não é zona: viário, praça, canteiro…)
    texto_original: str           # valor do GeoSampa (ex.: "ZEU", "PRAÇA/CANTEIRO")
    area_m2: float
    percentual: float             # 0–100 da área do lote


@dataclass
class LeituraMapaZoneamento:
    """Resultado de um Mapa 1 (lei) do GeoSampa sobre o lote."""
    lei: str
    camada: str
    papel: str                    # "vigente" | "contestado" | "historico"
    situacao: str
    respondeu: bool
    zonas: List[ParticipacaoZona] = field(default_factory=list)

    @property
    def zona_predominante(self) -> Optional[str]:
        validas = [z for z in self.zonas if z.sigla]
        return max(validas, key=lambda z: z.area_m2).sigla if validas else None


@dataclass
class ConfirmacaoZona:
    """Zona do lote confirmada pela interseção do polígono com o Mapa 1 vigente da LPUOS."""
    zona: Optional[str]
    status: str                   # "confirmada" | "lote em mais de uma zona" | "não confirmada"
    percentual_zona: float        # % do lote na zona indicada
    lei_referencia: str
    leituras: List[LeituraMapaZoneamento] = field(default_factory=list)
    alertas: List[str] = field(default_factory=list)

    @property
    def confirmada(self) -> bool:
        return self.status == "confirmada"


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
    confirmacao_zona: Optional[ConfirmacaoZona] = None

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
        return round(self.area_total_m2 * self.zoneamento.taxa_ocupacao_para_area(self.area_total_m2), 2)

    @property
    def area_permeavel_minima_m2(self) -> float:
        if not self.zoneamento:
            return 0.0
        pa = extrair_pa(self.qualificacao_ambiental.valor) if self.qualificacao_ambiental else None
        taxa = taxa_permeabilidade(self.zoneamento.sigla_zona, pa, self.area_total_m2)
        return round(self.area_total_m2 * (taxa or 0.0), 2)



def completar_campos_novos(objeto: Any) -> Any:
    """
    Objetos guardados em st.session_state sobrevivem a um deploy (Streamlit Cloud atualiza o código sem
    reiniciar a sessão) e podem ter sido criados por uma versão antiga da classe, sem os campos novos.
    Preenche, no próprio objeto e nos dataclasses aninhados, os campos ausentes com o valor padrão.
    """
    if not is_dataclass(objeto) or isinstance(objeto, type):
        return objeto
    # Depois de um deploy o objeto é instância da classe ANTIGA (módulo recarregado): os campos novos
    # só existem na classe atual, buscada pelo nome entre as classes deste módulo.
    classe_atual = globals().get(type(objeto).__name__)
    if not (isinstance(classe_atual, type) and is_dataclass(classe_atual)):
        classe_atual = type(objeto)
    for campo in fields(classe_atual):
        if not hasattr(objeto, campo.name):
            if campo.default is not MISSING:
                setattr(objeto, campo.name, campo.default)
            elif campo.default_factory is not MISSING:  # type: ignore[misc]
                setattr(objeto, campo.name, campo.default_factory())  # type: ignore[misc]
            continue
        valor = getattr(objeto, campo.name)
        if is_dataclass(valor):
            completar_campos_novos(valor)
        elif isinstance(valor, list):
            for item in valor:
                completar_campos_novos(item)
    return objeto
