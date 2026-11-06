"""
Modelos de dados do Estudo de Viabilidade (espelho da planilha QUADRO_DE_ÁREAS-R01.xlsx).

Cada dataclass corresponde a um bloco da planilha; os comentários indicam a célula de origem.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Colunas do Quadro de Áreas (aba Q. ÁREAS)
# ---------------------------------------------------------------------------

# Unidades por pavimento — colunas D:K
COLUNAS_UNIDADES: List[Tuple[str, str]] = [
    ("u_his2", "HIS-2"),
    ("u_his1", "HIS-1"),
    ("u_r2v1", "R2V-1"),
    ("u_his2_cota", "HIS-2 (Cota)"),
    ("u_his1_50", "HIS-1 (50%)"),
    ("u_r2v1_10", "R2V-1 (10%)"),
    ("u_nr1_12", "NR1-12"),
    ("u_nr1_3", "NR1-3 (F.A.)"),
]

# Áreas computáveis — colunas L:Q
COLUNAS_COMPUTAVEIS: List[Tuple[str, str]] = [
    ("c_his2", "HIS-2"),
    ("c_his1", "HIS-1"),
    ("c_terraco_his2", "Terraço HIS-2"),
    ("c_r2v1", "R2V-1"),
    ("c_terraco_r2v1", "Terraço R2V-1"),
    ("c_circ", "Circulação"),
]

# Áreas não computáveis — colunas R:AD
COLUNAS_NAO_COMPUTAVEIS: List[Tuple[str, str]] = [
    ("nc_circ", "Circulação"),
    ("nc_terraco", "Terraço"),
    ("nc_ecc", "E.C.C."),
    ("nc_ncc", "N.C.C."),
    ("nc_estacionamento", "Estacionamento"),
    ("nc_oc", "O.C."),
    ("nc_at", "A.T."),
    ("nc_his2_cota", "HIS-2 (Cota Solid.)"),
    ("nc_his1_50", "HIS-1 (50%)"),
    ("nc_r2v1_10", "R2V-1 (10% incentivo)"),
    ("nc_nr1_12", "NR1-12"),
    ("nc_circ_terraco_nr1_12", "Circ. + Terraço NR1-12"),
    ("nc_nr1_3_fa", "NR1-3 (Fachada Ativa)"),
]

TODAS_COLUNAS_AREA = [c for c, _ in COLUNAS_COMPUTAVEIS] + [c for c, _ in COLUNAS_NAO_COMPUTAVEIS]
TODAS_COLUNAS_UNIDADE = [c for c, _ in COLUNAS_UNIDADES]

MODALIDADES = {
    "EHIS": "EHIS — Decreto HIS 63.728/24 (C.A. Quadro 2)",
    "EHIS_COTA": "EHIS + Cota de Solidariedade (C.A. +20%)",
    "EHMP": "EHMP — Decreto HIS (C.A. EHMP)",
    "EZEIS": "EZEIS — ZEIS (proporção 60/40)",
    "LPUOS": "LPUOS ordinário (C.A. máximo Quadro 3)",
}


# ---------------------------------------------------------------------------
# Etapa 2 — Entrada vinda do GeoSampa (normalizada)
# ---------------------------------------------------------------------------

@dataclass
class EntradaGeo:
    area_escritura_m2: float                 # área geométrica do terreno (GeoSampa)
    area_doacao_m2: float                    # doação/melhoramento viário (usuário)
    area_terreno_m2: float                   # E − D = R  (Q. ÁREAS!D38)
    endereco: str                            # Q. ÁREAS!D37
    sqls: List[str]
    zona: Optional[str]                      # Q. ÁREAS!D39 (normalizada, chave do Quadro 2/3)
    zona_original: Optional[str]
    pa: Optional[str]                        # Q. ÁREAS!D40 (ex.: "PA 6")
    macroarea: Optional[str]
    macrozona: Optional[str]
    cota_terreno_m: Optional[float]          # cota do térreo (Q. ÁREAS!A5)
    cota_min_m: Optional[float]
    cota_max_m: Optional[float]
    testada_m: float = 0.0
    profundidade_m: float = 0.0
    tombamento: bool = False
    alertas: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Etapa 3 — Índices legais (Quadros 2, 3 e 4)
# ---------------------------------------------------------------------------

@dataclass
class IndicesLegais:
    zona: Optional[str]
    pa: Optional[str]
    area_terreno_m2: float
    modalidade: str
    to_max: Optional[float]                  # C43 (após trava da nota (b))
    to_tabela: Optional[float]               # valor de tabela antes da trava
    ca_minimo: Optional[float]
    ca_basico: Optional[float]               # C44
    ca_maximo_lpuos: Optional[float]         # C45 (Quadro 3)
    ca_max_ehis: Optional[float]             # C46 (Quadro 2)
    ca_max_ehmp: Optional[float]
    ca_majorado: Optional[float]             # W40 = C46 × 1,2
    ca_projeto: Optional[float]              # W38 (conforme modalidade)
    tp_min: Optional[float]                  # C47
    gabarito_m: Optional[float]              # C51 (None = sem limite)
    recuo_frente: str
    recuo_ate_10m: str
    recuo_acima_10m: str
    cota_parte_m2: Optional[float]           # Q. LUOPS!E22
    fachada_ativa_pct: float                 # 0,5 ou 0,2
    proporcao_his: float                     # 0,8 (ou 0,6 em EZEIS)
    # Áreas aplicadas ao terreno (coluna D da ficha)
    area_ocupacao_max_m2: Optional[float]    # D43
    area_comp_basica_m2: Optional[float]     # D44
    area_comp_max_lpuos_m2: Optional[float]  # D45
    area_comp_max_his_m2: Optional[float]    # D46
    area_permeavel_min_m2: Optional[float]   # D47
    area_comp_projeto_m2: Optional[float]    # T46 = W38 × W36
    notas: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Etapas 5/6 — Pavimentos e Quadro de Áreas
# ---------------------------------------------------------------------------

@dataclass
class Pavimento:
    nome: str
    pe_direito_m: float
    tipo: str = "tipo"                        # "inferior" | "terreo" | "tipo" | "atico"
    unidades: Dict[str, float] = field(default_factory=dict)
    areas: Dict[str, float] = field(default_factory=dict)
    cota_m: float = 0.0                       # calculada


@dataclass
class LinhaLimite:
    item: str
    maximo: Optional[float]
    projeto: float
    sobra: Optional[float]
    atende: Optional[bool]
    referencia: str
    sentido: str = "max"                      # "max" (projeto ≤ limite) | "min" (projeto ≥ exigido)


@dataclass
class QuadroAreas:
    pavimentos: List[Pavimento]
    subtotal_unidades: Dict[str, float]
    subtotal_areas: Dict[str, float]
    total_unidades: float
    total_unidades_planilha: float            # C25 = Σ(D+F+G+K) — fórmula original
    area_computavel_m2: float                 # L26
    area_nao_computavel_m2: float             # R26
    area_construida_m2: float                 # C27
    area_privativa_m2: float                  # E63
    area_loja_m2: float                       # E64
    eficiencia: Optional[float]               # E66
    pct_his: Optional[float]                  # L28
    pct_r2v: Optional[float]                  # O28
    atende_proporcao_ehis: Optional[bool]
    altura_edificacao_m: float                # E51
    atende_gabarito: Optional[bool]
    limites: List[LinhaLimite]
    total_por_pavimento: List[float]
    pct_circ_por_pavimento: List[Optional[float]]
    verificacao_soma: float                   # AE32 (deve ser 0)
    alertas: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Etapa 7 — Quadro de Uso e Ocupação do Solo
# ---------------------------------------------------------------------------

@dataclass
class LinhaQuadro:
    bloco: str
    item: str
    valor: Optional[float]
    unidade: str = ""
    observacao: str = ""


# ---------------------------------------------------------------------------
# Etapa 8 — Anexos
# ---------------------------------------------------------------------------

@dataclass
class ResultadoAnexos:
    reuso_vri_l: float
    reuso_vrv_l: float
    reuso_exigido_l: float
    reuso_projetado_l: float
    retardo_exigido_l: float
    retardo_projetado_l: float
    acessibilidade: List[LinhaQuadro]
    vagas: List[LinhaQuadro]
    uso_incentivado: List[LinhaQuadro]


# ---------------------------------------------------------------------------
# Etapa 9 — População e água
# ---------------------------------------------------------------------------

@dataclass
class PavimentoPopulacao:
    nome: str
    dorm1: int = 0
    dorm2: int = 0
    dorm3: int = 0


@dataclass
class ResultadoAgua:
    linhas: List[Dict[str, float]]
    pop_elevador: int
    pop_agua: int
    pop_bombeiros: int
    consumo_diario_l: float
    superior_recomendado_l: float
    inferior_recomendado_l: float
    total_recomendado_l: float
    superior_projetado_l: float
    inferior_projetado_l: float
    total_projetado_l: float


# ---------------------------------------------------------------------------
# Etapa 10 — Elevador
# ---------------------------------------------------------------------------

@dataclass
class ResultadoElevador:
    destinacao: str
    classe: str                               # "A" | "E" | "O"
    populacao: float
    pct_5min: float
    populacao_5min: float
    intervalo_max_s: Optional[float]
    paradas_provaveis: float
    t_acel: float
    t_porta: float
    t_passageiro: float
    t1: float
    t2: float
    t3: float
    t4: float
    soma_parcial: float
    adicional_10: float
    ttv: float
    intervalo_s: float
    capac_transporte: float
    capac_trafego: float
    grau_servico: float
    distancia_min_m: float
    atende_capacidade: bool
    atende_intervalo: Optional[bool]
    alertas: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Etapa 11 — Desnível
# ---------------------------------------------------------------------------

@dataclass
class ResultadoDesnivel:
    linhas_a: List[LinhaQuadro]
    linhas_b: List[LinhaQuadro]
    linhas_c: List[LinhaQuadro]
    cota_terreno_arquitetura: float
    cota_terreno_hidraulica: float
    diferenca: float
    resultado: str
    adequado: bool


# ---------------------------------------------------------------------------
# Etapa 13 — Viabilidade Econômico-Financeira e Cronograma de Obra
# ---------------------------------------------------------------------------

@dataclass
class ItemReceitaVGV:
    categoria: str
    unidades: int
    area_privativa_m2: float
    preco_m2_rs: float
    vgv_rs: float
    ticket_medio_rs: float
    participacao_pct: float


@dataclass
class ItemCustoEmpreendimento:
    grupo: str
    descricao: str
    valor_rs: float
    pct_custo_total: float
    pct_vgv: float
    criterio: str


@dataclass
class EtapaCronograma:
    ordem: int
    fase: str
    etapa: str
    mes_inicio: int
    mes_fim: int
    duracao_meses: int
    peso_obra_pct: float
    custo_estimado_rs: float
    barra_gantt: str


@dataclass
class PeriodoFluxoCaixa:
    periodo: str
    mes_inicio: int
    mes_fim: int
    avanco_fisico_pct: float
    avanco_acumulado_pct: float
    desembolso_total_rs: float
    receita_liquida_rs: float
    saldo_periodo_rs: float
    saldo_acumulado_rs: float


@dataclass
class ResultadoFinanceiroCronograma:
    # Receitas (VGV)
    itens_vgv: List[ItemReceitaVGV]
    vgv_bruto_rs: float
    preco_medio_privativo_m2_rs: float

    # Custos
    itens_custo: List[ItemCustoEmpreendimento]
    custo_terreno_total_rs: float
    custo_obra_direto_rs: float
    custo_obra_m2_efetivo_rs: float
    custo_projetos_taxas_rs: float
    custo_outorga_cota_rs: float
    custo_comercial_mkt_rs: float
    custo_incorporacao_impostos_rs: float
    custo_total_empreendimento_rs: float

    # Indicadores de Retorno
    lucro_liquido_rs: float
    margem_liquida_vgv_pct: float
    roi_sobre_custo_pct: float
    exposicao_maxima_caixa_rs: float
    mes_pico_exposicao: int
    payback_mes: Optional[int]
    vpl_rs: float
    tir_mensal_pct: float
    tir_anual_pct: float
    viavel: bool

    # Cronograma de Obra
    prazo_pre_obra_meses: int
    prazo_obra_meses: int
    prazo_total_meses: int
    sistema_construtivo: str
    etapas_cronograma: List[EtapaCronograma]
    fluxo_trimestral: List[PeriodoFluxoCaixa]
    notas: List[str] = field(default_factory=list)


