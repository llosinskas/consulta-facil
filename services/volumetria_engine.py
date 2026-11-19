"""
Motor da Etapa 16: volumetria aproximada do edifício (estudo de massa).

A partir do terreno (GeoSampa), do Quadro de Áreas (Etapa 6) e dos índices legais, monta um bloco
3D por pavimento:
- embasamento (pavimentos até 10 m de altura): planta = terreno reduzido até a projeção máxima (T.O.);
- torre (acima de 10 m): terreno recuado pelo recuo lateral/fundo da zona, também limitado pela T.O.;
- cada pavimento usa essa planta escalada até a sua área construída (nunca maior que a planta máxima);
- altura de cada bloco = pé-direito do pavimento.

É uma aproximação visual: a frente do lote não é identificada, então o recuo de frente não é
aplicado separadamente (fica um aviso), e a planta mantém o formato do terreno.
"""

import math
from typing import Dict, List, Optional

from shapely.affinity import scale as escalar
from shapely.geometry import MultiPolygon, Polygon

from domain.viabilidade_models import (
    CATEGORIAS_TIPOLOGIA,
    IndicesLegais,
    Pavimento,
    QuadroAreas,
    ResultadoVolumetria,
    VolumePavimento,
)
from services.spatial_analyzer import geometria_para_utm, geometria_para_wgs84
from services.viabilidade_bridge import parse_numero_tabela

ALTURA_RECUO_LATERAL_M = 10.0   # LPUOS: recuos laterais/fundo exigidos acima de 10 m de altura
AREA_MINIMA_PLANTA_M2 = 1.0


def _maior_poligono(geom) -> Optional[Polygon]:
    if geom is None or geom.is_empty:
        return None
    if isinstance(geom, MultiPolygon):
        return max(geom.geoms, key=lambda g: g.area)
    return geom if isinstance(geom, Polygon) else None


def _anel_wgs84(poligono_utm: Polygon) -> List[List[float]]:
    wgs = geometria_para_wgs84(poligono_utm)
    return [[round(x, 8), round(y, 8)] for x, y in wgs.exterior.coords]


def _escalar_ate_area(poligono: Polygon, area_alvo: float) -> Polygon:
    if poligono.area <= 0 or area_alvo >= poligono.area:
        return poligono
    fator = math.sqrt(max(area_alvo, 0.0) / poligono.area)
    return escalar(poligono, xfact=fator, yfact=fator, origin="centroid")


def _uso_predominante(p: Pavimento) -> str:
    if p.tipo == "atico":
        return "Ático"
    if float(p.areas.get("nc_nr1_3_fa", 0.0) or 0.0) > 0:
        return "NR1-3 (Fachada Ativa)"
    melhor, maior = "Áreas comuns", 0.0
    for categoria, (_, col_area, _) in CATEGORIAS_TIPOLOGIA.items():
        area = float(p.areas.get(col_area, 0.0) or 0.0)
        if area > maior:
            melhor, maior = categoria, area
    return melhor


