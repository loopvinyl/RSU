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

# =========================================================
# Configuração da página
# =========================================================
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
    index=1  # Padrão 2024
)

# =========================================================
# URLs dos arquivos por ano
# =========================================================
URLS_POR_ANO = {
    "2023": "https://github.com/loopvinyl/tco2eqv7/raw/main/rsuBrasil_2023.xlsx",
    "2024": "https://github.com/loopvinyl/tco2eqv7/raw/main/rsuBrasil_2024.xlsx"
}

# =============================================================================
# FUNÇÕES DE COTAÇÃO AUTOMÁTICA DO CARBONO E CÂMBIO
# =============================================================================

def obter_cotacao_carbono_investing():
    try:
        url = "https://www.investing.com/commodities/carbon-emissions"
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept-Language': 'pt-BR,pt;q=0.9,en;q=0.8',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Referer': 'https://www.investing.com/'
        }
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        selectores = [
            '[data-test="instrument-price-last"]',
            '.text-2xl',
            '.last-price-value',
            '.instrument-price-last',
            '.pid-1062510-last',
            '.float_lang_base_1',
            '.top.bold.inlineblock',
            '#last_last'
        ]
        preco = None
        fonte = "Investing.com"
        for seletor in selectores:
            try:
                elemento = soup.select_one(seletor)
                if elemento:
                    texto_preco = elemento.text.strip().replace(',', '')
                    texto_preco = ''.join(c for c in texto_preco if c.isdigit() or c == '.')
                    if texto_preco:
                        preco = float(texto_preco)
                        break
            except (ValueError, AttributeError):
                continue
        if preco is not None:
            return preco, "€", "Carbon Emissions Future", True, fonte
        padroes_preco = [
            r'"last":"([\d,]+)"',
            r'data-last="([\d,]+)"',
            r'last_price["\']?:\s*["\']?([\d,]+)',
            r'value["\']?:\s*["\']?([\d,]+)'
        ]
        html_texto = str(soup)
        for padrao in padroes_preco:
            matches = re.findall(padrao, html_texto)
            for match in matches:
                try:
                    preco_texto = match.replace(',', '')
                    preco = float(preco_texto)
                    if 50 < preco < 200:
                        return preco, "€", "Carbon Emissions Future", True, fonte
                except ValueError:
                    continue
        return None, None, None, False, fonte
    except Exception as e:
        return None, None, None, False, f"Investing.com - Erro: {str(e)}"

def obter_cotacao_carbono():
    preco, moeda, contrato_info, sucesso, fonte = obter_cotacao_carbono_investing()
    if sucesso:
        return preco, moeda, f"{contrato_info}", True, fonte
    return 85.50, "€", "Carbon Emissions (Referência)", False, "Referência"

def obter_cotacao_euro_real():
    try:
        url = "https://economia.awesomeapi.com.br/last/EUR-BRL"
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            cotacao = float(data['EURBRL']['bid'])
            return cotacao, "R$", True, "AwesomeAPI"
    except:
        pass
    try:
        url = "https://api.exchangerate-api.com/v4/latest/EUR"
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            cotacao = data['rates']['BRL']
            return cotacao, "R$", True, "ExchangeRate-API"
    except:
        pass
    return 5.50, "R$", False, "Referência"

def calcular_valor_creditos(emissoes_evitadas_tco2eq, preco_carbono_por_tonelada, moeda, taxa_cambio=1):
    return emissoes_evitadas_tco2eq * preco_carbono_por_tonelada * taxa_cambio

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

def formatar_numero_br(valor, casas_decimais=2):
    if pd.isna(valor) or valor is None:
        return "Não informado"
    try:
        num = float(valor)
        formato = f"{{:,.{casas_decimais}f}}".format(num)
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
# PARÂMETROS E FUNÇÕES ORIGINAIS (COMPOSTAGEM / VERMI – APENAS CH4)
# =========================================================
GWP_CH4_20 = 79.7
GWP_N2O_20 = 273.0
ANOS_PROJECAO_CREDITOS = 20
DIAS_PROJECAO = ANOS_PROJECAO_CREDITOS * 365
UMIDADE_PADRAO = 0.85
PHI_BASELINE = 0.85
CAPTURA_CH4 = 0.0

