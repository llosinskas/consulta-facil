"""
Tela de carregamento com barra de progresso que bloqueia a interface.

Uso típico (em app.py):

    reservar_area_carregamento()          # uma vez, no início do script, antes da sidebar
    with tela_de_carregamento("Consultando lote") as progresso:
        resultado = processar_terreno_completo(..., progresso=progresso)

Enquanto o bloco roda, uma camada semitransparente cobre a página inteira (mapa, sidebar e
botões), impedindo novos cliques até o cálculo terminar. Ao sair do bloco, a camada é removida.
A função `progresso(fração 0–1, mensagem)` é o mesmo callback aceito pelos serviços.
"""

import threading
from contextlib import contextmanager
from html import escape
from typing import Callable, Iterator

import streamlit as st

_CSS_OVERLAY = """
<style>
.cf-overlay { position: fixed; inset: 0; z-index: 1000000; background: rgba(15, 23, 42, .42);
              backdrop-filter: blur(1.5px); display: flex; align-items: center; justify-content: center;
              cursor: progress; }
.cf-card { background: #fff; border-radius: 14px; padding: 22px 26px; width: min(440px, 88vw);
           box-shadow: 0 18px 50px rgba(0,0,0,.25); font-family: -apple-system, 'Segoe UI', Roboto, Arial, sans-serif; }
.cf-title { font-size: 16px; font-weight: 650; color: #111827; margin-bottom: 4px; }
.cf-msg { font-size: 13.5px; color: #4b5563; min-height: 20px; margin-bottom: 12px; }
.cf-track { height: 10px; background: #e5e7eb; border-radius: 999px; overflow: hidden; }
.cf-bar { height: 100%; background: linear-gradient(90deg, #d97706, #f59e0b); border-radius: 999px;
          transition: width .35s ease; }
.cf-pct { font-size: 12.5px; color: #6b7280; margin-top: 8px; text-align: right; }
.cf-hint { font-size: 12px; color: #9ca3af; margin-top: 6px; }
</style>
"""

# Cada sessão do Streamlit executa o script na própria thread: a área reservada fica por thread,
# para que um usuário nunca desenhe a camada de carregamento na página de outro.
_local = threading.local()


def reservar_area_carregamento() -> None:
    """
    Cria, no corpo principal da página, o espaço onde a camada de carregamento será desenhada.
    Deve ser chamada no início de cada execução, antes da sidebar: dentro da sidebar uma
    camada `position: fixed` ficaria presa à largura da barra lateral.
    """
    _local.area = st.empty()


def _html_overlay(titulo: str, fracao: float, mensagem: str) -> str:
    pct = int(round(max(0.0, min(1.0, fracao)) * 100))
    return (
        f"{_CSS_OVERLAY}<div class='cf-overlay' role='progressbar' aria-valuenow='{pct}' "
        f"aria-valuemin='0' aria-valuemax='100'><div class='cf-card'>"
        f"<div class='cf-title'>{escape(titulo)}</div>"
        f"<div class='cf-msg'>{escape(mensagem)}</div>"
        f"<div class='cf-track'><div class='cf-bar' style='width:{max(pct, 3)}%'></div></div>"
        f"<div class='cf-pct'>{pct}%</div>"
        f"<div class='cf-hint'>Aguarde: a tela fica bloqueada até o fim da consulta.</div>"
        f"</div></div>"
    )


@contextmanager
def tela_de_carregamento(titulo: str, mensagem_inicial: str = "Preparando…") -> Iterator[Callable[[float, str], None]]:
    """Mostra a camada bloqueante com barra de progresso enquanto o bloco `with` executa."""
    area = getattr(_local, "area", None) or st.empty()
    estado = {"fracao": 0.0}

    def progresso(fracao: float, mensagem: str) -> None:
        # A barra nunca anda para trás (várias etapas podem reportar frações próximas)
        estado["fracao"] = max(estado["fracao"], float(fracao))
        area.markdown(_html_overlay(titulo, estado["fracao"], mensagem), unsafe_allow_html=True)

    progresso(0.0, mensagem_inicial)
    try:
        yield progresso
    finally:
        area.empty()


def sub_progresso(progresso: Callable[[float, str], None], inicio: float, fim: float) -> Callable[[float, str], None]:
    """Converte um progresso 0–1 de uma subetapa para a faixa [inicio, fim] da barra principal."""
    def _interno(fracao: float, mensagem: str) -> None:
        progresso(inicio + (fim - inicio) * max(0.0, min(1.0, fracao)), mensagem)
    return _interno
