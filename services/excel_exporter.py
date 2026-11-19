"""
Exportador nativo de planilha Excel (.xlsx) com estilização completa OpenXML (`xl/styles.xml`),
cores por categoria/status, listras zebra, largura automática de colunas, abas coloridas
e barras de Gantt coloridas na aba `CRONOGRAMA`.
"""

import io
import zipfile
from html import escape
from typing import Any, Dict, List, Optional, Sequence, Tuple

# Cores de cada aba (formato ARGB Hex de 8 dígitos para OpenXML)
TAB_COLORS: Dict[str, str] = {
    "Q. ÁREAS": "FF1E3A8A",     # Azul Marinho
    "Q. LUOPS": "FF4338CA",     # Índigo
    "Q. ANEXOS": "FF0F766E",    # Teal
    "CALC. ÁGUA": "FF0284C7",   # Azul Celeste
    "ELEVADOR": "FF6D28D9",     # Violeta
    "DADOS": "FF475569",        # Cinza Ardósia
    "DESNÍVEL": "FF0891B2",     # Ciano
    "FINANCEIRO": "FF059669",   # Verde Esmeralda
    "CRONOGRAMA": "FFD97706",   # Âmbar / Laranja
    "ELÉTRICA": "FFEAB308",     # Ouro / Amarelo Elétrico
}

# Índices de estilo (cellXfs em xl/styles.xml)
STYLE_DEFAULT = 0
STYLE_TITLE_BANNER = 1
STYLE_TABLE_HEADER = 2
STYLE_TEXT_EVEN = 3
STYLE_TEXT_ODD = 4
STYLE_NUM_EVEN = 5
STYLE_NUM_ODD = 6
STYLE_INT_EVEN = 7
STYLE_INT_ODD = 8
STYLE_TOTAL_TEXT = 9
STYLE_TOTAL_NUM = 10
STYLE_STATUS_OK = 11
STYLE_STATUS_WARN = 12
STYLE_GANTT_PRE = 13
STYLE_GANTT_OBRA = 14
STYLE_GANTT_EMPTY = 15
STYLE_CURVA_S = 16
STYLE_KEY_LABEL = 17


# ---------------------------------------------------------------------------
# Cores por tipologia: cada categoria de unidade tem uma cor própria em todas as abas.
# Detectada pelo texto do cabeçalho da coluna (ex.: "COMP. HIS-2", "N.COMP. HIS-1 (50%)") ou,
# em tabelas com coluna "CATEGORIA", pelo valor da categoria na linha.
# (nome, trecho procurado em caixa alta, cor forte do cabeçalho, cor clara dos dados)
# A ordem importa: variantes ("HIS-2 (COTA") vêm antes da categoria base ("HIS-2").
# ---------------------------------------------------------------------------
CORES_TIPOLOGIA: List[Tuple[str, str, str, str]] = [
    ("HIS-2 (Cota Solid.)", "HIS-2 (COTA", "FF0E7490", "FFCFFAFE"),     # ciano
    ("HIS-1 (50%)", "HIS-1 (50%", "FF4D7C0F", "FFECFCCB"),              # verde-oliva
    ("R2V-1 (10% incentivo)", "R2V-1 (10%", "FF4338CA", "FFE0E7FF"),    # índigo
    ("NR1-12", "NR1-12", "FF7E22CE", "FFF3E8FF"),                       # roxo
    ("NR1-3 (Fachada Ativa)", "NR1-3", "FFBE185D", "FFFCE7F3"),         # rosa
    ("HIS-2", "HIS-2", "FF1D4ED8", "FFDBEAFE"),                         # azul
    ("HIS-1", "HIS-1", "FF047857", "FFD1FAE5"),                         # esmeralda
    ("R2V-1", "R2V-1", "FFC2410C", "FFFFEDD5"),                         # laranja
]
_BASE_FILLS = 13
_BASE_XFS = 18
# Para a família i: cabeçalho, inteiro, decimal, texto e total (5 estilos)
_XFS_POR_FAMILIA = 5


