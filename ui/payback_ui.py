"""Página de payback: premissas, indicadores e gráficos (Streamlit + Altair)."""

from typing import Dict, Optional

import altair as alt
import pandas as pd
import streamlit as st

from services.aproveitamento import ResultadoAproveitamento
from services.payback import EntradaPayback, ResultadoPayback, calcular_payback, sensibilidade_payback
from ui.styles import aplicar_estilos, grade_cards, nota, preservar_campos, tabela, titulo_secao

# Paleta validada (scripts/validate_palette.js do guia de visualização), em tema claro e escuro.
TEMAS: Dict[str, Dict[str, str]] = {
    "light": {
        "simples": "#2a78d6", "descontado": "#eb6834", "entrada": "#2a78d6", "saida": "#e34948",
        "texto": "#0b0b0b", "texto2": "#52514e", "mudo": "#898781", "grade": "#e1e0d9", "base": "#c3c2b7", "neutro": "#f0efec", "fundo": "#ffffff",
        "seq_baixo": "#cde2fb", "seq_alto": "#104281",
    },
    "dark": {
        "simples": "#3987e5", "descontado": "#d95926", "entrada": "#3987e5", "saida": "#e66767",
        "texto": "#f0efec", "texto2": "#c3c2b7", "mudo": "#898781", "grade": "#2c2c2a", "base": "#383835", "neutro": "#383835", "fundo": "#0e1117",
        "seq_baixo": "#104281", "seq_alto": "#cde2fb",
    },
}
ROTULO_SIMPLES = "Acumulado simples"
ROTULO_DESCONTADO = "Acumulado descontado"


def _tema() -> Dict[str, str]:
    tipo = getattr(st.context.theme, "type", None) if hasattr(st.context, "theme") else None
    return TEMAS["dark" if tipo == "dark" else "light"]


def _num(valor: float, casas: int = 0) -> str:
    return f"{valor:,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".").replace("-", "−")


def _rs(valor: float) -> str:
    sinal = "−" if valor < 0 else ""
    return f"{sinal}R$ {_num(abs(valor))}"


def _rs_mi(valor: float) -> str:
    sinal = "−" if valor < 0 else ""
    return f"{sinal}R$ {_num(abs(valor) / 1e6, 1)} mi"


def _mes(valor: Optional[int]) -> str:
    return "Não se paga" if valor is None else f"Mês {valor}"


def _estilo(grafico: alt.Chart, t: Dict[str, str]) -> alt.Chart:
    return (
        grafico.configure(background="transparent", font="sans-serif")
        .configure_view(stroke=None)
        .configure_axis(labelColor=t["texto2"], titleColor=t["texto2"], gridColor=t["grade"], domainColor=t["base"],
                        tickColor=t["base"], labelFontSize=12, titleFontSize=12, titleFontWeight="normal")
        .configure_legend(labelColor=t["texto2"], titleColor=t["texto2"], labelFontSize=12, orient="top", title=None, symbolStrokeWidth=2)
    )


_EIXO_MILHOES = "replace(format(datum.value / 1000000, ',.0f'), ',', '.') + ' mi'"


