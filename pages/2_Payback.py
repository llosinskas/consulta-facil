"""Segunda página do app: fluxo de caixa e gráficos de payback."""

import streamlit as st

from ui.payback_ui import renderizar_pagina_payback

st.set_page_config(page_title="Payback · Estudo de Viabilidade", page_icon="📈", layout="wide")
renderizar_pagina_payback()
