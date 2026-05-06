import streamlit as st
import pandas as pd
import numpy as np
import unicodedata
import requests
from bs4 import BeautifulSoup
import re
from scipy.signal import fftconvolve
from datetime import datetime, timedelta
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.ticker import FuncFormatter
import yfinance as yf

# Configuração da página
st.set_page_config(
    page_title="Potencial de Compostagem de RSU",
    layout="wide"
)

st.title("🌱 Potencial de Compostagem e Vermicompostagem por Município")
st.markdown("""
Este aplicativo interpreta os **tipos de coleta executada** informados pelos municípios
e avalia o **potencial técnico para compostagem e vermicompostagem**
de resíduos sólidos urbanos.
""")

# =========================================================
# Seleção de Ano
# =========================================================
ano_selecionado = st.selectbox(
    "Selecione o ano de referência:",
    ["2023", "2024"],
    index=1
)

URLS_POR_ANO = {
    "2023": "https://github.com/loopvinyl/tco2eqv7/raw/main/rsuBrasil_2023.xlsx",
    "2024": "https://github.com/loopvinyl/tco2eqv7/raw/main/rsuBrasil_2024.xlsx"
}

# =========================================================
# FUNÇÕES DE COTAÇÃO (tco2eq)
# =========================================================
def obter_cotacao_carbono():
    """Obtém cotação do carbono via Yahoo Finance, fallback €85,50."""
    try:
        ticker = yf.Ticker("CO2.L")
        data = ticker.history(period="1d")
        if not data.empty:
            preco = data['Close'].iloc[-1]
            if 10 < preco < 200:
                return preco, "€", "Carbon Futures (CO2.L)", True, "Yahoo Finance"
    except:
        pass
    return 85.50, "€", "Referência", False, "Referência"

def obter_cotacao_euro_real():
    """Cotação EUR/BRL com APIs públicas."""
    try:
        resp = requests.get("https://economia.awesomeapi.com.br/last/EUR-BRL", timeout=10)
        if resp.status_code == 200:
            return float(resp.json()['EURBRL']['bid']), "R$", True, "AwesomeAPI"
    except:
        pass
    try:
        resp = requests.get("https://api.exchangerate-api.com/v4/latest/EUR", timeout=10)
        if resp.status_code == 200:
            return resp.json()['rates']['BRL'], "R$", True, "ExchangeRate-API"
    except:
        pass
    return 5.50, "R$", False, "Referência"

def calcular_valor_creditos(emissoes_evitadas, preco_ton, moeda, taxa_cambio=1):
    return emissoes_evitadas * preco_ton * taxa_cambio

# Inicialização das cotações no session_state
if 'preco_carbono' not in st.session_state:
    preco, moeda, _, _, _ = obter_cotacao_carbono()
    st.session_state.preco_carbono = preco
    st.session_state.moeda_carbono = moeda
if 'taxa_cambio' not in st.session_state:
    cambio, moeda_r, _, _ = obter_cotacao_euro_real()
    st.session_state.taxa_cambio = cambio
    st.session_state.moeda_real = moeda_r

# Formatações
def formatar_br(numero):
    if pd.isna(numero) or numero is None:
        return "N/A"
    numero = round(numero, 2)
    return f"{numero:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def br_format(x, pos):
    if x == 0:
        return "0"
    if abs(x) < 0.01:
        return f"{x:.1e}".replace(".", ",")
    if abs(x) >= 1000:
        return f"{x:,.0f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def formatar_numero_br(valor, decimais=2):
    if pd.isna(valor) or valor is None:
        return "Não informado"
    try:
        num = float(valor)
        formato = f"{{:,.{decimais}f}}".format(num)
        partes = formato.split(".")
        milhar = partes[0].replace(",", "X").replace(".", ",").replace("X", ".")
        return f"{milhar},{partes[1]}"
    except:
        return "Não informado"

def formatar_massa_br(valor):
    if pd.isna(valor) or valor is None:
        return "Não informado"
    return f"{formatar_numero_br(valor)} t"

def normalizar_texto(txt):
    if pd.isna(txt):
        return ""
    txt = unicodedata.normalize("NFKD", str(txt))
    txt = txt.encode("ASCII", "ignore").decode("utf-8")
    return txt.upper().strip()

def classificar_tipo_aterro(mcf):
    if mcf >= 0.95:
        return "Aterro Sanitário Gerenciado"
    elif mcf >= 0.6:
        return "Aterro Sanitário Não Gerenciado"
    elif mcf > 0:
        return "Aterro Controlado/Lixão"
    else:
        return "Não Aterro"

# =========================================================
# PARÂMETROS GERAIS (tco2eq)
# =========================================================
GWP_CH4_20 = 79.7
GWP_N2O_20 = 273.0
ANOS_PROJECAO = 20
DIAS_PROJECAO = ANOS_PROJECAO * 365
UMIDADE_PADRAO = 0.85
PHI_BASELINE = 0.85
CAPTURA_CH4 = 0.0

