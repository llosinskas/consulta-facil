"""
Interface Completa das Etapas 2 a 12 da Planilha de Estudo de Viabilidade (`QUADRO_DE_ÁREAS-R01.xlsx`),
conectada automaticamente aos dados espaciais extraídos do GeoSampa (`ResultadoTerreno`).
"""

from typing import Any, Dict, List, Sequence, Tuple

import pandas as pd
import streamlit as st

from domain.models import ResultadoTerreno
from domain.tabelas_dados import (
    QUADRO_2_RAW,
    QUADRO_3_RAW,
    QUADRO_4_RAW,
    SISTEMAS_CONSTRUTIVOS,
    TIPOS_ESCADA,
)
from domain.viabilidade_models import (
    COLUNAS_COMPUTAVEIS,
    COLUNAS_NAO_COMPUTAVEIS,
    COLUNAS_UNIDADES,
    MODALIDADES,
    TODAS_COLUNAS_AREA,
    TODAS_COLUNAS_UNIDADE,
    EntradaGeo,
    IndicesLegais,
    Pavimento,
    PavimentoPopulacao,
    QuadroAreas,
)
from services.agua_elevador_engine import (
    DESTINACOES_PREDIO,
    calcular_agua_e_populacao,
    calcular_trafego_elevadores,
)
from services.desnivel_engine import calcular_desnivel_reservatorios
from services.excel_exporter import gerar_xlsx_bytes
from services.financeiro_cronograma_engine import (
    calcular_retorno_financeiro_e_cronograma,
    estimar_prazo_obra_meses,
)
from services.quadro_areas_engine import (
    calcular_anexos,
    calcular_quadro_areas,
    calcular_quadro_luops,
    distribuir_areas_automaticas_por_terreno,
    gerar_pavimentos_padrao,
)
from services.viabilidade_bridge import (
    calcular_indices_legais,
    extrair_entrada_geo,
    listar_pas_disponiveis,
    listar_zonas_disponiveis,
)
from ui.styles import grade_cards, nota, tabela, titulo_secao

ITENS_CHECKLIST_PADRAO: List[str] = [
    "PLANIALTIMÉTRICO",
    "SONDAGEM",
    "COMAR",
    "COTA HIDROLÓGICO",
    "LAUDO HIDROLÓGICO",
    "ARVORE NO LOTE",
    "ARVORE NA CALÇADA",
    "POSTE NA FRENTE",
    "BUEIRO NA FRENTE",
    "CONTAMINAÇÃO",
    "MELHORAMENTO",
    "DIRETRIZ HIDRÁULICA",
    "DIS/DUP",
    "APP",
]


def _fmt_num(val: Any, sufixo: str = "", casas: int = 2) -> str:
    if val is None or val == "":
        return "NA"
    try:
        v = float(val)
    except (ValueError, TypeError):
        return str(val)
    fmt = f"{v:,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{fmt} {sufixo}".strip()


def _df_pavimentos_para_edicao(pavimentos: List[Pavimento]) -> pd.DataFrame:
    """Converte a lista de `Pavimento` em um DataFrame editável para o `st.data_editor`."""
    linhas = []
    for p in pavimentos:
        row: Dict[str, Any] = {
            "Nível (m)": round(p.cota_m, 2),
            "Pavimento": p.nome,
            "Pé-direito (m)": round(p.pe_direito_m, 2),
        }
        for chave_u, rotulo_u in COLUNAS_UNIDADES:
            row[f"UH {rotulo_u}"] = float(p.unidades.get(chave_u, 0.0))
        for chave_c, rotulo_c in COLUNAS_COMPUTAVEIS:
            row[f"[Comp] {rotulo_c}"] = float(p.areas.get(chave_c, 0.0))
        for chave_nc, rotulo_nc in COLUNAS_NAO_COMPUTAVEIS:
            row[f"[N.Comp] {rotulo_nc}"] = float(p.areas.get(chave_nc, 0.0))
        linhas.append(row)
    return pd.DataFrame(linhas)


def _df_editado_para_pavimentos(df: pd.DataFrame, pavs_originais: List[Pavimento]) -> List[Pavimento]:
    """Reconstrói a lista de `Pavimento` a partir do DataFrame editado pelo usuário."""
    novos: List[Pavimento] = []
    for idx, (_, row) in enumerate(df.iterrows()):
        tipo_orig = pavs_originais[idx].tipo if idx < len(pavs_originais) else "tipo"
        nome_pav = str(row.get("Pavimento", f"Pavimento {idx}"))
        pd_m = float(row.get("Pé-direito (m)", 2.72) or 2.72)

        unidades: Dict[str, float] = {}
        for chave_u, rotulo_u in COLUNAS_UNIDADES:
            unidades[chave_u] = float(row.get(f"UH {rotulo_u}", 0.0) or 0.0)

        areas: Dict[str, float] = {}
        for chave_c, rotulo_c in COLUNAS_COMPUTAVEIS:
            areas[chave_c] = float(row.get(f"[Comp] {rotulo_c}", 0.0) or 0.0)
        for chave_nc, rotulo_nc in COLUNAS_NAO_COMPUTAVEIS:
            areas[chave_nc] = float(row.get(f"[N.Comp] {rotulo_nc}", 0.0) or 0.0)

        novos.append(
            Pavimento(
                nome=nome_pav,
                pe_direito_m=pd_m,
                tipo=tipo_orig,
                unidades=unidades,
                areas=areas,
                cota_m=float(row.get("Nível (m)", 0.0) or 0.0),
            )
        )
    return novos


