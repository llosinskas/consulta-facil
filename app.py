"""
Aplicação Principal (Streamlit): Software de Estudo de Viabilidade e Consulta de Terrenos via GeoSampa.
Execute com:
    .venv\\Scripts\\streamlit.exe run app.py
"""

import importlib
from typing import Any, Dict, List, Optional

import streamlit as st
from streamlit_folium import st_folium

import config
import domain.legislacao_sp
import domain.lotes_exemplo
import domain.models
import domain.tabelas_dados
import domain.viabilidade_models
import services.agua_elevador_engine
import services.desnivel_engine
import services.eletrica_engine
import services.excel_exporter
import services.financeiro_cronograma_engine
import services.geocoder
import services.geosampa_client
import services.quadro_areas_engine
import services.spatial_analyzer
import services.viabilidade_bridge
import ui.carregamento
import ui.dashboard_cards
import ui.map_component
import ui.styles
import ui.viabilidade_ui

# Garante que módulos atualizados sejam recarregados mesmo com servidor Streamlit já aberto
importlib.reload(config)
importlib.reload(domain.legislacao_sp)
importlib.reload(domain.lotes_exemplo)
importlib.reload(domain.models)
importlib.reload(domain.tabelas_dados)
importlib.reload(domain.viabilidade_models)
importlib.reload(services.geocoder)
importlib.reload(services.geosampa_client)
importlib.reload(services.spatial_analyzer)
importlib.reload(services.viabilidade_bridge)
importlib.reload(services.quadro_areas_engine)
importlib.reload(services.agua_elevador_engine)
importlib.reload(services.desnivel_engine)
importlib.reload(services.eletrica_engine)
importlib.reload(services.excel_exporter)
importlib.reload(services.financeiro_cronograma_engine)
importlib.reload(ui.styles)
importlib.reload(ui.carregamento)
importlib.reload(ui.dashboard_cards)
importlib.reload(ui.map_component)
importlib.reload(ui.viabilidade_ui)

from services.geocoder import geocodificar_endereco_sp
from services.geosampa_client import (
    LOTES_EXEMPLO_SP,
    LOTES_VIZINHOS_DEMO_UTM,
    GeoSampaWFSClient,
    criar_feicao_referencia_coordenada,
    extrair_multiplos_sqls,
    validar_coordenadas_sp,
    validar_sql_input,
)
from services.spatial_analyzer import (
    alternar_lote_na_selecao,
    bbox_utm_com_margem,
    consultar_enquadramento_pelo_ponto_do_lote,
    encontrar_feicao_no_ponto,
    processar_terreno_completo,
)
from ui.dashboard_cards import (
    renderizar_painel_viabilidade,
    renderizar_resumo_terreno,
    renderizar_tabela_unitario_vs_unificado,
    renderizar_tabelas_geometricas,
)
from ui.carregamento import reservar_area_carregamento, sub_progresso, tela_de_carregamento
from ui.map_component import construir_mapa_terreno
from ui.styles import aplicar_estilos, nota, titulo_secao
from ui.viabilidade_ui import renderizar_estudo_completo_planilha

st.set_page_config(
    page_title="Estudo de Viabilidade · GeoSampa",
    page_icon="🏙️",
    layout="wide",
    initial_sidebar_state="expanded",
)


@st.cache_resource
def obter_cliente_geosampa(versao: str = "v7_cache_camadas_progresso") -> GeoSampaWFSClient:
    return GeoSampaWFSClient()


MAX_HISTORICO = 15


def _empilhar_historico() -> None:
    """Guarda o terreno atual (e seus vizinhos) para o botão Desfazer."""
    atual = st.session_state.get("resultado_terreno")
    if atual is None:
        return
    hist = st.session_state.setdefault("historico_selecoes", [])
    hist.append((atual, st.session_state.get("lotes_vizinhos")))
    del hist[:-MAX_HISTORICO]


