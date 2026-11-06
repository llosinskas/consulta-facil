"""
Motor de Viabilidade Econômico-Financeira (Retorno Financeiro Previsto)
e Cronograma Físico-Financeiro Aproximado de Obra (Etapa 13).

Conecta diretamente os quantitativos calculados a partir do GeoSampa + Planilha:
- Área do Terreno (`EntradaGeo.area_escritura_m2` e `area_terreno_m2`)
- Índices Urbanísticos (`IndicesLegais`: Zona, CA Básico, CA Projeto, Modalidade EHIS)
- Quadro de Áreas (`QuadroAreas`: Área Construída Total, Áreas Privativas por uso HIS-2, HIS-1, R2V-1, Lojas e nº de pavimentos)
- Sistema Construtivo selecionado (`Concreto Moldado in Loco`, `Alvenaria Estrutural`, `Paredes de Concreto`)
"""

import math
from typing import Dict, List, Optional, Tuple

from domain.viabilidade_models import (
    EntradaGeo,
    EtapaCronograma,
    IndicesLegais,
    ItemCustoEmpreendimento,
    ItemReceitaVGV,
    PeriodoFluxoCaixa,
    QuadroAreas,
    ResultadoFinanceiroCronograma,
)

FATOR_CUSTO_SISTEMA: Dict[str, float] = {
    "Concreto Moldado in Loco": 1.00,
    "Alvenaria Estrutural": 0.93,
    "Paredes de Concreto": 0.95,
}

FATOR_PRAZO_SISTEMA: Dict[str, float] = {
    "Concreto Moldado in Loco": 1.00,
    "Alvenaria Estrutural": 0.88,
    "Paredes de Concreto": 0.80,
}


def _calcular_tir_mensal(fluxos_mensais: List[float]) -> float:
    """
    Calcula a Taxa Interna de Retorno (TIR) mensal (%) por busca em bisseção segura.
    Retorna 0.0 se não houver mudança de sinal.
    """
    tem_negativo = any(f < 0 for f in fluxos_mensais)
    tem_positivo = any(f > 0 for f in fluxos_mensais)
    if not (tem_negativo and tem_positivo):
        return 0.0

    def vpl(taxa: float) -> float:
        total = 0.0
        for t, cf in enumerate(fluxos_mensais):
            total += cf / ((1.0 + taxa) ** t)
        return total

    low = -0.15
    high = 0.50
    v_low = vpl(low)
    v_high = vpl(high)
    if v_low * v_high > 0:
        # Caso a soma simples seja positiva, estima retorno médio mensal
        soma = sum(fluxos_mensais)
        inv = abs(sum(f for f in fluxos_mensais if f < 0))
        if inv > 0 and len(fluxos_mensais) > 1:
            r_total = max(0.0, soma / inv)
            return round((((1.0 + r_total) ** (1.0 / len(fluxos_mensais))) - 1.0) * 100.0, 2)
        return 0.0

    for _ in range(80):
        mid = (low + high) / 2.0
        v_mid = vpl(mid)
        if abs(v_mid) < 1e-4:
            return round(mid * 100.0, 2)
        if v_low * v_mid <= 0:
            high = mid
            v_high = v_mid
        else:
            low = mid
            v_low = v_mid

    return round(((low + high) / 2.0) * 100.0, 2)


def _gerar_barra_gantt(mes_inicio: int, mes_fim: int, prazo_total: int, largura_barra: int = 24) -> str:
    """Gera uma representação visual de barra Gantt proporcional ao prazo total."""
    if prazo_total <= 0:
        return "█"
    chars: List[str] = []
    for i in range(largura_barra):
        m_ref = 1 + (i * prazo_total) / float(largura_barra)
        m_ref_fim = 1 + ((i + 1) * prazo_total) / float(largura_barra)
        if m_ref_fim >= mes_inicio and m_ref <= mes_fim:
            chars.append("█")
        else:
            chars.append("░")
    return "".join(chars)