def _montar_abas_xlsx(
    entrada: EntradaGeo,
    indices: IndicesLegais,
    quadro: QuadroAreas,
    luops: List[Any],
    anexos: Any,
    agua: Any,
    elevador: Any,
    desnivel: Any,
    fin_cron: Any,
    nome_empreendimento: str,
    df_checklist: pd.DataFrame,
    df_mix: pd.DataFrame,
) -> List[Tuple[str, Sequence[Sequence[Any]]]]:
    """Prepara as 9 abas da planilha para exportação em `.xlsx` (7 abas originais + FINANCEIRO + CRONOGRAMA)."""
    # Aba 1: Q. ÁREAS
    cabecalho_qa = (
        ["NÍVEL", "PAVIMENTO", "UNIDADES TOTAL"]
        + [r for _, r in COLUNAS_UNIDADES]
        + [f"COMP. {r}" for _, r in COLUNAS_COMPUTAVEIS]
        + [f"N.COMP. {r}" for _, r in COLUNAS_NAO_COMPUTAVEIS]
        + ["TOTAL PAV. (m²)", "% CIRC./PAV."]
    )
    linhas_qa: List[List[Any]] = [
        ["QUADRO DE ÁREAS — " + nome_empreendimento],
        cabecalho_qa,
    ]
    for idx, p in enumerate(quadro.pavimentos):
        tot_u_pav = sum(p.unidades.values())
        tot_a_pav = quadro.total_por_pavimento[idx]
        pct_c = quadro.pct_circ_por_pavimento[idx]
        linhas_qa.append(
            [p.cota_m, p.nome, tot_u_pav]
            + [p.unidades[c] for c in TODAS_COLUNAS_UNIDADE]
            + [p.areas[c] for c in TODAS_COLUNAS_AREA]
            + [tot_a_pav, f"{pct_c:.2f}%" if pct_c is not None else "0,00%"]
        )
    linhas_qa.append(
        ["", "SUBTOTAL", quadro.total_unidades]
        + [quadro.subtotal_unidades[c] for c in TODAS_COLUNAS_UNIDADE]
        + [quadro.subtotal_areas[c] for c in TODAS_COLUNAS_AREA]
        + [quadro.area_construida_m2, ""]
    )
    linhas_qa.append([])
    linhas_qa.append(["FICHA DO TERRENO E QUADRO PROJETO"])
    linhas_qa.append(["Empreendimento", nome_empreendimento, "", "Área Terreno (m²)", entrada.area_terreno_m2])
    linhas_qa.append(["Endereço", entrada.endereco, "", "Zona", indices.zona])
    linhas_qa.append(["SQL(s)", " + ".join(entrada.sqls), "", "Qualificação Ambiental", indices.pa])
    linhas_qa.append(["T.O. Máxima", indices.to_max, "", "C.A. Básico / Máx / HIS / +20%", f"{indices.ca_basico} / {indices.ca_maximo_lpuos} / {indices.ca_max_ehis} / {indices.ca_majorado}"])
    linhas_qa.append(["Área Computável Total (m²)", quadro.area_computavel_m2, "", "Área Não Computável Total (m²)", quadro.area_nao_computavel_m2])
    linhas_qa.append(["Área Construída Total (m²)", quadro.area_construida_m2, "", "Área Privativa Total (m²)", quadro.area_privativa_m2])
    linhas_qa.append([])
    linhas_qa.append(["BALANÇO DE ÁREAS (ÁREA MÁX. × PROJETO × SOBRA)"])
    linhas_qa.append(["Item", "Limite Legal (m²)", "Projetado (m²)", "Sobra / Folga (m²)", "Status", "Referência"])
    for lim in quadro.limites:
        linhas_qa.append([lim.item, lim.maximo, lim.projeto, lim.sobra, "ATENDE" if lim.atende else "REVISAR", lim.referencia])

    # Aba 2: Q. LUOPS
    linhas_luops: List[List[Any]] = [
        ["QUADRO DE USO E OCUPAÇÃO DO SOLO"],
        ["Bloco", "Parâmetro", "Valor", "Unidade", "Observação"],
    ]
    for item in luops:
        linhas_luops.append([item.bloco, item.item, item.valor, item.unidade, item.observacao])

    # Aba 3: Q. ANEXOS
    linhas_anexos: List[List[Any]] = [
        ["VOLUMES DE RESERVATÓRIOS (REÚSO E RETARDO)"],
        ["Reservatório de Reúso — Vri (Impermeáveis)", anexos.reuso_vri_l, "L"],
        ["Reservatório de Reúso — Vrv (Verdes)", anexos.reuso_vrv_l, "L"],
        ["Reservatório de Reúso — Exigido (Vrm)", anexos.reuso_exigido_l, "L"],
        ["Reservatório de Reúso — Projetado", anexos.reuso_projetado_l, "L"],
        ["Reservatório de Retardo — Exigido (Área × 6,3)", anexos.retardo_exigido_l, "L"],
        ["Reservatório de Retardo — Projetado", anexos.retardo_projetado_l, "L"],
        [],
        ["QUADRO DEMONSTRATIVO DE ACESSIBILIDADE (Art. 14 Decreto 63.728/24)"],
        ["Categoria", "Item", "Valor", "Unidade", "Observação"],
    ]
    for ac in anexos.acessibilidade:
        linhas_anexos.append([ac.bloco, ac.item, ac.valor, ac.unidade, ac.observacao])
    linhas_anexos.append([])
    linhas_anexos.append(["QUADRO DE VAGAS DE ESTACIONAMENTO"])
    for vg in anexos.vagas:
        linhas_anexos.append([vg.bloco, vg.item, vg.valor, vg.unidade, vg.observacao])
    linhas_anexos.append([])
    linhas_anexos.append(["CÁLCULO DE USO INCENTIVADO (Decreto 63.728/24)"])
    for ui in anexos.uso_incentivado:
        linhas_anexos.append([ui.bloco, ui.item, ui.valor, ui.unidade, ui.observacao])

    # Aba 4: CALC. ÁGUA
    linhas_agua: List[List[Any]] = [
        ["CÁLCULO DE POPULAÇÃO E RESERVATÓRIO DE ÁGUA POTÁVEL"],
        ["Pavimento", "1 Dorm", "2 Dorm", "3 Dorm", "Pop. Elevador", "Pop. Água", "Pop. Bombeiros"],
    ]
    for r_ag in agua.linhas:
        linhas_agua.append(
            [r_ag["pavimento"], r_ag["dorm1"], r_ag["dorm2"], r_ag["dorm3"], r_ag["pop_elevador"], r_ag["pop_agua"], r_ag["pop_bombeiros"]]
        )
    linhas_agua.append(["TOTAL", "", "", "", agua.pop_elevador, agua.pop_agua, agua.pop_bombeiros])
    linhas_agua.append([])
    linhas_agua.append(["Consumo diário estimado (L)", agua.consumo_diario_l])
    linhas_agua.append(["Reservatório Superior Recomendado (L)", agua.superior_recomendado_l])
    linhas_agua.append(["Reservatório Inferior Recomendado (L)", agua.inferior_recomendado_l])
    linhas_agua.append(["Volume Total Recomendado (L)", agua.total_recomendado_l])

    # Aba 5: ELEVADOR
    linhas_elev: List[List[Any]] = [
        ["CÁLCULO DE TRÁFEGO DE ELEVADORES — NBR 5665"],
        ["Destinação de Uso", elevador.destinacao],
        ["População Total do Prédio", elevador.populacao],
        ["População a transportar em 5 min (passageiros)", elevador.populacao_5min],
        ["Número de Paradas Prováveis (Np)", elevador.paradas_provaveis],
        ["T1 — Percurso Total (s)", elevador.t1],
        ["T2 — Aceleração e Retardamento (s)", elevador.t2],
        ["T3 — Abertura e Fechamento (s)", elevador.t3],
        ["T4 — Entrada e Saída de Passageiros (s)", elevador.t4],
        ["Soma Parcial (T1+T2+T3+T4) (s)", elevador.soma_parcial],
        ["Adicional 10% (T3+T4) (s)", elevador.adicional_10],
        ["Tempo Total de Viagem — TTV (s)", elevador.ttv],
        ["Intervalo de Tráfego (s)", elevador.intervalo_s],
        ["Capacidade de Transporte por Elevador (pass./5 min)", elevador.capac_transporte],
        ["Capacidade de Tráfego Total (pass./5 min)", elevador.capac_trafego],
        ["Grau de Serviço", elevador.grau_servico],
        ["Distância mínima p/ atingir velocidade nominal (m)", elevador.distancia_min_m],
        ["Atende Capacidade Mínima?", "SIM" if elevador.atende_capacidade else "NÃO"],
    ]

    # Aba 6: DADOS
    linhas_dados: List[List[Any]] = [
        ["QUADRO 2 — PARÂMETROS DE OCUPAÇÃO POR ZONA DE USO (DECRETO HIS)"],
        ["Zona", "CA Mínimo", "CA Básico", "CA Máx EHIS", "CA Máx EHMP", "TO ≤ 500m²", "TO > 500m²", "Gabarito (m)", "Recuo Frente", "Recuo ≤10m", "Recuo >10m", "Cota-Parte"],
    ]
    for z_k, z_v in QUADRO_2_RAW.items():
        linhas_dados.append(
            [
                z_k, z_v["ca_minimo"], z_v["ca_basico"], z_v["ca_max_ehis"], z_v["ca_max_ehmp"],
                z_v["to_ate_500"], z_v["to_acima_500"], z_v["gabarito_m"], z_v["recuo_frente"],
                z_v["recuo_ate_10m"], z_v["recuo_acima_10m"], z_v["cota_parte"],
            ]
        )
    linhas_dados.append([])
    linhas_dados.append(["QUADRO 4 — TAXA DE PERMEABILIDADE MÍNIMA POR PA"])
    linhas_dados.append(["Perímetro (PA)", "Lote ≤ 500 m²", "Lote > 500 m²"])
    for pa_k, pa_v in QUADRO_4_RAW.items():
        linhas_dados.append([pa_k, pa_v["ate_500"], pa_v["acima_500"]])

    # Aba 7: DESNÍVEL
    linhas_desn: List[List[Any]] = [
        ["CÁLCULO PARA COTA DE DESNÍVEL DOS RESERVATÓRIOS (TRECHOS A, B E C)"],
        ["Trecho / Bloco", "Parâmetro", "Valor", "Unidade", "Observação"],
    ]
    for item_d in desnivel.linhas_a + desnivel.linhas_b + desnivel.linhas_c:
        linhas_desn.append([item_d.bloco, item_d.item, item_d.valor, item_d.unidade, item_d.observacao])

    # Aba 8: FINANCEIRO
    linhas_fin: List[List[Any]] = [
        ["ESTUDO DE RETORNO FINANCEIRO PREVISTO — " + nome_empreendimento],
        ["RESUMO EXECUTIVO"],
        ["VGV Bruto Previsto (R$)", fin_cron.vgv_bruto_rs],
        ["Custo Total do Empreendimento (R$)", fin_cron.custo_total_empreendimento_rs],
        ["Lucro Líquido Previsto (R$)", fin_cron.lucro_liquido_rs],
        ["Margem Líquida sobre VGV (%)", fin_cron.margem_liquida_vgv_pct],
        ["ROI sobre Custo Total (%)", fin_cron.roi_sobre_custo_pct],
        ["Exposição Máxima de Caixa (R$)", fin_cron.exposicao_maxima_caixa_rs, f"Pico no Mês {fin_cron.mes_pico_exposicao}"],
        ["Payback Estimado (Mês)", fin_cron.payback_mes or "No encerramento"],
        ["VPL à TMA (R$)", fin_cron.vpl_rs],
        ["TIR Mensal / Anual (%)", f"{fin_cron.tir_mensal_pct:.2f}% a.m. / {fin_cron.tir_anual_pct:.2f}% a.a."],
        [],
        ["COMPOSIÇÃO DO VGV POR CATEGORIA"],
        ["Categoria", "Unidades", "Área Privativa (m²)", "Preço/m² (R$)", "VGV (R$)", "Ticket Médio (R$)", "% VGV"],
    ]
    for iv in fin_cron.itens_vgv:
        linhas_fin.append([iv.categoria, iv.unidades, iv.area_privativa_m2, iv.preco_m2_rs, iv.vgv_rs, iv.ticket_medio_rs, iv.participacao_pct])
    linhas_fin.append([])
    linhas_fin.append(["COMPOSIÇÃO DOS CUSTOS DO EMPREENDIMENTO"])
    linhas_fin.append(["Grupo", "Descrição", "Valor (R$)", "% Custo Total", "% VGV", "Memória / Critério"])
    for ic in fin_cron.itens_custo:
        linhas_fin.append([ic.grupo, ic.descricao, ic.valor_rs, ic.pct_custo_total, ic.pct_vgv, ic.criterio])

    # Aba 9: CRONOGRAMA (Com grade mensal M01..MN de desembolso e Curva S)
    meses_cols = [f"M{m:02d}" for m in range(1, fin_cron.prazo_total_meses + 1)]
    linhas_cron: List[List[Any]] = [
        ["CRONOGRAMA FÍSICO-FINANCEIRO APROXIMADO DE OBRA — " + nome_empreendimento],
        [
            "Sistema Construtivo",
            fin_cron.sistema_construtivo,
            "Prazo Pré-Obra (meses)",
            fin_cron.prazo_pre_obra_meses,
            "Prazo Execução Obra (meses)",
            fin_cron.prazo_obra_meses,
            "Prazo Total (meses)",
            fin_cron.prazo_total_meses,
        ],
        [],
        ["CRONOGRAMA GANTT MENSAL POR MACROETAPA (DESEMBOLSO MENSAL EM R$)"],
        ["Ordem", "Fase", "Etapa", "Mês Início", "Mês Fim", "Duração (m)", "Peso Obra (%)", "Custo Estimado (R$)"] + meses_cols,
    ]
    soma_mensal_obra = [0.0] * fin_cron.prazo_total_meses
    for et in fin_cron.etapas_cronograma:
        custo_mes = round(et.custo_estimado_rs / max(1, et.duracao_meses), 2)
        valores_meses = []
        for m in range(1, fin_cron.prazo_total_meses + 1):
            if et.mes_inicio <= m <= et.mes_fim:
                valores_meses.append(custo_mes)
                if et.peso_obra_pct > 0:
                    soma_mensal_obra[m - 1] = round(soma_mensal_obra[m - 1] + custo_mes, 2)
            else:
                valores_meses.append(0.0)
        linhas_cron.append(
            [et.ordem, et.fase, et.etapa, et.mes_inicio, et.mes_fim, et.duracao_meses, et.peso_obra_pct, et.custo_estimado_rs]
            + valores_meses
        )

    avanco_mensal_pct = [
        round((v / fin_cron.custo_obra_direto_rs) * 100.0, 2) if fin_cron.custo_obra_direto_rs > 0 else 0.0
        for v in soma_mensal_obra
    ]
    avanco_acum_mensal = []
    acum_m = 0.0
    for p_m in avanco_mensal_pct:
        acum_m = round(min(100.0, acum_m + p_m), 2)
        avanco_acum_mensal.append(acum_m)

    linhas_cron.append(["", "", "DESEMBOLSO MENSAL DE OBRA DIRETA (R$)", "", "", "", 100.0, fin_cron.custo_obra_direto_rs] + soma_mensal_obra)
    linhas_cron.append(["", "", "AVANÇO FÍSICO MENSAL (%)", "", "", "", "", ""] + avanco_mensal_pct)
    linhas_cron.append(["", "", "CURVA S — AVANÇO FÍSICO ACUMULADO (%)", "", "", "", "", ""] + avanco_acum_mensal)
    linhas_cron.append([])
    linhas_cron.append(["CURVA S E FLUXO DE CAIXA TRIMESTRAL"])
    linhas_cron.append(["Período", "Avanço Físico (%)", "Avanço Acumulado (%)", "Desembolso Total (R$)", "Receita Estimada (R$)", "Saldo Período (R$)", "Saldo Acumulado (R$)"])
    for ft in fin_cron.fluxo_trimestral:
        linhas_cron.append([ft.periodo, ft.avanco_fisico_pct, ft.avanco_acumulado_pct, ft.desembolso_total_rs, ft.receita_liquida_rs, ft.saldo_periodo_rs, ft.saldo_acumulado_rs])

    return [
        ("Q. ÁREAS", linhas_qa),
        ("Q. LUOPS", linhas_luops),
        ("Q. ANEXOS", linhas_anexos),
        ("CALC. ÁGUA", linhas_agua),
        ("ELEVADOR", linhas_elev),
        ("DADOS", linhas_dados),
        ("DESNÍVEL", linhas_desn),
        ("FINANCEIRO", linhas_fin),
        ("CRONOGRAMA", linhas_cron),
    ]


