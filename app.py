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
    """
    Obtém a cotação em tempo real do carbono via web scraping do Investing.com
    """
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
    valor_total = emissoes_evitadas_tco2eq * preco_carbono_por_tonelada * taxa_cambio
    return valor_total

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

# =============================================================================
# FUNÇÕES AUXILIARES ORIGINAIS
# =============================================================================

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
# PARÂMETROS PARA CÁLCULO COM DECAIMENTO - RESÍDUOS ORGÂNICOS
# =========================================================
T_ORGANICO = 25
DOC_ORGANICO = 0.15
MCF_ORGANICO = 1
F_ORGANICO = 0.5
OX_ORGANICO = 0.1
Ri_ORGANICO = 0.0
k_ano_ORGANICO = 0.06
GWP_CH4_20 = 79.7
ANOS_PROJECAO_CREDITOS = 20
DIAS_PROJECAO = ANOS_PROJECAO_CREDITOS * 365

# =========================================================
# PARÂMETROS PARA CÁLCULO COM DECAIMENTO - PODAS E GALHADAS
# =========================================================
T_PODAS = 25
DOC_PODAS = 0.10
MCF_PODAS = 0.5
F_PODAS = 0.3
OX_PODAS = 0.2
Ri_PODAS = 0.0
k_ano_PODAS = 0.03

# =========================================================
# FATORES DE EMISSÃO - RESÍDUOS ORGÂNICOS (Yang et al. 2017)
# =========================================================
TOC_YANG_ORGANICO = 0.436
TN_YANG_ORGANICO = 14.2 / 1000
CH4_C_FRAC_YANG_ORGANICO = 0.13 / 100
N2O_N_FRAC_YANG_ORGANICO = 0.92 / 100
CH4_C_FRAC_THERMO_ORGANICO = 0.006
N2O_N_FRAC_THERMO_ORGANICO = 0.0196
DIAS_COMPOSTAGEM_ORGANICO = 50

# =========================================================
# FATORES DE EMISSÃO - PODAS E GALHADAS (ajustados)
# =========================================================
TOC_YANG_PODAS = 0.50
TN_YANG_PODAS = 5.0 / 1000
CH4_C_FRAC_YANG_PODAS = 0.02 / 100
N2O_N_FRAC_YANG_PODAS = 0.10 / 100
CH4_C_FRAC_THERMO_PODAS = 0.001
N2O_N_FRAC_THERMO_PODAS = 0.005
DIAS_COMPOSTAGEM_PODAS = 90

# =========================================================
# FUNÇÕES DE CÁLCULO COM ENTRADA CONTÍNUA E DECAIMENTO ACUMULADO
# =========================================================

def calcular_emissoes_aterro_entrada_continua(massa_kg_dia, mcf, dias_simulacao=DIAS_PROJECAO, tipo_residuo='organico'):
    if tipo_residuo == 'organico':
        T, DOC, k_ano, F, OX, Ri = T_ORGANICO, DOC_ORGANICO, k_ano_ORGANICO, F_ORGANICO, OX_ORGANICO, Ri_ORGANICO
    else:
        T, DOC, k_ano, F, OX, Ri = T_PODAS, DOC_PODAS, k_ano_PODAS, F_PODAS, OX_PODAS, Ri_PODAS
    
    DOCf = 0.0147 * T + 0.28
    potencial_CH4_por_kg = DOC * DOCf * mcf * F * (16/12) * (1 - Ri) * (1 - OX)
    potencial_CH4_diario_kg = massa_kg_dia * potencial_CH4_por_kg
    
    t = np.arange(1, dias_simulacao + 1, dtype=float)
    kernel_ch4 = np.exp(-k_ano * (t - 1) / 365.0) - np.exp(-k_ano * t / 365.0)
    entradas_diarias = np.ones(dias_simulacao, dtype=float) * potencial_CH4_diario_kg
    emissoes_CH4 = fftconvolve(entradas_diarias, kernel_ch4, mode='full')[:dias_simulacao]
    return emissoes_CH4

def calcular_ch4_total_aterro_20anos(massa_t_ano, mcf, tipo_residuo='organico'):
    if massa_t_ano <= 0 or mcf <= 0:
        return 0.0
    massa_kg_dia = (massa_t_ano * 1000) / 365
    emissoes_ch4_aterro_dia = calcular_emissoes_aterro_entrada_continua(massa_kg_dia, mcf, DIAS_PROJECAO, tipo_residuo)
    total_ch4_aterro_kg = emissoes_ch4_aterro_dia.sum()
    return total_ch4_aterro_kg / 1000

