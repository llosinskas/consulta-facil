"""
Componente de Mapa Interativo (Folium) para visualização do lote/terreno.

Recursos gráficos:
- Contorno do terreno com halo branco (legível sobre mapa claro e satélite)
- Linhas de cota no estilo de desenho técnico: deslocadas para fora do terreno,
  com linhas de chamada nos vértices e medida alinhada ao lado
- Vértices numerados, etiqueta de SQL em cada lote (unificação)
- Legenda fixa, seta de norte, tela cheia, régua de medição e minimapa
- Camadas WMS oficiais do GeoSampa (lotes e zoneamento)
"""

import math
from html import escape
from typing import List, Optional, Tuple

import folium
from branca.element import MacroElement, Template
from folium.features import DivIcon
from folium.plugins import Fullscreen, MeasureControl, MiniMap
from pyproj import Transformer
from shapely.geometry import Point, mapping, shape
from shapely.ops import transform as shapely_transform

from config import CRS_UTM_SP, CRS_WGS84, DEFAULT_MAP_CENTER, DEFAULT_MAP_ZOOM, GEOSAMPA_WMS_URL
from domain.models import ResultadoTerreno
from services.geosampa_client import LOTES_EXEMPLO_SP, LOTES_VIZINHOS_DEMO_UTM

_TO_UTM = Transformer.from_crs(CRS_WGS84, CRS_UTM_SP, always_xy=True)
_TO_WGS = Transformer.from_crs(CRS_UTM_SP, CRS_WGS84, always_xy=True)

# Paleta
COR_TERRENO = "#d97706"      # âmbar escuro (contorno)
COR_TERRENO_FILL = "#fbbf24"  # âmbar (preenchimento)
COR_LOTE = "#2563eb"          # azul (divisas internas)
COR_COTA = "#111827"          # grafite (linhas de cota)
FONTE = "-apple-system, 'Segoe UI', Roboto, Arial, sans-serif"


def _latlon(x: float, y: float) -> Tuple[float, float]:
    lon, lat = _TO_WGS.transform(x, y)
    return lat, lon


def _fmt_m(v: float) -> str:
    return f"{v:.2f}".replace(".", ",") + " m"


def _fmt_m2(v: float) -> str:
    return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") + " m²"


def _rotulo_rotacionado(texto: str, angulo_tela: float, destaque: bool = False) -> DivIcon:
    """Etiqueta centrada no ponto e girada para acompanhar a direção do lado."""
    fundo = "#111827" if destaque else "#ffffff"
    cor = "#ffffff" if destaque else "#111827"
    html = (
        f"<div style=\"position:absolute; left:0; top:0; transform:translate(-50%,-50%) rotate({angulo_tela:.1f}deg);"
        f"background:{fundo}; color:{cor}; border:1px solid #9ca3af; border-radius:4px;"
        f"padding:1px 6px; font:600 12px {FONTE}; white-space:nowrap; line-height:16px;"
        f"box-shadow:0 1px 2px rgba(0,0,0,.18);\">{escape(texto)}</div>"
    )
    return DivIcon(html=html, icon_size=(0, 0), icon_anchor=(0, 0))


def _rotulo_simples(texto: str, estilo_extra: str = "") -> DivIcon:
    html = (
        f"<div style=\"position:absolute; left:0; top:0; transform:translate(-50%,-50%);"
        f"font:600 11px {FONTE}; white-space:nowrap; {estilo_extra}\">{escape(texto)}</div>"
    )
    return DivIcon(html=html, icon_size=(0, 0), icon_anchor=(0, 0))


