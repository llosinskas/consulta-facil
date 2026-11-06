"""
Ponte de conexão (Etapas 1 a 4):
Conecta o objeto `ResultadoTerreno` (extraído do GeoSampa) às tabelas legais da aba `DADOS`
(Quadros 2, 3 e 4) e gera `EntradaGeo` e `IndicesLegais` com as mesmas fórmulas da planilha.
"""

import re
from typing import Dict, List, Optional, Tuple

from domain.models import ResultadoTerreno
from domain.tabelas_dados import (
    NOTAS_QUADRO_2,
    NOTAS_QUADRO_4,
    QUADRO_2_RAW,
    QUADRO_3_RAW,
    QUADRO_4_RAW,
)
from domain.viabilidade_models import EntradaGeo, IndicesLegais


def _mapa_chaves_normalizadas(dicionario: Dict[str, Dict]) -> Dict[str, str]:
    """Mapeia a sigla limpa (ex: 'ZEUP', 'PA 13') para a chave original da tabela (ex: 'ZEUP (a)', 'PA 13 (e)')."""
    mapa: Dict[str, str] = {}
    for k in dicionario.keys():
        limpa = re.sub(r"\s*\([a-zA-Z]\)\s*$", "", k.replace("\xa0", " ").strip())
        mapa[limpa] = k
        mapa[limpa.upper()] = k
        mapa[k] = k
    return mapa


_MAPA_Q2 = _mapa_chaves_normalizadas(QUADRO_2_RAW)
_MAPA_Q3 = _mapa_chaves_normalizadas(QUADRO_3_RAW)
_MAPA_Q4 = _mapa_chaves_normalizadas(QUADRO_4_RAW)


def listar_zonas_disponiveis() -> List[str]:
    """Retorna a lista de zonas limpas disponíveis nos Quadros 2 e 3."""
    zonas: List[str] = []
    for k in list(QUADRO_2_RAW.keys()) + list(QUADRO_3_RAW.keys()):
        limpa = re.sub(r"\s*\([a-zA-Z]\)\s*$", "", k.replace("\xa0", " ").strip())
        if limpa not in zonas:
            zonas.append(limpa)
    return zonas


def listar_pas_disponiveis() -> List[str]:
    """Retorna a lista de Perímetros de Qualificação Ambiental (PA 1 a PA 13)."""
    pas: List[str] = []
    for k in QUADRO_4_RAW.keys():
        limpa = re.sub(r"\s*\([a-zA-Z]\)\s*$", "", k.replace("\xa0", " ").strip())
        if limpa not in pas:
            pas.append(limpa)
    return pas


def normalizar_zona(zona_bruta: Optional[str]) -> Optional[str]:
    """
    Normaliza a sigla da zona vinda do GeoSampa (ex.: 'ZEUP (a)', 'ZM-2', 'ZCOR 1', 'zeua')
    para casar com as chaves dos Quadros 2 e 3 da aba DADOS.
    """
    if not zona_bruta:
        return None
    s = str(zona_bruta).replace("\xa0", " ").strip()
    s = re.sub(r"\s*\([a-zA-Z]\)\s*$", "", s).strip()
    if not s:
        return None

    # Caso direto
    if s in _MAPA_Q2 or s in _MAPA_Q3:
        return re.sub(r"\s*\([a-zA-Z]\)\s*$", "", (_MAPA_Q2.get(s) or _MAPA_Q3.get(s, s)))

    # Sufixo 'a' minúsculo (ZEUa, ZEUPa, ZCa, ZCORa, ZMa, ZMISa, ZERa, AIa)
    s_upper = s.upper()
    if s_upper in _MAPA_Q2 or s_upper in _MAPA_Q3:
        chave_real = _MAPA_Q2.get(s_upper) or _MAPA_Q3.get(s_upper, s_upper)
        return re.sub(r"\s*\([a-zA-Z]\)\s*$", "", chave_real)

    # Variações como ZM-1 / ZM-2 / ZM 1 -> ZM
    m_zm = re.match(r"^(ZM|ZEU|ZEUP|ZC|ZMIS|ZPR|ZPDS|ZEPAM)[-\s]+\d+$", s_upper)
    if m_zm:
        base = m_zm.group(1)
        if base in _MAPA_Q2 or base in _MAPA_Q3:
            return base

    # Variações com espaço em vez de hífen: 'ZEIS 1' -> 'ZEIS-1', 'ZCOR 2' -> 'ZCOR-2'
    s_hifen = re.sub(r"^(ZEIS|ZCOR|ZDE|ZPI|ZER|AVP|AC)\s+(\d+)$", r"\1-\2", s_upper)
    if s_hifen in _MAPA_Q2 or s_hifen in _MAPA_Q3:
        chave_real = _MAPA_Q2.get(s_hifen) or _MAPA_Q3.get(s_hifen, s_hifen)
        return re.sub(r"\s*\([a-zA-Z]\)\s*$", "", chave_real)

    return s