# Pré‑descarte (Feng et al. 2020)
CH4_pre_ugC_per_kg_h = 2.78
CH4_PRE_KG_POR_KG_DIA = CH4_pre_ugC_per_kg_h * (16/12) * 24 / 1_000_000

N2O_pre_mgN_per_kg = 20.26
N2O_pre_mgN_per_kg_dia = N2O_pre_mgN_per_kg / 3
N2O_PRE_KG_POR_KG_DIA = N2O_pre_mgN_per_kg_dia * (44/28) / 1_000_000

PROFILE_N2O_PRE = {1: 0.8623, 2: 0.10, 3: 0.0377}
PROFILE_N2O_LANDFILL = {1: 0.10, 2: 0.30, 3: 0.40, 4: 0.15, 5: 0.05}

# Parâmetros específicos de cada tipo de resíduo
# Orgânicos
T_ORGANICO, DOC_ORGANICO, k_ano_ORGANICO = 25.0, 0.15, 0.06
TOC_YANG_ORGANICO, CH4_C_FRAC_THERMO_ORGANICO = 0.436, 0.006
CH4_C_FRAC_YANG_ORGANICO = 0.13 / 100
DIAS_COMPOSTAGEM_ORGANICO = 50

# Podas
T_PODAS, DOC_PODAS, k_ano_PODAS = 25.0, 0.10, 0.03
TOC_YANG_PODAS, CH4_C_FRAC_THERMO_PODAS = 0.50, 0.001
CH4_C_FRAC_YANG_PODAS = 0.02 / 100
DIAS_COMPOSTAGEM_PODAS = 90

# Perfis de emissão diários (compostagem e vermi)
def carregar_perfis():
    perfil_ch4_vermi_org = np.array([
        0.02, 0.02, 0.02, 0.03, 0.03, 0.04, 0.04, 0.05, 0.05, 0.06,
        0.07, 0.08, 0.09, 0.10, 0.09, 0.08, 0.07, 0.06, 0.05, 0.04,
        0.03, 0.02, 0.02, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01,
        0.005, 0.005, 0.005, 0.005, 0.005, 0.005, 0.005, 0.005, 0.005, 0.005,
        0.002, 0.002, 0.002, 0.002, 0.002, 0.001, 0.001, 0.001, 0.001, 0.001
    ])
    perfil_ch4_vermi_org /= perfil_ch4_vermi_org.sum()

    perfil_ch4_thermo_org = perfil_ch4_vermi_org.copy()

    perfil_ch4_vermi_podas = np.array([
        0.01, 0.01, 0.02, 0.02, 0.03, 0.04, 0.05, 0.06, 0.07, 0.08,
        0.09, 0.10, 0.11, 0.12, 0.12, 0.12, 0.11, 0.10, 0.09, 0.08,
        0.07, 0.06, 0.05, 0.04, 0.03, 0.03, 0.03, 0.03, 0.03, 0.03,
        0.03, 0.03, 0.03, 0.02, 0.02, 0.02, 0.02, 0.02, 0.02, 0.02,
        0.02, 0.02, 0.02, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01,
        0.01, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01,
        0.01, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01,
        0.01, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01,
        0.01, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01,
    ])
    perfil_ch4_vermi_podas /= perfil_ch4_vermi_podas.sum()

    perfil_ch4_thermo_podas = perfil_ch4_vermi_podas.copy()

    return perfil_ch4_vermi_org, perfil_ch4_thermo_org, perfil_ch4_vermi_podas, perfil_ch4_thermo_podas

perfil_ch4_vermi_org, perfil_ch4_thermo_org, perfil_ch4_vermi_podas, perfil_ch4_thermo_podas = carregar_perfis()

