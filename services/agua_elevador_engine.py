"""
Motores de cálculo das Etapas 9 e 10:
- Etapa 9 (`CALC. ÁGUA`): Cálculo de população por pavimento (Elevador, Água e Bombeiros) e
  dimensionamento dos reservatórios superior e inferior de água potável.
- Etapa 10 (`ELEVADOR`): Cálculo de tráfego de elevadores segundo a NBR 5665 (Atlas Schindler).
"""

from typing import Dict, List, Optional

from domain.viabilidade_models import (
    PavimentoPopulacao,
    ResultadoAgua,
    ResultadoElevador,
)

DESTINACOES_PREDIO: Dict[int, Dict[str, object]] = {
    1: {"nome": "Escritórios Única Entidade", "pct_5min": 15.0, "classe": "E"},
    2: {"nome": "Escritórios Geral, Consultórios", "pct_5min": 12.0, "classe": "E"},
    3: {"nome": "Hospitais com Duto de Lixo e Monta Cargas", "pct_5min": 8.0, "classe": "O"},
    4: {"nome": "Hospitais SEM Duto de Lixo e Monta Cargas", "pct_5min": 12.0, "classe": "O"},
    5: {"nome": "Escolas", "pct_5min": 20.0, "classe": "O"},
    6: {"nome": "Hotéis", "pct_5min": 10.0, "classe": "O"},
    7: {"nome": "Apartamentos", "pct_5min": 10.0, "classe": "A"},
    8: {"nome": "Lojas e Centros Comerciais", "pct_5min": 10.0, "classe": "O"},
}


def gerar_populacao_padrao_pavimentos(
    qtd_pav_tipo: int = 9,
    unidades_1dorm_por_andar: int = 3,
    unidades_2dorm_por_andar: int = 8,
    unidades_3dorm_por_andar: int = 0,
) -> List[PavimentoPopulacao]:
    """Gera a tabela de população por pavimento (`CALC. ÁGUA!A3:G14`)."""
    linhas: List[PavimentoPopulacao] = [
        PavimentoPopulacao("SUBSOLO", 0, 0, 0),
        PavimentoPopulacao("INFERIOR 01", 0, 0, 0),
        PavimentoPopulacao("TÉRREO", 0, 0, 0),
    ]
    for i in range(1, qtd_pav_tipo + 1):
        linhas.append(
            PavimentoPopulacao(
                f"{i}º PAV.",
                int(unidades_1dorm_por_andar),
                int(unidades_2dorm_por_andar),
                int(unidades_3dorm_por_andar),
            )
        )
    return linhas


