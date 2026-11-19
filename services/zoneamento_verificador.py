"""
Confirmação da zona do lote (LPUOS, Mapa 1) a partir do GeoSampa.

Em vez de olhar só um ponto do lote, cruza o POLÍGONO do terreno com cada mapa de zoneamento
(config.MAPAS_ZONEAMENTO) e mede quanto da área cai em cada zona:
- a zona de referência vem do mapa vigente (Lei 18.081/2024);
- lote dividido entre zonas é sinalizado (com o percentual de cada uma);
- diferenças em relação ao mapa da Lei 18.177/2024 (art. 8º declarado inconstitucional) e ao mapa
  original de 2016 viram avisos, para o usuário saber se a zona é contestada ou mudou na revisão;
- a sigla é validada contra o Quadro 3 (domain/legislacao_sp.py).

`analisar_mapas` é pura (recebe as feições) e é a que os testes usam; `confirmar_zona` faz a consulta.
"""

from typing import Any, Callable, Dict, List, Optional, Tuple

from shapely.geometry import shape

from config import FRACAO_MINIMA_ZONA, MAPAS_ZONEAMENTO
from domain.legislacao_sp import QUADRO_3, normalizar_zona
from domain.models import ConfirmacaoZona, LeituraMapaZoneamento, ParticipacaoZona

STATUS_CONFIRMADA = "confirmada"
STATUS_DIVIDIDA = "lote em mais de uma zona"
STATUS_NAO_CONFIRMADA = "não confirmada"

# A zona só é confirmada se cobrir ao menos esta parte do lote (o resto pode ser via/praça desenhada)
PERCENTUAL_MINIMO_CONFIRMACAO = 50.0

_CAMPOS_ZONA = ("cd_zoneamento_perimetro", "tx_zoneamento_perimetro", "cd_zona", "sg_zona")


def _texto_zona(props: Dict[str, Any]) -> str:
    for campo in _CAMPOS_ZONA:
        valor = props.get(campo)
        if valor not in (None, ""):
            return str(valor).strip()
    return ""


def _participacoes(poligono_utm, feicoes: List[Dict[str, Any]]) -> List[ParticipacaoZona]:
    """Área do lote em cada zona do mapa (feições somadas pela sigla), da maior para a menor."""
    area_lote = poligono_utm.area or 1.0
    por_chave: Dict[str, List[float]] = {}
    textos: Dict[str, str] = {}
    for feat in feicoes:
        geom = feat.get("geometry")
        if not geom:
            continue
        try:
            inter = shape(geom).buffer(0).intersection(poligono_utm).area
        except Exception:
            continue
        if inter <= 0:
            continue
        texto = _texto_zona(feat.get("properties") or {})
        sigla = normalizar_zona(texto)
        chave = sigla or texto.upper() or "?"
        por_chave.setdefault(chave, []).append(inter)
        textos.setdefault(chave, texto)
    zonas = [
        ParticipacaoZona(
            sigla=normalizar_zona(textos[chave]),
            texto_original=textos[chave],
            area_m2=round(sum(areas), 2),
            percentual=round(100.0 * sum(areas) / area_lote, 2),
        )
        for chave, areas in por_chave.items()
    ]
    return sorted(zonas, key=lambda z: z.area_m2, reverse=True)


