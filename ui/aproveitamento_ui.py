"""Interface das contas de aproveitamento do terreno (Streamlit)."""

from typing import Optional

import pandas as pd
import streamlit as st

from domain.legislacao_sp import FATORES_FS, QUADRO_6, extrair_pa, identificar_macroarea_fp
from domain.models import ResultadoTerreno
from services.aproveitamento import (
    EHIS,
    EHMP,
    ORDINARIO,
    EntradaAproveitamento,
    ResultadoAproveitamento,
    calcular_aproveitamento,
)
from ui.styles import grade_cards, nota, preservar_campos, tabela, titulo_secao

MODALIDADES = {ORDINARIO: "LPUOS ordinário", EHIS: "EHIS (Decreto 63.728/24)", EHMP: "EHMP (Decreto 63.728/24)"}
OPCOES_PA = ["Não informado"] + [f"PA {i}" for i in range(1, 14)]
SEM_MACROAREA = "Não identificada"
LINK_QUADRO_14 = (
    "https://plpconsulta.saopaulo.sp.leg.br/Forms/MostrarArquivo?TIPO=Lei&NUMERO=16050&ANO=2014&DOCUMENTO=ANEXO&Anexo=30"
)


def _num(valor: Optional[float], casas: int = 2) -> str:
    if valor is None:
        return "—"
    return f"{valor:,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _m2(valor: Optional[float]) -> str:
    return "—" if valor is None else f"{_num(valor)} m²"


def _pct(valor: Optional[float]) -> str:
    return "Não se aplica" if valor is None else f"{valor * 100:.0f}%"


def _coletar_entrada(resultado: ResultadoTerreno, zona: str) -> EntradaAproveitamento:
    # A chave muda com o terreno e a zona, para que os campos voltem aos dados do novo lote.
    chave = f"{'+'.join(l.sql_formatado for l in resultado.lotes)}|{zona}"
    pa_detectado = extrair_pa(resultado.qualificacao_ambiental.valor) if resultado.qualificacao_ambiental else None
    macro = identificar_macroarea_fp(resultado.macroarea.valor) if resultado.macroarea else None
    opcoes_macro = [SEM_MACROAREA] + list(QUADRO_6)

    st.markdown("**Terreno**")
    c1, c2, c3, c4 = st.columns(4)
    area = c1.number_input("Área do terreno (m²)", min_value=0.01, value=max(round(resultado.area_total_m2, 2), 0.01),
                           key=f"apv_area_{chave}", help="Havendo divergência com a matrícula, vale a menor área apurada.")
    doacao = c2.number_input("Doação / melhoramento (m²)", min_value=0.0, value=0.0, key=f"apv_doacao_{chave}")
    testada = c3.number_input("Testada (m)", min_value=0.0, value=round(resultado.testada_principal_m, 2), key=f"apv_testada_{chave}")
    profundidade = c4.number_input("Profundidade (m)", min_value=0.0, value=round(resultado.profundidade_estimada_m, 2),
                                   key=f"apv_prof_{chave}")
    reservada = st.checkbox(
        "A faixa será reservada como não edificável, e não doada (índices sobre a área original)",
        key=f"apv_reserva_{chave}",
    )

    st.markdown("**Enquadramento e produto**")
    c1, c2, c3, c4 = st.columns(4)
    pa = c1.selectbox("Perímetro de qualificação ambiental", OPCOES_PA,
                      index=OPCOES_PA.index(pa_detectado) if pa_detectado else 0, key=f"apv_pa_{chave}")
    modalidade = c2.selectbox("Modalidade", list(MODALIDADES), format_func=MODALIDADES.get, key=f"apv_mod_{chave}")
    ca_usado = c3.number_input("C.A. a usar (0 = máximo disponível)", min_value=0.0, value=0.0, step=0.1, key=f"apv_ca_{chave}")
    area_media = c4.number_input("Área média da unidade (m²)", min_value=1.0, value=50.0, key=f"apv_media_{chave}")
    c1, c2, c3 = st.columns(3)
    pe_direito = c1.number_input("Pé-direito médio (m)", min_value=2.3, value=3.0, step=0.05, key=f"apv_pd_{chave}")
    solidariedade = c2.checkbox("Usar cota de solidariedade (+20% de computável)", key=f"apv_cota_{chave}")
    eixo_ativado = False
    if zona in ("ZEUP", "ZEUPa", "ZEM", "ZEMP"):
        eixo_ativado = c3.checkbox(
            f"{zona} ativada (PDE art. 83 / LPUOS art. 8º)", key=f"apv_eixo_{chave}",
            help="Só marque com confirmação oficial: muda o C.A. máximo e, em ZEM/ZEMP, dispensa o gabarito.",
        )

    st.markdown("**Outorga onerosa**")
    c1, c2, c3, c4 = st.columns(4)
    valor_v = c1.number_input("Valor V do Quadro 14 (R$/m²)", min_value=0.0, value=0.0, step=100.0, key=f"apv_v_{chave}",
                              help="Procure pelo SQ e pelo código do logradouro. Use o valor atualizado por decreto.")
    fs_nome = c2.selectbox("Fator social (Quadro 5)", list(FATORES_FS),
                           index=list(FATORES_FS).index("Habitação de 30 a 70 m²"), key=f"apv_fs_{chave}")
    macro_nome = c3.selectbox("Macroárea (Quadro 6)", opcoes_macro,
                              index=opcoes_macro.index(macro) if macro else 0, key=f"apv_macro_{chave}")
    uso = c4.radio("Uso", ["Residencial", "Não residencial"], horizontal=True, key=f"apv_uso_{chave}")
    st.caption(f"Valor V: [Quadro 14 do PDE (versão original de 2014)]({LINK_QUADRO_14}), atualizado depois por decretos.")

    return EntradaAproveitamento(
        area_terreno_m2=area,
        zona=zona,
        pa=None if pa == OPCOES_PA[0] else pa,
        area_doacao_m2=doacao,
        faixa_reservada_nao_edificavel=reservada,
        testada_m=testada,
        profundidade_m=profundidade,
        modalidade=modalidade,
        eixo_ativado=eixo_ativado,
        ca_utilizado=ca_usado or None,
        cota_solidariedade=solidariedade,
        valor_m2_quadro14=valor_v or None,
        fs=FATORES_FS[fs_nome],
        linha_quadro_6=None if macro_nome == SEM_MACROAREA else macro_nome,
        uso_residencial=uso == "Residencial",
        area_media_unidade_m2=area_media,
        pe_direito_m=pe_direito,
    )