def _limpar_estado_do_terreno() -> None:
    st.session_state["ultimo_erro"] = None
    st.session_state.pop("viab_df_pavimentos", None)
    st.session_state.pop("viab_ultima_assinatura_fa", None)
    st.session_state.pop("viab_tipologias_assinatura", None)


def _atualizar_vizinhos(client: Optional[GeoSampaWFSClient], progresso=None) -> None:
    """
    Busca no GeoSampa os lotes ao redor do terreno atual (clicáveis no mapa para unificar).
    Sem cliente (exemplos/offline), usa os vizinhos reais de demonstração gravados no projeto.
    """
    resultado = st.session_state.get("resultado_terreno")
    st.session_state["lotes_vizinhos"] = None
    if client is None or resultado is None:
        return
    if progresso:
        progresso(0.96, "Carregando os lotes vizinhos para seleção no mapa…")
    try:
        feats = client.consultar_camada_espacial_bbox("lote", *bbox_utm_com_margem(resultado))
    except Exception:
        feats = []
    st.session_state["lotes_vizinhos"] = feats or None


def carregar_exemplo(nome: str, empilhar: bool = True) -> None:
    dados = LOTES_EXEMPLO_SP[nome]
    if empilhar:
        _empilhar_historico()
    _limpar_estado_do_terreno()
    st.session_state["aviso_selecao_mapa"] = None
    st.session_state["ponto_clicado_latlon"] = None
    st.session_state["resultado_terreno"] = processar_terreno_completo(
        features_lotes=dados["features_utm"],
        client=None,
        endereco_referencia=dados["endereco"],
        zona_forcada=dados["zona"],
        cota_min_forcada=dados["cota_min"],
        cota_max_forcada=dados["cota_max"],
        valores_territoriais_iniciais={
            "macrozona": dados.get("macrozona"),
            "macroarea": dados.get("macroarea"),
            "qualificacao_ambiental": dados.get("qualificacao_ambiental"),
        },
        fonte_dados="Exemplo com lote real do GeoSampa (dados gravados — consulte online pelo ponto para atualizar)",
    )
    st.session_state["lotes_vizinhos"] = None  # usa os vizinhos reais de demonstração


def inicializar_estado() -> None:
    if "resultado_terreno" not in st.session_state:
        carregar_exemplo(next(iter(LOTES_EXEMPLO_SP)), empilhar=False)
    st.session_state.setdefault("ultimo_erro", None)
    st.session_state.setdefault("aviso_selecao_mapa", None)
    st.session_state.setdefault("ultimo_clique_processado", None)
    st.session_state.setdefault("ponto_clicado_latlon", None)
    st.session_state.setdefault("filtro_ativo", "SQL (Setor / Quadra / Lote)")
    st.session_state.setdefault("ultimo_endereco_buscado", "")
    st.session_state.setdefault("historico_selecoes", [])
    st.session_state.setdefault("lotes_vizinhos", None)


def salvar_resultado(
    feats: List[Dict[str, Any]],
    client: GeoSampaWFSClient,
    fonte: str,
    endereco: str = None,
    preservar_contexto_atual: bool = False,
    progresso=None,
) -> None:
    atual = st.session_state.get("resultado_terreno")
    zona_ini = atual.zoneamento.sigla_zona if (preservar_contexto_atual and atual and atual.zoneamento) else None
    valores_ini = None
    if preservar_contexto_atual and atual:
        valores_ini = {
            "macrozona": atual.macrozona.valor if atual.macrozona else None,
            "macroarea": atual.macroarea.valor if atual.macroarea else None,
            "qualificacao_ambiental": (
                atual.qualificacao_ambiental.valor if atual.qualificacao_ambiental else None
            ),
        }
    end_ref = endereco or (atual.endereco_aproximado if (preservar_contexto_atual and atual) else None)
    novo = processar_terreno_completo(
        features_lotes=feats,
        client=client,
        endereco_referencia=end_ref,
        zona_forcada=zona_ini,
        valores_territoriais_iniciais=valores_ini,
        fonte_dados=fonte,
        progresso=sub_progresso(progresso, 0.0, 0.95) if progresso else None,
    )
    _empilhar_historico()
    _limpar_estado_do_terreno()
    st.session_state["resultado_terreno"] = novo
    _atualizar_vizinhos(client, progresso)


