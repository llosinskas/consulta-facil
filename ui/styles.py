"""
Estilos globais e componentes HTML reutilizáveis para uma interface clean.
Todos os componentes quebram linha automaticamente (nenhum texto é cortado com "...").
"""

from html import escape
from typing import Iterable, List, Optional, Sequence, Tuple

import streamlit as st

CSS_GLOBAL = """
<style>
/* Base */
.block-container { padding-top: 1.6rem; padding-bottom: 3rem; max-width: 1280px; }
h1, h2, h3, h4 { letter-spacing: -0.01em; }
section[data-testid="stSidebar"] { min-width: 340px; }
section[data-testid="stSidebar"] .block-container { padding-top: 1.2rem; }

/* Remove truncamento padrão em rótulos de widgets */
label, [data-testid="stWidgetLabel"] p, [data-testid="stMarkdownContainer"] p {
    white-space: normal !important; overflow: visible !important; text-overflow: clip !important;
}

/* Cabeçalho do terreno */
.vb-header { border: 1px solid #e5e7eb; border-radius: 12px; padding: 18px 22px;
             background: #ffffff; margin-bottom: 18px; }
.vb-header-top { display: flex; flex-wrap: wrap; justify-content: space-between; gap: 12px; align-items: flex-start; }
.vb-eyebrow { font-size: 12px; color: #6b7280; text-transform: uppercase; letter-spacing: .06em; }
.vb-title { font-size: 22px; font-weight: 650; color: #111827; margin: 4px 0 6px 0; word-break: break-word; }
.vb-sub { font-size: 14px; color: #4b5563; word-break: break-word; }
.vb-badge { display: inline-block; background: #fef3c7; color: #92400e; border: 1px solid #fcd34d;
            font-weight: 650; font-size: 14px; padding: 6px 12px; border-radius: 999px; white-space: normal; }

/* Títulos de seção */
.vb-section { margin: 28px 0 12px 0; padding-bottom: 6px; border-bottom: 1px solid #e5e7eb; }
.vb-section h4 { margin: 0; font-size: 17px; font-weight: 650; color: #111827; }
.vb-section p { margin: 4px 0 0 0; font-size: 13px; color: #6b7280; }

/* Cards */
.vb-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 12px; }
.vb-card { background: #ffffff; border: 1px solid #e5e7eb; border-radius: 10px; padding: 14px 16px; }
.vb-card-label { font-size: 12.5px; color: #6b7280; line-height: 1.35; word-break: break-word; }
.vb-card-value { font-size: 21px; font-weight: 650; color: #111827; margin-top: 4px;
                 line-height: 1.25; word-break: break-word; }
.vb-card-note { font-size: 12.5px; color: #4b5563; margin-top: 4px; line-height: 1.35; word-break: break-word; }

/* Tabelas */
.vb-table-wrap { border: 1px solid #e5e7eb; border-radius: 10px; overflow-x: auto; background: #fff; }
.vb-table { width: 100%; border-collapse: collapse; font-size: 13.5px; }
.vb-table th { text-align: left; background: #f9fafb; color: #374151; font-weight: 600;
               padding: 9px 12px; border-bottom: 1px solid #e5e7eb; white-space: normal; }
.vb-table td { padding: 9px 12px; border-bottom: 1px solid #f3f4f6; color: #111827;
               white-space: normal; word-break: break-word; vertical-align: top; }
.vb-table tr:last-child td { border-bottom: none; }
.vb-row-total td { background: #fffbeb !important; font-weight: 650; border-top: 2px solid #f59e0b !important; color: #78350f !important; }

/* Caixas de texto informativas */
.vb-note { background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 10px; padding: 12px 14px;
           font-size: 14px; color: #374151; line-height: 1.5; word-break: break-word; }
.vb-warn { background: #fffbeb; border: 1px solid #fde68a; color: #78350f; }
.vb-alert { background: #fef2f2; border: 1px solid #fecaca; color: #7f1d1d; }
</style>
"""


def aplicar_estilos() -> None:
    st.markdown(CSS_GLOBAL, unsafe_allow_html=True)


def _html(conteudo: str) -> None:
    st.markdown(conteudo, unsafe_allow_html=True)


def titulo_secao(titulo: str, subtitulo: Optional[str] = None) -> None:
    sub = f"<p>{escape(subtitulo)}</p>" if subtitulo else ""
    _html(f'<div class="vb-section"><h4>{escape(titulo)}</h4>{sub}</div>')


def grade_cards(cards: Iterable[Tuple[str, str, Optional[str]]]) -> None:
    """cards = [(rótulo, valor, nota_opcional), ...]"""
    partes: List[str] = ['<div class="vb-grid">']
    for rotulo, valor, nota in cards:
        nota_html = f'<div class="vb-card-note">{escape(nota)}</div>' if nota else ""
        partes.append(
            '<div class="vb-card">'
            f'<div class="vb-card-label">{escape(rotulo)}</div>'
            f'<div class="vb-card-value">{escape(valor)}</div>'
            f"{nota_html}"
            "</div>"
        )
    partes.append("</div>")
    _html("".join(partes))


def tabela(
    cabecalhos: Sequence[str],
    linhas: Sequence[Sequence[object]],
    destacar_ultima_linha: bool = False,
) -> None:
    partes: List[str] = ['<div class="vb-table-wrap"><table class="vb-table"><thead><tr>']
    partes.extend(f"<th>{escape(str(c))}</th>" for c in cabecalhos)
    partes.append("</tr></thead><tbody>")
    total = len(linhas)
    for idx, linha in enumerate(linhas):
        classe = ' class="vb-row-total"' if (destacar_ultima_linha and idx == total - 1) else ""
        partes.append(f"<tr{classe}>" + "".join(f"<td>{escape(str(v))}</td>" for v in linha) + "</tr>")
    partes.append("</tbody></table></div>")
    _html("".join(partes))


def nota(texto: str, tipo: str = "") -> None:
    """tipo: '' (neutro), 'warn' (atenção) ou 'alert' (crítico)."""
    classe = {"warn": " vb-warn", "alert": " vb-alert"}.get(tipo, "")
    _html(f'<div class="vb-note{classe}">{escape(texto)}</div>')


def cabecalho_terreno(eyebrow: str, titulo: str, subtitulo: str, badge: str) -> None:
    _html(
        '<div class="vb-header"><div class="vb-header-top"><div>'
        f'<div class="vb-eyebrow">{escape(eyebrow)}</div>'
        f'<div class="vb-title">{escape(titulo)}</div>'
        f'<div class="vb-sub">{escape(subtitulo)}</div>'
        f'</div><div><span class="vb-badge">{escape(badge)}</span></div></div></div>'
    )

