"""
Motor de Cálculo das Etapas 6, 7 e 8:
- Etapa 6: Quadro de Áreas por pavimento (`Q. ÁREAS!A3:AF33`) e Balanço `Área Máx. × Projeto × Sobra` (`S44:W54`)
- Etapa 7: Quadro de Uso e Ocupação do Solo (`Q. LUOPS`)
- Etapa 8: Anexos (`Q. ANEXOS`: Reservatório de Reúso, Reservatório de Retardo, Acessibilidade, Vagas e Uso Incentivado)
"""

import math
from typing import Dict, List, Optional

from domain.viabilidade_models import (
    COLUNAS_COMPUTAVEIS,
    COLUNAS_NAO_COMPUTAVEIS,
    COLUNAS_UNIDADES,
    TODAS_COLUNAS_AREA,
    TODAS_COLUNAS_UNIDADE,
    IndicesLegais,
    LinhaLimite,
    LinhaQuadro,
    Pavimento,
    QuadroAreas,
    ResultadoAnexos,
)


def gerar_pavimentos_padrao(
    cota_terreno_m: float = 784.40,
    qtd_pavimentos_tipo: int = 18,
    incluir_atico: bool = True,
) -> List[Pavimento]:
    """
    Cria a lista de pavimentos com os pés-direitos idênticos aos da planilha:
    - Térreo -> 1º Pav: +2,85 m
    - 1º Pav -> 2º Pav: +2,85 m
    - 2º Pav -> 3º Pav: +3,50 m
    - 3º ao 18º Pav: +2,72 m por pavimento
    - 18º Pav -> Ático: +2,92 m
    """
    pavs: List[Pavimento] = []
    cota_atual = float(cota_terreno_m or 784.40)

    # Térreo
    pavs.append(
        Pavimento(
            nome="Térreo",
            pe_direito_m=2.85,
            tipo="terreo",
            unidades={c: 0.0 for c in TODAS_COLUNAS_UNIDADE},
            areas={c: 0.0 for c in TODAS_COLUNAS_AREA},
            cota_m=round(cota_atual, 2),
        )
    )
    cota_atual += 2.85

    for i in range(1, qtd_pavimentos_tipo + 1):
        if i == 1:
            pd_m = 2.85
        elif i == 2:
            pd_m = 3.50
        elif i == qtd_pavimentos_tipo:
            pd_m = 2.92
        else:
            pd_m = 2.72

        pavs.append(
            Pavimento(
                nome=f"{i}º Pavimento",
                pe_direito_m=pd_m,
                tipo="tipo",
                unidades={c: 0.0 for c in TODAS_COLUNAS_UNIDADE},
                areas={c: 0.0 for c in TODAS_COLUNAS_AREA},
                cota_m=round(cota_atual, 2),
            )
        )
        cota_atual += pd_m

    if incluir_atico:
        pavs.append(
            Pavimento(
                nome="Ático",
                pe_direito_m=2.30,
                tipo="atico",
                unidades={c: 0.0 for c in TODAS_COLUNAS_UNIDADE},
                areas={c: 0.0 for c in TODAS_COLUNAS_AREA},
                cota_m=round(cota_atual, 2),
            )
        )

    return pavs


