"""
Tabelas legais de São Paulo usadas nas contas de aproveitamento do terreno.

Conferidas em 05/11/2026 contra os anexos publicados no site da Câmara Municipal
(plpconsulta.saopaulo.sp.leg.br), exceto onde indicado:
- Quadro 3 e Quadro 3A: Lei 16.402/2016 (LPUOS), com as alterações da Lei 18.081/2024.
- Quadro 5: Lei 16.050/2014 (PDE), com a redação da Lei 17.975/2023.
- Quadro 6: PDE; Fp = 2 em ZEM e ZEMP pelo art. 8º, § 3º, da LPUOS.
- CA EHIS/EHMP: Quadro 2 do Decreto 63.728/2024, ATENÇÃO: transcrito da planilha Yonder
  (aba DADOS). O anexo do decreto não pôde ser lido; os valores batem com as regras de
  +50% / +25% do PDE (Quadro 2, nota "a"), mas devem ser conferidos.
"""

import re
import unicodedata
from dataclasses import dataclass
from typing import Dict, Optional, Tuple


@dataclass(frozen=True)
class ParametrosZonaLei:
    sigla: str
    nome: str
    ca_minimo: Optional[float]           # None = NA
    ca_basico: Optional[float]           # None = sem índice próprio (AVP-1, art. 30)
    ca_maximo: Optional[float]
    to_lote_menor_500: Optional[float]   # lote < 500 m²
    to_lote_500_ou_mais: Optional[float]  # lote >= 500 m²
    gabarito_m: Optional[float]          # None = sem limite (NA)
    recuo_frente_m: float                # 0 = NA
    recuo_ate_10m: float                 # laterais e fundo, altura <= 10 m (0 = NA)
    recuo_acima_10m: float               # laterais e fundo, altura > 10 m
    cota_parte_m2: Optional[float]       # None = NA
    ca_ehis: Optional[float]             # None = EHIS não previsto no Quadro 2 do decreto
    ca_ehmp: Optional[float]


def _z(sigla, nome, ca_min, ca_bas, ca_max, to_p, to_g, gab, frente, rec10, rec_mais,
       q=None, ehis=None, ehmp=None) -> ParametrosZonaLei:
    return ParametrosZonaLei(sigla, nome, ca_min, ca_bas, ca_max, to_p, to_g, gab, frente,
                             rec10, rec_mais, q, ehis, ehmp)