# Funções de cálculo de tratamento (somente CH4)
def calcular_emissoes_compostagem_entrada_continua(massa_kg_dia, dias_simulacao, tipo_residuo):
    if tipo_residuo == 'organico':
        TOC, fator, perfil = TOC_YANG_ORGANICO, CH4_C_FRAC_THERMO_ORGANICO, perfil_ch4_thermo_org
    else:
        TOC, fator, perfil = TOC_YANG_PODAS, CH4_C_FRAC_THERMO_PODAS, perfil_ch4_thermo_podas
    ch4_por_lote = massa_kg_dia * TOC * fator * (16/12)
    kernel = perfil * ch4_por_lote
    entradas = np.ones(dias_simulacao, dtype=float)
    return fftconvolve(entradas, kernel, mode='full')[:dias_simulacao]

def calcular_emissoes_vermicompostagem_entrada_continua(massa_kg_dia, dias_simulacao, tipo_residuo):
    if tipo_residuo == 'organico':
        TOC, fator, perfil = TOC_YANG_ORGANICO, CH4_C_FRAC_YANG_ORGANICO, perfil_ch4_vermi_org
    else:
        TOC, fator, perfil = TOC_YANG_PODAS, CH4_C_FRAC_YANG_PODAS, perfil_ch4_vermi_podas
    ch4_por_lote = massa_kg_dia * TOC * fator * (16/12)
    kernel = perfil * ch4_por_lote
    entradas = np.ones(dias_simulacao, dtype=float)
    return fftconvolve(entradas, kernel, mode='full')[:dias_simulacao]

def calcular_ch4_total_aterro_20anos(massa_t_ano, mcf, tipo_residuo):
    """ Mantida apenas para referência (usada em alguns locais na exibição do CH4). """
    if massa_t_ano <= 0 or mcf <= 0:
        return 0.0
    # Função original (simplificada) – vamos manter para exibir o CH4 separadamente
    doc = DOC_ORGANICO if tipo_residuo == 'organico' else DOC_PODAS
    docf = 0.0147 * (T_ORGANICO if tipo_residuo == 'organico' else T_PODAS) + 0.28
    ch4_pot = doc * docf * mcf * 0.5 * (16/12) * (1 - 0.1)
    massa_kg_dia = (massa_t_ano * 1000) / 365
    ch4_diario = massa_kg_dia * ch4_pot
    t = np.arange(1, DIAS_PROJECAO + 1, dtype=float)
    k = k_ano_ORGANICO if tipo_residuo == 'organico' else k_ano_PODAS
    kernel = np.exp(-k * (t - 1) / 365.0) - np.exp(-k * t / 365.0)
    emissoes = fftconvolve(np.ones(DIAS_PROJECAO, dtype=float) * ch4_diario, kernel, mode='full')[:DIAS_PROJECAO]
    return emissoes.sum() / 1000  # toneladas