def distribuir_areas_automaticas_por_terreno(
    indices: IndicesLegais,
    cota_terreno_m: float = 784.40,
    qtd_pav_tipo: int = 9,
    area_media_his2_m2: float = 25.0,
    area_media_r2v1_m2: float = 25.0,
    incluir_fachada_ativa: Optional[bool] = None,
    area_fachada_ativa_m2: Optional[float] = None,
    qtd_lojas_fa: int = 1,
) -> List[Pavimento]:
    """
    Pré-preenche o Quadro de Áreas automaticamente a partir do potencial construtivo do terreno
    extraído do GeoSampa, distribuindo 80% HIS-2 (ou 60% em EZEIS) e 20% R2V-1 nos pavimentos-tipo,
    além de áreas comuns no Térreo e Ático. O usuário pode editar qualquer célula depois.
    """
    pavs = gerar_pavimentos_padrao(cota_terreno_m=cota_terreno_m, qtd_pavimentos_tipo=qtd_pav_tipo, incluir_atico=True)
    if indices.gabarito_m is not None and len(pavs) > 1:
        altura_total = round(pavs[-1].cota_m - pavs[0].cota_m, 2)
        if altura_total > indices.gabarito_m:
            # Ajusta pés-direitos dos pavimentos-tipo para 2,72 m para respeitar o gabarito da zona (ex.: 28,0 m em ZM com T+9+Ático = 27,46 m)
            cota_acum = float(cota_terreno_m or 784.40)
            for idx, p in enumerate(pavs):
                p.cota_m = round(cota_acum, 2)
                if idx >= 2 and p.tipo == "tipo":
                    p.pe_direito_m = 2.72
                cota_acum += p.pe_direito_m
    area_comp_disp = float(indices.area_comp_projeto_m2 or (indices.area_terreno_m2 * 2.5))
    prop_his = indices.proporcao_his

    n_tipo = max(1, qtd_pav_tipo)
    comp_por_pav = area_comp_disp / n_tipo
    area_his2_pav = round(comp_por_pav * prop_his * 0.88, 2)
    area_r2v1_pav = round(comp_por_pav * (1.0 - prop_his) * 0.88, 2)
    circ_comp_pav = round(comp_por_pav * 0.12, 2)
    circ_nc_pav = round(comp_por_pav * 0.18, 2)
    terraco_nc_pav = round((indices.area_terreno_m2 * 0.05), 2)

    uh_his2_pav = max(1, int(round(area_his2_pav / max(area_media_his2_m2, 15.0))))
    uh_r2v1_pav = max(0, int(round(area_r2v1_pav / max(area_media_r2v1_m2, 15.0))))

    usar_fa = (indices.fachada_ativa_pct >= 0.5) if incluir_fachada_ativa is None else bool(incluir_fachada_ativa)

    for p in pavs:
        if p.tipo == "terreo":
            total_uh_est = (uh_his2_pav + uh_r2v1_pav) * n_tipo
            p.areas["nc_ecc"] = round(total_uh_est * 0.5, 2)
            p.areas["nc_circ"] = round(indices.area_terreno_m2 * 0.12, 2)
            if usar_fa:
                p.unidades["u_nr1_3"] = float(max(1, int(qtd_lojas_fa)))
                area_fa_padrao = round(indices.area_terreno_m2 * min(0.15, max(0.10, indices.fachada_ativa_pct)), 2)
                p.areas["nc_nr1_3_fa"] = round(
                    float(area_fachada_ativa_m2) if area_fachada_ativa_m2 is not None else area_fa_padrao,
                    2,
                )
            else:
                p.unidades["u_nr1_3"] = 0.0
                p.areas["nc_nr1_3_fa"] = 0.0
        elif p.tipo == "tipo":
            p.unidades["u_his2"] = float(uh_his2_pav)
            p.unidades["u_r2v1"] = float(uh_r2v1_pav)
            p.areas["c_his2"] = area_his2_pav
            p.areas["c_r2v1"] = area_r2v1_pav
            p.areas["c_circ"] = circ_comp_pav
            p.areas["nc_circ"] = circ_nc_pav
            p.areas["nc_terraco"] = terraco_nc_pav
        elif p.tipo == "atico":
            p.areas["nc_at"] = round(indices.area_terreno_m2 * 0.08, 2)
            p.areas["nc_circ"] = round(indices.area_terreno_m2 * 0.04, 2)

    return pavs


