"""
Cliente de integração com o servidor OGC WFS do GeoSampa (Prefeitura de São Paulo).
Suporta descoberta automática de schema (DescribeFeatureType), busca por SQL (Setor/Quadra/Lote),
busca espacial por ponto (clique no mapa / endereço geocodificado) e cruzamento com camadas
de Zoneamento, Curvas de Nível e Tombamento.
"""

import math
import re
import json
import unicodedata
import urllib3
from typing import Any, Dict, List, Optional, Tuple
import requests
from pyproj import Transformer
from shapely.geometry import Point, shape

from config import (
    CRS_UTM_SP,
    CRS_WGS84,
    GEOSAMPA_WFS_URLS,
    GEOSAMPA_WMS_URLS,
    LAYER_CANDIDATES,
    LAYER_EXCLUDE_TERMS,
    LAYER_KEYWORDS,
    REQUEST_TIMEOUT,
    SQL_FIELD_VARIATIONS,
)

# Desabilita avisos de certificado SSL caso o servidor da prefeitura apresente cadeia incompleta
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Transformadores de coordenadas (WGS84 <-> SIRGAS 2000 UTM 23S)
_TO_UTM = Transformer.from_crs(CRS_WGS84, CRS_UTM_SP, always_xy=True)
_TO_WGS84 = Transformer.from_crs(CRS_UTM_SP, CRS_WGS84, always_xy=True)


# Limites geográficos aproximados do Município de São Paulo (WGS84)
SP_LAT_MIN, SP_LAT_MAX = -24.05, -23.30
SP_LON_MIN, SP_LON_MAX = -46.85, -46.30


def normalizar_sql_input(setor: str, quadra: str, lote: str) -> Tuple[str, str, str]:
    """
    Normaliza os códigos de Setor (3 dígitos), Quadra (3 dígitos) e Lote (4 dígitos).
    Remove dígitos verificadores (ex: '-1', '-X') caso informados junto ao lote.
    """
    s = re.sub(r"\D", "", str(setor or "").strip()).zfill(3)[-3:]
    q = re.sub(r"\D", "", str(quadra or "").strip()).zfill(3)[-3:]
    lote_base = str(lote or "").strip().split("-")[0]
    l = re.sub(r"\D", "", lote_base).zfill(4)[-4:]
    return s, q, l


def validar_sql_input(
    setor: str, quadra: str, lote: str
) -> Tuple[Optional[Tuple[str, str, str]], Optional[str]]:
    """
    Valida os campos individuais de Setor, Quadra e Lote antes de consultar o GeoSampa.
    Retorna ((setor, quadra, lote), None) se válido, ou (None, mensagem_de_erro) se inválido.
    """
    s_dig = re.sub(r"\D", "", str(setor or "").strip())
    q_dig = re.sub(r"\D", "", str(quadra or "").strip())
    l_base = str(lote or "").strip().split("-")[0]
    l_dig = re.sub(r"\D", "", l_base)

    if not s_dig or not q_dig or not l_dig:
        return None, "Preencha Setor, Quadra e Lote com dígitos numéricos."

    s, q, l = normalizar_sql_input(setor, quadra, lote)
    if s == "000" or q == "000" or l == "0000":
        return None, f"Código SQL inválido ({s}.{q}.{l}). Setor, Quadra e Lote devem ser maiores que zero."

    return (s, q, l), None


def extrair_multiplos_sqls(texto_sql: str) -> List[Tuple[str, str, str]]:
    """
    Aceita uma string contendo um ou mais SQLs em formatos variados:
    - '012.034.0056'
    - '012.034.0056-1' ou '012.034.0056-X'
    - 'SQL 012.034.0056'
    - '0120340056' (10 dígitos) ou '01203400561' (11 dígitos com DV)
    - '012/034/0056, 012/034/0057'
    Retorna lista sem duplicatas de tuplas (setor, quadra, lote) válidas.
    """
    if not texto_sql or not str(texto_sql).strip():
        return []

    resultados: List[Tuple[str, str, str]] = []
    partes = re.split(r"[,\n;]+", str(texto_sql))
    for parte in partes:
        item = re.sub(r"^(?:sql|iptu)\s*[:\-]?\s*", "", parte.strip(), flags=re.IGNORECASE)
        if not item:
            continue
        # Formato separado por ponto, barra, hífen ou espaço: 012.034.0056(-1 ou -X)
        m = re.match(r"^(\d{1,3})[.\-/ ]+(\d{1,3})[.\-/ ]+(\d{1,4})(?:[.\-/ ][\dXx])?$", item)
        if m:
            validado, _ = validar_sql_input(m.group(1), m.group(2), m.group(3))
            if validado and validado not in resultados:
                resultados.append(validado)
            continue

        # Formato contínuo de 10 dígitos ou 11 caracteres (10 dígitos + DV numérico ou X)
        limpo = re.sub(r"[\s.\-/]", "", item)
        if re.fullmatch(r"\d{10}[\dXx]?", limpo):
            validado, _ = validar_sql_input(limpo[0:3], limpo[3:6], limpo[6:10])
            if validado and validado not in resultados:
                resultados.append(validado)

    return resultados