def familia_tipologia(texto: Any) -> Optional[int]:
    """Índice em CORES_TIPOLOGIA da tipologia citada no texto (cabeçalho ou categoria), ou None."""
    if not isinstance(texto, str):
        return None
    alvo = texto.upper().replace("\xa0", " ")
    for i, (_, trecho, _, _) in enumerate(CORES_TIPOLOGIA):
        if trecho in alvo:
            return i
    return None


def estilo_tipologia(familia: int, papel: str) -> int:
    """Índice do estilo (cellXfs) da tipologia para o papel: header, int, num, text ou total."""
    deslocamento = {"header": 0, "int": 1, "num": 2, "text": 3, "total": 4}[papel]
    return _BASE_XFS + familia * _XFS_POR_FAMILIA + deslocamento


def _fills_tipologia_xml() -> str:
    return "".join(
        f'<fill><patternFill patternType="solid"><fgColor rgb="{forte}"/><bgColor indexed="64"/></patternFill></fill>'
        f'<fill><patternFill patternType="solid"><fgColor rgb="{clara}"/><bgColor indexed="64"/></patternFill></fill>'
        for _, _, forte, clara in CORES_TIPOLOGIA
    )


def _xfs_tipologia_xml() -> str:
    partes = []
    for i in range(len(CORES_TIPOLOGIA)):
        fill_forte, fill_clara = _BASE_FILLS + 2 * i, _BASE_FILLS + 2 * i + 1
        partes += [
            # cabeçalho: branco negrito sobre a cor forte
            f'<xf numFmtId="0" fontId="2" fillId="{fill_forte}" borderId="3" xfId="0" applyFont="1" applyFill="1" '
            'applyBorder="1" applyAlignment="1"><alignment vertical="center" horizontal="center" wrapText="1"/></xf>',
            # inteiro
            f'<xf numFmtId="165" fontId="0" fillId="{fill_clara}" borderId="1" xfId="0" applyNumberFormat="1" '
            'applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment vertical="center" horizontal="center"/></xf>',
            # decimal
            f'<xf numFmtId="164" fontId="0" fillId="{fill_clara}" borderId="1" xfId="0" applyNumberFormat="1" '
            'applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment vertical="center" horizontal="right"/></xf>',
            # texto
            f'<xf numFmtId="0" fontId="0" fillId="{fill_clara}" borderId="1" xfId="0" applyFont="1" applyFill="1" '
            'applyBorder="1" applyAlignment="1"><alignment vertical="center" wrapText="1"/></xf>',
            # total: negrito sobre a cor clara com a borda de total
            f'<xf numFmtId="164" fontId="3" fillId="{fill_clara}" borderId="2" xfId="0" applyNumberFormat="1" '
            'applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment vertical="center" horizontal="right"/></xf>',
        ]
    return "".join(partes)


def _col_letter(col_idx_1based: int) -> str:
    result = ""
    n = col_idx_1based
    while n > 0:
        n, rem = divmod(n - 1, 26)
        result = chr(65 + rem) + result
    return result