def _grafico_acumulado(r: ResultadoPayback, t: Dict[str, str]) -> alt.Chart:
    base = pd.DataFrame(
        {
            "mes": [m.mes for m in r.meses],
            ROTULO_SIMPLES: [m.acumulado for m in r.meses],
            ROTULO_DESCONTADO: [m.acumulado_descontado for m in r.meses],
            "txt_simples": [_rs(m.acumulado) for m in r.meses],
            "txt_desc": [_rs(m.acumulado_descontado) for m in r.meses],
        }
    )
    longo = base.melt(id_vars=["mes"], value_vars=[ROTULO_SIMPLES, ROTULO_DESCONTADO], var_name="serie", value_name="valor")
    horizonte = r.meses[-1].mes
    valor_min, valor_max = float(longo["valor"].min()), float(longo["valor"].max())
    folga = (valor_max - valor_min) * 0.10
    escala_x = alt.Scale(domain=[0, horizonte * 1.16], nice=False)  # sobra à direita para os rótulos
    escala_y = alt.Scale(domain=[valor_min - folga, valor_max + folga], nice=True)
    eixo_x = alt.X("mes:Q", title="Mês do empreendimento", scale=escala_x, axis=alt.Axis(grid=False, values=list(range(0, horizonte + 1, 6)), format="d"))
    eixo_y = alt.Y("valor:Q", title=None, scale=escala_y, axis=alt.Axis(labelExpr=_EIXO_MILHOES, tickCount=6, domain=False, ticks=False))
    cor = alt.Color("serie:N", scale=alt.Scale(domain=[ROTULO_SIMPLES, ROTULO_DESCONTADO], range=[t["simples"], t["descontado"]]))

    linhas = alt.Chart(longo).mark_line(strokeWidth=2).encode(x=eixo_x, y=eixo_y, color=cor)
    zero = alt.Chart(pd.DataFrame({"valor": [0.0]})).mark_rule(color=t["mudo"], strokeWidth=1).encode(y=alt.Y("valor:Q", scale=escala_y))

    # Crosshair com todos os valores do mês no tooltip
    selecao = alt.selection_point(fields=["mes"], nearest=True, on="pointerover", empty=False, clear="pointerout")
    alvo = alt.Chart(base).mark_rule(strokeWidth=12, opacity=0).encode(
        x=alt.X("mes:Q", scale=escala_x),
        tooltip=[alt.Tooltip("mes:Q", title="Mês"), alt.Tooltip("txt_simples:N", title=ROTULO_SIMPLES),
                 alt.Tooltip("txt_desc:N", title=ROTULO_DESCONTADO)],
    ).add_params(selecao)
    guia = alt.Chart(base).mark_rule(color=t["mudo"], strokeWidth=1).encode(x=alt.X("mes:Q", scale=escala_x)).transform_filter(selecao)

    # Marcos: exposição máxima e meses de payback, com rótulo direto
    marcos = [{"mes": r.mes_exposicao_maxima, "valor": r.exposicao_maxima, "rotulo": f"Exposição máxima: {_rs_mi(r.exposicao_maxima)}",
               "cor": t["simples"], "posicao": "abaixo"}]
    # Perto do fim do fluxo, o rótulo vai para a direita do ponto; antes disso, centralizado.
    lado = "direita" if horizonte and (r.payback_descontado_mes or r.payback_simples_mes or 0) > horizonte * 0.6 else "centro"
    if r.payback_simples_mes is not None:
        marcos.append({"mes": r.payback_simples_mes, "valor": r.meses[r.payback_simples_mes].acumulado,
                       "rotulo": f"Payback: mês {r.payback_simples_mes}", "cor": t["simples"],
                       "posicao": "direita_acima" if lado == "direita" else "acima"})
    if r.payback_descontado_mes is not None:
        marcos.append({"mes": r.payback_descontado_mes, "valor": r.meses[r.payback_descontado_mes].acumulado_descontado,
                       "rotulo": f"Descontado: mês {r.payback_descontado_mes}", "cor": t["descontado"],
                       "posicao": "direita_abaixo" if lado == "direita" else "abaixo"})
    df_marcos = pd.DataFrame(marcos)
    pontos = alt.Chart(df_marcos).mark_point(size=70, filled=True, opacity=1, stroke=t["fundo"], strokeWidth=2).encode(
        x=alt.X("mes:Q", scale=escala_x), y=alt.Y("valor:Q", scale=escala_y), color=alt.Color("cor:N", scale=None, legend=None))

    def rotulos(posicao, **estilo):
        return alt.Chart(df_marcos[df_marcos["posicao"] == posicao]).mark_text(
            fontSize=12, fontWeight=600, color=t["texto"], **estilo
        ).encode(x=alt.X("mes:Q", scale=escala_x), y=alt.Y("valor:Q", scale=escala_y), text="rotulo:N")

    grafico = alt.layer(
        zero, linhas, guia, pontos,
        rotulos("abaixo", align="center", dy=18),
        rotulos("acima", align="center", dy=-18),
        rotulos("direita_acima", align="left", dx=10, dy=-6),
        rotulos("direita_abaixo", align="left", dx=10, dy=6),
        alvo,
    ).resolve_scale(color="independent").properties(height=400)
    return _estilo(grafico, t)


