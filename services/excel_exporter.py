"""
Exportador nativo de planilha Excel (.xlsx) sem dependências externas (usa `zipfile` e `xml` da biblioteca padrão).
Gera um arquivo `.xlsx` válido contendo as 7 abas da planilha de viabilidade:
1. Q. ÁREAS
2. Q. LUOPS
3. Q. ANEXOS
4. CALC. ÁGUA
5. ELEVADOR
6. DADOS
7. DESNÍVEL
"""

import io
import zipfile
from html import escape
from typing import Any, Dict, List, Sequence, Tuple


def _col_letter(col_idx_1based: int) -> str:
    result = ""
    n = col_idx_1based
    while n > 0:
        n, rem = divmod(n - 1, 26)
        result = chr(65 + rem) + result
    return result


def _sheet_xml(rows: Sequence[Sequence[Any]]) -> str:
    """Converte uma matriz de linhas/colunas em XML de worksheet OpenXML."""
    parts = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">',
        "<sheetData>",
    ]
    for r_idx, row in enumerate(rows, start=1):
        cells_xml: List[str] = []
        for c_idx, val in enumerate(row, start=1):
            if val is None or val == "":
                continue
            ref = f"{_col_letter(c_idx)}{r_idx}"
            if isinstance(val, bool):
                cells_xml.append(f'<c r="{ref}" t="inlineStr"><is><t>{ "SIM" if val else "NÃO" }</t></is></c>')
            elif isinstance(val, (int, float)):
                cells_xml.append(f'<c r="{ref}"><v>{val}</v></c>')
            else:
                txt = escape(str(val))
                cells_xml.append(f'<c r="{ref}" t="inlineStr"><is><t>{txt}</t></is></c>')
        if cells_xml:
            parts.append(f'<row r="{r_idx}">{"".join(cells_xml)}</row>')
    parts.append("</sheetData></worksheet>")
    return "".join(parts)


def gerar_xlsx_bytes(abas: List[Tuple[str, Sequence[Sequence[Any]]]]) -> bytes:
    """
    Recebe uma lista de tuplas `(nome_da_aba, linhas)` e retorna os bytes de um arquivo `.xlsx` OpenXML válido.
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

        # 3. xl/workbook.xml e xl/_rels/workbook.xml.rels
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

        # 4. Worksheets
        for idx, (_, rows) in enumerate(abas, start=1):
            zf.writestr(f"xl/worksheets/sheet{idx}.xml", _sheet_xml(rows))

    return buf.getvalue()

