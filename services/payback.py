"""
Fluxo de caixa mensal e payback de uma incorporação (estudo preliminar).

Módulo sem dependência de interface. Não considera financiamento à produção, permuta,
inflação nem correção do saldo a receber: é um fluxo do projeto, em valores constantes.
"""

import math
from dataclasses import dataclass, field, replace
from typing import List, Optional, Sequence


@dataclass
class EntradaPayback:
    area_privativa_m2: float
    preco_venda_m2: float
    area_construida_m2: float
    custo_obra_m2: float
    custo_terreno: float
    terreno_entrada_pct: float = 1.0        # paga no mês 0; o saldo vai em parcelas iguais
    terreno_parcelas_meses: int = 0
    outorga: float = 0.0                    # paga no mês do lançamento (premissa: alvará já emitido)
    projetos_pct_obra: float = 0.05         # projetos e aprovação, do mês 0 até o lançamento
    administracao_pct_obra: float = 0.08    # segue a curva da obra
    comercial_pct_vgv: float = 0.06         # comissão e marketing, no mês de cada venda
    impostos_pct_receita: float = 0.04      # sobre cada recebimento
    mes_lancamento: int = 6
    mes_inicio_obra: int = 9
    duracao_obra_meses: int = 24
    vendas_lancamento_pct: float = 0.30     # vendido no mês do lançamento
    duracao_vendas_meses: int = 18          # o restante, em parcelas iguais nos meses seguintes
    recebido_ate_chaves_pct: float = 0.30   # pago pelo comprador da venda até as chaves
    meses_repasse_apos_chaves: int = 2      # o restante entra de uma vez neste prazo
    tma_anual: float = 0.15


@dataclass
class MesFluxo:
    mes: int
    entradas: float
    saidas: float
    saldo: float
    acumulado: float
    acumulado_descontado: float


@dataclass
class ResultadoPayback:
    meses: List[MesFluxo]
    vgv: float
    custo_total: float
    custos_por_grupo: dict
    lucro: float
    margem_vgv: float
    exposicao_maxima: float
    mes_exposicao_maxima: int
    payback_simples_mes: Optional[int]
    payback_descontado_mes: Optional[int]
    vpl: float
    tir_anual: Optional[float]
    alertas: List[str] = field(default_factory=list)


def _curva_s(duracao: int) -> List[float]:
    """Pesos mensais da obra: mais lenta no início e no fim, somando 1."""
    if duracao <= 1:
        return [1.0]
    pesos = [math.sin(math.pi * (i + 0.5) / duracao) ** 2 for i in range(duracao)]
    total = sum(pesos)
    return [p / total for p in pesos]


def mes_payback(acumulado: Sequence[float]) -> Optional[int]:
    """Primeiro mês a partir do qual o acumulado nunca mais fica negativo. None se terminar negativo."""
    if not acumulado or acumulado[-1] < 0:
        return None
    for mes in range(len(acumulado) - 1, -1, -1):
        if acumulado[mes] < 0:
            return mes + 1
    return 0


def _vpl_mensal(saldos: Sequence[float], taxa: float) -> float:
    return sum(valor / (1 + taxa) ** mes for mes, valor in enumerate(saldos))


def tir_anual(saldos: Sequence[float]) -> Optional[float]:
    """TIR por bisseção. None se o fluxo não tiver taxa de retorno entre -99% e +1000% ao mês."""
    baixa, alta = -0.99, 10.0
    v_baixa, v_alta = _vpl_mensal(saldos, baixa), _vpl_mensal(saldos, alta)
    if v_baixa * v_alta > 0:
        return None
    for _ in range(200):
        meio = (baixa + alta) / 2
        v_meio = _vpl_mensal(saldos, meio)
        if v_baixa * v_meio <= 0:
            alta = meio
        else:
            baixa, v_baixa = meio, v_meio
    return (1 + (baixa + alta) / 2) ** 12 - 1


def _validar(e: EntradaPayback) -> None:
    for nome in ("area_privativa_m2", "preco_venda_m2", "area_construida_m2", "custo_obra_m2", "custo_terreno", "outorga"):
        if getattr(e, nome) < 0:
            raise ValueError(f"{nome} não pode ser negativo.")
    if e.area_privativa_m2 * e.preco_venda_m2 <= 0:
        raise ValueError("Informe área privativa e preço de venda: sem VGV não há payback.")
    for nome in ("terreno_entrada_pct", "vendas_lancamento_pct", "recebido_ate_chaves_pct"):
        if not 0 <= getattr(e, nome) <= 1:
            raise ValueError(f"{nome} deve estar entre 0% e 100%.")
    if e.duracao_obra_meses < 1:
        raise ValueError("A obra precisa durar ao menos 1 mês.")
    if min(e.mes_lancamento, e.mes_inicio_obra, e.duracao_vendas_meses, e.meses_repasse_apos_chaves, e.terreno_parcelas_meses) < 0:
        raise ValueError("Prazos não podem ser negativos.")
    if e.tma_anual <= -1:
        raise ValueError("A TMA deve ser maior que -100%.")