# =========================================================
# NOVA FUNÇÃO DE CÁLCULO DO ATERRO (tco2eq – CH4 + N2O + φ)
# =========================================================
def calcular_emissoes_aterro_tco2eq(massa_kg_dia, mcf, k_ano, temp_C, doc, dias_simulacao=DIAS_PROJECAO):
    # CH4 (IPCC 2006)
    docf = 0.0147 * temp_C + 0.28
    ch4_pot = doc * docf * mcf * 0.5 * (16/12) * (1 - 0.1)  # F=0.5, OX=0.1, Ri=0
    ch4_diario_base = massa_kg_dia * ch4_pot
    t = np.arange(1, dias_simulacao + 1, dtype=float)
    kernel_ch4 = np.exp(-k_ano * (t - 1) / 365.0) - np.exp(-k_ano * t / 365.0)
    ch4_decaido = fftconvolve(np.ones(dias_simulacao, dtype=float) * ch4_diario_base, kernel_ch4, mode='full')[:dias_simulacao]
    ch4_decaido *= PHI_BASELINE * (1 - CAPTURA_CH4)

    # N2O (Wang et al. 2017)
    opening = np.clip((100.0 / massa_kg_dia) * (8.0 / 24), 0.0, 1.0)
    E_avg = opening * 1.91 + (1 - opening) * 2.15
    E_avg *= (1 - UMIDADE_PADRAO) / (1 - 0.55)
    n2o_diario_base = (E_avg * (44/28) / 1_000_000) * massa_kg_dia

    kernel_n2o = np.array([PROFILE_N2O_LANDFILL.get(d, 0) for d in range(1, 6)], dtype=float)
    n2o_decaido = fftconvolve(np.full(dias_simulacao, n2o_diario_base), kernel_n2o, mode='full')[:dias_simulacao]

    # Pré‑descarte
    ch4_pre = np.full(dias_simulacao, massa_kg_dia * CH4_PRE_KG_POR_KG_DIA)
    n2o_pre = np.zeros(dias_simulacao)
    for dia_entrada in range(dias_simulacao):
        for d_atraso, frac in PROFILE_N2O_PRE.items():
            dia_emissao = dia_entrada + d_atraso - 1
            if dia_emissao < dias_simulacao:
                n2o_pre[dia_emissao] += massa_kg_dia * N2O_PRE_KG_POR_KG_DIA * frac

    ch4_total = ch4_decaido + ch4_pre
    n2o_total = n2o_decaido + n2o_pre

    co2eq_dia = (ch4_total * GWP_CH4_20 + n2o_total * GWP_N2O_20) / 1000.0
    return ch4_total, n2o_total, co2eq_dia

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

# =========================================================
# Função para determinar MCF baseado no tipo de destino
# =========================================================
def determinar_mcf_por_destino(destino, tipo_residuo='organico'):
    if pd.isna(destino):
        return 0.0
    destino_norm = normalizar_texto(destino)
    if "ATERRO SANITARIO" in destino_norm:
        if "GERENCIADO" in destino_norm or "COLETA GAS" in destino_norm or "COLETA DE GAS" in destino_norm:
            mcf_base = 1.0
        else:
            mcf_base = 0.8
    elif "ATERRO CONTROLADO" in destino_norm:
        mcf_base = 0.4
    elif "LIXAO" in destino_norm or "VAZADOURO" in destino_norm or "DESCARGA DIRETA" in destino_norm:
        mcf_base = 0.4
    elif "COMPOSTAGEM" in destino_norm or "VERMICOMPOSTAGEM" in destino_norm:
        mcf_base = 0.0
    elif "RECICLAGEM" in destino_norm or "TRIAGEM" in destino_norm:
        mcf_base = 0.0
    elif "INCINERACAO" in destino_norm or "QUEIMA" in destino_norm:
        mcf_base = 0.0
    elif "OUTRO" in destino_norm or "NAO INFORMADO" in destino_norm or "NAO SE APLICA" in destino_norm:
        mcf_base = 0.0
    else:
        mcf_base = 0.0
    if tipo_residuo == 'podas' and mcf_base > 0:
        return mcf_base * 0.5
    return mcf_base

# =========================================================
# Carga do Excel
# =========================================================
@st.cache_data
def load_data(ano):
    url = URLS_POR_ANO[ano]
    df = pd.read_excel(
        url,
        sheet_name="Manejo_Coleta_e_Destinação",
        header=13
    )
    df = df.dropna(how="all")
    df.columns = [str(col).strip() for col in df.columns]
    return df

df = load_data(ano_selecionado)

# =========================================================
# Definição de colunas
# =========================================================
df = df.rename(columns={
    df.columns[2]: "MUNICÍPIO",
    df.columns[17]: "TIPO_COLETA_EXECUTADA",
    df.columns[24]: "MASSA_COLETADA"
})

COL_MUNICIPIO = "MUNICÍPIO"
COL_TIPO_COLETA = "TIPO_COLETA_EXECUTADA"
COL_MASSA = "MASSA_COLETADA"
COL_DESTINO = df.columns[28]  # Coluna AC