def _styles_xml() -> str:
    """
    Constrói o arquivo `xl/styles.xml` com fontes, preenchimentos (fills), bordas,
    formatos numéricos (`#,##0.00` e `#,##0`) e os 18 estilos (`cellXfs`).
    """
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        # Formatos numéricos customizados
        '<numFmts count="2">'
        '<numFmt numFmtId="164" formatCode="#,##0.00"/>'
        '<numFmt numFmtId="165" formatCode="#,##0"/>'
        '</numFmts>'
        # Fontes (0..7)
        '<fonts count="8">'
        # 0: Padrão texto (Segoe UI 10pt escuro)
        '<font><sz val="10"/><color rgb="FF0F172A"/><name val="Segoe UI"/></font>'
        # 1: Título Banner (Segoe UI 11.5pt Negrito Branco)
        '<font><b/><sz val="11.5"/><color rgb="FFFFFFFF"/><name val="Segoe UI"/></font>'
        # 2: Cabeçalho de Tabela (Segoe UI 10pt Negrito Branco)
        '<font><b/><sz val="10"/><color rgb="FFFFFFFF"/><name val="Segoe UI"/></font>'
        # 3: Subtotal / Total (Segoe UI 10pt Negrito Marrom/Âmbar Escuro)
        '<font><b/><sz val="10"/><color rgb="FF78350F"/><name val="Segoe UI"/></font>'
        # 4: Status OK / Curva S (Segoe UI 10pt Negrito Verde Escuro)
        '<font><b/><sz val="10"/><color rgb="FF166534"/><name val="Segoe UI"/></font>'
        # 5: Status Alerta (Segoe UI 10pt Negrito Vermelho Escuro)
        '<font><b/><sz val="10"/><color rgb="FF991B1B"/><name val="Segoe UI"/></font>'
        # 6: Barra Gantt Ativa (Segoe UI 9.5pt Negrito Branco)
        '<font><b/><sz val="9.5"/><color rgb="FFFFFFFF"/><name val="Segoe UI"/></font>'
        # 7: Chave / Label Destacado (Segoe UI 10pt Negrito Azul Escuro)
        '<font><b/><sz val="10"/><color rgb="FF1E3A8A"/><name val="Segoe UI"/></font>'
        '</fonts>'
        # Preenchimentos / Fills (0..12)
        f'<fills count="{_BASE_FILLS + 2 * len(CORES_TIPOLOGIA)}">'
        '<fill><patternFill patternType="none"/></fill>'
        '<fill><patternFill patternType="gray125"/></fill>'
        # 2: Banner Azul Marinho (#1E3A8A)
        '<fill><patternFill patternType="solid"><fgColor rgb="FF1E3A8A"/><bgColor indexed="64"/></patternFill></fill>'
        # 3: Cabeçalho Tabela Azul-Ardósia (#334155)
        '<fill><patternFill patternType="solid"><fgColor rgb="FF334155"/><bgColor indexed="64"/></patternFill></fill>'
        # 4: Linha Par Branca (#FFFFFF)
        '<fill><patternFill patternType="solid"><fgColor rgb="FFFFFFFF"/><bgColor indexed="64"/></patternFill></fill>'
        # 5: Linha Ímpar Zebra Gelo (#F1F5F9)
        '<fill><patternFill patternType="solid"><fgColor rgb="FFF1F5F9"/><bgColor indexed="64"/></patternFill></fill>'
        # 6: Subtotal / Total Âmbar Suave (#FEF3C7)
        '<fill><patternFill patternType="solid"><fgColor rgb="FFFEF3C7"/><bgColor indexed="64"/></patternFill></fill>'
        # 7: Status OK Verde Suave (#DCFCE7)
        '<fill><patternFill patternType="solid"><fgColor rgb="FFDCFCE7"/><bgColor indexed="64"/></patternFill></fill>'
        # 8: Status Alerta Vermelho Suave (#FEE2E2)
        '<fill><patternFill patternType="solid"><fgColor rgb="FFFEE2E2"/><bgColor indexed="64"/></patternFill></fill>'
        # 9: Gantt Pré-Obra Índigo (#4F46E5)
        '<fill><patternFill patternType="solid"><fgColor rgb="FF4F46E5"/><bgColor indexed="64"/></patternFill></fill>'
        # 10: Gantt Execução Obra Azul Real (#2563EB)
        '<fill><patternFill patternType="solid"><fgColor rgb="FF2563EB"/><bgColor indexed="64"/></patternFill></fill>'
        # 11: Curva S Esmeralda Suave (#D1FAE5)
        '<fill><patternFill patternType="solid"><fgColor rgb="FFD1FAE5"/><bgColor indexed="64"/></patternFill></fill>'
        # 12: Chave / Label Azul Claro (#EFF6FF)
        '<fill><patternFill patternType="solid"><fgColor rgb="FFEFF6FF"/><bgColor indexed="64"/></patternFill></fill>'
        + _fills_tipologia_xml()
        + '</fills>'
        # Bordas (0..3)
        '<borders count="4">'
        # 0: Sem borda
        '<border><left/><right/><top/><bottom/><diagonal/></border>'
        # 1: Borda fina cinza suave (#CBD5E1)
        '<border>'
        '<left style="thin"><color rgb="FFCBD5E1"/></left>'
        '<right style="thin"><color rgb="FFCBD5E1"/></right>'
        '<top style="thin"><color rgb="FFCBD5E1"/></top>'
        '<bottom style="thin"><color rgb="FFCBD5E1"/></bottom>'
        '<diagonal/>'
        '</border>'
        # 2: Borda Total / Subtotal (topo médio + base dupla âmbar)
        '<border>'
        '<left style="thin"><color rgb="FFF59E0B"/></left>'
        '<right style="thin"><color rgb="FFF59E0B"/></right>'
        '<top style="medium"><color rgb="FFD97706"/></top>'
        '<bottom style="double"><color rgb="FFD97706"/></bottom>'
        '<diagonal/>'
        '</border>'
        # 3: Borda Cabeçalho
        '<border>'
        '<left style="thin"><color rgb="FF475569"/></left>'
        '<right style="thin"><color rgb="FF475569"/></right>'
        '<top style="thin"><color rgb="FF1E293B"/></top>'
        '<bottom style="medium"><color rgb="FF0F172A"/></bottom>'
        '<diagonal/>'
        '</border>'
        '</borders>'
        '<cellStyleXfs count="1">'
        '<xf numFmtId="0" fontId="0" fillId="0" borderId="0"/>'
        '</cellStyleXfs>'
        # 18 Estilos de Célula (cellXfs 0..17)
        f'<cellXfs count="{_BASE_XFS + _XFS_POR_FAMILIA * len(CORES_TIPOLOGIA)}">'
        # 0: STYLE_DEFAULT
        '<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
        # 1: STYLE_TITLE_BANNER
        '<xf numFmtId="0" fontId="1" fillId="2" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1">'
        '<alignment vertical="center" horizontal="left"/>'
        '</xf>'
        # 2: STYLE_TABLE_HEADER
        '<xf numFmtId="0" fontId="2" fillId="3" borderId="3" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1">'
        '<alignment vertical="center" horizontal="center" wrapText="1"/>'
        '</xf>'
        # 3: STYLE_TEXT_EVEN
        '<xf numFmtId="0" fontId="0" fillId="4" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1">'
        '<alignment vertical="center" wrapText="1"/>'
        '</xf>'
        # 4: STYLE_TEXT_ODD (Zebra)
        '<xf numFmtId="0" fontId="0" fillId="5" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1">'
        '<alignment vertical="center" wrapText="1"/>'
        '</xf>'
        # 5: STYLE_NUM_EVEN (#,##0.00)
        '<xf numFmtId="164" fontId="0" fillId="4" borderId="1" xfId="0" applyNumberFormat="1" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1">'
        '<alignment vertical="center" horizontal="right"/>'
        '</xf>'
        # 6: STYLE_NUM_ODD (#,##0.00 Zebra)
        '<xf numFmtId="164" fontId="0" fillId="5" borderId="1" xfId="0" applyNumberFormat="1" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1">'
        '<alignment vertical="center" horizontal="right"/>'
        '</xf>'
        # 7: STYLE_INT_EVEN (#,##0)
        '<xf numFmtId="165" fontId="0" fillId="4" borderId="1" xfId="0" applyNumberFormat="1" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1">'
        '<alignment vertical="center" horizontal="center"/>'
        '</xf>'
        # 8: STYLE_INT_ODD (#,##0 Zebra)
        '<xf numFmtId="165" fontId="0" fillId="5" borderId="1" xfId="0" applyNumberFormat="1" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1">'
        '<alignment vertical="center" horizontal="center"/>'
        '</xf>'
        # 9: STYLE_TOTAL_TEXT
        '<xf numFmtId="0" fontId="3" fillId="6" borderId="2" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1">'
        '<alignment vertical="center" horizontal="left"/>'
        '</xf>'
        # 10: STYLE_TOTAL_NUM
        '<xf numFmtId="164" fontId="3" fillId="6" borderId="2" xfId="0" applyNumberFormat="1" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1">'
        '<alignment vertical="center" horizontal="right"/>'
        '</xf>'
        # 11: STYLE_STATUS_OK
        '<xf numFmtId="0" fontId="4" fillId="7" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1">'
        '<alignment vertical="center" horizontal="center"/>'
        '</xf>'
        # 12: STYLE_STATUS_WARN
        '<xf numFmtId="0" fontId="5" fillId="8" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1">'
        '<alignment vertical="center" horizontal="center"/>'
        '</xf>'
        # 13: STYLE_GANTT_PRE
        '<xf numFmtId="165" fontId="6" fillId="9" borderId="1" xfId="0" applyNumberFormat="1" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1">'
        '<alignment vertical="center" horizontal="right"/>'
        '</xf>'
        # 14: STYLE_GANTT_OBRA
        '<xf numFmtId="165" fontId="6" fillId="10" borderId="1" xfId="0" applyNumberFormat="1" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1">'
        '<alignment vertical="center" horizontal="right"/>'
        '</xf>'
        # 15: STYLE_GANTT_EMPTY
        '<xf numFmtId="165" fontId="0" fillId="5" borderId="1" xfId="0" applyNumberFormat="1" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1">'
        '<alignment vertical="center" horizontal="center"/>'
        '</xf>'
        # 16: STYLE_CURVA_S
        '<xf numFmtId="164" fontId="4" fillId="11" borderId="1" xfId="0" applyNumberFormat="1" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1">'
        '<alignment vertical="center" horizontal="right"/>'
        '</xf>'
        # 17: STYLE_KEY_LABEL
        '<xf numFmtId="0" fontId="7" fillId="12" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1">'
        '<alignment vertical="center" horizontal="left"/>'
        '</xf>'
        + _xfs_tipologia_xml()
        + '</cellXfs>'
        '<cellStyles count="1">'
        '<cellStyle name="Normal" xfId="0" builtinId="0"/>'
        '</cellStyles>'
        '</styleSheet>'
    )