def _grafico_mensal(r: ResultadoPayback, t: Dict[str, str]) -> alt.Chart:
    df = pd.DataFrame(
        [
            linha
            for m in r.meses
            for linha in (
                {"mes": m.mes, "tipo": "Entradas", "valor": m.entradas, "txt": _rs(m.entradas)},
                {"mes": m.mes, "tipo": "Saídas", "valor": -m.saidas, "txt": _rs(m.saidas)},
            )
        ]
    )
    barras = alt.Chart(df).mark_bar(cornerRadiusEnd=2).encode(
        x=alt.X("mes:O", title="Mês do empreendimento",
                axis=alt.Axis(labelAngle=0, grid=False, labelExpr="datum.value % 6 === 0 ? datum.value : ''", ticks=False)),
        y=alt.Y("valor:Q", title=None, stack=None, axis=alt.Axis(labelExpr=_EIXO_MILHOES, tickCount=6, domain=False, ticks=False)),
        color=alt.Color("tipo:N", scale=alt.Scale(domain=["Entradas", "Saídas"], range=[t["entrada"], t["saida"]])),
        tooltip=[alt.Tooltip("mes:O", title="Mês"), alt.Tooltip("tipo:N", title="Tipo"), alt.Tooltip("txt:N", title="Valor")],
    )
    zero = alt.Chart(pd.DataFrame({"valor": [0.0]})).mark_rule(color=t["mudo"], strokeWidth=1).encode(y="valor:Q")
    return _estilo(alt.layer(barras, zero).properties(height=280), t)


