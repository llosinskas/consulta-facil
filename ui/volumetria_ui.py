"""
Etapa 16 na tela: volume aproximado do edifício em 3D sobre o mapa (pydeck / deck.gl).
Os cálculos ficam em services/volumetria_engine.py; aqui só há desenho.
"""

import math
from typing import Dict, List, Tuple

import pydeck as pdk
import streamlit as st
from shapely.geometry import Polygon

from domain.models import ResultadoTerreno
from domain.viabilidade_models import IndicesLegais, QuadroAreas, ResultadoVolumetria
from services.excel_exporter import CORES_TIPOLOGIA, familia_tipologia
from services.volumetria_engine import calcular_volumetria, raio_terreno_m
from ui.styles import grade_cards, nota, titulo_secao

COR_AREAS_COMUNS = (148, 163, 184)   # cinza-azulado
COR_ATICO = (71, 85, 105)            # ardósia
COR_TERRENO = (217, 119, 6)          # âmbar (mesmo contorno do mapa 2D)
COR_GABARITO = (220, 38, 38)         # vermelho


def _rgb(hex_argb: str) -> Tuple[int, int, int]:
    h = hex_argb[-6:]
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def cor_do_uso(uso: str) -> Tuple[int, int, int]:
    """Mesma cor da tipologia usada no Excel exportado."""
    if uso == "Ático":
        return COR_ATICO
    familia = familia_tipologia(uso)
    if familia is None:
        return COR_AREAS_COMUNS
    return _rgb(CORES_TIPOLOGIA[familia][2])


def _num(v: float, casas: int = 2) -> str:
    return f"{v:,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _zoom_para_raio(raio_m: float, lat: float) -> float:
    # metros por pixel no zoom z ≈ 156543·cos(lat)/2^z; enquadra ~5× o raio em ~560 px de altura
    metros_por_px = max(raio_m, 8.0) * 5.5 / 560
    return max(15.5, min(20.5, math.log2(156543.03 * math.cos(math.radians(lat)) / metros_por_px)))


def _bearing_obliquo(vol: ResultadoVolumetria) -> float:
    """Rumo da câmera em diagonal (≈35°) à face mais longa do terreno, para o volume não virar "parede"."""
    lat0 = vol.centro_latlon[0]
    k = 111_320 * math.cos(math.radians(lat0))
    pts = [(lon * k, lat * 110_540) for lon, lat in vol.terreno_wgs84]
    retangulo = list(Polygon(pts).minimum_rotated_rectangle.exterior.coords)
    lados = [(retangulo[i], retangulo[i + 1]) for i in range(4)]
    (x1, y1), (x2, y2) = max(lados, key=lambda l: math.dist(l[0], l[1]))
    azimute_lado = math.degrees(math.atan2(x2 - x1, y2 - y1))  # horário a partir do norte
    return (azimute_lado + 90 - 35) % 360


def _camadas(vol: ResultadoVolumetria, mostrar_gabarito: bool) -> List[pdk.Layer]:
    camadas = [
        pdk.Layer(
            "PolygonLayer",
            data=[{"polygon": vol.terreno_wgs84}],
            get_polygon="polygon",
            filled=True,
            stroked=True,
            get_fill_color=[*COR_TERRENO, 45],
            get_line_color=[*COR_TERRENO, 255],
            line_width_min_pixels=2,
        )
    ]
    if mostrar_gabarito and vol.gabarito_m:
        camadas.append(
            pdk.Layer(
                "PolygonLayer",
                data=[{"polygon": vol.envelope_wgs84, "altura": vol.gabarito_m}],
                get_polygon="polygon",
                extruded=True,
                wireframe=True,
                get_elevation="altura",
                get_fill_color=[*COR_GABARITO, 22],
                get_line_color=[*COR_GABARITO, 200],
                pickable=False,
            )
        )
    linhas: List[Dict] = []
    for b in vol.pavimentos:
        r, g, bl = cor_do_uso(b.uso_predominante)
        linhas.append(
            {
                # z da planta = altura do piso: deck.gl extruda a partir dela (blocos empilhados)
                "polygon": [[lon, lat, b.base_m] for lon, lat in b.poligono_wgs84],
                "altura": b.altura_m,
                "cor": [r, g, bl, 235],
                "nome": b.nome,
                "uso": b.uso_predominante,
                "area": _num(b.area_m2),
                "base": _num(b.base_m),
                "pe_direito": _num(b.altura_m),
                "aviso": " · limitado pela projeção" if b.limitado_pela_projecao else "",
            }
        )
    camadas.append(
        pdk.Layer(
            "PolygonLayer",
            data=linhas,
            get_polygon="polygon",
            extruded=True,
            wireframe=True,
            get_elevation="altura",
            get_fill_color="cor",
            get_line_color=[255, 255, 255, 160],
            pickable=True,
            auto_highlight=True,
            highlight_color=[250, 204, 21, 220],
            material={"ambient": 0.55, "diffuse": 0.6, "shininess": 24, "specularColor": [60, 64, 70]},
        )
    )
    return camadas