_HEADER_FIRST_CELLS = {
    "NÍVEL",
    "ITEM",
    "BLOCO",
    "CATEGORIA",
    "PAVIMENTO",
    "ZONA",
    "PERÍMETRO (PA)",
    "TRECHO / BLOCO",
    "GRUPO",
    "ORDEM",
    "PERÍODO",
}

_TOTAL_KEYWORDS = (
    "SUBTOTAL",
    "TOTAL",
    "LUCRO LÍQUIDO",
    "VGV BRUTO",
    "DESEMBOLSO MENSAL",
    "AVANÇO FÍSICO MENSAL",
)


def _classificar_linha(row: Sequence[Any], r_idx: int) -> str:
    """
    Classifica semanticamente uma linha da planilha para aplicar o estilo visual adequado:
    - 'banner': linha de título principal ou seção em caixa alta (1 única célula preenchida)
    - 'header': cabeçalho de tabela
    - 'curva_s': linha de Curva S acumulada
    - 'total': linha de subtotal, total ou indicador mestre
    - 'kv': linha de chave-valor de resumo
    - 'data': linha normal de dados
    """
    non_empty = [c for c in row if c is not None and c != ""]
    if not non_empty:
        return "empty"

    first_str = str(non_empty[0]).strip()
    first_upper = first_str.upper()

    if len(non_empty) == 1 and (r_idx == 1 or first_str == first_upper and len(first_str) >= 6):
        return "banner"

    if first_upper in _HEADER_FIRST_CELLS:
        return "header"

    row_joined_upper = " ".join(str(c).upper() for c in non_empty[:3])
    if "CURVA S" in row_joined_upper:
        return "curva_s"

    if any(k in row_joined_upper for k in _TOTAL_KEYWORDS):
        return "total"

    if len(non_empty) in (2, 3, 4) and isinstance(non_empty[0], str) and any(isinstance(x, (int, float)) for x in non_empty[1:]):
        # Verifica se parece ficha/resumo (primeira coluna texto curto e segunda número)
        if len(row) <= 5:
            return "kv"

    return "data"


