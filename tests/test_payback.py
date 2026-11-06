"""Fluxo de caixa e payback, com valores conferidos à mão."""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.payback import (
    EntradaPayback,
    _curva_s,
    calcular_payback,
    mes_payback,
    sensibilidade_payback,
    tir_anual,
)


def caso_simples(**kw):
    """VGV 2.000 recebido à vista no mês 2; obra 1.000 no mês 1; terreno 200 no mês 0; sem outros custos."""
    base = dict(
        area_privativa_m2=100.0, preco_venda_m2=20.0, area_construida_m2=100.0, custo_obra_m2=10.0, custo_terreno=200.0,
        projetos_pct_obra=0.0, administracao_pct_obra=0.0, comercial_pct_vgv=0.0, impostos_pct_receita=0.0,
        mes_lancamento=2, mes_inicio_obra=1, duracao_obra_meses=1, vendas_lancamento_pct=1.0, duracao_vendas_meses=0,
        recebido_ate_chaves_pct=0.0, meses_repasse_apos_chaves=0, tma_anual=0.0,
    )
    base.update(kw)
    return EntradaPayback(**base)


class TestFuncoes(unittest.TestCase):
    def test_curva_s_soma_um_e_tem_pico_no_meio(self):
        pesos = _curva_s(24)
        self.assertAlmostEqual(sum(pesos), 1)
        self.assertGreater(pesos[12], pesos[0])
        self.assertEqual(_curva_s(1), [1.0])

    def test_payback_usa_a_ultima_virada(self):
        self.assertEqual(mes_payback([-10, 5, -2, 3, 4]), 3)  # volta a ficar negativo no mês 2
        self.assertIsNone(mes_payback([-10, 5, -2]))
        self.assertEqual(mes_payback([1, 2]), 0)
        self.assertIsNone(mes_payback([]))

    def test_tir_conhecida(self):
        # −100 hoje e +110 em 1 mês: 10% ao mês, ou 1,1^12 − 1 ao ano
        self.assertAlmostEqual(tir_anual([-100, 110]), 1.1 ** 12 - 1, places=6)
        self.assertIsNone(tir_anual([-100, -50]))


class TestFluxo(unittest.TestCase):
    def test_caso_a_mao(self):
        r = calcular_payback(caso_simples())
        self.assertEqual([round(m.saldo) for m in r.meses], [-200, -1000, 2000])
        self.assertEqual([round(m.acumulado) for m in r.meses], [-200, -1200, 800])
        self.assertAlmostEqual(r.lucro, 800)
        self.assertAlmostEqual(r.vgv, 2000)
        self.assertAlmostEqual(r.custo_total, 1200)
        self.assertAlmostEqual(r.margem_vgv, 0.4)
        self.assertAlmostEqual(r.exposicao_maxima, -1200)
        self.assertEqual(r.mes_exposicao_maxima, 1)
        self.assertEqual(r.payback_simples_mes, 2)

    def test_lucro_igual_a_receita_menos_custos_em_caso_completo(self):
        e = EntradaPayback(area_privativa_m2=8000, preco_venda_m2=9000, area_construida_m2=15000, custo_obra_m2=3500,
                           custo_terreno=6e6, terreno_entrada_pct=0.3, terreno_parcelas_meses=12, outorga=2e6)
        r = calcular_payback(e)
        self.assertAlmostEqual(sum(m.entradas for m in r.meses), r.vgv, places=2)
        self.assertAlmostEqual(sum(m.saidas for m in r.meses), r.custo_total, places=2)
        self.assertAlmostEqual(r.lucro, r.vgv - r.custo_total, places=2)
        self.assertAlmostEqual(r.custos_por_grupo["Impostos"], r.vgv * 0.04, places=2)
        self.assertAlmostEqual(r.custos_por_grupo["Comercial"], r.vgv * 0.06, places=2)

    def test_venda_depois_das_chaves_recebe_no_mes_da_venda(self):
        e = caso_simples(mes_lancamento=5, recebido_ate_chaves_pct=0.3)
        r = calcular_payback(e)
        self.assertAlmostEqual(r.meses[5].entradas, 2000)

    def test_tma_atrasa_o_payback_e_reduz_o_vpl(self):
        e = EntradaPayback(area_privativa_m2=8000, preco_venda_m2=12000, area_construida_m2=15000, custo_obra_m2=3500, custo_terreno=6e6)
        r = calcular_payback(e)
        self.assertLess(r.vpl, r.lucro)
        self.assertGreaterEqual(r.payback_descontado_mes, r.payback_simples_mes)

    def test_projeto_com_prejuizo_nao_tem_payback(self):
        r = calcular_payback(caso_simples(custo_terreno=5000.0))
        self.assertIsNone(r.payback_simples_mes)
        self.assertLess(r.lucro, 0)

    def test_outorga_cai_no_lancamento(self):
        r = calcular_payback(caso_simples(outorga=100.0))
        self.assertAlmostEqual(r.meses[2].saidas, 100)

    def test_sensibilidade_tem_todas_as_celulas_e_prazo_move_o_payback(self):
        e = EntradaPayback(area_privativa_m2=8000, preco_venda_m2=12000, area_construida_m2=15000, custo_obra_m2=3500, custo_terreno=6e6)
        linhas = sensibilidade_payback(e)
        self.assertEqual(len(linhas), 25)
        por_chave = {(l["preco"], l["prazo"]): l for l in linhas}
        base = por_chave[(0.0, 0)]
        self.assertGreater(por_chave[(0.2, 0)]["lucro"], base["lucro"])
        self.assertEqual(por_chave[(0.0, 6)]["payback"], base["payback"] + 6)
        self.assertEqual(por_chave[(0.0, -6)]["payback"], base["payback"] - 6)

    def test_sensibilidade_mostra_quando_o_projeto_nao_se_paga(self):
        e = EntradaPayback(area_privativa_m2=8000, preco_venda_m2=10000, area_construida_m2=15000, custo_obra_m2=3500, custo_terreno=6e6)
        por_chave = {(l["preco"], l["prazo"]): l for l in sensibilidade_payback(e)}
        self.assertIsNone(por_chave[(-0.2, 0)]["payback"])

    def test_alerta_quando_payback_coincide_com_repasse(self):
        e = EntradaPayback(area_privativa_m2=8000, preco_venda_m2=12000, area_construida_m2=15000, custo_obra_m2=3500, custo_terreno=6e6)
        self.assertTrue(any("coincide com o repasse" in a for a in calcular_payback(e).alertas))

    def test_entradas_invalidas(self):
        for kw in ({"preco_venda_m2": 0.0}, {"custo_terreno": -1.0}, {"duracao_obra_meses": 0},
                   {"vendas_lancamento_pct": 1.5}, {"mes_lancamento": -1}):
            with self.assertRaises(ValueError, msg=str(kw)):
                calcular_payback(caso_simples(**kw))


if __name__ == "__main__":
    unittest.main()