def _grafico_sensibilidade(linhas, t: Dict[str, str]) -> alt.Chart:
    def rotulo(variacao: float) -> str:
        return "Base" if variacao == 0 else f"{variacao:+.0%}".replace("-", "−")

    def rotulo_prazo(meses: int) -> str:
        return "Base" if meses == 0 else f"{meses:+d} meses".replace("-", "−")

    df = pd.DataFrame(
        [
            {
                "preco": rotulo(l["preco"]),
                "prazo": rotulo_prazo(l["prazo"]),
                "payback": l["payback"],
                "txt": "Não se paga" if l["payback"] is None else str(l["payback"]),
                "lucro": _rs_mi(l["lucro"]),
            }
            for l in linhas
        ]
    )
    com_valor = df[df["payback"].notna()]
    ordem_preco = list(dict.fromkeys(rotulo(l["preco"]) for l in linhas))
    ordem_prazo = list(dict.fromkeys(rotulo_prazo(l["prazo"]) for l in linhas))
    x = alt.X("prazo:N", title="Variação do prazo de obra", sort=ordem_prazo, axis=alt.Axis(labelAngle=0, ticks=False, domain=False, orient="top"))
    y = alt.Y("preco:N", title="Variação do preço de venda", sort=list(reversed(ordem_preco)), axis=alt.Axis(ticks=False, domain=False))
    dica = [alt.Tooltip("preco:N", title="Preço"), alt.Tooltip("prazo:N", title="Prazo de obra"),
            alt.Tooltip("txt:N", title="Payback (mês)"), alt.Tooltip("lucro:N", title="Lucro")]
    fundo = alt.Chart(df).mark_rect(color=t["neutro"], stroke=t["fundo"], strokeWidth=2, cornerRadius=3).encode(x=x, y=y, tooltip=dica)
    camadas = [fundo]
    if not com_valor.empty:
        minimo, maximo = float(com_valor["payback"].min()), float(com_valor["payback"].max())
        maximo = max(maximo, minimo + 1)  # valor único fica no tom mais claro, com texto legível
        meio = (minimo + maximo) / 2
        celulas = alt.Chart(com_valor).mark_rect(stroke=t["fundo"], strokeWidth=2, cornerRadius=3).encode(
            x=x, y=y, tooltip=dica,
            color=alt.Color("payback:Q", title="Mês do payback",
                            scale=alt.Scale(domain=[minimo, maximo], range=[t["seq_baixo"], t["seq_alto"]]),
                            legend=None),
        )
        escura = t["seq_alto"] == TEMAS["light"]["seq_alto"]
        texto_claro = "#ffffff" if escura else "#0b0b0b"
        texto_escuro = "#0b0b0b" if escura else "#ffffff"
        cor_texto = alt.condition(f"datum.payback > {meio}", alt.value(texto_claro), alt.value(texto_escuro))
        textos = alt.Chart(com_valor).mark_text(fontSize=13, fontWeight=600).encode(x=x, y=y, text="txt:N", color=cor_texto)
        camadas += [celulas, textos]
    sem_valor = df[df["payback"].isna()]
    if not sem_valor.empty:
        camadas.append(alt.Chart(sem_valor).mark_text(fontSize=11, color=t["texto2"]).encode(x=x, y=y, text="txt:N"))
    return _estilo(alt.layer(*camadas).resolve_scale(color="independent").properties(height=280), t)