def _legenda(vol: ResultadoVolumetria) -> str:
    usos = list(dict.fromkeys(b.uso_predominante for b in vol.pavimentos))
    chips = []
    for uso in usos:
        r, g, b = cor_do_uso(uso)
        chips.append(
            f"<span style='display:inline-flex;align-items:center;gap:6px;margin:0 14px 6px 0;font-size:13px;'>"
            f"<span style='width:14px;height:14px;border-radius:3px;background:rgb({r},{g},{b});"
            f"display:inline-block;'></span>{uso}</span>"
        )
    chips.append(
        "<span style='display:inline-flex;align-items:center;gap:6px;margin:0 14px 6px 0;font-size:13px;'>"
        f"<span style='width:14px;height:14px;border:2px solid rgb{COR_TERRENO};display:inline-block;'></span>"
        "Terreno</span>"
    )
    if vol.gabarito_m:
        chips.append(
            "<span style='display:inline-flex;align-items:center;gap:6px;margin:0 14px 6px 0;font-size:13px;'>"
            f"<span style='width:14px;height:14px;border:2px dashed rgb{COR_GABARITO};display:inline-block;'></span>"
            f"Gabarito da zona ({_num(vol.gabarito_m)} m)</span>"
        )
    return "<div style='display:flex;flex-wrap:wrap;'>" + "".join(chips) + "</div>"


def renderizar_volumetria(resultado: ResultadoTerreno, quadro: QuadroAreas, indices: IndicesLegais) -> None:
    """Desenha o volume aproximado do edifício (pavimento a pavimento) sobre o mapa, em 3D."""
    titulo_secao(
        "Etapa 16 — Volume aproximado do edifício no mapa",
        "Massa 3D montada a partir do Quadro de Áreas: um bloco por pavimento, com o pé-direito e a área "
        "construída de cada andar, dentro dos recuos e da projeção máxima. Arraste para girar "
        "(Ctrl/⌘ + arrastar inclina) e passe o mouse sobre um pavimento para ver os dados.",
    )
    try:
        vol = calcular_volumetria(resultado.geojson_unificado_wgs84, quadro, indices)
    except ValueError as exc:
        nota(f"Não foi possível montar o volume: {exc}", "warn")
        return
    if not vol.pavimentos:
        nota("O Quadro de Áreas não tem pavimentos com área: preencha as Etapas 5 e 6.", "info")
        return

    for alerta in vol.alertas:
        nota(alerta, "warn")

    gabarito_txt = "Sem limite" if vol.gabarito_m is None else f"{_num(vol.gabarito_m)} m"
    grade_cards(
        [
            ("Altura aproximada", f"{_num(vol.altura_total_m)} m",
             f"Gabarito da zona: {gabarito_txt}"
             + ("" if vol.atende_gabarito is None else (" ✅" if vol.atende_gabarito else " ⚠️ acima"))),
            ("Pavimentos no volume", str(len(vol.pavimentos)), "Térreo, tipos e ático com área no quadro"),
            ("Volume construído", f"{_num(vol.volume_m3, 0)} m³", "Σ área × pé-direito"),
            ("Maior planta", f"{_num(vol.area_projecao_m2)} m²",
             f"Projeção máxima (T.O.): {_num(indices.area_ocupacao_max_m2 or 0)} m²"),
            ("Recuo lateral/fundo aplicado", f"{_num(vol.recuo_aplicado_m)} m", "Quadro 3 da LPUOS"),
        ]
    )

    col_opcoes, col_vista = st.columns([1, 1], vertical_alignment="center")
    mostrar_gabarito = col_opcoes.checkbox(
        "Mostrar o gabarito máximo da zona", value=vol.gabarito_m is not None,
        disabled=vol.gabarito_m is None, key="vol_mostrar_gabarito",
    )
    vista = col_vista.radio(
        "Vista", ["Perspectiva", "De cima"], horizontal=True, key="vol_vista", label_visibility="collapsed"
    )

    lat, lon = vol.centro_latlon
    deck = pdk.Deck(
        layers=_camadas(vol, mostrar_gabarito),
        initial_view_state=pdk.ViewState(
            latitude=lat,
            longitude=lon,
            zoom=_zoom_para_raio(
                max(raio_terreno_m(vol), vol.altura_total_m * 0.9) if vista == "Perspectiva" else raio_terreno_m(vol),
                lat,
            ),
            pitch=45 if vista == "Perspectiva" else 0,
            bearing=_bearing_obliquo(vol) if vista == "Perspectiva" else 0,
        ),
        map_provider="carto",
        map_style=pdk.map_styles.LIGHT,
        tooltip={
            "html": "<b>{nome}</b><br/>Uso: {uso}<br/>Área: {area} m²{aviso}<br/>"
                    "Piso a {base} m · pé-direito {pe_direito} m",
            "style": {"backgroundColor": "#111827", "color": "#fff", "fontSize": "12.5px"},
        },
    )
    st.pydeck_chart(deck, height=560, key=f"vol_deck_{vista}_{mostrar_gabarito}")
    st.markdown(_legenda(vol), unsafe_allow_html=True)
    st.caption(
        "Aproximação para estudo de massa: a planta mantém o formato do terreno, recuada e reduzida até a "
        "área de cada pavimento. Não substitui o projeto de arquitetura."
    )
