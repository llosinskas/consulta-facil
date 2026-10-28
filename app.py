"""
Aplicação Principal (Streamlit): Software de Estudo de Viabilidade e Consulta de Terrenos via GeoSampa.
Execute com:
    .venv\\Scripts\\streamlit.exe run app.py
"""

import importlib
from typing import Any, Dict, List

import streamlit as st
from streamlit_folium import st_folium

import config
import domain.models
import services.geocoder
import services.geosampa_client
import services.spatial_analyzer
import ui.dashboard_cards
import ui.map_component
import ui.styles

# Garante que módulos atualizados sejam recarregados mesmo com servidor Streamlit já aberto
importlib.reload(config)
importlib.reload(domain.models)
importlib.reload(services.geocoder)
importlib.reload(services.geosampa_client)
importlib.reload(services.spatial_analyzer)
importlib.reload(ui.styles)
importlib.reload(ui.dashboard_cards)
importlib.reload(ui.map_component)

from services.geocoder import geocodificar_endereco_sp
from services.geosampa_client import (
    LOTES_EXEMPLO_SP,
    GeoSampaWFSClient,
    criar_feicao_referencia_coordenada,
    extrair_multiplos_sqls,
    validar_coordenadas_sp,
    validar_sql_input,
)
from services.spatial_analyzer import (
    alternar_lote_na_selecao,
    consultar_enquadramento_pelo_ponto_do_lote,
    processar_terreno_completo,
)
from ui.dashboard_cards import (
    renderizar_painel_viabilidade,
    renderizar_resumo_terreno,
    renderizar_tabela_unitario_vs_unificado,
    renderizar_tabelas_geometricas,
)
from ui.map_component import construir_mapa_terreno
from ui.styles import aplicar_estilos, nota, titulo_secao

st.set_page_config(
    page_title="Estudo de Viabilidade · GeoSampa",
    page_icon="🏙️",
    layout="wide",
    initial_sidebar_state="expanded",
)


@st.cache_resource
def obter_cliente_geosampa(versao: str = "v6_multilote_unitario_unificado") -> GeoSampaWFSClient:
    return GeoSampaWFSClient()


def carregar_exemplo(nome: str) -> None:
    dados = LOTES_EXEMPLO_SP[nome]
    st.session_state["ultimo_erro"] = None
    st.session_state["aviso_selecao_mapa"] = None
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
        fonte_dados="Exemplo demonstrativo (pronto para consulta online pelo ponto)",
    )


def inicializar_estado() -> None:
    if "resultado_terreno" not in st.session_state:
        carregar_exemplo(next(iter(LOTES_EXEMPLO_SP)))
    st.session_state.setdefault("ultimo_erro", None)
    st.session_state.setdefault("aviso_selecao_mapa", None)
    st.session_state.setdefault("ultimo_clique_processado", None)
    st.session_state.setdefault("ponto_clicado_latlon", None)
    st.session_state.setdefault("filtro_ativo", "SQL (Setor / Quadra / Lote)")
    st.session_state.setdefault("ultimo_endereco_buscado", "")


def salvar_resultado(
    feats: List[Dict[str, Any]],
    client: GeoSampaWFSClient,
    fonte: str,
    endereco: str = None,
    preservar_contexto_atual: bool = False,
) -> None:
    st.session_state["ultimo_erro"] = None
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
    st.session_state["resultado_terreno"] = processar_terreno_completo(
        features_lotes=feats,
        client=client,
        endereco_referencia=end_ref,
        zona_forcada=zona_ini,
        valores_territoriais_iniciais=valores_ini,
        fonte_dados=fonte,
    )