# Pré‑descarte
CH4_PRE_KG_POR_KG_DIA = 2.78 * (16/12) * 24 / 1_000_000
N2O_PRE_KG_POR_KG_DIA = (20.26 / 3) * (44/28) / 1_000_000
PROFILE_N2O_PRE = {1: 0.8623, 2: 0.10, 3: 0.0377}
PROFILE_N2O_LANDFILL = {1: 0.10, 2: 0.30, 3: 0.40, 4: 0.15, 5: 0.05}

# Parâmetros por tipo
T_ORGANICO, DOC_ORGANICO, k_ano_ORGANICO = 25.0, 0.15, 0.06
TOC_ORGANICO, TN_ORGANICO = 0.436, 14.2 / 1000
CH4_C_FRAC_YANG_ORGANICO = 0.13 / 100
CH4_C_FRAC_THERMO_ORGANICO = 0.006
N2O_N_FRAC_YANG_ORGANICO = 0.92 / 100
N2O_N_FRAC_THERMO_ORGANICO = 0.0196
DIAS_COMPOSTAGEM_ORGANICO = 50

T_PODAS, DOC_PODAS, k_ano_PODAS = 25.0, 0.10, 0.03
TOC_PODAS, TN_PODAS = 0.50, 5.0 / 1000
CH4_C_FRAC_YANG_PODAS = 0.02 / 100
CH4_C_FRAC_THERMO_PODAS = 0.001
N2O_N_FRAC_YANG_PODAS = 0.10 / 100
N2O_N_FRAC_THERMO_PODAS = 0.005
DIAS_COMPOSTAGEM_PODAS = 90

# Perfis (já normalizados)
def carregar_perfis():
    p_ch4_vermi_org = np.array([
        0.02, 0.02, 0.02, 0.03, 0.03, 0.04, 0.04, 0.05, 0.05, 0.06,
        0.07, 0.08, 0.09, 0.10, 0.09, 0.08, 0.07, 0.06, 0.05, 0.04,
        0.03, 0.02, 0.02, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01,
        0.005, 0.005, 0.005, 0.005, 0.005, 0.005, 0.005, 0.005, 0.005, 0.005,
        0.002, 0.002, 0.002, 0.002, 0.002, 0.001, 0.001, 0.001, 0.001, 0.001
    ])
    p_ch4_vermi_org /= p_ch4_vermi_org.sum()

    p_n2o_vermi_org = np.array([
        0.15, 0.10, 0.20, 0.05, 0.03, 0.03, 0.03, 0.04, 0.05, 0.06,
        0.08, 0.09, 0.10, 0.08, 0.07, 0.06, 0.05, 0.04, 0.03, 0.02,
        0.01, 0.01, 0.005, 0.005, 0.005, 0.005, 0.005, 0.005, 0.005, 0.005,
        0.002, 0.002, 0.002, 0.002, 0.002, 0.001, 0.001, 0.001, 0.001, 0.001,
        0.001, 0.001, 0.001, 0.001, 0.001, 0.001, 0.001, 0.001, 0.001, 0.001
    ])
    p_n2o_vermi_org /= p_n2o_vermi_org.sum()

    p_ch4_thermo_org = p_ch4_vermi_org.copy()

    p_n2o_thermo_org = np.array([
        0.10, 0.08, 0.15, 0.05, 0.03, 0.04, 0.05, 0.07, 0.10, 0.12,
        0.15, 0.18, 0.20, 0.18, 0.15, 0.12, 0.10, 0.08, 0.06, 0.05,
        0.04, 0.03, 0.02, 0.02, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01,
        0.005, 0.005, 0.005, 0.005, 0.005, 0.002, 0.002, 0.002, 0.002, 0.002,
        0.001, 0.001, 0.001, 0.001, 0.001, 0.001, 0.001, 0.001, 0.001, 0.001
    ])
    p_n2o_thermo_org /= p_n2o_thermo_org.sum()

    p_ch4_thermo_podas = np.array([
        0.005, 0.01, 0.02, 0.03, 0.04, 0.05, 0.06, 0.07, 0.08, 0.09,
        0.10, 0.11, 0.12, 0.13, 0.14, 0.15, 0.16, 0.17, 0.18, 0.18,
        0.18, 0.17, 0.16, 0.15, 0.14, 0.13, 0.12, 0.11, 0.10, 0.09,
        0.08, 0.07, 0.06, 0.05, 0.04, 0.03, 0.03, 0.03, 0.03, 0.03,
        0.03, 0.03, 0.03, 0.02, 0.02, 0.02, 0.02, 0.02, 0.02, 0.02,
        0.02, 0.02, 0.02, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01,
        0.01, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01,
        0.01, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01,
        0.01, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01
    ])
    p_ch4_thermo_podas /= p_ch4_thermo_podas.sum()

    p_n2o_thermo_podas = np.array([
        0.05, 0.04, 0.07, 0.02, 0.01, 0.02, 0.02, 0.03, 0.04, 0.06,
        0.08, 0.09, 0.10, 0.09, 0.07, 0.06, 0.05, 0.04, 0.03, 0.02,
        0.01, 0.01, 0.005, 0.005, 0.005, 0.005, 0.005, 0.005, 0.005, 0.005,
        0.002, 0.002, 0.002, 0.002, 0.002, 0.001, 0.001, 0.001, 0.001, 0.001,
        0.001, 0.001, 0.001, 0.001, 0.001, 0.001, 0.001, 0.001, 0.001, 0.001,
        0.001, 0.001, 0.001, 0.001, 0.001, 0.001, 0.001, 0.001, 0.001, 0.001,
        0.001, 0.001, 0.001, 0.001, 0.001, 0.001, 0.001, 0.001, 0.001, 0.001,
        0.001, 0.001, 0.001, 0.001, 0.001, 0.001, 0.001, 0.001, 0.001, 0.001,
        0.001, 0.001, 0.001, 0.001, 0.001, 0.001, 0.001, 0.001, 0.001, 0.001
    ])
    p_n2o_thermo_podas /= p_n2o_thermo_podas.sum()

    return (p_ch4_vermi_org, p_n2o_vermi_org,
            p_ch4_thermo_org, p_n2o_thermo_org,
            p_ch4_thermo_podas, p_n2o_thermo_podas)

