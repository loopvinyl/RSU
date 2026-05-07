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

    return (p_ch4_vermi_org, p_n2o_vermi_org)

(p_ch4_vermi_org, p_n2o_vermi_org) = carregar_perfis()

# =========================================================
# FUNÇÕES DE CÁLCULO – LOTE ÚNICO
# =========================================================
def calcular_emissoes_aterro_lote_unico(massa_total_kg, mcf, k_ano, temp_C, doc, dias=DIAS_PROJECAO):
    docf = 0.0147 * temp_C + 0.28
    ch4_pot_por_kg = doc * docf * mcf * 0.5 * (16/12) * (1 - 0.1)

    t = np.arange(1, dias + 1, dtype=float)
    kernel_ch4 = np.exp(-k_ano * (t - 1) / 365.0) - np.exp(-k_ano * t / 365.0)

    ch4_diario = massa_total_kg * ch4_pot_por_kg * kernel_ch4
    ch4_diario *= PHI_BASELINE * (1 - CAPTURA_CH4)

    n2o_diario = np.zeros(dias)
    opening = np.clip((100.0 / (massa_total_kg / 365)) * (8.0 / 24), 0.0, 1.0) if massa_total_kg > 0 else 0.0
    E_avg = opening * 1.91 + (1 - opening) * 2.15
    E_avg *= (1 - UMIDADE_PADRAO) / (1 - 0.55)
    fator_n2o_por_kg = (E_avg * (44/28) / 1_000_000)
    perfil_anual = np.array([PROFILE_N2O_LANDFILL.get(y, 0) for y in range(1, 6)])
    for ano_idx, peso in enumerate(perfil_anual):
        dia_inicio = ano_idx * 365
        dia_fim = min((ano_idx + 1) * 365, dias)
        n2o_diario[dia_inicio:dia_fim] = (massa_total_kg * fator_n2o_por_kg * peso) / 365

    ch4_pre = np.zeros(dias)
    n2o_pre = np.zeros(dias)
    ch4_pre[:3] = massa_total_kg * CH4_PRE_KG_POR_KG_DIA / 3
    for d_atraso, frac in PROFILE_N2O_PRE.items():
        dia = d_atraso - 1
        if dia < dias:
            n2o_pre[dia] += massa_total_kg * N2O_PRE_KG_POR_KG_DIA * frac

    ch4_total = ch4_diario + ch4_pre
    n2o_total = n2o_diario + n2o_pre
    co2eq_dia = (ch4_total * GWP_CH4_20 + n2o_total * GWP_N2O_20) / 1000.0
    return ch4_total, n2o_total, co2eq_dia

def calcular_emissoes_vermicompostagem_lote_unico(massa_total_kg):
    dias = DIAS_PROJECAO
    ch4_dia = np.zeros(dias)
    n2o_dia = np.zeros(dias)

    ch4_total_lote = massa_total_kg * TOC_ORGANICO * CH4_C_FRAC_YANG_ORGANICO * (16/12)
    n2o_total_lote = massa_total_kg * TN_ORGANICO * N2O_N_FRAC_YANG_ORGANICO * (44/28)

    for d in range(DIAS_COMPOSTAGEM_ORGANICO):
        ch4_dia[d] = ch4_total_lote * p_ch4_vermi_org[d]
        n2o_dia[d] = n2o_total_lote * p_n2o_vermi_org[d]

    return ch4_dia, n2o_dia

def calcular_co2eq_aterro_lote_20anos(massa_t_ano, mcf):
    if massa_t_ano <= 0 or mcf <= 0:
        return 0.0
    massa_kg = massa_t_ano * 1000
    _, _, co2eq_dia = calcular_emissoes_aterro_lote_unico(massa_kg, mcf, k_ano_ORGANICO, T_ORGANICO, DOC_ORGANICO)
    return co2eq_dia.sum()