_CORES_FASE_GANTT: Dict[str, Tuple[str, str, str]] = {
    "Pré-Obra": ("#4f46e5", "#eef2ff", "#3730a3"),
    "Obra — Início": ("#d97706", "#fffbeb", "#92400e"),
    "Obra — Infra": ("#ea580c", "#fff7ed", "#9a3412"),
    "Obra — Estrutura": ("#2563eb", "#eff6ff", "#1e40af"),
    "Obra — Vedação": ("#0284c7", "#f0f9ff", "#075985"),
    "Obra — Sistemas": ("#7c3aed", "#f5f3ff", "#5b21b6"),
    "Obra — Estanqueidade": ("#0d9488", "#f0fdfa", "#115e59"),
    "Obra — Acabamentos": ("#059669", "#ecfdf5", "#065f46"),
    "Obra — Equipamentos": ("#16a34a", "#f0fdf4", "#166534"),
    "Pós-Obra / Entrega": ("#15803d", "#dcfce7", "#14532d"),
}


def _renderizar_gantt_visual(fin_cron: Any) -> None:
    """
    Renderiza um Gráfico de Gantt profissional e interativo em HTML/CSS com:
    - Faixa superior de Marcos do Empreendimento (Milestones)
    - Grade mensal (M01..MN) com separação visual entre Pré-Obra e Execução de Obra
    - Barras horizontais contínuas coloridas por fase, com rótulo de duração/peso e tooltip rico
    - Rodapé integrado com Intensidade de Desembolso Mensal e Curva S Acumulada (0% -> 100%)
    """
    n_meses = max(1, int(fin_cron.prazo_total_meses))
    m_pre = int(fin_cron.prazo_pre_obra_meses)
    m_pico = int(fin_cron.mes_pico_exposicao)
    m_payback = fin_cron.payback_mes

    # Calcula avanço físico mensal e acumulado para o rodapé do Gantt
    custo_obra_mes = [0.0] * n_meses
    for et in fin_cron.etapas_cronograma:
        if et.peso_obra_pct > 0:
            v_m = et.custo_estimado_rs / max(1, et.duracao_meses)
            for m in range(et.mes_inicio, et.mes_fim + 1):
                if 1 <= m <= n_meses:
                    custo_obra_mes[m - 1] += v_m

    pct_mes = [
        (v / fin_cron.custo_obra_direto_rs * 100.0) if fin_cron.custo_obra_direto_rs > 0 else 0.0
        for v in custo_obra_mes
    ]
    pct_acum: List[float] = []
    ac = 0.0
    for p in pct_mes:
        ac = min(100.0, ac + p)
        pct_acum.append(ac)
    max_pct_mes = max(pct_mes) if pct_mes and max(pct_mes) > 0 else 1.0

    # 1. Faixa de Marcos (Milestones)
    marcos_html = f"""
    <div style="display:flex;flex-wrap:wrap;gap:10px;margin-bottom:14px;">
      <div style="background:#eef2ff;border:1px solid #c7d2fe;border-radius:8px;padding:8px 12px;font-size:12.5px;color:#3730a3;">
        <strong>📐 Mês 1 a Mês {m_pre}:</strong> Pré-Obra, Projetos e Aprovação Legal
      </div>
      <div style="background:#eff6ff;border:1px solid #bfdbfe;border-radius:8px;padding:8px 12px;font-size:12.5px;color:#1e40af;">
        <strong>🚀 Mês {m_pre}:</strong> Registro de Incorporação (RI) &amp; Lançamento Comercial
      </div>
      <div style="background:#fff7ed;border:1px solid #fed7aa;border-radius:8px;padding:8px 12px;font-size:12.5px;color:#9a3412;">
        <strong>🏗️ Mês {m_pre + 1}:</strong> Início das Obras Civis ({fin_cron.sistema_construtivo})
      </div>
      <div style="background:#fef2f2;border:1px solid #fecaca;border-radius:8px;padding:8px 12px;font-size:12.5px;color:#991b1b;">
        <strong>📉 Mês {m_pico}:</strong> Pico de Exposição de Caixa (R$ {_fmt_num(fin_cron.exposicao_maxima_caixa_rs, '', 0)})
      </div>
      <div style="background:#ecfdf5;border:1px solid #a7f3d0;border-radius:8px;padding:8px 12px;font-size:12.5px;color:#065f46;">
        <strong>💰 {'Mês ' + str(m_payback) if m_payback else 'Mês ' + str(n_meses)}:</strong> Payback (Ponto de Equilíbrio do Caixa)
      </div>
      <div style="background:#dcfce7;border:1px solid #86efac;border-radius:8px;padding:8px 12px;font-size:12.5px;color:#14532d;">
        <strong>🔑 Mês {n_meses}:</strong> Habite-se, Vistoria e Entrega das Chaves
      </div>
    </div>
    """

    # 2. Cabeçalho da Tabela Gantt Mês a Mês
    ths_meses = []
    for m in range(1, n_meses + 1):
        bg_th = "#eef2ff" if m <= m_pre else "#f8fafc"
        borda_dir = "border-right:2px solid #6366f1;" if m == m_pre else "border-right:1px solid #e5e7eb;"
        icone_marco = ""
        if m == m_pre:
            icone_marco = "🚀"
        elif m == m_pico:
            icone_marco = "📉"
        elif m_payback and m == m_payback:
            icone_marco = "💰"
        elif m == n_meses:
            icone_marco = "🔑"
        ths_meses.append(
            f'<th style="text-align:center;padding:6px 2px;font-size:11px;min-width:34px;background:{bg_th};{borda_dir}">'
            f'<div>M{m:02d}</div><div style="font-size:10px;line-height:1;">{icone_marco}</div></th>'
        )

    # 3. Linhas de cada Macroetapa com barra Gantt contínua (colspan sobre os meses ativos)
    linhas_html = []
    for et in fin_cron.etapas_cronograma:
        cor_barra, cor_bg_badge, cor_txt_badge = _CORES_FASE_GANTT.get(
            et.fase, ("#2563eb", "#eff6ff", "#1e40af")
        )
        peso_str = f"{_fmt_num(et.peso_obra_pct, '%', 1)}" if et.peso_obra_pct > 0 else "Pré-Obra"
        custo_mensal_et = et.custo_estimado_rs / max(1, et.duracao_meses)
        tooltip = (
            f"{et.ordem}. {et.etapa} ({et.fase}) | "
            f"Mês {et.mes_inicio} ao Mês {et.mes_fim} ({et.duracao_meses} meses) | "
            f"Total: R$ {_fmt_num(et.custo_estimado_rs)} (R$ {_fmt_num(custo_mensal_et)}/mês)"
        )

        # Células antes do início da etapa
        tds_cron: List[str] = []
        for m in range(1, et.mes_inicio):
            bg_cel = "#f8faff" if m <= m_pre else "#ffffff"
            borda_dir = "border-right:2px dashed #818cf8;" if m == m_pre else "border-right:1px solid #f1f5f9;"
            tds_cron.append(f'<td style="padding:4px 0;background:{bg_cel};{borda_dir}"></td>')

        # Célula mesclada (colspan) para a barra ativa da etapa
        colspan = max(1, et.mes_fim - et.mes_inicio + 1)
        rotulo_barra = f"M{et.mes_inicio:02d}→M{et.mes_fim:02d} ({et.duracao_meses}m · {peso_str})"
        tds_cron.append(
            f'<td colspan="{colspan}" title="{tooltip}" style="padding:5px 3px;vertical-align:middle;background:#f8fafc;border-right:1px solid #f1f5f9;">'
            f'<div style="background:linear-gradient(90deg, {cor_barra} 0%, {cor_barra}dd 100%);'
            f'color:#ffffff;font-weight:600;font-size:11px;line-height:1.2;padding:5px 8px;'
            f'border-radius:6px;box-shadow:0 1px 2px rgba(0,0,0,0.12);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;text-align:center;">'
            f'{rotulo_barra}'
            f'</div></td>'
        )

        # Células após o fim da etapa
        for m in range(et.mes_fim + 1, n_meses + 1):
            bg_cel = "#f8faff" if m <= m_pre else "#ffffff"
            borda_dir = "border-right:2px dashed #818cf8;" if m == m_pre else "border-right:1px solid #f1f5f9;"
            tds_cron.append(f'<td style="padding:4px 0;background:{bg_cel};{borda_dir}"></td>')

        linhas_html.append(
            f'<tr style="border-bottom:1px solid #eef2f6;">'
            f'<td style="padding:7px 8px;font-weight:650;color:#475569;text-align:center;">{et.ordem}</td>'
            f'<td style="padding:7px 8px;"><span style="background:{cor_bg_badge};color:{cor_txt_badge};padding:3px 8px;border-radius:999px;font-size:11.5px;font-weight:600;white-space:nowrap;">{et.fase}</span></td>'
            f'<td style="padding:7px 10px;font-weight:500;color:#111827;min-width:230px;">{et.etapa}</td>'
            f'<td style="padding:7px 8px;text-align:center;font-size:12px;color:#334155;white-space:nowrap;">M{et.mes_inicio:02d}–M{et.mes_fim:02d} ({et.duracao_meses}m)</td>'
            f'<td style="padding:7px 8px;text-align:right;font-weight:600;font-size:12px;color:#1e293b;white-space:nowrap;">{peso_str}</td>'
            f'<td style="padding:7px 10px;text-align:right;font-weight:600;font-size:12px;color:#0f172a;white-space:nowrap;">R$ {_fmt_num(et.custo_estimado_rs, "", 0)}</td>'
            + "".join(tds_cron)
            + "</tr>"
        )

    # 4. Linha de Avanço Físico Mensal (%) com mini-barras verticais (Histograma de Obra)
    tds_avanco_mes = []
    for idx_m, p_m in enumerate(pct_mes):
        alt_px = int(round((p_m / max_pct_mes) * 24)) if p_m > 0 else 0
        cor_hist = "#3b82f6" if p_m > 0 else "transparent"
        valor_m_rs = custo_obra_mes[idx_m]
        tds_avanco_mes.append(
            f'<td title="Mês {idx_m + 1}: {p_m:.1f}% da obra (R$ {_fmt_num(valor_m_rs, "", 0)})" '
            f'style="padding:4px 2px;vertical-align:bottom;text-align:center;background:#f8fafc;border-right:1px solid #e5e7eb;">'
            f'<div style="height:26px;display:flex;align-items:flex-end;justify-content:center;">'
            f'<div style="width:18px;height:{alt_px}px;background:{cor_hist};border-radius:3px 3px 0 0;"></div>'
            f'</div>'
            f'<div style="font-size:10px;font-weight:600;color:#1e3a8a;margin-top:2px;">{p_m:.1f}%</div>'
            f'</td>'
        )

    # 5. Linha de Curva S Acumulada (0% -> 100%)
    tds_curva_s = []
    for idx_m, ac_m in enumerate(pct_acum):
        cor_cs = "#059669" if ac_m >= 99.9 else ("#2563eb" if ac_m > 0 else "#94a3b8")
        tds_curva_s.append(
            f'<td title="Acumulado até Mês {idx_m + 1}: {ac_m:.1f}%" '
            f'style="padding:6px 2px;text-align:center;background:#f0fdf4;border-right:1px solid #dcfce7;">'
            f'<div style="font-size:10.5px;font-weight:700;color:{cor_cs};">{ac_m:.0f}%</div>'
            f'<div style="width:100%;height:5px;background:#e2e8f0;border-radius:3px;overflow:hidden;margin-top:2px;">'
            f'<div style="width:{min(100.0, ac_m):.0f}%;height:100%;background:{cor_cs};"></div>'
            f'</div>'
            f'</td>'
        )

    html_completo = (
        marcos_html
        + '<div style="border:1px solid #e2e8f0;border-radius:12px;overflow-x:auto;background:#ffffff;box-shadow:0 1px 3px rgba(0,0,0,0.04);">'
        + '<table style="width:100%;border-collapse:collapse;font-size:12.5px;">'
        + '<thead>'
        + '<tr style="background:#f1f5f9;border-bottom:2px solid #cbd5e1;color:#1e293b;">'
        + '<th style="padding:9px 8px;text-align:center;width:36px;">#</th>'
        + '<th style="padding:9px 8px;text-align:left;">Fase</th>'
        + '<th style="padding:9px 10px;text-align:left;">Macroetapa da Obra</th>'
        + '<th style="padding:9px 8px;text-align:center;">Período</th>'
        + '<th style="padding:9px 8px;text-align:right;">Peso</th>'
        + '<th style="padding:9px 10px;text-align:right;">Custo (R$)</th>'
        + "".join(ths_meses)
        + '</tr>'
        + '</thead>'
        + '<tbody>'
        + "".join(linhas_html)
        + '<tr style="border-top:2px solid #cbd5e1;background:#f8fafc;">'
        + '<td colspan="6" style="padding:6px 10px;font-weight:650;color:#1e3a8a;text-align:right;">📊 Histograma de Avanço Físico Mensal (% da obra/mês):</td>'
        + "".join(tds_avanco_mes)
        + '</tr>'
        + '<tr style="border-top:1px solid #bbf7d0;background:#f0fdf4;">'
        + '<td colspan="6" style="padding:6px 10px;font-weight:700;color:#065f46;text-align:right;">📈 Curva S — Avanço Físico Acumulado (0% → 100%):</td>'
        + "".join(tds_curva_s)
        + '</tr>'
        + '</tbody></table></div>'
    )
    st.markdown(html_completo, unsafe_allow_html=True)


