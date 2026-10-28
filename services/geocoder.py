"""
Serviço de Geocodificação (Endereço ou CEP -> Coordenadas Lat/Lon em São Paulo).
"""

import re
from typing import Optional, Tuple
import requests


def validar_endereco_input(endereco_ou_cep: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Valida e sanitiza o texto de endereço ou CEP informado pelo usuário.
    Retorna (termo_limpo, None) se válido, ou (None, mensagem_de_erro) se inválido.
    """
    termo = str(endereco_ou_cep or "").strip()
    if not termo:
        return None, "Informe um endereço ou CEP para localizar o terreno."

    # Verifica se o usuário digitou apenas números/traços/pontos (intenção de CEP)
    if re.fullmatch(r"[\d.\-\s]+", termo):
        digitos = re.sub(r"\D", "", termo)
        if len(digitos) != 8:
            return None, "CEP inválido. O CEP deve conter exatamente 8 dígitos (ex.: 01310-200)."
        if not digitos.startswith("0"):
            return None, f"O CEP {digitos[:5]}-{digitos[5:]} não pertence ao município de São Paulo (faixa 01000-000 a 08499-999)."
        return digitos, None

    if len(termo) < 3:
        return None, "Informe um endereço mais completo (mínimo de 3 caracteres)."

    return termo, None


def geocodificar_endereco_sp(endereco_ou_cep: str) -> Tuple[Optional[Tuple[float, float]], Optional[str], Optional[str]]:
    """
    Converte um endereço ou CEP de São Paulo em (latitude, longitude), endereço formatado e erro opcional.
    Utiliza ViaCEP (se for um CEP de 8 dígitos) + Nominatim (OpenStreetMap).
    """
    termo_valido, erro_val = validar_endereco_input(endereco_ou_cep)
    if erro_val or not termo_valido:
        return None, None, erro_val
    termo = termo_valido

    headers = {"User-Agent": "EstudoViabilidadeGeoSampaSP/1.0 (contato@viabilidade.sp.br)"}
    apenas_digitos = re.sub(r"\D", "", termo)

    # 1. Se o usuário digitou um CEP (8 dígitos), consulta ViaCEP primeiro para obter o logradouro exato
    if len(apenas_digitos) == 8:
        try:
            resp_cep = requests.get(f"https://viacep.com.br/ws/{apenas_digitos}/json/", timeout=8)
            if resp_cep.status_code == 200:
                dados_cep = resp_cep.json()
                if not dados_cep.get("erro"):
                    logradouro = dados_cep.get("logradouro", "")
                    bairro = dados_cep.get("bairro", "")
                    localidade = dados_cep.get("localidade", "São Paulo")
                    termo = f"{logradouro}, {bairro}, {localidade}, SP, Brasil"
        except requests.RequestException:
            pass

    # Garante que a busca seja restrita a São Paulo - SP caso não mencionado
    if "são paulo" not in termo.lower() and "sao paulo" not in termo.lower():
        busca_completa = f"{termo}, São Paulo, SP, Brasil"
    else:
        busca_completa = termo

    # 2. Consulta Nominatim (OpenStreetMap)
    try:
        params = {
            "q": busca_completa,
            "format": "jsonv2",
            "limit": 1,
            "countrycodes": "br",
            "viewbox": "-46.826,-23.356,-46.365,-24.008",  # Bounding box do município de São Paulo
            "bounded": 1,
        }
        resp = requests.get("https://nominatim.openstreetmap.org/search", params=params, headers=headers, timeout=10)
        if resp.status_code == 200:
            resultados = resp.json()
            if resultados:
                item = resultados[0]
                lat = float(item["lat"])
                lon = float(item["lon"])
                display_name = item.get("display_name", busca_completa)
                return (lat, lon), display_name, None
    except requests.RequestException as exc:
        return None, None, f"Erro ao consultar serviço de geocodificação: {exc}"

    return None, None, f"Endereço '{endereco_ou_cep}' não encontrado no município de São Paulo."