def calcular_emissoes_compostagem_entrada_continua(massa_kg_dia, dias_simulacao=DIAS_PROJECAO, tipo_residuo='organico'):
    if tipo_residuo == 'organico':
        TOC_YANG, CH4_C_FRAC_THERMO, DIAS = TOC_YANG_ORGANICO, CH4_C_FRAC_THERMO_ORGANICO, DIAS_COMPOSTAGEM_ORGANICO
        PERFIL_CH4_THERMO = np.array([
            0.01, 0.02, 0.03, 0.05, 0.08,
            0.12, 0.15, 0.18, 0.20, 0.18,
            0.15, 0.12, 0.10, 0.08, 0.06,
            0.05, 0.04, 0.03, 0.02, 0.02,
            0.01, 0.01, 0.01, 0.01, 0.01,
            0.005, 0.005, 0.005, 0.005, 0.005,
            0.002, 0.002, 0.002, 0.002, 0.002,
            0.001, 0.001, 0.001, 0.001, 0.001,
            0.001, 0.001, 0.001, 0.001, 0.001,
            0.001, 0.001, 0.001, 0.001, 0.001
        ])
    else:
        TOC_YANG, CH4_C_FRAC_THERMO, DIAS = TOC_YANG_PODAS, CH4_C_FRAC_THERMO_PODAS, DIAS_COMPOSTAGEM_PODAS
        PERFIL_CH4_THERMO = np.array([
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
    
    PERFIL_CH4_THERMO /= PERFIL_CH4_THERMO.sum()
    fator_C_para_CH4 = 16/12
    ch4_por_lote_kg = massa_kg_dia * TOC_YANG * CH4_C_FRAC_THERMO * fator_C_para_CH4
    kernel_compost = PERFIL_CH4_THERMO * ch4_por_lote_kg
    entradas_diarias = np.ones(dias_simulacao, dtype=float)
    emissoes_CH4 = fftconvolve(entradas_diarias, kernel_compost, mode='full')[:dias_simulacao]
    return emissoes_CH4

def calcular_emissoes_vermicompostagem_entrada_continua(massa_kg_dia, dias_simulacao=DIAS_PROJECAO, tipo_residuo='organico'):
    if tipo_residuo == 'organico':
        TOC_YANG, CH4_C_FRAC_YANG, DIAS = TOC_YANG_ORGANICO, CH4_C_FRAC_YANG_ORGANICO, DIAS_COMPOSTAGEM_ORGANICO
        PERFIL_CH4_VERMI = np.array([
            0.02, 0.02, 0.02, 0.03, 0.03,
            0.04, 0.04, 0.05, 0.05, 0.06,
            0.07, 0.08, 0.09, 0.10, 0.09,
            0.08, 0.07, 0.06, 0.05, 0.04,
            0.03, 0.02, 0.02, 0.01, 0.01,
            0.01, 0.01, 0.01, 0.01, 0.01,
            0.005, 0.005, 0.005, 0.005, 0.005,
            0.005, 0.005, 0.005, 0.005, 0.005,
            0.002, 0.002, 0.002, 0.002, 0.002,
            0.001, 0.001, 0.001, 0.001, 0.001
        ])
    else:
        TOC_YANG, CH4_C_FRAC_YANG, DIAS = TOC_YANG_PODAS, CH4_C_FRAC_YANG_PODAS, DIAS_COMPOSTAGEM_PODAS
        PERFIL_CH4_VERMI = np.array([
            0.01, 0.01, 0.02, 0.02, 0.03, 0.04, 0.05, 0.06, 0.07, 0.08,
            0.09, 0.10, 0.11, 0.12, 0.12, 0.12, 0.11, 0.10, 0.09, 0.08,
            0.07, 0.06, 0.05, 0.04, 0.03, 0.03, 0.03, 0.03, 0.03, 0.03,
            0.03, 0.03, 0.03, 0.02, 0.02, 0.02, 0.02, 0.02, 0.02, 0.02,
            0.02, 0.02, 0.02, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01,
            0.01, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01,
            0.01, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01,
            0.01, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01,
            0.01, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01
        ])
    
    PERFIL_CH4_VERMI /= PERFIL_CH4_VERMI.sum()
    fator_C_para_CH4 = 16/12
    ch4_por_lote_kg = massa_kg_dia * TOC_YANG * CH4_C_FRAC_YANG * fator_C_para_CH4
    kernel_vermi = PERFIL_CH4_VERMI * ch4_por_lote_kg
    entradas_diarias = np.ones(dias_simulacao, dtype=float)
    emissoes_CH4 = fftconvolve(entradas_diarias, kernel_vermi, mode='full')[:dias_simulacao]
    return emissoes_CH4

def calcular_emissoes_totais_entrada_continua(massa_t_ano, mcf, tipo_residuo='organico'):
    if massa_t_ano <= 0 or mcf <= 0:
        return {
            'co2eq_aterro_total': 0, 'co2eq_evitado_compostagem': 0,
            'co2eq_evitado_vermicompostagem': 0,
            'co2eq_evitado_medio_anual_compostagem': 0,
            'co2eq_evitado_medio_anual_vermicompostagem': 0,
            'ch4_aterro_total': 0, 'massa_anual_considerada': 0,
            'massa_total_20_anos': 0
        }
    
    massa_kg_dia = (massa_t_ano * 1000) / 365
    emissoes_ch4_aterro_dia = calcular_emissoes_aterro_entrada_continua(massa_kg_dia, mcf, DIAS_PROJECAO, tipo_residuo)
    emissoes_ch4_compostagem_dia = calcular_emissoes_compostagem_entrada_continua(massa_kg_dia, DIAS_PROJECAO, tipo_residuo)
    emissoes_ch4_vermicompostagem_dia = calcular_emissoes_vermicompostagem_entrada_continua(massa_kg_dia, DIAS_PROJECAO, tipo_residuo)
    
    total_ch4_aterro_kg = emissoes_ch4_aterro_dia.sum()
    total_ch4_compostagem_kg = emissoes_ch4_compostagem_dia.sum()
    total_ch4_vermicompostagem_kg = emissoes_ch4_vermicompostagem_dia.sum()
    
    total_ch4_aterro_t = total_ch4_aterro_kg / 1000
    total_ch4_compostagem_t = total_ch4_compostagem_kg / 1000
    total_ch4_vermicompostagem_t = total_ch4_vermicompostagem_kg / 1000
    
    co2eq_aterro = total_ch4_aterro_t * GWP_CH4_20
    co2eq_compostagem = total_ch4_compostagem_t * GWP_CH4_20
    co2eq_vermicompostagem = total_ch4_vermicompostagem_t * GWP_CH4_20
    
    co2eq_evitado_compostagem = co2eq_aterro - co2eq_compostagem
    co2eq_evitado_vermicompostagem = co2eq_aterro - co2eq_vermicompostagem
    
    return {
        'co2eq_aterro_total': co2eq_aterro,
        'co2eq_evitado_compostagem': co2eq_evitado_compostagem,
        'co2eq_evitado_vermicompostagem': co2eq_evitado_vermicompostagem,
        'co2eq_evitado_medio_anual_compostagem': co2eq_evitado_compostagem / ANOS_PROJECAO_CREDITOS,
        'co2eq_evitado_medio_anual_vermicompostagem': co2eq_evitado_vermicompostagem / ANOS_PROJECAO_CREDITOS,
        'ch4_aterro_total': total_ch4_aterro_t,
        'massa_anual_considerada': massa_t_ano,
        'massa_total_20_anos': massa_t_ano * ANOS_PROJECAO_CREDITOS
    }

def calcular_emissoes_diarias_detalhadas(massa_t_ano, mcf, tipo_residuo='organico'):
    massa_kg_dia = (massa_t_ano * 1000) / 365
    emissoes_ch4_aterro_dia = calcular_emissoes_aterro_entrada_continua(massa_kg_dia, mcf, DIAS_PROJECAO, tipo_residuo)
    emissoes_ch4_compostagem_dia = calcular_emissoes_compostagem_entrada_continua(massa_kg_dia, DIAS_PROJECAO, tipo_residuo)
    emissoes_ch4_vermicompostagem_dia = calcular_emissoes_vermicompostagem_entrada_continua(massa_kg_dia, DIAS_PROJECAO, tipo_residuo)
    
    emissoes_aterro_tco2eq_dia = (emissoes_ch4_aterro_dia * GWP_CH4_20) / 1000
    emissoes_compostagem_tco2eq_dia = (emissoes_ch4_compostagem_dia * GWP_CH4_20) / 1000
    emissoes_vermicompostagem_tco2eq_dia = (emissoes_ch4_vermicompostagem_dia * GWP_CH4_20) / 1000
    
    data_inicio = datetime(2024, 1, 1)
    datas = [data_inicio + timedelta(days=i) for i in range(DIAS_PROJECAO)]
    
    df = pd.DataFrame({
        'Data': datas,
        'Emissoes_Aterro_tCO2eq_dia': emissoes_aterro_tco2eq_dia,
        'Emissoes_Compostagem_tCO2eq_dia': emissoes_compostagem_tco2eq_dia,
        'Emissoes_Vermicompostagem_tCO2eq_dia': emissoes_vermicompostagem_tco2eq_dia
    })
    
    df['Total_Aterro_tCO2eq_acum'] = df['Emissoes_Aterro_tCO2eq_dia'].cumsum()
    df['Total_Compostagem_tCO2eq_acum'] = df['Emissoes_Compostagem_tCO2eq_dia'].cumsum()
    df['Total_Vermicompostagem_tCO2eq_acum'] = df['Emissoes_Vermicompostagem_tCO2eq_dia'].cumsum()
    df['Reducao_Compostagem_tCO2eq_acum'] = df['Total_Aterro_tCO2eq_acum'] - df['Total_Compostagem_tCO2eq_acum']
    df['Reducao_Vermicompostagem_tCO2eq_acum'] = df['Total_Aterro_tCO2eq_acum'] - df['Total_Vermicompostagem_tCO2eq_acum']
    return df

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
# Classificação técnica
# =========================================================
def classificar_coleta(texto):
    if pd.isna(texto):
        return ("Não informado", False, False, "Tipo não informado")

    t = str(texto).lower()
    palavras = {
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
# Tabela principal (ALTERAÇÃO AQUI)
# =========================================================
resultados = []
total_massa = massa_compostagem = massa_vermi = 0

for _, row in df_mun.iterrows():
    categoria, comp, vermi, just = classificar_coleta(row[COL_TIPO_COLETA])
    massa = pd.to_numeric(row[COL_MASSA], errors="coerce") or 0
    total_massa += massa
    if comp:
        massa_compostagem += massa
    if vermi:
        massa_vermi += massa

    resultados.append({
        "Tipo de coleta": row[COL_TIPO_COLETA],
        "Massa": formatar_massa_br(massa),
        "Categoria": categoria,
        "Compostagem": "✅" if comp else "❌",
        "Tecnicamente apto para vermicompostagem": "✅" if vermi else "❌",
        "Justificativa": just
    })

st.dataframe(pd.DataFrame(resultados), use_container_width=True)

st.caption(
    "A coluna **'Tecnicamente apto para vermicompostagem'** é uma interpretação técnica "
    "baseada nas características do resíduo informado (ex.: orgânicos segregados, podas limpas). "
    "Ela indica o **potencial** para esse tipo de tratamento, não necessariamente que a "
    "vermicompostagem já é praticada pelo município."
)

# ============================================================
# ♻️ DESTINAÇÃO DA COLETA SELETIVA DE RESÍDUOS ORGÂNICOS
# ============================================================
st.markdown("---")
st.subheader("♻️ Destinação da Coleta Seletiva de Resíduos Orgânicos")

# Filtrar apenas os registros de coleta seletiva de orgânicos
df_organicos = df_mun[df_mun[COL_TIPO_COLETA].astype(str).str.contains(
    "seletiva.*orgânico|orgânico.*seletiva", 
    case=False, 
    na=False, 
    regex=True
)].copy()

if not df_organicos.empty:
    # Calcular massa total de orgânicos coletados seletivamente
    df_organicos["MASSA_FLOAT"] = pd.to_numeric(df_organicos[COL_MASSA], errors="coerce").fillna(0)
    total_organicos = df_organicos["MASSA_FLOAT"].sum()
    
    st.metric("Massa total de orgânicos coletados seletivamente", f"{formatar_numero_br(total_organicos)} t")
    
    # Agrupar por destino
    df_organicos_destino = df_organicos.groupby(COL_DESTINO)["MASSA_FLOAT"].sum().reset_index()
    df_organicos_destino["Percentual (%)"] = df_organicos_destino["MASSA_FLOAT"] / total_organicos * 100
    df_organicos_destino = df_organicos_destino.sort_values("Percentual (%)", ascending=False)
    
    # Formatar para exibição
    df_view_organicos = df_organicos_destino.copy()
    df_view_organicos["Massa (t)"] = df_view_organicos["MASSA_FLOAT"].apply(formatar_numero_br)
    df_view_organicos["Percentual (%)"] = df_view_organicos["Percentual (%)"].apply(lambda x: formatar_numero_br(x, 1))
    
    st.dataframe(df_view_organicos[[COL_DESTINO, "Massa (t)", "Percentual (%)"]], use_container_width=True)
    
    # =========================================================
    # 🔥 Cálculo detalhado de emissões por tipo de destino (orgânicos)
    # =========================================================
    st.subheader("🔥 Cálculo Detalhado de Emissões de CH₄ por Tipo de Destino (Orgânicos)")
    
    # Adicionar coluna de MCF à tabela
    df_organicos_destino["MCF"] = df_organicos_destino[COL_DESTINO].apply(lambda x: determinar_mcf_por_destino(x, 'organico'))
    
    # Lista para armazenar resultados detalhados
    resultados_emissoes_organicos = []
    ch4_total_aterro_20anos_organicos = 0  # AGORA COM DECAIMENTO
    massa_total_aterro_t_organicos = 0
    
    for _, row in df_organicos_destino.iterrows():
        destino = row[COL_DESTINO]
        massa_t_ano = row["MASSA_FLOAT"]  # Massa ANUAL do ano selecionado
        mcf = row["MCF"]
        
        # Só calcular emissões para destinos com MCF > 0 (aterros)
        if mcf > 0 and massa_t_ano > 0:
            # CÁLCULO COM DECAIMENTO (20 anos com entrada contínua) - MESMO MÉTODO DO SCRIPT TCO2E
            ch4_20anos = calcular_ch4_total_aterro_20anos(massa_t_ano, mcf, 'organico')
            
            ch4_total_aterro_20anos_organicos += ch4_20anos
            massa_total_aterro_t_organicos += massa_t_ano
            
            resultados_emissoes_organicos.append({
                "Destino": destino,
                "Massa anual (t)": formatar_numero_br(massa_t_ano),
                "MCF": formatar_numero_br(mcf, 2),
                "CH₄ Gerado (t) - 20 anos": formatar_numero_br(ch4_20anos, 3),
                "Tipo de Aterro": classificar_tipo_aterro(mcf)
            })
    
    # Se houver emissões de aterro, mostrar resultados
    if resultados_emissoes_organicos:
        st.dataframe(pd.DataFrame(resultados_emissoes_organicos), use_container_width=True)
        
        # =========================================================
        # 📊 Comparação com Cenário de Tratamento Biológico (orgânicos)
        # =========================================================
        st.subheader("📊 Comparação: Aterro vs Tratamento Biológico (Orgânicos)")
        
        # Calcular emissões do cenário de tratamento biológico (com entrada contínua)
        massa_kg_total_aterro_organicos = massa_total_aterro_t_organicos * 1000
        
        # Para compostagem: usar mesmo método de entrada contínua
        # Converter massa anual para diária
        massa_kg_dia_organicos = massa_kg_total_aterro_organicos / 365
        
        # Calcular emissões de CH4 da compostagem (20 anos com entrada contínua)
        emissoes_ch4_compostagem_dia = calcular_emissoes_compostagem_entrada_continua(massa_kg_dia_organicos, DIAS_PROJECAO, 'organico')
        ch4_comp_total_t_20anos_organicos = emissoes_ch4_compostagem_dia.sum() / 1000
        
        # Calcular emissões de CH4 da vermicompostagem (20 anos com entrada contínua)
        emissoes_ch4_vermicompostagem_dia = calcular_emissoes_vermicompostagem_entrada_continua(massa_kg_dia_organicos, DIAS_PROJECAO, 'organico')
        ch4_vermi_total_t_20anos_organicos = emissoes_ch4_vermicompostagem_dia.sum() / 1000
        
        # Emissões evitadas (20 anos)
        ch4_evitado_20anos_comp_organicos = ch4_total_aterro_20anos_organicos - ch4_comp_total_t_20anos_organicos
        ch4_evitado_20anos_vermi_organicos = ch4_total_aterro_20anos_organicos - ch4_vermi_total_t_20anos_organicos
        
        # Calcular CO₂ equivalente (20 anos) usando GWP de 20 anos - APENAS CH4
        co2eq_evitado_20anos_comp_organicos = ch4_evitado_20anos_comp_organicos * GWP_CH4_20
        co2eq_evitado_20anos_vermi_organicos = ch4_evitado_20anos_vermi_organicos * GWP_CH4_20
        
        # Médias anuais
        ch4_evitado_medio_anual_comp_organicos = ch4_evitado_20anos_comp_organicos / ANOS_PROJECAO_CREDITOS
        co2eq_evitado_medio_anual_comp_organicos = co2eq_evitado_20anos_comp_organicos / ANOS_PROJECAO_CREDITOS
        
        # Métricas comparativas ATUALIZADAS (com decaimento)
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric(
                "Massa em aterros",
                f"{formatar_numero_br(massa_total_aterro_t_organicos)} t",
                help=f"Total de orgânicos destinados a aterros em {ano_selecionado} (base para projeção)"
            )
        
        with col2:
            st.metric(
                "CH₄ do aterro (20 anos)",
                f"{formatar_numero_br(ch4_total_aterro_20anos_organicos, 1)} t",
                delta=None,
                help=f"CH₄ gerado em aterros em {ANOS_PROJECAO_CREDITOS} anos com decaimento (k={k_ano_ORGANICO} ano⁻¹)"
            )
        
        with col3:
            st.metric(
                "CH₄ evitado (Comp. 20 anos)",
                f"{formatar_numero_br(ch4_evitado_20anos_comp_organicos, 1)} t",
                delta=f"-{formatar_numero_br((ch4_evitado_20anos_comp_organicos/ch4_total_aterro_20anos_organicos)*100 if ch4_total_aterro_20anos_organicos > 0 else 0, 1)}%",
                delta_color="inverse",
                help=f"Redução de CH₄ em {ANOS_PROJECAO_CREDITOS} anos ao optar por compostagem"
            )
        
        with col4:
            st.metric(
                "CO₂e evitado (Comp. 20 anos)",
                f"{formatar_numero_br(co2eq_evitado_20anos_comp_organicos, 1)} t CO₂e",
                help=f"Equivalente em CO₂ (GWP20 = {GWP_CH4_20})"
            )
        
        # Nota explicativa sobre o método de cálculo
        st.info(f"""
        **🧮 Método de cálculo (igual ao script tco2e) - RESÍDUOS ORGÂNICOS:**
        - **Tipo de resíduo:** Resíduos orgânicos (alimentares, jardim)
        - **Período:** {ANOS_PROJECAO_CREDITOS} anos com entrada contínua
        - **Constante de decaimento (k):** {k_ano_ORGANICO} ano⁻¹
        - **Modelo:** Decomposição exponencial com convolução (IPCC 2006)
        - **Entrada anual constante:** {formatar_numero_br(massa_total_aterro_t_organicos)} t/ano (dados de {ano_selecionado})
        - **Massa total 20 anos:** {formatar_numero_br(massa_total_aterro_t_organicos * ANOS_PROJECAO_CREDITOS)} t
        - **Método matemático:** `fftconvolve(entradas_diarias, kernel_exponencial)`
        - **DOC:** {DOC_ORGANICO} (carbono orgânico degradável)
        - **TOC:** {TOC_YANG_ORGANICO} (carbono orgânico total)
        - **Fator de emissão CH₄ compostagem:** {CH4_C_FRAC_THERMO_ORGANICO}
        - **⚠️ APENAS CH₄:** Este cálculo considera somente emissões de metano (CH₄)
        """)
        
        # =============================================================================
        # 🎯 PROJEÇÃO PARA CRÉDITOS DE CARBONO (20 ANOS COM ENTRADA CONTÍNUA) - RESÍDUOS ORGÂNICOS
        # =============================================================================
        st.markdown("---")
        st.subheader("🎯 Projeção para Créditos de Carbono - Resíduos Orgânicos (20 anos com entrada contínua)")
        
        st.info(f"""
        **Metodologia avançada para resíduos orgânicos:** Este cálculo considera **entrada contínua de resíduos orgânicos** (mesma massa de {ano_selecionado} a cada ano)
        e o **decaimento acumulado das emissões no aterro ao longo de {ANOS_PROJECAO_CREDITOS} anos**,
        conforme modelo do IPCC 2006 e implementado no script original tco2e.
        
        - **Período:** {ANOS_PROJECAO_CREDITOS} anos (padrão para projetos de créditos de carbono)
        - **Entrada anual:** {formatar_numero_br(massa_total_aterro_t_organicos)} t/ano (mantendo massa de {ano_selecionado})
        - **Total massa em 20 anos:** {formatar_numero_br(massa_total_aterro_t_organicos * ANOS_PROJECAO_CREDITOS)} t
        - **Constante de decaimento (k):** {k_ano_ORGANICO} ano⁻¹
        - **GWP CH₄ (20 anos):** {GWP_CH4_20}
        - **Considera decomposição gradual** dos resíduos de todos os anos
        - **⚠️ APENAS CH₄:** Este cálculo considera somente emissões de metano (CH₄)
        """)
        
        # Calcular emissões COM ENTRADA CONTÍNUA para cada tipo de aterro (orgânicos)
        resultados_entrada_continua_organicos = []
        co2eq_total_aterro_20anos_organicos = 0
        co2eq_total_evitado_compostagem_20anos_organicos = 0
        co2eq_total_evitado_vermicompostagem_20anos_organicos = 0
        
        for _, row in df_organicos_destino.iterrows():
            destino = row[COL_DESTINO]
            massa_t_ano = row["MASSA_FLOAT"]  # Massa ANUAL do ano selecionado
            mcf = row["MCF"]
            
            if mcf > 0 and massa_t_ano > 0:
                # Calcular emissões com entrada contínua para 20 anos
                resultados = calcular_emissoes_totais_entrada_continua(massa_t_ano, mcf, 'organico')
                
                co2eq_total_aterro_20anos_organicos += resultados['co2eq_aterro_total']
                co2eq_total_evitado_compostagem_20anos_organicos += resultados['co2eq_evitado_compostagem']
                co2eq_total_evitado_vermicompostagem_20anos_organicos += resultados['co2eq_evitado_vermicompostagem']
                
                resultados_entrada_continua_organicos.append({
                    "Destino": destino,
                    "Massa anual (t)": formatar_numero_br(massa_t_ano),
                    "MCF": formatar_numero_br(mcf, 2),
                    "Linha de Base (tCO₂e)": formatar_numero_br(resultados['co2eq_aterro_total'], 1),
                    "Emissões Evitadas - Compostagem (tCO₂e)": formatar_numero_br(resultados['co2eq_evitado_compostagem'], 1),
                    "Emissões Evitadas - Vermicompostagem (tCO₂e)": formatar_numero_br(resultados['co2eq_evitado_vermicompostagem'], 1),
                    "Média anual evitada (tCO₂e/ano)": formatar_numero_br(resultados['co2eq_evitado_medio_anual_compostagem'], 1)
                })
        
        if resultados_entrada_continua_organicos:
            # Mostrar tabela de resultados com entrada contínua
            st.dataframe(pd.DataFrame(resultados_entrada_continua_organicos), use_container_width=True)
            
            # Calcular médias anuais (dividindo por 20)
            media_anual_evitado_compostagem_organicos = co2eq_total_evitado_compostagem_20anos_organicos / ANOS_PROJECAO_CREDITOS
            media_anual_evitado_vermicompostagem_organicos = co2eq_total_evitado_vermicompostagem_20anos_organicos / ANOS_PROJECAO_CREDITOS
            
            # Resumo geral para orgânicos
            st.markdown("#### 📊 Resumo Geral da Projeção - Resíduos Orgânicos (20 anos)")
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.metric(
                    "Massa total 20 anos",
                    f"{formatar_numero_br(massa_total_aterro_t_organicos * ANOS_PROJECAO_CREDITOS)} t",
                    help=f"{formatar_numero_br(massa_total_aterro_t_organicos)} t/ano × {ANOS_PROJECAO_CREDITOS} anos"
                )
            
            with col2:
                st.metric(
                    "Linha de Base total (tCO₂e)",
                    f"{formatar_numero_br(co2eq_total_aterro_20anos_organicos, 1)} tCO₂e",
                    help="Emissões acumuladas do aterro em 20 anos (APENAS CH₄)"
                )
            
            with col3:
                st.metric(
                    "Emissões Evitadas - Compostagem (tCO₂e)",
                    f"{formatar_numero_br(co2eq_total_evitado_compostagem_20anos_organicos, 1)} tCO₂e",
                    help="Emissões evitadas com compostagem em 20 anos (APENAS CH₄)"
                )
            
            # =============================================================================
            # 📈 GRÁFICO: REDUÇÃO DE EMISSÕES ACUMULADA - RESÍDUOS ORGÂNICOS (IGUAL AO SCRIPT TCO2E)
            # =============================================================================
            st.markdown("---")
            st.subheader("📉 Redução de Emissões Acumulada - Resíduos Orgânicos (20 anos)")
            
            # Calcular dados para o gráfico (somar todos os destinos)
            # Inicializar arrays de emissões diárias
            datas = []
            total_aterro_diario_organicos = np.zeros(DIAS_PROJECAO)
            total_compostagem_diario_organicos = np.zeros(DIAS_PROJECAO)
            total_vermicompostagem_diario_organicos = np.zeros(DIAS_PROJECAO)
            
            # Data inicial para o gráfico
            data_inicio = datetime(2024, 1, 1)
            
            # Para cada destino, calcular emissões diárias e somar
            for _, row in df_organicos_destino.iterrows():
                massa_t_ano = row["MASSA_FLOAT"]
                mcf = row["MCF"]
                
                if mcf > 0 and massa_t_ano > 0:
                    # Calcular emissões diárias detalhadas
                    df_detalhado = calcular_emissoes_diarias_detalhadas(massa_t_ano, mcf, 'organico')
                    
                    # Somar às totais
                    total_aterro_diario_organicos += df_detalhado['Emissoes_Aterro_tCO2eq_dia'].values
                    total_compostagem_diario_organicos += df_detalhado['Emissoes_Compostagem_tCO2eq_dia'].values
                    total_vermicompostagem_diario_organicos += df_detalhado['Emissoes_Vermicompostagem_tCO2eq_dia'].values
            
            # Criar DataFrame para o gráfico
            df_grafico_organicos = pd.DataFrame({
                'Data': [data_inicio + timedelta(days=i) for i in range(DIAS_PROJECAO)],
                'Total_Aterro_tCO2eq_dia': total_aterro_diario_organicos,
                'Total_Compostagem_tCO2eq_dia': total_compostagem_diario_organicos,
                'Total_Vermicompostagem_tCO2eq_dia': total_vermicompostagem_diario_organicos
            })
            
            # Calcular acumuladas
            df_grafico_organicos['Total_Aterro_tCO2eq_acum'] = df_grafico_organicos['Total_Aterro_tCO2eq_dia'].cumsum()
            df_grafico_organicos['Total_Compostagem_tCO2eq_acum'] = df_grafico_organicos['Total_Compostagem_tCO2eq_dia'].cumsum()
            df_grafico_organicos['Total_Vermicompostagem_tCO2eq_acum'] = df_grafico_organicos['Total_Vermicompostagem_tCO2eq_dia'].cumsum()
            
            # Criar gráfico
            fig, ax = plt.subplots(figsize=(12, 6))
            
            # Plotar linhas
            ax.plot(df_grafico_organicos['Data'], df_grafico_organicos['Total_Aterro_tCO2eq_acum'], 
                   'r-', label='Cenário Base (Aterro Sanitário)', linewidth=2)
            ax.plot(df_grafico_organicos['Data'], df_grafico_organicos['Total_Compostagem_tCO2eq_acum'], 
                   'g-', label='Projeto (Compostagem Termofílica)', linewidth=2)
            ax.plot(df_grafico_organicos['Data'], df_grafico_organicos['Total_Vermicompostagem_tCO2eq_acum'], 
                   'b-', label='Projeto (Vermicompostagem)', linewidth=2, linestyle='--')
            
            # Preencher área entre as linhas (emissões evitadas)
            ax.fill_between(df_grafico_organicos['Data'], 
                           df_grafico_organicos['Total_Compostagem_tCO2eq_acum'], 
                           df_grafico_organicos['Total_Aterro_tCO2eq_acum'],
                           color='lightgreen', alpha=0.3, label='Emissões Evitadas (Compostagem)')
            
            # Configurar eixos
            ax.set_title(f'Redução de Emissões Acumulada - Resíduos Orgânicos em {ANOS_PROJECAO_CREDITOS} Anos', fontsize=14, fontweight='bold')
            ax.set_xlabel('Ano', fontsize=12)
            ax.set_ylabel('tCO₂e Acumulado', fontsize=12)
            
            # Formatar eixo X para mostrar apenas anos
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y'))
            ax.xaxis.set_major_locator(mdates.YearLocator(2))  # Mostrar a cada 2 anos
            plt.xticks(rotation=45)
            
            # Formatar eixo Y no padrão brasileiro
            br_formatter = FuncFormatter(br_format)
            ax.yaxis.set_major_formatter(br_formatter)
            
            # Adicionar grid e legenda
            ax.grid(True, linestyle='--', alpha=0.7)
            ax.legend(loc='upper left', fontsize=10)
            
            # Ajustar layout
            plt.tight_layout()
            
            # Mostrar gráfico no Streamlit
            st.pyplot(fig)
            
            # Adicionar informações abaixo do gráfico
            st.markdown(f"""
            **📊 Interpretação do Gráfico - Resíduos Orgânicos:**
            - **Linha Vermelha:** Emissões acumuladas do cenário base (aterro sanitário) - **{formatar_numero_br(df_grafico_organicos['Total_Aterro_tCO2eq_acum'].iloc[-1], 1)} tCO₂e**
            - **Linha Verde:** Emissões acumuladas do projeto (compostagem) - **{formatar_numero_br(df_grafico_organicos['Total_Compostagem_tCO2eq_acum'].iloc[-1], 1)} tCO₂e**
            - **Linha Azul Tracejada:** Emissões acumuladas do projeto (vermicompostagem) - **{formatar_numero_br(df_grafico_organicos['Total_Vermicompostagem_tCO2eq_acum'].iloc[-1], 1)} tCO₂e**
            - **Área Verde:** Emissões evitadas pela compostagem - **{formatar_numero_br(co2eq_total_evitado_compostagem_20anos_organicos, 1)} tCO₂e**
            
            **💡 Observações para resíduos orgânicos:**
            1. Resíduos orgânicos coletados seletivamente têm **alto potencial** para compostagem/vermicompostagem
            2. Já estão **segregados na fonte**, reduzindo custos de triagem
            3. Podem ser tratados **localmente**, reduzindo custos de transporte
            4. A **área entre as curvas** representa os créditos de carbono gerados
            5. Curva do aterro mostra o **efeito do decaimento exponencial** (k = {k_ano_ORGANICO} ano⁻¹)
            6. **⚠️ APENAS CH₄:** Este gráfico considera somente emissões de metano (CH₄)
            """)
            
            # =============================================================================
            # SEÇÃO DE COTAÇÃO AUTOMÁTICA DO CARBONO - RESÍDUOS ORGÂNICOS
            # =============================================================================
            st.markdown("---")
            st.subheader("💰 Mercado de Carbono - Valor Financeiro das Emissões Evitadas (Resíduos Orgânicos)")
            
            # Obter cotações automaticamente
            with st.spinner("🔄 Obtendo cotações em tempo real..."):
                # Obter cotação do carbono
                preco_carbono, moeda_carbono, contrato_info, sucesso_carbono, fonte_carbono = obter_cotacao_carbono()
                
                # Obter cotação do Euro
                taxa_cambio, moeda_real, sucesso_euro, fonte_euro = obter_cotacao_euro_real()
            
            # Exibir cotações atuais
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.metric(
                    label=f"Preço do Carbono (tCO₂eq)",
                    value=f"{moeda_carbono} {formatar_br(preco_carbono)}",
                    help=f"Fonte: {fonte_carbono}"
                )
            
            with col2:
                st.metric(
                    label="Euro (EUR/BRL)",
                    value=f"{moeda_real} {formatar_br(taxa_cambio)}",
                    help=f"Fonte: {fonte_euro}"
                )
            
            with col3:
                preco_carbono_reais = preco_carbono * taxa_cambio
                st.metric(
                    label=f"Carbono em Reais (tCO₂eq)",
                    value=f"R$ {formatar_br(preco_carbono_reais)}",
                    help="Preço do carbono convertido para Reais Brasileiros"
                )
            
            # =============================================================================
            # VALOR FINANCEIRO DAS EMISSÕES EVITADAS - PROJEÇÃO 20 ANOS COM ENTRADA CONTÍNUA (ORGÂNICOS)
            # =============================================================================
            st.subheader("💵 Valor Financeiro do CO₂e Evitado - Resíduos Orgânicos (20 anos com entrada contínua)")
            
            # Calcular valores financeiros para 20 anos (TOTAL)
            valor_total_euros_20anos_comp_organicos = calcular_valor_creditos(
                co2eq_total_evitado_compostagem_20anos_organicos, preco_carbono, moeda_carbono
            )
            valor_total_reais_20anos_comp_organicos = calcular_valor_creditos(
                co2eq_total_evitado_compostagem_20anos_organicos, preco_carbono, "R$", taxa_cambio
            )
            
            valor_total_euros_20anos_vermi_organicos = calcular_valor_creditos(
                co2eq_total_evitado_vermicompostagem_20anos_organicos, preco_carbono, moeda_carbono
            )
            valor_total_reais_20anos_vermi_organicos = calcular_valor_creditos(
                co2eq_total_evitado_vermicompostagem_20anos_organicos, preco_carbono, "R$", taxa_cambio
            )
            
            # Calcular médias anuais (dividir por 20)
            valor_medio_anual_euros_comp_organicos = valor_total_euros_20anos_comp_organicos / ANOS_PROJECAO_CREDITOS
            valor_medio_anual_reais_comp_organicos = valor_total_reais_20anos_comp_organicos / ANOS_PROJECAO_CREDITOS
            
            valor_medio_anual_euros_vermi_organicos = valor_total_euros_20anos_vermi_organicos / ANOS_PROJECAO_CREDITOS
            valor_medio_anual_reais_vermi_organicos = valor_total_reais_20anos_vermi_organicos / ANOS_PROJECAO_CREDITOS
            
            # Exibir resultados da projeção - COMPOSTAGEM (ORGÂNICOS)
            st.markdown("#### 🍂 Compostagem - Valor dos Créditos de Carbono (Resíduos Orgânicos)")
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.metric(
                    "Emissões Evitadas (tCO₂e)",
                    f"{formatar_br(co2eq_total_evitado_compostagem_20anos_organicos)} tCO₂e",
                    help=f"Total em {ANOS_PROJECAO_CREDITOS} anos com entrada contínua (APENAS CH₄)"
                )
            
            with col2:
                st.metric(
                    "Média anual (tCO₂e/ano)",
                    f"{formatar_br(media_anual_evitado_compostagem_organicos)} tCO₂e/ano",
                    help="Média anual (total ÷ 20) - APENAS CH₄"
                )
            
            with col3:
                st.metric(
                    "Valor total (Euro)",
                    f"{moeda_carbono} {formatar_br(valor_total_euros_20anos_comp_organicos)}",
                    help=f"Valor acumulado em {ANOS_PROJECAO_CREDITOS} anos"
                )
            
            with col4:
                st.metric(
                    "Valor médio anual (Euro)",
                    f"{moeda_carbono} {formatar_br(valor_medio_anual_euros_comp_organicos)}/ano",
                    help="Média anual (total ÷ 20)"
                )
            
            # Linha 2: Compostagem em Reais (Orgânicos)
            col1, col2 = st.columns(2)
            
            with col1:
                st.metric(
                    "Valor total (R$)",
                    f"R$ {formatar_br(valor_total_reais_20anos_comp_organicos)}",
                    help=f"Valor acumulado em {ANOS_PROJECAO_CREDITOS} anos"
                )
            
            with col2:
                st.metric(
                    "Valor médio anual (R$)",
                    f"R$ {formatar_br(valor_medio_anual_reais_comp_organicos)}/ano",
                    help="Média anual (total ÷ 20)"
                )
            
            # Exibir resultados da projeção - VERMICOMPOSTAGEM (ORGÂNICOS)
            st.markdown("#### 🐛 Vermicompostagem - Valor dos Créditos de Carbono (Resíduos Orgânicos)")
            col1, col2, col3, col4 = st.columns(4)
            
            with col1:
                st.metric(
                    "Emissões Evitadas (tCO₂e)",
                    f"{formatar_br(co2eq_total_evitado_vermicompostagem_20anos_organicos)} tCO₂e",
                    help=f"Total em {ANOS_PROJECAO_CREDITOS} anos com entrada contínua (APENAS CH₄)"
                )
            
            with col2:
                st.metric(
                    "Média anual (tCO₂e/ano)",
                    f"{formatar_br(media_anual_evitado_vermicompostagem_organicos)} tCO₂e/ano",
                    help="Média anual (total ÷ 20) - APENAS CH₄"
                )
            
            with col3:
                st.metric(
                    "Valor total (Euro)",
                    f"{moeda_carbono} {formatar_br(valor_total_euros_20anos_vermi_organicos)}",
                    help=f"Valor acumulado em {ANOS_PROJECAO_CREDITOS} anos"
                )
            
            with col4:
                st.metric(
                    "Valor médio anual (Euro)",
                    f"{moeda_carbono} {formatar_br(valor_medio_anual_euros_vermi_organicos)}/ano",
                    help="Média anual (total ÷ 20)"
                )
            
            # Linha 4: Vermicompostagem em Reais (Orgânicos)
            col1, col2 = st.columns(2)
            
            with col1:
                st.metric(
                    "Valor total (R$)",
                    f"R$ {formatar_br(valor_total_reais_20anos_vermi_organicos)}",
                    help=f"Valor acumulado em {ANOS_PROJECAO_CREDITOS} anos"
                )
            
            with col2:
                st.metric(
                    "Valor médio anual (R$)",
                    f"R$ {formatar_br(valor_medio_anual_reais_vermi_organicos)}/ano",
                    help="Média anual (total ÷ 20)"
                )
            
            # Explicação sobre como calcular o valor
            with st.expander("🧮 Como é calculado o valor dos créditos de carbono para resíduos orgânicos?"):
                st.markdown(f"""
                **📊 Fórmula de Cálculo:**