def consultar_coordenada_com_fallback_mapa(
    lat: float,
    lon: float,
    client: GeoSampaWFSClient,
    fonte: str,
    endereco: str = None,
    progresso=None,
) -> None:
    """
    Consulta o lote na coordenada (lat, lon) e atualiza o mapa imediatamente.
    Caso o servidor WFS não retorne o polígono vetorial do lote naquele ponto,
    centraliza o mapa na coordenada informada e executa a consulta pelo ponto geográfico
    (Macrozona, Macroárea, Qualificação Ambiental e Zoneamento).
    """
    if progresso:
        progresso(0.03, "Localizando o lote no ponto informado…")
    feats, _ = client.consultar_lote_por_coordenada(lat, lon)
    if not feats:
        feats = [criar_feicao_referencia_coordenada(lat, lon, endereco=endereco)]
    st.session_state["ponto_clicado_latlon"] = (round(lat, 6), round(lon, 6))
    salvar_resultado(feats, client, fonte, endereco, progresso=sub_progresso(progresso, 0.08, 1.0) if progresso else None)


def _sql_da_feicao(feat: Dict[str, Any]) -> str:
    props = feat.get("properties") or {}
    return (
        f"{props.get('cd_setor_fiscal', '000')}."
        f"{props.get('cd_quadra_fiscal', '000')}."
        f"{props.get('cd_lote', '0000')}"
    )


def _lote_clicado(resultado, lat: float, lon: float, client: GeoSampaWFSClient, progresso):
    """
    Identifica o lote clicado: primeiro entre os lotes já desenhados no mapa (selecionados e
    vizinhos — sem acesso à rede) e, se não houver, consultando o GeoSampa pelo ponto.
    """
    locais = [l.geojson_wgs84 for l in resultado.lotes]
    locais += st.session_state.get("lotes_vizinhos") or LOTES_VIZINHOS_DEMO_UTM
    feat = encontrar_feicao_no_ponto(locais, lat, lon)
    if feat is not None:
        return [feat], None
    progresso(0.04, "Buscando o lote clicado no GeoSampa…")
    return client.consultar_lote_por_coordenada(lat, lon)