(p_ch4_vermi_org, p_n2o_vermi_org,
 p_ch4_thermo_org, p_n2o_thermo_org,
 p_ch4_thermo_podas, p_n2o_thermo_podas) = carregar_perfis()

# =========================================================
# FUNÇÕES DE CÁLCULO
# =========================================================
def calcular_emissoes_aterro_tco2eq(massa_kg_dia, mcf, k_ano, temp_C, doc, dias=DIAS_PROJECAO):
    docf = 0.0147 * temp_C + 0.28
    ch4_pot = doc * docf * mcf * 0.5 * (16/12) * (1 - 0.1)
    ch4_diario_base = massa_kg_dia * ch4_pot
    t = np.arange(1, dias + 1, dtype=float)
    kernel_ch4 = np.exp(-k_ano * (t - 1) / 365.0) - np.exp(-k_ano * t / 365.0)
    ch4_decaido = fftconvolve(np.ones(dias) * ch4_diario_base, kernel_ch4, mode='full')[:dias]
    ch4_decaido *= PHI_BASELINE * (1 - CAPTURA_CH4)

    opening = np.clip((100.0 / massa_kg_dia) * (8.0 / 24), 0.0, 1.0)
    E_avg = opening * 1.91 + (1 - opening) * 2.15
    E_avg *= (1 - UMIDADE_PADRAO) / (1 - 0.55)
    n2o_diario_base = (E_avg * (44/28) / 1_000_000) * massa_kg_dia
    kernel_n2o = np.array([PROFILE_N2O_LANDFILL.get(d, 0) for d in range(1, 6)])
    n2o_decaido = fftconvolve(np.full(dias, n2o_diario_base), kernel_n2o, mode='full')[:dias]

    ch4_pre = np.full(dias, massa_kg_dia * CH4_PRE_KG_POR_KG_DIA)
    n2o_pre = np.zeros(dias)
    for dia_entrada in range(dias):
        for d_atraso, frac in PROFILE_N2O_PRE.items():
            dia_emissao = dia_entrada + d_atraso - 1
            if dia_emissao < dias:
                n2o_pre[dia_emissao] += massa_kg_dia * N2O_PRE_KG_POR_KG_DIA * frac

    ch4_total = ch4_decaido + ch4_pre
    n2o_total = n2o_decaido + n2o_pre
    co2eq = (ch4_total * GWP_CH4_20 + n2o_total * GWP_N2O_20) / 1000.0
    return ch4_total, n2o_total, co2eq

def calcular_co2eq_total_aterro_20anos(massa_t_ano, mcf, tipo_residuo):
    if massa_t_ano <= 0 or mcf <= 0:
        return 0.0
    if tipo_residuo == 'podas':
        k, doc, temp = k_ano_PODAS, DOC_PODAS, T_PODAS
    else:
        k, doc, temp = k_ano_ORGANICO, DOC_ORGANICO, T_ORGANICO
    massa_kg_dia = (massa_t_ano * 1000) / 365.0
    _, _, co2eq_dia = calcular_emissoes_aterro_tco2eq(massa_kg_dia, mcf, k, temp, doc)
    return co2eq_dia.sum()

