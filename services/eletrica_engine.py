"""
Motor de Engenharia Elétrica Preliminar (Etapa 14):
- Demanda média por apartamento (individual e diversificada no barramento coletivo conforme NBR 5410 e Norma Enel SP)
- Demanda do condomínio (elevadores, bombas, áreas comuns, recarga VE) e lojas (Fachada Ativa / NR)
- Diagnóstico de obrigatoriedade de Subestação / Posto de Transformação (limite de 75 kVA em BT e faixas de MT 13,8 kV)
- Dimensionamento de Transformador Comercial (112,5 / 150 / 225 / 300 / 500 / 750 / 1000 kVA) e Gerador de Emergência
- Orçamento estimado completo da Parte Elétrica (Entrada/Subestação, Medição/Prumadas, Unidades, Condomínio/SPDA e Gerador)
"""

from typing import Dict, List, Optional, Tuple

from domain.viabilidade_models import (
    ItemCustoEletrica,
    QuadroAreas,
    ResultadoPreviaEletrica,
)

PERFIS_ELETRICOS_APTO: Dict[str, Dict[str, object]] = {
    "PADRAO_HIS_CHUVEIRO": {
        "nome": "Padrão HIS / Econômico (Chuveiro Elétrico 5.500W + Previsão Split)",
        "carga_base_kva": 9.80,
        "demanda_indiv_base_kva": 4.90,
        "disjuntor_a": 50,
        "fornecimento": "Bifásico 220/127 V",
    },
    "PADRAO_GAS_SPLIT": {
        "nome": "Padrão Aquecimento a Gás + Ar-Condicionado Split",
        "carga_base_kva": 6.80,
        "demanda_indiv_base_kva": 3.40,
        "disjuntor_a": 40,
        "fornecimento": "Bifásico 220/127 V",
    },
    "PADRAO_100_ELETRICO": {
        "nome": "Padrão 100% Elétrico (Chuveiro + Cooktop Indução + Split)",
        "carga_base_kva": 13.50,
        "demanda_indiv_base_kva": 6.40,
        "disjuntor_a": 63,
        "fornecimento": "Trifásico 220/127 V",
    },
}

TRANSFORMADORES_PADRAO_KVA: List[float] = [75.0, 112.5, 150.0, 225.0, 300.0, 500.0, 750.0, 1000.0, 1500.0]


def _fator_diversidade_coletivo(num_unidades: int) -> float:
    """
    Retorna o fator de simultaneidade/diversidade coletivo para edifícios residenciais
    multifamiliares (curva típica Enel SP / normas de distribuição para agrupamento de unidades).
    """
    n = max(1, int(num_unidades))
    if n <= 4:
        return 0.85
    if n <= 10:
        return 0.72
    if n <= 20:
        return 0.62
    if n <= 40:
        return 0.54
    if n <= 60:
        return 0.48
    if n <= 100:
        return 0.44
    if n <= 160:
        return 0.40
    if n <= 250:
        return 0.37
    return 0.35


def _selecionar_transformador_comercial(demanda_total_kva: float) -> Tuple[Optional[float], str, float]:
    """
    Seleciona a potência nominal padronizada de transformador (com folga operacional de ~15%)
    e retorna `(potencia_kva, configuracao_subestacao, area_minima_m2)`.
    """
    if demanda_total_kva <= 75.0:
        return None, "Entrada Direta em Baixa Tensão (Sem Subestação / Sem Transformador Exclusivo)", 0.0

    demanda_projeto = demanda_total_kva * 1.12  # Folga técnica de 12%
    escolhido = TRANSFORMADORES_PADRAO_KVA[-1]
    for pot in TRANSFORMADORES_PADRAO_KVA:
        if pot >= demanda_projeto and pot > 75.0:
            escolhido = pot
            break

    if escolhido <= 225.0:
        return (
            escolhido,
            f"Posto de Transformação / Subestação Simplificada ({escolhido:g} kVA — 13,8 kV / 220-127 V)",
            12.0,
        )
    if escolhido <= 500.0:
        return (
            escolhido,
            f"Subestação / Cabine Primária Abrigada c/ Transformador a Seco ({escolhido:g} kVA — 13,8 kV)",
            18.0,
        )
    return (
        escolhido,
        f"Subestação / Cabine Primária de Grande Porte ({escolhido:g} kVA — 13,8 kV, medição e proteção MT)",
        26.0,
    )


