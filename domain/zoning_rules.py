"""
Tabela de Parâmetros Urbanísticos de São Paulo (Quadro 3 - LPUOS Lei 16.402/16 e Revisão Lei 18.081/24).
Fornece os índices construtivos (CA, TO, Permeabilidade, Gabarito e Recuos) a partir da sigla de zoneamento.
"""

from typing import Dict, Optional
from domain.models import ParametrosZoneamento


ZONING_DATABASE: Dict[str, ParametrosZoneamento] = {
    "ZEU": ParametrosZoneamento(
        sigla_zona="ZEU",
        nome_zona="Zona Eixo de Estruturação da Transformação Urbana",
        ca_minimo=0.5,
        ca_basico=1.0,
        ca_maximo=4.0,
        taxa_ocupacao_max=0.70,
        taxa_permeabilidade_min=0.15,
        gabarito_altura_max_m=None,  # Sem limite (NA)
        recuo_frontal_m=0.0,         # Fachada ativa dispensada até alinhamento / 5m regra geral
        recuo_lateral_fundo_m="Isento até H<=10m; 3,0m acima de 10m",
        descricao_uso="Uso misto de alta densidade junto aos eixos de transporte público de massa (Metrô/Trem/Corredores).",
    ),
    "ZEUA": ParametrosZoneamento(
        sigla_zona="ZEUa",
        nome_zona="Zona Eixo de Estruturação da Transformação Urbana Ambiental",
        ca_minimo=0.5,
        ca_basico=1.0,
        ca_maximo=2.0,
        taxa_ocupacao_max=0.50,
        taxa_permeabilidade_min=0.30,
        gabarito_altura_max_m=28.0,
        recuo_frontal_m=5.0,
        recuo_lateral_fundo_m="3,0m acima de 10m",
        descricao_uso="Eixo de transformação urbana inserido na Macroárea de Contenção Urbana e Uso Sustentável.",
    ),
    "ZEUP": ParametrosZoneamento(
        sigla_zona="ZEUP",
        nome_zona="Zona Eixo de Estruturação da Transformação Urbana Previsto",
        ca_minimo=0.5,
        ca_basico=1.0,
        ca_maximo=2.0,  # Pode chegar a 4.0 após ordem de serviço da infraestrutura
        taxa_ocupacao_max=0.70,
        taxa_permeabilidade_min=0.15,
        gabarito_altura_max_m=28.0,
        recuo_frontal_m=5.0,
        recuo_lateral_fundo_m="3,0m acima de 10m",
        descricao_uso="Eixos de transporte previstos pelo PDE (CA máx = 2,0 enquanto não ativado para ZEU).",
    ),
    "ZEM": ParametrosZoneamento(
        sigla_zona="ZEM",
        nome_zona="Zona Eixo de Estruturação da Transformação Metropolitana",
        ca_minimo=0.5,
        ca_basico=1.0,
        ca_maximo=2.0,  # Até 4.0 mediante PIU / Operação Urbana
        taxa_ocupacao_max=0.70,
        taxa_permeabilidade_min=0.15,
        gabarito_altura_max_m=28.0,
        recuo_frontal_m=5.0,
        recuo_lateral_fundo_m="3,0m acima de 10m",
        descricao_uso="Áreas na Macroárea de Estruturação Metropolitana com transição para alta densidade.",
    ),
    "ZC": ParametrosZoneamento(
        sigla_zona="ZC",
        nome_zona="Zona de Centralidade",
        ca_minimo=0.3,
        ca_basico=1.0,
        ca_maximo=2.0,
        taxa_ocupacao_max=0.70,
        taxa_permeabilidade_min=0.15,
        gabarito_altura_max_m=48.0,
        recuo_frontal_m=5.0,
        recuo_lateral_fundo_m="3,0m acima de 10m",
        descricao_uso="Promoção de atividades comerciais, serviços e uso misto em centralidades locais e regionais.",
    ),
    "ZM": ParametrosZoneamento(
        sigla_zona="ZM",
        nome_zona="Zona Mista",
        ca_minimo=0.3,
        ca_basico=1.0,
        ca_maximo=2.0,
        taxa_ocupacao_max=0.70,
        taxa_permeabilidade_min=0.15,
        gabarito_altura_max_m=28.0,
        recuo_frontal_m=5.0,
        recuo_lateral_fundo_m="3,0m acima de 10m",
        descricao_uso="Porções do território destinadas a usos residenciais e não residenciais com densidades médias.",
    ),
    "ZMA": ParametrosZoneamento(
        sigla_zona="ZMa",
        nome_zona="Zona Mista Ambiental",
        ca_minimo=0.2,
        ca_basico=1.0,
        ca_maximo=1.0,
        taxa_ocupacao_max=0.50,
        taxa_permeabilidade_min=0.30,
        gabarito_altura_max_m=15.0,
        recuo_frontal_m=5.0,
        recuo_lateral_fundo_m="3,0m acima de 10m",
        descricao_uso="Zona Mista localizada em área de sensibilidade ambiental, com gabarito e ocupação controlados.",
    ),
    "ZMIS": ParametrosZoneamento(
        sigla_zona="ZMIS",
        nome_zona="Zona Mista de Interesse Social",
        ca_minimo=0.3,
        ca_basico=1.0,
        ca_maximo=2.0,
        taxa_ocupacao_max=0.70,
        taxa_permeabilidade_min=0.15,
        gabarito_altura_max_m=28.0,
        recuo_frontal_m=5.0,
        recuo_lateral_fundo_m="3,0m acima de 10m",
        descricao_uso="Assentamentos habitacionais populares regularizados com permissão para comércio e serviços locais.",
    ),
    "ZEIS-1": ParametrosZoneamento(
        sigla_zona="ZEIS-1",
        nome_zona="Zona Especial de Interesse Social 1",
        ca_minimo=0.5,
        ca_basico=1.0,
        ca_maximo=2.5,
        taxa_ocupacao_max=0.70,
        taxa_permeabilidade_min=0.15,
        gabarito_altura_max_m=28.0,
        recuo_frontal_m=5.0,
        recuo_lateral_fundo_m="3,0m acima de 10m",
        descricao_uso="Áreas ocupadas por população de baixa renda voltadas à urbanização e produção de HIS/HMP.",
    ),
    "ZEIS-2": ParametrosZoneamento(
        sigla_zona="ZEIS-2",
        nome_zona="Zona Especial de Interesse Social 2",
        ca_minimo=0.5,
        ca_basico=1.0,
        ca_maximo=4.0,
        taxa_ocupacao_max=0.70,
        taxa_permeabilidade_min=0.15,
        gabarito_altura_max_m=None,
        recuo_frontal_m=5.0,
        recuo_lateral_fundo_m="3,0m acima de 10m",
        descricao_uso="Terrenos subutilizados ou não edificados adequados à produção de Habitação de Interesse Social (HIS).",
    ),
    "ZEIS-3": ParametrosZoneamento(
        sigla_zona="ZEIS-3",
        nome_zona="Zona Especial de Interesse Social 3",
        ca_minimo=0.5,
        ca_basico=1.0,
        ca_maximo=4.0,
        taxa_ocupacao_max=0.70,
        taxa_permeabilidade_min=0.15,
        gabarito_altura_max_m=None,
        recuo_frontal_m=5.0,
        recuo_lateral_fundo_m="3,0m acima de 10m",
        descricao_uso="Imóveis subutilizados em regiões dotadas de infraestrutura e serviços urbanos centrais para HIS.",
    ),
    "ZEIS-5": ParametrosZoneamento(
        sigla_zona="ZEIS-5",
        nome_zona="Zona Especial de Interesse Social 5",
        ca_minimo=0.5,
        ca_basico=1.0,
        ca_maximo=4.0,
        taxa_ocupacao_max=0.70,
        taxa_permeabilidade_min=0.15,
        gabarito_altura_max_m=None,
        recuo_frontal_m=5.0,
        recuo_lateral_fundo_m="3,0m acima de 10m",
        descricao_uso="Lotes vazios ou subutilizados em áreas bem localizadas voltados prioritariamente a HIS e HMP.",
    ),
    "ZCOR-1": ParametrosZoneamento(
        sigla_zona="ZCOR-1",
        nome_zona="Zona Corredor 1",
        ca_minimo=0.05,
        ca_basico=1.0,
        ca_maximo=1.0,
        taxa_ocupacao_max=0.50,
        taxa_permeabilidade_min=0.30,
        gabarito_altura_max_m=10.0,
        recuo_frontal_m=5.0,
        recuo_lateral_fundo_m="3,0m em todos os pavimentos",
        descricao_uso="Corredor lindeiro a ZER com permissão controlada de serviços de baixo impacto e gabarito de 10m.",
    ),
    "ZCOR-2": ParametrosZoneamento(
        sigla_zona="ZCOR-2",
        nome_zona="Zona Corredor 2",
        ca_minimo=0.05,
        ca_basico=1.0,
        ca_maximo=1.0,
        taxa_ocupacao_max=0.50,
        taxa_permeabilidade_min=0.30,
        gabarito_altura_max_m=15.0,
        recuo_frontal_m=5.0,
        recuo_lateral_fundo_m="3,0m em todos os pavimentos",
        descricao_uso="Corredor de uso misto de baixa densidade incrustado ou adjacente a áreas predominantemente residenciais.",
    ),
    "ZCOR-3": ParametrosZoneamento(
        sigla_zona="ZCOR-3",
        nome_zona="Zona Corredor 3",
        ca_minimo=0.05,
        ca_basico=1.0,
        ca_maximo=1.0,
        taxa_ocupacao_max=0.50,
        taxa_permeabilidade_min=0.30,
        gabarito_altura_max_m=15.0,
        recuo_frontal_m=5.0,
        recuo_lateral_fundo_m="3,0m em todos os pavimentos",
        descricao_uso="Corredor em grandes avenidas lindeiras a zonas residenciais permitindo comércio diversificado.",
    ),
    "ZER-1": ParametrosZoneamento(
        sigla_zona="ZER-1",
        nome_zona="Zona Exclusivamente Residencial 1",
        ca_minimo=0.05,
        ca_basico=1.0,
        ca_maximo=1.0,
        taxa_ocupacao_max=0.50,
        taxa_permeabilidade_min=0.30,
        gabarito_altura_max_m=10.0,
        recuo_frontal_m=5.0,
        recuo_lateral_fundo_m="3,0m de um dos lados ou conforme escritura",
        descricao_uso="Uso estritamente residencial unifamiliar de baixa densidade (bairros-jardim).",
    ),
    "ZER-2": ParametrosZoneamento(
        sigla_zona="ZER-2",
        nome_zona="Zona Exclusivamente Residencial 2",
        ca_minimo=0.05,
        ca_basico=1.0,
        ca_maximo=1.0,
        taxa_ocupacao_max=0.50,
        taxa_permeabilidade_min=0.30,
        gabarito_altura_max_m=10.0,
        recuo_frontal_m=5.0,
        recuo_lateral_fundo_m="3,0m acima de 6m",
        descricao_uso="Uso estritamente residencial de média-baixa densidade.",
    ),
    "ZDE-1": ParametrosZoneamento(
        sigla_zona="ZDE-1",
        nome_zona="Zona de Desenvolvimento Econômico 1",
        ca_minimo=0.5,
        ca_basico=1.0,
        ca_maximo=2.0,
        taxa_ocupacao_max=0.70,
        taxa_permeabilidade_min=0.15,
        gabarito_altura_max_m=28.0,
        recuo_frontal_m=5.0,
        recuo_lateral_fundo_m="3,0m acima de 10m",
        descricao_uso="Incentivo a usos produtivos, tecnológicos, logísticos e industriais compatíveis com uso urbano.",
    ),
    "ZPI-1": ParametrosZoneamento(
        sigla_zona="ZPI-1",
        nome_zona="Zona Predominantemente Industrial 1",
        ca_minimo=0.5,
        ca_basico=1.0,
        ca_maximo=1.5,
        taxa_ocupacao_max=0.70,
        taxa_permeabilidade_min=0.15,
        gabarito_altura_max_m=28.0,
        recuo_frontal_m=5.0,
        recuo_lateral_fundo_m="3,0m em todos os pavimentos",
        descricao_uso="Destinada à implantação e manutenção de atividades industriais e logísticas de maior porte.",
    ),
}