def extrair_pa(texto_pa: Optional[str], macroarea: Optional[str] = None) -> str:
    """
    Extrai o código padronizado 'PA 1' .. 'PA 13' a partir do texto retornado pelo GeoSampa
    (ex.: 'PA 6 (Perímetro de Qualificação Ambiental 6 — Quota Ambiental)' -> 'PA 6').
    """
    if texto_pa:
        limpo = str(texto_pa).replace("\xa0", " ").strip()
        m = re.search(r"\bPA\s*[-:]?\s*(\d{1,2})\b", limpo, flags=re.IGNORECASE)
        if m:
            num = int(m.group(1))
            if 1 <= num <= 13:
                return f"PA {num}"
        m_num = re.fullmatch(r"(\d{1,2})", limpo)
        if m_num and 1 <= int(m_num.group(1)) <= 13:
            return f"PA {int(m_num.group(1))}"

    if macroarea:
        ma_low = macroarea.lower()
        if "contenção" in ma_low or "contencao" in ma_low or "preservação" in ma_low or "preservacao" in ma_low:
            return "PA 13"

    return "PA 6"


def parse_numero_tabela(valor_str: Optional[str]) -> Tuple[Optional[float], Optional[str]]:
    """
    Converte strings das tabelas DADOS como '0.85', '2,5 (f)', '28 (c)', 'NA', '(k)'
    em (valor_float_ou_None, letra_da_nota_opcional).
    """
    if valor_str is None:
        return None, None
    s = str(valor_str).replace("\xa0", " ").strip()
    if not s or s.upper() == "NA":
        return None, None

    nota_match = re.findall(r"\(([a-zA-Z])\)", s)
    nota = nota_match[0].lower() if nota_match else None
    sem_nota = re.sub(r"\([a-zA-Z]\)", "", s).strip().replace(",", ".")
    if not sem_nota:
        return None, nota
    try:
        return float(sem_nota), nota
    except ValueError:
        return None, nota