# =========================================================
# Classificação técnica (CORRIGIDA)
# =========================================================
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

# =========================================================
# Limpeza
# =========================================================
df_clean = df.dropna(subset=[COL_MUNICIPIO])
df_clean[COL_MUNICIPIO] = df_clean[COL_MUNICIPIO].astype(str).str.strip()

# =========================================================
# Interface
# =========================================================
municipios = ["BRASIL – Todos os municípios"] + sorted(df_clean[COL_MUNICIPIO].unique())
municipio = st.selectbox("Selecione o município:", municipios)

df_mun = df_clean.copy() if municipio == municipios[0] else df_clean[df_clean[COL_MUNICIPIO] == municipio]
st.subheader(f"🇧🇷 Brasil — Síntese Nacional de RSU ({ano_selecionado})" if municipio == municipios[0] else f"📍 {municipio} - Ano {ano_selecionado}")

# =========================================================
# 🗺️ DESTINAÇÃO FINAL
# =========================================================
st.markdown("---")
st.subheader("🗺️ Para onde o resíduo está indo? (Destinação Final)")

df_mun["MASSA_FLOAT"] = pd.to_numeric(df_mun[COL_MASSA], errors="coerce").fillna(0)

destinacao = df_mun.groupby(COL_DESTINO).agg(
    Massa_Total=("MASSA_FLOAT", "sum")
).reset_index()
destinacao = destinacao.sort_values("Massa_Total", ascending=False)

def ja_eh_tratamento(destino):
    d = str(destino).lower()
    return "compostagem" in d or "vermicompostagem" in d

destinacao["Ja_Biologico"] = destinacao[COL_DESTINO].apply(ja_eh_tratamento)

df_view = destinacao.copy()
df_view["Massa Total (t)"] = df_view["Massa_Total"].apply(formatar_numero_br)
df_view["Já é Tratamento Biológico?"] = df_view["Ja_Biologico"].apply(lambda x: "✅ Sim" if x else "❌ Não")

st.dataframe(
    df_view[[COL_DESTINO, "Massa Total (t)", "Já é Tratamento Biológico?"]],
    use_container_width=True
)

massa_biologica = destinacao.loc[destinacao["Ja_Biologico"], "Massa_Total"].sum()
st.caption(f"Total destinado a compostagem/vermicompostagem: **{formatar_numero_br(massa_biologica)} t**")

# ============================================================
# ♻️ DESTINAÇÃO DA COLETA SELETIVA DE RESÍDUOS ORGÂNICOS
# ============================================================
st.markdown("---")
st.subheader("♻️ Destinação da Coleta Seletiva de Resíduos Orgânicos")

df_organicos = df_mun[df_mun[COL_TIPO_COLETA].astype(str).str.contains(
    "seletiva.*orgânico|orgânico.*seletiva", 
    case=False, 
    na=False, 
    regex=True
)].copy()