def calcular_ch4_total_aterro_20anos(massa_t_ano, mcf, tipo_residuo):
    if massa_t_ano <= 0 or mcf <= 0:
        return 0.0
    doc = DOC_ORGANICO if tipo_residuo == 'organico' else DOC_PODAS
    temp = T_ORGANICO if tipo_residuo == 'organico' else T_PODAS
    docf = 0.0147 * temp + 0.28
    ch4_pot = doc * docf * mcf * 0.5 * (16/12) * (1 - 0.1)
    massa_kg_dia = (massa_t_ano * 1000) / 365
    ch4_diario = massa_kg_dia * ch4_pot
    t = np.arange(1, DIAS_PROJECAO + 1, dtype=float)
    k = k_ano_ORGANICO if tipo_residuo == 'organico' else k_ano_PODAS
    kernel = np.exp(-k * (t - 1) / 365.0) - np.exp(-k * t / 365.0)
    emissoes = fftconvolve(np.ones(DIAS_PROJECAO) * ch4_diario, kernel, mode='full')[:DIAS_PROJECAO]
    return emissoes.sum() / 1000

def calcular_emissoes_compostagem_diarias(massa_kg_dia, tipo_residuo):
    if tipo_residuo == 'organico':
        TOC, TN = TOC_ORGANICO, TN_ORGANICO
        f_ch4, f_n2o = CH4_C_FRAC_THERMO_ORGANICO, N2O_N_FRAC_THERMO_ORGANICO
        p_ch4, p_n2o = p_ch4_thermo_org, p_n2o_thermo_org
    else:
        TOC, TN = TOC_PODAS, TN_PODAS
        f_ch4, f_n2o = CH4_C_FRAC_THERMO_PODAS, N2O_N_FRAC_THERMO_PODAS
        p_ch4, p_n2o = p_ch4_thermo_podas, p_n2o_thermo_podas
    ch4_por_lote = massa_kg_dia * TOC * f_ch4 * (16/12)
    n2o_por_lote = massa_kg_dia * TN * f_n2o * (44/28)
    entradas = np.ones(DIAS_PROJECAO, dtype=float)
    ch4_dia = fftconvolve(entradas, p_ch4 * ch4_por_lote, mode='full')[:DIAS_PROJECAO]
    n2o_dia = fftconvolve(entradas, p_n2o * n2o_por_lote, mode='full')[:DIAS_PROJECAO]
    return ch4_dia, n2o_dia

def calcular_emissoes_vermicompostagem_diarias(massa_kg_dia):
    TOC, TN = TOC_ORGANICO, TN_ORGANICO
    f_ch4, f_n2o = CH4_C_FRAC_YANG_ORGANICO, N2O_N_FRAC_YANG_ORGANICO
    p_ch4, p_n2o = p_ch4_vermi_org, p_n2o_vermi_org
    ch4_por_lote = massa_kg_dia * TOC * f_ch4 * (16/12)
    n2o_por_lote = massa_kg_dia * TN * f_n2o * (44/28)
    entradas = np.ones(DIAS_PROJECAO, dtype=float)
    ch4_dia = fftconvolve(entradas, p_ch4 * ch4_por_lote, mode='full')[:DIAS_PROJECAO]
    n2o_dia = fftconvolve(entradas, p_n2o * n2o_por_lote, mode='full')[:DIAS_PROJECAO]
    return ch4_dia, n2o_dia

# =========================================================
# MCF por destino
# =========================================================
def determinar_mcf_por_destino(destino, tipo_residuo='organico'):
    if pd.isna(destino):
        return 0.0
    destino_norm = normalizar_texto(destino)
    if "ATERRO SANITARIO" in destino_norm:
        mcf_base = 1.0 if "GERENCIADO" in destino_norm or "COLETA" in destino_norm else 0.8
    elif "ATERRO CONTROLADO" in destino_norm:
        mcf_base = 0.4
    elif "LIXAO" in destino_norm or "VAZADOURO" in destino_norm:
        mcf_base = 0.4
    else:
        mcf_base = 0.0
    if tipo_residuo == 'podas' and mcf_base > 0:
        return mcf_base * 0.5
    return mcf_base

# =========================================================
# Carga e preparação dos dados
# =========================================================
@st.cache_data
def load_data(ano):
    url = URLS_POR_ANO[ano]
    df = pd.read_excel(url, sheet_name="Manejo_Coleta_e_Destinação", header=13)
    df = df.dropna(how="all")
    df.columns = [str(col).strip() for col in df.columns]
    return df

df = load_data(ano_selecionado)

# Definição de colunas principais
COL_CODIGO_ROTA = df.columns[16]   # Código da rota (ex.: 3543402DEST001)
COL_MUNICIPIO = df.columns[2]      # será renomeado
COL_TIPO_COLETA = df.columns[17]   # será renomeado
COL_MASSA = df.columns[24]         # será renomeado
COL_DESTINO = df.columns[28]       # Tipo de unidade de destino