def obter_parametros_zoneamento(sigla_bruta: Optional[str]) -> Optional[ParametrosZoneamento]:
    """
    Normaliza a sigla de zoneamento retornada pelo GeoSampa (ex: 'ZM', 'ZEU', 'ZEIS 1', 'ZM-a')
    e retorna os parâmetros urbanísticos correspondentes.
    """
    if not sigla_bruta:
        return None

    limpa = sigla_bruta.strip().upper().replace(" ", "-")
    if limpa in ZONING_DATABASE:
        return ZONING_DATABASE[limpa]

    # Tentativa sem hífen ou por prefixo
    sem_hifen = limpa.replace("-", "")
    if sem_hifen in ZONING_DATABASE:
        return ZONING_DATABASE[sem_hifen]

    for chave, params in ZONING_DATABASE.items():
        if limpa.startswith(chave):
            return params

    # Fallback genérico caso seja uma zona especial (ex: ZOE, AC, ZEPAM)
    return ParametrosZoneamento(
        sigla_zona=sigla_bruta.strip(),
        nome_zona=f"Zona Especial / Específica ({sigla_bruta.strip()})",
        ca_minimo=0.3,
        ca_basico=1.0,
        ca_maximo=1.0,
        taxa_ocupacao_max=0.50,
        taxa_permeabilidade_min=0.20,
        gabarito_altura_max_m=28.0,
        recuo_frontal_m=5.0,
        recuo_lateral_fundo_m="Consultar regramento específico (LPUOS / Operação Urbana)",
        descricao_uso="Zona com parâmetros específicos definidos em decreto, Operação Urbana Consorciada ou PIU.",
    )