def _renderizar_resultado(r: ResultadoAproveitamento) -> None:
    titulo_secao("Resultado do aproveitamento")
    pavimentos = f"{r.pavimentos_necessarios} pavimentos" if r.pavimentos_necessarios else "—"
    limite = f"Gabarito: {r.pavimentos_max_gabarito} pav." if r.pavimentos_max_gabarito else "Sem limite de gabarito"
    grade_cards(
        [
            (f"Computável sem outorga (C.A. {_num(r.ca_basico)})", _m2(r.computavel_basica_m2), None),
            (f"Computável máxima (C.A. {_num(r.ca_final)})", _m2(r.computavel_maxima_m2), f"C.A. ordinário: {_num(r.ca_maximo)}"),
            ("Adicional a pagar", _m2(r.adicional_a_pagar_m2), f"C.A. usado: {_num(r.ca_usado)}"),
            ("Outorga estimada", f"R$ {_num(r.outorga_total)}" if r.outorga_total is not None else "Faltam dados",
             f"R$ {_num(r.contrapartida_m2)}/m² · Fp {_num(r.fp, 1)}" if r.contrapartida_m2 is not None else "Informe V e a macroárea"),
            (f"Projeção máxima (T.O. {_pct(r.to_aplicada)})", _m2(r.projecao_max_m2), None),
            (f"Área permeável mínima ({_pct(r.tp_aplicada)})", _m2(r.area_permeavel_min_m2),
             f"Quota Ambiental mínima: {_num(r.qa_minima)}" if r.qa_minima else "Sem pontuação de QA"),
            ("Área construída total máxima", _m2(r.area_total_max_m2), f"Não computável até {_m2(r.nao_computavel_max_m2)}"),
            ("Pavimentos estimados", pavimentos, limite),
            ("Unidades", f"{r.unidades_estimadas} estimadas",
             f"Mínimo pela cota-parte: {r.unidades_minimas}" if r.unidades_minimas else "Sem cota-parte nesta zona"),
        ]
    )

    if r.alertas:
        titulo_secao("Pontos de atenção")
        for alerta in r.alertas:
            nota(alerta, "warn")

    titulo_secao("Memória de cálculo", "Cada resultado com a fórmula e a base legal.")
    tabela(
        ["Grupo", "Item", "Valor", "Fórmula", "Base legal"],
        [[l.grupo, l.item, f"{_num(l.valor)} {l.unidade}".strip() if l.valor is not None else "Não se aplica", l.formula, l.base_legal]
         for l in r.memoria],
    )

    csv = pd.DataFrame(
        [{"Grupo": l.grupo, "Item": l.item, "Valor": l.valor, "Unidade": l.unidade, "Fórmula": l.formula, "Base legal": l.base_legal}
         for l in r.memoria]
    ).to_csv(index=False, sep=";", decimal=",").encode("utf-8-sig")
    st.download_button("Baixar memória de cálculo (CSV)", csv, file_name=f"aproveitamento_{r.zona}.csv", mime="text/csv")


def renderizar_aproveitamento(resultado: ResultadoTerreno, zona: str) -> None:
    """Formulário e resultado das contas, com os campos já preenchidos pelo terreno consultado."""
    if len(set(resultado.zonas_detectadas)) > 1:
        nota(
            f"O terreno toca mais de uma zona ({', '.join(resultado.zonas_detectadas)}). As contas usam só a zona selecionada: "
            "confira a regra de lote em mais de uma zona.",
            "alert",
        )
    nota(
        "A zona vem da camada de 2016 do GeoSampa. O Mapa 1 foi alterado pelas Leis 18.081 e 18.177/2024 e é objeto de ADIN: "
        "confirme a zona vigente. Operações Urbanas, mananciais e tombamento podem ter índices próprios.",
        "warn",
    )
    preservar_campos("pb_")  # mantém as premissas da página de payback ao trocar de página
    entrada = _coletar_entrada(resultado, zona)
    try:
        calculo = calcular_aproveitamento(entrada)
    except ValueError as erro:
        st.session_state.pop("aproveitamento_atual", None)
        nota(str(erro), "alert")
        return
    st.session_state["aproveitamento_atual"] = calculo  # usado pela página de payback
    _renderizar_resultado(calculo)
