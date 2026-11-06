"""
Contas de aproveitamento do terreno em São Paulo (estudo de massa preliminar).

Módulo sem dependência de interface: recebe EntradaAproveitamento e devolve os limites legais,
a outorga onerosa e a memória de cálculo com a base legal de cada linha.
Não substitui a análise de projeto nem a consulta à legislação no licenciamento.
"""

import math
from dataclasses import dataclass, field, replace
from typing import List, Optional

from domain.legislacao_sp import (
    FP_ZEM_ZEMP,
    PA_SEM_QUOTA_AMBIENTAL,
    QUADRO_3,
    QUADRO_3A,
    QUADRO_6,
    TP_FIXA_POR_ZONA,
    ParametrosZonaLei,
    taxa_permeabilidade,
)

ORDINARIO = "ORDINARIO"
EHIS = "EHIS"
EHMP = "EHMP"

ZONAS_EIXO = {"ZEU", "ZEUa", "ZEUP", "ZEUPa", "ZEM", "ZEMP"}
ZONAS_FACHADA_50 = ZONAS_EIXO | {"ZC", "ZCa"}
LIMITE_NAO_COMPUTAVEL = 0.59          # LPUOS art. 62, § 2º
LIMIAR_COTA_SOLIDARIEDADE_M2 = 20000.0  # PDE art. 112


@dataclass
class EntradaAproveitamento:
    area_terreno_m2: float
    zona: str
    pa: Optional[str] = None
    area_doacao_m2: float = 0.0
    faixa_reservada_nao_edificavel: bool = False  # art. 67, § 3º: índices sobre a área original
    testada_m: float = 0.0
    profundidade_m: float = 0.0
    modalidade: str = ORDINARIO
    eixo_ativado: bool = False            # ZEUP/ZEUPa com art. 83 do PDE ou ZEM/ZEMP com art. 8º da LPUOS
    ca_utilizado: Optional[float] = None  # None = usa o máximo disponível
    cota_solidariedade: bool = False      # PDE art. 112, § 3º e § 8º (+20% de área computável)
    valor_m2_quadro14: Optional[float] = None
    fs: float = 1.0
    linha_quadro_6: Optional[str] = None
    uso_residencial: bool = True
    fp_informado: Optional[float] = None  # substitui o Quadro 6 quando houver regra específica
    area_media_unidade_m2: float = 50.0
    pe_direito_m: float = 3.0


@dataclass
class LinhaMemoria:
    grupo: str
    item: str
    valor: Optional[float]
    unidade: str
    formula: str
    base_legal: str


@dataclass
class ResultadoAproveitamento:
    zona: str
    area_base_potencial_m2: float
    area_remanescente_m2: float
    to_aplicada: float
    tp_aplicada: Optional[float]
    projecao_max_m2: float
    area_permeavel_min_m2: Optional[float]
    qa_minima: Optional[float]
    ca_minimo: Optional[float]
    ca_basico: float
    ca_maximo: float
    ca_final: float
    ca_usado: float
    computavel_basica_m2: float
    computavel_maxima_m2: float
    computavel_usada_m2: float
    potencial_adicional_m2: float
    adicional_a_pagar_m2: float
    fp: Optional[float]
    contrapartida_m2: Optional[float]
    outorga_total: Optional[float]
    unidades_minimas: Optional[int]
    unidades_estimadas: int
    area_total_max_m2: float
    nao_computavel_max_m2: float
    fachada_ativa_max_m2: float
    gabarito_m: Optional[float]
    pavimentos_necessarios: Optional[int]
    pavimentos_max_gabarito: Optional[int]
    altura_estimada_m: Optional[float]
    ca_atingivel_gabarito: Optional[float]
    memoria: List[LinhaMemoria] = field(default_factory=list)
    alertas: List[str] = field(default_factory=list)


def taxa_ocupacao_tabela(params: ParametrosZonaLei, area_lote_m2: float) -> float:
    """Quadro 3: a primeira faixa é de lotes menores que 500 m²; exatamente 500 m² já usa a segunda."""
    return params.to_lote_menor_500 if area_lote_m2 < 500 else params.to_lote_500_ou_mais