def calcular_previa_eletrica(
    quadro: QuadroAreas,
    num_elevadores: int = 2,
    perfil_chave: str = "PADRAO_HIS_CHUVEIRO",
    vagas_recarga_ve: int = 2,
    incluir_gerador_emergencia: bool = True,
    custo_base_instalacao_m2_rs: float = 235.0,
) -> ResultadoPreviaEletrica:
    """
    ETAPA 14: Calcula a prévia completa de Engenharia Elétrica:
    1. Demanda média dos apartamentos (individual e diversificada no barramento do prédio)
    2. Demanda do condomínio, lojas e recarga de veículos elétricos
    3. Necessidade ou não de Subestação / Posto de Transformação (critério 75 kVA BT / MT 13,8 kV Enel SP)
    4. Custo estimado detalhado da parte elétrica do empreendimento
    """
    perfil = PERFIS_ELETRICOS_APTO.get(perfil_chave, PERFIS_ELETRICOS_APTO["PADRAO_HIS_CHUVEIRO"])
    sub_u = quadro.subtotal_unidades
    sub_a = quadro.subtotal_areas

    uh_res = int(
        round(
            sub_u.get("u_his2", 0.0)
            + sub_u.get("u_his2_cota", 0.0)
            + sub_u.get("u_his1", 0.0)
            + sub_u.get("u_his1_50", 0.0)
            + sub_u.get("u_r2v1", 0.0)
            + sub_u.get("u_r2v1_10", 0.0)
        )
    )
    uh_res_calc = max(1, uh_res)

    area_priv_res = (
        sub_a.get("c_his2", 0.0)
        + sub_a.get("c_his1", 0.0)
        + sub_a.get("c_r2v1", 0.0)
        + sub_a.get("nc_his2_cota", 0.0)
        + sub_a.get("nc_his1_50", 0.0)
        + sub_a.get("nc_r2v1_10", 0.0)
        + sub_a.get("nc_terraco", 0.0)
    )
    area_media_apto = round(area_priv_res / uh_res_calc, 2) if area_priv_res > 0 else 25.0

    # Ajuste fino de iluminação + tomadas de uso geral (TUGs) pela área privativa média da unidade (NBR 5410)
    fator_area = max(0.88, min(1.35, 0.82 + (area_media_apto / 135.0)))
    carga_inst_apto_kva = round(float(perfil["carga_base_kva"]) * fator_area, 2)
    demanda_indiv_apto_kva = round(float(perfil["demanda_indiv_base_kva"]) * fator_area, 2)

    # Fator de diversidade coletivo pelo número de apartamentos (Agrupamento Enel SP)
    fator_div = _fator_diversidade_coletivo(uh_res_calc)
    demanda_media_apto_kva = round(demanda_indiv_apto_kva * fator_div, 2)
    demanda_media_apto_kw = round(demanda_media_apto_kva * 0.92, 2)  # Fator de potência médio 0,92
    # Corrente equivalente por apartamento no barramento trifásico 220V (I = S / (sqrt(3)*0.220)) e bifásico (S / 0.220)
    corrente_media_apto_a = round((demanda_media_apto_kva * 1000.0) / 220.0, 1)

    demanda_apartamentos_kva = round(uh_res * demanda_media_apto_kva, 2)

    # 2. Demanda do Condomínio (Elevadores + Bombas + Iluminação/Ventilação Áreas Comuns)
    dem_elevadores = max(1, int(num_elevadores)) * 12.0 * 0.80
    dem_bombas = 9.5  # Recalque água potável + reúso + drenagem
    dem_areas_comuns = max(6.0, quadro.area_nao_computavel_m2 * 0.012)
    demanda_condominio_kva = round(dem_elevadores + dem_bombas + dem_areas_comuns, 2)

    # 3. Demanda de Lojas / Fachada Ativa (NR1-3 e NR1-12)
    area_lojas = sub_a.get("nc_nr1_3_fa", 0.0) + sub_a.get("nc_nr1_12", 0.0)
    demanda_lojas_kva = round(area_lojas * 0.075, 2)

    # 4. Demanda de Recarga de Veículos Elétricos (Wallbox 7,4 kVA com fator de simultaneidade 0,40)
    demanda_ve_kva = round(max(0, int(vagas_recarga_ve)) * 7.4 * 0.40, 2)

    demanda_total_kva = round(
        demanda_apartamentos_kva + demanda_condominio_kva + demanda_lojas_kva + demanda_ve_kva,
        2,
    )

    # 5. Diagnóstico de Subestação / Posto de Transformação (Concessionária Enel SP)
    trafo_kva, config_se, area_se_m2 = _selecionar_transformador_comercial(demanda_total_kva)
    if demanda_total_kva <= 75.0:
        precisa_se = False
        faixa_atend = "Até 75 kVA — Atendimento Direto em Baixa Tensão (BT)"
        classif_se = "NÃO PRECISA DE SUBESTAÇÃO (Ligação Direta na Rede BT 220/127 V da Concessionária)"
        tensao_forn = "Baixa Tensão (BT — 220/127 V Trifásico)"
    elif demanda_total_kva <= 225.0:
        precisa_se = True
        faixa_atend = "Acima de 75 kVA até 225 kVA — Exige Posto de Transformação / Subestação"
        classif_se = f"SIM — PRECISA DE SUBESTAÇÃO / POSTO DE TRANSFORMAÇÃO ({trafo_kva:g} kVA)"
        tensao_forn = "Média Tensão Primaria 13,8 kV → Secundário 220/127 V"
    else:
        precisa_se = True
        faixa_atend = "Acima de 225 kVA — Subestação / Cabine Primária Obrigatória em Média Tensão"
        classif_se = f"SIM — PRECISA DE SUBESTAÇÃO / CABINE PRIMÁRIA DEDICADA ({trafo_kva:g} kVA)"
        tensao_forn = "Média Tensão Primaria 13,8 kV → Secundário 220/127 V"

    # 6. Grupo Gerador de Emergência (atende Elevador de Segurança + Bombas + Iluminação/Portaria)
    gerador_kva = 0.0
    if incluir_gerador_emergencia:
        dem_emerg = (12.0 + dem_bombas + max(5.0, dem_areas_comuns * 0.55)) * 1.25
        for g_std in [40.0, 55.0, 75.0, 100.0, 115.0, 150.0, 180.0]:
            if g_std >= dem_emerg:
                gerador_kva = g_std
                break
        if gerador_kva == 0.0:
            gerador_kva = 180.0

    # 7. Estimativa de Custos da Parte Elétrica
    # 7.1 Padrão de Entrada + Subestação / Posto de Transformação
    if not precisa_se:
        custo_entrada_se = 48000.0
        desc_se = "Padrão de Entrada Coletivo em Baixa Tensão (Ramal Subterrâneo, QGBT e Proteção)"
    elif (trafo_kva or 0) <= 150.0:
        custo_entrada_se = 165000.0
        desc_se = f"Posto de Transformação {trafo_kva:g} kVA (Trafo, Proteção MT/BT, Obra Civil e Interligação Enel)"
    elif (trafo_kva or 0) <= 225.0:
        custo_entrada_se = 215000.0
        desc_se = f"Posto de Transformação / Cabine {trafo_kva:g} kVA (Trafo a Seco, Cubículo MT, Malha e Obra Civil)"
    elif (trafo_kva or 0) <= 300.0:
        custo_entrada_se = 275000.0
        desc_se = f"Subestação Abrigada {trafo_kva:g} kVA (Cubículos 13,8 kV, Trafo a Seco, Proteção Relé Cabine)"
    else:
        custo_entrada_se = 350000.0 + max(0.0, ((trafo_kva or 500.0) - 500.0) * 320.0)
        desc_se = f"Subestação de Grande Porte {trafo_kva:g} kVA (Cubículos MT, Trafo a Seco e Automação)"

    # 7.2 Centros de Medição (QMs), Prumadas / Barramento Blindado e Quadros de Condomínio
    custo_medicao_prumadas = round((uh_res_calc * 2350.0) + (len(quadro.pavimentos) * 4200.0), 2)

    # 7.3 Instalações Elétricas Internas dos Apartamentos (QDC, Eletrodutos, Fiação, Tomadas/Interruptores)
    fator_perfil_custo = 1.12 if perfil_chave == "PADRAO_100_ELETRICO" else (0.95 if perfil_chave == "PADRAO_GAS_SPLIT" else 1.00)
    custo_unidades_interna = round(area_priv_res * (custo_base_instalacao_m2_rs * 0.72) * fator_perfil_custo, 2)

    # 7.4 Áreas Comuns, Iluminação LED, Telecom/Interfonia/CFTV, SPDA (Para-Raios NBR 5419) e Bombas
    custo_comum_spda = round(
        (quadro.area_nao_computavel_m2 * (custo_base_instalacao_m2_rs * 0.65))
        + (len(quadro.pavimentos) * 3800.0)
        + (max(0, int(vagas_recarga_ve)) * 6500.0),
        2,
    )

    # 7.5 Grupo Gerador de Emergência Carenado / Acústico + QTA
    custo_gerador = round((62000.0 + gerador_kva * 820.0) if incluir_gerador_emergencia else 0.0, 2)

    custo_total_el = round(
        custo_entrada_se + custo_medicao_prumadas + custo_unidades_interna + custo_comum_spda + custo_gerador,
        2,
    )
    custo_por_uh = round(custo_total_el / uh_res_calc, 2)
    custo_por_m2 = round(custo_total_el / max(1.0, quadro.area_construida_m2), 2)

    def _mk_item(nome: str, esp: str, val: float) -> ItemCustoEletrica:
        return ItemCustoEletrica(
            item=nome,
            especificacao=esp,
            valor_rs=round(val, 2),
            custo_por_uh_rs=round(val / uh_res_calc, 2),
            participacao_pct=round((val / custo_total_el) * 100.0, 1) if custo_total_el > 0 else 0.0,
        )

    itens_custo = [
        _mk_item("1. Entrada de Energia e Subestação", desc_se, custo_entrada_se),
        _mk_item(
            "2. Centros de Medição (QMs) e Prumadas",
            f"Agrupamento de {uh_res_calc} medidores Enel + prumadas elétricas ({len(quadro.pavimentos)} níveis)",
            custo_medicao_prumadas,
        ),
        _mk_item(
            "3. Elétrica Privativa dos Apartamentos",
            f"{uh_res_calc} unidades ({area_priv_res:,.1f} m² priv.) — QDCs, cabos, pontos e acabamentos",
            custo_unidades_interna,
        ),
        _mk_item(
            "4. Condomínio, Iluminação LED, Telecom e SPDA",
            f"Áreas comuns ({quadro.area_nao_computavel_m2:,.1f} m²), SPDA NBR 5419, CFTV/Interfonia e {vagas_recarga_ve} ponto(s) VE",
            custo_comum_spda,
        ),
    ]
    if incluir_gerador_emergencia:
        itens_custo.append(
            _mk_item(
                "5. Grupo Gerador de Emergência + QTA",
                f"Gerador acústico {gerador_kva:g} kVA com Quadro de Transferência Automática (Elevador/Bombas/Comum)",
                custo_gerador,
            )
        )

    alertas: List[str] = []
    if precisa_se:
        alertas.append(
            f"Como a demanda total calculada ({demanda_total_kva:.1f} kVA) ultrapassa o limite de 75 kVA de Baixa Tensão da concessionária, "
            f"o empreendimento PRECISA DE SUBESTAÇÃO / POSTO DE TRANSFORMAÇÃO ({trafo_kva:g} kVA). "
            f"Reserve aproximadamente {area_se_m2:.0f} m² no Térreo/Recuo frontal com acesso técnico para a concessionária."
        )
    else:
        alertas.append(
            f"A demanda total calculada ({demanda_total_kva:.1f} kVA) está dentro do limite de 75 kVA. "
            "O atendimento pode ser feito diretamente em Baixa Tensão (220/127 V), sem necessidade de subestação própria."
        )

    return ResultadoPreviaEletrica(
        padrao_eletrodomesticos=str(perfil["nome"]),
        total_unidades_residenciais=uh_res,
        area_media_apto_m2=area_media_apto,
        carga_instalada_por_apto_kva=carga_inst_apto_kva,
        fator_diversidade_aplicado=fator_div,
        demanda_media_por_apto_kva=demanda_media_apto_kva,
        demanda_media_por_apto_kw=demanda_media_apto_kw,
        corrente_media_por_apto_220v_a=corrente_media_apto_a,
        disjuntor_padrao_apto_in_a=int(perfil["disjuntor_a"]),
        tipo_fornecimento_apto=str(perfil["fornecimento"]),
        demanda_apartamentos_kva=demanda_apartamentos_kva,
        demanda_condominio_kva=demanda_condominio_kva,
        demanda_lojas_kva=demanda_lojas_kva,
        demanda_recarga_ve_kva=demanda_ve_kva,
        demanda_total_edificio_kva=demanda_total_kva,
        precisa_subestacao=precisa_se,
        faixa_atendimento=faixa_atend,
        classificacao_subestacao=classif_se,
        tensao_fornecimento=tensao_forn,
        transformador_recomendado_kva=trafo_kva,
        configuracao_subestacao=config_se,
        area_tecnica_subestacao_m2=area_se_m2,
        gerador_emergencia_kva=gerador_kva,
        itens_custo_eletrica=itens_custo,
        custo_entrada_subestacao_rs=round(custo_entrada_se, 2),
        custo_total_eletrica_rs=custo_total_el,
        custo_eletrica_por_uh_rs=custo_por_uh,
        custo_eletrica_por_m2_rs=custo_por_m2,
        alertas=alertas,
    )