_ZONAS = [
    # sigla, nome, CAmin, CAbás, CAmáx, TO<500, TO>=500, gabarito, frente, lat<=10, lat>10, Q, EHIS, EHMP
    _z("ZEU", "Eixo de Estruturação da Transformação Urbana", .5, 1, 4, .85, .70, None, 0, 0, 3, 20, 6, 5),
    _z("ZEUa", "Eixo de Estruturação da Transformação Urbana Ambiental", None, 1, 2, .70, .50, 28, 0, 0, 3, 40, 3, 2.5),
    _z("ZEUP", "Eixo de Estruturação da Transformação Urbana Previsto", .5, 1, 2, .85, .70, 28, 0, 0, 3, None, 3, 2.5),
    _z("ZEUPa", "Eixo de Estruturação da Transformação Urbana Previsto Ambiental", None, 1, 1, .70, .50, 28, 0, 0, 3, None, 1.5, 1.25),
    _z("ZEM", "Eixo de Estruturação da Transformação Metropolitana", .5, 1, 2, .85, .70, 28, 0, 0, 3, 20, 3, 2.5),
    _z("ZEMP", "Eixo de Estruturação da Transformação Metropolitana Previsto", .5, 1, 2, .85, .70, 28, 0, 0, 3, 40, 3, 2.5),
    _z("ZC", "Centralidade", .3, 1, 2, .85, .70, 48, 5, 0, 3, None, 3, 2.5),
    _z("ZCa", "Centralidade Ambiental", None, 1, 1, .70, .70, 20, 5, 0, 3, None, 1.5, 1.25),
    _z("ZC-ZEIS", "Centralidade lindeira à ZEIS", .5, 1, 2, .85, .70, None, 5, 0, 3, None, 3, 2.5),
    _z("ZCOR-1", "Corredor 1", .05, 1, 1, .50, .50, 10, 5, 0, 3, None, 1.5, 1.25),
    _z("ZCOR-2", "Corredor 2", .05, 1, 1, .50, .50, 10, 5, 0, 3, None, 1.5, 1.25),
    _z("ZCOR-3", "Corredor 3", .05, 1, 1, .50, .50, 10, 5, 0, 3, None, 1.5, 1.25),
    _z("ZCORa", "Corredor Ambiental", None, 1, 1, .50, .50, 10, 5, 0, 3, None, 1.5, 1.25),
    _z("ZM", "Mista", .3, 1, 2, .85, .70, 28, 5, 0, 3, None, 3, 2.5),
    _z("ZMa", "Mista Ambiental", None, 1, 1, .70, .50, 15, 5, 0, 3, None, 1.5, 1.25),
    _z("ZMIS", "Mista de Interesse Social", .3, 1, 2, .85, .70, 28, 5, 0, 3, None, 3, 2.5),
    _z("ZMISa", "Mista de Interesse Social Ambiental", None, 1, 1, .70, .50, 15, 5, 0, 3, None, 1.5, 1.25),
    _z("ZEIS-1", "Especial de Interesse Social 1", .5, 1, 2.5, .85, .70, None, 5, 0, 3, None, 2.5, None),
    _z("ZEIS-2", "Especial de Interesse Social 2", .5, 1, 4, .85, .70, None, 5, 0, 3, None, 4, None),
    _z("ZEIS-3", "Especial de Interesse Social 3", .5, 1, 4, .85, .70, None, 5, 0, 3, None, 4, None),
    _z("ZEIS-4", "Especial de Interesse Social 4", None, 1, 2, .70, .50, None, 5, 0, 3, None, 2, None),
    _z("ZEIS-5", "Especial de Interesse Social 5", .5, 1, 4, .85, .70, None, 5, 0, 3, None, 4, None),
    _z("ZDE-1", "Desenvolvimento Econômico 1", .5, 1, 2, .70, .70, 28, 5, 0, 3, None, 3, 2.5),
    _z("ZDE-2", "Desenvolvimento Econômico 2", .5, 1, 2, .70, .50, 28, 5, 3, 3, None, 3, 2.5),
    _z("ZPI-1", "Predominantemente Industrial 1", .5, 1, 1.5, .70, .70, 28, 5, 3, 3, None, 2.25, 1.875),
    _z("ZPI-2", "Predominantemente Industrial 2", None, 1, 1.5, .50, .50, 28, 5, 3, 3, None, 2.25, 1.875),
    _z("ZPR", "Predominantemente Residencial", .05, 1, 1, .50, .50, 10, 5, 0, 3),
    _z("ZER-1", "Exclusivamente Residencial 1", .05, 1, 1, .50, .50, 10, 5, 0, 3),
    _z("ZER-2", "Exclusivamente Residencial 2", .05, 1, 1, .50, .50, 10, 5, 0, 3),
    _z("ZERa", "Exclusivamente Residencial Ambiental", None, 1, 1, .50, .50, 10, 5, 0, 3),
    _z("ZPDS", "Preservação e Desenvolvimento Sustentável", None, 1, 1, .35, .25, 20, 5, 0, 3),
    _z("ZPDSr", "Preservação e Desenvolvimento Sustentável Rural", None, .2, .2, .20, .15, 10, 5, 0, 3),
    _z("ZEPAM", "Especial de Preservação Ambiental", None, .1, .1, .10, .10, 10, 5, 0, 3),
    _z("AVP-1", "Área Verde Pública 1 (ver art. 30 da LPUOS)", None, None, None, None, None, 28, 0, 0, 3),
    _z("AVP-2", "Área Verde Pública 2", None, 1, 1, .30, .30, 28, 0, 0, 3),
    _z("AI", "Área Institucional", None, 1, 4, .85, .70, 28, 0, 0, 3),
    _z("AIa", "Área Institucional Ambiental", None, 1, 2, .50, .50, 15, 0, 0, 3),
    _z("AC-1", "Clubes Esportivos e Sociais", None, .6, .6, .60, .60, 20, 5, 3, 3),
    _z("AC-2", "Clubes de Campo e Clube Náutico", None, .4, .4, .40, .40, 10, 5, 3, 3),
]

QUADRO_3: Dict[str, ParametrosZonaLei] = {z.sigla: z for z in _ZONAS}