def calcular_co2eq_vermi_lote_20anos(massa_t_ano):
    if massa_t_ano <= 0:
        return 0.0
    massa_kg = massa_t_ano * 1000
    ch4, n2o = calcular_emissoes_vermicompostagem_lote_unico(massa_kg)
    co2eq = (ch4.sum() * GWP_CH4_20 + n2o.sum() * GWP_N2O_20) / 1000.0
    return co2eq

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

COL_CODIGO_ROTA = df.columns[16]
COL_MUNICIPIO = df.columns[2]
COL_TIPO_COLETA = df.columns[17]
COL_MASSA = df.columns[24]
COL_DESTINO = df.columns[28]
COL_UF = df.columns[3]

df = df.rename(columns={
    COL_MUNICIPIO: "MUNICÍPIO",
    COL_TIPO_COLETA: "TIPO_COLETA_EXECUTADA",
    COL_MASSA: "MASSA_COLETADA"
})

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
# 🗺️ Destinação Final (com checkbox e coluna %)
# =========================================================
st.markdown("---")
st.subheader(f"🗺️ Para onde o resíduo está indo? (Destinação Final, {ano_selecionado})")

ocultar_transbordo = st.checkbox("Ocultar transbordos", value=False)

if ocultar_transbordo:
    df_mun = df_mun[~df_mun[COL_DESTINO].apply(
        lambda x: "TRANSBORDO" in normalizar_texto(x) if pd.notna(x) else False
    )]

df_mun["MASSA_FLOAT"] = pd.to_numeric(df_mun[COL_MASSA], errors="coerce").fillna(0)

massa_total = df_mun["MASSA_FLOAT"].sum()
st.markdown(f"### Total de resíduos coletados: **{formatar_numero_br(massa_total)} t**")
st.markdown("""
A tabela abaixo exibe **cada rota de coleta** e seu respectivo tipo de unidade, exatamente como declarado no SNIS.
Nenhuma agregação ou filtro foi aplicado – os valores correspondem à massa anual coletada para cada rota e destino.
""")

tabela_destino = df_mun[[COL_CODIGO_ROTA, COL_TIPO_COLETA, COL_DESTINO, "MASSA_FLOAT"]].copy()
tabela_destino = tabela_destino.rename(columns={
    COL_CODIGO_ROTA: "Código Rota",
    COL_TIPO_COLETA: "Tipo de Coleta",
    COL_DESTINO: "Tipo de Unidade (SNIS)",
    "MASSA_FLOAT": "Massa (t)"
})

# Calcula percentual em relação ao total exibido (massa_total)
tabela_destino["%"] = (tabela_destino["Massa (t)"] / massa_total) * 100 if massa_total > 0 else 0

# Formata as colunas
tabela_destino["Massa (t)"] = tabela_destino["Massa (t)"].apply(formatar_numero_br)
tabela_destino["%"] = tabela_destino["%"].apply(lambda x: formatar_numero_br(x, 1))

st.dataframe(tabela_destino[["Código Rota", "Tipo de Coleta", "Tipo de Unidade (SNIS)", "Massa (t)", "%"]], use_container_width=True)
st.caption("""
📌 Os dados refletem fielmente os registros do SNIS. A coluna lista todos os tipos de unidade (intermediárias e finais). 
Possíveis duplicidades (ex.: transbordo + aterro) decorrem de como o gestor preencheu as rotas.
""")