def calcular_quadro_areas(
    pavimentos: List[Pavimento],
    indices: IndicesLegais,
    cota_terreno_m: Optional[float] = None,
    area_permeavel_projetada_m2: Optional[float] = None,
    area_lazer_descoberto_m2: Optional[float] = None,
) -> QuadroAreas:
    """
    ETAPA 6: Calcula o Quadro de Áreas completo (`Q. ÁREAS!A3:AF33`) e o quadro de limites
    (`S44:W54` — Área Máx. × Projeto × Sobra).
    """
    cota_base = cota_terreno_m if cota_terreno_m is not None else (pavimentos[0].cota_m if pavimentos else 784.40)
    cota_acum = float(cota_base)

    sub_unidades: Dict[str, float] = {c: 0.0 for c in TODAS_COLUNAS_UNIDADE}
    sub_areas: Dict[str, float] = {c: 0.0 for c in TODAS_COLUNAS_AREA}
    totais_pav: List[float] = []
    pct_circ_pav: List[Optional[float]] = []

    total_unidades_todos = 0.0
    total_unidades_planilha = 0.0  # C5 = D5 + F5 + G5 + K5

    for p in pavimentos:
        p.cota_m = round(cota_acum, 2)
        cota_acum += float(p.pe_direito_m or 0.0)

        for col_u in TODAS_COLUNAS_UNIDADE:
            val_u = float(p.unidades.get(col_u, 0.0) or 0.0)
            p.unidades[col_u] = val_u
            sub_unidades[col_u] = round(sub_unidades[col_u] + val_u, 2)
            total_unidades_todos += val_u

        # Na planilha original: C5 = D5 + F5 + G5 + K5
        total_unidades_planilha += (
            p.unidades.get("u_his2", 0.0)
            + p.unidades.get("u_r2v1", 0.0)
            + p.unidades.get("u_his2_cota", 0.0)
            + p.unidades.get("u_nr1_3", 0.0)
        )

        soma_linha_area = 0.0
        for col_a in TODAS_COLUNAS_AREA:
            val_a = round(float(p.areas.get(col_a, 0.0) or 0.0), 2)
            p.areas[col_a] = val_a
            sub_areas[col_a] = round(sub_areas[col_a] + val_a, 2)
            soma_linha_area += val_a

        totais_pav.append(round(soma_linha_area, 2))
        r_circ = p.areas.get("nc_circ", 0.0)
        pct_circ_pav.append(round((r_circ / soma_linha_area) * 100.0, 2) if soma_linha_area > 0 else None)

    # L26 = L25 + M25 + N25 + O25 + P25 + Q25 (Total Computável)
    cols_comp = [c for c, _ in COLUNAS_COMPUTAVEIS]
    cols_ncomp = [c for c, _ in COLUNAS_NAO_COMPUTAVEIS]
    area_computavel = round(sum(sub_areas[c] for c in cols_comp), 2)
    area_nao_computavel = round(sum(sub_areas[c] for c in cols_ncomp), 2)
    area_construida = round(area_computavel + area_nao_computavel, 2)  # C27 = L26 + R26

    # Verificação cruzada soma das linhas vs soma das colunas (AE32)
    soma_totais_pav = round(sum(totais_pav), 2)
    verificacao_soma = round(soma_totais_pav - area_construida, 4)

    # E63 = L31+M31+O31+P31+S31+Y31+AA31+AB31 (+ N31 Terraço HIS-2)
    area_privativa = round(
        sub_areas["c_his2"]
        + sub_areas["c_his1"]
        + sub_areas["c_terraco_his2"]
        + sub_areas["c_r2v1"]
        + sub_areas["c_terraco_r2v1"]
        + sub_areas["nc_terraco"]
        + sub_areas["nc_his2_cota"]
        + sub_areas["nc_his1_50"]
        + sub_areas["nc_r2v1_10"]
        + sub_areas["nc_nr1_12"],
        2,
    )
    area_loja = round(sub_areas["nc_nr1_3_fa"], 2)  # E64 = AD25
    eficiencia = (
        round(((area_privativa + area_loja) / area_construida) * 100.0, 2)
        if area_construida > 0
        else None
    )

    # L28 e O28: Percentual dos usos computáveis EHIS = (HIS-2 + HIS-1) / (HIS-2 + HIS-1 + R2V-1)
    base_ehis = sub_areas["c_his2"] + sub_areas["c_his1"] + sub_areas["c_r2v1"]
    if base_ehis > 0:
        pct_his = round(((sub_areas["c_his2"] + sub_areas["c_his1"]) / base_ehis) * 100.0, 2)
        pct_r2v = round((sub_areas["c_r2v1"] / base_ehis) * 100.0, 2)
        atende_ehis = pct_his >= (indices.proporcao_his * 100.0 - 0.01)
    else:
        pct_his = None
        pct_r2v = None
        atende_ehis = None

    # Gabarito projetado (E51 = cota do último pavimento - cota do térreo)
    cota_terreo = pavimentos[0].cota_m if pavimentos else cota_base
    cota_topo = max((p.cota_m for p in pavimentos), default=cota_terreo)
    altura_edif = round(max(0.0, cota_topo - cota_terreo), 2)
    atende_gabarito = (altura_edif <= indices.gabarito_m) if indices.gabarito_m is not None else True

    # Quadro Projeto — Balanço Área Máx. × Projeto × Sobra (T46:W54)
    w36 = indices.area_terreno_m2
    w37 = round(w36 * 0.05, 2)  # Terraço / pav. = 5% da área do terreno
    w42 = len(pavimentos)
    u46 = round(
        sub_areas["c_his2"]
        + sub_areas["c_his1"]
        + sub_areas["c_r2v1"]
        + sub_areas["c_terraco_r2v1"]
        + sub_areas["c_circ"]
        + sub_areas["c_terraco_his2"],
        2,
    )
    t46 = round(w36 * (indices.ca_projeto or 1.0), 2)

    uh_his_ecc = (
        sub_unidades["u_his2"]
        + sub_unidades["u_his1"]
        + sub_unidades["u_his2_cota"]
        + sub_unidades["u_his1_50"]
    )
    uh_his_lazer = sub_unidades["u_his2"] + sub_unidades["u_his1"] + sub_unidades["u_his2_cota"]

    exig_perm = round(w36 * (indices.tp_min or 0.0), 2)
    proj_perm = round(
        area_permeavel_projetada_m2 if area_permeavel_projetada_m2 is not None else exig_perm, 2
    )
    exig_ecc = round(uh_his_ecc * 0.5, 2)
    proj_ecc = round(sub_areas["nc_ecc"], 2)
    exig_lazer = round(uh_his_lazer * 2.0, 2)
    proj_lazer = round(
        area_lazer_descoberto_m2 if area_lazer_descoberto_m2 is not None else exig_lazer, 2
    )

    limites: List[LinhaLimite] = [
        LinhaLimite(
            item="COMP. (Área Computável)",
            maximo=t46,
            projeto=u46,
            sobra=round(t46 - u46, 2),
            atende=u46 <= t46 + 0.01,
            referencia=f"CA {indices.ca_projeto or 1.0:.2f} × Área Terreno",
            sentido="max",
        ),
        LinhaLimite(
            item="HIS-2 (Cota Solidariedade)",
            maximo=round(u46 * 0.10, 2),
            projeto=sub_areas["nc_his2_cota"],
            sobra=round(u46 * 0.10 - sub_areas["nc_his2_cota"], 2),
            atende=sub_areas["nc_his2_cota"] <= u46 * 0.10 + 0.01,
            referencia="PDE, art. 112 §8º (10% comp.)",
            sentido="max",
        ),
        LinhaLimite(
            item="NR1-12 (Não Residencial)",
            maximo=round(sub_areas["c_his2"] * 0.20, 2),
            projeto=sub_areas["nc_nr1_12"],
            sobra=round(sub_areas["c_his2"] * 0.20 - sub_areas["nc_nr1_12"], 2),
            atende=sub_areas["nc_nr1_12"] <= sub_areas["c_his2"] * 0.20 + 0.01,
            referencia="20% de HIS-2 computável",
            sentido="max",
        ),
        LinhaLimite(
            item="NR1-3 (Fachada Ativa)",
            maximo=round(w36 * indices.fachada_ativa_pct, 2),
            projeto=sub_areas["nc_nr1_3_fa"],
            sobra=round(w36 * indices.fachada_ativa_pct - sub_areas["nc_nr1_3_fa"], 2),
            atende=sub_areas["nc_nr1_3_fa"] <= w36 * indices.fachada_ativa_pct + 0.01,
            referencia=f"Decreto HIS, art. 13 ({indices.fachada_ativa_pct * 100:.0f}% terreno)",
            sentido="max",
        ),
        LinhaLimite(
            item="R2V-1 (10% incentivo)",
            maximo=round(u46 * 0.10, 2),
            projeto=sub_areas["nc_r2v1_10"],
            sobra=round(u46 * 0.10 - sub_areas["nc_r2v1_10"], 2),
            atende=sub_areas["nc_r2v1_10"] <= u46 * 0.10 + 0.01,
            referencia="10% da área computável",
            sentido="max",
        ),
        LinhaLimite(
            item="TERRAÇO",
            maximo=round(w37 * w42, 2),
            projeto=round(sub_areas["nc_terraco"] + sub_areas["c_terraco_r2v1"], 2),
            sobra=round(w37 * w42 - (sub_areas["nc_terraco"] + sub_areas["c_terraco_r2v1"]), 2),
            atende=(sub_areas["nc_terraco"] + sub_areas["c_terraco_r2v1"]) <= w37 * w42 + 0.01,
            referencia="LPUOS, art. 62 (5% terreno/pav.)",
            sentido="max",
        ),
        LinhaLimite(
            item="PERMEÁVEL",
            maximo=exig_perm,
            projeto=proj_perm,
            sobra=round(proj_perm - exig_perm, 2),
            atende=proj_perm >= exig_perm - 0.01,
            referencia=f"Quadro 4 ({indices.pa}) / LPUOS art. 81",
            sentido="min",
        ),
        LinhaLimite(
            item="E.C.C. (Espaço Coberto Comum)",
            maximo=exig_ecc,
            projeto=proj_ecc,
            sobra=round(proj_ecc - exig_ecc, 2),
            atende=proj_ecc >= exig_ecc - 0.01,
            referencia="Decreto HIS, art. 18 (0,50 m²/UH HIS)",
            sentido="min",
        ),
        LinhaLimite(
            item="LAZER DESCOBERTO",
            maximo=exig_lazer,
            projeto=proj_lazer,
            sobra=round(proj_lazer - exig_lazer, 2),
            atende=proj_lazer >= exig_lazer - 0.01,
            referencia="Decreto HIS, art. 18 (2,00 m²/UH HIS)",
            sentido="min",
        ),
    ]

    alertas: List[str] = []
    if atende_ehis is False:
        alertas.append(
            f"Proporção EHIS ({pct_his:.1f}% HIS / {pct_r2v:.1f}% R2V) abaixo do mínimo exigido de {indices.proporcao_his * 100:.0f}% HIS."
        )
    if atende_gabarito is False and indices.gabarito_m is not None:
        alertas.append(
            f"Gabarito projetado ({altura_edif:.2f} m) ultrapassa o gabarito máximo da zona ({indices.gabarito_m:.2f} m)."
        )

    return QuadroAreas(
        pavimentos=pavimentos,
        subtotal_unidades=sub_unidades,
        subtotal_areas=sub_areas,
        total_unidades=round(total_unidades_todos, 2),
        total_unidades_planilha=round(total_unidades_planilha, 2),
        area_computavel_m2=area_computavel,
        area_nao_computavel_m2=area_nao_computavel,
        area_construida_m2=area_construida,
        area_privativa_m2=area_privativa,
        area_loja_m2=area_loja,
        eficiencia=eficiencia,
        pct_his=pct_his,
        pct_r2v=pct_r2v,
        atende_proporcao_ehis=atende_ehis,
        altura_edificacao_m=altura_edif,
        atende_gabarito=atende_gabarito,
        limites=limites,
        total_por_pavimento=totais_pav,
        pct_circ_por_pavimento=pct_circ_pav,
        verificacao_soma=verificacao_soma,
        alertas=alertas,
    )


