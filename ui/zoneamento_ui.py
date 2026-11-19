"""Bloco "Confirmação da zona": zona do lote conferida no Mapa 1 vigente da LPUOS (GeoSampa)."""

from domain.legislacao_sp import QUADRO_3
from domain.models import ResultadoTerreno
from ui.styles import grade_cards, nota, tabela, titulo_secao

_ICONE_STATUS = {
    "confirmada": "✅ Confirmada",
    "lote em mais de uma zona": "⚠️ Lote em mais de uma zona",
    "não confirmada": "⚠️ Não confirmada",
}


def _pct(v: float) -> str:
    return f"{v:.1f}%".replace(".", ",")


def renderizar_confirmacao_zona(resultado: ResultadoTerreno) -> None:
    titulo_secao(
        "Confirmação da zona (LPUOS — Mapa 1)",
        "A zona é conferida cruzando o polígono do lote com o mapa de zoneamento vigente do GeoSampa "
        "(Lei 18.081/2024) e comparada com os mapas da Lei 18.177/2024 e de 2016.",
    )
    conf = getattr(resultado, "confirmacao_zona", None)  # sessões anteriores ao campo não o têm
    if conf is None:
        zona = resultado.zoneamento.sigla_zona if resultado.zoneamento else "—"
        nota(
            f"Zona {zona} vinda dos dados gravados (exemplo ou consulta sem o GeoSampa). Para confirmar no mapa "
            "vigente, clique em “Consultar Macrozona, Macroárea e Qualificação Ambiental pelo ponto do lote” "
            "ou faça a busca pelo SQL.",
            "info",
        )
        return

    params = QUADRO_3.get(conf.zona) if conf.zona else None
    grade_cards(
        [
            ("Zona do lote", conf.zona or "—", params.nome if params else "Sem parâmetros no Quadro 3"),
            ("Situação", _ICONE_STATUS.get(conf.status, conf.status),
             f"{_pct(conf.percentual_zona)} do lote nesta zona"),
            ("Mapa de referência", conf.lei_referencia, "Mapa 1 da LPUOS no GeoSampa"),
        ]
    )
    for alerta in conf.alertas:
        nota(alerta, "warn" if conf.status != "confirmada" or "inconstitucional" in alerta else "info")

    linhas = []
    for leitura in conf.leituras:
        if not leitura.respondeu:
            zonas = "Sem resposta do GeoSampa"
        elif not leitura.zonas:
            zonas = "Nenhuma zona sobre o lote"
        else:
            zonas = " · ".join(
                f"{z.sigla or z.texto_original} ({_pct(z.percentual)})" for z in leitura.zonas
            )
        linhas.append([leitura.lei, zonas, leitura.situacao])
    tabela(["Mapa", "Zonas sobre o lote (% da área)", "Situação legal"], linhas)