# =========================================================
# 📊 Distribuição por tipo de destino (com checkbox e total DEDICADO)
# =========================================================
if municipio == municipios[0]:
    st.markdown("---")
    st.subheader(f"📊 Distribuição dos resíduos por tipo de destino ({ano_selecionado})")

    ocultar_transbordo_dist = st.checkbox("Ocultar transbordos", value=False, key="ocultar_transbordo_dist")

    df_dist = df_mun.copy()
    if ocultar_transbordo_dist:
        df_dist = df_dist[~df_dist[COL_DESTINO].apply(
            lambda x: "TRANSBORDO" in normalizar_texto(x) if pd.notna(x) else False
        )]

    massa_total_dist = df_dist["MASSA_FLOAT"].sum()
    st.markdown(f"### Total de resíduos coletados: **{formatar_numero_br(massa_total_dist)} t**")

    agg_destino = df_dist.groupby(COL_DESTINO)["MASSA_FLOAT"].sum().reset_index()
    agg_destino = agg_destino.sort_values("MASSA_FLOAT", ascending=False)
    agg_destino["Percentual (%)"] = (agg_destino["MASSA_FLOAT"] / massa_total_dist) * 100 if massa_total_dist > 0 else 0
    agg_destino["Massa (t)"] = agg_destino["MASSA_FLOAT"].apply(formatar_numero_br)
    agg_destino["Percentual (%)"] = agg_destino["Percentual (%)"].apply(lambda x: formatar_numero_br(x, 2))
    st.dataframe(
        agg_destino.rename(columns={COL_DESTINO: "Tipo de Unidade (SNIS)"})[["Tipo de Unidade (SNIS)", "Massa (t)", "Percentual (%)"]],
        use_container_width=True
    )
    st.caption("Nota: a soma das massas pode exceder o total coletado devido a duplicidades nas rotas (ex.: transbordo e destino final).")

    # =========================================================
    # 🏳️ Coleta de RSU pelos estados do Brasil (com checkbox próprio)
    # =========================================================
    st.markdown("---")
    st.subheader(f"🏳️ Coleta de RSU pelos estados do Brasil ({ano_selecionado})")

    ocultar_transbordo_est = st.checkbox("Ocultar transbordos", value=False, key="ocultar_transbordo_est")

    df_estados = df_mun.copy()
    if ocultar_transbordo_est:
        df_estados = df_estados[~df_estados[COL_DESTINO].apply(
            lambda x: "TRANSBORDO" in normalizar_texto(x) if pd.notna(x) else False
        )]

    massa_total_est = df_estados["MASSA_FLOAT"].sum()
    agg_estados = df_estados.groupby(COL_UF)["MASSA_FLOAT"].sum().reset_index()
    agg_estados = agg_estados.sort_values("MASSA_FLOAT", ascending=False)
    agg_estados["%"] = (agg_estados["MASSA_FLOAT"] / massa_total_est) * 100 if massa_total_est > 0 else 0
    agg_estados["% acumulado"] = agg_estados["%"].cumsum()

    agg_estados["Massa (t)"] = agg_estados["MASSA_FLOAT"].apply(formatar_numero_br)
    agg_estados["%"] = agg_estados["%"].apply(lambda x: formatar_numero_br(x, 2))
    agg_estados["% acumulado"] = agg_estados["% acumulado"].apply(lambda x: formatar_numero_br(x, 2))

    st.dataframe(
        agg_estados.rename(columns={COL_UF: "Estado"})[["Estado", "Massa (t)", "%", "% acumulado"]],
        use_container_width=True
    )