def calcular_payback(e: EntradaPayback) -> ResultadoPayback:
    _validar(e)

    vgv = e.area_privativa_m2 * e.preco_venda_m2
    obra = e.area_construida_m2 * e.custo_obra_m2
    mes_chaves = e.mes_inicio_obra + e.duracao_obra_meses - 1
    ultima_venda = e.mes_lancamento + e.duracao_vendas_meses
    horizonte = max(mes_chaves + e.meses_repasse_apos_chaves, ultima_venda, e.terreno_parcelas_meses) + 1

    entradas = [0.0] * horizonte
    saidas = [0.0] * horizonte

    # Terreno: sem parcelas, o valor todo é pago no mês 0.
    entrada_terreno = e.custo_terreno if e.terreno_parcelas_meses == 0 else e.custo_terreno * e.terreno_entrada_pct
    saidas[0] += entrada_terreno
    for mes in range(1, e.terreno_parcelas_meses + 1):
        saidas[mes] += (e.custo_terreno - entrada_terreno) / e.terreno_parcelas_meses

    projetos = obra * e.projetos_pct_obra
    meses_projeto = max(e.mes_lancamento, 1)
    for mes in range(meses_projeto):
        saidas[mes] += projetos / meses_projeto
    saidas[e.mes_lancamento] += e.outorga

    administracao = obra * e.administracao_pct_obra
    for i, peso in enumerate(_curva_s(e.duracao_obra_meses)):
        saidas[e.mes_inicio_obra + i] += (obra + administracao) * peso

    # Vendas e recebimentos
    if e.duracao_vendas_meses == 0:
        vendas = {e.mes_lancamento: 1.0}
    else:
        vendas = {e.mes_lancamento: e.vendas_lancamento_pct}
        for mes in range(e.mes_lancamento + 1, ultima_venda + 1):
            vendas[mes] = (1 - e.vendas_lancamento_pct) / e.duracao_vendas_meses

    mes_repasse = mes_chaves + e.meses_repasse_apos_chaves
    for mes, fatia in vendas.items():
        valor_venda = vgv * fatia
        saidas[mes] += valor_venda * e.comercial_pct_vgv
        ate_chaves = valor_venda * e.recebido_ate_chaves_pct
        parcelas = max(mes_chaves - mes + 1, 1)
        for m in range(mes, mes + parcelas):
            entradas[m] += ate_chaves / parcelas
        entradas[max(mes, mes_repasse)] += valor_venda - ate_chaves

    impostos_total = 0.0
    for mes in range(horizonte):
        imposto = entradas[mes] * e.impostos_pct_receita
        saidas[mes] += imposto
        impostos_total += imposto

    # Indicadores
    taxa_mensal = (1 + e.tma_anual) ** (1 / 12) - 1
    meses: List[MesFluxo] = []
    acumulado = descontado = 0.0
    for mes in range(horizonte):
        saldo = entradas[mes] - saidas[mes]
        acumulado += saldo
        descontado += saldo / (1 + taxa_mensal) ** mes
        meses.append(MesFluxo(mes, entradas[mes], saidas[mes], saldo, acumulado, descontado))

    serie = [m.acumulado for m in meses]
    serie_desc = [m.acumulado_descontado for m in meses]
    saldos = [m.saldo for m in meses]
    pior = min(range(horizonte), key=lambda i: serie[i])

    alertas: List[str] = []
    if e.area_construida_m2 < e.area_privativa_m2:
        alertas.append("A área construída está menor que a área privativa: confira as duas.")
    if e.mes_inicio_obra < e.mes_lancamento:
        alertas.append("A obra começa antes do lançamento: a exposição de caixa tende a ser maior.")
    if mes_payback(serie) == mes_chaves + e.meses_repasse_apos_chaves and e.recebido_ate_chaves_pct < 1:
        alertas.append(
            "O payback coincide com o repasse: é a entrega da obra que libera o caixa. Atrasar a obra atrasa o retorno "
            "na mesma medida, e reduzir custo aumenta o lucro, mas não antecipa esse mês."
        )
    trocas = sum(1 for a, b in zip(
        [s for s in saldos if s], [s for s in saldos if s][1:]) if a * b < 0)
    if trocas > 1:
        alertas.append("O saldo mensal troca de sinal mais de uma vez: a TIR pode não ser única; prefira o VPL.")

    grupos = {
        "Terreno": e.custo_terreno,
        "Outorga": e.outorga,
        "Projetos e aprovação": projetos,
        "Obra": obra,
        "Administração": administracao,
        "Comercial": vgv * e.comercial_pct_vgv,
        "Impostos": impostos_total,
    }
    return ResultadoPayback(
        meses=meses,
        vgv=vgv,
        custo_total=sum(grupos.values()),
        custos_por_grupo=grupos,
        lucro=serie[-1],
        margem_vgv=serie[-1] / vgv,
        exposicao_maxima=min(serie[pior], 0.0),
        mes_exposicao_maxima=pior,
        payback_simples_mes=mes_payback(serie),
        payback_descontado_mes=mes_payback(serie_desc),
        vpl=serie_desc[-1],
        tir_anual=tir_anual(saldos),
        alertas=alertas,
    )


def sensibilidade_payback(
    e: EntradaPayback,
    variacoes_preco: Sequence[float] = (-0.2, -0.1, 0.0, 0.1, 0.2),
    variacoes_prazo: Sequence[int] = (-6, -3, 0, 3, 6),
) -> List[dict]:
    """
    Payback simples por variação do preço de venda e do prazo de obra (em meses).
    O eixo é o prazo porque, com receita concentrada no repasse, é ele que move o mês do payback;
    o custo de obra muda o lucro, e por isso só decide se o projeto se paga ou não.
    """
    linhas = []
    for dv in variacoes_preco:
        for dm in variacoes_prazo:
            variante = replace(e, preco_venda_m2=e.preco_venda_m2 * (1 + dv), duracao_obra_meses=max(1, e.duracao_obra_meses + dm))
            r = calcular_payback(variante)
            linhas.append({"preco": dv, "prazo": dm, "payback": r.payback_simples_mes, "lucro": r.lucro})
    return linhas