def _adicionar_cotas(mapa_grupo: folium.FeatureGroup, resultado: ResultadoTerreno) -> None:
    """Desenha as linhas de cota de cada lado, deslocadas para fora do polígono."""
    poligono_utm = shapely_transform(
        _TO_UTM.transform, shape(resultado.geojson_unificado_wgs84["geometry"])
    )
    escala = math.sqrt(max(poligono_utm.area, 1.0))
    deslocamento = max(1.8, min(6.0, escala * 0.08))  # distância da cota ao lado (m)
    folga = deslocamento * 0.25                        # espaço entre o vértice e a linha de chamada

    for aresta in resultado.arestas:
        lat1, lon1 = aresta.ponto_inicial_latlon
        lat2, lon2 = aresta.ponto_final_latlon
        x1, y1 = _TO_UTM.transform(lon1, lat1)
        x2, y2 = _TO_UTM.transform(lon2, lat2)
        dx, dy = x2 - x1, y2 - y1
        comp = math.hypot(dx, dy)
        if comp < 0.5:
            continue

        # Normal unitária; inverte se apontar para dentro do terreno
        nx, ny = dy / comp, -dx / comp
        xm, ym = (x1 + x2) / 2, (y1 + y2) / 2
        if poligono_utm.contains(Point(xm + nx * 0.3, ym + ny * 0.3)):
            nx, ny = -nx, -ny

        # Linhas de chamada (dos vértices até um pouco além da linha de cota)
        for xv, yv in ((x1, y1), (x2, y2)):
            folium.PolyLine(
                [_latlon(xv + nx * folga, yv + ny * folga),
                 _latlon(xv + nx * (deslocamento + folga), yv + ny * (deslocamento + folga))],
                color=COR_COTA, weight=0.8, opacity=0.7,
            ).add_to(mapa_grupo)

        # Linha de cota com marcas nas extremidades
        a = (x1 + nx * deslocamento, y1 + ny * deslocamento)
        b = (x2 + nx * deslocamento, y2 + ny * deslocamento)
        folium.PolyLine([_latlon(*a), _latlon(*b)], color=COR_COTA, weight=1.2, opacity=0.9).add_to(mapa_grupo)

        tx, ty = dx / comp, dy / comp  # direção do lado
        marca = min(0.6, deslocamento * 0.3)
        for px, py in (a, b):
            # traço oblíquo a 45° (padrão de desenho arquitetônico)
            ox, oy = (tx + nx) * marca / math.sqrt(2), (ty + ny) * marca / math.sqrt(2)
            folium.PolyLine(
                [_latlon(px - ox, py - oy), _latlon(px + ox, py + oy)],
                color=COR_COTA, weight=1.6, opacity=0.9,
            ).add_to(mapa_grupo)

        # Texto da medida alinhado ao lado e sempre legível (nunca de cabeça para baixo)
        angulo = -math.degrees(math.atan2(dy, dx))
        if angulo > 90:
            angulo -= 180
        elif angulo < -90:
            angulo += 180
        folium.Marker(
            location=_latlon(xm + nx * deslocamento, ym + ny * deslocamento),
            icon=_rotulo_rotacionado(f"L{aresta.indice} · {_fmt_m(aresta.comprimento_m)}", angulo),
            tooltip=(
                f"Lado L{aresta.indice}: {_fmt_m(aresta.comprimento_m)} — "
                f"azimute {aresta.azimute_graus:.1f}° ({aresta.orientacao_cardeal})"
            ),
        ).add_to(mapa_grupo)


def _adicionar_vertices(grupo: folium.FeatureGroup, resultado: ResultadoTerreno) -> None:
    centro_lat, centro_lon = resultado.centroide_latlon
    cx, cy = _TO_UTM.transform(centro_lon, centro_lat)
    for aresta in resultado.arestas:
        lat, lon = aresta.ponto_inicial_latlon
        folium.CircleMarker(
            location=(lat, lon), radius=4, color=COR_COTA, weight=1.5,
            fill=True, fill_color="#ffffff", fill_opacity=1.0,
            tooltip=f"V{aresta.indice}: {lat:.6f}, {lon:.6f}",
        ).add_to(grupo)
        # Número do vértice levemente deslocado para dentro do terreno
        x, y = _TO_UTM.transform(lon, lat)
        d = math.hypot(cx - x, cy - y) or 1.0
        passo = min(1.8, d * 0.25)
        folium.Marker(
            location=_latlon(x + (cx - x) / d * passo, y + (cy - y) / d * passo),
            icon=_rotulo_simples(f"V{aresta.indice}", "color:#374151; text-shadow:0 0 3px #fff,0 0 3px #fff;"),
        ).add_to(grupo)


