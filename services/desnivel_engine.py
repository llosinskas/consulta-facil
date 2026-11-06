"""
Motor de Cálculo da Etapa 11 (`DESNÍVEL`):
Cálculo de Cota de Desnível dos Reservatórios (Trechos A, B e C) e verificação
de deságue por gravidade na sarjeta, eliminando os vínculos quebrados com planilhas externas.
"""

from domain.viabilidade_models import LinhaQuadro, ResultadoDesnivel


def calcular_desnivel_reservatorios(
    cota_sarjeta_m: float = 768.31,
    cota_terreno_arquitetura_m: float = 769.00,
    comprimento_trecho_a_m: float = 30.0,
    comprimento_trecho_b_m: float = 20.0,
    comprimento_trecho_c_m: float = 10.0,
    cota_tampa_reuso_imaginada_m: float = 0.0,
    inclinacao_tubulacao: float = 0.0005,
    espessura_laje_m: float = 0.12,
    interferencia_tubulacoes_m: float = 0.20,
    diametro_tubulacao_m: float = 0.10,
) -> ResultadoDesnivel:
    """
    ETAPA 11: Executa todas as fórmulas da aba `DESNÍVEL` (`B1:I49`):
    - Trecho A (`B10:C22`): Final do terreno até o Reservatório de Reúso
    - Trecho B (`B24:C37`): Final do terreno até o Reservatório de Retardo
    - Trecho C (`B39:E49`): Reservatório de Retardo até a Sarjeta
    - Comparativo (`F3:I7` e `B47:E49`): Cota do Terreno Arquitetura vs. Cota do Terreno Hidráulica
    """
    # Trecho A — Reservatório de Reúso
    c11 = float(cota_tampa_reuso_imaginada_m)
    c12 = round(c11 - 0.40, 4)
    c13 = max(0.0, float(comprimento_trecho_a_m))
    c14 = round(c13 * 1.30, 4)
    c15 = float(inclinacao_tubulacao)
    c16 = round((c15 * c14) * 10.0, 4)
    c17 = float(espessura_laje_m)
    c18 = float(interferencia_tubulacoes_m)
    c19 = float(diametro_tubulacao_m)
    c20 = round(c12 + c16 + c17 + c18 + c19, 4)
    c21 = round(c20 - c16 - c17 - c18 - c19, 4)
    b22 = "Subir cota de Nível" if c21 > 0 else "Descer cota de nível"

    linhas_a = [
        LinhaQuadro("Trecho A", "Comprimento do Trecho A (final do terreno até Reúso)", c13, "m", ""),
        LinhaQuadro("Trecho A", "Cota de tampa do reservatório de Reúso imaginada", c11, "m", ""),
        LinhaQuadro("Trecho A", "Nível D'água imaginado (C11 − 0,40)", c12, "m", ""),
        LinhaQuadro("Trecho A", "Coeficiente de Segurança (1,3 × Comprimento)", c14, "m", ""),
        LinhaQuadro("Trecho A", "Inclinação da Tubulação AP", c15 * 100.0, "%", f"{c15:.4f} m/m"),
        LinhaQuadro("Trecho A", "Altura Inicial × Final da Tubulação AP", c16, "m", "(C15 × C14) × 10"),
        LinhaQuadro("Trecho A", "Espessura da Laje", c17, "m", ""),
        LinhaQuadro("Trecho A", "Interferência de Tubulações", c18, "m", ""),
        LinhaQuadro("Trecho A", "Diâmetro da Tubulação", c19, "m", ""),
        LinhaQuadro("Trecho A", "Cota de tampa do reservatório de Reúso Real", c20, "m", ""),
        LinhaQuadro("Trecho A", "Nível d'água (Reúso)", c21, "m", b22),
    ]

    # Trecho B — Reservatório de Retardo
    c25 = c20
    c26 = max(0.0, float(comprimento_trecho_b_m))
    c27 = round(c26 * 1.20, 4)
    c28 = float(inclinacao_tubulacao)
    c29 = round((c28 * c27) * 10.0, 4)
    c30 = float(espessura_laje_m)
    c31 = float(interferencia_tubulacoes_m)
    c32 = float(diametro_tubulacao_m)
    c33 = round(c25 - c29 - c30 - c31 - c32, 4)
    c34 = "Cota RALO" if c33 > c21 else "Cota REUSO"
    c35 = round((c21 - 0.10) if c34.lower() == "cota reuso" else (c33 - 0.10), 4)
    c36 = round(c12 - c35, 4)
    b37 = "Subir cota de Nível" if c36 > 0 else "Descer cota de nível"

    linhas_b = [
        LinhaQuadro("Trecho B", "Comprimento do Trecho B (final do terreno até Retardo)", c26, "m", ""),
        LinhaQuadro("Trecho B", "Verdadeira cota da Tampa de Reúso", c25, "m", ""),
        LinhaQuadro("Trecho B", "Coeficiente de Segurança (1,2 × Comprimento)", c27, "m", ""),
        LinhaQuadro("Trecho B", "Inclinação da Tubulação de Ralo Terreno", c28 * 100.0, "%", f"{c28:.4f} m/m"),
        LinhaQuadro("Trecho B", "Altura Inicial × Final da Tubulação de Ralo", c29, "m", "(C28 × C27) × 10"),
        LinhaQuadro("Trecho B", "Saída Ralos no Retardo", c33, "m", f"Cota mais restritiva: {c34}"),
        LinhaQuadro("Trecho B", "Nível D'água (Retardo)", c35, "m", ""),
        LinhaQuadro("Trecho B", "Diferença Total (C12 − C35)", c36, "m", b37),
    ]

    # Trecho C — Deságue na Sarjeta
    c40 = float(cota_sarjeta_m)
    c41 = max(0.0, float(comprimento_trecho_c_m))
    c42 = float(inclinacao_tubulacao)
    c43 = round((c41 * c42) * 10.0, 4)
    c44 = round(c43 + c36 + c21, 4)
    b45 = "Subir cota de Nível" if c44 > 0 else "Descer cota de nível"

    # E48 = C40 + C43 + (C21 - C35) + (C20 - C21)
    cota_hidraulica = round(c40 + c43 + (c21 - c35) + (c20 - c21), 3)
    cota_arq = round(float(cota_terreno_arquitetura_m), 3)
    dif_cota = round(cota_arq - cota_hidraulica, 3)
    adequado = cota_arq >= cota_hidraulica
    if adequado:
        diagnostico = f"COTA DO TERRENO ADEQUADA (folga de +{dif_cota:.2f} m sobre a cota hidráulica)"
    else:
        diagnostico = (
            f"Subir cota do terreno em {abs(dif_cota):.2f} m (Cota Hidráulica {cota_hidraulica:.2f} m > Arquitetura {cota_arq:.2f} m)"
        )

    linhas_c = [
        LinhaQuadro("Trecho C", "Cota da Sarjeta", c40, "m", ""),
        LinhaQuadro("Trecho C", "Comprimento da Calçada + Distância até Retardo", c41, "m", ""),
        LinhaQuadro("Trecho C", "Inclinação da Tubulação", c42 * 100.0, "%", f"{c42:.4f} m/m"),
        LinhaQuadro("Trecho C", "Altura Inicial × Final da Tubulação", c43, "m", "(C41 × C42) × 10"),
        LinhaQuadro("Trecho C", "Cota Sarjeta × Cota do Terreno (C43 + C36 + C21)", c44, "m", b45),
        LinhaQuadro("Comparativo", "Cota do Terreno Arquitetura", cota_arq, "m", f"Desnível p/ sarjeta: {cota_arq - c40:+.2f} m"),
        LinhaQuadro("Comparativo", "Cota do Terreno Hidráulica Mínima", cota_hidraulica, "m", f"Desnível p/ sarjeta: {cota_hidraulica - c40:+.2f} m"),
        LinhaQuadro("Resultado", "Diferença (Arquitetura − Hidráulica)", dif_cota, "m", diagnostico),
    ]

    return ResultadoDesnivel(
        linhas_a=linhas_a,
        linhas_b=linhas_b,
        linhas_c=linhas_c,
        cota_terreno_arquitetura=cota_arq,
        cota_terreno_hidraulica=cota_hidraulica,
        diferenca=dif_cota,
        resultado=diagnostico,
        adequado=adequado,
    )

