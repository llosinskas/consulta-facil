"""
Parâmetros urbanísticos por zona, no formato usado pelo painel e pelo mapa.
Os valores vêm do Quadro 3 da LPUOS em domain/legislacao_sp.py, que é a única fonte destes números.
"""

from typing import Dict, Optional

from domain.legislacao_sp import QUADRO_3, TP_FIXA_POR_ZONA, TP_SEM_PA, ParametrosZonaLei, normalizar_zona
from domain.models import ParametrosZoneamento


def _descrever_recuos(zona: ParametrosZonaLei) -> str:
    ate_10 = f"{zona.recuo_ate_10m:.0f} m até 10 m de altura" if zona.recuo_ate_10m else "Isento até 10 m de altura"
    return f"{ate_10}; {zona.recuo_acima_10m:.0f} m acima de 10 m"


def _converter(zona: ParametrosZonaLei) -> ParametrosZoneamento:
    return ParametrosZoneamento(
        sigla_zona=zona.sigla,
        nome_zona=f"Zona {zona.nome}",
        ca_minimo=zona.ca_minimo or 0.0,
        ca_basico=zona.ca_basico,
        ca_maximo=zona.ca_maximo,
        taxa_ocupacao_max=zona.to_lote_500_ou_mais,
        taxa_ocupacao_lote_menor_500=zona.to_lote_menor_500,
        taxa_permeabilidade_min=TP_FIXA_POR_ZONA.get(zona.sigla, TP_SEM_PA[1]),
        gabarito_altura_max_m=zona.gabarito_m,
        recuo_frontal_m=zona.recuo_frente_m,
        recuo_lateral_fundo_m=_descrever_recuos(zona),
        descricao_uso="Índices do Quadro 3 da LPUOS; a permeabilidade depende do PA (Quadro 3A).",
    )


# AVP-1 fica de fora: não tem índices no Quadro 3 (nota k, art. 30 da LPUOS).
ZONING_DATABASE: Dict[str, ParametrosZoneamento] = {
    sigla.upper(): _converter(zona) for sigla, zona in QUADRO_3.items() if zona.ca_basico is not None
}


def obter_parametros_zoneamento(sigla_bruta: Optional[str]) -> Optional[ParametrosZoneamento]:
    """
    Normaliza a sigla do GeoSampa (ex.: 'ZM', 'ZEIS 1', 'ZM-a') e devolve os parâmetros da zona.
    Zonas fora do Quadro 3 (ex.: ZOE, ZEP) devolvem um registro genérico marcado como regra específica.
    """
    if not sigla_bruta:
        return None

    sigla = normalizar_zona(sigla_bruta)
    if sigla and sigla.upper() in ZONING_DATABASE:
        return ZONING_DATABASE[sigla.upper()]

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