def _escolher_estilo_celula(
    sheet_name: str,
    row_kind: str,
    r_idx: int,
    c_idx: int,
    val: Any,
    row: Sequence[Any],
) -> int:
    """Retorna o índice `s` (0..17) do estilo OpenXML para a célula `(r_idx, c_idx)`."""
    if row_kind == "banner":
        return STYLE_TITLE_BANNER
    if row_kind == "header":
        return STYLE_TABLE_HEADER
    if row_kind == "curva_s":
        return STYLE_CURVA_S if isinstance(val, (int, float)) else STYLE_TOTAL_TEXT
    if row_kind == "total":
        return STYLE_TOTAL_NUM if isinstance(val, (int, float)) else STYLE_TOTAL_TEXT

    # Status semântico ("ATENDE", "REVISAR", "ADEQUADA", etc.)
    if isinstance(val, str):
        v_up = val.strip().upper()
        if v_up in ("ATENDE", "SIM", "ADEQUADA", "VIÁVEL") or "ADEQUADA" in v_up:
            return STYLE_STATUS_OK
        if v_up in ("REVISAR", "NÃO", "INADEQUADA") or "INADEQUADA" in v_up or "ABAIXO" in v_up:
            return STYLE_STATUS_WARN

    # Destaque de barras de Gantt na aba CRONOGRAMA (colunas M01..MN a partir da coluna 9)
    if sheet_name == "CRONOGRAMA" and c_idx >= 9 and row_kind == "data":
        if isinstance(val, (int, float)):
            if float(val) > 0:
                fase_str = str(row[1]) if len(row) > 1 else ""
                return STYLE_GANTT_PRE if "Pré-Obra" in fase_str else STYLE_GANTT_OBRA
            return STYLE_GANTT_EMPTY

    if row_kind == "kv" and c_idx in (1, 4):
        return STYLE_KEY_LABEL

    is_odd = (r_idx % 2) == 1
    if isinstance(val, bool):
        return STYLE_TEXT_ODD if is_odd else STYLE_TEXT_EVEN
    if isinstance(val, int) or (isinstance(val, float) and val.is_integer() and c_idx <= 4):
        return STYLE_INT_ODD if is_odd else STYLE_INT_EVEN
    if isinstance(val, (int, float)):
        return STYLE_NUM_ODD if is_odd else STYLE_NUM_EVEN
    return STYLE_TEXT_ODD if is_odd else STYLE_TEXT_EVEN