def barra_lateral(client: GeoSampaWFSClient) -> Dict[str, bool]:
    with st.sidebar:
        st.markdown("### Localizar terreno")
        st.caption("A consulta utiliza exclusivamente o filtro selecionado abaixo.")

        modo = st.radio(
            "Filtro de busca",
            options=["SQL (Setor / Quadra / Lote)", "Endereço ou CEP", "Coordenadas (lat / lon)"],
        )

        # Se o usuário trocou o filtro, limpa qualquer mensagem de erro do filtro anterior
        if modo != st.session_state.get("filtro_ativo"):
            st.session_state["filtro_ativo"] = modo
            st.session_state["ultimo_erro"] = None

        if modo.startswith("SQL"):
            formato = st.radio(
                "Quantidade de lotes",
                options=["Um lote", "Vários lotes (unificação)"],
                horizontal=True,
            )

            if formato == "Um lote":
                with st.form("form_busca_sql_unico", border=False):
                    setor_in = st.text_input("Setor (3 dígitos)", value="039", max_chars=3)
                    quadra_in = st.text_input("Quadra (3 dígitos)", value="079", max_chars=3)
                    lote_in = st.text_input("Lote (4 dígitos, dígito verificador opcional)", value="0071", max_chars=6)
                    submeteu_sql = st.form_submit_button("Consultar lote por SQL", type="primary", width="stretch")

                if submeteu_sql:
                    sql_ok, erro_val = validar_sql_input(setor_in, quadra_in, lote_in)
                    if erro_val or not sql_ok:
                        st.session_state["ultimo_erro"] = erro_val
                    else:
                        s, q, l = sql_ok
                        with tela_de_carregamento(f"Consultando o SQL {s}.{q}.{l}") as progresso:
                            progresso(0.03, "Buscando o lote no GeoSampa…")
                            feats, erro = client.consultar_lote_por_sql(s, q, l)
                            if feats:
                                st.session_state["ponto_clicado_latlon"] = None
                                salvar_resultado(
                                    feats, client, "GeoSampa WFS (busca por SQL)",
                                    progresso=sub_progresso(progresso, 0.1, 1.0),
                                )
                            else:
                                st.session_state["ultimo_erro"] = erro
            else:
                with st.form("form_busca_sql_multi", border=False):
                    texto = st.text_area(
                        "Códigos SQL — um por linha ou separados por vírgula",
                        value="039.079.0070\n039.079.0071\n039.079.0072",
                        height=110,
                    )
                    st.caption("Os polígonos dos lotes vizinhos são unidos em um único terreno.")
                    submeteu_multi = st.form_submit_button("Consultar e unificar SQLs", type="primary", width="stretch")

                if submeteu_multi:
                    lista = extrair_multiplos_sqls(texto)
                    if not lista:
                        st.session_state["ultimo_erro"] = "Formato de SQL inválido. Exemplo: 012.034.0056."
                    else:
                        todas: List[Dict[str, Any]] = []
                        erros: List[str] = []
                        with tela_de_carregamento(f"Consultando e unificando {len(lista)} lote(s)") as progresso:
                            for i_sql, (s, q, l) in enumerate(lista):
                                progresso(0.3 * i_sql / len(lista), f"Buscando o SQL {s}.{q}.{l} ({i_sql + 1}/{len(lista)})…")
                                feats, erro = client.consultar_lote_por_sql(s, q, l)
                                if feats:
                                    todas.extend(feats)
                                elif erro:
                                    erros.append(erro)
                            if todas:
                                st.session_state["ponto_clicado_latlon"] = None
                                salvar_resultado(
                                    todas, client, "GeoSampa WFS (unificação por SQL)",
                                    progresso=sub_progresso(progresso, 0.3, 1.0),
                                )
                                st.session_state["resultado_terreno"].avisos.extend(erros)
                            else:
                                st.session_state["ultimo_erro"] = " | ".join(erros)

        elif modo.startswith("Endereço"):
            endereco_in = st.text_input(
                "Digite o endereço ou CEP e pressione Enter",
                value="",
                placeholder="Ex.: Av. Paulista, 1578 ou 01310-200",
                key="input_endereco_sp",
            )
            clicou_end = st.button("Localizar endereço e atualizar mapa", type="primary", width="stretch")
            digitou_novo_end = (
                bool(endereco_in.strip())
                and endereco_in.strip() != st.session_state.get("ultimo_endereco_buscado", "")
            )

            if clicou_end or digitou_novo_end:
                st.session_state["ultimo_endereco_buscado"] = endereco_in.strip()
                with tela_de_carregamento(f"Localizando “{endereco_in.strip()}”") as progresso:
                    progresso(0.02, "Convertendo o endereço em coordenadas…")
                    latlon, end_fmt, erro_geo = geocodificar_endereco_sp(endereco_in)
                    if erro_geo or not latlon:
                        st.session_state["ultimo_erro"] = erro_geo
                    else:
                        consultar_coordenada_com_fallback_mapa(
                            latlon[0],
                            latlon[1],
                            client,
                            "GeoSampa (busca por endereço)",
                            end_fmt,
                            progresso=sub_progresso(progresso, 0.1, 1.0),
                        )

        else:
            with st.form("form_busca_coordenadas", border=False):
                lat_in = st.number_input("Latitude", value=-23.561414, format="%.6f", step=0.0001)
                lon_in = st.number_input("Longitude", value=-46.655881, format="%.6f", step=0.0001)
                submeteu_coord = st.form_submit_button("Consultar coordenada e atualizar mapa", type="primary", width="stretch")

            if submeteu_coord:
                coord_ok, erro_coord = validar_coordenadas_sp(lat_in, lon_in)
                if erro_coord or not coord_ok:
                    st.session_state["ultimo_erro"] = erro_coord
                else:
                    with tela_de_carregamento("Consultando a coordenada") as progresso:
                        consultar_coordenada_com_fallback_mapa(
                            coord_ok[0],
                            coord_ok[1],
                            client,
                            "GeoSampa (busca por coordenada)",
                            progresso=progresso,
                        )

        st.divider()
        st.markdown("### Opções do mapa")
        exibir_cotas = st.checkbox("Mostrar medidas dos lados", value=True)
        exibir_wms = st.checkbox("Mostrar camadas do GeoSampa (lotes e zoneamento)", value=True)

        st.divider()
        st.markdown("### Exemplos para teste")
        st.caption(
            "Lotes reais de São Paulo com os dados do GeoSampa gravados no projeto: abrem na hora, "
            "mesmo sem conexão. Clique nos lotes vizinhos do mapa para unificar."
        )
        exemplo = st.selectbox("Exemplo", options=list(LOTES_EXEMPLO_SP.keys()))
        if st.button("Carregar exemplo", width="stretch"):
            carregar_exemplo(exemplo)

    return {"cotas": exibir_cotas, "wms": exibir_wms}


