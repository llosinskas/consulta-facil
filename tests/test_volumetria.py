"""Testes da Etapa 16: volumetria aproximada do edifício."""

import unittest

from domain.viabilidade_models import TipologiaPavimento
from services.geosampa_client import LOTES_EXEMPLO_SP
from services.quadro_areas_engine import (
    aplicar_tipologias_aos_pavimentos,
    calcular_quadro_areas,
    distribuir_areas_automaticas_por_terreno,
)
from services.spatial_analyzer import geometria_para_utm, processar_terreno_completo
from services.viabilidade_bridge import calcular_indices_legais, extrair_entrada_geo
from services.volumetria_engine import calcular_volumetria, raio_terreno_m

EX_VM_3_LOTES = "Vila Mariana · R. Dr. Pinto Ferraz, 285 a 299 · 3 lotes unificados"


def _poligono_utm(anel):
    return geometria_para_utm({"type": "Polygon", "coordinates": [anel]})


class TestVolumetria(unittest.TestCase):
    def setUp(self) -> None:
        ex = LOTES_EXEMPLO_SP[EX_VM_3_LOTES]
        self.terreno = processar_terreno_completo(ex["features_utm"], zona_forcada="ZM")
        entrada = extrair_entrada_geo(self.terreno, zona_override="ZM", pa_override="PA 6")
        self.indices = calcular_indices_legais(entrada, modalidade="EHIS_COTA")
        base = distribuir_areas_automaticas_por_terreno(self.indices, cota_terreno_m=790.0, qtd_pav_tipo=9)
        pavs = aplicar_tipologias_aos_pavimentos(base, [TipologiaPavimento("HIS-2", "STUDIO", 25.0, 8)])
        self.quadro = calcular_quadro_areas(pavs, self.indices, cota_terreno_m=790.0)
        self.vol = calcular_volumetria(self.terreno.geojson_unificado_wgs84, self.quadro, self.indices)

    def test_um_bloco_por_pavimento_empilhado_ate_a_altura_total(self) -> None:
        com_area = [p for i, p in enumerate(self.quadro.pavimentos) if self.quadro.total_por_pavimento[i] > 0]
        self.assertEqual(len(self.vol.pavimentos), len(com_area))
        self.assertEqual(self.vol.pavimentos[0].base_m, 0.0)
        for anterior, atual in zip(self.vol.pavimentos, self.vol.pavimentos[1:]):
            self.assertAlmostEqual(atual.base_m, anterior.base_m + anterior.altura_m, places=2)
        topo = self.vol.pavimentos[-1].base_m + self.vol.pavimentos[-1].altura_m
        self.assertAlmostEqual(topo, self.vol.altura_total_m, places=1)
        self.assertEqual(self.vol.pavimentos[1].uso_predominante, "HIS-2")
        self.assertEqual(self.vol.pavimentos[-1].uso_predominante, "Ático")

    def test_planta_respeita_recuo_projecao_e_area_de_cada_pavimento(self) -> None:
        terreno = _poligono_utm(self.vol.terreno_wgs84)
        envelope = _poligono_utm(self.vol.envelope_wgs84)
        self.assertGreater(self.vol.recuo_aplicado_m, 0)  # ZM acima de 10 m: recuo lateral de 3 m
        self.assertTrue(terreno.buffer(0.05).contains(envelope))
        self.assertLessEqual(envelope.area, self.indices.area_ocupacao_max_m2 + 0.5)
        for bloco in self.vol.pavimentos:
            planta = _poligono_utm(bloco.poligono_wgs84)
            self.assertTrue(terreno.buffer(0.05).contains(planta))
            self.assertLessEqual(planta.area, self.indices.area_ocupacao_max_m2 + 0.5)
            if bloco.base_m + bloco.altura_m > 10.0:  # torre: dentro da planta recuada
                self.assertLessEqual(planta.area, envelope.area + 0.5)
            if not bloco.limitado_pela_projecao:
                self.assertAlmostEqual(planta.area, bloco.area_quadro_m2, delta=0.5)
        self.assertAlmostEqual(
            self.vol.volume_m3, sum(b.area_m2 * b.altura_m for b in self.vol.pavimentos), places=1
        )
        self.assertGreater(raio_terreno_m(self.vol), 10)

    def test_embasamento_ate_10m_sem_recuo_lateral(self) -> None:
        # Lote estreito (6 m de largura): recuo de 3 m de cada lado só vale acima de 10 m de altura
        estreito = {"type": "Polygon", "coordinates": [[[333000, 7390000], [333006, 7390000],
                                                        [333006, 7390060], [333000, 7390060],
                                                        [333000, 7390000]]]}
        pavs = [p for p in self.quadro.pavimentos]
        for p in pavs:
            for col in list(p.areas):
                p.areas[col] = 0.0
            p.areas["c_his2"] = 200.0
        quadro = calcular_quadro_areas(pavs, self.indices, cota_terreno_m=790.0)
        vol = calcular_volumetria({"geometry": estreito}, quadro, self.indices)
        terreo = vol.pavimentos[0]
        self.assertAlmostEqual(terreo.area_m2, 200.0, delta=0.5)   # embasamento: cabe sem recuo
        self.assertFalse(terreo.limitado_pela_projecao)
        self.assertEqual(vol.recuo_aplicado_m, 0.0)                 # 6 - 2×3 = 0: torre sem área útil
        self.assertTrue(any("acima de 10 m" in a for a in vol.alertas))

    def test_gabarito_e_avisos(self) -> None:
        self.assertEqual(self.vol.gabarito_m, 28.0)  # ZM
        self.assertEqual(self.vol.atende_gabarito, self.vol.altura_total_m <= 28.0)
        self.assertTrue(any("frente" in a for a in self.vol.alertas))  # recuo de frente 5 m em ZM

    def test_pavimento_maior_que_a_planta_fica_limitado_e_avisa(self) -> None:
        pavs = [p for p in self.quadro.pavimentos]
        pavs[1].areas["nc_estacionamento"] = 5000.0
        quadro = calcular_quadro_areas(pavs, self.indices, cota_terreno_m=790.0)
        vol = calcular_volumetria(self.terreno.geojson_unificado_wgs84, quadro, self.indices)
        self.assertTrue(vol.pavimentos[1].limitado_pela_projecao)
        self.assertTrue(any("maior que a planta" in a for a in vol.alertas))

    def test_terreno_de_ate_250m2_dispensa_recuo_lateral_art_66_III(self) -> None:
        pequeno = {"type": "Polygon", "coordinates": [[[333000, 7390000], [333004, 7390000],
                                                       [333004, 7390040], [333000, 7390040],
                                                       [333000, 7390000]]]}  # 160 m²
        vol = calcular_volumetria({"geometry": pequeno}, self.quadro, self.indices)
        self.assertEqual(vol.recuo_aplicado_m, 0.0)
        self.assertTrue(any("art. 66, III" in a for a in vol.alertas))

    def test_frente_de_ate_10m_dispensa_recuo_mesmo_em_terreno_grande(self) -> None:
        com_frente = calcular_volumetria(
            self.terreno.geojson_unificado_wgs84, self.quadro, self.indices, frente_m=9.5
        )
        self.assertEqual(com_frente.recuo_aplicado_m, 0.0)
        self.assertTrue(any("art. 66, III" in a for a in com_frente.alertas))
        sem_frente = calcular_volumetria(
            self.terreno.geojson_unificado_wgs84, self.quadro, self.indices, frente_m=25.0
        )
        self.assertEqual(sem_frente.recuo_aplicado_m, 3.0)

    def test_zona_com_recuo_ate_10m_recua_tambem_o_embasamento(self) -> None:
        from dataclasses import replace
        indices_zpi = replace(self.indices, zona="ZPI-1", recuo_ate_10m="3", recuo_acima_10m="3")
        vol = calcular_volumetria(self.terreno.geojson_unificado_wgs84, self.quadro, indices_zpi, frente_m=25.0)
        terreno = _poligono_utm(vol.terreno_wgs84)
        terreo = _poligono_utm(vol.pavimentos[0].poligono_wgs84)
        recuado = terreno.buffer(-3.0, join_style=2)
        self.assertTrue(recuado.buffer(0.05).contains(terreo))

if __name__ == "__main__":
    unittest.main()