# ============================================================
# 🏆 RANKING MUNICIPAL (agora antes dos orgânicos, com métricas adicionais)
# ============================================================
if municipio == municipios[0]:
    st.markdown("---")
    st.header(f"🏆 Mapeamento de Coleta Seletiva de Orgânicos ({ano_selecionado})")
    st.markdown("""
    Lista de todos os municípios que declararam possuir **coleta seletiva de resíduos orgânicos**,
    com a massa coletada e a **receita potencial anual com créditos de carbono** (vermicompostagem).
    """)

    with st.spinner("Consultando dados..."):
        mask_organicos = df_clean[COL_TIPO_COLETA].astype(str).str.contains(
            "seletiva.*orgânico|orgânico.*seletiva", case=False, na=False, regex=True)
        df_org_ranking = df_clean[mask_organicos].copy()

        if df_org_ranking.empty:
            st.info("Nenhum município registrou coleta seletiva de resíduos orgânicos.")
        else:
            df_org_ranking["MASSA_FLOAT_RANK"] = pd.to_numeric(df_org_ranking[COL_MASSA], errors="coerce").fillna(0)

            # --- Métricas consolidadas ---
            num_municipios = df_org_ranking[COL_MUNICIPIO].nunique()
            total_massa_org = df_org_ranking["MASSA_FLOAT_RANK"].sum()
            massa_compostagem = df_org_ranking[df_org_ranking[COL_DESTINO].str.contains("COMPOSTAGEM", case=False, na=False)]["MASSA_FLOAT_RANK"].sum()
            massa_aterro = df_org_ranking[df_org_ranking[COL_DESTINO].str.contains("ATERRO", case=False, na=False)]["MASSA_FLOAT_RANK"].sum()

            if total_massa_org > 0:
                pct_comp = (massa_compostagem / total_massa_org) * 100
                pct_aterro = (massa_aterro / total_massa_org) * 100
            else:
                pct_comp = pct_aterro = 0.0

            col_m1, col_m2, col_m3 = st.columns(3)
            col_m1.metric("Municípios com coleta seletiva", num_municipios)
            col_m2.metric("Massa p/ Compostagem", f"{formatar_numero_br(pct_comp, 1)}%")
            col_m3.metric("Massa p/ Aterro", f"{formatar_numero_br(pct_aterro, 1)}%")

            ranking_data = df_org_ranking.groupby([COL_MUNICIPIO, COL_UF, COL_DESTINO])["MASSA_FLOAT_RANK"].sum().reset_index()

            mapeamento = []
            preco = st.session_state.preco_carbono
            cambio = st.session_state.taxa_cambio
            for (mun, uf), grupo in ranking_data.groupby([COL_MUNICIPIO, COL_UF]):
                massa_total = grupo["MASSA_FLOAT_RANK"].sum()
                destinos = ", ".join(sorted(grupo[COL_DESTINO].unique()))
                
                grupo["MCF"] = grupo[COL_DESTINO].apply(lambda x: determinar_mcf_por_destino(x, 'organico'))
                massa_aterro_local = grupo[grupo["MCF"] > 0]["MASSA_FLOAT_RANK"].sum()
                
                receita_anual = 0.0
                if massa_aterro_local > 0:
                    co2eq_aterro = calcular_co2eq_aterro_lote_20anos(massa_aterro_local, 0.8)
                    co2eq_vermi = calcular_co2eq_vermi_lote_20anos(massa_aterro_local)
                    evitado_20anos = co2eq_aterro - co2eq_vermi
                    receita_anual = (evitado_20anos / ANOS_PROJECAO) * preco * cambio

                mapeamento.append({
                    "Município": mun,
                    "UF": uf,
                    "Massa Total (t/ano)": massa_total,
                    "Massa para Aterro (t/ano)": massa_aterro_local,
                    "Tipo(s) de Unidade (SNIS)": destinos,
                    "Receita Potencial (R$/ano)": receita_anual
                })

            df_mapeamento = pd.DataFrame(mapeamento).sort_values("Massa Total (t/ano)", ascending=False)

            st.dataframe(df_mapeamento.style.format({
                "Massa Total (t/ano)": lambda x: formatar_numero_br(x, 1),
                "Massa para Aterro (t/ano)": lambda x: formatar_numero_br(x, 1),
                "Receita Potencial (R$/ano)": lambda x: f"R$ {formatar_numero_br(x, 2)}"
            }), use_container_width=True, height=600)

            st.caption("""
            - Cálculo baseado em **lote único** de resíduos (massa anual declarada).
            - Receita potencial anual considerando o preço atual do carbono (cenário otimista GWP-20).
            """)

# ============================================================
# ♻️ ORGÂNICOS (após o mapeamento, com nova tabela resumo e checkbox)
# ============================================================
st.markdown("---")
st.subheader(f"♻️ Destinação da Coleta Seletiva de Resíduos Orgânicos ({ano_selecionado})")
df_organicos = df_mun[df_mun[COL_TIPO_COLETA].astype(str).str.contains(
    "seletiva.*orgânico|orgânico.*seletiva", case=False, na=False, regex=True)].copy()