def validar_coordenadas_sp(
    lat_input: Any, lon_input: Any
) -> Tuple[Optional[Tuple[float, float]], Optional[str]]:
    """
    Converte e valida um par (latitude, longitude) verificando se está dentro dos limites
    geográficos do município de São Paulo.
    """
    try:
        lat = float(str(lat_input).strip().replace(",", "."))
        lon = float(str(lon_input).strip().replace(",", "."))
    except (ValueError, TypeError):
        return None, "Latitude e Longitude devem ser valores numéricos válidos."

    if math.isnan(lat) or math.isnan(lon) or math.isinf(lat) or math.isinf(lon):
        return None, "Latitude e Longitude não podem ser valores indefinidos (NaN/Inf)."

    if not (SP_LAT_MIN <= lat <= SP_LAT_MAX and SP_LON_MIN <= lon <= SP_LON_MAX):
        return (
            None,
            f"Coordenada ({lat:.6f}, {lon:.6f}) está fora dos limites do município de São Paulo "
            f"(Lat entre {SP_LAT_MIN} e {SP_LAT_MAX}, Lon entre {SP_LON_MIN} e {SP_LON_MAX}).",
        )

    return (lat, lon), None


class GeoSampaWFSClient:
    """Cliente resiliente para consumo de feições geográficas do GeoSampa via protocolo WFS."""

    def __init__(self) -> None:
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) EstudoViabilidadeGeoSampa/1.0",
                "Accept": "application/json, text/xml, */*",
            }
        )
        self._schema_cache: Dict[str, Dict[str, Any]] = {}
        self._active_wfs_url: str = GEOSAMPA_WFS_URLS[0]
        self._active_wms_url: str = GEOSAMPA_WMS_URLS[0]
        self._camadas_servidor: Optional[List[str]] = None
        self._catalogo_servidor: Optional[List[Dict[str, str]]] = None

    @staticmethod
    def _sem_acento(texto: str) -> str:
        nfkd = unicodedata.normalize("NFKD", texto or "")
        return "".join(c for c in nfkd if not unicodedata.combining(c)).lower()

    def listar_catalogo_camadas(self) -> List[Dict[str, str]]:
        """
        Extrai (uma vez por sessão) o catálogo de camadas publicadas no WFS do GeoSampa,
        incluindo <Name>, <Title> e <Abstract>, para localizar camadas mesmo quando o
        identificador técnico for abreviado e o nome por extenso estiver apenas no título.
        """
        if self._catalogo_servidor is not None:
            return self._catalogo_servidor

        params = {"service": "WFS", "version": "1.1.0", "request": "GetCapabilities"}
        resp = self._request_wfs(params, timeout=40)
        catalogo: List[Dict[str, str]] = []
        if resp and resp.text:
            blocos = re.findall(r"<FeatureType\b[^>]*>(.*?)</FeatureType>", resp.text, flags=re.DOTALL)
            for bloco in blocos:
                m_name = re.search(r"<Name>([^<]+)</Name>", bloco)
                if not m_name:
                    continue
                m_title = re.search(r"<Title>([^<]*)</Title>", bloco)
                m_abs = re.search(r"<Abstract>([^<]*)</Abstract>", bloco)
                nome = m_name.group(1).strip()
                titulo = m_title.group(1).strip() if m_title else ""
                resumo = m_abs.group(1).strip() if m_abs else ""
                catalogo.append(
                    {
                        "name": nome,
                        "title": titulo,
                        "search_text": self._sem_acento(f"{nome} {titulo} {resumo}"),
                    }
                )
            if not catalogo:
                for nome in re.findall(r"<Name>([^<]+)</Name>", resp.text):
                    catalogo.append({"name": nome, "title": "", "search_text": self._sem_acento(nome)})

        self._catalogo_servidor = catalogo
        self._camadas_servidor = [item["name"] for item in catalogo]
        return catalogo

    def listar_camadas(self) -> List[str]:
        """Lista os nomes técnicos (<Name>) de todas as camadas publicadas no WFS do GeoSampa."""
        if self._camadas_servidor is None:
            self.listar_catalogo_camadas()
        return self._camadas_servidor or []

    def resolver_camadas(self, tema: str) -> List[str]:
        """
        Camadas candidatas de um tema:
        1. Camadas cujo <Name> ou <Title> no GetCapabilities casa com as palavras-chave do tema;
        2. Nomes candidatos configurados em LAYER_CANDIDATES (excluindo legislações revogadas).
        """
        palavras = [self._sem_acento(p) for p in LAYER_KEYWORDS.get(tema, [])]
        termos_excluir = [self._sem_acento(t) for t in LAYER_EXCLUDE_TERMS]
        encontradas_nome: List[str] = []
        encontradas_titulo: List[str] = []

        if palavras:
            for item in self.listar_catalogo_camadas():
                nome = item["name"]
                nome_limpo = self._sem_acento(nome)
                texto_busca = item["search_text"]
                if any(t in texto_busca for t in termos_excluir):
                    continue
                if any(p in nome_limpo for p in palavras):
                    encontradas_nome.append(nome)
                elif any(p in texto_busca for p in palavras):
                    encontradas_titulo.append(nome)

        fixas = LAYER_CANDIDATES.get(tema, [])
        servidor = set(self._camadas_servidor or [])
        fixas_existentes = [c for c in fixas if servidor and c in servidor]
        fixas_restantes = [c for c in fixas if c not in fixas_existentes]
        return list(dict.fromkeys(encontradas_nome + fixas_existentes + encontradas_titulo + fixas_restantes))

    def consultar_camada_no_ponto(self, tema: str, x_utm: float, y_utm: float) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        """
        Segunda consulta espacial pelo Ponto Geográfico do Lote (x_utm, y_utm em EPSG:31983):
        1. Tenta WFS GetFeature com BBOX nativo ao redor do ponto (independe do nome da coluna geométrica);
        2. Tenta WFS GetFeature com CQL_FILTER INTERSECTS(geom_col, POINT(x y));
        3. Tenta WMS GetFeatureInfo no ponto exato como fallback.
        Retorna (lista de feições que contêm o ponto, nome da camada encontrada).
        """
        candidatas = self.resolver_camadas(tema)
        d = 0.5  # janela de 1 metro centrada no ponto geográfico do lote
        bbox_nativo = f"{x_utm - d:.2f},{y_utm - d:.2f},{x_utm + d:.2f},{y_utm + d:.2f},{CRS_UTM_SP}"
        bbox_simples = f"{x_utm - d:.2f},{y_utm - d:.2f},{x_utm + d:.2f},{y_utm + d:.2f}"

        for layer in candidatas:
            # Tentativa 1: BBOX OGC nativo no WFS 1.0.0 (não depende do nome da coluna de geometria)
            for bbox_val in (bbox_simples, bbox_nativo):
                params_bbox = {
                    "service": "WFS",
                    "version": "1.0.0",
                    "request": "GetFeature",
                    "typeName": layer,
                    "outputFormat": "application/json",
                    "BBOX": bbox_val,
                    "srsName": CRS_UTM_SP,
                    "maxFeatures": "5",
                }
                resp = self._request_wfs(params_bbox, timeout=10)
                if resp:
                    try:
                        feats = resp.json().get("features", [])
                        if feats:
                            return feats, layer
                    except ValueError:
                        pass

            # Tentativa 2: CQL_FILTER INTERSECTS com a coluna geométrica descoberta via DescribeFeatureType
            schema = self.descobrir_schema_camada(layer)
            colunas_geom = [schema["geom_col"]] if schema else ["geometria", "geom", "the_geom"]
            for geom_col in colunas_geom:
                params_cql = {
                    "service": "WFS",
                    "version": "1.0.0",
                    "request": "GetFeature",
                    "typeName": layer,
                    "outputFormat": "application/json",
                    "CQL_FILTER": f"INTERSECTS({geom_col}, POINT({x_utm:.2f} {y_utm:.2f}))",
                    "srsName": CRS_UTM_SP,
                    "maxFeatures": "5",
                }
                resp = self._request_wfs(params_cql, timeout=10)
                if resp:
                    try:
                        feats = resp.json().get("features", [])
                        if feats:
                            return feats, layer
                    except ValueError:
                        pass

            # Tentativa 3: WMS GetFeatureInfo no ponto geográfico do lote
            feats_wms = self._consultar_wms_feature_info_no_ponto(layer, x_utm, y_utm)
            if feats_wms:
                return feats_wms, layer

        return [], None

    def _consultar_wms_feature_info_no_ponto(
        self, layer: str, x_utm: float, y_utm: float
    ) -> List[Dict[str, Any]]:
        """Consulta WMS GetFeatureInfo em JSON centrado exatamente no ponto UTM (x_utm, y_utm) do lote."""
        d = 1.0
        params = {
            "SERVICE": "WMS",
            "VERSION": "1.1.1",
            "REQUEST": "GetFeatureInfo",
            "LAYERS": layer,
            "QUERY_LAYERS": layer,
            "SRS": CRS_UTM_SP,
            "BBOX": f"{x_utm - d:.2f},{y_utm - d:.2f},{x_utm + d:.2f},{y_utm + d:.2f}",
            "WIDTH": "3",
            "HEIGHT": "3",
            "X": "1",
            "Y": "1",
            "INFO_FORMAT": "application/json",
            "FEATURE_COUNT": "5",
        }
        urls_to_try = [self._active_wms_url] + [u for u in GEOSAMPA_WMS_URLS if u != self._active_wms_url]
        for url in urls_to_try:
            try:
                resp = self.session.get(url, params=params, timeout=8, verify=False)
                if resp.status_code == 200:
                    self._active_wms_url = url
                    feats = resp.json().get("features", [])
                    if feats:
                        return feats
            except (requests.RequestException, ValueError):
                continue
        return []

    def _request_wfs(self, params: Dict[str, str], timeout: int = REQUEST_TIMEOUT) -> Optional[requests.Response]:
        """Tenta realizar a requisição nos endpoints WFS configurados (HTTPS e HTTP fallback)."""
        urls_to_try = [self._active_wfs_url] + [u for u in GEOSAMPA_WFS_URLS if u != self._active_wfs_url]
        for url in urls_to_try:
            try:
                resp = self.session.get(url, params=params, timeout=timeout, verify=False)
                if resp.status_code == 200:
                    self._active_wfs_url = url
                    return resp
            except requests.RequestException:
                continue
        return None

    def descobrir_schema_camada(self, type_name: str) -> Optional[Dict[str, Any]]:
        """
        Consulta DescribeFeatureType em JSON para descobrir o nome exato da coluna de geometria
        e os atributos disponíveis na camada do GeoSampa.
        """
        if type_name in self._schema_cache:
            return self._schema_cache[type_name]

        params = {
            "service": "WFS",
            "version": "1.1.0",
            "request": "DescribeFeatureType",
            "typeName": type_name,
            "outputFormat": "application/json",
        }
        resp = self._request_wfs(params, timeout=8)
        if not resp:
            return None

        try:
            data = resp.json()
            feature_types = data.get("featureTypes", [])
            if not feature_types:
                return None
            props = feature_types[0].get("properties", [])
            geom_col = "geometria"
            prop_names = []
            for p in props:
                name = p.get("name", "")
                local_type = p.get("localType", "").lower()
                prop_names.append(name)
                if any(g in local_type for g in ("polygon", "geometry", "surface", "linestring", "point", "multiline")):
                    geom_col = name

            schema_info = {"geom_col": geom_col, "properties": prop_names}
            self._schema_cache[type_name] = schema_info
            return schema_info
        except (ValueError, KeyError):
            return None

    def consultar_lote_por_sql(
        self, setor: str, quadra: str, lote: str
    ) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        """
        Busca um lote no GeoSampa usando Setor, Quadra e Lote (SQL).
        Retorna (lista de features GeoJSON em EPSG:31983, mensagem_erro_opcional).
        """
        s, q, l = normalizar_sql_input(setor, quadra, lote)

        for layer in LAYER_CANDIDATES["lote"]:
            schema = self.descobrir_schema_camada(layer)
            prop_list = schema["properties"] if schema else []

            # Escolhe os nomes das colunas com base no schema real ou tenta as variações conhecidas
            variacoes = []
            for var in SQL_FIELD_VARIATIONS:
                if not prop_list or all(c in prop_list for c in var.values()):
                    variacoes.append(var)
            if not variacoes:
                variacoes = SQL_FIELD_VARIATIONS

            for campos in variacoes:
                cql = (
                    f"{campos['setor']}='{s}' AND "
                    f"{campos['quadra']}='{q}' AND "
                    f"{campos['lote']}='{l}'"
                )
                params = {
                    "service": "WFS",
                    "version": "1.0.0",
                    "request": "GetFeature",
                    "typeName": layer,
                    "outputFormat": "application/json",
                    "CQL_FILTER": cql,
                    "srsName": CRS_UTM_SP,
                    "maxFeatures": "20",
                }
                resp = self._request_wfs(params)
                if not resp:
                    continue

                try:
                    data = resp.json()
                    features = data.get("features", [])
                    if features:
                        return features, None
                except ValueError:
                    continue

        # Caso o lote específico não esteja individualizado (ex: quadra sem desdobro de lote no mapa),
        # tenta buscar a quadra fiscal correspondente como referência
        features_quadra = self._consultar_quadra_fallback(s, q)
        if features_quadra:
            for f in features_quadra:
                f.setdefault("properties", {})["_aviso_fallback"] = (
                    f"O lote {l} não possui polígono individualizado na camada pública; "
                    f"exibindo o polígono da Quadra Fiscal {s}.{q}."
                )
                f["properties"]["cd_setor_fiscal"] = s
                f["properties"]["cd_quadra_fiscal"] = q
                f["properties"]["cd_lote"] = l
            return features_quadra, None

        return [], f"Lote {s}.{q}.{l} não localizado na base WFS do GeoSampa ou serviço indisponível."

    def _consultar_quadra_fallback(self, setor: str, quadra: str) -> List[Dict[str, Any]]:
        """Busca o polígono da quadra fiscal caso o lote ainda não esteja individualizado."""
        for layer in LAYER_CANDIDATES["quadra"]:
            for col_setor, col_quadra in [("cd_setor_fiscal", "cd_quadra_fiscal"), ("cd_setor", "cd_quadra")]:
                cql = f"{col_setor}='{setor}' AND {col_quadra}='{quadra}'"
                params = {
                    "service": "WFS",
                    "version": "1.0.0",
                    "request": "GetFeature",
                    "typeName": layer,
                    "outputFormat": "application/json",
                    "CQL_FILTER": cql,
                    "srsName": CRS_UTM_SP,
                    "maxFeatures": "5",
                }
                resp = self._request_wfs(params, timeout=8)
                if resp:
                    try:
                        feats = resp.json().get("features", [])
                        if feats:
                            return feats
                    except ValueError:
                        pass
        return []

    def _selecionar_lote_mais_proximo_do_ponto(
        self, features: List[Dict[str, Any]], x_utm: float, y_utm: float
    ) -> List[Dict[str, Any]]:
        """Seleciona a feição cujo polígono contém o ponto clicado (ou a mais próxima dele)."""
        if not features:
            return []
        ponto = Point(x_utm, y_utm)
        for f in features:
            try:
                g = shape(f["geometry"])
                if g.contains(ponto) or g.intersects(ponto):
                    return [f]
            except Exception:
                continue
        # Se nenhuma continha exatamente o ponto (ex: clique na calçada junto à testada), pega a mais próxima
        try:
            mais_proxima = min(features, key=lambda f: shape(f["geometry"]).distance(ponto))
            return [mais_proxima]
        except Exception:
            return [features[0]]

    def consultar_lote_por_coordenada(
        self, lat: float, lon: float, raios_busca_m: Tuple[float, ...] = (3.0, 25.0, 60.0)
    ) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        """
        Localiza o lote que contém ou está mais próximo da coordenada (lat, lon) em WGS84.
        Usa raios progressivos (3m para clique direto no lote; 25m e 60m para endereços geocodificados
        no eixo da rua/logradouro) e faz fallback para a quadra fiscal caso o lote não esteja
        individualizado na camada vetorial pública.
        """
        coord_ok, erro_coord = validar_coordenadas_sp(lat, lon)
        if erro_coord or not coord_ok:
            return [], erro_coord

        lat_v, lon_v = coord_ok
        x_utm, y_utm = _TO_UTM.transform(lon_v, lat_v)

        # Verifica lote local primeiro caso seja clique direto sobre lote de demonstração
        lote_local = buscar_lote_local_por_ponto_utm(x_utm, y_utm)

        # 1. Busca na camada de lotes com raios progressivos (3m -> 25m -> 60m)
        for layer in LAYER_CANDIDATES["lote"]:
            schema = self.descobrir_schema_camada(layer)
            geom_col = schema["geom_col"] if schema else "geometria"

            for d in raios_busca_m:
                bbox_str = f"{x_utm - d:.2f},{y_utm - d:.2f},{x_utm + d:.2f},{y_utm + d:.2f}"

                # Tentativa A: BBOX OGC nativo no WFS
                params_bbox = {
                    "service": "WFS",
                    "version": "1.0.0",
                    "request": "GetFeature",
                    "typeName": layer,
                    "outputFormat": "application/json",
                    "BBOX": bbox_str,
                    "srsName": CRS_UTM_SP,
                    "maxFeatures": "15",
                }
                resp_b = self._request_wfs(params_bbox, timeout=10)
                if resp_b:
                    try:
                        feats = resp_b.json().get("features", [])
                        if feats:
                            return self._selecionar_lote_mais_proximo_do_ponto(feats, x_utm, y_utm), None
                    except ValueError:
                        pass

                # Tentativa B: CQL_FILTER INTERSECTS (no primeiro raio) e BBOX
                filtros_cql = [f"BBOX({geom_col}, {bbox_str})"]
                if d <= 5.0:
                    filtros_cql.insert(0, f"INTERSECTS({geom_col}, POINT({x_utm:.2f} {y_utm:.2f}))")

                for cql in filtros_cql:
                    params = {
                        "service": "WFS",
                        "version": "1.0.0",
                        "request": "GetFeature",
                        "typeName": layer,
                        "outputFormat": "application/json",
                        "CQL_FILTER": cql,
                        "srsName": CRS_UTM_SP,
                        "maxFeatures": "15",
                    }
                    resp = self._request_wfs(params, timeout=10)
                    if not resp:
                        continue
                    try:
                        feats = resp.json().get("features", [])
                        if feats:
                            return self._selecionar_lote_mais_proximo_do_ponto(feats, x_utm, y_utm), None
                    except ValueError:
                        continue

            # Tentativa C: WMS GetFeatureInfo para a camada de lote
            feats_wms = self._consultar_wms_feature_info_no_ponto(layer, x_utm, y_utm)
            if feats_wms and feats_wms[0].get("geometry"):
                return [feats_wms[0]], None

        # 2. Fallback: Busca na camada de Quadra Fiscal (quadras sem lotes individualizados no WFS)
        for layer_q in LAYER_CANDIDATES["quadra"]:
            for d_q in (10.0, 45.0):
                bbox_q = f"{x_utm - d_q:.2f},{y_utm - d_q:.2f},{x_utm + d_q:.2f},{y_utm + d_q:.2f}"
                params_q = {
                    "service": "WFS",
                    "version": "1.0.0",
                    "request": "GetFeature",
                    "typeName": layer_q,
                    "outputFormat": "application/json",
                    "BBOX": bbox_q,
                    "srsName": CRS_UTM_SP,
                    "maxFeatures": "10",
                }
                resp_q = self._request_wfs(params_q, timeout=10)
                if resp_q:
                    try:
                        feats_q = resp_q.json().get("features", [])
                        if feats_q:
                            escolhida = self._selecionar_lote_mais_proximo_do_ponto(feats_q, x_utm, y_utm)
                            escolhida[0].setdefault("properties", {})["_aviso_fallback"] = (
                                "O lote neste endereço não possui polígono individualizado na camada vetorial; "
                                "exibindo o polígono da Quadra Fiscal correspondente."
                            )
                            return escolhida, None
                    except ValueError:
                        pass

        if lote_local:
            return [lote_local], None

        return [], f"Nenhum lote vetorial encontrado nas coordenadas ({lat_v:.6f}, {lon_v:.6f})."

    def consultar_camada_espacial_bbox(
        self, tema: str, minx: float, miny: float, maxx: float, maxy: float
    ) -> List[Dict[str, Any]]:
        """
        Consulta feições de uma camada temática (zoneamento, curva_nivel, tombamento)
        que intersectam a Bounding Box (em EPSG:31983) do terreno.
        """
        candidatas = LAYER_CANDIDATES.get(tema, [])
        for layer in candidatas:
            schema = self.descobrir_schema_camada(layer)
            geom_col = schema["geom_col"] if schema else "geometria"
            cql = f"BBOX({geom_col}, {minx:.2f}, {miny:.2f}, {maxx:.2f}, {maxy:.2f})"
            params = {
                "service": "WFS",
                "version": "1.0.0",
                "request": "GetFeature",
                "typeName": layer,
                "outputFormat": "application/json",
                "CQL_FILTER": cql,
                "srsName": CRS_UTM_SP,
                "maxFeatures": "50",
            }
            resp = self._request_wfs(params, timeout=8)
            if not resp:
                continue
            try:
                feats = resp.json().get("features", [])
                if feats:
                    return feats
            except ValueError:
                continue
        return []