def calcular_quadro_luops(
    indices: IndicesLegais,
    quadro_areas: QuadroAreas,
    area_ocupacao_utilizada_m2: Optional[float] = None,
    area_permeavel_utilizada_m2: Optional[float] = None,
    area_lazer_descoberto_m2: Optional[float] = None,
    ecc_1_pav_m2: float = 0.0,
) -> List[LinhaQuadro]:
    """
    ETAPA 7: Monta o Quadro de Uso e Ocupação do Solo (`Q. LUOPS!A1:G40`) conectado
    aos resultados de `IndicesLegais` e `QuadroAreas`.
    """
    e2 = indices.area_terreno_m2
    e3 = indices.to_max or 0.0
    e5 = round(e2 * e3, 2)
    # E6 = 'Q. ÁREAS'!AE5 (área do térreo) ou projeção informada
    area_terreo = quadro_areas.total_por_pavimento[0] if quadro_areas.total_por_pavimento else 0.0
    e6 = round(area_ocupacao_utilizada_m2 if area_ocupacao_utilizada_m2 is not None else area_terreo, 2)
    e4 = round(e6 / e2, 4) if e2 > 0 else 0.0

    e7 = indices.tp_min or 0.0
    e9 = round(e2 * e7, 2)
    e10 = round(area_permeavel_utilizada_m2 if area_permeavel_utilizada_m2 is not None else e9, 2)
    e8 = round(e10 / e2, 4) if e2 > 0 else 0.0

    e11 = indices.ca_basico or 1.0
    e12 = indices.ca_maximo_lpuos or 2.0
    e13 = indices.ca_majorado or indices.ca_projeto or 3.6
    e15 = round(e2 * (indices.ca_projeto or 1.0), 2)
    e16 = quadro_areas.area_computavel_m2
    e14 = round(e16 / e2, 4) if e2 > 0 else 0.0

    e19 = quadro_areas.area_construida_m2
    e17 = round(e19 * 0.59, 2)
    e18 = quadro_areas.area_nao_computavel_m2

    e20 = round(e2 * indices.fachada_ativa_pct, 2)
    e21 = round(quadro_areas.subtotal_areas.get("nc_nr1_3_fa", 0.0), 2)

    sub_u = quadro_areas.subtotal_unidades
    uh_his2 = sub_u.get("u_his2", 0.0) + sub_u.get("u_his2_cota", 0.0)
    uh_r2v1 = sub_u.get("u_r2v1", 0.0) + sub_u.get("u_r2v1_10", 0.0)
    uh_his1 = sub_u.get("u_his1", 0.0) + sub_u.get("u_his1_50", 0.0)
    uh_nr1_12 = sub_u.get("u_nr1_12", 0.0)
    uh_nr1_3 = sub_u.get("u_nr1_3", 0.0)
    uh_total = uh_his2 + uh_r2v1 + uh_his1 + uh_nr1_12 + uh_nr1_3
    uh_residenciais = uh_his2 + uh_r2v1 + uh_his1

    ecc_exig = round((uh_his2 + uh_his1) * 0.5, 2)
    ecc_proj = round(quadro_areas.subtotal_areas.get("nc_ecc", 0.0), 2)
    lazer_exig = round((uh_his2 + uh_his1) * 2.0, 2)
    lazer_proj = round(area_lazer_descoberto_m2 if area_lazer_descoberto_m2 is not None else lazer_exig, 2)

    linhas: List[LinhaQuadro] = [
        LinhaQuadro("TERRENO", "Área do terreno (E = R)", e2, "m²", "Remanescente após doação, se houver"),
        LinhaQuadro("OCUPAÇÃO", "Taxa de Ocupação Máxima", round(e3 * 100, 2), "%", f"Quadro 2 ({indices.zona})"),
        LinhaQuadro("OCUPAÇÃO", "Taxa de Ocupação Utilizada", round(e4 * 100, 2), "%", "Área ocupada / Área do terreno"),
        LinhaQuadro("OCUPAÇÃO", "Área de Ocupação Máxima", e5, "m²", ""),
        LinhaQuadro("OCUPAÇÃO", "Área de Ocupação Utilizada", e6, "m²", "Projeção implantada no térreo"),
        LinhaQuadro("PERMEABILIDADE", "Taxa de Permeabilidade Exigida", round(e7 * 100, 2), "%", f"Quadro 4 ({indices.pa})"),
        LinhaQuadro("PERMEABILIDADE", "Taxa de Permeabilidade Utilizada", round(e8 * 100, 2), "%", ""),
        LinhaQuadro("PERMEABILIDADE", "Área Permeável Mínima Exigida", e9, "m²", ""),
        LinhaQuadro("PERMEABILIDADE", "Área Permeável Utilizada", e10, "m²", ""),
        LinhaQuadro("C.A.", "C.A. Básico", e11, "", ""),
        LinhaQuadro("C.A.", "C.A. Máximo (LPUOS)", e12, "", ""),
        LinhaQuadro("C.A.", "C.A. Majorado (Decreto HIS / Cota +20%)", e13, "", ""),
        LinhaQuadro("C.A.", "C.A. Utilizado no Projeto", e14, "", "Área computável / Área do terreno"),
        LinhaQuadro("ÁREAS", "Área Computável Máxima", e15, "m²", ""),
        LinhaQuadro("ÁREAS", "Área Computável Utilizada", e16, "m²", ""),
        LinhaQuadro("ÁREAS", "Área Não Computável Máxima (59%)", e17, "m²", "59% da área construída total"),
        LinhaQuadro("ÁREAS", "Área Não Computável Utilizada", e18, "m²", ""),
        LinhaQuadro("ÁREAS", "Área Construída Total", e19, "m²", ""),
        LinhaQuadro(
            "FACHADA ATIVA",
            f"Permitida ({indices.fachada_ativa_pct * 100:.0f}% da área do terreno)",
            e20,
            "m²",
            "Decreto 63.728/24 (50% em ZEU/ZEM/ZEMP/ZC; 20% nas demais)",
        ),
        LinhaQuadro("FACHADA ATIVA", "Projetada", e21, "m²", ""),
    ]

    if indices.cota_parte_m2:
        q = indices.cota_parte_m2
        n_calc = (e14 * e2) / (e13 * q) if (e13 * q) > 0 else 0.0
        n_min = float(math.ceil(n_calc)) if n_calc > 0 else 0.0
        linhas.extend(
            [
                LinhaQuadro("COTA PARTE", "Cota-parte máxima (Art. 79 Lei 16.050/14)", q, "m²/unid.", f"Aplicável em {indices.zona}"),
                LinhaQuadro("COTA PARTE", "N = (CAu × At) / (CAmáx × Q)", round(n_calc, 2), "unid.", ""),
                LinhaQuadro("COTA PARTE", "Número mínimo de unidades exigido", n_min, "unid.", "ROUNDUP(N, 0)"),
            ]
        )

    linhas.extend(
        [
            LinhaQuadro("UNIDADES", "Categoria HIS-2", uh_his2, "uh", ""),
            LinhaQuadro("UNIDADES", "Categoria R2V-1", uh_r2v1, "uh", ""),
            LinhaQuadro("UNIDADES", "(HIS-1) Habitação de Interesse Social", uh_his1, "unid.", ""),
            LinhaQuadro("UNIDADES", "(NR1-12) Não-Residencial", uh_nr1_12, "unid.", ""),
            LinhaQuadro("UNIDADES", "(NR1-3) Fachada Ativa", uh_nr1_3, "unid.", ""),
            LinhaQuadro("UNIDADES", "Quantidade Total de Unidades", uh_total, "uh", ""),
            LinhaQuadro("ÁREAS COMUNS", "Espaço Coberto Comum Exigido (0,50 m²/unid. HIS)", ecc_exig, "m²", "Decreto 63.728/24"),
            LinhaQuadro("ÁREAS COMUNS", "Espaço Coberto Comum Projetado", ecc_proj, "m²", ""),
            LinhaQuadro("ÁREAS COMUNS", "Lazer Descoberto Exigido (2,00 m²/unid. HIS)", lazer_exig, "m²", "Decreto 63.728/24"),
            LinhaQuadro("ÁREAS COMUNS", "Lazer Descoberto Projetado", lazer_proj, "m²", ""),
            LinhaQuadro(
                "COE Art. 108",
                "E.C.C. Máximo fora do térreo (3,00 m²/unid. residencial)",
                round(3.0 * uh_residenciais, 2),
                "m²",
                f"3,00 m² × {int(uh_residenciais)} UH residenciais",
            ),
            LinhaQuadro("COE Art. 108", "Total E.C.C. projetado fora do térreo", round(ecc_1_pav_m2, 2), "m²", ""),
        ]
    )
    return linhas