def renderizar_estudo_completo_planilha(resultado: ResultadoTerreno) -> None:
    """
    Renderiza todas as etapas da planilha (`Q. ÁREAS`, `Q. LUOPS`, `Q. ANEXOS`,
    `CALC. ÁGUA`, `ELEVADOR`, `DADOS` e `DESNÍVEL`) conectadas passo a passo
    aos dados extraídos do GeoSampa.
    """
    titulo_secao(
        "Planilha Completa de Viabilidade Conectada ao GeoSampa (Etapas 2 a 12)",
        "Os dados espaciais do terreno (Área, SQL, Zona, PA e Cotas Topográficas) alimentam automaticamente todas as contas abaixo.",
    )

    # -----------------------------------------------------------------------
    # ETAPAS 2, 3 e 4: Normalização, Lookup em DADOS e Ficha do Terreno
    # -----------------------------------------------------------------------
    zonas_opcoes = listar_zonas_disponiveis()
    pas_opcoes = listar_pas_disponiveis()
    entrada_inicial = extrair_entrada_geo(resultado)

    idx_zona_default = zonas_opcoes.index(entrada_inicial.zona) if entrada_inicial.zona in zonas_opcoes else 0
    idx_pa_default = pas_opcoes.index(entrada_inicial.pa) if entrada_inicial.pa in pas_opcoes else 5

    c_f1, c_f2, c_f3, c_f4 = st.columns([1.4, 1.0, 1.0, 1.4])
    with c_f1:
        nome_empreendimento = st.text_input(
            "Nome do Empreendimento (D36)",
            value=f"Estudo {' + '.join(entrada_inicial.sqls[:2])}",
            key="viab_nome_emp",
        )
    with c_f2:
        zona_sel = st.selectbox(
            "Zona de Uso (D39 — Quadros 2 e 3)",
            options=zonas_opcoes,
            index=idx_zona_default,
            key=f"viab_zona_{entrada_inicial.zona}",
        )
    with c_f3:
        pa_sel = st.selectbox(
            "Qualificação Ambiental (D40 — Quadro 4)",
            options=pas_opcoes,
            index=idx_pa_default,
            key=f"viab_pa_{entrada_inicial.pa}",
        )
    with c_f4:
        modalidade_sel = st.selectbox(
            "Modalidade / Enquadramento Legal (W38)",
            options=list(MODALIDADES.keys()),
            format_func=lambda k: MODALIDADES[k],
            index=1,  # EHIS_COTA (+20%)
            key="viab_modalidade",
        )

    c_f5, c_f6, c_f7, c_f8 = st.columns(4)
    with c_f5:
        doacao_m2 = st.number_input(
            "Doação de calçada / melhoramento (m²)",
            min_value=0.0,
            max_value=float(max(0.0, resultado.area_total_m2 - 1.0)),
            value=0.0,
            step=1.0,
            key="viab_doacao_m2",
        )
    with c_f6:
        sistema_construtivo = st.selectbox(
            "Sistema Construtivo (D52)",
            options=list(SISTEMAS_CONSTRUTIVOS.keys()),
            format_func=lambda k: f"{k} ({SISTEMAS_CONSTRUTIVOS[k]})",
            index=1,
            key="viab_sis_const",
        )
    with c_f7:
        tipo_escada = st.selectbox(
            "Tipo de Escada (D56)",
            options=TIPOS_ESCADA,
            index=0,
            key="viab_tipo_escada",
        )
    with c_f8:
        cota_terreo_in = st.number_input(
            "Cota de nível do Térreo (A5 em m)",
            value=float(entrada_inicial.cota_terreno_m or 784.40),
            step=0.10,
            format="%.2f",
            key=f"viab_cota_terreo_{entrada_inicial.cota_terreno_m}",
        )

    # Executa Etapas 2 e 3
    entrada = extrair_entrada_geo(
        resultado,
        area_doacao_m2=doacao_m2,
        zona_override=zona_sel,
        pa_override=pa_sel,
    )
    entrada.cota_terreno_m = cota_terreo_in
    indices = calcular_indices_legais(entrada, modalidade=modalidade_sel)

    for alerta_geo in indices.notas:
        nota(alerta_geo, "info")

    titulo_secao(
        "Etapas 2, 3 e 4 — Ficha do Terreno e Índices Urbanísticos (Quadros 2, 3 e 4)",
        f"Conexão direta: Área GeoSampa = {_fmt_num(entrada.area_escritura_m2, 'm²')} → Área Remanescente (D38) = {_fmt_num(entrada.area_terreno_m2, 'm²')} · Zona {indices.zona} · {indices.pa}",
    )

    grade_cards(
        [
            (
                "Área do Terreno (D38)",
                _fmt_num(indices.area_terreno_m2, "m²"),
                f"Escritura: {_fmt_num(entrada.area_escritura_m2, 'm²')} − Doação: {_fmt_num(entrada.area_doacao_m2, 'm²')}",
            ),
            (
                "Taxa de Ocupação Máx. (C43)",
                _fmt_num((indices.to_max or 0) * 100, "%", 1),
                f"Área máx. (D43): {_fmt_num(indices.area_ocupacao_max_m2, 'm²')} ({'Lote < 500m²' if indices.area_terreno_m2 < 500 else 'Lote ≥ 500m²'})",
            ),
            (
                "Permeabilidade Mín. QA (C47)",
                _fmt_num((indices.tp_min or 0) * 100, "%", 1),
                f"Área mín. (D47): {_fmt_num(indices.area_permeavel_min_m2, 'm²')} ({indices.pa})",
            ),
            (
                "C.A. Básico / Máx. LPUOS (C44/C45)",
                f"{_fmt_num(indices.ca_basico)} / {_fmt_num(indices.ca_maximo_lpuos)}",
                f"Básico: {_fmt_num(indices.area_comp_basica_m2, 'm²')} · LPUOS: {_fmt_num(indices.area_comp_max_lpuos_m2, 'm²')}",
            ),
            (
                "C.A. Decreto HIS / +20% (C46/W40)",
                f"{_fmt_num(indices.ca_max_ehis)} / {_fmt_num(indices.ca_majorado)}",
                f"Potencial Projeto (T46): {_fmt_num(indices.area_comp_projeto_m2, 'm²')}",
            ),
            (
                "Gabarito Máx. (C51) e Recuos",
                _fmt_num(indices.gabarito_m, "m", 0) if indices.gabarito_m else "Sem limite (NA)",
                f"Frente: {indices.recuo_frente} m · Lat./Fundo >10m: {indices.recuo_acima_10m}",
            ),
        ]
    )

    # -----------------------------------------------------------------------
    # ETAPAS 5 e 6: Quadro de Áreas por Pavimento (Matriz Completa)
    # -----------------------------------------------------------------------
    titulo_secao(
        "Etapas 5 e 6 — Quadro de Áreas Pavimento a Pavimento (Aba Q. ÁREAS)",
        "Cota de nível do Térreo ancorada na topografia do GeoSampa. Edite qualquer célula ou use o preenchimento automático pelo potencial do terreno.",
    )

    chave_state_pavs = "viab_df_pavimentos"
    col_b1, col_b2, col_b3, col_b4 = st.columns([1.1, 1.4, 1.2, 1.2], vertical_alignment="bottom")
    with col_b1:
        qtd_pav_tipo = st.number_input(
            "Nº de Pavimentos Tipo",
            min_value=1,
            max_value=45,
            value=9,
            step=1,
            key="viab_qtd_pav_tipo",
        )
    with col_b2:
        if st.button(
            "Preencher automaticamente pelo potencial do terreno",
            type="primary",
            width="stretch",
            key="btn_autopreencher_quadro",
        ):
            pavs_auto = distribuir_areas_automaticas_por_terreno(
                indices=indices,
                cota_terreno_m=cota_terreo_in,
                qtd_pav_tipo=int(qtd_pav_tipo),
            )
            st.session_state[chave_state_pavs] = _df_pavimentos_para_edicao(pavs_auto)
            st.rerun()
    with col_b3:
        if st.button("Zerar matriz de pavimentos (padrão planilha)", width="stretch", key="btn_zerar_quadro"):
            pavs_zero = gerar_pavimentos_padrao(
                cota_terreno_m=cota_terreo_in,
                qtd_pavimentos_tipo=int(qtd_pav_tipo),
                incluir_atico=True,
            )
            st.session_state[chave_state_pavs] = _df_pavimentos_para_edicao(pavs_zero)
            st.rerun()
    with col_b4:
        area_perm_proj_in = st.number_input(
            "Área Permeável Projetada (U52 em m²)",
            min_value=0.0,
            value=float(indices.area_permeavel_min_m2 or 0.0),
            step=1.0,
            key=f"viab_perm_proj_{indices.area_permeavel_min_m2}",
        )

    if chave_state_pavs not in st.session_state:
        pavs_iniciais = distribuir_areas_automaticas_por_terreno(
            indices=indices,
            cota_terreno_m=cota_terreo_in,
            qtd_pav_tipo=int(qtd_pav_tipo),
        )
        st.session_state[chave_state_pavs] = _df_pavimentos_para_edicao(pavs_iniciais)

    df_editado = st.data_editor(
        st.session_state[chave_state_pavs],
        width="stretch",
        num_rows="dynamic",
        key="editor_quadro_areas",
    )

    pavs_atuais = _df_editado_para_pavimentos(
        df_editado,
        gerar_pavimentos_padrao(cota_terreno_m=cota_terreo_in, qtd_pavimentos_tipo=len(df_editado)),
    )
    quadro = calcular_quadro_areas(
        pavimentos=pavs_atuais,
        indices=indices,
        cota_terreno_m=cota_terreo_in,
        area_permeavel_projetada_m2=area_perm_proj_in,
    )

    for alerta_qa in quadro.alertas:
        nota(alerta_qa, "warn")

    grade_cards(
        [
            (
                "Área Computável Total (L26)",
                _fmt_num(quadro.area_computavel_m2, "m²"),
                f"Limite (T46): {_fmt_num(indices.area_comp_projeto_m2, 'm²')}",
            ),
            (
                "Área Não Computável Total (R26)",
                _fmt_num(quadro.area_nao_computavel_m2, "m²"),
                f"Verificação soma linhas×colunas: {quadro.verificacao_soma:.2f}",
            ),
            (
                "Área Construída Total (C27 / E62)",
                _fmt_num(quadro.area_construida_m2, "m²"),
                f"Altura edificação (E51): {_fmt_num(quadro.altura_edificacao_m, 'm')}",
            ),
            (
                "Área Privativa Total (E63)",
                _fmt_num(quadro.area_privativa_m2, "m²"),
                f"Lojas (E64): {_fmt_num(quadro.area_loja_m2, 'm²')}",
            ),
            (
                "Eficiência (E66 = Privativa / Construída)",
                _fmt_num(quadro.eficiencia, "%", 1) if quadro.eficiencia is not None else "—",
                f"Total de unidades: {int(quadro.total_unidades)} UH",
            ),
            (
                "Proporção Usos Computáveis EHIS (L28/O28)",
                (
                    f"{quadro.pct_his:.1f}% HIS / {quadro.pct_r2v:.1f}% R2V"
                    if quadro.pct_his is not None
                    else "—"
                ),
                f"Exigido Dec. 63.728/24: mín. {indices.proporcao_his * 100:.0f}% HIS",
            ),
        ]
    )

    titulo_secao(
        "Quadro Projeto — Balanço Área Máxima × Projeto × Sobra (Q. ÁREAS!S44:W54)",
        "Controle automático de cada limite legal conforme LPUOS, PDE e Decreto HIS nº 63.728/2024.",
    )
    tabela(
        ["Item", "Sentido", "Limite / Exigido (m²)", "Projetado (m²)", "Sobra / Folga (m²)", "Status", "Base Legal"],
        [
            [
                lim.item,
                "Máximo ≤" if lim.sentido == "max" else "Mínimo ≥",
                _fmt_num(lim.maximo, "m²"),
                _fmt_num(lim.projeto, "m²"),
                _fmt_num(lim.sobra, "m²"),
                "✅ Atende" if lim.atende else "⚠️ Revisar",
                lim.referencia,
            ]
            for lim in quadro.limites
        ],
    )

    # -----------------------------------------------------------------------
    # Mix de Unidades / Tipologias e Checklist Técnico (Q. ÁREAS!B57:X82)
    # -----------------------------------------------------------------------
    titulo_secao(
        "Mix de Unidades, VGV Preliminar e Checklist Técnico (Q. ÁREAS!B57:X82)",
        "Quantidades por categoria/tipologia e verificação de interferências físicas e legais do lote.",
    )
    col_mix, col_chk = st.columns([1.3, 1.1], gap="large")
    with col_mix:
        st.markdown("**Mix de Tipologias e Preço/m²**")
        df_mix_padrao = pd.DataFrame(
            [
                {"Categoria": "HIS-1", "Tipologia": "STUDIO", "Área (m²)": 24.57, "Quantidade": 24, "Preço/m² (R$)": 6500.0},
                {"Categoria": "HIS-1", "Tipologia": "1 DORM", "Área (m²)": 24.47, "Quantidade": 22, "Preço/m² (R$)": 6500.0},
                {"Categoria": "HIS-1", "Tipologia": "1 DORM + OFFICE", "Área (m²)": 27.00, "Quantidade": 6, "Preço/m² (R$)": 6500.0},
                {"Categoria": "HIS-2", "Tipologia": "STUDIO", "Área (m²)": 24.57, "Quantidade": 47, "Preço/m² (R$)": 6800.0},
                {"Categoria": "HIS-2", "Tipologia": "1 DORM", "Área (m²)": 24.47, "Quantidade": 49, "Preço/m² (R$)": 6800.0},
                {"Categoria": "HIS-2", "Tipologia": "1 DORM + OFFICE", "Área (m²)": 27.00, "Quantidade": 12, "Preço/m² (R$)": 6800.0},
                {"Categoria": "R2V-1", "Tipologia": "STUDIO", "Área (m²)": 17.78, "Quantidade": 74, "Preço/m² (R$)": 7000.0},
                {"Categoria": "R2V-1", "Tipologia": "STUDIO 24m²", "Área (m²)": 24.57, "Quantidade": 3, "Preço/m² (R$)": 7000.0},
                {"Categoria": "R2V-1", "Tipologia": "1 DORM", "Área (m²)": 24.47, "Quantidade": 3, "Preço/m² (R$)": 7000.0},
                {"Categoria": "R2V-1", "Tipologia": "1 DORM + OFFICE", "Área (m²)": 27.00, "Quantidade": 1, "Preço/m² (R$)": 7000.0},
            ]
        )
        df_mix_edit = st.data_editor(df_mix_padrao, width="stretch", num_rows="dynamic", key="editor_mix_tipologias")
        tot_unid_mix = int(df_mix_edit["Quantidade"].fillna(0).sum())
        area_priv_mix = float((df_mix_edit["Área (m²)"].fillna(0) * df_mix_edit["Quantidade"].fillna(0)).sum())
        vgv_estimado = float(
            (df_mix_edit["Área (m²)"].fillna(0) * df_mix_edit["Quantidade"].fillna(0) * df_mix_edit["Preço/m² (R$)"].fillna(0)).sum()
        )
        st.caption(
            f"**Total no Mix:** {tot_unid_mix} unidades · "
            f"**Área Privativa do Mix:** {_fmt_num(area_priv_mix, 'm²')} · "
            f"**VGV Bruto Estimado:** R$ {_fmt_num(vgv_estimado, '', 2)}"
        )

    with col_chk:
        st.markdown("**Checklist Técnico do Terreno (B68:F82)**")
        desnivel_geo = (resultado.topografia.desnivel_m or 0.0) if resultado.topografia else 0.0
        linhas_chk = []
        for item_c in ITENS_CHECKLIST_PADRAO:
            obs_ini = ""
            status_ini = "N/A"
            if item_c == "PLANIALTIMÉTRICO" and desnivel_geo > 0:
                status_ini = "SIM"
                obs_ini = f"Curvas GeoSampa: desnível {desnivel_geo:.1f} m"
            elif item_c == "DIS/DUP" and resultado.tombamento_detectado:
                status_ini = "SIM"
                obs_ini = "Verificar tombamento detectado no GeoSampa"
            linhas_chk.append({"Item": item_c, "Status": status_ini, "Observação": obs_ini})
        df_chk_edit = st.data_editor(
            pd.DataFrame(linhas_chk),
            width="stretch",
            disabled=["Item"],
            column_config={
                "Status": st.column_config.SelectboxColumn("Status", options=["SIM", "NÃO", "N/A"], required=True),
            },
            key="editor_checklist_terreno",
        )

    # -----------------------------------------------------------------------
    # ETAPA 7: Quadro de Uso e Ocupação do Solo (Q. LUOPS)
    # -----------------------------------------------------------------------
    titulo_secao(
        "Etapa 7 — Quadro de Uso e Ocupação do Solo (Aba Q. LUOPS)",
        "Consolidado automaticamente a partir da Ficha do Terreno e do Quadro de Áreas.",
    )
    linhas_luops = calcular_quadro_luops(
        indices=indices,
        quadro_areas=quadro,
        area_permeavel_utilizada_m2=area_perm_proj_in,
    )
    tabela(
        ["Bloco", "Parâmetro", "Valor", "Unid.", "Observação Legal"],
        [[l.bloco, l.item, _fmt_num(l.valor), l.unidade, l.observacao] for l in linhas_luops],
    )

    # -----------------------------------------------------------------------
    # ETAPA 8: Anexos (Reservatórios de Reúso e Retardo, Acessibilidade, Vagas e Uso Incentivado)
    # -----------------------------------------------------------------------
    titulo_secao(
        "Etapa 8 — Reservatórios Pluviais, Acessibilidade, Vagas e Uso Incentivado (Aba Q. ANEXOS)",
        "Reservatório de Retardo calculado diretamente pela Área do Terreno no GeoSampa (Área × 6,3 L).",
    )
    ca1, ca2, ca3, ca4 = st.columns(4)
    with ca1:
        cob_imp_m2 = st.number_input(
            "Área cobertura impermeável Aci (m²)",
            min_value=0.0,
            value=float(indices.area_ocupacao_max_m2 or 0.0),
            step=5.0,
            key=f"viab_aci_{indices.area_ocupacao_max_m2}",
        )
    with ca2:
        cob_verde_m2 = st.number_input(
            "Área cobertura verde Acv (m²)",
            min_value=0.0,
            value=0.0,
            step=5.0,
            key="viab_acv",
        )
    with ca3:
        fator_vrv = st.selectbox(
            "Fator cobertura verde Vrv (L/m²)",
            options=[6.30, 5.40],
            index=0,
            key="viab_fator_vrv",
        )
    with ca4:
        vagas_livres_in = st.number_input(
            "Vagas de automóveis projetadas (Livres)",
            min_value=0,
            value=max(0, int(quadro.total_unidades // 4)),
            step=1,
            key="viab_vagas_livres",
        )

    anexos = calcular_anexos(
        indices=indices,
        quadro_areas=quadro,
        area_cobertura_impermeavel_m2=cob_imp_m2,
        area_cobertura_verde_m2=cob_verde_m2,
        fator_cobertura_verde=float(fator_vrv),
        vagas_automoveis_livres=int(vagas_livres_in),
    )

    grade_cards(
        [
            (
                "Reservatório de Reúso Exigido (Vrm)",
                _fmt_num(anexos.reuso_exigido_l, "L"),
                f"Vri (16×Aci): {_fmt_num(anexos.reuso_vri_l, 'L')} + Vrv ({fator_vrv}×Acv): {_fmt_num(anexos.reuso_vrv_l, 'L')}",
            ),
            (
                "Reservatório de Reúso Projetado",
                _fmt_num(anexos.reuso_projetado_l, "L", 0),
                "Arredondado comercialmente (múltiplos de 1.000 L)",
            ),
            (
                "Reservatório de Retardo Exigido (Área × 6,3)",
                _fmt_num(anexos.retardo_exigido_l, "L"),
                f"Área GeoSampa: {_fmt_num(indices.area_terreno_m2, 'm²')} × 6,3 L/m²",
            ),
            (
                "Reservatório de Retardo Projetado",
                _fmt_num(anexos.retardo_projetado_l, "L", 0),
                "Arredondado para cima (múltiplos de 5.000 L)",
            ),
        ]
    )

    col_acess, col_vag_inc = st.columns(2, gap="large")
    with col_acess:
        st.markdown("**Quadro Demonstrativo de Acessibilidade (Art. 14 Decreto 63.728/24)**")
        tabela(
            ["Categoria", "Parâmetro", "Valor", "Unid.", "Nota"],
            [[a.bloco, a.item, _fmt_num(a.valor), a.unidade, a.observacao] for a in anexos.acessibilidade],
        )
    with col_vag_inc:
        st.markdown("**Quadro de Vagas de Estacionamento**")
        tabela(
            ["Tipo", "Regra", "Quantidade", "Unid."],
            [[v.bloco, v.item, _fmt_num(v.valor, "", 0), v.unidade] for v in anexos.vagas],
        )
        st.write("")
        st.markdown("**Cálculo de Uso Incentivado (Art. 1º III e Art. 18 IV Dec. 63.728/24)**")
        tabela(
            ["Uso", "Regra", "Permitido (m²)", "Projetado"],
            [[u.bloco, u.item, _fmt_num(u.valor, "m²"), u.observacao] for u in anexos.uso_incentivado],
        )

    # -----------------------------------------------------------------------
    # ETAPA 9: População e Consumo de Água Potável (CALC. ÁGUA)
    # -----------------------------------------------------------------------
    titulo_secao(
        "Etapa 9 — Cálculo de População e Reservatório de Água Potável (Aba CALC. ÁGUA)",
        "Fórmulas de população para Elevador, Água e Bombeiros e dimensionamento dos reservatórios Superior (40% + incêndio) e Inferior (60%).",
    )
    cp1, cp2, cp3, cp4, cp5 = st.columns(5)
    with cp1:
        u_1d_andar = st.number_input("Unid. 1 Dorm / andar", min_value=0, value=3, step=1, key="viab_1d_andar")
    with cp2:
        u_2d_andar = st.number_input("Unid. 2 Dorm / andar", min_value=0, value=8, step=1, key="viab_2d_andar")
    with cp3:
        u_3d_andar = st.number_input("Unid. 3 Dorm / andar", min_value=0, value=0, step=1, key="viab_3d_andar")
    with cp4:
        per_capita_l = st.selectbox(
            "Consumo per capita (L/dia)",
            options=[125.0, 100.0, 75.0],
            format_func=lambda v: f"{v:.0f} L/hab.dia ({'Recomendado Eng.' if v == 125 else 'Fórmula L4 original' if v == 75 else 'Intermediário'})",
            index=0,
            key="viab_per_capita",
        )
    with cp5:
        reserva_inc_l = st.number_input(
            "Reserva de incêndio / base L7 (L)",
            min_value=0.0,
            value=25000.0,
            step=1000.0,
            key="viab_res_inc",
        )

    pavs_pop = [
        PavimentoPopulacao("SUBSOLO", 0, 0, 0),
        PavimentoPopulacao("INFERIOR 01", 0, 0, 0),
        PavimentoPopulacao("TÉRREO", 0, 0, 0),
    ] + [
        PavimentoPopulacao(f"{i}º PAV.", int(u_1d_andar), int(u_2d_andar), int(u_3d_andar))
        for i in range(1, int(qtd_pav_tipo) + 1)
    ]
    agua = calcular_agua_e_populacao(
        pavimentos_pop=pavs_pop,
        litros_per_capita=float(per_capita_l),
        reserva_incendio_l=float(reserva_inc_l),
    )

    grade_cards(
        [
            ("População Prédio (Elevador / Água)", f"{agua.pop_agua} pessoas", f"Bombeiros: {agua.pop_bombeiros} pessoas"),
            ("Consumo Diário Estimado (L4)", _fmt_num(agua.consumo_diario_l, "L", 0), f"{agua.pop_agua} hab. × {per_capita_l:.0f} L/dia"),
            ("Reservatório Superior Recomendado (M10)", _fmt_num(agua.superior_recomendado_l, "L", 0), "40% do consumo + reserva L7"),
            ("Reservatório Inferior Recomendado (M13)", _fmt_num(agua.inferior_recomendado_l, "L", 0), "60% do consumo diário"),
            ("Volume Total Recomendado (M16)", _fmt_num(agua.total_recomendado_l, "L", 0), "Superior + Inferior"),
        ]
    )

    # -----------------------------------------------------------------------
    # ETAPA 10: Cálculo de Tráfego de Elevadores — NBR 5665 (Aba ELEVADOR)
    # -----------------------------------------------------------------------
    titulo_secao(
        "Etapa 10 — Cálculo de Tráfego de Elevadores — NBR 5665 (Aba ELEVADOR)",
        f"População ({agua.pop_elevador} pessoas) vinda da Etapa 9 e percurso ({quadro.altura_edificacao_m:.2f} m) vindo das cotas do Quadro de Áreas.",
    )
    ce1, ce2, ce3, ce4, ce5, ce6 = st.columns(6)
    with ce1:
        dest_cod = st.selectbox(
            "Destinação (O11)",
            options=list(DESTINACOES_PREDIO.keys()),
            format_func=lambda k: f"{k} — {DESTINACOES_PREDIO[k]['nome']}",
            index=6,  # 7 = Apartamentos
            key="viab_elev_dest",
        )
    with ce2:
        n_elev_in = st.number_input("Nº de Elevadores (D31)", min_value=1, max_value=12, value=2, step=1, key="viab_n_elev")
    with ce3:
        cap_pass_in = st.number_input("Capacidade Passag. (D33)", min_value=4, max_value=30, value=8, step=1, key="viab_cap_pass")
    with ce4:
        vel_elev_in = st.selectbox(
            "Velocidade (D37 em m/s)",
            options=[0.63, 0.75, 1.00, 1.25, 1.50, 1.75, 2.00, 2.50],
            index=4,  # 1.50 m/s
            key="viab_vel_elev",
        )
    with ce5:
        porta_in = st.selectbox("Tipo de Porta (D38)", options=["AC", "AL", "EV"], index=0, key="viab_porta_elev")
    with ce6:
        abert_in = st.selectbox("Abertura Porta (D39 em m)", options=[0.80, 0.90, 1.00, 1.10, 1.20], index=0, key="viab_abert_elev")

    elevador = calcular_trafego_elevadores(
        populacao_predio=agua.pop_elevador,
        unidades_no_grupo=int(n_elev_in),
        capac_nominal_pass=int(cap_pass_in),
        capac_calculo_pass=int(cap_pass_in),
        numero_paradas=max(2, len(quadro.pavimentos)),
        percurso_m=max(3.0, quadro.altura_edificacao_m),
        velocidade_m_s=float(vel_elev_in),
        tipo_porta=porta_in,
        abertura_porta_m=float(abert_in),
        codigo_destinacao=int(dest_cod),
    )

    for alerta_el in elevador.alertas:
        nota(alerta_el, "alert")

    grade_cards(
        [
            ("População em 5 min (D27)", f"{elevador.populacao_5min:.1f} pass.", f"{elevador.pct_5min:.0f}% de {elevador.populacao:.0f} pessoas"),
            ("Paradas Prováveis Np (D35)", f"{elevador.paradas_provaveis:.2f}", f"Total de paradas: {len(quadro.pavimentos)}"),
            ("Tempo Total de Viagem TTV (D51)", f"{elevador.ttv:.2f} s", f"T1={elevador.t1:.1f}s · T2={elevador.t2:.1f}s · T3={elevador.t3:.1f}s · T4={elevador.t4:.1f}s"),
            ("Intervalo de Tráfego (D52)", f"{elevador.intervalo_s:.2f} s", f"Máximo: {elevador.intervalo_max_s or 'Isento (Aptos)'}"),
            (
                "Capacidade de Tráfego (J54)",
                f"{elevador.capac_trafego:.2f} pass./5min",
                "✅ Atende demanda" if elevador.atende_capacidade else "⚠️ Abaixo da demanda de 5 min",
            ),
            ("Distância Mín. Aceleração (D57)", f"{elevador.distancia_min_m:.2f} m", f"Grau de serviço: {elevador.grau_servico:.2f}"),
        ]
    )

    # -----------------------------------------------------------------------
    # ETAPA 11: Cálculo de Cota de Desnível dos Reservatórios (Aba DESNÍVEL)
    # -----------------------------------------------------------------------
    titulo_secao(
        "Etapa 11 — Cálculo para Cota de Desnível dos Reservatórios (Aba DESNÍVEL — Trechos A, B e C)",
        "Cotas ancoradas na topografia do GeoSampa e comprimentos sugeridos pelas dimensões do lote (sem vínculos externos quebrados).",
    )
    cota_sarj_sugerida = float(entrada.cota_min_m if entrada.cota_min_m is not None else (cota_terreo_in - 0.69))
    comp_a_sug = round(max(10.0, entrada.profundidade_m or 30.0), 1)
    comp_b_sug = round(max(10.0, (entrada.profundidade_m or 30.0) * 0.65), 1)

    cd1, cd2, cd3, cd4, cd5 = st.columns(5)
    with cd1:
        cota_sarj_in = st.number_input(
            "Cota da Sarjeta (C40/G4 em m)",
            value=round(cota_sarj_sugerida, 2),
            step=0.10,
            format="%.2f",
            key=f"viab_cota_sarj_{cota_sarj_sugerida}",
        )
    with cd2:
        cota_arq_in = st.number_input(
            "Cota Terreno Arquitetura (G5/C48 em m)",
            value=round(float(cota_terreo_in), 2),
            step=0.10,
            format="%.2f",
            key=f"viab_cota_arq_{cota_terreo_in}",
        )
    with cd3:
        trecho_a_in = st.number_input("Trecho A — até Reúso (C4 em m)", min_value=1.0, value=comp_a_sug, step=1.0, key="viab_tr_a")
    with cd4:
        trecho_b_in = st.number_input("Trecho B — até Retardo (C6 em m)", min_value=1.0, value=comp_b_sug, step=1.0, key="viab_tr_b")
    with cd5:
        trecho_c_in = st.number_input("Trecho C — até Sarjeta (C8 em m)", min_value=1.0, value=10.0, step=1.0, key="viab_tr_c")

    desnivel = calcular_desnivel_reservatorios(
        cota_sarjeta_m=cota_sarj_in,
        cota_terreno_arquitetura_m=cota_arq_in,
        comprimento_trecho_a_m=trecho_a_in,
        comprimento_trecho_b_m=trecho_b_in,
        comprimento_trecho_c_m=trecho_c_in,
    )

    nota(desnivel.resultado, "info" if desnivel.adequado else "warn")

    tabela(
        ["Bloco / Trecho", "Parâmetro", "Valor", "Unid.", "Diagnóstico / Fórmula"],
        [
            [d.bloco, d.item, _fmt_num(d.valor, "", 3), d.unidade, d.observacao]
            for d in (desnivel.linhas_a + desnivel.linhas_b + desnivel.linhas_c)
        ],
    )

    # -----------------------------------------------------------------------
    # ETAPA 12: Retorno Financeiro Previsto (Viabilidade Econômico-Financeira)
    # -----------------------------------------------------------------------
    titulo_secao(
        "Etapa 12 — Retorno Financeiro Previsto (VGV, Orçamento, Lucro, Margem, ROI, VPL e TIR)",
        "Cálculo econômico-financeiro conectado diretamente às Áreas Privativas (HIS-2, HIS-1, R2V-1 e Lojas), Área Construída Total e Área do Terreno extraída do GeoSampa.",
    )

    _, prazo_obra_sugerido = estimar_prazo_obra_meses(
        area_construida_m2=quadro.area_construida_m2,
        num_pavimentos=max(1, len(quadro.pavimentos)),
        sistema_construtivo=sistema_construtivo,
    )

    cf1, cf2, cf3, cf4 = st.columns(4)
    with cf1:
        pm2_his2_in = st.number_input(
            "Preço Venda HIS-2 (R$/m² priv.)",
            min_value=1000.0,
            value=7200.0,
            step=100.0,
            key="viab_fin_pm2_his2",
        )
    with cf2:
        pm2_r2v1_in = st.number_input(
            "Preço Venda R2V-1 Mercado (R$/m² priv.)",
            min_value=1000.0,
            value=9500.0,
            step=100.0,
            key="viab_fin_pm2_r2v1",
        )
    with cf3:
        pm2_his1_in = st.number_input(
            "Preço Venda HIS-1 (R$/m² priv.)",
            min_value=1000.0,
            value=6500.0,
            step=100.0,
            key="viab_fin_pm2_his1",
        )
    with cf4:
        pm2_loja_in = st.number_input(
            "Preço Venda Lojas / Fachada Ativa (R$/m²)",
            min_value=1000.0,
            value=11000.0,
            step=100.0,
            key="viab_fin_pm2_loja",
        )

    cf5, cf6, cf7, cf8 = st.columns(4)
    with cf5:
        custo_terr_m2_in = st.number_input(
            "Custo Terreno (R$/m² de terreno)",
            min_value=0.0,
            value=4500.0,
            step=100.0,
            key="viab_fin_terr_m2",
        )
    with cf6:
        permuta_pct_in = st.number_input(
            "Permuta no Terreno (%)",
            min_value=0.0,
            max_value=100.0,
            value=0.0,
            step=5.0,
            key="viab_fin_permuta_pct",
        )
    with cf7:
        custo_obra_m2_in = st.number_input(
            "Custo Base Obra / CUB (R$/m² const.)",
            min_value=1000.0,
            value=3150.0,
            step=50.0,
            key="viab_fin_obra_m2",
        )
    with cf8:
        prazo_obra_in = st.number_input(
            "Prazo Execução de Obra (meses)",
            min_value=6,
            max_value=48,
            value=int(prazo_obra_sugerido),
            step=1,
            key=f"viab_fin_prazo_obra_{prazo_obra_sugerido}",
        )

    cf9, cf10, cf11, cf12 = st.columns(4)
    with cf9:
        pct_proj_in = st.number_input(
            "Projetos, Aprovações e Taxas (% obra)",
            min_value=0.0,
            max_value=25.0,
            value=5.0,
            step=0.5,
            key="viab_fin_pct_proj",
        )
    with cf10:
        pct_mkt_in = st.number_input(
            "Comercialização e Marketing (% VGV)",
            min_value=0.0,
            max_value=20.0,
            value=6.0,
            step=0.5,
            key="viab_fin_pct_mkt",
        )
    with cf11:
        pct_ret_in = st.number_input(
            "Impostos RET Ponderado (% VGV)",
            min_value=0.0,
            max_value=15.0,
            value=2.2,
            step=0.2,
            key="viab_fin_pct_ret",
        )
    with cf12:
        tma_anual_in = st.number_input(
            "Taxa Mínima de Atratividade TMA (% a.a.)",
            min_value=1.0,
            max_value=35.0,
            value=12.0,
            step=0.5,
            key="viab_fin_tma",
        )

    fin_cron = calcular_retorno_financeiro_e_cronograma(
        entrada=entrada,
        indices=indices,
        quadro=quadro,
        sistema_construtivo=sistema_construtivo,
        preco_m2_his2_rs=float(pm2_his2_in),
        preco_m2_his1_rs=float(pm2_his1_in),
        preco_m2_r2v1_rs=float(pm2_r2v1_in),
        preco_m2_loja_rs=float(pm2_loja_in),
        custo_terreno_m2_rs=float(custo_terr_m2_in),
        permuta_terreno_pct=float(permuta_pct_in),
        custo_obra_base_m2_rs=float(custo_obra_m2_in),
        pct_projetos_aprovacoes=float(pct_proj_in),
        pct_comercial_marketing=float(pct_mkt_in),
        pct_impostos_ret_vgv=float(pct_ret_in),
        tma_anual_pct=float(tma_anual_in),
        prazo_obra_override_meses=int(prazo_obra_in),
    )

    for n_fin in fin_cron.notas:
        nota(n_fin, "info")

    grade_cards(
        [
            (
                "VGV Bruto Previsto",
                f"R$ {_fmt_num(fin_cron.vgv_bruto_rs)}",
                f"Preço médio priv.: R$ {_fmt_num(fin_cron.preco_medio_privativo_m2_rs)}/m²",
            ),
            (
                "Custo Total do Empreendimento",
                f"R$ {_fmt_num(fin_cron.custo_total_empreendimento_rs)}",
                f"Obra direta: R$ {_fmt_num(fin_cron.custo_obra_direto_rs)} (R$ {_fmt_num(fin_cron.custo_obra_m2_efetivo_rs)}/m²)",
            ),
            (
                "Lucro Líquido Previsto",
                f"R$ {_fmt_num(fin_cron.lucro_liquido_rs)}",
                "✅ Empreendimento Viável" if fin_cron.viavel else "⚠️ Margem abaixo de 10%",
            ),
            (
                "Margem Líquida sobre VGV",
                _fmt_num(fin_cron.margem_liquida_vgv_pct, "%"),
                f"ROI sobre Custo Total: {_fmt_num(fin_cron.roi_sobre_custo_pct, '%')}",
            ),
            (
                "TIR Estimada e VPL",
                f"{_fmt_num(fin_cron.tir_anual_pct, '% a.a.')} ({_fmt_num(fin_cron.tir_mensal_pct, '% a.m.')})",
                f"VPL (TMA {tma_anual_in:.1f}% a.a.): R$ {_fmt_num(fin_cron.vpl_rs)}",
            ),
            (
                "Exposição Máxima de Caixa e Payback",
                f"R$ {_fmt_num(fin_cron.exposicao_maxima_caixa_rs)}",
                f"Pico no Mês {fin_cron.mes_pico_exposicao} · Payback: {'Mês ' + str(fin_cron.payback_mes) if fin_cron.payback_mes else 'No encerramento'}",
            ),
        ]
    )

    col_vgv_tab, col_custo_tab = st.columns([1.05, 1.25], gap="large")
    with col_vgv_tab:
        st.markdown("**Quadro de Receitas — VGV por Categoria de Uso**")
        tabela(
            ["Categoria", "Unidades", "Área Privativa (m²)", "R$/m²", "VGV Previsto (R$)", "Ticket Médio (R$)", "% VGV"],
            [
                [
                    iv.categoria,
                    str(iv.unidades),
                    _fmt_num(iv.area_privativa_m2, "m²"),
                    f"R$ {_fmt_num(iv.preco_m2_rs, '', 0)}",
                    f"R$ {_fmt_num(iv.vgv_rs)}",
                    f"R$ {_fmt_num(iv.ticket_medio_rs)}",
                    _fmt_num(iv.participacao_pct, "%", 1),
                ]
                for iv in fin_cron.itens_vgv
            ],
        )

    with col_custo_tab:
        st.markdown("**Orçamento Sintético — Custos e Despesas do Empreendimento**")
        tabela(
            ["Grupo de Custo", "Valor Previsto (R$)", "% Custo", "% VGV", "Memória de Cálculo"],
            [
                [
                    ic.grupo,
                    f"R$ {_fmt_num(ic.valor_rs)}",
                    _fmt_num(ic.pct_custo_total, "%", 1),
                    _fmt_num(ic.pct_vgv, "%", 1),
                    ic.criterio,
                ]
                for ic in fin_cron.itens_custo
            ],
        )

    # -----------------------------------------------------------------------
    # ETAPA 13: Cronograma Físico-Financeiro Aproximado de Obra e Curva S
    # -----------------------------------------------------------------------
    titulo_secao(
        "Etapa 13 — Cronograma Físico-Financeiro Aproximado de Obra e Curva S",
        f"Prazo total estimado: {fin_cron.prazo_total_meses} meses ({fin_cron.prazo_pre_obra_meses} meses Pré-Obra/Aprovação + {fin_cron.prazo_obra_meses} meses de Execução em {fin_cron.sistema_construtivo}).",
    )

    _renderizar_gantt_visual(fin_cron)

    st.write("")
    st.markdown("**Curva S e Fluxo de Caixa Trimestral Estimado (Desembolso × Receita × Saldo de Caixa)**")
    tabela(
        [
            "Trimestre",
            "Avanço Físico Obra",
            "Avanço Acumulado (Curva S)",
            "Desembolso Total (R$)",
            "Receita de Vendas/Repasse (R$)",
            "Saldo no Trimestre (R$)",
            "Saldo Acumulado de Caixa (R$)",
        ],
        [
            [
                ft.periodo,
                _fmt_num(ft.avanco_fisico_pct, "%", 1),
                _fmt_num(ft.avanco_acumulado_pct, "%", 1),
                f"R$ {_fmt_num(ft.desembolso_total_rs)}",
                f"R$ {_fmt_num(ft.receita_liquida_rs)}",
                f"R$ {_fmt_num(ft.saldo_periodo_rs)}",
                f"R$ {_fmt_num(ft.saldo_acumulado_rs)}",
            ]
            for ft in fin_cron.fluxo_trimestral
        ],
    )

    # -----------------------------------------------------------------------
    # ETAPA 14: Exportação da Planilha Completa (.xlsx com as 9 abas)
    # -----------------------------------------------------------------------
    titulo_secao(
        "Etapa 14 — Exportar Planilha Completa Calculada (.xlsx)",
        "Gera o arquivo Excel (.xlsx) com as 9 abas (Q. ÁREAS, Q. LUOPS, Q. ANEXOS, CALC. ÁGUA, ELEVADOR, DADOS, DESNÍVEL, FINANCEIRO e CRONOGRAMA) preenchidas com os dados do terreno.",
    )
    abas_xlsx = _montar_abas_xlsx(
        entrada=entrada,
        indices=indices,
        quadro=quadro,
        luops=linhas_luops,
        anexos=anexos,
        agua=agua,
        elevador=elevador,
        desnivel=desnivel,
        fin_cron=fin_cron,
        nome_empreendimento=nome_empreendimento,
        df_checklist=df_chk_edit,
        df_mix=df_mix_edit,
    )
    xlsx_bytes = gerar_xlsx_bytes(abas_xlsx)
    sql_base = entrada.sqls[0].replace(".", "_") if entrada.sqls else "terreno"
    st.download_button(
        "📥 Baixar Planilha Completa de Viabilidade (.xlsx — 9 Abas + Financeiro e Cronograma)",
        data=xlsx_bytes,
        file_name=f"QUADRO_DE_AREAS_{sql_base}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="primary",
        width="stretch",
        key="btn_download_xlsx_completo",
    )