# Exemplos pré-carregados de lotes reais em São Paulo (para testes rápidos / modo demonstração offline)
LOTES_EXEMPLO_SP: Dict[str, Dict[str, Any]] = {
    "Av. Paulista (Bela Vista) - ZEU (Lote Comercial)": {
        "sql": ("009", "074", "0015"),
        "endereco": "Av. Paulista, Bela Vista - São Paulo/SP",
        "zona": "ZEU",
        "macrozona": "Macrozona de Estruturação e Qualificação Urbana",
        "macroarea": "Macroárea de Urbanização Consolidada (MUC)",
        "qualificacao_ambiental": "PA 5 (Perímetro de Qualificação Ambiental 5 — Quota Ambiental)",
        "cota_min": 816.0,
        "cota_max": 818.0,
        "features_utm": [
            {
                "type": "Feature",
                "properties": {
                    "cd_setor_fiscal": "009",
                    "cd_quadra_fiscal": "074",
                    "cd_lote": "0015",
                    "nm_logradouro": "AV PAULISTA",
                    "cd_zona": "ZEU",
                },
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [
                            [330980.0, 7393410.0],
                            [331008.0, 7393392.0],
                            [330978.0, 7393345.0],
                            [330950.0, 7393363.0],
                            [330980.0, 7393410.0],
                        ]
                    ],
                },
            }
        ],
    },
    "Pinheiros (Unificação de 3 Lotes Contíguos) - ZEU": {
        "sql": ("083", "112", "0021"),
        "endereco": "Rua dos Pinheiros, Pinheiros - São Paulo/SP (Remembramento de 3 Lotes)",
        "zona": "ZEU",
        "macrozona": "Macrozona de Estruturação e Qualificação Urbana",
        "macroarea": "Macroárea de Urbanização Consolidada (MUC)",
        "qualificacao_ambiental": "PA 4 (Perímetro de Qualificação Ambiental 4 — Quota Ambiental)",
        "cota_min": 742.0,
        "cota_max": 745.5,
        "features_utm": [
            {
                "type": "Feature",
                "properties": {
                    "cd_setor_fiscal": "083",
                    "cd_quadra_fiscal": "112",
                    "cd_lote": "0021",
                    "cd_zona": "ZEU",
                },
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [
                            [328110.0, 7392850.0],
                            [328120.0, 7392850.0],
                            [328120.0, 7392815.0],
                            [328110.0, 7392815.0],
                            [328110.0, 7392850.0],
                        ]
                    ],
                },
            },
            {
                "type": "Feature",
                "properties": {
                    "cd_setor_fiscal": "083",
                    "cd_quadra_fiscal": "112",
                    "cd_lote": "0022",
                    "cd_zona": "ZEU",
                },
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [
                            [328120.0, 7392850.0],
                            [328130.0, 7392850.0],
                            [328130.0, 7392815.0],
                            [328120.0, 7392815.0],
                            [328120.0, 7392850.0],
                        ]
                    ],
                },
            },
            {
                "type": "Feature",
                "properties": {
                    "cd_setor_fiscal": "083",
                    "cd_quadra_fiscal": "112",
                    "cd_lote": "0023",
                    "cd_zona": "ZEU",
                },
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [
                            [328130.0, 7392850.0],
                            [328142.0, 7392850.0],
                            [328142.0, 7392815.0],
                            [328130.0, 7392815.0],
                            [328130.0, 7392850.0],
                        ]
                    ],
                },
            },
        ],
    },
    "Vila Mariana - Zona Mista (ZM)": {
        "sql": ("037", "045", "0088"),
        "endereco": "Rua Domingos de Morais, Vila Mariana - São Paulo/SP",
        "zona": "ZM",
        "macrozona": "Macrozona de Estruturação e Qualificação Urbana",
        "macroarea": "Macroárea de Urbanização Consolidada (MUC)",
        "qualificacao_ambiental": "PA 6 (Perímetro de Qualificação Ambiental 6 — Quota Ambiental)",
        "cota_min": 788.0,
        "cota_max": 792.0,
        "features_utm": [
            {
                "type": "Feature",
                "properties": {
                    "cd_setor_fiscal": "037",
                    "cd_quadra_fiscal": "045",
                    "cd_lote": "0088",
                    "cd_zona": "ZM",
                },
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [
                            [332850.0, 7390420.0],
                            [332872.0, 7390420.0],
                            [332872.0, 7390380.0],
                            [332850.0, 7390380.0],
                            [332850.0, 7390420.0],
                        ]
                    ],
                },
            }
        ],
    },
}