df = df.rename(columns={
    COL_MUNICIPIO: "MUNICÍPIO",
    COL_TIPO_COLETA: "TIPO_COLETA_EXECUTADA",
    COL_MASSA: "MASSA_COLETADA"
})

# Atualiza as referências para os nomes renomeados
COL_MUNICIPIO = "MUNICÍPIO"
COL_TIPO_COLETA = "TIPO_COLETA_EXECUTADA"
COL_MASSA = "MASSA_COLETADA"

def classificar_coleta(texto):
    if pd.isna(texto):
        return ("Não informado", False, False, "Tipo não informado")
    t = str(texto).lower()
    palavras = {
        "compostagem": ("Orgânico direto", True, True, "Coleta para compostagem"),
        "vermicompostagem": ("Orgânico direto", True, True, "Coleta para vermicompostagem"),
        "poda": ("Orgânico direto", True, True, "Resíduo vegetal limpo"),
        "galhada": ("Orgânico direto", True, True, "Resíduo vegetal limpo"),
        "verde": ("Orgânico direto", True, True, "Resíduo vegetal limpo"),
        "orgânica": ("Orgânico direto", True, True, "Orgânico segregado"),
        "domiciliar": ("Orgânico potencial", True, False, "Exige triagem"),
        "varrição": ("Inapto", False, False, "Alta contaminação"),
        "seletiva": ("Não orgânico", False, False, "Recicláveis")
    }
    for p, c in palavras.items():
        if p in t:
            return c
    return ("Indefinido", False, False, "Não classificado")

df_clean = df.dropna(subset=[COL_MUNICIPIO])
df_clean[COL_MUNICIPIO] = df_clean[COL_MUNICIPIO].astype(str).str.strip()
municipios = ["BRASIL – Todos os municípios"] + sorted(df_clean[COL_MUNICIPIO].unique())
municipio = st.selectbox("Selecione o município:", municipios)
df_mun = df_clean.copy() if municipio == municipios[0] else df_clean[df_clean[COL_MUNICIPIO] == municipio]

st.subheader(f"🇧🇷 Brasil — Síntese Nacional de RSU ({ano_selecionado})" if municipio == municipios[0] else f"📍 {municipio} - Ano {ano_selecionado}")

# =========================================================
# 🗺️ Destinação Final (exatamente igual ao Excel)
# =========================================================
st.markdown("---")
st.subheader("🗺️ Para onde o resíduo está indo? (Destinação Final)")

df_mun["MASSA_FLOAT"] = pd.to_numeric(df_mun[COL_MASSA], errors="coerce").fillna(0)

# Exibe todas as rotas individuais, sem agregação
tabela_destino = df_mun[[COL_CODIGO_ROTA, COL_TIPO_COLETA, COL_DESTINO, "MASSA_FLOAT"]].copy()
tabela_destino = tabela_destino.rename(columns={
    COL_CODIGO_ROTA: "Código Rota",
    COL_TIPO_COLETA: "Tipo de Coleta",
    COL_DESTINO: "Destino",
    "MASSA_FLOAT": "Massa (t)"
})
tabela_destino["Massa (t)"] = tabela_destino["Massa (t)"].apply(formatar_numero_br)

st.dataframe(tabela_destino, use_container_width=True)

massa_total = df_mun["MASSA_FLOAT"].sum()
st.caption(f"Massa total coletada: **{formatar_numero_br(massa_total)} t**")

st.info("""
📌 **Nota:** A tabela acima mostra os registros exatamente como declarados no SNIS, sem nenhuma agregação ou filtro.
Os valores correspondem à massa anual coletada para cada rota e destino.
""")

# ============================================================
# ♻️ ORGÂNICOS (demais seções mantidas)
# ============================================================
st.markdown("---")
st.subheader("♻️ Destinação da Coleta Seletiva de Resíduos Orgânicos")
df_organicos = df_mun[df_mun[COL_TIPO_COLETA].astype(str).str.contains(
    "seletiva.*orgânico|orgânico.*seletiva", case=False, na=False, regex=True)].copy()