ACAO_MULTIPLA = "Adicionar/remover lotes da seleção"
ACAO_SUBSTITUIR = "Trocar pelo lote clicado"
ACAO_FICHA = "Só ver a ficha (não altera)"


def _processar_clique_no_mapa(resultado, lat_c: float, lon_c: float, acao_clique: str, client) -> None:
    """Trata o clique no mapa com a tela de carregamento bloqueando a interface até o fim."""
    if acao_clique == ACAO_MULTIPLA:
        with tela_de_carregamento("Atualizando a seleção de lotes") as progresso:
            feats_novas, erro = _lote_clicado(resultado, lat_c, lon_c, client, progresso)
            if not feats_novas:
                st.session_state["aviso_selecao_mapa"] = erro or "Nenhum lote encontrado neste ponto."
                return
            feats_atualizadas, acao_lote = alternar_lote_na_selecao(resultado.lotes, feats_novas)
            sql_nv = _sql_da_feicao(feats_novas[0])
            if acao_lote == "mantido":
                st.session_state["aviso_selecao_mapa"] = (
                    f"O lote {sql_nv} é o único da seleção: clique em um lote vizinho para unificar."
                )
                return  # nada mudou: não reprocessa
            progresso(0.08, f"Lote {sql_nv} {acao_lote}. Recalculando o terreno unificado…")
            salvar_resultado(
                feats_atualizadas,
                client,
                f"GeoSampa (seleção no mapa — {len(feats_atualizadas)} lote(s))",
                preservar_contexto_atual=True,
                progresso=sub_progresso(progresso, 0.1, 1.0),
            )
            verbo = "adicionado ao" if acao_lote == "adicionado" else "removido do"
            st.session_state["aviso_selecao_mapa"] = (
                f"Lote {sql_nv} {verbo} estudo — {len(feats_atualizadas)} lote(s) selecionado(s)."
            )
    elif acao_clique == ACAO_SUBSTITUIR:
        st.session_state["aviso_selecao_mapa"] = None
        with tela_de_carregamento("Consultando o lote clicado") as progresso:
            feats, _ = _lote_clicado(resultado, lat_c, lon_c, client, progresso)
            if feats:
                st.session_state["ponto_clicado_latlon"] = (round(lat_c, 6), round(lon_c, 6))
                salvar_resultado(
                    feats, client, f"GeoSampa (clique no mapa em {lat_c:.5f}, {lon_c:.5f})",
                    progresso=sub_progresso(progresso, 0.08, 1.0),
                )
            else:
                consultar_coordenada_com_fallback_mapa(
                    lat_c, lon_c, client, f"GeoSampa (clique no mapa em {lat_c:.5f}, {lon_c:.5f})",
                    progresso=progresso,
                )