def quota_ambiental_minima(pa: Optional[str], area_lote_m2: float) -> Optional[float]:
    """Pontuação mínima do Quadro 3A. Lotes até 500 m² são isentos (art. 76, § 2º)."""
    if area_lote_m2 <= 500 or pa not in QUADRO_3A:
        return None
    faixas = QUADRO_3A[pa][2]
    for limite, valor in zip((1000, 2500, 5000, 10000), faixas):
        if area_lote_m2 <= limite:
            return valor
    return faixas[4]


def _ca_maximo_por_lote(params: ParametrosZonaLei, area_lote_m2: float) -> float:
    """Notas (f), (g) e (h) do Quadro 3."""
    if params.sigla in ("ZEIS-1", "ZEIS-2", "ZEIS-5") and area_lote_m2 < 1000:
        return 2.0
    if params.sigla == "ZEIS-3" and area_lote_m2 < 500:
        return 2.0
    if params.sigla == "ZEIS-4" and area_lote_m2 < 1000:
        return 1.0
    return params.ca_maximo


def _resolver_parametros(ent: EntradaAproveitamento) -> ParametrosZonaLei:
    """ZEUP/ZEUPa ativadas assumem ZEU/ZEUa (notas b e c). ZEM/ZEMP ativadas são tratadas em calcular()."""
    params = QUADRO_3[ent.zona]
    if ent.eixo_ativado and ent.zona == "ZEUP":
        return QUADRO_3["ZEU"]
    if ent.eixo_ativado and ent.zona == "ZEUPa":
        return QUADRO_3["ZEUa"]
    return params