def _aplicar_cor_tipologia(style_id: int, row_kind: str, val: Any, familia: Optional[int]) -> int:
    """Troca o estilo pela versão colorida da tipologia (mantém status ATENDE/REVISAR e Gantt)."""
    if familia is None or style_id in (STYLE_STATUS_OK, STYLE_STATUS_WARN, STYLE_GANTT_PRE, STYLE_GANTT_OBRA):
        return style_id
    if row_kind == "header":
        return estilo_tipologia(familia, "header")
    if row_kind == "total":
        return estilo_tipologia(familia, "total") if isinstance(val, (int, float)) else style_id
    if row_kind in ("data", "kv"):
        if style_id in (STYLE_INT_EVEN, STYLE_INT_ODD):
            return estilo_tipologia(familia, "int")
        if style_id in (STYLE_NUM_EVEN, STYLE_NUM_ODD):
            return estilo_tipologia(familia, "num")
        if style_id in (STYLE_TEXT_EVEN, STYLE_TEXT_ODD):
            return estilo_tipologia(familia, "text")
    return style_id


def _calcular_larguras_colunas(sheet_name: str, rows: Sequence[Sequence[Any]]) -> List[float]:
    """Calcula a largura ideal de cada coluna para evitar textos truncados ou `###`."""
    max_cols = max((len(r) for r in rows), default=1)
    widths = [11.0] * max_cols
    for r in rows:
        non_empty = [c for c in r if c is not None and c != ""]
        if len(non_empty) == 1:
            # Ignora títulos de largura total no cálculo da coluna A
            continue
        for idx, val in enumerate(r):
            if val is None or val == "":
                continue
            if isinstance(val, float):
                s_len = len(f"{val:,.2f}") + 3
            else:
                s_len = len(str(val)) + 3
            if s_len > widths[idx]:
                widths[idx] = float(s_len)

    for idx in range(max_cols):
        if sheet_name == "CRONOGRAMA" and idx >= 8:
            # Colunas M01..MN do Gantt
            widths[idx] = max(11.5, min(14.0, widths[idx]))
        else:
            widths[idx] = max(10.0, min(44.0, widths[idx]))
    return widths


