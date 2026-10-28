"""
Componentes visuais do Dashboard (Streamlit):
- Cabeçalho e indicadores físicos do lote/terreno
- Estudo de viabilidade (CA, TO, permeabilidade, gabarito, recuos) e topografia
- Tabelas de arestas, lotes consultados e atributos brutos do GeoSampa
- Exportação (GeoJSON, JSON e CSV)

Todos os textos ficam visíveis: cards e tabelas quebram linha, sem abas nem seções recolhidas.
"""

import json
import math

import pandas as pd
import streamlit as st

from domain.models import ResultadoTerreno
from domain.zoning_rules import ZONING_DATABASE, obter_parametros_zoneamento
from ui.styles import cabecalho_terreno, grade_cards, nota, tabela, titulo_secao


def _m2(valor: float) -> str:
    return f"{valor:,.2f} m²".replace(",", "X").replace(".", ",").replace("X", ".")


def _m(valor: float) -> str:
    return f"{valor:,.2f} m".replace(",", "X").replace(".", ",").replace("X", ".")


def renderizar_resumo_terreno(resultado: ResultadoTerreno) -> None:
    """Cabeçalho de identificação, alertas e indicadores físicos do terreno."""
    sqls = [l.sql_formatado for l in resultado.lotes]
    titulo = " + ".join(sqls)
    local = resultado.endereco_aproximado or (
        f"Coordenadas: {resultado.centroide_latlon[0]:.6f}, {resultado.centroide_latlon[1]:.6f}"
    )
    zona = resultado.zoneamento.sigla_zona if resultado.zoneamento else "Não identificada"

    cabecalho_terreno(
        eyebrow=f"SQL (Setor.Quadra.Lote) · Fonte: {resultado.fonte_dados}",
        titulo=titulo,
        subtitulo=local,
        badge=f"Zona {zona}",
    )

    for aviso in resultado.avisos:
        nota(aviso, "warn")

    if resultado.tombamento_detectado:
        nota(
            "Atenção: incidência de patrimônio cultural / tombamento no lote — "
            + "; ".join(resultado.detalhes_tombamento),
            "alert",
        )

    titulo_secao("Dados do terreno", "Medidas calculadas sobre o polígono em SIRGAS 2000 / UTM 23S (EPSG:31983).")
    grade_cards(
        [
            ("Área total", _m2(resultado.area_total_m2),
             f"{len(resultado.lotes)} lotes unificados" if resultado.unificado else "Lote único"),
            ("Perímetro", _m(resultado.perimetro_total_m), f"{len(resultado.arestas)} lados"),
            ("Testada / largura estimada", _m(resultado.testada_principal_m), None),
            ("Profundidade estimada", _m(resultado.profundidade_estimada_m), None),
            ("Regularidade da forma", f"{resultado.fator_regularidade * 100:.1f}%",
             "Próximo de retângulo" if resultado.fator_regularidade >= 0.88 else "Polígono irregular"),
            ("Centroide (lat, lon)",
             f"{resultado.centroide_latlon[0]:.6f}, {resultado.centroide_latlon[1]:.6f}", None),
        ]
    )

    lat_p, lon_p = resultado.centroide_latlon
    e_utm, n_utm = getattr(resultado, "ponto_utm", (0.0, 0.0))
    sub_ponto = (
        f"2ª consulta espacial realizada a partir do ponto geográfico do lote: "
        f"Lat/Lon ({lat_p:.6f}, {lon_p:.6f}) · SIRGAS 2000 UTM 23S (E {e_utm:,.2f} m, N {n_utm:,.2f} m)."
    )
    titulo_secao(
        "Enquadramento territorial (consulta pelo ponto geográfico do lote)",
        sub_ponto,
    )
    zona_txt = resultado.zoneamento.sigla_zona if resultado.zoneamento else "Não identificada"
    cards = [
        (info.tema, info.valor or "Não encontrado", info.observacao)
        for info in _infos_territoriais(resultado)
    ]
    cards.append(("Zona de uso (LPUOS)", zona_txt, ", ".join(resultado.zonas_detectadas) or None))
    grade_cards(cards)


def _infos_territoriais(resultado: ResultadoTerreno):
    return [i for i in (resultado.macrozona, resultado.macroarea, resultado.qualificacao_ambiental) if i]