def _campos_premissas(atual: Optional[ResultadoAproveitamento], id_terreno: str, area_terreno: float) -> EntradaPayback:
    computavel = atual.computavel_usada_m2 if atual else 5000.0
    # A chave muda com o estudo, para as áreas e a outorga acompanharem a página principal.
    id_estudo = f"{id_terreno}|{computavel:.0f}"
    outorga_padrao = float(round(atual.outorga_total, 2)) if atual and atual.outorga_total else 0.0

    def numero(coluna, rotulo, chave, padrao, passo=None, ajuda=None, minimo=0.0):
        return coluna.number_input(rotulo, min_value=minimo, value=padrao, step=passo, key=f"pb_{chave}", help=ajuda)

    def pct(coluna, rotulo, chave, padrao, ajuda=None):
        return numero(coluna, rotulo, chave, padrao, 1.0, ajuda) / 100

    def inteiro(coluna, rotulo, chave, padrao, ajuda=None):
        return int(coluna.number_input(rotulo, min_value=0, value=padrao, step=1, key=f"pb_{chave}", help=ajuda))

    st.markdown("**Produto e receita**")
    c1, c2, c3, c4 = st.columns(4)
    privativa = numero(c1, "Área privativa vendável (m²)", f"priv_{id_estudo}", round(computavel * 0.8, 0), 100.0,
                       "Sugestão: 80% da computável usada na página principal.")
    preco = numero(c2, "Preço de venda (R$/m² privativo)", "preco", 12000.0, 100.0)
    construida = numero(c3, "Área construída total (m²)", f"constr_{id_estudo}", round(computavel * 1.5, 0), 100.0,
                        "Sugestão: 1,5 × a computável. Inclui garagem e demais não computáveis.")
    custo_obra = numero(c4, "Custo de obra (R$/m² construído)", "obra", 3500.0, 100.0)

    st.markdown("**Terreno e demais custos**")
    c1, c2, c3, c4 = st.columns(4)
    terreno = numero(c1, "Preço do terreno (R$)", f"terreno_{id_terreno}", round(area_terreno * 3000.0, 0), 100000.0)
    entrada = pct(c2, "Entrada do terreno (%)", "ent_terreno", 100.0, "Usada só com parcelas. Sem parcelas, tudo é pago no mês 0.")
    parcelas = inteiro(c3, "Parcelas do saldo do terreno (meses)", "parc_terreno", 0)
    outorga = numero(c4, "Outorga onerosa (R$)", f"outorga_{id_estudo}_{outorga_padrao:.0f}", outorga_padrao, 10000.0,
                     "Vem da página principal quando o valor V e a macroárea foram informados.")
    c1, c2, c3, c4 = st.columns(4)
    projetos = pct(c1, "Projetos e aprovação (% da obra)", "projetos", 5.0)
    adm = pct(c2, "Administração (% da obra)", "adm", 8.0)
    comercial = pct(c3, "Comissão e marketing (% do VGV)", "comercial", 6.0)
    impostos = pct(c4, "Impostos (% da receita)", "impostos", 4.0, "Confirme o regime tributário do empreendimento com o contador.")

    st.markdown("**Prazos, vendas e taxa**")
    c1, c2, c3, c4 = st.columns(4)
    lancamento = inteiro(c1, "Lançamento (mês)", "lanc", 6)
    inicio_obra = inteiro(c2, "Início da obra (mês)", "ini_obra", 9)
    duracao = int(c3.number_input("Duração da obra (meses)", min_value=1, value=24, step=1, key="pb_dur_obra"))
    tma = pct(c4, "TMA (% ao ano)", "tma", 15.0, "Taxa mínima de atratividade, usada no payback descontado e no VPL.")
    c1, c2, c3, c4 = st.columns(4)
    no_lancamento = pct(c1, "Vendido no lançamento (%)", "vend_lanc", 30.0)
    prazo_vendas = inteiro(c2, "Meses para vender o restante", "prazo_vend", 18)
    ate_chaves = pct(c3, "Recebido até as chaves (%)", "ate_chaves", 30.0, "O restante entra de uma vez no repasse.")
    repasse = inteiro(c4, "Repasse após as chaves (meses)", "repasse", 2)

    if atual and atual.adicional_a_pagar_m2 > 0 and not outorga:
        nota("A outorga está zerada, mas o estudo usa potencial adicional. Informe V e a macroárea na página principal, ou digite o valor aqui.", "warn")
    if atual and construida > atual.area_total_max_m2:
        nota(f"A área construída passa do limite estimado de {_num(atual.area_total_max_m2)} m² pelo art. 62, § 2º, da LPUOS.", "warn")

    return EntradaPayback(
        area_privativa_m2=privativa, preco_venda_m2=preco, area_construida_m2=construida, custo_obra_m2=custo_obra,
        custo_terreno=terreno, terreno_entrada_pct=entrada, terreno_parcelas_meses=parcelas, outorga=outorga,
        projetos_pct_obra=projetos, administracao_pct_obra=adm, comercial_pct_vgv=comercial, impostos_pct_receita=impostos,
        mes_lancamento=lancamento, mes_inicio_obra=inicio_obra, duracao_obra_meses=duracao,
        vendas_lancamento_pct=no_lancamento, duracao_vendas_meses=prazo_vendas,
        recebido_ate_chaves_pct=ate_chaves, meses_repasse_apos_chaves=repasse, tma_anual=tma,
    )


def _df_fluxo(r: ResultadoPayback) -> pd.DataFrame:
    return pd.DataFrame(
        [{"Mês": m.mes, "Entradas (R$)": round(m.entradas, 2), "Saídas (R$)": round(m.saidas, 2), "Saldo (R$)": round(m.saldo, 2),
          "Acumulado (R$)": round(m.acumulado, 2), "Acumulado descontado (R$)": round(m.acumulado_descontado, 2)} for m in r.meses]
    )