def _legenda(resultado: ResultadoTerreno, exibir_cotas: bool) -> MacroElement:
    zona = resultado.zoneamento.sigla_zona if resultado.zoneamento else "—"
    qtd_lotes = len(resultado.lotes)
    rotulo_terreno = f"Terreno unificado ({qtd_lotes} lotes)" if qtd_lotes > 1 else "Lote selecionado (1 lote)"
    linhas: List[str] = [
        f"<div style='display:flex;align-items:center;gap:8px;'>"
        f"<span style='width:18px;height:12px;background:{COR_TERRENO_FILL}66;border:2px solid {COR_TERRENO};"
        f"border-radius:2px;'></span>{escape(rotulo_terreno)}</div>",
        f"<div style='display:flex;align-items:center;gap:8px;'>"
        f"<span style='width:18px;border-top:2px dashed {COR_LOTE};'></span>Divisa de lote unitário (#1, #2…)</div>",
    ]
    if exibir_cotas:
        linhas.append(
            f"<div style='display:flex;align-items:center;gap:8px;'>"
            f"<span style='width:18px;border-top:1.5px solid {COR_COTA};'></span>Cota (medida do lado)</div>"
        )
    corpo = "".join(linhas)
    html = f"""
{{% macro html(this, kwargs) %}}
<div style="position:absolute; left:12px; bottom:38px; z-index:9999; background:rgba(255,255,255,.96);
            border:1px solid #e5e7eb; border-radius:10px; padding:10px 12px; font:12.5px {FONTE};
            color:#111827; box-shadow:0 2px 6px rgba(0,0,0,.12); max-width:270px; line-height:1.6;">
  <div style="font-weight:650; font-size:13px; margin-bottom:2px;">Área total: {_fmt_m2(resultado.area_total_m2)}</div>
  <div style="color:#4b5563; margin-bottom:6px;">Perímetro: {_fmt_m(resultado.perimetro_total_m)} · Zona {escape(zona)}</div>
  {corpo}
</div>
<div style="position:absolute; right:12px; bottom:34px; z-index:9999; width:44px; height:52px;
            background:rgba(255,255,255,.96); border:1px solid #e5e7eb; border-radius:10px;
            box-shadow:0 2px 6px rgba(0,0,0,.12); text-align:center; font:700 12px {FONTE}; color:#111827;">
  <svg width="22" height="28" viewBox="0 0 22 28" style="margin-top:5px;">
    <polygon points="11,1 19,25 11,19" fill="#111827"/>
    <polygon points="11,1 3,25 11,19" fill="#9ca3af"/>
  </svg>
  <div style="margin-top:-4px;">N</div>
</div>
{{% endmacro %}}
"""
    elemento = MacroElement()
    elemento._template = Template(html)
    return elemento


def _popup_terreno_html(resultado: ResultadoTerreno) -> str:
    """Monta a ficha completa em HTML exibida ao clicar diretamente sobre o terreno no mapa."""
    zona = resultado.zoneamento.sigla_zona if resultado.zoneamento else "Não identificada"
    sqls = ", ".join(l.sql_formatado for l in resultado.lotes)
    mz = resultado.macrozona.valor if (resultado.macrozona and resultado.macrozona.valor) else "—"
    ma = resultado.macroarea.valor if (resultado.macroarea and resultado.macroarea.valor) else "—"
    qa = (
        resultado.qualificacao_ambiental.valor
        if (resultado.qualificacao_ambiental and resultado.qualificacao_ambiental.valor)
        else "—"
    )
    lat_c, lon_c = resultado.centroide_latlon
    e_utm, n_utm = getattr(resultado, "ponto_utm", (0.0, 0.0))

    return (
        f"<div style='font:12.5px {FONTE}; color:#111827; min-width:270px; max-width:340px; line-height:1.45;'>"
        f"<div style='font-size:11px; text-transform:uppercase; color:#6b7280; letter-spacing:.04em;'>"
        f"Ficha do Terreno Selecionado</div>"
        f"<div style='font-size:15px; font-weight:700; margin:2px 0 8px 0; color:#111827;'>"
        f"SQL {escape(sqls)}</div>"
        f"<table style='width:100%; border-collapse:collapse; font-size:12.5px;'>"
        f"<tr><td style='padding:3px 0; color:#4b5563;'>Área total:</td>"
        f"<td style='padding:3px 0; font-weight:600; text-align:right;'>{_fmt_m2(resultado.area_total_m2)}</td></tr>"
        f"<tr><td style='padding:3px 0; color:#4b5563;'>Perímetro:</td>"
        f"<td style='padding:3px 0; font-weight:600; text-align:right;'>{_fmt_m(resultado.perimetro_total_m)}</td></tr>"
        f"<tr><td style='padding:3px 0; color:#4b5563;'>Testada × Profundidade:</td>"
        f"<td style='padding:3px 0; font-weight:600; text-align:right;'>"
        f"{_fmt_m(resultado.testada_principal_m)} × {_fmt_m(resultado.profundidade_estimada_m)}</td></tr>"
        f"<tr style='border-top:1px solid #e5e7eb;'><td style='padding:4px 0 2px 0; color:#4b5563;'>Zona (LPUOS):</td>"
        f"<td style='padding:4px 0 2px 0; font-weight:700; color:#92400e; text-align:right;'>{escape(zona)}</td></tr>"
        f"<tr><td style='padding:2px 0; color:#4b5563;'>Potencial básico / máx.:</td>"
        f"<td style='padding:2px 0; font-weight:600; text-align:right;'>"
        f"{_fmt_m2(resultado.potencial_construtivo_basico_m2)} / {_fmt_m2(resultado.potencial_construtivo_maximo_m2)}</td></tr>"
        f"<tr style='border-top:1px solid #e5e7eb;'><td colspan='2' style='padding:4px 0 2px 0; color:#4b5563;'>"
        f"<b>Macrozona:</b> {escape(mz)}</td></tr>"
        f"<tr><td colspan='2' style='padding:2px 0; color:#4b5563;'>"
        f"<b>Macroárea:</b> {escape(ma)}</td></tr>"
        f"<tr><td colspan='2' style='padding:2px 0; color:#4b5563;'>"
        f"<b>Qualificação ambiental:</b> {escape(qa)}</td></tr>"
        f"<tr style='border-top:1px solid #e5e7eb;'><td colspan='2' style='padding:4px 0 0 0; font-size:11px; color:#6b7280;'>"
        f"Ponto: {lat_c:.6f}, {lon_c:.6f} (UTM E {e_utm:,.1f}, N {n_utm:,.1f})</td></tr>"
        f"</table></div>"
    )