def _estimar_massa(ent, params, projecao, area_computavel):
    """
    Pavimentos a partir de um retângulo testada × profundidade. Simplificação conservadora: aplica o
    recuo acima de 10 m a todos os pavimentos e admite cada pavimento 100% computável.
    Devolve (projeção útil, pavimentos necessários, altura, pavimentos máximos pelo gabarito).
    """
    pe_direito = max(ent.pe_direito_m, 0.1)
    util = projecao
    if ent.testada_m > 0 and ent.profundidade_m > 0:
        pavs_baixos = math.ceil(area_computavel / max(projecao, 1.0))
        recuo = params.recuo_ate_10m if pavs_baixos * pe_direito <= 10 else params.recuo_acima_10m
        largura = max(ent.testada_m - 2 * recuo, 0.0)
        comprimento = max(ent.profundidade_m - params.recuo_frente_m - recuo, 0.0)
        util = min(projecao, largura * comprimento)
    if util <= 0:
        return 0.0, None, None, None
    pavimentos = math.ceil(round(area_computavel / util, 6))
    pav_gabarito = int(params.gabarito_m // pe_direito) if params.gabarito_m else None
    return util, pavimentos, pavimentos * pe_direito, pav_gabarito


def calcular_aproveitamento(ent: EntradaAproveitamento) -> ResultadoAproveitamento:
    if ent.zona not in QUADRO_3:
        raise ValueError(f"Zona {ent.zona!r} não consta do Quadro 3 da LPUOS; consulte a regra específica.")
    if ent.area_terreno_m2 <= 0:
        raise ValueError("A área do terreno deve ser maior que zero.")
    if not 0 <= ent.area_doacao_m2 < ent.area_terreno_m2:
        raise ValueError("A área doada deve ser menor que a área do terreno.")

    params = _resolver_parametros(ent)
    if params.ca_basico is None:
        raise ValueError(f"{ent.zona} não tem índices no Quadro 3 (nota k): ver art. 30 da LPUOS.")

    alertas: List[str] = []
    mem: List[LinhaMemoria] = []

    def linha(grupo, item, valor, unidade, formula, base):
        mem.append(LinhaMemoria(grupo, item, valor, unidade, formula, base))

    # 1. Áreas de cálculo
    original = ent.area_terreno_m2
    doacao = ent.area_doacao_m2
    reservada = ent.faixa_reservada_nao_edificavel
    remanescente = original if reservada else original - doacao
    if reservada or doacao == 0:
        base_potencial = original
        base_txt = "LPUOS art. 67, § 3º" if reservada else "—"
    elif ent.zona in ZONAS_EIXO:
        base_potencial = original
        base_txt = "PDE art. 81"
    else:
        base_potencial = remanescente
        base_txt = "Conservador: fora dos eixos, confirmar"
        alertas.append(
            "Doação fora de zona de eixo: o potencial foi calculado sobre o remanescente, por cautela. "
            "O PDE art. 81 garante a área original nos eixos; confirme a regra aplicável a esta zona."
        )
    linha("Terreno", "Área do terreno", original, "m²", "Informada", "Decreto 57.776 art. 102, § 8º (vale a menor área apurada)")
    linha("Terreno", "Área remanescente", remanescente, "m²", "Terreno − doação", "LPUOS art. 62, § 4º, I; Decreto 57.776 art. 102, I")
    linha("Terreno", "Base do potencial construtivo", base_potencial, "m²", "Área original ou remanescente", base_txt)

    # 2. Ocupação e permeabilidade
    to_tabela = taxa_ocupacao_tabela(params, remanescente)
    tp = taxa_permeabilidade(ent.zona, ent.pa, remanescente)
    to_final = min(to_tabela, 1.0 - tp) if tp is not None else to_tabela
    projecao = to_final * remanescente
    permeavel = tp * remanescente if tp is not None else None
    qa = quota_ambiental_minima(ent.pa, remanescente)

    if tp is not None and to_final < to_tabela:
        alertas.append(
            f"T.O. reduzida de {to_tabela:.2f} para {to_final:.2f}: T.O. + permeabilidade não pode passar de 1,00 "
            "(Quadro 3A, nota b)."
        )
    if ent.pa is None and ent.zona not in TP_FIXA_POR_ZONA:
        alertas.append("PA não informado: foi usada a maior permeabilidade do Quadro 3A. Informe o PA para o valor real.")
    if original >= 500 > remanescente:
        alertas.append("A doação leva o lote para abaixo de 500 m² e muda a faixa de T.O. e permeabilidade: confirme o enquadramento.")

    linha("Ocupação", "Taxa de ocupação do Quadro 3", to_tabela, "", "Lote < 500 m² ou ≥ 500 m²", "LPUOS Quadro 3")
    linha("Ocupação", "Taxa de ocupação aplicada", to_final, "", "mín(T.O.; 1 − T.P.)", "LPUOS Quadro 3A, nota b")
    linha("Ocupação", "Projeção máxima", projecao, "m²", "T.O. × remanescente", "LPUOS Quadro 3; não se aplica a subsolo de garagem (art. 63)")
    linha("Permeabilidade", "Taxa de permeabilidade mínima", tp, "", "Quadro 3A por PA, ou nota a por zona", "LPUOS art. 81 e Quadro 3A")
    linha("Permeabilidade", "Área permeável mínima", permeavel, "m²", "T.P. × remanescente", "LPUOS art. 81")
    linha("Permeabilidade", "Quota Ambiental mínima", qa, "pontos", "Quadro 3A por faixa de área", "LPUOS art. 76; isento até 500 m²")
    if remanescente > 500 and ent.pa != PA_SEM_QUOTA_AMBIENTAL:
        linha("Permeabilidade", "Reservatório de controle, mínimo legal", 6.3 * original, "L", "6,3 L × área total do lote",
              "LPUOS art. 79, § 2º; o Quadro 3B pode exigir mais")

    # 3. Coeficientes
    ca_ordinario = _ca_maximo_por_lote(params, base_potencial)
    zem_ativada = ent.eixo_ativado and ent.zona in ("ZEM", "ZEMP")
    if zem_ativada:
        ca_ordinario = 4.0
    ca_max = ca_ordinario
    if ent.modalidade == EHIS:
        if params.ca_ehis is None:
            alertas.append(f"EHIS não previsto para {ent.zona} no Quadro 2 do Decreto 63.728: usado o C.A. ordinário.")
        else:
            ca_max = 6.0 if zem_ativada else params.ca_ehis
    elif ent.modalidade == EHMP:
        if params.ca_ehmp is None:
            alertas.append(f"EHMP não previsto para {ent.zona} no Quadro 2 do Decreto 63.728: usado o C.A. ordinário.")
        else:
            ca_max = 5.0 if zem_ativada else params.ca_ehmp
    if ent.modalidade != ORDINARIO:
        alertas.append(
            "C.A. de EHIS/EHMP vem do Quadro 2 do Decreto 63.728 conforme transcrito na planilha Yonder: confira no anexo oficial. "
            "EHIS exige ao menos 80% da área computável para HIS."
        )
    ca_final = ca_max * 1.2 if ent.cota_solidariedade else ca_max
    ca_usado = ent.ca_utilizado if ent.ca_utilizado is not None else ca_final
    if ca_usado > ca_final + 1e-9:
        alertas.append(f"C.A. informado ({ca_usado:.2f}) acima do máximo disponível ({ca_final:.2f}): limitado ao máximo.")
        ca_usado = ca_final
    if params.ca_minimo and ca_usado < params.ca_minimo:
        alertas.append(f"C.A. usado abaixo do mínimo da zona ({params.ca_minimo:.2f}): lote pode ser considerado subutilizado.")

    comp_basica = params.ca_basico * base_potencial
    comp_maxima = ca_final * base_potencial
    comp_usada = ca_usado * base_potencial
    adicional = max(0.0, comp_usada - comp_basica)
    linha("Coeficiente", "C.A. mínimo", params.ca_minimo, "", "Tabela", "LPUOS Quadro 3")
    linha("Coeficiente", "C.A. básico", params.ca_basico, "", "Tabela", "LPUOS Quadro 3")
    linha("Coeficiente", "C.A. máximo ordinário", ca_ordinario, "", "Tabela e notas d a h", "LPUOS Quadro 3 e art. 8º")
    linha("Coeficiente", "C.A. máximo disponível", ca_final, "", "Modalidade; +20% se houver cota de solidariedade",
          "Decreto 63.728 Quadro 2; PDE art. 60 e art. 112, § 3º")
    linha("Área computável", "Sem outorga (básica)", comp_basica, "m²", "C.A. básico × base", "PDE art. 116")
    linha("Área computável", "Máxima", comp_maxima, "m²", "C.A. máximo × base", "LPUOS Quadro 3")
    linha("Área computável", "Usada no estudo", comp_usada, "m²", "C.A. usado × base", "—")

    # 4. Outorga onerosa
    isenta_doacao = 0.0
    if doacao and not reservada and base_potencial == original:
        isenta_doacao = max(0.0, ca_ordinario - params.ca_basico) * doacao
    a_pagar = max(0.0, adicional - isenta_doacao)
    linha("Outorga", "Potencial adicional", adicional, "m²", "Computável usada − básica", "PDE art. 117, § 1º")
    linha("Outorga", "Isento pela doação", isenta_doacao, "m²", "(C.A. máx − C.A. bás) × doação", "PDE art. 81")
    linha("Outorga", "Adicional a pagar", a_pagar, "m²", "Adicional − isento", "PDE art. 117")

    fp = ent.fp_informado
    if fp is None and ent.zona in ("ZEM", "ZEMP"):
        fp = FP_ZEM_ZEMP
    if fp is None and ent.linha_quadro_6 in QUADRO_6:
        fp = QUADRO_6[ent.linha_quadro_6][0 if ent.uso_residencial else 1]
    contrapartida = total = None
    if ent.valor_m2_quadro14 is not None and ent.valor_m2_quadro14 > 0 and fp is not None and comp_usada > 0:
        contrapartida = (base_potencial / comp_usada) * ent.valor_m2_quadro14 * ent.fs * fp
        total = contrapartida * a_pagar
        linha("Outorga", "Fator de planejamento (Fp)", fp, "", "Quadro 6, ou 2 em ZEM/ZEMP", "PDE Quadro 6; LPUOS art. 8º, § 3º")
        linha("Outorga", "Fator de interesse social (Fs)", ent.fs, "", "Quadro 5", "PDE Quadro 5 e art. 79")
        linha("Outorga", "Contrapartida (C)", contrapartida, "R$/m²", "(At / Ac) × V × Fs × Fp", "PDE art. 117")
        linha("Outorga", "Outorga total estimada", total, "R$", "C × adicional a pagar", "PDE art. 117, § 1º")
    elif a_pagar > 0:
        alertas.append("Outorga não calculada: informe o valor V do Cadastro de Valor de Terreno e a macroárea (Fp).")
    if a_pagar > 0:
        alertas.append(
            "Um único Fs foi aplicado a todo o empreendimento. Com tipologias diferentes, C é calculado por tipologia "
            "(Decreto 63.504 art. 3º, § 2º). O Quadro 14 é atualizado por decreto: use o valor vigente."
        )

    # 5. Unidades e cota-parte
    area_media = max(ent.area_media_unidade_m2, 1.0)
    unidades_est = int(comp_usada // area_media)
    unidades_min = None
    if params.cota_parte_m2:
        unidades_min = math.ceil(round((ca_usado * base_potencial) / (ca_final * params.cota_parte_m2), 6))
        linha("Unidades", "Unidades mínimas pela cota-parte", unidades_min, "un", "N = (CAu × At) / (CAmáx × Q)", "PDE art. 79, § 1º")
        if unidades_est < unidades_min and ent.uso_residencial:
            alertas.append(
                f"Com unidades de {area_media:.0f} m², o estudo gera {unidades_est} unidades, abaixo do mínimo de {unidades_min} "
                "pela cota-parte: reduza a área média, ou verifique a superação com Fs (PDE art. 79, §§ 9º e 10)."
            )
    linha("Unidades", "Unidades estimadas", unidades_est, "un", "Computável usada ÷ área média", "Estimativa")

    # 6. Limites de áreas não computáveis e incentivos
    area_total_max = comp_usada / (1 - LIMITE_NAO_COMPUTAVEL)
    nao_comp_max = area_total_max - comp_usada
    pct_fachada = 0.5 if ent.zona in ZONAS_FACHADA_50 else 0.2
    fachada_max = pct_fachada * remanescente
    linha("Não computável", "Área construída total máxima", area_total_max, "m²", "Computável ÷ (1 − 0,59)",
          "LPUOS art. 62, § 2º (sem contar incisos VII a XVI)")
    linha("Não computável", "Não computável máxima (incisos I a VI)", nao_comp_max, "m²", "0,59 × área total", "LPUOS art. 62, § 2º")
    linha("Não computável", "Fachada ativa não computável", fachada_max, "m²", f"{pct_fachada:.0%} × remanescente", "LPUOS art. 62, VII e § 4º, I")
    linha("Não computável", "Terraço não computável por pavimento", 0.05 * remanescente, "m²", "5% × terreno", "COE art. 108, I; Decreto 57.776 art. 102, I")
    if ent.uso_residencial:
        linha("Não computável", "Área comum em qualquer pavimento", 3.0 * unidades_est, "m²", "3 m² × unidades", "COE art. 108, VII, b")
    if ent.zona in ZONAS_FACHADA_50:
        linha("Não computável", "Uso nR incentivado (misto com fachada ativa)", 0.2 * comp_usada, "m²", "20% × computável", "LPUOS art. 62, VIII")
    if ent.zona in ZONAS_EIXO and ent.uso_residencial:
        vagas_alt1 = unidades_est if area_media >= 30 else 0
        vagas_alt2 = int((unidades_est * area_media) // 60)
        vagas = max(vagas_alt1, vagas_alt2)
        linha("Não computável", "Vagas não computáveis (teto)", vagas, "vagas", "1 por unid. ≥ 30 m², ou 1 a cada 60 m² privativos", "LPUOS art. 62, I, a")
        linha("Não computável", "Garagem não computável (teto)", 32.0 * vagas, "m²", "Vagas × 32 m²", "LPUOS art. 62, I, a")

    # 7. Cota de solidariedade
    if comp_usada > LIMIAR_COTA_SOLIDARIEDADE_M2 or ent.cota_solidariedade:
        his = 0.10 * comp_usada
        linha("Cota de solidariedade", "HIS a destinar (não computável)", his, "m²", "10% × computável", "PDE art. 112, caput e § 1º")
        if ent.valor_m2_quadro14:
            linha("Cota de solidariedade", "Alternativa: depósito no FUNDURB", 0.20 * ent.valor_m2_quadro14 * original, "R$",
                  "20% × V × área do terreno", "PDE art. 112, § 2º, III")
    if comp_usada > LIMIAR_COTA_SOLIDARIEDADE_M2:
        alertas.append("Computável acima de 20.000 m²: a cota de solidariedade é obrigatória (PDE art. 112).")

    # 8. Massa e gabarito
    params_massa = replace(params, gabarito_m=None) if zem_ativada else params  # art. 8º, § 1º: dispensa o gabarito
    gabarito = params_massa.gabarito_m
    util, pavimentos, altura, pav_gabarito = _estimar_massa(ent, params_massa, projecao, comp_usada)
    ca_atingivel = None
    if pav_gabarito is not None and base_potencial > 0:
        ca_atingivel = pav_gabarito * util / base_potencial
        if ca_atingivel < ca_usado - 1e-9:
            alertas.append(
                f"O gabarito de {gabarito:.0f} m permite cerca de {pav_gabarito} pavimentos, o que limita o C.A. a {ca_atingivel:.2f} "
                f"(abaixo de {ca_usado:.2f}) nesta projeção. Estimativa simplificada."
            )
    linha("Massa", "Projeção útil por pavimento", util, "m²", "mín(projeção; retângulo menos recuos)", "LPUOS Quadro 3 e art. 66; estimativa")
    linha("Massa", "Pavimentos necessários", pavimentos, "pav", "Computável ÷ projeção útil", "Estimativa")
    linha("Massa", "Altura estimada", altura, "m", "Pavimentos × pé-direito", "Estimativa")
    linha("Massa", "Pavimentos máximos pelo gabarito", pav_gabarito, "pav", "Gabarito ÷ pé-direito", "LPUOS art. 60")
    linha("Massa", "Recuo de frente", params_massa.recuo_frente_m, "m", "Tabela; 0 = não se aplica", "LPUOS Quadro 3; facultativo pelos arts. 67 e 69")
    linha("Massa", "Recuo lateral e de fundo acima de 10 m", params_massa.recuo_acima_10m, "m", "Tabela", "LPUOS Quadro 3 e art. 66")

    # 9. Condicionantes por tamanho de lote
    if ent.testada_m and ent.testada_m <= 10 and params_massa.recuo_acima_10m:
        alertas.append(
            "Frente de até 10 m: os recuos laterais e de fundo podem ser dispensados (LPUOS art. 66, III, objeto de ADIN). "
            "O estudo mantém os recuos, por cautela."
        )
    if original < 125:
        alertas.append("Lote abaixo da área mínima de 125 m² do município (LPUOS art. 41): verifique a regularidade do lote.")
    if ent.zona in ZONAS_FACHADA_50 and 10000 < original <= 20000:
        alertas.append(
            "Lote entre 10.000 e 20.000 m²: fruição pública de 20% do lote (usos nR), até 25% de muro na testada "
            "e fachada ativa em 25% da testada são obrigatórios (LPUOS art. 87)."
        )
    if original > 20000:
        alertas.append("Lote acima de 20.000 m²: verifique a obrigação de parcelamento e os limites do art. 42 da LPUOS.")
    if ent.zona in ZONAS_EIXO or original > 2500:
        alertas.append("Passeio de 5 m pode ser exigido, por doação ou faixa não edificável; isso dispensa o recuo de frente (LPUOS art. 67).")
    if ent.zona.startswith("ZEIS"):
        alertas.append("Em ZEIS há percentuais mínimos de HIS (PDE Quadro 4); o estudo não verifica esses percentuais.")

    return ResultadoAproveitamento(
        zona=ent.zona,
        area_base_potencial_m2=base_potencial,
        area_remanescente_m2=remanescente,
        to_aplicada=to_final,
        tp_aplicada=tp,
        projecao_max_m2=projecao,
        area_permeavel_min_m2=permeavel,
        qa_minima=qa,
        ca_minimo=params.ca_minimo,
        ca_basico=params.ca_basico,
        ca_maximo=ca_ordinario,
        ca_final=ca_final,
        ca_usado=ca_usado,
        computavel_basica_m2=comp_basica,
        computavel_maxima_m2=comp_maxima,
        computavel_usada_m2=comp_usada,
        potencial_adicional_m2=adicional,
        adicional_a_pagar_m2=a_pagar,
        fp=fp,
        contrapartida_m2=contrapartida,
        outorga_total=total,
        unidades_minimas=unidades_min,
        unidades_estimadas=unidades_est,
        area_total_max_m2=area_total_max,
        nao_computavel_max_m2=nao_comp_max,
        fachada_ativa_max_m2=fachada_max,
        gabarito_m=gabarito,
        pavimentos_necessarios=pavimentos,
        pavimentos_max_gabarito=pav_gabarito,
        altura_estimada_m=altura,
        ca_atingivel_gabarito=ca_atingivel,
        memoria=mem,
        alertas=alertas,
    )