def consultar_coordenada_com_fallback_mapa(
    lat: float,
    lon: float,
    client: GeoSampaWFSClient,
    fonte: str,
    endereco: str = None,
) -> None:
    """
    Consulta o lote na coordenada (lat, lon) e atualiza o mapa imediatamente.
    Caso o servidor WFS não retorne o polígono vetorial do lote naquele ponto,
    centraliza o mapa na coordenada informada e executa a consulta pelo ponto geográfico
    (Macrozona, Macroárea, Qualificação Ambiental e Zoneamento).
    """
    feats, _ = client.consultar_lote_por_coordenada(lat, lon)
    if not feats:
        feats = [criar_feicao_referencia_coordenada(lat, lon, endereco=endereco)]
    st.session_state["ponto_clicado_latlon"] = (round(lat, 6), round(lon, 6))
    salvar_resultado(feats, client, fonte, endereco)


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
                    setor_in = st.text_input("Setor (3 dígitos)", value="009", max_chars=3)
                    quadra_in = st.text_input("Quadra (3 dígitos)", value="074", max_chars=3)
                    lote_in = st.text_input("Lote (4 dígitos, dígito verificador opcional)", value="0015", max_chars=6)
                    submeteu_sql = st.form_submit_button("Consultar lote por SQL", type="primary", width="stretch")

                if submeteu_sql:
                    sql_ok, erro_val = validar_sql_input(setor_in, quadra_in, lote_in)
                    if erro_val or not sql_ok:
                        st.session_state["ultimo_erro"] = erro_val
                    else:
                        s, q, l = sql_ok
                        with st.spinner(f"Consultando SQL {s}.{q}.{l} no GeoSampa..."):
                            feats, erro = client.consultar_lote_por_sql(s, q, l)
                        if feats:
                            st.session_state["ponto_clicado_latlon"] = None
                            salvar_resultado(feats, client, "GeoSampa WFS (busca por SQL)")
                        else:
                            st.session_state["ultimo_erro"] = erro
            else:
                with st.form("form_busca_sql_multi", border=False):
                    texto = st.text_area(
                        "Códigos SQL — um por linha ou separados por vírgula",
                        value="083.112.0021\n083.112.0022\n083.112.0023",
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
                        with st.spinner(f"Consultando {len(lista)} lote(s) no GeoSampa..."):
                            for s, q, l in lista:
                                feats, erro = client.consultar_lote_por_sql(s, q, l)
                                if feats:
                                    todas.extend(feats)
                                elif erro:
                                    erros.append(erro)
                        if todas:
                            st.session_state["ponto_clicado_latlon"] = None
                            salvar_resultado(todas, client, "GeoSampa WFS (unificação por SQL)")
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
                with st.spinner(f"Localizando '{endereco_in}' e atualizando mapa..."):
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
                    with st.spinner("Consultando coordenada e atualizando mapa..."):
                        consultar_coordenada_com_fallback_mapa(
                            coord_ok[0],
                            coord_ok[1],
                            client,
                            "GeoSampa (busca por coordenada)",
                        )

        st.divider()
        st.markdown("### Opções do mapa")
        exibir_cotas = st.checkbox("Mostrar medidas dos lados", value=True)
        exibir_wms = st.checkbox("Mostrar camadas do GeoSampa (lotes e zoneamento)", value=True)

        st.divider()
        st.markdown("### Exemplos para teste")
        st.caption("Geometrias fictícias, úteis para conhecer a interface sem conexão com o GeoSampa.")
        exemplo = st.selectbox("Exemplo", options=list(LOTES_EXEMPLO_SP.keys()))
        if st.button("Carregar exemplo", width="stretch"):
            carregar_exemplo(exemplo)

    return {"cotas": exibir_cotas, "wms": exibir_wms}


def main() -> None:
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
        with st.spinner(
            f"Consultando Macrozona, Macroárea e Qualificação Ambiental no ponto ({lat_p:.6f}, {lon_p:.6f})..."
        ):
            st.session_state["resultado_terreno"] = consultar_enquadramento_pelo_ponto_do_lote(resultado, client)
        st.rerun()

    titulo_secao(
        "Mapa interativo do terreno (seleção de 1 ou múltiplos lotes)",
        "Clique nos lotes diretamente sobre o mapa para selecioná-los no estudo (unificar) ou substituir o lote analisado.",
    )
    acao_clique = st.radio(
        "Ação ao clicar em um lote no mapa",
        options=[
            "Selecionar múltiplos lotes no mapa (clicar adiciona/remove lote no estudo)",
            "Consultar apenas o lote clicado (substituir seleção)",
            "Apenas abrir ficha no balão do mapa",
        ],
        horizontal=True,
    )

    if st.session_state.get("aviso_selecao_mapa"):
        nota(st.session_state["aviso_selecao_mapa"], "info")

    mapa = construir_mapa_terreno(
        resultado=resultado,
        exibir_cotas_arestas=opcoes["cotas"],
        exibir_wms_geosampa=opcoes["wms"],
        ponto_clicado_latlon=st.session_state.get("ponto_clicado_latlon"),
    )
    chave_mapa = f"mapa_{resultado.centroide_latlon[0]:.5f}_{resultado.centroide_latlon[1]:.5f}_{len(resultado.lotes)}"
    evento = st_folium(
        mapa,
        width=None,
        height=560,
        returned_objects=["last_clicked"],
        key=chave_mapa,
    )

    if evento and evento.get("last_clicked"):
        lat_c = float(evento["last_clicked"]["lat"])
        lon_c = float(evento["last_clicked"]["lng"])
        chave_clique = (round(lat_c, 6), round(lon_c, 6))

        if chave_clique != st.session_state.get("ultimo_clique_processado"):
            st.session_state["ultimo_clique_processado"] = chave_clique
            st.session_state["ponto_clicado_latlon"] = chave_clique

            if acao_clique.startswith("Selecionar múltiplos lotes"):
                with st.spinner(f"Buscando lote clicado em ({lat_c:.6f}, {lon_c:.6f}) para atualizar seleção..."):
                    feats_novas, erro = client.consultar_lote_por_coordenada(lat_c, lon_c)
                if feats_novas:
                    feats_atualizadas, acao_lote = alternar_lote_na_selecao(resultado.lotes, feats_novas)
                    props_nv = feats_novas[0].get("properties") or {}
                    sql_nv = (
                        f"{props_nv.get('cd_setor_fiscal', '000')}."
                        f"{props_nv.get('cd_quadra_fiscal', '000')}."
                        f"{props_nv.get('cd_lote', '0000')}"
                    )
                    if acao_lote == "adicionado":
                        st.session_state["aviso_selecao_mapa"] = (
                            f"Lote SQL {sql_nv} adicionado ao estudo ({len(feats_atualizadas)} lotes selecionados)."
                        )
                    elif acao_lote == "removido":
                        st.session_state["aviso_selecao_mapa"] = (
                            f"Lote SQL {sql_nv} removido da seleção ({len(feats_atualizadas)} lote(s) restante(s))."
                        )
                    else:
                        st.session_state["aviso_selecao_mapa"] = (
                            f"Lote SQL {sql_nv} já é o único lote selecionado no estudo."
                        )
                    salvar_resultado(
                        feats_atualizadas,
                        client,
                        f"GeoSampa (seleção no mapa — {len(feats_atualizadas)} lote(s))",
                        preservar_contexto_atual=True,
                    )
                    st.rerun()
                else:
                    nota(erro or "Nenhum lote encontrado neste ponto para adicionar à seleção.", "warn")

            elif acao_clique.startswith("Consultar apenas o lote clicado"):
                st.session_state["aviso_selecao_mapa"] = None
                with st.spinner(f"Localizando terreno clicado em ({lat_c:.6f}, {lon_c:.6f}) e consultando parâmetros..."):
                    consultar_coordenada_com_fallback_mapa(
                        lat_c,
                        lon_c,
                        client,
                        f"GeoSampa (clique no mapa em {lat_c:.5f}, {lon_c:.5f})",
                    )
                st.rerun()

    # Barra de gerenciamento rápido dos lotes selecionados no estudo
    st.markdown(f"**Lotes selecionados no estudo ({len(resultado.lotes)}):**")
    cols_lotes = st.columns(min(len(resultado.lotes) + 1, 5))
    for idx_l, lote_sel in enumerate(resultado.lotes):
        col_atual = cols_lotes[idx_l % len(cols_lotes)]
        with col_atual:
            st.caption(
                f"**#{idx_l + 1} · SQL {lote_sel.sql_formatado}**  \n"
                f"Área: {lote_sel.area_cartografica_m2:,.2f} m² · "
                f"Testada: {lote_sel.testada_estimada_m:.1f} m"
            )
            if len(resultado.lotes) > 1:
                if st.button(
                    f"Remover #{idx_l + 1} ({lote_sel.sql_formatado})",
                    key=f"btn_rem_lote_{idx_l}_{lote_sel.sql_formatado}",
                    width="stretch",
                ):
                    feats_rest = [l.geojson_wgs84 for i, l in enumerate(resultado.lotes) if i != idx_l]
                    st.session_state["aviso_selecao_mapa"] = (
                        f"Lote SQL {lote_sel.sql_formatado} removido. Restam {len(feats_rest)} lote(s)."
                    )
                    salvar_resultado(
                        feats_rest,
                        client,
                        f"GeoSampa ({len(feats_rest)} lote(s) selecionado(s))",
                        preservar_contexto_atual=True,
                    )
                    st.rerun()

    if len(resultado.lotes) > 1:
        with cols_lotes[-1]:
            st.caption("**Ação rápida**")
            if st.button("Manter apenas o 1º lote", key="btn_limpar_multilote", width="stretch"):
                primeiro = [resultado.lotes[0].geojson_wgs84]
                st.session_state["aviso_selecao_mapa"] = "Seleção redefinida para o 1º lote."
                salvar_resultado(
                    primeiro,
                    client,
                    "GeoSampa (1 lote selecionado)",
                    preservar_contexto_atual=True,
                )
                st.rerun()

    renderizar_painel_viabilidade(resultado)
    renderizar_tabela_unitario_vs_unificado(resultado)
    renderizar_tabelas_geometricas(resultado)


if __name__ == "__main__":
    main()