def estimar_prazo_obra_meses(
    area_construida_m2: float,
    num_pavimentos: int,
    sistema_construtivo: str = "Alvenaria Estrutural",
) -> Tuple[int, int]:
    """
    Estima o prazo de Pré-Obra (aprovação/incorporação) e o prazo de Execução de Obra (meses)
    com base na área construída total, número de pavimentos e sistema construtivo.
    """
    prazo_pre_obra = 4 if area_construida_m2 <= 6000 else 6

    # Base de engenharia: ~10 meses fixos (fundação + acabamentos + habite-se)
    # + 0,55 mês por pavimento + 1 mês a cada 1.800 m² de área construída
    base_obra = 9.0 + (max(1, num_pavimentos) * 0.50) + (max(0.0, area_construida_m2) / 2200.0)
    fator_sis = FATOR_PRAZO_SISTEMA.get(sistema_construtivo, 1.0)
    prazo_obra = int(round(max(12.0, min(36.0, base_obra * fator_sis))))
    return prazo_pre_obra, prazo_obra


def calcular_retorno_financeiro_e_cronograma(
    entrada: EntradaGeo,
    indices: IndicesLegais,
    quadro: QuadroAreas,
    sistema_construtivo: str = "Alvenaria Estrutural",
    preco_m2_his2_rs: float = 7200.0,
    preco_m2_his1_rs: float = 6500.0,
    preco_m2_r2v1_rs: float = 9500.0,
    preco_m2_loja_rs: float = 11000.0,
    custo_terreno_m2_rs: float = 4500.0,
    permuta_terreno_pct: float = 0.0,
    custo_obra_base_m2_rs: float = 3150.0,
    valor_outorga_m2_rs: float = 1450.0,
    pct_projetos_aprovacoes: float = 5.0,
    pct_comercial_marketing: float = 6.0,
    pct_incorporacao_gestao: float = 4.0,
    pct_impostos_ret_vgv: float = 2.2,
    tma_anual_pct: float = 12.0,
    prazo_obra_override_meses: Optional[int] = None,
) -> ResultadoFinanceiroCronograma:
    """
    Calcula o Retorno Financeiro Previsto (VGV, Custos Detalhados, Lucro Líquido, Margem, ROI,
    VPL, TIR, Exposição de Caixa e Payback) e o Cronograma Físico-Financeiro Aproximado de Obra.
    """
    sub_u = quadro.subtotal_unidades
    sub_a = quadro.subtotal_areas

    # -----------------------------------------------------------------------
    # 1. RECEITAS — VGV POR CATEGORIA DE USO (Conectado ao Quadro de Áreas)
    # -----------------------------------------------------------------------
    uh_his2 = int(round(sub_u.get("u_his2", 0.0) + sub_u.get("u_his2_cota", 0.0)))
    uh_his1 = int(round(sub_u.get("u_his1", 0.0) + sub_u.get("u_his1_50", 0.0)))
    uh_r2v1 = int(round(sub_u.get("u_r2v1", 0.0) + sub_u.get("u_r2v1_10", 0.0)))
    uh_loja = int(round(sub_u.get("u_nr1_3", 0.0) + sub_u.get("u_nr1_12", 0.0)))

    # Rateio proporcional do terraço não computável entre HIS e R2V
    base_comp_res = sub_a.get("c_his2", 0.0) + sub_a.get("c_his1", 0.0) + sub_a.get("c_r2v1", 0.0)
    terraco_nc = sub_a.get("nc_terraco", 0.0)
    if base_comp_res > 0:
        terr_his2 = terraco_nc * (sub_a.get("c_his2", 0.0) / base_comp_res)
        terr_his1 = terraco_nc * (sub_a.get("c_his1", 0.0) / base_comp_res)
        terr_r2v1 = terraco_nc * (sub_a.get("c_r2v1", 0.0) / base_comp_res)
    else:
        terr_his2, terr_his1, terr_r2v1 = terraco_nc * 0.80, 0.0, terraco_nc * 0.20

    area_priv_his2 = round(
        sub_a.get("c_his2", 0.0)
        + sub_a.get("c_terraco_his2", 0.0)
        + sub_a.get("nc_his2_cota", 0.0)
        + terr_his2,
        2,
    )
    area_priv_his1 = round(
        sub_a.get("c_his1", 0.0) + sub_a.get("nc_his1_50", 0.0) + terr_his1,
        2,
    )
    area_priv_r2v1 = round(
        sub_a.get("c_r2v1", 0.0)
        + sub_a.get("c_terraco_r2v1", 0.0)
        + sub_a.get("nc_r2v1_10", 0.0)
        + terr_r2v1,
        2,
    )
    area_priv_loja = round(
        sub_a.get("nc_nr1_3_fa", 0.0) + sub_a.get("nc_nr1_12", 0.0),
        2,
    )

    vgv_his2 = round(area_priv_his2 * preco_m2_his2_rs, 2)
    vgv_his1 = round(area_priv_his1 * preco_m2_his1_rs, 2)
    vgv_r2v1 = round(area_priv_r2v1 * preco_m2_r2v1_rs, 2)
    vgv_loja = round(area_priv_loja * preco_m2_loja_rs, 2)

    vgv_bruto = round(vgv_his2 + vgv_his1 + vgv_r2v1 + vgv_loja, 2)
    area_priv_total_venda = round(area_priv_his2 + area_priv_his1 + area_priv_r2v1 + area_priv_loja, 2)
    preco_medio_m2 = round(vgv_bruto / area_priv_total_venda, 2) if area_priv_total_venda > 0 else 0.0

    itens_vgv: List[ItemReceitaVGV] = []
    for cat, uh, area_p, pm2, vgv_c in [
        ("Residencial HIS-2", uh_his2, area_priv_his2, preco_m2_his2_rs, vgv_his2),
        ("Residencial HIS-1", uh_his1, area_priv_his1, preco_m2_his1_rs, vgv_his1),
        ("Residencial R2V-1 (Mercado)", uh_r2v1, area_priv_r2v1, preco_m2_r2v1_rs, vgv_r2v1),
        ("Comercial / Fachada Ativa (NR)", uh_loja, area_priv_loja, preco_m2_loja_rs, vgv_loja),
    ]:
        if area_p > 0 or uh > 0:
            ticket = round(vgv_c / uh, 2) if uh > 0 else vgv_c
            part = round((vgv_c / vgv_bruto) * 100.0, 2) if vgv_bruto > 0 else 0.0
            itens_vgv.append(
                ItemReceitaVGV(
                    categoria=cat,
                    unidades=uh,
                    area_privativa_m2=area_p,
                    preco_m2_rs=pm2,
                    vgv_rs=vgv_c,
                    ticket_medio_rs=ticket,
                    participacao_pct=part,
                )
            )

    # -----------------------------------------------------------------------
    # 2. CUSTOS DO EMPREENDIMENTO (Terreno, Obra, Outorga, Projetos, Comercial, Impostos)
    # -----------------------------------------------------------------------
    # 2.1 Terreno (Aquisição em dinheiro e/ou Permuta Financeira + ITBI/Registro 4%)
    valor_terreno_base = round(entrada.area_escritura_m2 * custo_terreno_m2_rs, 2)
    fator_caixa_terreno = max(0.0, min(1.0, (100.0 - permuta_terreno_pct) / 100.0))
    custo_terreno_aquisicao = round(valor_terreno_base * fator_caixa_terreno, 2)
    custo_permuta_financeira = round(vgv_bruto * (permuta_terreno_pct / 100.0), 2)
    custo_itbi_escritura = round(valor_terreno_base * 0.04, 2)
    custo_terreno_total = round(custo_terreno_aquisicao + custo_permuta_financeira + custo_itbi_escritura, 2)

    # 2.2 Custo Direto de Obra (Hard Cost) ajustado pelo Sistema Construtivo e Topografia
    fator_sis_custo = FATOR_CUSTO_SISTEMA.get(sistema_construtivo, 1.0)
    desnivel_lote = float(
        (entrada.cota_max_m - entrada.cota_min_m)
        if (entrada.cota_max_m is not None and entrada.cota_min_m is not None)
        else 0.0
    )
    adicional_topografia = 1.03 if desnivel_lote > 4.0 else 1.00
    custo_obra_m2_efetivo = round(custo_obra_base_m2_rs * fator_sis_custo * adicional_topografia, 2)
    custo_obra_direto = round(quadro.area_construida_m2 * custo_obra_m2_efetivo, 2)

    # 2.3 Projetos Executivos, Aprovações, Taxas, Seguros e Ligações Definitivas
    custo_projetos_taxas = round(custo_obra_direto * (pct_projetos_aprovacoes / 100.0), 2)

    # 2.4 Outorga Onerosa e Cota de Solidariedade
    # Áreas HIS são isentas de outorga onerosa (PDE Art. 117 / Decreto HIS 63.728/24).
    # Cobra-se sobre o excedente computável não-HIS acima do CA Básico (proporcional à parcela R2V).
    ca_bas_m2 = float(indices.area_comp_basica_m2 or entrada.area_terreno_m2)
    excedente_comp_total = max(0.0, quadro.area_computavel_m2 - ca_bas_m2)
    prop_r2v_efetiva = (
        (quadro.pct_r2v / 100.0)
        if quadro.pct_r2v is not None
        else max(0.0, 1.0 - indices.proporcao_his)
    )
    area_outorga_tributavel = round(excedente_comp_total * prop_r2v_efetiva, 2)
    custo_outorga_cota = round(area_outorga_tributavel * valor_outorga_m2_rs, 2)

    # 2.5 Comercialização, Stand, Marketing e Corretagem (% sobre VGV)
    custo_comercial_mkt = round(vgv_bruto * (pct_comercial_marketing / 100.0), 2)

    # 2.6 Incorporação, Administração e Tributos (RET sobre VGV)
    custo_incorp_gestao = round(custo_obra_direto * (pct_incorporacao_gestao / 100.0), 2)
    custo_impostos_ret = round(vgv_bruto * (pct_impostos_ret_vgv / 100.0), 2)
    custo_incorporacao_impostos = round(custo_incorp_gestao + custo_impostos_ret, 2)

    custo_total = round(
        custo_terreno_total
        + custo_obra_direto
        + custo_projetos_taxas
        + custo_outorga_cota
        + custo_comercial_mkt
        + custo_incorporacao_impostos,
        2,
    )

    def _item_custo(grupo: str, desc: str, val: float, crit: str) -> ItemCustoEmpreendimento:
        p_custo = round((val / custo_total) * 100.0, 2) if custo_total > 0 else 0.0
        p_vgv = round((val / vgv_bruto) * 100.0, 2) if vgv_bruto > 0 else 0.0
        return ItemCustoEmpreendimento(
            grupo=grupo,
            descricao=desc,
            valor_rs=val,
            pct_custo_total=p_custo,
            pct_vgv=p_vgv,
            criterio=crit,
        )

    itens_custo: List[ItemCustoEmpreendimento] = [
        _item_custo(
            "1. Terreno e Legalização",
            "Aquisição do Terreno + Permuta + ITBI/Registro (4%)",
            custo_terreno_total,
            f"{entrada.area_escritura_m2:,.2f} m² × R$ {custo_terreno_m2_rs:,.0f}/m² (+4% ITBI)",
        ),
        _item_custo(
            "2. Custo Direto de Obra (Hard Cost)",
            f"Construção Civil ({sistema_construtivo})",
            custo_obra_direto,
            f"{quadro.area_construida_m2:,.2f} m² × R$ {custo_obra_m2_efetivo:,.2f}/m²",
        ),
        _item_custo(
            "3. Projetos e Aprovações",
            "Projetos Executivos, Licenças, Taxas e Ensaios",
            custo_projetos_taxas,
            f"{pct_projetos_aprovacoes:.1f}% sobre o Custo Direto de Obra",
        ),
        _item_custo(
            "4. Outorga Onerosa / Cota Solidariedade",
            "Outorga sobre fração R2V acima do C.A. Básico (HIS isento)",
            custo_outorga_cota,
            f"{area_outorga_tributavel:,.2f} m² tributáveis × R$ {valor_outorga_m2_rs:,.0f}/m²",
        ),
        _item_custo(
            "5. Comercialização e Marketing",
            "Corretagem, Stand/Decorado e Publicidade",
            custo_comercial_mkt,
            f"{pct_comercial_marketing:.1f}% sobre o VGV Bruto",
        ),
        _item_custo(
            "6. Incorporação, Gestão e Tributos (RET)",
            f"Taxa de Gestão ({pct_incorporacao_gestao:.1f}% obra) + Impostos RET ({pct_impostos_ret_vgv:.1f}% VGV)",
            custo_incorporacao_impostos,
            "Regime Especial de Tributação (RET HIS/MCMV + Mercado)",
        ),
    ]

    # -----------------------------------------------------------------------
    # 3. CRONOGRAMA FÍSICO-FINANCEIRO APROXIMADO DE OBRA (10 Macroetapas)
    # -----------------------------------------------------------------------
    num_pavs = max(1, len(quadro.pavimentos))
    prazo_pre, prazo_obra_calc = estimar_prazo_obra_meses(
        area_construida_m2=quadro.area_construida_m2,
        num_pavimentos=num_pavs,
        sistema_construtivo=sistema_construtivo,
    )
    prazo_obra = int(prazo_obra_override_meses) if prazo_obra_override_meses else prazo_obra_calc
    prazo_total = prazo_pre + prazo_obra

    def _m_obra(frac_ini: float, frac_fim: float) -> Tuple[int, int]:
        m_i = prazo_pre + max(1, int(round(frac_ini * prazo_obra)))
        m_f = prazo_pre + max(m_i - prazo_pre, int(round(frac_fim * prazo_obra)))
        m_f = min(prazo_total, max(m_i, m_f))
        return m_i, m_f

    # Definição das 10 macroetapas escalonadas ao prazo da obra
    definicoes_etapas = [
        (1, "Pré-Obra", "Projetos Executivos, Aprovação Legal, RI e Lançamento", 1, prazo_pre, 0.0, custo_projetos_taxas),
        (2, "Obra — Início", "Serviços Preliminares, Canteiro, Demolição e Terraplenagem", *_m_obra(0.00, 0.12), 4.5, None),
        (3, "Obra — Infra", "Fundações, Contenções e Infraestrutura Enterrada", *_m_obra(0.08, 0.28), 11.5, None),
        (4, "Obra — Estrutura", f"Superestrutura ({num_pavs} níveis — {sistema_construtivo})", *_m_obra(0.20, 0.65), 26.0, None),
        (5, "Obra — Vedação", "Alvenaria de Vedação, Divisórias e Fechamentos", *_m_obra(0.30, 0.72), 8.5, None),
        (6, "Obra — Sistemas", "Instalações Elétricas, Hidrossanitárias, Gás e Incêndio", *_m_obra(0.35, 0.85), 14.0, None),
        (7, "Obra — Estanqueidade", "Impermeabilização, Cobertura e Reservatórios (Água/Reúso/Retardo)", *_m_obra(0.55, 0.82), 5.5, None),
        (8, "Obra — Acabamentos", "Revestimentos Internos (Piso/Parede), Fachada e Esquadrias", *_m_obra(0.50, 0.92), 16.5, None),
        (9, "Obra — Equipamentos", "Elevadores, Louças, Metais, Bancadas e Pintura", *_m_obra(0.68, 0.96), 9.0, None),
        (10, "Pós-Obra / Entrega", "Áreas Comuns, Fachada Ativa, Paisagismo, Limpeza e Habite-se", *_m_obra(0.85, 1.00), 4.5, None),
    ]

    etapas_cronograma: List[EtapaCronograma] = []
    for ordem, fase, nome_etapa, m_ini, m_fim, peso_obra, custo_fixo in definicoes_etapas:
        dur = max(1, m_fim - m_ini + 1)
        custo_et = round(custo_fixo if custo_fixo is not None else (custo_obra_direto * (peso_obra / 100.0)), 2)
        barra = _gerar_barra_gantt(m_ini, m_fim, prazo_total)
        etapas_cronograma.append(
            EtapaCronograma(
                ordem=ordem,
                fase=fase,
                etapa=nome_etapa,
                mes_inicio=m_ini,
                mes_fim=m_fim,
                duracao_meses=dur,
                peso_obra_pct=peso_obra,
                custo_estimado_rs=custo_et,
                barra_gantt=barra,
            )
        )

    # -----------------------------------------------------------------------
    # 4. CURVA S E FLUXO DE CAIXA MENSAL / TRIMESTRAL
    # -----------------------------------------------------------------------
    # Distribui os custos de obra pelas etapas mês a mês (Curva S real das etapas)
    custo_obra_mensal = [0.0] * prazo_total
    for et in etapas_cronograma:
        if et.peso_obra_pct > 0:
            valor_mes_et = et.custo_estimado_rs / float(et.duracao_meses)
            for m in range(et.mes_inicio, et.mes_fim + 1):
                if 1 <= m <= prazo_total:
                    custo_obra_mensal[m - 1] += valor_mes_et

    # Desembolso total mensal (Terreno na pré-obra + Outorga + Obra + Gestão + Comercial + Impostos)
    desembolso_mensal = [0.0] * prazo_total
    receita_mensal = [0.0] * prazo_total

    # Terreno + ITBI concentrados nos primeiros 2 meses de pré-obra
    meses_terreno = min(2, prazo_pre)
    for m in range(meses_terreno):
        desembolso_mensal[m] += (custo_terreno_aquisicao + custo_itbi_escritura) / float(meses_terreno)

    # Projetos e Outorga distribuídos na pré-obra
    for m in range(prazo_pre):
        desembolso_mensal[m] += (custo_projetos_taxas + custo_outorga_cota) / float(max(1, prazo_pre))

    # Obra e Gestão durante os meses de execução
    for m in range(prazo_total):
        desembolso_mensal[m] += custo_obra_mensal[m]
        if m >= prazo_pre and prazo_obra > 0:
            desembolso_mensal[m] += custo_incorp_gestao / float(prazo_obra)

    # Receita de vendas (Lançamento no último mês da pré-obra + medição/repasse CEF/associativo durante a obra + chaves)
    vgv_disponivel_incorporador = max(0.0, vgv_bruto - custo_permuta_financeira)
    for m in range(prazo_total):
        mes_num = m + 1
        if mes_num < prazo_pre:
            fator_rec = 0.0
        elif mes_num == prazo_pre:
            # Lançamento comercial (sinal / entrada: 8% do VGV)
            fator_rec = 0.08
        elif mes_num < prazo_total:
            # Repasse associativo / evolução de obra proporcional ao avanço físico (77% do VGV ao longo da obra)
            avanco_m = (custo_obra_mensal[m] / custo_obra_direto) if custo_obra_direto > 0 else (1.0 / max(1, prazo_obra))
            fator_rec = 0.77 * avanco_m
        else:
            # Entrega das chaves / repasse final no último mês (15% restante + avanço do último mês)
            avanco_m = (custo_obra_mensal[m] / custo_obra_direto) if custo_obra_direto > 0 else 0.0
            fator_rec = 0.15 + (0.77 * avanco_m)

        rec_bruta_m = vgv_disponivel_incorporador * fator_rec
        receita_mensal[m] = rec_bruta_m
        # Comercialização e Impostos RET proporcionais ao recebimento
        if vgv_disponivel_incorporador > 0:
            prop_rec = rec_bruta_m / vgv_disponivel_incorporador
            desembolso_mensal[m] += (custo_comercial_mkt + custo_impostos_ret) * prop_rec

    fluxo_liquido_mensal: List[float] = []
    saldo_acum = 0.0
    exposicao_maxima = 0.0
    mes_pico_exp = 1
    payback_mes: Optional[int] = None
    ja_ficou_negativo = False

    for m in range(prazo_total):
        liq = receita_mensal[m] - desembolso_mensal[m]
        fluxo_liquido_mensal.append(liq)
        saldo_acum += liq
        if saldo_acum < 0:
            ja_ficou_negativo = True
        if saldo_acum < exposicao_maxima:
            exposicao_maxima = saldo_acum
            mes_pico_exp = m + 1
        if ja_ficou_negativo and saldo_acum >= 0 and payback_mes is None:
            payback_mes = m + 1

    # Agrupamento trimestral para exibição limpa e executiva
    fluxo_trimestral: List[PeriodoFluxoCaixa] = []
    avanco_acum_pct = 0.0
    saldo_acum_trim = 0.0
    trim_idx = 1
    for m_start in range(0, prazo_total, 3):
        m_end = min(prazo_total, m_start + 3)
        obra_trim = sum(custo_obra_mensal[m_start:m_end])
        avanco_trim = round((obra_trim / custo_obra_direto) * 100.0, 2) if custo_obra_direto > 0 else 0.0
        avanco_acum_pct = round(min(100.0, avanco_acum_pct + avanco_trim), 2)
        desemb_trim = round(sum(desembolso_mensal[m_start:m_end]), 2)
        rec_trim = round(sum(receita_mensal[m_start:m_end]), 2)
        saldo_per = round(rec_trim - desemb_trim, 2)
        saldo_acum_trim = round(saldo_acum_trim + saldo_per, 2)

        fluxo_trimestral.append(
            PeriodoFluxoCaixa(
                periodo=f"T{trim_idx} (Meses {m_start + 1} a {m_end})",
                mes_inicio=m_start + 1,
                mes_fim=m_end,
                avanco_fisico_pct=avanco_trim,
                avanco_acumulado_pct=avanco_acum_pct,
                desembolso_total_rs=desemb_trim,
                receita_liquida_rs=rec_trim,
                saldo_periodo_rs=saldo_per,
                saldo_acumulado_rs=saldo_acum_trim,
            )
        )
        trim_idx += 1

    # -----------------------------------------------------------------------
    # 5. INDICADORES DE RETORNO FINANCEIRO (Lucro, Margem, ROI, VPL, TIR)
    # -----------------------------------------------------------------------
    lucro_liquido = round(vgv_bruto - custo_total, 2)
    margem_vgv = round((lucro_liquido / vgv_bruto) * 100.0, 2) if vgv_bruto > 0 else 0.0
    roi_custo = round((lucro_liquido / custo_total) * 100.0, 2) if custo_total > 0 else 0.0

    tma_mensal = ((1.0 + (tma_anual_pct / 100.0)) ** (1.0 / 12.0)) - 1.0
    vpl = round(
        sum(cf / ((1.0 + tma_mensal) ** (t + 1)) for t, cf in enumerate(fluxo_liquido_mensal)),
        2,
    )
    tir_mensal = _calcular_tir_mensal(fluxo_liquido_mensal)
    tir_anual = round((((1.0 + (tir_mensal / 100.0)) ** 12.0) - 1.0) * 100.0, 2) if tir_mensal > -99.0 else 0.0

    notas: List[str] = []
    if area_outorga_tributavel == 0.0 and quadro.area_computavel_m2 > ca_bas_m2:
        notas.append("Isenção total de Outorga Onerosa aplicada para a área computável destinada a HIS.")
    elif area_outorga_tributavel > 0.0:
        notas.append(
            f"Outorga Onerosa estimada apenas sobre a fração não-HIS acima do C.A. Básico ({area_outorga_tributavel:,.2f} m²)."
        )
    notas.append(
        f"Cronograma dimensionado para {quadro.area_construida_m2:,.2f} m² ({num_pavs} níveis) em {sistema_construtivo}: "
        f"{prazo_pre} meses de pré-obra + {prazo_obra} meses de execução = {prazo_total} meses totais."
    )

    return ResultadoFinanceiroCronograma(
        itens_vgv=itens_vgv,
        vgv_bruto_rs=vgv_bruto,
        preco_medio_privativo_m2_rs=preco_medio_m2,
        itens_custo=itens_custo,
        custo_terreno_total_rs=custo_terreno_total,
        custo_obra_direto_rs=custo_obra_direto,
        custo_obra_m2_efetivo_rs=custo_obra_m2_efetivo,
        custo_projetos_taxas_rs=custo_projetos_taxas,
        custo_outorga_cota_rs=custo_outorga_cota,
        custo_comercial_mkt_rs=custo_comercial_mkt,
        custo_incorporacao_impostos_rs=custo_incorporacao_impostos,
        custo_total_empreendimento_rs=custo_total,
        lucro_liquido_rs=lucro_liquido,
        margem_liquida_vgv_pct=margem_vgv,
        roi_sobre_custo_pct=roi_custo,
        exposicao_maxima_caixa_rs=round(abs(exposicao_maxima), 2),
        mes_pico_exposicao=mes_pico_exp,
        payback_mes=payback_mes,
        vpl_rs=vpl,
        tir_mensal_pct=tir_mensal,
        tir_anual_pct=tir_anual,
        viavel=lucro_liquido > 0 and margem_vgv >= 10.0,
        prazo_pre_obra_meses=prazo_pre,
        prazo_obra_meses=prazo_obra,
        prazo_total_meses=prazo_total,
        sistema_construtivo=sistema_construtivo,
        etapas_cronograma=etapas_cronograma,
        fluxo_trimestral=fluxo_trimestral,
        notas=notas,
    )