if not df_organicos.empty:
    df_organicos["MASSA_FLOAT"] = pd.to_numeric(df_organicos[COL_MASSA], errors="coerce").fillna(0)
    total_organicos = df_organicos["MASSA_FLOAT"].sum()
    
    st.metric("Massa total de orgânicos coletados seletivamente", f"{formatar_numero_br(total_organicos)} t")
    
    df_organicos_destino = df_organicos.groupby(COL_DESTINO)["MASSA_FLOAT"].sum().reset_index()
    df_organicos_destino["Percentual (%)"] = df_organicos_destino["MASSA_FLOAT"] / total_organicos * 100
    df_organicos_destino = df_organicos_destino.sort_values("Percentual (%)", ascending=False)
    
    df_view_organicos = df_organicos_destino.copy()
    df_view_organicos["Massa (t)"] = df_view_organicos["MASSA_FLOAT"].apply(formatar_numero_br)
    df_view_organicos["Percentual (%)"] = df_view_organicos["Percentual (%)"].apply(lambda x: formatar_numero_br(x, 1))
    
    st.dataframe(df_view_organicos[[COL_DESTINO, "Massa (t)", "Percentual (%)"]], use_container_width=True)
    
    st.subheader("🔥 Cálculo Detalhado de Emissões (Orgânicos)")
    df_organicos_destino["MCF"] = df_organicos_destino[COL_DESTINO].apply(lambda x: determinar_mcf_por_destino(x, 'organico'))
    
    # Listas para armazenamento numérico antes da formatação
    resultados_emissoes = []
    massas_num = []
    mcfs_num = []
    co2eq_aterro_total = 0.0
    massa_total_aterro = 0.0
    
    for _, row in df_organicos_destino.iterrows():
        destino = row[COL_DESTINO]
        massa_t_ano = row["MASSA_FLOAT"]
        mcf = row["MCF"]
        if mcf > 0 and massa_t_ano > 0:
            co2eq_20 = calcular_co2eq_total_aterro_20anos(massa_t_ano, mcf, 'organico')
            ch4_20 = calcular_ch4_total_aterro_20anos(massa_t_ano, mcf, 'organico')
            co2eq_aterro_total += co2eq_20
            massa_total_aterro += massa_t_ano
            massas_num.append(massa_t_ano)
            mcfs_num.append(mcf)
            resultados_emissoes.append({
                "Destino": destino,
                "Massa anual (t)": formatar_numero_br(massa_t_ano),
                "MCF": formatar_numero_br(mcf, 2),
                "CO₂e gerado (t) - 20 anos": formatar_numero_br(co2eq_20, 1),
                "CH₄ gerado (t) - 20 anos": formatar_numero_br(ch4_20, 3),
                "Tipo de Aterro": classificar_tipo_aterro(mcf)
            })
    
    if resultados_emissoes:
        st.dataframe(pd.DataFrame(resultados_emissoes), use_container_width=True)
        
        st.subheader("📊 Comparação: Aterro vs Tratamento Biológico (Orgânicos)")
        massa_kg_dia = (massa_total_aterro * 1000) / 365
        
        ch4_comp_dia = calcular_emissoes_compostagem_entrada_continua(massa_kg_dia, DIAS_PROJECAO, 'organico')
        ch4_comp_t = ch4_comp_dia.sum() / 1000
        ch4_vermi_dia = calcular_emissoes_vermicompostagem_entrada_continua(massa_kg_dia, DIAS_PROJECAO, 'organico')
        ch4_vermi_t = ch4_vermi_dia.sum() / 1000
        
        co2eq_comp = ch4_comp_t * GWP_CH4_20
        co2eq_vermi = ch4_vermi_t * GWP_CH4_20
        
        evitado_comp = co2eq_aterro_total - co2eq_comp
        evitado_vermi = co2eq_aterro_total - co2eq_vermi
        
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Massa em aterros", f"{formatar_numero_br(massa_total_aterro)} t")
        with col2:
            st.metric("CO₂e do aterro (20 anos)", f"{formatar_numero_br(co2eq_aterro_total, 1)} tCO₂e",
                     help="CH₄ + N₂O + pré‑descarte, φ=0,85")
        with col3:
            st.metric("CO₂e evitado (Compostagem)", f"{formatar_numero_br(evitado_comp, 1)} tCO₂e")
        with col4:
            st.metric("CO₂e evitado (Vermi)", f"{formatar_numero_br(evitado_vermi, 1)} tCO₂e")
        
        st.info(f"""
        **🧮 Método de cálculo (aterro conforme script tco2eq):**
        - **Período:** {ANOS_PROJECAO_CREDITOS} anos, entrada contínua.
        - **k:** {k_ano_ORGANICO} ano⁻¹, DOC: {DOC_ORGANICO}, T: {T_ORGANICO}°C.
        - **φ = 0,85** (UNFCCC 2024), captura = 0%.
        - Inclui CH₄, N₂O (Wang et al. 2017) e pré‑descarte (Feng et al. 2020).
        - Tratamentos (compostagem/vermi) consideram apenas CH₄.
        """)
        
        # Gráfico de redução acumulada
        st.markdown("---")
        st.subheader("📉 Redução de Emissões Acumulada (Orgânicos)")
        
        # Cálculo do MCF médio ponderado (agora com valores numéricos)
        if massas_num:
            mcf_medio = np.average(mcfs_num, weights=massas_num)
        else:
            mcf_medio = 0.8  # fallback
        
        _, _, co2eq_aterro_dia = calcular_emissoes_aterro_tco2eq(
            massa_kg_dia, mcf_medio, k_ano_ORGANICO, T_ORGANICO, DOC_ORGANICO
        )
        co2eq_comp_dia = ch4_comp_dia * GWP_CH4_20 / 1000
        co2eq_vermi_dia = ch4_vermi_dia * GWP_CH4_20 / 1000
        
        datas = [datetime(2024, 1, 1) + timedelta(days=i) for i in range(DIAS_PROJECAO)]
        df_plot = pd.DataFrame({
            'Data': datas,
            'Aterro': co2eq_aterro_dia.cumsum(),
            'Compostagem': co2eq_comp_dia.cumsum(),
            'Vermicompostagem': co2eq_vermi_dia.cumsum()
        })
        
        fig, ax = plt.subplots(figsize=(12, 6))
        ax.plot(df_plot['Data'], df_plot['Aterro'], 'r-', label='Cenário Base (Aterro)', linewidth=2)
        ax.plot(df_plot['Data'], df_plot['Compostagem'], 'g-', label='Compostagem', linewidth=2)
        ax.plot(df_plot['Data'], df_plot['Vermicompostagem'], 'b--', label='Vermicompostagem', linewidth=2)
        ax.fill_between(df_plot['Data'], df_plot['Compostagem'], df_plot['Aterro'], color='lightgreen', alpha=0.3)
        ax.set_title('Redução de Emissões Acumulada - Orgânicos')
        ax.set_xlabel('Ano')
        ax.set_ylabel('tCO₂e Acumulado')
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y'))
        ax.xaxis.set_major_locator(mdates.YearLocator(2))
        plt.xticks(rotation=45)
        ax.yaxis.set_major_formatter(FuncFormatter(br_format))
        ax.grid(True, linestyle='--', alpha=0.7)
        ax.legend()
        plt.tight_layout()
        st.pyplot(fig)
        
    else:
        st.success("✅ Nenhum orgânico indo para aterro.")