def analisar_mapas(
    poligono_utm,
    feicoes_por_camada: Dict[str, Tuple[List[Dict[str, Any]], bool]],
    mapas: Optional[List[Dict[str, str]]] = None,
) -> ConfirmacaoZona:
    """Decide a zona do lote a partir das feições de cada mapa: {camada: (feições, respondeu)}."""
    mapas = mapas or MAPAS_ZONEAMENTO
    leituras: List[LeituraMapaZoneamento] = []
    for mapa in mapas:
        feicoes, respondeu = feicoes_por_camada.get(mapa["camada"], ([], False))
        leituras.append(
            LeituraMapaZoneamento(
                lei=mapa["lei"],
                camada=mapa["camada"],
                papel=mapa["papel"],
                situacao=mapa["situacao"],
                respondeu=respondeu,
                zonas=_participacoes(poligono_utm, feicoes) if respondeu else [],
            )
        )

    alertas: List[str] = []
    vigente = next((l for l in leituras if l.papel == "vigente"), None)
    referencia = vigente if vigente and vigente.respondeu and vigente.zona_predominante else None
    if referencia is None:
        # Mapa vigente indisponível: usa o melhor mapa que respondeu, mas não confirma
        referencia = next((l for l in leituras if l.respondeu and l.zona_predominante), None)
        if referencia is None:
            return ConfirmacaoZona(
                zona=None, status=STATUS_NAO_CONFIRMADA, percentual_zona=0.0,
                lei_referencia=vigente.lei if vigente else "", leituras=leituras,
                alertas=["Nenhum mapa de zoneamento do GeoSampa respondeu para este lote."],
            )
        alertas.append(
            f"O mapa vigente ({vigente.lei if vigente else 'Lei 18.081/2024'}) não respondeu; a zona abaixo vem do "
            f"mapa da {referencia.lei} e precisa ser conferida."
        )

    validas = [z for z in referencia.zonas if z.sigla and z.percentual >= FRACAO_MINIMA_ZONA * 100]
    principal = validas[0] if validas else None
    zona = principal.sigla if principal else None
    status = STATUS_CONFIRMADA if referencia is vigente else STATUS_NAO_CONFIRMADA

    if len(validas) > 1:
        status = STATUS_DIVIDIDA if referencia is vigente else status
        partes = ", ".join(f"{z.sigla} ({z.percentual:.1f}%)" for z in validas)
        alertas.append(
            f"O lote está em mais de uma zona: {partes}. Os parâmetros de cada parte seguem a sua zona; "
            f"o estudo usa {zona}, a predominante. Confira a regra de lote em mais de uma zona na LPUOS."
        )
    fora = [z for z in referencia.zonas if not z.sigla and z.percentual >= FRACAO_MINIMA_ZONA * 100]
    for z in fora:
        alertas.append(
            f"{z.percentual:.1f}% do polígono cai em '{z.texto_original}' (não é zona de uso): "
            "o desenho do lote pode avançar sobre via ou praça."
        )
    if principal and principal.percentual < PERCENTUAL_MINIMO_CONFIRMACAO:
        status = STATUS_NAO_CONFIRMADA
        alertas.insert(
            0,
            f"Só {principal.percentual:.1f}% do lote está em zona de uso ({zona}); o restante não é zona "
            "(via, praça ou área pública). A zona não pode ser confirmada: confira o SQL e o desenho do lote.",
        )
    cobertura = sum(z.percentual for z in referencia.zonas)
    if cobertura < 95:
        alertas.append(f"Só {cobertura:.0f}% do lote está coberto pelo mapa de zoneamento consultado.")
    if zona and zona not in QUADRO_3:
        alertas.append(f"A zona {zona} não tem parâmetros no Quadro 3 da LPUOS: confira a legislação específica.")

    for leitura in leituras:
        if leitura is referencia or not leitura.respondeu or not leitura.zona_predominante:
            continue
        outra = leitura.zona_predominante
        if outra == zona:
            continue
        if leitura.papel == "contestado":
            alertas.append(
                f"Pelo mapa da {leitura.lei} a zona seria {outra}. Esse mapa teve o art. 8º declarado "
                "inconstitucional pelo TJSP (26/08/2026), que restabeleceu o mapa da Lei 18.081/2024; atos "
                "aprovados na vigência da Lei 18.177 foram preservados e o tema ainda depende do STF."
            )
        elif leitura.papel == "historico":
            alertas.append(f"A zona mudou na revisão de 2024: era {outra} no {leitura.lei}.")

    return ConfirmacaoZona(
        zona=zona,
        status=status,
        percentual_zona=principal.percentual if principal else 0.0,
        lei_referencia=referencia.lei,
        leituras=leituras,
        alertas=alertas,
    )


def confirmar_zona(
    client,
    poligono_utm,
    progresso: Optional[Callable[[float, str], None]] = None,
) -> ConfirmacaoZona:
    """Consulta os mapas de zoneamento do GeoSampa na área do lote e confirma a zona."""
    minx, miny, maxx, maxy = poligono_utm.bounds
    feicoes: Dict[str, Tuple[List[Dict[str, Any]], bool]] = {}
    for i, mapa in enumerate(MAPAS_ZONEAMENTO):
        if progresso:
            progresso(i / len(MAPAS_ZONEAMENTO), f"Confirmando a zona no mapa da {mapa['lei']}…")
        try:
            feicoes[mapa["camada"]] = client.consultar_feicoes_camada_bbox(mapa["camada"], minx, miny, maxx, maxy)
        except Exception:
            feicoes[mapa["camada"]] = ([], False)
    return analisar_mapas(poligono_utm, feicoes)