def renderizar_painel_viabilidade(resultado: ResultadoTerreno) -> None:
    """Parâmetros urbanísticos aplicados à área real do terreno, com simulação de zona."""
    titulo_secao(
        "Estudo preliminar de viabilidade",
        "Índices da LPUOS aplicados à área do terreno. Confira sempre o Quadro 3 da lei vigente.",
    )

    opcoes = list(ZONING_DATABASE.keys())
    atual = resultado.zoneamento.sigla_zona.upper() if resultado.zoneamento else "ZM"
    indice = opcoes.index(atual) if atual in opcoes else opcoes.index("ZM")

    col_sel, col_desc = st.columns([1, 2], gap="large")
    with col_sel:
        zona_escolhida = st.selectbox(
            "Zona de uso (detectada ou simulação)",
            options=opcoes,
            index=indice,
        )
    params = obter_parametros_zoneamento(zona_escolhida)
    resultado.zoneamento = params
    if not params:
        return

    with col_desc:
        nota(f"{params.sigla_zona} — {params.nome_zona}. {params.descricao_uso} Referência: {params.legislacao_ref}.")

    area = resultado.area_total_m2
    pot_basico = area * params.ca_basico
    pot_maximo = area * params.ca_maximo
    outorga = max(0.0, pot_maximo - pot_basico)
    projecao = area * params.taxa_ocupacao_max
    permeavel = area * params.taxa_permeabilidade_min
    gabarito = f"{params.gabarito_altura_max_m:.0f} m" if params.gabarito_altura_max_m else "Sem limite"
    pavimentos = (
        int(params.gabarito_altura_max_m // 3.0)
        if params.gabarito_altura_max_m
        else max(1, int(math.ceil(pot_maximo / max(projecao * 0.75, 1.0))))
    )

    st.write("")
    grade_cards(
        [
            (f"Potencial construtivo básico (CA {params.ca_basico:.1f})", _m2(pot_basico), "Sem outorga onerosa"),
            (f"Potencial construtivo máximo (CA {params.ca_maximo:.1f})", _m2(pot_maximo), None),
            ("Área sujeita a outorga onerosa", _m2(outorga), "Máximo − básico"),
            (f"Projeção máxima (TO {params.taxa_ocupacao_max * 100:.0f}%)", _m2(projecao),
             f"Área livre: {_m2(area - projecao)}"),
            (f"Área permeável mínima (TP {params.taxa_permeabilidade_min * 100:.0f}%)", _m2(permeavel), None),
            ("Gabarito máximo de altura", gabarito, f"Cerca de {pavimentos} pavimentos (estimativa)"),
        ]
    )

    titulo_secao("Quadro de índices e recuos")
    tabela(
        ["Parâmetro", "Valor", "Aplicado ao terreno"],
        [
            ["Coeficiente de aproveitamento mínimo", f"{params.ca_minimo:.2f}", _m2(area * params.ca_minimo)],
            ["Coeficiente de aproveitamento básico", f"{params.ca_basico:.2f}", _m2(pot_basico)],
            ["Coeficiente de aproveitamento máximo", f"{params.ca_maximo:.2f}", _m2(pot_maximo)],
            ["Taxa de ocupação máxima", f"{params.taxa_ocupacao_max * 100:.0f}%", _m2(projecao)],
            ["Taxa de permeabilidade mínima", f"{params.taxa_permeabilidade_min * 100:.0f}%", _m2(permeavel)],
            ["Recuo de frente mínimo", _m(params.recuo_frontal_m), "—"],
            ["Recuos laterais e de fundo", params.recuo_lateral_fundo_m, "—"],
        ],
    )

    titulo_secao("Topografia", "Curvas de nível do GeoSampa que cruzam o terreno.")
    topo = resultado.topografia
    if topo and topo.cota_min_m is not None:
        grade_cards(
            [
                ("Cota mínima", _m(topo.cota_min_m), None),
                ("Cota máxima", _m(topo.cota_max_m), None),
                ("Desnível estimado", _m(topo.desnivel_m), f"Declividade média ≈ {topo.declividade_media_pct:.2f}%"),
                ("Situação", topo.observacao, None),
            ]
        )
    else:
        nota(topo.observacao if topo else "Topografia não consultada.")


def gerar_dataframe_unitario_vs_unificado(resultado: ResultadoTerreno) -> pd.DataFrame:
    """
    Gera um DataFrame estruturado comparando cada lote individual (Unitário)
    com o resultado consolidado do terreno (Unificado).
    """
    zona_padrao = resultado.zoneamento.sigla_zona if resultado.zoneamento else "ZM"
    params_padrao = resultado.zoneamento or obter_parametros_zoneamento(zona_padrao)
    area_total = max(resultado.area_total_m2, 0.01)

    registros = []
    for idx, lote in enumerate(resultado.lotes, start=1):
        sigla_lote = lote.zona_incidente or zona_padrao
        p_lote = obter_parametros_zoneamento(sigla_lote) or params_padrao
        ca_b = p_lote.ca_basico if p_lote else 1.0
        ca_m = p_lote.ca_maximo if p_lote else 2.0
        to_max = p_lote.taxa_ocupacao_max if p_lote else 0.70
        tp_min = p_lote.taxa_permeabilidade_min if p_lote else 0.15

        area_u = round(lote.area_cartografica_m2, 2)
        pot_b = round(area_u * ca_b, 2)
        pot_m = round(area_u * ca_m, 2)
        outorga_u = round(max(0.0, pot_m - pot_b), 2)
        proj_u = round(area_u * to_max, 2)
        perm_u = round(area_u * tp_min, 2)

        registros.append(
            {
                "Tipo": f"Unitário #{idx}",
                "SQL": lote.sql_formatado,
                "Setor": lote.setor,
                "Quadra": lote.quadra,
                "Lote": lote.lote,
                "Area_m2": area_u,
                "Participacao_pct": round((area_u / area_total) * 100.0, 2),
                "Testada_Estimada_m": round(lote.testada_estimada_m, 2),
                "Profundidade_Estimada_m": round(lote.profundidade_estimada_m, 2),
                "Perimetro_m": round(lote.perimetro_m, 2),
                "Zona": sigla_lote,
                "CA_Basico": ca_b,
                "CA_Maximo": ca_m,
                "Potencial_Basico_m2": pot_b,
                "Potencial_Maximo_m2": pot_m,
                "Outorga_Onerosa_m2": outorga_u,
                "Projecao_Max_TO_m2": proj_u,
                "Area_Permeavel_TP_m2": perm_u,
            }
        )

    ca_b_tot = params_padrao.ca_basico if params_padrao else 1.0
    ca_m_tot = params_padrao.ca_maximo if params_padrao else 2.0
    to_tot = params_padrao.taxa_ocupacao_max if params_padrao else 0.70
    tp_tot = params_padrao.taxa_permeabilidade_min if params_padrao else 0.15

    area_unif = round(resultado.area_total_m2, 2)
    pot_b_unif = round(area_unif * ca_b_tot, 2)
    pot_m_unif = round(area_unif * ca_m_tot, 2)
    outorga_unif = round(max(0.0, pot_m_unif - pot_b_unif), 2)
    proj_unif = round(area_unif * to_tot, 2)
    perm_unif = round(area_unif * tp_tot, 2)

    registros.append(
        {
            "Tipo": f"UNIFICADO ({len(resultado.lotes)} lote{'s' if len(resultado.lotes) != 1 else ''})",
            "SQL": " + ".join(l.sql_formatado for l in resultado.lotes),
            "Setor": resultado.lotes[0].setor if resultado.lotes else "—",
            "Quadra": resultado.lotes[0].quadra if resultado.lotes else "—",
            "Lote": f"{len(resultado.lotes)} lote(s)",
            "Area_m2": area_unif,
            "Participacao_pct": 100.0,
            "Testada_Estimada_m": round(resultado.testada_principal_m, 2),
            "Profundidade_Estimada_m": round(resultado.profundidade_estimada_m, 2),
            "Perimetro_m": round(resultado.perimetro_total_m, 2),
            "Zona": zona_padrao,
            "CA_Basico": ca_b_tot,
            "CA_Maximo": ca_m_tot,
            "Potencial_Basico_m2": pot_b_unif,
            "Potencial_Maximo_m2": pot_m_unif,
            "Outorga_Onerosa_m2": outorga_unif,
            "Projecao_Max_TO_m2": proj_unif,
            "Area_Permeavel_TP_m2": perm_unif,
        }
    )
    return pd.DataFrame(registros)


def renderizar_tabela_unitario_vs_unificado(resultado: ResultadoTerreno) -> None:
    """
    Exibe a tabela comparativa completa entre cada Lote Unitário selecionado e o Terreno Unificado,
    com botão direto de download em CSV (compatível com Excel).
    """
    qtd = len(resultado.lotes)
    sub = (
        f"Comparativo direto entre os {qtd} lotes individuais selecionados (Unitário) e o polígono remembrado (Unificado)."
        if qtd > 1
        else "Valores do lote unitário atual e linha consolidada. Clique em lotes vizinhos no mapa para unificar e comparar."
    )
    titulo_secao("Tabela comparativa: Lotes Unitários vs. Terreno Unificado", sub)

    df = gerar_dataframe_unitario_vs_unificado(resultado)
    colunas_visuais = [
        "Item",
        "SQL",
        "Área (m²)",
        "% Área",
        "Testada est.",
        "Profundidade est.",
        "Perímetro",
        "Zona",
        "Pot. Básico (CA bás.)",
        "Pot. Máximo (CA máx.)",
        "Outorga Onerosa",
        "Projeção Máx. (TO)",
        "Área Permeável (TP)",
    ]

    linhas_visuais = []
    for _, row in df.iterrows():
        linhas_visuais.append(
            [
                str(row["Tipo"]),
                str(row["SQL"]),
                _m2(float(row["Area_m2"])),
                f"{float(row['Participacao_pct']):.1f}%",
                _m(float(row["Testada_Estimada_m"])),
                _m(float(row["Profundidade_Estimada_m"])),
                _m(float(row["Perimetro_m"])),
                str(row["Zona"]),
                _m2(float(row["Potencial_Basico_m2"])),
                _m2(float(row["Potencial_Maximo_m2"])),
                _m2(float(row["Outorga_Onerosa_m2"])),
                _m2(float(row["Projecao_Max_TO_m2"])),
                _m2(float(row["Area_Permeavel_TP_m2"])),
            ]
        )

    tabela(colunas_visuais, linhas_visuais, destacar_ultima_linha=True)

    soma_perimetros_unit = sum(l.perimetro_m for l in resultado.lotes)
    divisa_eliminada = max(0.0, soma_perimetros_unit - resultado.perimetro_total_m)
    col_resumo, col_dl = st.columns([2.6, 1.2], vertical_alignment="center")
    with col_resumo:
        if qtd > 1:
            nota(
                f"Síntese da unificação ({qtd} lotes): Área somada = {_m2(resultado.area_total_m2)} · "
                f"Soma dos perímetros unitários = {_m(soma_perimetros_unit)} → Perímetro unificado = {_m(resultado.perimetro_total_m)} "
                f"(divisas internas suprimidas: {_m(divisa_eliminada)})."
            )
        else:
            st.caption(
                "Dica: no mapa interativo acima, clique sobre os lotes vizinhos para selecioná-los no estudo e comparar cada lote unitário com o terreno unificado."
            )
    with col_dl:
        base_sql = resultado.lotes[0].sql_formatado.replace(".", "_") if resultado.lotes else "terreno"
        csv_bytes = df.to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig")
        st.download_button(
            "Baixar tabela Unitário vs. Unificado (.csv)",
            data=csv_bytes,
            file_name=f"unitario_vs_unificado_{base_sql}.csv",
            mime="text/csv",
            width="stretch",
            key="btn_dl_unitario_unificado_topo",
        )


def renderizar_tabelas_geometricas(resultado: ResultadoTerreno) -> None:
    """Tabelas de lados, lotes, atributos brutos e botões de exportação — tudo visível."""
    titulo_secao("Dimensões dos lados (Terreno Unificado)", "Numeração igual às etiquetas L1, L2… exibidas no mapa.")
    if resultado.arestas:
        perimetro = max(resultado.perimetro_total_m, 1.0)
        tabela(
            ["Lado", "Comprimento", "% do perímetro", "Azimute", "Orientação", "Início (lat, lon)", "Fim (lat, lon)"],
            [
                [
                    f"L{a.indice}",
                    _m(a.comprimento_m),
                    f"{a.comprimento_m / perimetro * 100:.1f}%",
                    f"{a.azimute_graus:.1f}°",
                    a.orientacao_cardeal,
                    f"{a.ponto_inicial_latlon[0]:.6f}, {a.ponto_inicial_latlon[1]:.6f}",
                    f"{a.ponto_final_latlon[0]:.6f}, {a.ponto_final_latlon[1]:.6f}",
                ]
                for a in resultado.arestas
            ],
        )
    else:
        nota("Nenhum lado extraído do polígono.")

    titulo_secao("Atributos retornados pelo GeoSampa", "Campos originais de cada lote, sem tratamento.")
    for l in resultado.lotes:
        attrs = {k: v for k, v in l.atributos_brutos.items() if not k.startswith("_")}
        st.markdown(f"**SQL {l.sql_formatado}**")
        if attrs:
            tabela(["Campo", "Valor"], [[k, "—" if v in (None, "") else v] for k, v in attrs.items()])
        else:
            nota("Nenhum atributo retornado.")
        st.write("")

    for info in _infos_territoriais(resultado):
        if info.atributos:
            st.markdown(f"**{info.tema}** — camada `{info.camada}`")
            tabela(["Campo", "Valor"], [[k, "—" if v in (None, "") else v] for k, v in info.atributos.items()])
            st.write("")

    titulo_secao("Exportar", "GeoJSON para QGIS/CAD, ficha em JSON, tabela Unitário vs. Unificado e lados em CSV (Excel).")
    base = resultado.lotes[0].sql_formatado.replace(".", "_")
    c1, c2, c3, c4 = st.columns(4)

    c1.download_button(
        "Polígono (.geojson)",
        data=json.dumps(resultado.geojson_unificado_wgs84, ensure_ascii=False, indent=2),
        file_name=f"terreno_{base}.geojson",
        mime="application/geo+json",
        width="stretch",
    )

    z = resultado.zoneamento
    df_comp = gerar_dataframe_unitario_vs_unificado(resultado)
    ficha = {
        "sqls": [l.sql_formatado for l in resultado.lotes],
        "unificado": resultado.unificado,
        "area_total_m2": resultado.area_total_m2,
        "perimetro_total_m": resultado.perimetro_total_m,
        "testada_estimada_m": resultado.testada_principal_m,
        "profundidade_estimada_m": resultado.profundidade_estimada_m,
        "centroide_latlon": resultado.centroide_latlon,
        "macrozona": resultado.macrozona.valor if resultado.macrozona else None,
        "macroarea": resultado.macroarea.valor if resultado.macroarea else None,
        "perimetro_qualificacao_ambiental": (
            resultado.qualificacao_ambiental.valor if resultado.qualificacao_ambiental else None
        ),
        "zoneamento": {
            "sigla": z.sigla_zona if z else None,
            "nome": z.nome_zona if z else None,
            "ca_basico": z.ca_basico if z else None,
            "ca_maximo": z.ca_maximo if z else None,
            "taxa_ocupacao_max": z.taxa_ocupacao_max if z else None,
            "potencial_basico_m2": resultado.potencial_construtivo_basico_m2,
            "potencial_maximo_m2": resultado.potencial_construtivo_maximo_m2,
            "projecao_maxima_m2": resultado.projecao_maxima_m2,
        },
        "comparativo_unitario_vs_unificado": df_comp.to_dict(orient="records"),
        "lados": [
            {"lado": f"L{a.indice}", "comprimento_m": a.comprimento_m,
             "azimute_graus": a.azimute_graus, "orientacao": a.orientacao_cardeal}
            for a in resultado.arestas
        ],
    }
    c2.download_button(
        "Ficha de viabilidade (.json)",
        data=json.dumps(ficha, ensure_ascii=False, indent=2),
        file_name=f"viabilidade_{base}.json",
        mime="application/json",
        width="stretch",
    )

    c3.download_button(
        "Unitário vs. Unificado (.csv)",
        data=df_comp.to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig"),
        file_name=f"unitario_vs_unificado_{base}.csv",
        mime="text/csv",
        width="stretch",
        key="btn_dl_unitario_unificado_rodape",
    )

    if resultado.arestas:
        csv = pd.DataFrame(
            [{"Lado": f"L{a.indice}", "Comprimento_m": a.comprimento_m,
              "Azimute_graus": a.azimute_graus, "Orientacao": a.orientacao_cardeal}
             for a in resultado.arestas]
        ).to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig")
        c4.download_button(
            "Lados do terreno (.csv)",
            data=csv,
            file_name=f"lados_{base}.csv",
            mime="text/csv",
            width="stretch",
        )