def calcular_agua_e_populacao(
    pavimentos_pop: List[PavimentoPopulacao],
    litros_per_capita: float = 125.0,
    reserva_incendio_l: float = 25000.0,
    superior_projetado_l: float = 0.0,
    inferior_projetado_l: float = 0.0,
) -> ResultadoAgua:
    """
    ETAPA 9: Executa os cálculos da aba `CALC. ÁGUA`:
    - População por pavimento (Elevador = 1D×2 + 2D×4 + 3D×5; Água = idem; Bombeiros = 1D×4 + 2D×6 + 3D×8)
    - Consumo diário (`L4 = F15 × per_capita`, padrão 125 L/per capita conforme nota L35, ou 75 L)
    - Reservatório Superior Recomendado `M10 = (L4 × 0,4) + L7`
    - Reservatório Inferior Recomendado `M13 = L4 × 0,6`
    - Volume Total Recomendado `M16 = M10 + M13`
    """
    linhas_detalhe: List[Dict[str, float]] = []
    tot_elev = 0
    tot_agua = 0
    tot_bomb = 0

    for p in pavimentos_pop:
        d1 = max(0, int(p.dorm1))
        d2 = max(0, int(p.dorm2))
        d3 = max(0, int(p.dorm3))
        pop_el = d1 * 2 + d2 * 4 + d3 * 5
        pop_ag = d1 * 2 + d2 * 4 + d3 * 5
        pop_bm = d1 * 4 + d2 * 6 + d3 * 8
        tot_elev += pop_el
        tot_agua += pop_ag
        tot_bomb += pop_bm
        linhas_detalhe.append(
            {
                "pavimento": p.nome,
                "dorm1": d1,
                "dorm2": d2,
                "dorm3": d3,
                "pop_elevador": pop_el,
                "pop_agua": pop_ag,
                "pop_bombeiros": pop_bm,
            }
        )

    l4_consumo = round(tot_agua * float(litros_per_capita), 2)
    m10_sup_rec = round((l4_consumo * 0.40) + float(reserva_incendio_l), 2)
    m13_inf_rec = round(l4_consumo * 0.60, 2)
    m16_tot_rec = round(m10_sup_rec + m13_inf_rec, 2)

    sup_proj = round(float(superior_projetado_l or m10_sup_rec), 2)
    inf_proj = round(float(inferior_projetado_l or m13_inf_rec), 2)
    tot_proj = round(sup_proj + inf_proj, 2)

    return ResultadoAgua(
        linhas=linhas_detalhe,
        pop_elevador=tot_elev,
        pop_agua=tot_agua,
        pop_bombeiros=tot_bomb,
        consumo_diario_l=l4_consumo,
        superior_recomendado_l=m10_sup_rec,
        inferior_recomendado_l=m13_inf_rec,
        total_recomendado_l=m16_tot_rec,
        superior_projetado_l=sup_proj,
        inferior_projetado_l=inf_proj,
        total_projetado_l=tot_proj,
    )


