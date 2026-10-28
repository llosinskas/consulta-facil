"""
Motor de Análise Geoespacial em Python (Shapely + PyProj).
Calcula área exata em SIRGAS 2000 UTM 23S (EPSG:31983), perímetro, comprimentos das arestas,
azimutes, retângulo envolvente mínimo (largura x profundidade), unificação de lotes (remembramento)
e cruzamento espacial com Zoneamento, Topografia e Tombamento do GeoSampa.
"""

import math
import re
from typing import Any, Dict, List, Optional, Tuple
from pyproj import Transformer
from shapely.geometry import MultiPolygon, Polygon, mapping, shape
from shapely.ops import transform as shapely_transform, unary_union

from config import CRS_UTM_SP, CRS_WGS84
from domain.models import (
    DadosTopografia,
    InfoTerritorial,
    LoteIndividual,
    ResultadoTerreno,
    SegmentoAresta,
)
from domain.zoning_rules import obter_parametros_zoneamento
from services.geosampa_client import GeoSampaWFSClient

_UTM_TO_WGS84 = Transformer.from_crs(CRS_UTM_SP, CRS_WGS84, always_xy=True)
_WGS84_TO_UTM = Transformer.from_crs(CRS_WGS84, CRS_UTM_SP, always_xy=True)


def _eh_coordenada_wgs84(geom: Any) -> bool:
    """Detecta se a geometria já veio em graus (Lon/Lat ~ -46, -23) ao invés de metros UTM (~330000, 7390000)."""
    minx, miny, _, _ = geom.bounds
    return abs(minx) <= 180.0 and abs(miny) <= 90.0


def _garantir_geometria_utm(geom_bruta: Any) -> Any:
    """Garante que a geometria Shapely esteja em metros (EPSG:31983)."""
    if _eh_coordenada_wgs84(geom_bruta):
        return shapely_transform(_WGS84_TO_UTM.transform, geom_bruta)
    return geom_bruta


def _converter_para_wgs84(geom_utm: Any) -> Any:
    """Converte geometria em metros (EPSG:31983) para Latitude/Longitude (EPSG:4326)."""
    return shapely_transform(_UTM_TO_WGS84.transform, geom_utm)