def calcular_anexos(
    indices: IndicesLegais,
    quadro_areas: QuadroAreas,
    area_cobertura_impermeavel_m2: Optional[float] = None,
    area_cobertura_verde_m2: float = 0.0,
    fator_cobertura_verde: float = 6.30,
    vagas_automoveis_livres: int = 0,
) -> ResultadoAnexos:
    """
    ETAPA 8: Calcula os quadros da aba `Q. ANEXOS`:
    - Reservatório de Reúso (Aproveitamento de águas pluviais das coberturas)
    - Reservatório de Retardo (Controle de escoamento superficial: Área do Terreno × 6,3 L)
    - Quadro Demonstrativo de Acessibilidade (Art. 14 do Decreto nº 63.728/2024)
    - Quadro de Vagas de Estacionamento
    - Cálculo de Uso Incentivado (Art. 1º III e Art. 18 IV do Decreto nº 63.728/2024)
    """
    # 1. Reservatório de Reúso
    if area_cobertura_impermeavel_m2 is None:
        # Na planilha D3 = 'Q. ÁREAS'!AE7 (2º pavimento), ou projeção média do pavimento-tipo
        area_cobertura_impermeavel_m2 = (
            quadro_areas.total_por_pavimento[2]
            if len(quadro_areas.total_por_pavimento) > 2
            else (indices.area_ocupacao_max_m2 or 0.0)
        )
    aci = max(0.0, float(area_cobertura_impermeavel_m2))
    acv = max(0.0, float(area_cobertura_verde_m2))
    vri = round(16.0 * aci, 2)
    vrv = round(float(fator_cobertura_verde) * acv, 2)
    vrm_exig = round(vri + vrv, 2)
    # Arredondado comercialmente para cima em múltiplos de 1.000 L (ou mínimo 5.000 L quando > 0)
    vrm_proj = float(math.ceil(vrm_exig / 1000.0) * 1000) if vrm_exig > 0 else 0.0

    # 2. Reservatório de Retardo (direto da Área do Terreno do GeoSampa: D38 * 6,3)
    retardo_exig = round(indices.area_terreno_m2 * 6.30, 2)
    retardo_proj = float(max(5000, math.ceil(retardo_exig / 5000.0) * 5000)) if retardo_exig > 0 else 0.0

    # 3. Acessibilidade (Art. 14 Decreto 63.728/24)
    sub_u = quadro_areas.subtotal_unidades
    tot_his2 = sub_u.get("u_his2", 0.0) + sub_u.get("u_his2_cota", 0.0)
    tot_r2v1 = sub_u.get("u_r2v1", 0.0) + sub_u.get("u_r2v1_10", 0.0)
    tot_his1 = sub_u.get("u_his1", 0.0) + sub_u.get("u_his1_50", 0.0)
    tot_nr1_12 = sub_u.get("u_nr1_12", 0.0)

    exig_his2 = round(tot_his2 * 0.03, 2)
    proj_his2 = float(math.ceil(exig_his2))
    exig_r2v1 = round(tot_r2v1 * 0.03, 2)
    proj_r2v1 = float(math.ceil(exig_r2v1))
    exig_his1 = round(tot_his1 * 0.03, 2)
    proj_his1 = float(math.ceil(exig_his1))
    exig_nr1_12 = round(tot_nr1_12 * 0.05, 2)
    proj_nr1_12 = float(math.ceil(exig_nr1_12))

    acessibilidade = [
        LinhaQuadro("HIS-2 (3% adaptáveis)", "Total de unidades", tot_his2, "uh", ""),
        LinhaQuadro("HIS-2 (3% adaptáveis)", "Exigido (3%)", exig_his2, "uh", ""),
        LinhaQuadro("HIS-2 (3% adaptáveis)", "Projetado (arredondado p/ cima)", proj_his2, "uh", "Art. 14 Dec. 63.728/24"),
        LinhaQuadro("R2V-1 (3% adaptáveis)", "Total de unidades", tot_r2v1, "uh", ""),
        LinhaQuadro("R2V-1 (3% adaptáveis)", "Exigido (3%)", exig_r2v1, "uh", ""),
        LinhaQuadro("R2V-1 (3% adaptáveis)", "Projetado (arredondado p/ cima)", proj_r2v1, "uh", "Art. 14 Dec. 63.728/24"),
        LinhaQuadro("HIS-1 (3% adaptáveis)", "Total de unidades", tot_his1, "unid.", ""),
        LinhaQuadro("HIS-1 (3% adaptáveis)", "Exigido (3%)", exig_his1, "unid.", ""),
        LinhaQuadro("HIS-1 (3% adaptáveis)", "Projetado (arredondado p/ cima)", proj_his1, "unid.", "Mín. 1 por pavimento quando aplicável"),
        LinhaQuadro("NR1-12 (5% adaptadas)", "Total de unidades", tot_nr1_12, "unid.", ""),
        LinhaQuadro("NR1-12 (5% adaptadas)", "Projetado (5% arredondado p/ cima)", proj_nr1_12, "unid.", "Corrigido para 5% conforme texto legal"),
    ]

    # 4. Vagas de Estacionamento
    vagas_pne = float(max(1, math.ceil(quadro_areas.area_computavel_m2 / 4000.0))) if quadro_areas.area_computavel_m2 > 0 else 0.0
    vagas_idoso = float(math.ceil(vagas_automoveis_livres * 0.05))
    vagas_motos = float(math.ceil(vagas_automoveis_livres * 0.05))
    vagas = [
        LinhaQuadro("P.N.E. / Utilitários", "1 vaga a cada 4.000 m² computáveis", vagas_pne, "vagas", ""),
        LinhaQuadro("Livres (Automóveis)", "Não computável (projetadas)", float(vagas_automoveis_livres), "vagas", ""),
        LinhaQuadro("Idoso", "5% × automóveis", vagas_idoso, "vagas", ""),
        LinhaQuadro("Motos", "5% × automóveis", vagas_motos, "vagas", ""),
    ]

    # 5. Uso Incentivado (Art. 1º Inciso III e Art. 18 Inciso IV Decreto 63.728/24)
    t46 = indices.area_comp_projeto_m2 or 0.0
    sub_a = quadro_areas.subtotal_areas
    perm_his2 = round(t46 * indices.proporcao_his, 2)
    perm_r2v1 = round(t46 * (1.0 - indices.proporcao_his), 2)
    perm_his1_benef = round(t46 * 0.50, 2)
    perm_r2v1_inc = round(quadro_areas.area_computavel_m2 * 0.10, 2)

    uso_incentivado = [
        LinhaQuadro(
            "HIS-2",
            f"Permitido ({indices.proporcao_his * 100:.0f}% C.A. máx.)",
            perm_his2,
            "m²",
            f"Projetado: {sub_a.get('c_his2', 0.0):,.2f} m²",
        ),
        LinhaQuadro(
            "R2V-1",
            f"Permitido ({(1.0 - indices.proporcao_his) * 100:.0f}% C.A. máx.)",
            perm_r2v1,
            "m²",
            f"Projetado: {sub_a.get('c_r2v1', 0.0):,.2f} m²",
        ),
        LinhaQuadro(
            "HIS-1 (Benefício 50%)",
            "Limite de incentivo",
            perm_his1_benef,
            "m²",
            f"Projetado: {sub_a.get('nc_his1_50', 0.0):,.2f} m²",
        ),
        LinhaQuadro(
            "R2V-1 (10% incentivo)",
            "Limite de 10% da área computável",
            perm_r2v1_inc,
            "m²",
            f"Projetado: {sub_a.get('nc_r2v1_10', 0.0):,.2f} m²",
        ),
    ]

    return ResultadoAnexos(
        reuso_vri_l=vri,
        reuso_vrv_l=vrv,
        reuso_exigido_l=vrm_exig,
        reuso_projetado_l=vrm_proj,
        retardo_exigido_l=retardo_exig,
        retardo_projetado_l=retardo_proj,
        acessibilidade=acessibilidade,
        vagas=vagas,
        uso_incentivado=uso_incentivado,
    )