else:
    st.info("ℹ️ Sem registros de coleta seletiva de orgânicos.")

# ============================================================
# 🌳 DESTINAÇÃO DAS PODAS E GALHADAS
# ============================================================
st.markdown("---")
st.subheader("🌳 Destinação das podas e galhadas de áreas verdes públicas")

df_podas = df_mun[df_mun[COL_TIPO_COLETA].astype(str).str.contains("áreas verdes públicas", case=False, na=False)].copy()

if not df_podas.empty:
    df_podas["MASSA_FLOAT"] = pd.to_numeric(df_podas[COL_MASSA], errors="coerce").fillna(0)
    total_podas = df_podas["MASSA_FLOAT"].sum()

    df_podas_destino = df_podas.groupby(COL_DESTINO)["MASSA_FLOAT"].sum().reset_index()
    df_podas_destino["Percentual (%)"] = df_podas_destino["MASSA_FLOAT"] / total_podas * 100
    df_podas_destino = df_podas_destino.sort_values("Percentual (%)", ascending=False)

    st.metric("Massa total de podas e galhadas", f"{formatar_numero_br(total_podas)} t")

    df_view = df_podas_destino.copy()
    df_view["Massa (t)"] = df_view["MASSA_FLOAT"].apply(formatar_numero_br)
    df_view["Percentual (%)"] = df_view["Percentual (%)"].apply(lambda x: formatar_numero_br(x, 1))
    st.dataframe(df_view[[COL_DESTINO, "Massa (t)", "Percentual (%)"]], use_container_width=True)

    st.subheader("🔥 Cálculo Detalhado de Emissões (Podas e Galhadas)")
    df_podas_destino["MCF"] = df_podas_destino[COL_DESTINO].apply(lambda x: determinar_mcf_por_destino(x, 'podas'))
    
    resultados_emissoes = []
    massas_num = []
    mcfs_num = []
    co2eq_aterro_total = 0.0
    massa_total_aterro = 0.0
    
    for _, row in df_podas_destino.iterrows():
        destino = row[COL_DESTINO]
        massa_t_ano = row["MASSA_FLOAT"]
        mcf = row["MCF"]
        if mcf > 0 and massa_t_ano > 0:
            co2eq_20 = calcular_co2eq_total_aterro_20anos(massa_t_ano, mcf, 'podas')
            ch4_20 = calcular_ch4_total_aterro_20anos(massa_t_ano, mcf, 'podas')
            co2eq_aterro_total += co2eq_20
            massa_total_aterro += massa_t_ano
            massas_num.append(massa_t_ano)
            mcfs_num.append(mcf)
            resultados_emissoes.append({
                "Destino": destino,
                "Massa anual (t)": formatar_numero_br(massa_t_ano),
                "MCF": formatar_numero_br(mcf, 2),
                "CO₂e gerado (t) - 20 anos": formatar_numero_br(co2eq_20, 1),
                "CH₄ gerado (t) - 20 anos": formatar_numero_br(ch4_20, 3),
                "Tipo de Aterro": classificar_tipo_aterro(mcf)
            })
    
    if resultados_emissoes:
        st.dataframe(pd.DataFrame(resultados_emissoes), use_container_width=True)
        
        st.subheader("📊 Comparação: Aterro vs Compostagem (Podas)")
        massa_kg_dia = (massa_total_aterro * 1000) / 365
        ch4_comp_dia = calcular_emissoes_compostagem_entrada_continua(massa_kg_dia, DIAS_PROJECAO, 'podas')
        ch4_comp_t = ch4_comp_dia.sum() / 1000
        co2eq_comp = ch4_comp_t * GWP_CH4_20
        evitado_comp = co2eq_aterro_total - co2eq_comp
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Massa em aterros", f"{formatar_numero_br(massa_total_aterro)} t")
        with col2:
            st.metric("CO₂e do aterro (20 anos)", f"{formatar_numero_br(co2eq_aterro_total, 1)} tCO₂e",
                     help="CH₄ + N₂O + pré‑descarte, φ=0,85")
        with col3:
            st.metric("CO₂e evitado (Compostagem)", f"{formatar_numero_br(evitado_comp, 1)} tCO₂e")
        
        st.info(f"""
        **🧮 Método (podas):** k = {k_ano_PODAS} ano⁻¹, DOC = {DOC_PODAS}. 
        Fatores de emissão reduzidos (CH₄). Baseline inclui N₂O.
        """)
        
        # Gráfico opcional para podas (pode ser adicionado similar ao de orgânicos)
    else:
        st.success("✅ Nenhuma poda indo para aterro.")
else:
    st.info("Não há dados de podas e galhadas.")

# =========================================================
# Rodapé
# =========================================================
st.markdown("---")
st.caption(f"""
Fonte: SNIS – Sistema Nacional de Informações sobre Saneamento (ano {ano_selecionado}) | 
Metodologia: IPCC 2006, Wang et al. (2017), Feng et al. (2020) – baseline de aterro conforme script tco2eq | 
Cotações atualizadas automaticamente via Investing.com e APIs de câmbio | 
Projeção de créditos de carbono: 20 anos com entrada contínua e decaimento acumulado | 
**⚠️ Baseline inclui CH₄ + N₂O; tratamentos ainda consideram apenas CH₄.**
""")