if not df_organicos.empty:
    df_organicos["MASSA_FLOAT"] = pd.to_numeric(df_organicos[COL_MASSA], errors="coerce").fillna(0)
    total_organicos = df_organicos["MASSA_FLOAT"].sum()
    st.metric("Massa total de orgânicos coletados seletivamente", f"{formatar_numero_br(total_organicos)} t")

    df_org_dest = df_organicos.groupby(COL_DESTINO)["MASSA_FLOAT"].sum().reset_index()
    df_org_dest["%"] = df_org_dest["MASSA_FLOAT"] / total_organicos * 100
    df_org_dest = df_org_dest.sort_values("%", ascending=False)
    df_org_dest_view = df_org_dest.copy()
    df_org_dest_view["Massa (t)"] = df_org_dest_view["MASSA_FLOAT"].apply(formatar_numero_br)
    df_org_dest_view["%"] = df_org_dest_view["%"].apply(lambda x: formatar_numero_br(x, 1))
    st.dataframe(df_org_dest_view[[COL_DESTINO, "Massa (t)", "%"]], use_container_width=True)

    st.subheader("🔥 Emissões detalhadas (Orgânicos)")
    df_org_dest["MCF"] = df_org_dest[COL_DESTINO].apply(lambda x: determinar_mcf_por_destino(x, 'organico'))
    resultados, massas_num, mcfs_num = [], [], []
    co2eq_aterro_total, massa_aterro_total = 0.0, 0.0
    for _, row in df_org_dest.iterrows():
        massa_t, mcf = row["MASSA_FLOAT"], row["MCF"]
        if mcf > 0 and massa_t > 0:
            co2 = calcular_co2eq_total_aterro_20anos(massa_t, mcf, 'organico')
            ch4 = calcular_ch4_total_aterro_20anos(massa_t, mcf, 'organico')
            co2eq_aterro_total += co2
            massa_aterro_total += massa_t
            massas_num.append(massa_t)
            mcfs_num.append(mcf)
            resultados.append({
                "Destino": row[COL_DESTINO],
                "Massa (t)": formatar_numero_br(massa_t),
                "MCF": formatar_numero_br(mcf, 2),
                "CO₂e (t) 20 anos": formatar_numero_br(co2, 1),
                "CH₄ (t) 20 anos": formatar_numero_br(ch4, 3),
                "Tipo de Aterro": classificar_tipo_aterro(mcf)
            })
    if resultados:
        st.dataframe(pd.DataFrame(resultados), use_container_width=True)
        massa_kg_dia = (massa_aterro_total * 1000) / 365
        ch4_comp, n2o_comp = calcular_emissoes_compostagem_diarias(massa_kg_dia, 'organico')
        ch4_vermi, n2o_vermi = calcular_emissoes_vermicompostagem_diarias(massa_kg_dia)
        co2eq_comp = (ch4_comp.sum() * GWP_CH4_20 + n2o_comp.sum() * GWP_N2O_20) / 1000
        co2eq_vermi = (ch4_vermi.sum() * GWP_CH4_20 + n2o_vermi.sum() * GWP_N2O_20) / 1000
        evitado_comp = co2eq_aterro_total - co2eq_comp
        evitado_vermi = co2eq_aterro_total - co2eq_vermi

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Massa em aterros", formatar_massa_br(massa_aterro_total))
        col2.metric("CO₂e do aterro (20 anos)", f"{formatar_numero_br(co2eq_aterro_total, 1)} tCO₂e",
                    help="CH₄ + N₂O + pré‑descarte, φ=0,85")
        col3.metric("Evitado Compostagem", f"{formatar_numero_br(evitado_comp, 1)} tCO₂e")
        col4.metric("Evitado Vermicompostagem", f"{formatar_numero_br(evitado_vermi, 1)} tCO₂e")
        st.info(f"**Metodologia (tco2eq):** Aterro: CH₄+N₂O; φ=0,85; k={k_ano_ORGANICO} ano⁻¹. Compostagem e vermicompostagem: CH₄+N₂O (perfis diários).")

        # Gráfico
        st.markdown("---")
        st.subheader("📉 Redução de Emissões Acumulada (Orgânicos)")
        if massas_num:
            mcf_medio = np.average(mcfs_num, weights=massas_num)
        else:
            mcf_medio = 0.8
        _, _, co2eq_aterro_dia = calcular_emissoes_aterro_tco2eq(massa_kg_dia, mcf_medio, k_ano_ORGANICO, T_ORGANICO, DOC_ORGANICO)
        co2eq_comp_dia = (ch4_comp * GWP_CH4_20 + n2o_comp * GWP_N2O_20) / 1000
        co2eq_vermi_dia = (ch4_vermi * GWP_CH4_20 + n2o_vermi * GWP_N2O_20) / 1000
        datas = [datetime(2024, 1, 1) + timedelta(days=i) for i in range(DIAS_PROJECAO)]
        df_plot = pd.DataFrame({
            'Data': datas,
            'Aterro': co2eq_aterro_dia.cumsum(),
            'Compostagem': co2eq_comp_dia.cumsum(),
            'Vermicompostagem': co2eq_vermi_dia.cumsum()
        })
        plt.style.use('dark_background')
        fig, ax = plt.subplots(figsize=(12, 6))
        ax.plot(df_plot['Data'], df_plot['Aterro'], 'r-', label='Aterro', linewidth=2)
        ax.plot(df_plot['Data'], df_plot['Compostagem'], 'g-', label='Compostagem', linewidth=2)
        ax.plot(df_plot['Data'], df_plot['Vermicompostagem'], 'b--', label='Vermicompostagem', linewidth=2)
        ax.fill_between(df_plot['Data'], df_plot['Compostagem'], df_plot['Aterro'], color='lightgreen', alpha=0.3)
        ax.set_title('Redução de Emissões Acumulada - Orgânicos')
        ax.set_xlabel('Ano')
        ax.set_ylabel('tCO₂e')
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y'))
        ax.xaxis.set_major_locator(mdates.YearLocator(2))
        plt.xticks(rotation=45, color='white')
        ax.yaxis.set_major_formatter(FuncFormatter(br_format))
        ax.legend()
        st.pyplot(fig)

        # Créditos de carbono
        st.markdown("---")
        st.subheader("💰 Potencial de Créditos de Carbono (Orgânicos)")

        with st.container():
            st.markdown("### 🌍 Cotações de Mercado (Cenário Otimista GWP-20)")
            col_cot1, col_cot2, col_cot3 = st.columns(3)
            with col_cot1:
                if st.button("🔄 Atualizar Cotações", key="atualizar_cotacoes_org"):
                    preco, moeda, _, _, _ = obter_cotacao_carbono()
                    cambio, moeda_r, _, _ = obter_cotacao_euro_real()
                    st.session_state.preco_carbono = preco
                    st.session_state.moeda_carbono = moeda
                    st.session_state.taxa_cambio = cambio
                    st.session_state.moeda_real = moeda_r
                    st.rerun()
            preco = st.session_state.preco_carbono
            moeda = st.session_state.moeda_carbono
            cambio = st.session_state.taxa_cambio
            with col_cot2:
                st.metric("Carbono", f"{moeda} {formatar_br(preco)}/tCO₂e")
            with col_cot3:
                st.metric("Câmbio EUR/BRL", f"R$ {formatar_br(cambio)}")
            st.metric("Preço em R$", f"R$ {formatar_br(preco * cambio)}/tCO₂e")

        valor_comp_eur = calcular_valor_creditos(evitado_comp, preco, "€")
        valor_comp_brl = calcular_valor_creditos(evitado_comp, preco, "R$", cambio)
        valor_vermi_eur = calcular_valor_creditos(evitado_vermi, preco, "€")
        valor_vermi_brl = calcular_valor_creditos(evitado_vermi, preco, "R$", cambio)

        st.markdown("#### 💶 Compostagem")
        col1, col2 = st.columns(2)
        col1.metric("Valor total (€)", f"{moeda} {formatar_br(valor_comp_eur)}")
        col2.metric("Valor total (R$)", f"R$ {formatar_br(valor_comp_brl)}")
        st.markdown("#### 💶 Vermicompostagem")
        col1, col2 = st.columns(2)
        col1.metric("Valor total (€)", f"{moeda} {formatar_br(valor_vermi_eur)}")
        col2.metric("Valor total (R$)", f"R$ {formatar_br(valor_vermi_brl)}")
    else:
        st.success("✅ Nenhum orgânico destinado a aterro.")
