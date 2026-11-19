"""Sessão aberta antes de um deploy: objetos da versão anterior não podem quebrar o app."""

import unittest
from dataclasses import dataclass, field
from typing import Any, Dict, List

import domain.models as modelos
from domain.models import completar_campos_novos


def _classe_antiga():
    # Simula o ResultadoTerreno de uma versão anterior (sem confirmacao_zona e outros campos novos)
    @dataclass
    class ResultadoTerreno:
        lotes: List[Any]
        area_total_m2: float
        avisos: List[str] = field(default_factory=list)

    @dataclass
    class LoteIndividual:
        setor: str
        atributos_brutos: Dict[str, Any] = field(default_factory=dict)

    return ResultadoTerreno, LoteIndividual


class TestMigracaoDeSessao(unittest.TestCase):
    def test_completa_campos_novos_pela_classe_atual(self):
        Antigo, LoteAntigo = _classe_antiga()
        antigo = Antigo(lotes=[LoteAntigo("039")], area_total_m2=419.0)
        self.assertFalse(hasattr(antigo, "confirmacao_zona"))

        completar_campos_novos(antigo)

        self.assertIsNone(antigo.confirmacao_zona)          # campo novo com default None
        self.assertEqual(antigo.zonas_detectadas, [])        # default_factory
        self.assertEqual(antigo.area_total_m2, 419.0)        # valores existentes preservados
        self.assertEqual(antigo.lotes[0].zona_incidente, None)  # dataclass aninhado também
        self.assertEqual(antigo.lotes[0].setor, "039")

    def test_objeto_atual_e_outros_tipos_ficam_intactos(self):
        self.assertIsNone(completar_campos_novos(None))
        self.assertEqual(completar_campos_novos({"a": 1}), {"a": 1})
        self.assertIsNotNone(modelos.ResultadoTerreno)


if __name__ == "__main__":
    unittest.main()