def _barra_lotes_selecionados(resultado, client) -> None:
    """Lista os lotes do estudo com ações de remover, manter só o 1º e desfazer."""
    historico = st.session_state.get("historico_selecoes") or []
    col_tit, col_undo = st.columns([3, 1], vertical_alignment="center")
    col_tit.markdown(f"**Lotes selecionados no estudo ({len(resultado.lotes)})** · "
                     f"área total {resultado.area_total_m2:,.2f} m²".replace(",", "X").replace(".", ",").replace("X", "."))
    if col_undo.button(
        f"↶ Desfazer ({len(historico)})" if historico else "↶ Desfazer",
        disabled=not historico,
        width="stretch",
        help="Volta para o terreno anterior (seleção de lotes ou consulta).",
        key="btn_desfazer_selecao",
    ):
        anterior, vizinhos = historico.pop()
        _limpar_estado_do_terreno()
        st.session_state["resultado_terreno"] = anterior
        st.session_state["lotes_vizinhos"] = vizinhos
        st.session_state["aviso_selecao_mapa"] = "Seleção anterior restaurada."
        st.rerun()

    cols_lotes = st.columns(min(len(resultado.lotes) + 1, 5))
    for idx_l, lote_sel in enumerate(resultado.lotes):
        with cols_lotes[idx_l % len(cols_lotes)]:
            st.caption(
                f"**#{idx_l + 1} · SQL {lote_sel.sql_formatado}**  \n"
                f"Área: {lote_sel.area_cartografica_m2:,.2f} m² · "
                f"Testada: {lote_sel.testada_estimada_m:.1f} m"
            )
            if len(resultado.lotes) > 1 and st.button(
                f"Remover #{idx_l + 1}",
                key=f"btn_rem_lote_{idx_l}_{lote_sel.sql_formatado}",
                width="stretch",
            ):
                feats_rest = [l.geojson_wgs84 for i, l in enumerate(resultado.lotes) if i != idx_l]
                with tela_de_carregamento(f"Removendo o lote {lote_sel.sql_formatado}") as progresso:
                    salvar_resultado(
                        feats_rest, client, f"GeoSampa ({len(feats_rest)} lote(s) selecionado(s))",
                        preservar_contexto_atual=True, progresso=progresso,
                    )
                st.session_state["aviso_selecao_mapa"] = (
                    f"Lote SQL {lote_sel.sql_formatado} removido. Restam {len(feats_rest)} lote(s)."
                )
                st.rerun()

    if len(resultado.lotes) > 1:
        with cols_lotes[-1]:
            st.caption("**Ação rápida**")
            if st.button("Manter apenas o 1º lote", key="btn_limpar_multilote", width="stretch"):
                with tela_de_carregamento("Redefinindo a seleção") as progresso:
                    salvar_resultado(
                        [resultado.lotes[0].geojson_wgs84], client, "GeoSampa (1 lote selecionado)",
                        preservar_contexto_atual=True, progresso=progresso,
                    )
                st.session_state["aviso_selecao_mapa"] = "Seleção redefinida para o 1º lote."
                st.rerun()