def _sheet_xml(sheet_name: str, rows: Sequence[Sequence[Any]]) -> str:
    """Converte uma matriz de linhas/colunas em XML de worksheet OpenXML colorido e estilizado."""
    tab_rgb = TAB_COLORS.get(sheet_name, "FF1E3A8A")
    col_widths = _calcular_larguras_colunas(sheet_name, rows)
    max_cols_sheet = max(len(col_widths), 6)

    cols_xml = "".join(
        f'<col min="{i}" max="{i}" width="{w:.1f}" customWidth="1"/>'
        for i, w in enumerate(col_widths, start=1)
    )

    parts = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">',
        f'<sheetPr><tabColor rgb="{tab_rgb}"/></sheetPr>',
        '<sheetViews><sheetView workbookViewId="0" showGridLines="1"/></sheetViews>',
        '<sheetFormatPr defaultRowHeight="19"/>',
        f"<cols>{cols_xml}</cols>",
        "<sheetData>",
    ]

    merge_refs: List[str] = []
    # Cores por tipologia: colunas da tabela atual (pelo cabeçalho) e coluna "CATEGORIA" (por linha)
    familias_colunas: Dict[int, int] = {}
    col_categoria: Optional[int] = None

    for r_idx, row in enumerate(rows, start=1):
        row_kind = _classificar_linha(row, r_idx)
        if row_kind == "empty":
            continue
        if row_kind == "banner":
            familias_colunas, col_categoria = {}, None
        elif row_kind == "header":
            familias_colunas = {
                c: f for c, v in enumerate(row, start=1) if (f := familia_tipologia(v)) is not None
            }
            col_categoria = next(
                (c for c, v in enumerate(row, start=1) if isinstance(v, str) and v.strip().upper() == "CATEGORIA"),
                None,
            )
        familia_linha = (
            familia_tipologia(row[col_categoria - 1])
            if col_categoria and row_kind in ("data", "kv") and len(row) >= col_categoria
            else None
        )

        row_ht = "26" if row_kind == "banner" else ("24" if row_kind == "header" else ("21" if row_kind in ("total", "curva_s") else "19"))
        cells_xml: List[str] = []

        if row_kind == "banner":
            # Preenche o banner até a coluna final da tabela e mescla para visual de faixa executiva
            val_banner = next((c for c in row if c is not None and c != ""), "")
            txt_b = escape(str(val_banner))
            span_cols = min(max_cols_sheet, 10)
            for c_i in range(1, span_cols + 1):
                ref_b = f"{_col_letter(c_i)}{r_idx}"
                if c_i == 1:
                    cells_xml.append(f'<c r="{ref_b}" s="{STYLE_TITLE_BANNER}" t="inlineStr"><is><t>{txt_b}</t></is></c>')
                else:
                    cells_xml.append(f'<c r="{ref_b}" s="{STYLE_TITLE_BANNER}"/>')
            if span_cols > 1:
                merge_refs.append(f"A{r_idx}:{_col_letter(span_cols)}{r_idx}")
        else:
            for c_idx, val in enumerate(row, start=1):
                if val is None or val == "":
                    continue
                ref = f"{_col_letter(c_idx)}{r_idx}"
                style_id = _escolher_estilo_celula(sheet_name, row_kind, r_idx, c_idx, val, row)
                style_id = _aplicar_cor_tipologia(
                    style_id, row_kind, val, familias_colunas.get(c_idx, familia_linha)
                )
                if isinstance(val, bool):
                    txt_bool = "SIM" if val else "NÃO"
                    cells_xml.append(f'<c r="{ref}" s="{style_id}" t="inlineStr"><is><t>{txt_bool}</t></is></c>')
                elif isinstance(val, (int, float)):
                    cells_xml.append(f'<c r="{ref}" s="{style_id}"><v>{val}</v></c>')
                else:
                    txt = escape(str(val))
                    cells_xml.append(f'<c r="{ref}" s="{style_id}" t="inlineStr"><is><t>{txt}</t></is></c>')

        if cells_xml:
            parts.append(f'<row r="{r_idx}" ht="{row_ht}" customHeight="1">{"".join(cells_xml)}</row>')

    parts.append("</sheetData>")
    if merge_refs:
        merges_xml = "".join(f'<mergeCell ref="{m}"/>' for m in merge_refs)
        parts.append(f'<mergeCells count="{len(merge_refs)}">{merges_xml}</mergeCells>')
    parts.append("</worksheet>")
    return "".join(parts)