def buscar_lote_local_por_ponto_utm(x_utm: float, y_utm: float) -> Optional[Dict[str, Any]]:
    """
    Verifica se o ponto UTM (x_utm, y_utm) está contido em algum dos lotes locais de exemplo
    ou nos lotes vizinhos de demonstração, permitindo clique interativo sobre múltiplos lotes
    mesmo em modo offline.
    """
    ponto = Point(x_utm, y_utm)
    todas_feicoes: List[Dict[str, Any]] = []
    for dados in LOTES_EXEMPLO_SP.values():
        todas_feicoes.extend(dados.get("features_utm", []))
    todas_feicoes.extend(LOTES_VIZINHOS_DEMO_UTM)

    for feat in todas_feicoes:
        try:
            pol = shape(feat["geometry"])
            if pol.contains(ponto) or pol.intersects(ponto):
                return feat
        except Exception:
            continue
    return None


LOTES_VIZINHOS_DEMO_UTM: List[Dict[str, Any]] = [
    # Vizinhos contíguos na Av. Paulista (009.074.0016 e 009.074.0014)
    {
        "type": "Feature",
        "properties": {
            "cd_setor_fiscal": "009",
            "cd_quadra_fiscal": "074",
            "cd_lote": "0016",
            "nm_logradouro": "AV PAULISTA",
            "cd_zona": "ZEU",
        },
        "geometry": {
            "type": "Polygon",
            "coordinates": [
                [
                    [331008.0, 7393392.0],
                    [331036.0, 7393374.0],
                    [331006.0, 7393327.0],
                    [330978.0, 7393345.0],
                    [331008.0, 7393392.0],
                ]
            ],
        },
    },
    {
        "type": "Feature",
        "properties": {
            "cd_setor_fiscal": "009",
            "cd_quadra_fiscal": "074",
            "cd_lote": "0014",
            "nm_logradouro": "AV PAULISTA",
            "cd_zona": "ZEU",
        },
        "geometry": {
            "type": "Polygon",
            "coordinates": [
                [
                    [330952.0, 7393428.0],
                    [330980.0, 7393410.0],
                    [330950.0, 7393363.0],
                    [330922.0, 7393381.0],
                    [330952.0, 7393428.0],
                ]
            ],
        },
    },
    # Vizinho adicional em Pinheiros (083.112.0024)
    {
        "type": "Feature",
        "properties": {
            "cd_setor_fiscal": "083",
            "cd_quadra_fiscal": "112",
            "cd_lote": "0024",
            "cd_zona": "ZEU",
        },
        "geometry": {
            "type": "Polygon",
            "coordinates": [
                [
                    [328142.0, 7392850.0],
                    [328154.0, 7392850.0],
                    [328154.0, 7392815.0],
                    [328142.0, 7392815.0],
                    [328142.0, 7392850.0],
                ]
            ],
        },
    },
    # Vizinhos contíguos na Vila Mariana (037.045.0089 e 037.045.0090)
    {
        "type": "Feature",
        "properties": {
            "cd_setor_fiscal": "037",
            "cd_quadra_fiscal": "045",
            "cd_lote": "0089",
            "cd_zona": "ZM",
        },
        "geometry": {
            "type": "Polygon",
            "coordinates": [
                [
                    [332872.0, 7390420.0],
                    [332894.0, 7390420.0],
                    [332894.0, 7390380.0],
                    [332872.0, 7390380.0],
                    [332872.0, 7390420.0],
                ]
            ],
        },
    },
    {
        "type": "Feature",
        "properties": {
            "cd_setor_fiscal": "037",
            "cd_quadra_fiscal": "045",
            "cd_lote": "0090",
            "cd_zona": "ZM",
        },
        "geometry": {
            "type": "Polygon",
            "coordinates": [
                [
                    [332894.0, 7390420.0],
                    [332916.0, 7390420.0],
                    [332916.0, 7390380.0],
                    [332894.0, 7390380.0],
                    [332894.0, 7390420.0],
                ]
            ],
        },
    },
]