def _calcular_azimute_e_cardeal(dx: float, dy: float) -> Tuple[float, str]:
    """Calcula o azimute (0° = Norte, sentido horário) e a direção cardeal correspondente."""
    ang_rad = math.atan2(dx, dy)
    azimute = (math.degrees(ang_rad) + 360.0) % 360.0
    direcoes = ["N", "NE", "L", "SE", "S", "SO", "O", "NO"]
    idx = int((azimute + 22.5) // 45.0) % 8
    return round(azimute, 1), direcoes[idx]


def _extrair_arestas(poligono_utm: Any) -> List[SegmentoAresta]:
    """
    Extrai os segmentos de reta (lados/arestas) do anel externo do terreno,
    simplificando pequenos vértices colineares (< 8cm) para apresentar cotas limpas.
    """
    if isinstance(poligono_utm, MultiPolygon):
        poligono_principal = max(poligono_utm.geoms, key=lambda g: g.area)
    elif isinstance(poligono_utm, Polygon):
        poligono_principal = poligono_utm
    else:
        return []

    simplificado = poligono_principal.simplify(0.08, preserve_topology=True)
    if not isinstance(simplificado, Polygon):
        simplificado = poligono_principal

    coords_utm = list(simplificado.exterior.coords)
    arestas: List[SegmentoAresta] = []

    idx_aresta = 1
    for i in range(len(coords_utm) - 1):
        x1, y1 = coords_utm[i][0], coords_utm[i][1]
        x2, y2 = coords_utm[i + 1][0], coords_utm[i + 1][1]
        dx = x2 - x1
        dy = y2 - y1
        comp = math.hypot(dx, dy)
        if comp < 0.30:  # Ignora micro-segmentos menores que 30cm
            continue

        lon1, lat1 = _UTM_TO_WGS84.transform(x1, y1)
        lon2, lat2 = _UTM_TO_WGS84.transform(x2, y2)
        xm, ym = (x1 + x2) / 2.0, (y1 + y2) / 2.0
        lon_m, lat_m = _UTM_TO_WGS84.transform(xm, ym)
        azimute, cardeal = _calcular_azimute_e_cardeal(dx, dy)

        arestas.append(
            SegmentoAresta(
                indice=idx_aresta,
                ponto_inicial_latlon=(lat1, lon1),
                ponto_final_latlon=(lat2, lon2),
                ponto_medio_latlon=(lat_m, lon_m),
                comprimento_m=round(comp, 2),
                azimute_graus=azimute,
                orientacao_cardeal=cardeal,
            )
        )
        idx_aresta += 1

    return arestas


def _estimar_dimensoes_retangulo_minimo(poligono_utm: Any) -> Tuple[float, float, float]:
    """
    Calcula o Minimum Rotated Rectangle (menor retângulo envolvente) do terreno
    para estimar largura (menor dimensão / testada típica), profundidade (maior dimensão)
    e fator de regularidade (Área do Lote / Área do Retângulo Envolvente).
    """
    rect = poligono_utm.minimum_rotated_rectangle
    if not isinstance(rect, Polygon):
        lado = math.sqrt(max(poligono_utm.area, 1.0))
        return round(lado, 2), round(lado, 2), 1.0

    coords = list(rect.exterior.coords)
    if len(coords) < 4:
        lado = math.sqrt(max(poligono_utm.area, 1.0))
        return round(lado, 2), round(lado, 2), 1.0

    d1 = math.hypot(coords[1][0] - coords[0][0], coords[1][1] - coords[0][1])
    d2 = math.hypot(coords[2][0] - coords[1][0], coords[2][1] - coords[1][1])
    largura = min(d1, d2)
    profundidade = max(d1, d2)
    fator_reg = poligono_utm.area / rect.area if rect.area > 0 else 1.0
    return round(largura, 2), round(profundidade, 2), round(min(fator_reg, 1.0), 3)


def _extrair_sigla_zona_de_propriedades(props: Dict[str, Any]) -> Optional[str]:
    """Inspeciona um dicionário de propriedades WFS para encontrar a coluna que contém a sigla da Zona."""
    chaves_prioritarias = [
        "cd_zona",
        "sg_zona",
        "tx_zona",
        "zona",
        "cd_zoneamento",
        "sigla_zona",
        "nm_zona",
    ]
    for k in chaves_prioritarias:
        for prop_key, val in props.items():
            if prop_key.lower() == k and val:
                return str(val).strip()

    # Busca heurística por valores que começam com Z (ex: ZEU, ZM, ZC, ZER, ZCOR, ZEIS)
    for prop_key, val in props.items():
        if isinstance(val, str):
            v = val.strip().upper()
            if v.startswith(("ZEU", "ZM", "ZC", "ZER", "ZCOR", "ZEIS", "ZDE", "ZPI", "ZEM", "ZOE", "ZEPAM")):
                return val.strip()
    return None


def _extrair_cota_altimetrica(props: Dict[str, Any]) -> Optional[float]:
    """Extrai o valor numérico da cota (elevação em metros) de uma feição de curva de nível."""
    for chave, valor in props.items():
        if any(termo in chave.lower() for termo in ("cota", "elev", "alt", "vl_", "valor", "z")):
            try:
                num = float(str(valor).replace(",", "."))
                if 500.0 <= num <= 1300.0:  # Altitude típica do município de São Paulo
                    return num
            except (ValueError, TypeError):
                continue
    return None


def _descrever_feicao(props: Dict[str, Any], radicais: List[str]) -> Optional[str]:
    """
    Monta uma descrição legível a partir dos atributos de uma feição territorial.
    Prioriza campos cujo nome contém o radical do tema (ex.: 'macroarea', 'qualif', 'pqa')
    e depois campos descritivos (nm_, tx_, ds_, sg_, cd_). Combina nome por extenso e sigla.
    """
    def eh_texto_util(v: Any) -> bool:
        if not isinstance(v, str):
            return False
        s = v.strip()
        return len(s) >= 2 and not re.fullmatch(r"[\d\s.,:/\-T]+", s)

    tema_keys = [k for k in props if any(r in k.lower() for r in radicais)]
    desc_keys = [k for k in props if k.lower().startswith(("nm_", "tx_", "ds_", "sg_", "cd_", "nome", "sigla"))]
    candidatos = [str(props[k]).strip() for k in dict.fromkeys(tema_keys + desc_keys) if eh_texto_util(props[k])]

    # Caso o perímetro de qualificação ambiental venha como número (ex.: nr_perimetro = 5 -> "PA 5")
    if not candidatos:
        for k in tema_keys + desc_keys:
            val = props.get(k)
            if isinstance(val, (int, float)) or (isinstance(val, str) and val.strip().isdigit()):
                if any(r in k.lower() for r in ("perimetro", "qualif", "quota", "pqa", "pa")):
                    candidatos.append(f"PA {val}")
                    break

    if not candidatos:
        return None

    nome = max(candidatos, key=len)
    siglas = [c for c in candidatos if len(c) <= 12 and c != nome]
    if siglas and siglas[0].lower() not in nome.lower():
        return f"{nome} ({siglas[0]})"
    return nome


_TEMAS_TERRITORIAIS = {
    "macrozona": ("Macrozona", ["macrozona", "mz"]),
    "macroarea": ("Macroárea", ["macroarea", "macro_area", "ma_"]),
    "qualificacao_ambiental": ("Qualificação ambiental (Quota Ambiental)", ["qualif", "quota", "perimetro", "pqa", "pa_"]),
}


def _consultar_temas_territoriais(
    client: Optional[GeoSampaWFSClient],
    x_utm: float,
    y_utm: float,
    valores_iniciais: Optional[Dict[str, Optional[str]]] = None,
) -> Dict[str, InfoTerritorial]:
    """
    Executa a consulta espacial pelo ponto geográfico do lote (x_utm, y_utm em EPSG:31983)
    para identificar a Macrozona, a Macroárea e a Qualificação Ambiental incidentes.
    """
    lon, lat = _UTM_TO_WGS84.transform(x_utm, y_utm)
    ponto_latlon = (round(lat, 6), round(lon, 6))
    ponto_utm = (round(x_utm, 2), round(y_utm, 2))
    iniciais = valores_iniciais or {}

    resultado: Dict[str, InfoTerritorial] = {}
    for chave, (rotulo, radicais) in _TEMAS_TERRITORIAIS.items():
        if client is None:
            val_ini = iniciais.get(chave)
            obs_ini = (
                f"Referência demonstrativa no ponto ({ponto_latlon[0]:.5f}, {ponto_latlon[1]:.5f}) — clique em consultar no GeoSampa para validar online"
                if val_ini
                else "Não consultado (exemplo offline)"
            )
            resultado[chave] = InfoTerritorial(
                tema=rotulo,
                valor=val_ini,
                observacao=obs_ini,
                ponto_latlon=ponto_latlon,
                ponto_utm=ponto_utm,
            )
            continue
        try:
            feats, camada = client.consultar_camada_no_ponto(chave, x_utm, y_utm)
        except Exception as exc:  # falha de rede não deve derrubar a análise
            resultado[chave] = InfoTerritorial(
                tema=rotulo,
                observacao=f"Erro na consulta pelo ponto: {exc}",
                ponto_latlon=ponto_latlon,
                ponto_utm=ponto_utm,
            )
            continue
        if not feats:
            camadas = client.resolver_camadas(chave)
            obs = (
                f"Nenhuma feição encontrada no ponto ({ponto_latlon[0]:.5f}, {ponto_latlon[1]:.5f})."
                if camadas
                else "Camada não localizada ou indisponível no GeoSampa."
            )
            resultado[chave] = InfoTerritorial(
                tema=rotulo,
                observacao=obs,
                ponto_latlon=ponto_latlon,
                ponto_utm=ponto_utm,
            )
            continue
        props = feats[0].get("properties") or {}
        valor = _descrever_feicao(props, radicais)
        resultado[chave] = InfoTerritorial(
            tema=rotulo,
            valor=valor,
            camada=camada,
            atributos=props,
            observacao=(
                f"Consultado pelo ponto ({ponto_latlon[0]:.5f}, {ponto_latlon[1]:.5f}) na camada {camada}"
                if valor
                else f"Camada {camada} sem campo descritivo — veja os atributos."
            ),
            ponto_latlon=ponto_latlon,
            ponto_utm=ponto_utm,
        )
    return resultado


def consultar_enquadramento_pelo_ponto_do_lote(
    resultado: ResultadoTerreno, client: GeoSampaWFSClient
) -> ResultadoTerreno:
    """
    A partir do ponto geográfico do lote já localizado (centroide / ponto representativo),
    realiza uma nova consulta espacial no GeoSampa para buscar:
    - Macrozona
    - Macroárea
    - Qualificação Ambiental (Perímetro de Qualificação Ambiental / Quota Ambiental)
    - Zoneamento no ponto (caso ainda não identificado)
    """
    if not hasattr(client, "consultar_camada_no_ponto"):
        client = GeoSampaWFSClient()

    if getattr(resultado, "ponto_utm", (0.0, 0.0)) != (0.0, 0.0):
        x_utm, y_utm = resultado.ponto_utm
    else:
        lat, lon = resultado.centroide_latlon
        x_utm, y_utm = _WGS84_TO_UTM.transform(lon, lat)
        resultado.ponto_utm = (round(x_utm, 2), round(y_utm, 2))

    territoriais = _consultar_temas_territoriais(client, x_utm, y_utm)
    resultado.macrozona = territoriais["macrozona"]
    resultado.macroarea = territoriais["macroarea"]
    resultado.qualificacao_ambiental = territoriais["qualificacao_ambiental"]

    # Também verifica o zoneamento no mesmo ponto geográfico
    try:
        feats_zon, _ = client.consultar_camada_no_ponto("zoneamento", x_utm, y_utm)
        for fz in feats_zon:
            sigla = _extrair_sigla_zona_de_propriedades(fz.get("properties") or {})
            if sigla:
                if sigla not in resultado.zonas_detectadas:
                    resultado.zonas_detectadas.insert(0, sigla)
                resultado.zoneamento = obter_parametros_zoneamento(sigla)
                break
    except Exception:
        pass

    return resultado


def processar_terreno_completo(
    features_lotes: List[Dict[str, Any]],
    client: Optional[GeoSampaWFSClient] = None,
    endereco_referencia: Optional[str] = None,
    zona_forcada: Optional[str] = None,
    cota_min_forcada: Optional[float] = None,
    cota_max_forcada: Optional[float] = None,
    valores_territoriais_iniciais: Optional[Dict[str, Optional[str]]] = None,
    fonte_dados: str = "GeoSampa WFS Oficial",
) -> ResultadoTerreno:
    """
    Processa uma lista de features de lotes (1 ou vários lotes para unificação),
    calcula todas as métricas geométricas e realiza o cruzamento espacial com
    Zoneamento, Topografia e Tombamento.
    """
    lotes_individuais: List[LoteIndividual] = []
    geometrias_utm: List[Any] = []
    avisos: List[str] = []
    zonas_detectadas: List[str] = []

    for idx, feat in enumerate(features_lotes):
        props = feat.get("properties") or {}
        geom_dict = feat.get("geometry")
        if not geom_dict:
            continue

        geom_raw = shape(geom_dict)
        geom_utm = _garantir_geometria_utm(geom_raw)
        geom_wgs84 = _converter_para_wgs84(geom_utm)
        geometrias_utm.append(geom_utm)

        setor = str(
            props.get("cd_setor_fiscal")
            or props.get("cd_setor")
            or props.get("setor")
            or "000"
        )
        quadra = str(
            props.get("cd_quadra_fiscal")
            or props.get("cd_quadra")
            or props.get("quadra")
            or "000"
        )
        lote = str(
            props.get("cd_lote")
            or props.get("lote")
            or f"{idx + 1:04d}"
        )
        sql_fmt = f"{setor}.{quadra}.{lote}"

        if "_aviso_fallback" in props:
            avisos.append(str(props["_aviso_fallback"]))

        zona_prop = _extrair_sigla_zona_de_propriedades(props)
        if zona_prop and zona_prop not in zonas_detectadas:
            zonas_detectadas.append(zona_prop)

        larg_ind, prof_ind, reg_ind = _estimar_dimensoes_retangulo_minimo(geom_utm)
        pt_ind = geom_wgs84.representative_point()

        lotes_individuais.append(
            LoteIndividual(
                setor=setor,
                quadra=quadra,
                lote=lote,
                sql_formatado=sql_fmt,
                area_cartografica_m2=round(geom_utm.area, 2),
                perimetro_m=round(geom_utm.length, 2),
                atributos_brutos=props,
                geojson_wgs84={
                    "type": "Feature",
                    "properties": {"sql": sql_fmt, **props},
                    "geometry": mapping(geom_wgs84),
                },
                zona_incidente=zona_prop,
                testada_estimada_m=larg_ind,
                profundidade_estimada_m=prof_ind,
                fator_regularidade=reg_ind,
                centroide_latlon=(round(pt_ind.y, 6), round(pt_ind.x, 6)),
            )
        )

    # Unifica todas as geometrias dos lotes selecionados (suporte a remembramento de múltiplos lotes)
    uniao_utm = unary_union(geometrias_utm)
    uniao_wgs84 = _converter_para_wgs84(uniao_utm)

    area_total = round(uniao_utm.area, 2)
    perimetro_total = round(uniao_utm.length, 2)
    largura_est, prof_est, fator_reg = _estimar_dimensoes_retangulo_minimo(uniao_utm)
    arestas = _extrair_arestas(uniao_utm)
    testada_principal = largura_est
    if arestas:
        # A testada principal em lotes urbanos costuma aproximar a largura frontal
        comprimentos = [a.comprimento_m for a in arestas]
        mais_proximo = min(comprimentos, key=lambda c: abs(c - largura_est))
        testada_principal = round(mais_proximo, 2)

    ponto_interno_wgs84 = uniao_wgs84.representative_point()
    centroide_latlon = (round(ponto_interno_wgs84.y, 6), round(ponto_interno_wgs84.x, 6))
    min_lon, min_lat, max_lon, max_lat = uniao_wgs84.bounds

    # Consultas espaciais complementares no WFS do GeoSampa (Zoneamento, Topografia, Tombamento)
    minx_utm, miny_utm, maxx_utm, maxy_utm = uniao_utm.bounds
    tombamento_detectado = False
    detalhes_tombamento: List[str] = []
    cotas_encontradas: List[float] = []

    if zona_forcada and zona_forcada not in zonas_detectadas:
        zonas_detectadas.insert(0, zona_forcada)

    if client is not None:
        # 1. Zoneamento (caso ainda não tenha vindo nos atributos do lote)
        if not zonas_detectadas:
            feats_zon = client.consultar_camada_espacial_bbox(
                "zoneamento", minx_utm, miny_utm, maxx_utm, maxy_utm
            )
            for fz in feats_zon:
                try:
                    g_zon = _garantir_geometria_utm(shape(fz["geometry"]))
                    if g_zon.intersects(uniao_utm.representative_point()) or g_zon.intersects(uniao_utm):
                        sigla = _extrair_sigla_zona_de_propriedades(fz.get("properties") or {})
                        if sigla and sigla not in zonas_detectadas:
                            zonas_detectadas.append(sigla)
                except Exception:
                    continue

        # 2. Topografia / Curvas de nível (com buffer de 10m para capturar curvas adjacentes ao lote)
        feats_curvas = client.consultar_camada_espacial_bbox(
            "curva_nivel", minx_utm - 10.0, miny_utm - 10.0, maxx_utm + 10.0, maxy_utm + 10.0
        )
        for fc in feats_curvas:
            cota = _extrair_cota_altimetrica(fc.get("properties") or {})
            if cota is not None:
                cotas_encontradas.append(cota)

        # 3. Patrimônio / Tombamento
        feats_tomb = client.consultar_camada_espacial_bbox(
            "tombamento", minx_utm, miny_utm, maxx_utm, maxy_utm
        )
        for ft in feats_tomb:
            try:
                g_tomb = _garantir_geometria_utm(shape(ft["geometry"]))
                if g_tomb.intersects(uniao_utm):
                    tombamento_detectado = True
                    p_tomb = ft.get("properties") or {}
                    nome_bem = (
                        p_tomb.get("nm_bem_tombado")
                        or p_tomb.get("tx_denominacao")
                        or p_tomb.get("ds_resolucao")
                        or "Incidência de Patrimônio Cultural / Tombamento"
                    )
                    if str(nome_bem) not in detalhes_tombamento:
                        detalhes_tombamento.append(str(nome_bem))
            except Exception:
                continue

    # Consolidação da Topografia
    if cota_min_forcada is not None and cota_max_forcada is not None:
        cotas_encontradas = [cota_min_forcada, cota_max_forcada]

    if cotas_encontradas:
        c_min = round(min(cotas_encontradas), 1)
        c_max = round(max(cotas_encontradas), 1)
        desnivel = round(c_max - c_min, 2)
        decliv_pct = round((desnivel / max(prof_est, 1.0)) * 100.0, 2)
        topografia = DadosTopografia(
            cota_min_m=c_min,
            cota_max_m=c_max,
            desnivel_m=desnivel,
            declividade_media_pct=decliv_pct,
            qtd_curvas_interceptadas=len(cotas_encontradas),
            observacao="Terreno plano (< 5%)" if decliv_pct < 5.0 else "Terreno com aclive/declive moderado",
        )
    else:
        topografia = DadosTopografia(
            observacao="Sem curvas de nível interceptando diretamente o lote (terreno predominantemente plano na quadra)."
        )

    sigla_principal = zonas_detectadas[0] if zonas_detectadas else None
    parametros_zona = obter_parametros_zoneamento(sigla_principal)

    # 2ª Consulta Espacial: Macrozona, Macroárea e Qualificação Ambiental pelo ponto geográfico do lote
    ponto_utm = uniao_utm.representative_point()
    coord_utm_tupla = (round(ponto_utm.x, 2), round(ponto_utm.y, 2))
    territoriais = _consultar_temas_territoriais(
        client, ponto_utm.x, ponto_utm.y, valores_iniciais=valores_territoriais_iniciais
    )

    geojson_unificado = {
        "type": "Feature",
        "properties": {
            "sqls": [l.sql_formatado for l in lotes_individuais],
            "area_m2": area_total,
            "perimetro_m": perimetro_total,
            "zona": sigla_principal or "Consulte Camada WMS",
        },
        "geometry": mapping(uniao_wgs84),
    }

    return ResultadoTerreno(
        lotes=lotes_individuais,
        unificado=len(lotes_individuais) > 1,
        area_total_m2=area_total,
        perimetro_total_m=perimetro_total,
        largura_estimada_m=largura_est,
        profundidade_estimada_m=prof_est,
        testada_principal_m=testada_principal,
        fator_regularidade=fator_reg,
        centroide_latlon=centroide_latlon,
        bbox_latlon=(min_lon, min_lat, max_lon, max_lat),
        geojson_unificado_wgs84=geojson_unificado,
        ponto_utm=coord_utm_tupla,
        arestas=arestas,
        zoneamento=parametros_zona,
        zonas_detectadas=zonas_detectadas,
        topografia=topografia,
        macrozona=territoriais["macrozona"],
        macroarea=territoriais["macroarea"],
        qualificacao_ambiental=territoriais["qualificacao_ambiental"],
        tombamento_detectado=tombamento_detectado,
        detalhes_tombamento=detalhes_tombamento,
        endereco_aproximado=endereco_referencia,
        fonte_dados=fonte_dados,
        avisos=avisos,
    )


def alternar_lote_na_selecao(
    lotes_atuais: List[LoteIndividual], novas_features: List[Dict[str, Any]]
) -> Tuple[List[Dict[str, Any]], str]:
    """
    Gerencia a seleção múltipla de lotes via clique no mapa:
    - Se o lote clicado ainda não está na seleção, adiciona-o à lista de lotes do estudo;
    - Se o lote clicado já está na seleção (e há mais de 1 lote selecionado), remove-o;
    Retorna (lista_de_features_atualizada, acao_realizada: 'adicionado' | 'removido' | 'mantido').
    """
    feats_atuais = [l.geojson_wgs84 for l in lotes_atuais]
    if not novas_features:
        return feats_atuais, "mantido"

    nova = novas_features[0]
    geom_nova_utm = _garantir_geometria_utm(shape(nova["geometry"]))
    pt_novo = geom_nova_utm.representative_point()
    props_nova = nova.get("properties") or {}
    sql_novo = (
        f"{props_nova.get('cd_setor_fiscal') or props_nova.get('cd_setor') or ''}."
        f"{props_nova.get('cd_quadra_fiscal') or props_nova.get('cd_quadra') or ''}."
        f"{props_nova.get('cd_lote') or props_nova.get('lote') or ''}"
    )

    indice_existente: Optional[int] = None
    for idx, lote_ex in enumerate(lotes_atuais):
        geom_ex_utm = _garantir_geometria_utm(shape(lote_ex.geojson_wgs84["geometry"]))
        mesmo_sql = (
            sql_novo != ".."
            and lote_ex.sql_formatado == sql_novo
            and not lote_ex.sql_formatado.endswith(".LOCAL")
        )
        mesma_geometria = geom_ex_utm.representative_point().distance(pt_novo) < 1.5
        if mesmo_sql or mesma_geometria:
            indice_existente = idx
            break

    if indice_existente is not None:
        if len(feats_atuais) > 1:
            feats_restantes = [f for i, f in enumerate(feats_atuais) if i != indice_existente]
            return feats_restantes, "removido"
        return feats_atuais, "mantido"

    return feats_atuais + [nova], "adicionado"