if not df_organicos.empty:
    df_organicos["MASSA_FLOAT"] = pd.to_numeric(df_organicos[COL_MASSA], errors="coerce").fillna(0)

    ocultar_transbordo_org = st.checkbox("Ocultar transbordos", value=False, key="ocultar_transbordo_org")
    if ocultar_transbordo_org:
        df_organicos = df_organicos[~df_organicos[COL_DESTINO].apply(
            lambda x: "TRANSBORDO" in normalizar_texto(x) if pd.notna(x) else False
        )]

    total_organicos = df_organicos["MASSA_FLOAT"].sum()
    massa_total_geral = df_mun["MASSA_FLOAT"].sum()

    st.markdown(f"### Total de orgânicos coletados seletivamente: **{formatar_numero_br(total_organicos)} t**")

    # --- NOVA TABELA RESUMO ---
    st.markdown("#### Tabela – Destino da coleta de recicláveis orgânicos")
    agg_org = df_organicos.groupby(COL_DESTINO)["MASSA_FLOAT"].sum().reset_index()
    agg_org = agg_org.sort_values("MASSA_FLOAT", ascending=False)
    agg_org["% do tipo"] = (agg_org["MASSA_FLOAT"] / total_organicos) * 100 if total_organicos > 0 else 0
    agg_org["% do total no ano"] = (agg_org["MASSA_FLOAT"] / massa_total_geral) * 100 if massa_total_geral > 0 else 0

    linhas = []
    for _, row in agg_org.iterrows():
        linhas.append({
            "Destino": row[COL_DESTINO],
            "Massa Anual (t)": formatar_numero_br(row["MASSA_FLOAT"], 2),
            "% do tipo": formatar_numero_br(row["% do tipo"], 2),
            "% do total no ano": formatar_numero_br(row["% do total no ano"], 4)
        })

    perc_total_tipo = (total_organicos / massa_total_geral) * 100 if massa_total_geral > 0 else 0
    linhas.append({
        "Destino": "Total do tipo",
        "Massa Anual (t)": formatar_numero_br(total_organicos, 2),
        "% do tipo": "100,00%",
        "% do total no ano": formatar_numero_br(perc_total_tipo, 4)
    })

    linhas.append({
        "Destino": "Total no ano",
        "Massa Anual (t)": formatar_numero_br(massa_total_geral, 2),
        "% do tipo": " - ",
        "% do total no ano": "100,00%"
    })

    df_resumo = pd.DataFrame(linhas)
    st.dataframe(df_resumo, use_container_width=True)

    # --- TABELA DETALHADA ---
    st.markdown("#### Detalhamento por destino")
    df_org_dest = df_organicos.groupby(COL_DESTINO)["MASSA_FLOAT"].sum().reset_index()
    df_org_dest["%"] = (df_org_dest["MASSA_FLOAT"] / total_organicos) * 100 if total_organicos > 0 else 0
    df_org_dest = df_org_dest.sort_values("%", ascending=False)
    df_org_dest_view = df_org_dest.copy()
    df_org_dest_view["Massa (t)"] = df_org_dest_view["MASSA_FLOAT"].apply(formatar_numero_br)
    df_org_dest_view["%"] = df_org_dest_view["%"].apply(lambda x: formatar_numero_br(x, 1))
    st.dataframe(
        df_org_dest_view.rename(columns={COL_DESTINO: "Tipo de Unidade (SNIS)"})[["Tipo de Unidade (SNIS)", "Massa (t)", "%"]],
        use_container_width=True
    )

    st.subheader("🔥 Emissões detalhadas (Orgânicos)")
    df_org_dest["MCF"] = df_org_dest[COL_DESTINO].apply(lambda x: determinar_mcf_por_destino(x, 'organico'))
    resultados = []
    co2eq_aterro_total = 0.0
    massa_aterro_total = 0.0
    for _, row in df_org_dest.iterrows():
        massa_t, mcf = row["MASSA_FLOAT"], row["MCF"]
        if mcf > 0 and massa_t > 0:
            co2eq_aterro = calcular_co2eq_aterro_lote_20anos(massa_t, mcf)
            co2eq_aterro_total += co2eq_aterro
            massa_aterro_total += massa_t
            resultados.append({
                "Tipo de Unidade (SNIS)": row[COL_DESTINO],
                "Massa (t)": formatar_numero_br(massa_t),
                "MCF": formatar_numero_br(mcf, 2),
                "CO₂e aterro (20 anos)": formatar_numero_br(co2eq_aterro, 1)
            })

    if resultados:
        st.dataframe(pd.DataFrame(resultados), use_container_width=True)

        co2eq_vermi = calcular_co2eq_vermi_lote_20anos(massa_aterro_total)
        evitado_vermi = co2eq_aterro_total - co2eq_vermi

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Massa em aterros", formatar_massa_br(massa_aterro_total))
        col2.metric("CO₂e aterro (20 anos)", f"{formatar_numero_br(co2eq_aterro_total, 1)} tCO₂e")
        col3.metric("CO₂e vermicompostagem (20 anos)", f"{formatar_numero_br(co2eq_vermi, 1)} tCO₂e")
        col4.metric("Emissões Evitadas", f"{formatar_numero_br(evitado_vermi, 1)} tCO₂e")

        # ============================================================
        # 💰 POTENCIAL DE CRÉDITOS DE CARBONO (COM COTAÇÕES ATUALIZÁVEIS)
        # ============================================================
        st.markdown("---")
        st.subheader("💰 Potencial de Créditos de Carbono (Vermicompostagem)")

        with st.container():
            st.markdown("### 🌍 Cotações de Mercado (Cenário Otimista GWP-20)")
            col_cot1, col_cot2, col_cot3 = st.columns(3)
            with col_cot1:
                if st.button("🔄 Atualizar Cotações"):
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

        valor_vermi_eur = calcular_valor_creditos(evitado_vermi, preco, "€")
        valor_vermi_brl = calcular_valor_creditos(evitado_vermi, preco, "R$", cambio)

        st.metric("Valor total em Reais (R$)", f"R$ {formatar_br(valor_vermi_brl)}")
        st.caption(f"Equivalente a {moeda} {formatar_br(valor_vermi_eur)}")

        st.info("ℹ️ **Nota sobre os arredondamentos:**\n\n"
                "Os cálculos financeiros utilizam os valores exatos das cotações (com todas as casas decimais fornecidas pela API). "
                "As quantidades exibidas na tela são arredondadas para duas casas decimais apenas para facilitar a leitura. "
                "Pequenas diferenças entre uma multiplicação manual com os números da tela e o resultado apresentado são normais e decorrem exclusivamente desse arredondamento visual.")

        with st.expander("ℹ️ Como interpretar"):
            st.markdown(f"""
            - **Emissões evitadas:** {formatar_numero_br(evitado_vermi, 1)} tCO₂e
            - **Preço do carbono:** {moeda} {formatar_br(preco)}/tCO₂e
            - **Câmbio:** R$ {formatar_br(cambio)}/€
            """)

    else:
        st.success("✅ Nenhum orgânico destinado a aterro.")
else:
    st.info("ℹ️ Sem registros de coleta seletiva de orgânicos.")

# =========================================================
# Rodapé
# =========================================================
st.markdown("---")
st.caption(f"""
Fonte: SNIS (ano {ano_selecionado}) | Metodologia: IPCC 2006, Wang et al. (2017), Yang et al. (2017), Feng et al. (2020) |
Baseline do aterro com CH₄ + N₂O; vermicompostagem: CH₄+N₂O (perfis diários) |
Cotações em tempo real via Yahoo Finance e APIs de câmbio. |
⚠️ Dados exibidos conforme SNIS, sem deduplicação. Transbordos podem ser ocultados com o checkbox.
""")