def renderizar_pagina_payback() -> None:
    aplicar_estilos()
    preservar_campos("apv_")  # mantém os campos da página principal ao trocar de página

    st.markdown("## Payback do empreendimento")
    resultado = st.session_state.get("resultado_terreno")
    atual: Optional[ResultadoAproveitamento] = st.session_state.get("aproveitamento_atual")
    if resultado:
        sqls = " + ".join(l.sql_formatado for l in resultado.lotes)
        st.caption(f"Terreno: SQL {sqls} · Zona {atual.zona if atual else 'não calculada'}")
        id_terreno, area_terreno = sqls, atual.area_base_potencial_m2 if atual else resultado.area_total_m2
    else:
        st.caption("Nenhum terreno consultado: abra a página principal para trazer as áreas do estudo.")
        id_terreno, area_terreno = "manual", 1000.0
    nota(
        "Preços, custos, prazos e velocidade de vendas são valores de exemplo, não dados de mercado: substitua pelos do "
        "empreendimento. O fluxo é do projeto, em valores constantes, sem financiamento à produção nem permuta.",
        "alert",
    )

    titulo_secao("Premissas")
    entrada = _campos_premissas(atual, id_terreno, area_terreno)

    try:
        r = calcular_payback(entrada)
        sensibilidade = sensibilidade_payback(entrada)
    except ValueError as erro:
        nota(str(erro), "alert")
        return
    t = _tema()

    titulo_secao("Indicadores")
    grade_cards(
        [
            ("Payback simples", _mes(r.payback_simples_mes), "Acumulado fica positivo de vez"),
            ("Payback descontado", _mes(r.payback_descontado_mes), f"Com TMA de {_num(entrada.tma_anual * 100, 1)}% ao ano"),
            ("Exposição máxima de caixa", _rs(r.exposicao_maxima), f"No mês {r.mes_exposicao_maxima}"),
            ("Lucro do projeto", _rs(r.lucro), f"{_num(r.margem_vgv * 100, 1)}% do VGV de {_rs_mi(r.vgv)}"),
            ("VPL", _rs(r.vpl), None),
            ("TIR", "Sem TIR definida" if r.tir_anual is None else f"{_num(r.tir_anual * 100, 1)}% ao ano", None),
        ]
    )
    for alerta in r.alertas:
        nota(alerta, "warn")

    titulo_secao("Caixa acumulado", "O payback é o mês em que a linha cruza o zero e não volta a ficar negativa.")
    st.altair_chart(_grafico_acumulado(r, t), width="stretch", theme=None)

    titulo_secao("Entradas e saídas por mês", "Mostra de onde vem a exposição: terreno e obra de um lado, recebimentos do outro.")
    st.altair_chart(_grafico_mensal(r, t), width="stretch", theme=None)

    titulo_secao(
        "Sensibilidade do payback simples",
        "Mês do payback conforme preço de venda e prazo de obra. Quanto mais escura a célula, mais demorado o retorno. "
        "Mudar o preço não altera a velocidade de vendas nesta simulação.",
    )
    st.altair_chart(_grafico_sensibilidade(sensibilidade, t), width="stretch", theme=None)

    titulo_secao("Composição dos custos")
    custo_total = r.custo_total or 1.0
    tabela(
        ["Grupo", "Valor", "% do custo total", "% do VGV"],
        [[g, _rs(v), f"{_num(v / custo_total * 100, 1)}%", f"{_num(v / r.vgv * 100, 1)}%"] for g, v in r.custos_por_grupo.items()]
        + [["Total", _rs(r.custo_total), "100,0%", f"{_num(r.custo_total / r.vgv * 100, 1)}%"]],
        destacar_ultima_linha=True,
    )

    titulo_secao("Fluxo de caixa mensal")
    df = _df_fluxo(r)
    st.dataframe(df, hide_index=True, width="stretch", height=320)
    st.download_button("Baixar fluxo de caixa (CSV)", df.to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig"),
                       file_name="fluxo_payback.csv", mime="text/csv")