def calcular_volumetria(
    geojson_terreno: Dict,
    quadro: QuadroAreas,
    indices: IndicesLegais,
) -> ResultadoVolumetria:
    """Volume aproximado do edifício, pavimento a pavimento, sobre o terreno."""
    alertas: List[str] = []
    geometria = geojson_terreno.get("geometry", geojson_terreno)
    terreno = _maior_poligono(geometria_para_utm(geometria))
    if terreno is None:
        raise ValueError("Geometria do terreno vazia ou inválida.")

    pavimentos = [p for p in quadro.pavimentos]
    altura_total = round(sum(float(p.pe_direito_m or 0.0) for p in pavimentos), 2)

    projecao = indices.area_ocupacao_max_m2

    def _limitar_a_projecao(planta: Polygon) -> Polygon:
        return _escalar_ate_area(planta, projecao) if projecao and planta.area > projecao else planta

    # 1. Embasamento (pavimentos até 10 m): sem recuo lateral/fundo, limitado pela projeção (T.O.)
    planta_embasamento = _limitar_a_projecao(terreno)

    # 2. Torre (pavimentos acima de 10 m): recuo lateral/fundo do Quadro 3, também limitada pela T.O.
    recuo = 0.0
    planta_torre = planta_embasamento
    if altura_total > ALTURA_RECUO_LATERAL_M:
        valor, _ = parse_numero_tabela(indices.recuo_acima_10m)
        recuo = float(valor or 0.0)
        if recuo > 0:
            recuada = _maior_poligono(terreno.buffer(-recuo, join_style=2))
            if recuada is None or recuada.area < AREA_MINIMA_PLANTA_M2:
                alertas.append(
                    f"O recuo lateral/fundo de {recuo:.2f} m não deixa área útil neste terreno acima de 10 m; "
                    "a volumetria usa a planta do embasamento."
                )
                recuo = 0.0
            else:
                planta_torre = _limitar_a_projecao(recuada)
    frente, _ = parse_numero_tabela(indices.recuo_frente)
    if frente and frente > recuo:
        alertas.append(
            f"Recuo de frente de {frente:.2f} m não aplicado em separado (a frente do lote não é identificada "
            f"automaticamente); considere-o no projeto."
        )

    # 3. Um bloco por pavimento, escalado até a área construída do pavimento
    cota_base = float(pavimentos[0].cota_m) if pavimentos else 0.0
    blocos: List[VolumePavimento] = []
    excedidos: List[str] = []
    for idx, p in enumerate(pavimentos):
        pe_direito = float(p.pe_direito_m or 0.0)
        area_quadro = float(quadro.total_por_pavimento[idx]) if idx < len(quadro.total_por_pavimento) else 0.0
        base = round(float(p.cota_m or 0.0) - cota_base, 2)  # cotas acumuladas por calcular_quadro_areas
        if area_quadro < AREA_MINIMA_PLANTA_M2 or pe_direito <= 0:
            continue
        na_torre = base + pe_direito > ALTURA_RECUO_LATERAL_M + 0.01
        planta = planta_torre if na_torre else planta_embasamento
        limitado = area_quadro > planta.area + 0.01
        if limitado:
            excedidos.append(p.nome)
        poligono = _escalar_ate_area(planta, area_quadro)
        blocos.append(
            VolumePavimento(
                nome=p.nome,
                tipo=p.tipo,
                base_m=base,
                altura_m=round(pe_direito, 2),
                area_m2=round(poligono.area, 2),
                area_quadro_m2=round(area_quadro, 2),
                uso_predominante=_uso_predominante(p),
                poligono_wgs84=_anel_wgs84(poligono),
                limitado_pela_projecao=limitado,
            )
        )
    if excedidos:
        alertas.append(
            "Área construída maior que a planta possível (recuos e T.O.) em: " + ", ".join(excedidos)
            + ". O volume mostra a planta máxima; revise o Quadro de Áreas."
        )

    gabarito = indices.gabarito_m
    atende_gabarito = None if gabarito is None else altura_total <= gabarito + 0.01
    if atende_gabarito is False:
        alertas.append(f"Altura de {altura_total:.2f} m acima do gabarito de {gabarito:.2f} m da zona.")

    centro = geometria_para_wgs84(terreno).representative_point()
    return ResultadoVolumetria(
        pavimentos=blocos,
        altura_total_m=altura_total,
        volume_m3=round(sum(b.area_m2 * b.altura_m for b in blocos), 2),
        area_projecao_m2=round(max((b.area_m2 for b in blocos), default=0.0), 2),
        recuo_aplicado_m=round(recuo, 2),
        gabarito_m=gabarito,
        atende_gabarito=atende_gabarito,
        terreno_wgs84=_anel_wgs84(terreno),
        envelope_wgs84=_anel_wgs84(planta_torre),
        centro_latlon=(round(centro.y, 7), round(centro.x, 7)),
        alertas=alertas,
    )


def raio_terreno_m(volumetria: ResultadoVolumetria) -> float:
    """Meia-diagonal aproximada (m) do terreno, para escolher o zoom do mapa 3D."""
    xs = [c[0] for c in volumetria.terreno_wgs84]
    ys = [c[1] for c in volumetria.terreno_wgs84]
    dx = (max(xs) - min(xs)) * 111_320 * math.cos(math.radians(volumetria.centro_latlon[0]))
    dy = (max(ys) - min(ys)) * 110_540
    return math.hypot(dx, dy) / 2