def construir_mapa_terreno(
    resultado: Optional[ResultadoTerreno] = None,
    exibir_cotas_arestas: bool = True,
    exibir_wms_geosampa: bool = True,
    ponto_clicado_latlon: Optional[Tuple[float, float]] = None,
) -> folium.Map:
    """Cria o mapa interativo centralizado no terreno analisado (ou no centro de SP)."""
    centro = resultado.centroide_latlon if resultado else DEFAULT_MAP_CENTER
    mapa = folium.Map(
        location=centro,
        zoom_start=19 if resultado else DEFAULT_MAP_ZOOM,
        max_zoom=22,
        tiles=None,
        control_scale=True,
    )

    # Mapas de fundo
    folium.TileLayer(
        tiles="https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png",
        attr="&copy; OpenStreetMap &copy; CARTO",
        name="Mapa claro",
        max_zoom=22, max_native_zoom=19,
    ).add_to(mapa)
    folium.TileLayer(
        tiles="https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        attr="Esri World Imagery",
        name="Satélite",
        max_zoom=22, max_native_zoom=19,
    ).add_to(mapa)
    folium.TileLayer(
        tiles="OpenStreetMap",
        name="Ruas (OpenStreetMap)",
        max_zoom=22, max_native_zoom=19,
    ).add_to(mapa)

    # Camadas oficiais do GeoSampa
    if exibir_wms_geosampa:
        folium.raster_layers.WmsTileLayer(
            url=GEOSAMPA_WMS_URL, layers="geoportal:lote_cidadao",
            name="GeoSampa · Lotes", fmt="image/png", transparent=True,
            overlay=True, show=True, opacity=0.55, max_zoom=22,
        ).add_to(mapa)
        folium.raster_layers.WmsTileLayer(
            url=GEOSAMPA_WMS_URL, layers="geoportal:zoneamento_2016_map1",
            name="GeoSampa · Zoneamento", fmt="image/png", transparent=True,
            overlay=True, show=False, opacity=0.45, max_zoom=22,
        ).add_to(mapa)
        if resultado:
            for info in (resultado.macrozona, resultado.macroarea, resultado.qualificacao_ambiental):
                if info and info.camada:
                    folium.raster_layers.WmsTileLayer(
                        url=GEOSAMPA_WMS_URL, layers=info.camada,
                        name=f"GeoSampa · {info.tema}", fmt="image/png", transparent=True,
                        overlay=True, show=False, opacity=0.45, max_zoom=22,
                    ).add_to(mapa)

    # Ferramentas
    Fullscreen(position="topleft", title="Tela cheia", title_cancel="Sair da tela cheia").add_to(mapa)
    MeasureControl(
        position="topleft", primary_length_unit="meters", secondary_length_unit=None,
        primary_area_unit="sqmeters", secondary_area_unit=None,
    ).add_to(mapa)
    MiniMap(toggle_display=True, minimized=True, position="bottomright", width=140, height=110).add_to(mapa)

    if not resultado:
        folium.LayerControl(collapsed=False).add_to(mapa)
        return mapa

    zona = resultado.zoneamento.sigla_zona if resultado.zoneamento else "—"
    sqls = ", ".join(l.sql_formatado for l in resultado.lotes)
    dica_terreno = (
        f"<div style='font:13px {FONTE}; line-height:1.5;'>"
        f"<b>SQL:</b> {escape(sqls)}<br>"
        f"<b>Área:</b> {_fmt_m2(resultado.area_total_m2)}<br>"
        f"<b>Perímetro:</b> {_fmt_m(resultado.perimetro_total_m)}<br>"
        f"<b>Testada estimada:</b> {_fmt_m(resultado.testada_principal_m)}<br>"
        f"<b>Zona:</b> {escape(zona)}</div>"
    )

    # Terreno: halo branco + preenchimento + contorno
    grupo_terreno = folium.FeatureGroup(name="Terreno analisado", show=True)
    folium.GeoJson(
        resultado.geojson_unificado_wgs84,
        style_function=lambda _: {"color": "#ffffff", "weight": 8, "opacity": 0.9, "fillOpacity": 0},
        interactive=False,
    ).add_to(grupo_terreno)
    folium.GeoJson(
        resultado.geojson_unificado_wgs84,
        style_function=lambda _: {
            "color": COR_TERRENO, "weight": 3, "fillColor": COR_TERRENO_FILL, "fillOpacity": 0.28,
        },
        highlight_function=lambda _: {"fillOpacity": 0.45, "weight": 4},
        tooltip=folium.Tooltip(dica_terreno, sticky=True),
        popup=folium.Popup(_popup_terreno_html(resultado), max_width=360),
    ).add_to(grupo_terreno)
    grupo_terreno.add_to(mapa)

    # Divisas internas e etiqueta de SQL de cada lote selecionado no estudo
    grupo_lotes = folium.FeatureGroup(name="Lotes selecionados (#1, #2…)", show=True)
    for idx_lote, lote in enumerate(resultado.lotes, start=1):
        if resultado.unificado:
            folium.GeoJson(
                lote.geojson_wgs84,
                style_function=lambda _: {
                    "color": COR_LOTE, "weight": 1.8, "dashArray": "6 4", "fillOpacity": 0.04,
                },
                tooltip=(
                    f"Lote Unitário #{idx_lote} · SQL {lote.sql_formatado} · {_fmt_m2(lote.area_cartografica_m2)} "
                    f"(clique para alternar seleção)"
                ),
                popup=folium.Popup(
                    f"<div style='font:12.5px {FONTE}; min-width:210px;'>"
                    f"<b>Lote Unitário #{idx_lote} · SQL {escape(lote.sql_formatado)}</b><br>"
                    f"Área unitária: {_fmt_m2(lote.area_cartografica_m2)}<br>"
                    f"Testada × Prof.: {_fmt_m(lote.testada_estimada_m)} × {_fmt_m(lote.profundidade_estimada_m)}<br>"
                    f"Perímetro unitário: {_fmt_m(lote.perimetro_m)}</div>",
                    max_width=270,
                ),
            ).add_to(grupo_lotes)
        ponto = shape(lote.geojson_wgs84["geometry"]).representative_point()
        folium.Marker(
            location=(ponto.y, ponto.x),
            icon=_rotulo_simples(
                f"#{idx_lote} · {lote.sql_formatado}",
                f"color:{COR_LOTE}; background:rgba(255,255,255,.94); padding:2px 6px;"
                "border-radius:4px; border:1px solid #93c5fd; box-shadow:0 1px 2px rgba(0,0,0,.1);",
            ),
            tooltip=f"Lote Unitário #{idx_lote}: SQL {lote.sql_formatado} ({_fmt_m2(lote.area_cartografica_m2)})",
        ).add_to(grupo_lotes)
    grupo_lotes.add_to(mapa)

    # Lotes vizinhos de demonstração próximos (para facilitar clique multi-lote mesmo sem rede)
    sqls_atuais = {l.sql_formatado for l in resultado.lotes}
    cx_utm, cy_utm = _TO_UTM.transform(resultado.centroide_latlon[1], resultado.centroide_latlon[0])
    pt_centro_utm = Point(cx_utm, cy_utm)
    candidatos_vizinhos = list(LOTES_VIZINHOS_DEMO_UTM)
    for d_ex in LOTES_EXEMPLO_SP.values():
        candidatos_vizinhos.extend(d_ex.get("features_utm", []))

    grupo_vizinhos = folium.FeatureGroup(name="Lotes vizinhos (clique para adicionar)", show=True)
    adicionou_vizinho = False
    for feat_v in candidatos_vizinhos:
        props_v = feat_v.get("properties") or {}
        sql_v = (
            f"{props_v.get('cd_setor_fiscal', '000')}."
            f"{props_v.get('cd_quadra_fiscal', '000')}."
            f"{props_v.get('cd_lote', '0000')}"
        )
        if sql_v in sqls_atuais:
            continue
        geom_v_utm = shape(feat_v["geometry"])
        if geom_v_utm.distance(pt_centro_utm) <= 120.0:
            geom_v_wgs = shapely_transform(_TO_WGS.transform, geom_v_utm)
            folium.GeoJson(
                {"type": "Feature", "properties": props_v, "geometry": mapping(geom_v_wgs)},
                style_function=lambda _: {
                    "color": "#64748b",
                    "weight": 1.6,
                    "dashArray": "4 4",
                    "fillColor": "#94a3b8",
                    "fillOpacity": 0.14,
                },
                highlight_function=lambda _: {"color": COR_LOTE, "weight": 2.5, "fillOpacity": 0.28},
                tooltip=(
                    f"Lote vizinho SQL {sql_v} ({_fmt_m2(geom_v_utm.area)}) — "
                    "Clique para selecionar/adicionar este lote ao estudo"
                ),
            ).add_to(grupo_vizinhos)
            pt_v = geom_v_wgs.representative_point()
            folium.Marker(
                location=(pt_v.y, pt_v.x),
                icon=_rotulo_simples(
                    f"+ {sql_v}",
                    "color:#475569; background:rgba(255,255,255,.88); padding:1px 5px;"
                    "border-radius:4px; border:1px dashed #94a3b8;",
                ),
                tooltip=f"Clique para adicionar o lote {sql_v} à seleção",
            ).add_to(grupo_vizinhos)
            adicionou_vizinho = True

    if adicionou_vizinho:
        grupo_vizinhos.add_to(mapa)

    # Marcador visual do último ponto clicado pelo usuário no mapa
    if ponto_clicado_latlon:
        folium.CircleMarker(
            location=ponto_clicado_latlon,
            radius=7,
            color="#dc2626",
            weight=2.5,
            fill=True,
            fill_color="#ef4444",
            fill_opacity=0.85,
            tooltip=f"Ponto clicado: {ponto_clicado_latlon[0]:.6f}, {ponto_clicado_latlon[1]:.6f}",
        ).add_to(mapa)

    # Cotas e vértices
    if exibir_cotas_arestas and resultado.arestas:
        grupo_cotas = folium.FeatureGroup(name="Cotas e vértices", show=True)
        _adicionar_cotas(grupo_cotas, resultado)
        _adicionar_vertices(grupo_cotas, resultado)
        grupo_cotas.add_to(mapa)

    mapa.get_root().add_child(_legenda(resultado, exibir_cotas_arestas))

    # Enquadra o terreno com margem para as cotas e a legenda
    min_lon, min_lat, max_lon, max_lat = resultado.bbox_latlon
    margem_lat = max((max_lat - min_lat) * 0.45, 0.00012)
    margem_lon = max((max_lon - min_lon) * 0.45, 0.00012)
    mapa.fit_bounds([[min_lat - margem_lat, min_lon - margem_lon], [max_lat + margem_lat, max_lon + margem_lon]])

    folium.LayerControl(collapsed=False, position="topright").add_to(mapa)
    return mapa