def main() -> None:
    reservar_area_carregamento()  # antes de tudo: é onde a tela de carregamento é desenhada
    aplicar_estilos()
    inicializar_estado()
    client = obter_cliente_geosampa()
    opcoes = barra_lateral(client)

    st.markdown("## Estudo de Viabilidade de Terrenos")
    st.caption("Dados de lote, zoneamento e topografia consultados no GeoSampa — Prefeitura de São Paulo.")

    if st.session_state.get("ultimo_erro"):
        filtro_atual = st.session_state.get("filtro_ativo", "")
        dica_filtro = (
            " Confira se o SQL tem setor (3 dígitos), quadra (3 dígitos) e lote (4 dígitos)."
            if filtro_atual.startswith("SQL")
            else ""
        )
        nota(
            f"Não foi possível concluir a consulta ({filtro_atual}): {st.session_state['ultimo_erro']}{dica_filtro}",
            "alert",
        )

    resultado = st.session_state.get("resultado_terreno")
    if not resultado:
        return

    renderizar_resumo_terreno(resultado)

    lat_p, lon_p = resultado.centroide_latlon
    e_utm, n_utm = getattr(resultado, "ponto_utm", (0.0, 0.0))
    col_info_pt, col_btn_pt = st.columns([2.2, 1.3], vertical_alignment="center")
    col_info_pt.caption(
        f"Ponto geográfico extraído do lote: **Lat {lat_p:.6f}, Lon {lon_p:.6f}** · "
        f"**UTM E {e_utm:,.2f} m, N {n_utm:,.2f} m (EPSG:31983)**"
    )
    if col_btn_pt.button(
        "Consultar Macrozona, Macroárea e Qualificação Ambiental pelo ponto do lote",
        width="stretch",
    ):
        with tela_de_carregamento("Consultando o enquadramento pelo ponto do lote") as progresso:
            progresso(0.1, "Consultando macroárea, macrozona, PA e zoneamento…")
            _empilhar_historico()
            st.session_state["resultado_terreno"] = consultar_enquadramento_pelo_ponto_do_lote(resultado, client)
            _atualizar_vizinhos(client, progresso)
        st.rerun()

    titulo_secao(
        "Mapa interativo do terreno",
        "Clique em um lote vizinho (cinza) para unificá-lo ao estudo, ou em um lote selecionado (laranja) "
        "para retirá-lo. A tela fica bloqueada com uma barra de progresso até a consulta terminar.",
    )
    acao_clique = st.radio(
        "Ao clicar em um lote no mapa",
        options=[ACAO_MULTIPLA, ACAO_SUBSTITUIR, ACAO_FICHA],
        horizontal=True,
        key="acao_clique_mapa",
    )

    if st.session_state.get("aviso_selecao_mapa"):
        nota(st.session_state["aviso_selecao_mapa"], "info")

    mapa = construir_mapa_terreno(
        resultado=resultado,
        exibir_cotas_arestas=opcoes["cotas"],
        exibir_wms_geosampa=opcoes["wms"],
        ponto_clicado_latlon=st.session_state.get("ponto_clicado_latlon"),
        lotes_vizinhos=st.session_state.get("lotes_vizinhos"),
        aviso_carregando_ao_clicar=acao_clique != ACAO_FICHA,
    )
    chave_mapa = f"mapa_{resultado.centroide_latlon[0]:.5f}_{resultado.centroide_latlon[1]:.5f}_{len(resultado.lotes)}"
    evento = st_folium(
        mapa,
        width=None,
        height=580,
        returned_objects=["last_clicked"],
        key=chave_mapa,
    )

    if evento and evento.get("last_clicked"):
        lat_c = float(evento["last_clicked"]["lat"])
        lon_c = float(evento["last_clicked"]["lng"])
        chave_clique = (round(lat_c, 6), round(lon_c, 6))

        if chave_clique != st.session_state.get("ultimo_clique_processado"):
            st.session_state["ultimo_clique_processado"] = chave_clique
            if acao_clique != ACAO_FICHA:
                st.session_state["ponto_clicado_latlon"] = chave_clique
                _processar_clique_no_mapa(resultado, lat_c, lon_c, acao_clique, client)
                st.rerun()

    _barra_lotes_selecionados(resultado, client)

    renderizar_painel_viabilidade(resultado)
    renderizar_tabela_unitario_vs_unificado(resultado)
    renderizar_estudo_completo_planilha(resultado)
    renderizar_tabelas_geometricas(resultado)


if __name__ == "__main__":
    main()