def gerar_xlsx_bytes(abas: List[Tuple[str, Sequence[Sequence[Any]]]]) -> bytes:
    """
    Recebe uma lista de tuplas `(nome_da_aba, linhas)` e retorna os bytes de um arquivo `.xlsx`
    OpenXML válido, colorido e estilizado.
    """
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        # 1. [Content_Types].xml
        overrides = "".join(
            f'<Override PartName="/xl/worksheets/sheet{i}.xml" '
            f'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            for i in range(1, len(abas) + 1)
        )
        content_types = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            '<Override PartName="/xl/styles.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
            f"{overrides}"
            "</Types>"
        )
        zf.writestr("[Content_Types].xml", content_types)

        # 2. _rels/.rels
        rels_root = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" '
            'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
            'Target="xl/workbook.xml"/>'
            "</Relationships>"
        )
        zf.writestr("_rels/.rels", rels_root)

        # 3. xl/styles.xml
        zf.writestr("xl/styles.xml", _styles_xml())

        # 4. xl/workbook.xml e xl/_rels/workbook.xml.rels
        sheets_tags = []
        rels_tags = []
        for idx, (nome, _) in enumerate(abas, start=1):
            nome_limpo = escape(nome[:31])
            sheets_tags.append(
                f'<sheet name="{nome_limpo}" sheetId="{idx}" r:id="rId{idx}"/>'
            )
            rels_tags.append(
                f'<Relationship Id="rId{idx}" '
                f'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
                f'Target="worksheets/sheet{idx}.xml"/>'
            )
        rels_tags.append(
            f'<Relationship Id="rIdStyles" '
            f'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" '
            f'Target="styles.xml"/>'
        )

        workbook_xml = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            f'<sheets>{"".join(sheets_tags)}</sheets>'
            "</workbook>"
        )
        zf.writestr("xl/workbook.xml", workbook_xml)

        workbook_rels = (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            f'{"".join(rels_tags)}'
            "</Relationships>"
        )
        zf.writestr("xl/_rels/workbook.xml.rels", workbook_rels)

        # 5. Worksheets estilizadas
        for idx, (nome, rows) in enumerate(abas, start=1):
            zf.writestr(f"xl/worksheets/sheet{idx}.xml", _sheet_xml(nome, rows))

    return buf.getvalue()