def _chave_zona(texto: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", texto.upper())


_POR_CHAVE: Dict[str, str] = {_chave_zona(s): s for s in QUADRO_3}


def normalizar_zona(texto: Optional[str]) -> Optional[str]:
    """Devolve a sigla oficial ('ZEUP (b)' → 'ZEUP', 'ZEIS 1' → 'ZEIS-1') ou None se a zona não constar do Quadro 3."""
    if not texto:
        return None
    sem_nota = re.sub(r"\(.*?\)", "", texto.replace("\xa0", " "))
    return _POR_CHAVE.get(_chave_zona(sem_nota))


# Quadro 3A — por PA: (TP lote <= 500, TP lote > 500, QA mínimo nas 5 faixas de área)
QUADRO_3A: Dict[str, Tuple[float, float, Tuple[float, float, float, float, float]]] = {
    "PA 1": (.15, .25, (.45, .60, .70, .80, 1.00)),
    "PA 2": (.15, .25, (.40, .52, .64, .70, .86)),
    "PA 3": (.15, .25, (.37, .48, .60, .65, .78)),
    "PA 4": (.15, .25, (.37, .48, .60, .65, .78)),
    "PA 5": (.15, .25, (.29, .37, .46, .50, .57)),
    "PA 6": (.15, .20, (.34, .44, .55, .60, .71)),
    "PA 7": (.15, .20, (.31, .41, .51, .55, .64)),
    "PA 8": (.15, .20, (.37, .48, .60, .65, .78)),
    "PA 9": (.10, .15, (.37, .48, .60, .65, .78)),
    "PA 10": (.20, .25, (.23, .30, .37, .40, .42)),
    "PA 11": (.20, .30, (.26, .34, .42, .45, .49)),
    "PA 12": (.20, .30, (.26, .34, .42, .45, .49)),
}
PA_SEM_QUOTA_AMBIENTAL = "PA 13"  # Nota (c): Contenção Urbana e Preservação de Ecossistemas

# Nota (a) do Quadro 3A: taxa fixa, independente do tamanho do lote
TP_FIXA_POR_ZONA: Dict[str, float] = {
    "ZEPAM": .90, "ZPDSr": .70, "ZPDS": .50,
    "ZCOR-1": .30, "ZCOR-2": .30, "ZCOR-3": .30, "ZCORa": .30,
    "ZPR": .30, "ZER-1": .30, "ZER-2": .30, "ZERa": .30,
}

TP_SEM_PA = (.20, .30)  # maior taxa do Quadro 3A, usada enquanto o PA não é informado


def taxa_permeabilidade(zona: Optional[str], pa: Optional[str], area_lote_m2: float) -> Optional[float]:
    """Quadro 3A: faixas ≤ 500 / > 500 m². None em PA 13. Sem PA informado, usa a maior taxa do quadro."""
    if zona in TP_FIXA_POR_ZONA:
        return TP_FIXA_POR_ZONA[zona]
    if pa == PA_SEM_QUOTA_AMBIENTAL:
        return None
    menor, maior = QUADRO_3A[pa][:2] if pa in QUADRO_3A else TP_SEM_PA
    return menor if area_lote_m2 <= 500 else maior


def extrair_pa(texto: Optional[str]) -> Optional[str]:
    """'PA 6 (Perímetro ...)', 'PA-06' ou 'PA6' → 'PA 6'. Devolve None se não houver PA válido."""
    if not texto:
        return None
    achado = re.search(r"\bPA[\s\-_]*0*(\d{1,2})\b", texto.replace("\xa0", " "), re.IGNORECASE)
    if not achado:
        return None
    numero = int(achado.group(1))
    return f"PA {numero}" if 1 <= numero <= 13 else None


# Quadro 5 — Fator de interesse social, usos mais comuns em estudo de massa
FATORES_FS: Dict[str, float] = {
    "HIS": 0.0,
    "HMP até 50 m²": 0.4,
    "HMP de 51 a 70 m²": 0.6,
    "Habitação até 30 m²": 1.0,
    "Habitação de 30 a 70 m²": 0.8,
    "Habitação acima de 70 m²": 1.0,
    "Outras atividades (não residencial)": 1.0,
}

# Quadro 6 — Fator de planejamento: (Fp residencial, Fp não residencial)
QUADRO_6: Dict[str, Tuple[float, float]] = {
    "MEM - Noroeste": (.3, 0),
    "MEM - Arco Jacu-Pêssego": (.3, 0),
    "MEM - Avenida Cupecê": (.3, 0),
    "MEM - Arco Leste": (.3, 0),
    "MEM - Fernão Dias": (.3, 0),
    "MEM - Arco Tietê": (1.2, 1.3),
    "MEM - Centro": (1.2, 1.3),
    "MEM - Arco Tamanduateí": (1.2, 1.3),
    "MEM - Arco Pinheiros": (1.2, 1.3),
    "MEM - Arco Jurubatuba": (1.2, 1.3),
    "Urbanização Consolidada": (.7, 1.3),
    "Qualificação Urbana": (.6, .5),
    "Redução da Vulnerabilidade": (.3, 0),
    "Redução da Vulnerabilidade Urbana e Recuperação Ambiental": (1.0, 0),
    "Controle e Qualificação Urbana e Ambiental": (1.0, 0),
}
FP_ZEM_ZEMP = 2.0  # LPUOS art. 8º, § 3º; Decreto 63.504/2024 art. 3º, § 8º


def _sem_acento(texto: str) -> str:
    base = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in base if not unicodedata.combining(c)).lower()


def identificar_macroarea_fp(texto: Optional[str]) -> Optional[str]:
    """
    Associa o texto da macroárea do GeoSampa a uma linha do Quadro 6.
    Devolve None se for ambíguo: 'Estruturação Metropolitana' sem o subsetor não define o Fp (0,3 ou 1,2).
    """
    if not texto:
        return None
    alvo = _sem_acento(texto)
    if "recuperacao ambiental" in alvo:
        return "Redução da Vulnerabilidade Urbana e Recuperação Ambiental"
    for chave, trecho in (
        ("Controle e Qualificação Urbana e Ambiental", "controle e qualificacao"),
        ("Urbanização Consolidada", "urbanizacao consolidada"),
        ("Qualificação Urbana", "qualificacao da urbanizacao"),
        ("Qualificação Urbana", "qualificacao urbana"),
        ("Redução da Vulnerabilidade", "reducao da vulnerabilidade"),
    ):
        if trecho in alvo:
            return chave
    for chave in QUADRO_6:
        if chave.startswith("MEM - ") and _sem_acento(chave[6:]) in alvo:
            return chave
    return None