def extrair_entrada_geo(
    resultado: ResultadoTerreno,
    area_doacao_m2: float = 0.0,
    zona_override: Optional[str] = None,
    pa_override: Optional[str] = None,
) -> EntradaGeo:
    """
    ETAPAS 1 e 2: Converte `ResultadoTerreno` (GeoSampa) em `EntradaGeo` normalizada.
    """
    alertas: List[str] = []
    area_escritura = round(float(resultado.area_total_m2), 2)
    doacao = max(0.0, round(float(area_doacao_m2 or 0.0), 2))
    area_rem = max(0.01, round(area_escritura - doacao, 2))
    if doacao > 0:
        alertas.append(
            f"Área de doação viária aplicada: {doacao:,.2f} m² (Escritura {area_escritura:,.2f} m² → Remanescente {area_rem:,.2f} m²)."
        )

    sqls = [l.sql_formatado for l in resultado.lotes]
    zonas_lotes = sorted({l.zona_incidente for l in resultado.lotes if l.zona_incidente})
    if len(zonas_lotes) > 1:
        alertas.append(
            f"Os lotes selecionados possuem zonas distintas ({', '.join(zonas_lotes)}). "
            "Verifique a zona predominante selecionada para os cálculos."
        )

    zona_bruta = (
        zona_override
        or (resultado.zoneamento.sigla_zona if resultado.zoneamento else None)
        or (resultado.zonas_detectadas[0] if resultado.zonas_detectadas else None)
        or "ZM"
    )
    zona_norm = normalizar_zona(zona_bruta) or "ZM"

    macroarea_val = resultado.macroarea.valor if (resultado.macroarea and resultado.macroarea.valor) else None
    macrozona_val = resultado.macrozona.valor if (resultado.macrozona and resultado.macrozona.valor) else None
    pa_bruto = (
        pa_override
        or (resultado.qualificacao_ambiental.valor if resultado.qualificacao_ambiental else None)
    )
    pa_norm = extrair_pa(pa_bruto, macroarea=macroarea_val)

    cota_min = resultado.topografia.cota_min_m if resultado.topografia else None
    cota_max = resultado.topografia.cota_max_m if resultado.topografia else None
    if cota_min is not None and cota_max is not None:
        cota_terreno = round((cota_min + cota_max) / 2.0, 2)
    elif cota_min is not None:
        cota_terreno = round(cota_min, 2)
    else:
        cota_terreno = 784.40

    endereco = resultado.endereco_aproximado
    if not endereco and resultado.lotes:
        logr = resultado.lotes[0].atributos_brutos.get("nm_logradouro")
        if logr:
            endereco = f"{logr} — SQL {' + '.join(sqls)}"
    if not endereco:
        endereco = f"SQL {' + '.join(sqls)} ({resultado.centroide_latlon[0]:.6f}, {resultado.centroide_latlon[1]:.6f})"

    if resultado.tombamento_detectado:
        alertas.append("Incidência de tombamento / patrimônio cultural detectada no GeoSampa.")

    return EntradaGeo(
        area_escritura_m2=area_escritura,
        area_doacao_m2=doacao,
        area_terreno_m2=area_rem,
        endereco=endereco,
        sqls=sqls,
        zona=zona_norm,
        zona_original=zona_bruta,
        pa=pa_norm,
        macroarea=macroarea_val,
        macrozona=macrozona_val,
        cota_terreno_m=cota_terreno,
        cota_min_m=cota_min,
        cota_max_m=cota_max,
        testada_m=resultado.testada_principal_m,
        profundidade_m=resultado.profundidade_estimada_m,
        tombamento=resultado.tombamento_detectado,
        alertas=alertas,
    )