def calcular_trafego_elevadores(
    populacao_predio: float,
    unidades_no_grupo: int = 2,
    capac_nominal_pass: int = 8,
    capac_calculo_pass: int = 8,
    numero_paradas: int = 12,
    percurso_m: float = 30.0,
    velocidade_m_s: float = 1.50,
    tipo_porta: str = "AC",
    abertura_porta_m: float = 0.80,
    codigo_destinacao: int = 7,
) -> ResultadoElevador:
    """
    ETAPA 10: Calcula o estudo de tráfego de elevadores (`ELEVADOR` — NBR 5665)
    exatamente com as fórmulas das células `D26:D57` e `J52:K56`.
    """
    info_dest = DESTINACOES_PREDIO.get(codigo_destinacao, DESTINACOES_PREDIO[7])
    nome_dest = str(info_dest["nome"])
    pct_5min = float(info_dest["pct_5min"])
    classe = str(info_dest["classe"])

    pop_total = max(0.0, float(populacao_predio))
    pop_5min = round(pop_total * pct_5min / 100.0, 2)

    n_elev = max(1, int(unidades_no_grupo))
    p_nom = max(1, int(capac_nominal_pass))
    p_calc = max(1, int(capac_calculo_pass))
    n_paradas = max(2, int(numero_paradas))
    h_percurso = max(1.0, float(percurso_m))
    v = max(0.1, float(velocidade_m_s))
    porta = (tipo_porta or "AC").strip().upper()
    abertura = float(abertura_porta_m or 0.80)

    alertas: List[str] = []
    if p_nom < p_calc:
        alertas.append("Capac. Nominal deve ser maior ou igual à Capac. para Cálculo.")
    if porta not in ("AC", "AL", "EV"):
        alertas.append("Tipo de Porta deve ser AC, AL ou EV.")
    if abertura < 0.60 or abertura > 1.50:
        alertas.append("Verifique Abertura da Porta em metros (0,80 a 1,50 m).")

    # D28: Intervalo de tráfego máximo (None para Apartamentos 'A')
    if classe == "A":
        intervalo_max: Optional[float] = None
    elif n_elev == 1:
        intervalo_max = 80.0
    elif n_elev == 2:
        intervalo_max = 60.0
    elif n_elev == 3:
        intervalo_max = 50.0
    elif classe == "E":
        intervalo_max = 40.0
    else:
        intervalo_max = 45.0

    # D35: Número de paradas prováveis = D34 - (D34 - 1) * ((D34 - 2) / (D34 - 1)) ^ D33
    if n_paradas <= 2:
        np_prov = float(n_paradas)
    else:
        np_prov = n_paradas - (n_paradas - 1) * (((n_paradas - 2) / (n_paradas - 1)) ** p_calc)

    # D41: Aceleração e retardamento segundo regra de velocidades da planilha
    if v <= 0.75:
        t_acel = 2.5
    elif v <= 1.0:
        t_acel = 3.0 + (v - 1.0) * 2.0
    elif v <= 1.25:
        t_acel = 3.0
    elif v <= 2.75:
        t_acel = 4.5 + (v - 2.0) * 2.0
    else:
        t_acel = 6.0

    # D42: Abertura e fechamento (AC=3,9s, AL=5,5s, EV=6,0s)
    if porta == "AC":
        t_porta = 3.9
    elif porta == "AL":
        t_porta = 5.5
    else:
        t_porta = 6.0

    # D43: Entrada e saída de passageiros (2,4s para aberturas até 1,0m; 2,0s para >= 1,1m)
    t_pass = 2.4 if abertura < 1.10 else 2.0

    # D45:D51 — Tempos totais calculados
    t1 = (h_percurso * 2.0) / v
    t2 = (t_acel * np_prov) / 2.0
    t3 = t_porta * np_prov
    t4 = t_pass * p_calc
    soma_parcial = t1 + t2 + t3 + t4
    adicional_10 = (t3 + t4) * 0.10
    ttv = soma_parcial + adicional_10

    # D52:D55 — Indicadores de tráfego
    intervalo_s = ttv / n_elev
    capac_transporte = (p_calc * 300.0) / ttv if ttv > 0 else 0.0
    capac_trafego = n_elev * capac_transporte
    grau_servico = (ttv / 4.0) + (intervalo_s / 2.0)

    # D57: Distância mínima para atingir velocidade nominal e parar (a=0,9 m/s², J=1,5 m/s³)
    dist_min = v * ((v / 0.9) + (0.9 / 1.5))

    atende_cap = capac_trafego >= pop_5min - 0.01
    if not atende_cap:
        alertas.append("NÃO ATENDE CAPACIDADE DE TRÁFEGO MÍNIMA EM 5 MINUTOS.")

    if intervalo_max is not None:
        atende_int: Optional[bool] = int(intervalo_s + 0.5) <= intervalo_max
        if not atende_int:
            alertas.append("NÃO ATENDE INTERVALO DE TRÁFEGO MÁXIMO.")
    else:
        atende_int = None

    return ResultadoElevador(
        destinacao=nome_dest,
        classe=classe,
        populacao=round(pop_total, 2),
        pct_5min=pct_5min,
        populacao_5min=pop_5min,
        intervalo_max_s=intervalo_max,
        paradas_provaveis=round(np_prov, 2),
        t_acel=round(t_acel, 2),
        t_porta=round(t_porta, 2),
        t_passageiro=round(t_pass, 2),
        t1=round(t1, 2),
        t2=round(t2, 2),
        t3=round(t3, 2),
        t4=round(t4, 2),
        soma_parcial=round(soma_parcial, 2),
        adicional_10=round(adicional_10, 2),
        ttv=round(ttv, 2),
        intervalo_s=round(intervalo_s, 2),
        capac_transporte=round(capac_transporte, 2),
        capac_trafego=round(capac_trafego, 2),
        grau_servico=round(grau_servico, 2),
        distancia_min_m=round(dist_min, 2),
        atende_capacidade=atende_cap,
        atende_intervalo=atende_int,
        alertas=alertas,
    )