else:
    st.info("ℹ️ Sem registros de coleta seletiva de orgânicos.")

# ============================================================
# 🌳 PODAS E GALHADAS
# ============================================================
st.markdown("---")
st.subheader("🌳 Destinação das podas e galhadas de áreas verdes públicas")
df_podas = df_mun[df_mun[COL_TIPO_COLETA].astype(str).str.contains("áreas verdes públicas", case=False, na=False)].copy()

if not df_podas.empty:
    df_podas["MASSA_FLOAT"] = pd.to_numeric(df_podas[COL_MASSA], errors="coerce").fillna(0)
    total_podas = df_podas["MASSA_FLOAT"].sum()
    st.metric("Massa total de podas e galhadas", f"{formatar_numero_br(total_podas)} t")

    df_pod_dest = df_podas.groupby(COL_DESTINO)["MASSA_FLOAT"].sum().reset_index()
    df_pod_dest["%"] = df_pod_dest["MASSA_FLOAT"] / total_podas * 100
    df_pod_dest = df_pod_dest.sort_values("%", ascending=False)
    df_view_pod = df_pod_dest.copy()
    df_view_pod["Massa (t)"] = df_view_pod["MASSA_FLOAT"].apply(formatar_numero_br)
    df_view_pod["%"] = df_view_pod["%"].apply(lambda x: formatar_numero_br(x, 1))
    st.dataframe(df_view_pod[[COL_DESTINO, "Massa (t)", "%"]], use_container_width=True)

    st.subheader("🔥 Emissões detalhadas (Podas e Galhadas)")
    df_pod_dest["MCF"] = df_pod_dest[COL_DESTINO].apply(lambda x: determinar_mcf_por_destino(x, 'podas'))
    resultados, massas_num, mcfs_num = [], [], []
    co2eq_aterro_total, massa_aterro_total = 0.0, 0.0
    for _, row in df_pod_dest.iterrows():
        massa_t, mcf = row["MASSA_FLOAT"], row["MCF"]
        if mcf > 0 and massa_t > 0:
            co2 = calcular_co2eq_total_aterro_20anos(massa_t, mcf, 'podas')
            ch4 = calcular_ch4_total_aterro_20anos(massa_t, mcf, 'podas')
            co2eq_aterro_total += co2
            massa_aterro_total += massa_t
            massas_num.append(massa_t)
            mcfs_num.append(mcf)
            resultados.append({
                "Destino": row[COL_DESTINO],
                "Massa (t)": formatar_numero_br(massa_t),
                "MCF": formatar_numero_br(mcf, 2),
                "CO₂e (t) 20 anos": formatar_numero_br(co2, 1),
                "CH₄ (t) 20 anos": formatar_numero_br(ch4, 3),
                "Tipo de Aterro": classificar_tipo_aterro(mcf)
            })
    if resultados:
        st.dataframe(pd.DataFrame(resultados), use_container_width=True)
        massa_kg_dia = (massa_aterro_total * 1000) / 365
        ch4_comp, n2o_comp = calcular_emissoes_compostagem_diarias(massa_kg_dia, 'podas')
        co2eq_comp = (ch4_comp.sum() * GWP_CH4_20 + n2o_comp.sum() * GWP_N2O_20) / 1000
        evitado_comp = co2eq_aterro_total - co2eq_comp

        col1, col2, col3 = st.columns(3)
        col1.metric("Massa em aterros", formatar_massa_br(massa_aterro_total))
        col2.metric("CO₂e do aterro (20 anos)", f"{formatar_numero_br(co2eq_aterro_total, 1)} tCO₂e",
                    help="CH₄ + N₂O + pré‑descarte, φ=0,85")
        col3.metric("Evitado Compostagem", f"{formatar_numero_br(evitado_comp, 1)} tCO₂e")
        st.info(f"**Metodologia (podas):** k={k_ano_PODAS}, DOC={DOC_PODAS}. Compostagem em leiras a céu aberto (CH₄+N₂O). Vermicompostagem não recomendada.")

        # Créditos de carbono (podas)
        st.markdown("---")
        st.subheader("💰 Potencial de Créditos de Carbono (Podas - Compostagem)")

        with st.container():
            st.markdown("### 🌍 Cotações de Mercado (Cenário Otimista GWP-20)")
            col_cot1, col_cot2, col_cot3 = st.columns(3)
            with col_cot1:
                if st.button("🔄 Atualizar Cotações", key="atualizar_cotacoes_podas"):
                    preco, moeda, _, _, _ = obter_cotacao_carbono()
                    cambio, moeda_r, _, _ = obter_cotacao_euro_real()
                    st.session_state.preco_carbono = preco
                    st.session_state.moeda_carbono = moeda
                    st.session_state.taxa_cambio = cambio
                    st.session_state.moeda_real = moeda_r
                    st.rerun()
            preco = st.session_state.preco_carbono
            moeda = st.session_state.moeda_carbono
            cambio = st.session_state.taxa_cambio
            with col_cot2:
                st.metric("Carbono", f"{moeda} {formatar_br(preco)}/tCO₂e")
            with col_cot3:
                st.metric("Câmbio EUR/BRL", f"R$ {formatar_br(cambio)}")
            st.metric("Preço em R$", f"R$ {formatar_br(preco * cambio)}/tCO₂e")

        valor_comp_eur = calcular_valor_creditos(evitado_comp, preco, "€")
        valor_comp_brl = calcular_valor_creditos(evitado_comp, preco, "R$", cambio)

        st.markdown("#### 💶 Compostagem")
        col1, col2 = st.columns(2)
        col1.metric("Valor total (€)", f"{moeda} {formatar_br(valor_comp_eur)}")
        col2.metric("Valor total (R$)", f"R$ {formatar_br(valor_comp_brl)}")
    else:
        st.success("✅ Nenhuma poda indo para aterro.")
else:
    st.info("Não há dados de podas e galhadas.")

with st.expander("💡 Inovação sugerida"):
    st.markdown("""
    **Próximo passo:** classificar os municípios por **potencial total de emissões evitadas**
    e gerar um **ranking municipal dinâmico**, identificando onde um projeto de compostagem
    teria maior impacto ambiental e financeiro.
    """)

st.markdown("---")
st.caption(f"""
Fonte: SNIS (ano {ano_selecionado}) | Metodologia: IPCC 2006, Wang et al. (2017), Yang et al. (2017), Feng et al. (2020) |
Baseline do aterro com CH₄ + N₂O; tratamentos também incluem N₂O (conforme tco2eq) |
Cotações em tempo real via Yahoo Finance e APIs de câmbio. |
⚠️ Os dados de destinação final são exibidos exatamente como declarados no SNIS, sem agregação ou filtro.
""")