def criar_feicao_referencia_coordenada(
    lat: float, lon: float, endereco: Optional[str] = None
) -> Dict[str, Any]:
    """
    Cria um polígono de referência (10m x 25m = 250m²) centrado na coordenada (lat, lon)
    quando o endereço/coordenada foi localizado no mapa, mas a camada vetorial de lotes
    do GeoSampa não retornou polígono individualizado naquele ponto.
    Isso garante que o mapa centralize imediatamente no endereço digitado e execute a
    consulta espacial pelo ponto (Zoneamento, Macrozona, Macroárea e Qualificação Ambiental).
    """
    x_utm, y_utm = _TO_UTM.transform(lon, lat)
    meia_larg = 5.0
    meia_prof = 12.5
    return {
        "type": "Feature",
        "properties": {
            "cd_setor_fiscal": "---",
            "cd_quadra_fiscal": "---",
            "cd_lote": "LOCAL",
            "nm_logradouro": endereco or f"{lat:.6f}, {lon:.6f}",
            "_aviso_fallback": (
                f"Mapa centralizado em ({lat:.6f}, {lon:.6f}). "
                "A camada vetorial não retornou o recorte exato do lote neste ponto — "
                "exibindo lote de referência (10m × 25m) com os parâmetros territoriais consultados no ponto "
                "e as camadas WMS do GeoSampa sobrepostas no mapa. Clique sobre um lote vizinho para selecioná-lo."
            ),
        },
        "geometry": {
            "type": "Polygon",
            "coordinates": [
                [
                    [x_utm - meia_larg, y_utm + meia_prof],
                    [x_utm + meia_larg, y_utm + meia_prof],
                    [x_utm + meia_larg, y_utm - meia_prof],
                    [x_utm - meia_larg, y_utm - meia_prof],
                    [x_utm - meia_larg, y_utm + meia_prof],
                ]
            ],
        },
    }