def calcular_indices_legais(
    entrada: EntradaGeo,
    modalidade: str = "EHIS_COTA",
    ca_customizado: Optional[float] = None,
) -> IndicesLegais:
    """
    ETAPAS 3 e 4: Executa os lookups exatos nos Quadros 2, 3 e 4 da aba `DADOS`
    e calcula os limites legais aplicados à área do terreno.
    """
    area = entrada.area_terreno_m2
    zona = entrada.zona or "ZM"
    pa = entrada.pa or "PA 6"
    notas: List[str] = list(entrada.alertas)

    chave_q2 = _MAPA_Q2.get(zona) or _MAPA_Q2.get(zona.upper())
    chave_q3 = _MAPA_Q3.get(zona) or _MAPA_Q3.get(zona.upper())
    chave_q4 = _MAPA_Q4.get(pa) or _MAPA_Q4.get(pa.upper())

    d_q2 = QUADRO_2_RAW.get(chave_q2, {}) if chave_q2 else {}
    d_q3 = QUADRO_3_RAW.get(chave_q3, {}) if chave_q3 else {}
    d_q4 = QUADRO_4_RAW.get(chave_q4, {}) if chave_q4 else {}

    # C.A. Mínimo e Básico (Quadro 2 com fallback no Quadro 3)
    ca_min, _ = parse_numero_tabela(d_q2.get("ca_minimo") or d_q3.get("ca_minimo"))
    ca_bas, _ = parse_numero_tabela(d_q2.get("ca_basico") or d_q3.get("ca_basico"))
    if ca_bas is None:
        ca_bas = 1.0

    # C.A. Máximo LPUOS (Quadro 3: DADOS!AE:AJ col 4 -> ca_maximo)
    ca_max_lpuos, nota_ca_q3 = parse_numero_tabela(d_q3.get("ca_maximo"))
    if ca_max_lpuos is None:
        ca_max_lpuos = ca_bas

    # C.A. Decreto HIS e EHMP (Quadro 2: DADOS!C:I col 4 e 5)
    ca_ehis, nota_ca_q2 = parse_numero_tabela(d_q2.get("ca_max_ehis"))
    ca_ehmp, _ = parse_numero_tabela(d_q2.get("ca_max_ehmp"))
    if ca_ehis is None:
        ca_ehis = ca_max_lpuos

    # Notas de restrição por área de lote em ZEIS (notas e, f, g do Quadro 2 e f, g, h do Quadro 3)
    if zona in ("ZEIS-1", "ZEIS-2", "ZEIS-5") and area <= 1000.0:
        notas.append(
            f"Nota (e)/(f) ZEIS: Para lote ≤ 1.000 m² ({area:,.2f} m²), CA máx ordinário = 2,0, "
            f"sendo admitido CA máx = {ca_ehis} apenas para EZEIS."
        )
        if modalidade == "LPUOS":
            ca_max_lpuos = min(ca_max_lpuos, 2.0)
    elif zona == "ZEIS-3" and area <= 500.0:
        notas.append(
            f"Nota (f)/(g) ZEIS-3: Para lote ≤ 500 m² ({area:,.2f} m²), CA máx ordinário = 2,0 (4,0 para EZEIS)."
        )
        if modalidade == "LPUOS":
            ca_max_lpuos = min(ca_max_lpuos, 2.0)
    elif zona == "ZEIS-4" and area <= 1000.0:
        notas.append(
            f"Nota (g)/(h) ZEIS-4: Para lote ≤ 1.000 m² ({area:,.2f} m²), CA máx ordinário = 1,0 (2,0 para EZEIS)."
        )
        if modalidade == "LPUOS":
            ca_max_lpuos = min(ca_max_lpuos, 1.0)

    # C.A. Majorado (+20% Cota de Solidariedade — W40 = W39 * 1.2)
    ca_majorado = round(ca_ehis * 1.2, 4) if ca_ehis is not None else None

    # Taxa de Ocupação Máxima — Fórmula exata de C43: IF(D38<500, VLOOKUP(...,6), VLOOKUP(...,7))
    to_ate_500, _ = parse_numero_tabela(d_q2.get("to_ate_500") or d_q3.get("to_ate_500"))
    to_acima_500, _ = parse_numero_tabela(d_q2.get("to_acima_500") or d_q3.get("to_acima_500"))
    to_tabela = to_ate_500 if area < 500.0 else to_acima_500

    # Taxa de Permeabilidade Mínima — Fórmula exata de C47: IF(D38>500, VLOOKUP(...,3), VLOOKUP(...,2))
    tp_ate_500, _ = parse_numero_tabela(d_q4.get("ate_500"))
    tp_acima_500, _ = parse_numero_tabela(d_q4.get("acima_500"))
    tp_min = tp_acima_500 if area > 500.0 else tp_ate_500

    if area == 500.0:
        notas.append(
            "Terreno com exatamente 500,00 m²: pela fórmula da planilha, T.O. usa faixa '≥ 500 m²' e Permeabilidade usa faixa '≤ 500 m²'."
        )

    # Nota (a) do Quadro 4: ZCOR exige TP = 0,30 independente do tamanho do lote
    if zona.startswith("ZCOR"):
        tp_min = 0.30
        notas.append("Nota (a) Quadro 4: Em ZCOR aplica-se taxa de permeabilidade mínima de 0,30 independente da área do lote.")

    # Nota (e) do Quadro 4: PA 13 não exige quota ambiental
    if pa.upper().startswith("PA 13"):
        tp_min = 0.0
        notas.append("Nota (e) Quadro 4: PA 13 corresponde às Macroáreas de Contenção/Preservação (isento de Quota Ambiental).")

    # Nota (b) do Quadro 4: se TO + TP > 1.0, respeita TP e reduz TO proporcionalmente
    to_max = to_tabela
    if to_max is not None and tp_min is not None and (to_max + tp_min) > 1.0:
        to_max = round(1.0 - tp_min, 4)
        notas.append(
            f"Nota (b) Quadro 4: Como T.O. ({to_tabela:.2f}) + T.P. ({tp_min:.2f}) > 1,00, "
            f"a T.O. máxima foi ajustada para {to_max:.2f}."
        )

    # Gabarito (C51)
    gabarito_m, nota_gab = parse_numero_tabela(d_q2.get("gabarito_m") or d_q3.get("gabarito_m"))
    if nota_gab in ("c", "d"):
        notas.append(
            f"Nota ({nota_gab}) Quadro 2: Em {zona}, o CA Máximo poderá chegar a 6 (EHIS) / 5 (EHMP) com dispensa de gabarito nos termos do art. 8º da LPUOS."
        )

    # Recuos e Cota-parte (N8:N33 / AO6:AO44)
    recuo_frente = str(d_q2.get("recuo_frente") or d_q3.get("recuo_frente") or "NA")
    recuo_ate_10m = str(d_q2.get("recuo_ate_10m") or d_q3.get("recuo_ate_10m") or "NA")
    recuo_acima_10m = str(d_q2.get("recuo_acima_10m") or d_q3.get("recuo_acima_10m") or "3 (j)")
    cota_parte_m2, _ = parse_numero_tabela(d_q2.get("cota_parte") or d_q3.get("cota_parte"))

    # Fachada Ativa: 50% em ZEU, ZEUa, ZEUP, ZEUPa, ZEM, ZEMP, ZC; 20% nas demais (Q. LUOPS!G20)
    zonas_fa_50 = {"ZEU", "ZEUa", "ZEUP", "ZEUPa", "ZEM", "ZEMP", "ZC", "ZC-ZEIS"}
    fachada_ativa_pct = 0.50 if zona in zonas_fa_50 else 0.20

    # Seleção do C.A. do projeto (W38) conforme modalidade escolhida
    if ca_customizado is not None and ca_customizado > 0:
        ca_projeto = float(ca_customizado)
    elif modalidade == "LPUOS":
        ca_projeto = ca_max_lpuos
    elif modalidade == "EHMP":
        ca_projeto = ca_ehmp or ca_max_lpuos
    elif modalidade == "EHIS":
        ca_projeto = ca_ehis
    elif modalidade == "EZEIS":
        ca_projeto = ca_ehis
    else:  # EHIS_COTA (+20%) ou padrão
        ca_projeto = ca_ehmp if (zona == "ZM" and ca_customizado is None and modalidade == "PADRAO_PLANILHA") else (ca_majorado or ca_ehis)

    proporcao_his = 0.60 if (modalidade == "EZEIS" or zona == "ZEIS-5") else 0.80

    # Áreas aplicadas ao terreno (D43:D47 e T46)
    area_ocup_max = round(area * to_max, 2) if to_max is not None else None
    area_comp_bas = round(area * ca_bas, 2) if ca_bas is not None else None
    area_comp_lpuos = round(area * ca_max_lpuos, 2) if ca_max_lpuos is not None else None
    area_comp_his = round(area * ca_ehis, 2) if ca_ehis is not None else None
    area_perm_min = round(area * tp_min, 2) if tp_min is not None else None
    area_comp_proj = round(area * ca_projeto, 2) if ca_projeto is not None else None

    return IndicesLegais(
        zona=zona,
        pa=pa,
        area_terreno_m2=area,
        modalidade=modalidade,
        to_max=to_max,
        to_tabela=to_tabela,
        ca_minimo=ca_min,
        ca_basico=ca_bas,
        ca_maximo_lpuos=ca_max_lpuos,
        ca_max_ehis=ca_ehis,
        ca_max_ehmp=ca_ehmp,
        ca_majorado=ca_majorado,
        ca_projeto=ca_projeto,
        tp_min=tp_min,
        gabarito_m=gabarito_m,
        recuo_frente=recuo_frente,
        recuo_ate_10m=recuo_ate_10m,
        recuo_acima_10m=recuo_acima_10m,
        cota_parte_m2=cota_parte_m2,
        fachada_ativa_pct=fachada_ativa_pct,
        proporcao_his=proporcao_his,
        area_ocupacao_max_m2=area_ocup_max,
        area_comp_basica_m2=area_comp_bas,
        area_comp_max_lpuos_m2=area_comp_lpuos,
        area_comp_max_his_m2=area_comp_his,
        area_permeavel_min_m2=area_perm_min,
        area_comp_projeto_m2=area_comp_proj,
        notas=notas,
    )

