# =========================================================
# CONFIGURAÇÃO DA PÁGINA
# =========================================================
import streamlit as st
import pandas as pd
import numpy as np
import unicodedata
import requests
import os
from bs4 import BeautifulSoup
import re
from scipy.signal import fftconvolve
from datetime import datetime, timedelta
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.ticker import FuncFormatter
import yfinance as yf

# ========== IMPORTAÇÃO DA IA ==========
from utils.ia_classificacao import ClassificadorDestinoIA, classificar_destino_regra, normalizar_texto

# ========== CONFIGURAÇÃO DA PÁGINA ==========
st.set_page_config(
    page_title="Composta.IA - Potencial de Compostagem e Créditos de Carbono",
    layout="wide"
)

st.title("🌱 Composta.IA - Potencial de Compostagem e Créditos de Carbono (UNFCCC)")
st.markdown("""
Este aplicativo interpreta os **tipos de coleta executada** informados pelos municípios no SNIS
e avalia o **potencial técnico para compostagem** de resíduos sólidos urbanos,
utilizando **Inteligência Artificial** para padronizar os dados e a **metodologia UNFCCC A6.4-AMT-003** para o cálculo de emissões.

**Ferramenta de apoio à gestão pública** – desenvolvida para subsidiar o SINISA e políticas de resíduos sólidos.
""")

# =========================================================
# SELEÇÃO DE ANO
# =========================================================
ano_selecionado = st.selectbox(
    "Selecione o ano de referência:",
    ["2023", "2024"],
    index=1
)

# =========================================================
# CARREGAMENTO DOS PARQUETS (GERADOS PELO COLAB CORRIGIDO)
# =========================================================
@st.cache_data
def carregar_parquets():
    """Carrega os Parquets gerados pelo Colab (com IS_TRANSBORDO e dados agregados)."""
    try:
        residuos = pd.read_parquet("residuos_anuais.parquet")
        rotas = pd.read_parquet("rotas.parquet")
        # municipios não é usado diretamente, mas pode ser útil
        # municipios = pd.read_parquet("municipios.parquet")
        return residuos, rotas
    except FileNotFoundError:
        st.error("❌ Arquivos Parquet não encontrados. Certifique-se de que 'residuos_anuais.parquet' e 'rotas.parquet' estão no mesmo diretório do app.")
        st.stop()

residuos, rotas = carregar_parquets()

# =========================================================
# FUNÇÕES DE COTAÇÃO
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

# =========================================================
# FORMATAÇÕES
# =========================================================
def formatar_br(numero, auto_precision=True, casas_override=None):
    if pd.isna(numero) or numero is None:
        return "N/A"
    try:
        numero = float(numero)
        if casas_override is not None:
            decimais = casas_override
        elif auto_precision:
            decimais = 2 if abs(numero) >= 1 else 4
        else:
            decimais = 2
        numero_arredondado = round(numero, decimais)
        if decimais == 0:
            return f"{numero_arredondado:,.0f}".replace(",", "X").replace(".", ",").replace("X", ".")
        else:
            formato = f"{{:,.{decimais}f}}"
            return formato.format(numero_arredondado).replace(",", "X").replace(".", ",").replace("X", ".")
    except (ValueError, TypeError):
        return "N/A"

def formatar_numero_br(valor, decimais=None, auto_precision=True):
    if decimais is not None:
        return formatar_br(valor, auto_precision=False, casas_override=decimais)
    return formatar_br(valor, auto_precision=auto_precision, casas_override=None)

def br_format(x, pos):
    if x == 0:
        return "0"
    if abs(x) < 0.01:
        return f"{x:.1e}".replace(".", ",")
    if abs(x) >= 1000:
        return f"{x:,.0f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def formatar_massa_br(valor):
    if pd.isna(valor) or valor is None:
        return "Não informado"
    return f"{formatar_br(valor)} t"

def formatar_eixo_abreviado(x, pos):
    """Formata números grandes para exibir como Mi (milhões) ou Bi (bilhões)."""
    if x == 0:
        return "0"
    if abs(x) >= 1e9:
        return f"{x/1e9:.1f} Bi"
    if abs(x) >= 1e6:
        return f"{x/1e6:.1f} Mi"
    if abs(x) >= 1e3:
        return f"{x/1e3:.1f} k"
    return f"{x:.0f}"

# =========================================================
# PARÂMETROS UNFCCC A6.4-AMT-003-v01.0 (2025) – Application B (Tropical Wet)
# =========================================================
GWP_CH4 = 28.0
GWP_N2O = 265.0
PHI_APPLICATION_B = 0.85      # para clima úmido (Brasil majoritariamente)
OX_SOIL_COVER = 0.383
F_METHANE_FRACTION = 0.5
MCF_DEFAULT_BULK = 0.8

ANOS_PROJECAO = 20
DIAS_PROJECAO = ANOS_PROJECAO * 365
T_ORGANICO = 25.0
DOC_PADRAO = 0.15
K_PADRAO = 0.07

# =========================================================
# FUNÇÃO PARA CALCULAR DOC, DOC_f e k PONDERADOS (VIA SNIS)
# =========================================================
def calcular_doc_k_ponderado(df_municipio):
    """
    Calcula DOC médio, DOC_f (fração que realmente se decompõe) e k (decay rate)
    com base na caracterização dos resíduos (colunas GTR1501 a GTR1507).
    Segue as Tabelas 7 e 10 da UNFCCC A6.4-AMT-003 (Tropical Wet).
    """
    # Mapeamento para DOC (Tabela 9 do anexo - % wet waste)
    doc_map = {
        'GTR1501': 0.15,  # Alimentos e Verdes (15%)
        'GTR1502': 0.00,  # Vidros (inerte)
        'GTR1503': 0.00,  # Metais (inerte)
        'GTR1504': 0.00,  # Plásticos (inerte)
        'GTR1505': 0.40,  # Papéis (40%)
        'GTR1506': 0.24,  # Têxteis (24%)
        'GTR1507': 0.10   # Outros (madeira, etc. - 10%)
    }

    # Mapeamento para DOC_f (Tabela 7 - fração que se decompõe)
    docf_map = {
        'GTR1501': 0.7,   # Altamente decomponível (alimentos/verdes)
        'GTR1502': 0.0,   # Inerte
        'GTR1503': 0.0,   # Inerte
        'GTR1504': 0.0,   # Inerte
        'GTR1505': 0.5,   # Moderadamente decomponível (papéis)
        'GTR1506': 0.5,   # Moderadamente decomponível (têxteis)
        'GTR1507': 0.1    # Pouco decomponível (madeira, etc.)
    }

    # Mapeamento para k (Tabela 10 - Tropical Wet, MAP > 1000mm)
    k_map = {
        'GTR1501': 0.17,  # Outros orgânicos putrescíveis (jardim/poda) - conservador
        'GTR1502': 0.0,
        'GTR1503': 0.0,
        'GTR1504': 0.0,
        'GTR1505': 0.07,  # Papel, papelão (Tropical Wet)
        'GTR1506': 0.07,  # Têxteis (Tropical Wet)
        'GTR1507': 0.035  # Madeira, produtos de madeira (Tropical Wet)
    }

    # Seleciona as colunas disponíveis no DataFrame
    cols = [col for col in doc_map.keys() if col in df_municipio.columns]
    if not cols:
        # Fallback para valores padrão caso não haja caracterização
        return 0.15, 0.5, 0.07  # (DOC, DOC_f, k) - valores médios

    # Converte para numérico e preenche NAs com 0
    pct = pd.to_numeric(df_municipio[cols], errors='coerce').fillna(0)

    # Calcula as médias ponderadas (assumindo que as colunas são percentuais em %)
    # Soma dos percentuais para normalização (pode ser diferente de 100% devido a arredondamentos)
    total_pct = pct.sum().sum()  # soma de todas as frações
    if total_pct <= 0:
        return 0.15, 0.5, 0.07

    # DOC médio
    doc_pond = sum(pct[col].sum() * doc_map.get(col, 0) for col in cols) / total_pct

    # DOC_f médio
    docf_pond = sum(pct[col].sum() * docf_map.get(col, 0) for col in cols) / total_pct

    # k médio (ano^-1)
    k_pond = sum(pct[col].sum() * k_map.get(col, 0) for col in cols) / total_pct

    # Limites para evitar valores fora da faixa esperada
    doc_pond = max(0.01, min(0.5, doc_pond))
    docf_pond = max(0.05, min(0.9, docf_pond))
    k_pond = max(0.01, min(0.5, k_pond))

    return doc_pond, docf_pond, k_pond

# =========================================================
# FUNÇÃO DE CÁLCULO – ATERRO (BASELINE UNFCCC) - MODELO ANUAL (EQUAÇÃO 1)
# =========================================================
def calcular_co2eq_aterro_20anos(massa_t_ano, mcf, k_ano, doc_pond, docf_pond):
    """
    Calcula as emissões acumuladas em 20 anos (tCO2e) para uma massa anual de resíduos
    enviada a um aterro, utilizando o modelo FOD anual da UNFCCC (Equação 1 da A6.4-AMT-003).
    """
    if massa_t_ano <= 0 or mcf <= 0:
        return 0.0

    massa_kg = massa_t_ano * 1000
    
    # Potencial de geração de CH4 por kg de resíduo (constante do modelo)
    ch4_pot_por_kg = (doc_pond * docf_pond * mcf * F_METHANE_FRACTION * (16/12) *
                      (1 - OX_SOIL_COVER) * PHI_APPLICATION_B)
    
    # Fração total do resíduo que se decompõe ao longo de 20 anos (somatório da série)
    frac_decomposta_20_anos = 1 - np.exp(-k_ano * ANOS_PROJECAO)
    
    # Total de CH4 gerado em 20 anos (kg)
    ch4_total_kg = massa_kg * ch4_pot_por_kg * frac_decomposta_20_anos
    
    # Converte para tCO2e
    co2eq_total_t = (ch4_total_kg * GWP_CH4) / 1000.0
    return co2eq_total_t

# =========================================================
# FUNÇÃO DE CÁLCULO – COMPOSTAGEM (UNFCCC TOOL13 / AMS-III.F)
# =========================================================
def calcular_co2eq_compostagem_UNFCCC(massa_t_ano):
    if massa_t_ano <= 0:
        return 0.0
    massa_kg = massa_t_ano * 1000
    ch4_kg = massa_kg * 0.002
    n2o_kg = massa_kg * 0.0002
    co2eq_t = (ch4_kg * GWP_CH4 + n2o_kg * GWP_N2O) / 1000.0
    return co2eq_t

def determinar_mcf_por_destino(destino, tipo_residuo='organico'):
    if pd.isna(destino):
        return 0.0
    destino_norm = normalizar_texto(destino)
    if "ATERRO SANITARIO" in destino_norm:
        if "GERENCIADO" in destino_norm or "COLETA" in destino_norm or "BIOGÁS" in destino_norm:
            mcf_base = 1.0
        else:
            mcf_base = 0.8
    elif "ATERRO CONTROLADO" in destino_norm:
        mcf_base = 0.4
    elif "LIXAO" in destino_norm or "VAZADOURO" in destino_norm:
        mcf_base = 0.4
    else:
        mcf_base = 0.0
    return mcf_base

# =========================================================
# FUNÇÕES DE PROJEÇÃO PER CAPITA E SIMULAÇÃO
# =========================================================
def projetar_residuos_per_capita(populacao_atual, massa_anual_atual, 
                                 taxa_crescimento_pop=0.01, anos=10):
    if populacao_atual <= 0 or massa_anual_atual <= 0:
        raise ValueError("População e massa devem ser maiores que zero.")
    per_capita = massa_anual_atual / populacao_atual
    resultados = []
    pop = populacao_atual
    massa = massa_anual_atual
    for i in range(1, anos + 1):
        pop = pop * (1 + taxa_crescimento_pop)
        massa = pop * per_capita
        resultados.append({
            'Ano': datetime.now().year + i,
            'Populacao_Projetada': pop,
            'Massa_Projetada_ton': massa
        })
    return pd.DataFrame(resultados)

def plot_projecao_residuos(df_proj):
    fig, ax1 = plt.subplots(figsize=(10, 6))
    ax1.set_xlabel('Ano')
    ax1.set_ylabel('População (habitantes)', color='blue')
    ax1.plot(df_proj['Ano'], df_proj['Populacao_Projetada'], 'o-', color='blue', linewidth=2, label='População')
    ax1.tick_params(axis='y', labelcolor='blue')
    ax2 = ax1.twinx()
    ax2.set_ylabel('Massa de Resíduos (toneladas/ano)', color='green')
    ax2.plot(df_proj['Ano'], df_proj['Massa_Projetada_ton'], 's-', color='green', linewidth=2, label='Massa')
    ax2.tick_params(axis='y', labelcolor='green')
    for i, row in df_proj.iterrows():
        ax1.annotate(formatar_br(row['Populacao_Projetada'], auto_precision=False, casas_override=0), 
                    (row['Ano'], row['Populacao_Projetada']), 
                    textcoords="offset points", xytext=(0,10), ha='center', fontsize=8, color='blue')
        ax2.annotate(formatar_br(row['Massa_Projetada_ton'], auto_precision=False, casas_override=0), 
                    (row['Ano'], row['Massa_Projetada_ton']), 
                    textcoords="offset points", xytext=(0,-15), ha='center', fontsize=8, color='green')
    plt.title('Projeção de População e Geração de Resíduos', fontsize=14)
    fig.tight_layout()
    return fig

def simular_cenarios_compostagem(massa_aterro_ano, 
                                 co2_evitado_por_tonelada, 
                                 preco_carbono_atual, 
                                 taxa_cambio,
                                 anos_projecao=10, 
                                 taxa_crescimento_compostagem=0.10,
                                 inflacao_carbono=0.02):
    if massa_aterro_ano <= 0:
        raise ValueError("Massa de aterro deve ser maior que zero.")
    resultados = []
    massa_estatica = massa_aterro_ano
    for ano in range(1, anos_projecao + 1):
        fator_desvio = (1 + taxa_crescimento_compostagem) ** (ano - 1)
        massa_projetada = massa_aterro_ano * fator_desvio
        preco_atualizado = preco_carbono_atual * (1 + inflacao_carbono) ** (ano - 1)
        co2_evitado_estatico = massa_estatica * co2_evitado_por_tonelada
        co2_evitado_projetado = massa_projetada * co2_evitado_por_tonelada
        receita_estatico_brl = co2_evitado_estatico * preco_atualizado * taxa_cambio
        receita_projetado_brl = co2_evitado_projetado * preco_atualizado * taxa_cambio
        ganho_incremental = receita_projetado_brl - receita_estatico_brl
        resultados.append({
            'Ano': datetime.now().year + ano,
            'Massa_Desviada_Acumulada(t)': massa_projetada,
            'Receita_Anual_BRL': receita_projetado_brl,
            'Ganho_Adicional_BRL': ganho_incremental
        })
    df = pd.DataFrame(resultados)
    df['Receita_Acumulada_BRL'] = df['Receita_Anual_BRL'].cumsum()
    return df

def plot_simulacao_compostagem(df_sim):
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.plot(df_sim['Ano'], df_sim['Receita_Acumulada_BRL'], 'o-', color='green', linewidth=2, label='Receita Acumulada')
    ax.fill_between(df_sim['Ano'], 0, df_sim['Receita_Acumulada_BRL'], alpha=0.3, color='lightgreen')
    for i, row in df_sim.iterrows():
        ax.annotate(f"R$ {formatar_br(row['Receita_Acumulada_BRL'], auto_precision=False, casas_override=0)}", 
                    (row['Ano'], row['Receita_Acumulada_BRL']), 
                    textcoords="offset points", xytext=(0,10), ha='center', fontsize=8)
    ax.set_xlabel('Ano')
    ax.set_ylabel('Receita Acumulada (R$)')
    ax.set_title('Projeção de Ganhos com Créditos de Carbono (Compostagem)', fontsize=14)
    ax.grid(True, linestyle='--', alpha=0.5)
    ax.legend()
    return fig

# =========================================================
# CARREGAMENTO E PREPARAÇÃO DOS DADOS A PARTIR DOS PARQUETS
# =========================================================
@st.cache_data
def load_data(ano):
    """
    Carrega os dados dos Parquets, filtra pelo ano e faz o merge entre
    rotas e resíduos para obter a caracterização (GTR1501-GTR1507).
    """
    # Filtra pelo ano
    df_rotas = rotas[rotas['ANO'] == int(ano)].copy()
    df_residuos = residuos[residuos['ANO'] == int(ano)].copy()
    
    # Renomeia colunas para compatibilidade com o resto do script
    # (o script espera 'MUNICÍPIO', 'TIPO_COLETA_EXECUTADA', 'MASSA_COLETADA', 'UF', 'POPULACAO_TOTAL')
    df_rotas.rename(columns={
        'MUNICIPIO': 'MUNICÍPIO',
        'TIPO_COLETA': 'TIPO_COLETA_EXECUTADA',
        'MASSA_ROTA': 'MASSA_COLETADA',
        'UF': 'UF'
    }, inplace=True)
    
    # Mantém apenas as colunas relevantes das rotas
    cols_rotas = ['COD_IBGE', 'MUNICÍPIO', 'UF', 'TIPO_COLETA_EXECUTADA', 
                  'TIPO_DESTINO', 'MASSA_COLETADA', 'IS_SELETIVA', 'IS_TRANSBORDO']
    # Algumas podem não existir; seleciona as que existem
    cols_rotas_exist = [c for c in cols_rotas if c in df_rotas.columns]
    df_rotas = df_rotas[cols_rotas_exist]
    
    # Do DataFrame de resíduos, pega POP_TOTAL e as colunas de caracterização (GTR1501-GTR1507)
    cols_res = ['COD_IBGE', 'POP_TOTAL', 'MASSA_TOTAL_RSU', 'MASSA_SELETIVA']
    # Adiciona GTR1501 a GTR1507 se existirem
    for i in range(1, 8):
        col = f'GTR150{i}'
        if col in df_residuos.columns:
            cols_res.append(col)
    df_residuos = df_residuos[cols_res]
    
    # Merge
    df = pd.merge(df_rotas, df_residuos, on='COD_IBGE', how='left')
    
    # Renomeia POP_TOTAL para POPULACAO_TOTAL (o script espera esse nome)
    df.rename(columns={'POP_TOTAL': 'POPULACAO_TOTAL'}, inplace=True)
    
    # Remove linhas sem município
    df = df.dropna(subset=['MUNICÍPIO'])
    df['MUNICÍPIO'] = df['MUNICÍPIO'].astype(str).str.strip()
    
    return df

# Carrega os dados do ano selecionado
df = load_data(ano_selecionado)

# Definição das colunas utilizadas (mesmas do script original)
COL_CODIGO_ROTA = 'COD_IBGE'  # ou pode ser outra, mas usaremos COD_IBGE
COL_MUNICIPIO = 'MUNICÍPIO'
COL_TIPO_COLETA = 'TIPO_COLETA_EXECUTADA'
COL_MASSA = 'MASSA_COLETADA'
COL_DESTINO = 'TIPO_DESTINO'   # originalmente era a coluna de destino
COL_UF = 'UF'

# O script original também usa a coluna "destino_agrupado" gerada pela IA, que será criada adiante.
# Também usaremos IS_TRANSBORDO para o filtro.

# Lista de municípios (mantida)
municipios = ["BRASIL – Todos os municípios"] + sorted(df[COL_MUNICIPIO].unique())
municipio = st.selectbox("Selecione o município:", municipios)
df_mun = df.copy() if municipio == municipios[0] else df[df[COL_MUNICIPIO] == municipio]

# =========================================================
# INICIALIZAÇÃO DA IA (PLN)
# =========================================================
with st.spinner("🤖 Inicializando o modelo de Inteligência Artificial..."):
    classificador_ia = ClassificadorDestinoIA()
    try:
        classificador_ia.carregar_ou_treinar(df, col_texto=COL_DESTINO)
        st.success("✅ IA carregada com sucesso!")
    except Exception as e:
        st.warning(f"⚠️ Modelo não encontrado. Treinando com dados atuais... (pode levar alguns segundos)")
        classificador_ia.treinar_com_dados_snis(df, col_texto=COL_DESTINO)
        st.success("✅ IA treinada e salva com sucesso!")

# =========================================================
# CRIAÇÃO DAS ABAS (AGORA COM 3)
# =========================================================
tab_tradicional, tab_ia, tab_diagnostico = st.tabs([
    "📊 Análise Tradicional (SNIS)", 
    "🤖 Insights com Inteligência Artificial",
    "🔥 Diagnóstico de Emissões (Baseline)"
])

# ======================== ABA TRADICIONAL ========================
with tab_tradicional:
    st.subheader(f"🇧🇷 Brasil — Síntese Nacional de RSU ({ano_selecionado})" if municipio == municipios[0] else f"📍 {municipio} - Ano {ano_selecionado}")

    # ... (todo o código da aba tradicional permanece IDÊNTICO, exceto onde mencionamos o uso de IS_TRANSBORDO)
    # A única modificação será no checkbox "Ocultar transbordos" para usar a coluna IS_TRANSBORDO
    # e na parte de cálculo da taxa de coleta seletiva (se houver) para usar MASSA_SELETIVA.
    # Como o script original já usa os dados agregados para a maioria das coisas,
    # e a taxa de coleta seletiva não é explicitamente calculada, não há muito a alterar.
    # Porém, para garantir, onde houver filtro de transbordo, usaremos IS_TRANSBORDO.

    # Vou reescrever apenas as partes que usam "Ocultar transbordos" (há várias ocorrências).
    # Cada uma será substituída para usar IS_TRANSBORDO.

    # =========================================================
    # 1. 🗺️ Destinação Final
    # =========================================================
    st.markdown("---")
    st.subheader(f"🗺️ Para onde o resíduo está indo? (Destinação Final, {ano_selecionado})")

    ocultar_transbordo = st.checkbox("Ocultar transbordos", value=False)

    df_mun_dest = df_mun.copy()
    if ocultar_transbordo:
        # Usa a flag IS_TRANSBORDO (presente nos Parquets) em vez da normalização de texto
        if 'IS_TRANSBORDO' in df_mun_dest.columns:
            df_mun_dest = df_mun_dest[~df_mun_dest['IS_TRANSBORDO']]
        else:
            # Fallback para o método antigo (caso a flag não exista)
            df_mun_dest = df_mun_dest[~df_mun_dest[COL_DESTINO].apply(
                lambda x: "TRANSBORDO" in normalizar_texto(x) if pd.notna(x) else False
            )]

    df_mun_dest["MASSA_FLOAT"] = pd.to_numeric(df_mun_dest[COL_MASSA], errors="coerce").fillna(0)
    massa_total_geral = df_mun_dest["MASSA_FLOAT"].sum()

    st.markdown(f"### Total de resíduos coletados: **{formatar_br(massa_total_geral, auto_precision=False, casas_override=0)} t**")

    st.markdown("#### 📊 Distribuição dos principais destinos")
    df_mun_dest['destino_agrupado'] = df_mun_dest[COL_DESTINO].apply(
        lambda x: classificador_ia.prever(x, threshold=0.3) if pd.notna(x) else "Indefinido"
    )
    agg_grafico = df_mun_dest.groupby('destino_agrupado')['MASSA_FLOAT'].sum().reset_index()
    agg_grafico = agg_grafico.sort_values('MASSA_FLOAT', ascending=False).head(8)

    fig_dest, ax_dest = plt.subplots(figsize=(10, 8))
    cores = plt.cm.Set3(np.linspace(0, 1, len(agg_grafico)))
    wedges, texts, autotexts = ax_dest.pie(
        agg_grafico['MASSA_FLOAT'],
        labels=None,
        autopct=lambda p: f'{p:.1f}%' if p > 1 else '',
        startangle=90,
        colors=cores,
        textprops={'fontsize': 9},
        pctdistance=0.7,
    )
    ax_dest.legend(wedges, agg_grafico['destino_agrupado'],
                   title="Destino",
                   loc="center left",
                   bbox_to_anchor=(1, 0, 0.5, 1),
                   fontsize=9)
    ax_dest.axis('equal')
    plt.tight_layout()
    st.pyplot(fig_dest)
    plt.close(fig_dest)
    st.caption("📌 Classificação dos destinos feita pela IA (PLN) para padronizar as variações textuais do SNIS.")

    st.markdown("#### 📋 Detalhamento por rota de coleta")
    tabela_destino = df_mun_dest[[COL_CODIGO_ROTA, COL_TIPO_COLETA, COL_DESTINO, "MASSA_FLOAT"]].copy()
    tabela_destino = tabela_destino.rename(columns={
        COL_CODIGO_ROTA: "Código Rota",
        COL_TIPO_COLETA: "Tipo de Coleta",
        COL_DESTINO: "Tipo de Unidade (SNIS)",
        "MASSA_FLOAT": "Massa (t)"
    })
    tabela_destino["%"] = (tabela_destino["Massa (t)"] / massa_total_geral) * 100 if massa_total_geral > 0 else 0
    tabela_destino["Massa (t)"] = tabela_destino["Massa (t)"].apply(formatar_numero_br)
    tabela_destino["%"] = tabela_destino["%"].apply(lambda x: formatar_numero_br(x, 1))

    st.dataframe(
        tabela_destino[["Código Rota", "Tipo de Coleta", "Tipo de Unidade (SNIS)", "Massa (t)", "%"]],
        use_container_width=True
    )
    st.caption("📌 Os dados refletem fielmente os registros do SNIS. A classificação dos destinos é feita pela IA.")

    # =========================================================
    # 2. 📊 Distribuição por tipo de destino (Brasil)
    # =========================================================
    if municipio == municipios[0]:
        st.markdown("---")
        st.subheader(f"📊 Distribuição dos resíduos por tipo de destino ({ano_selecionado})")

        ocultar_transbordo_dist = st.checkbox("Ocultar transbordos", value=False, key="ocultar_transbordo_dist")

        df_dist = df_mun_dest.copy()
        if ocultar_transbordo_dist:
            if 'IS_TRANSBORDO' in df_dist.columns:
                df_dist = df_dist[~df_dist['IS_TRANSBORDO']]
            else:
                df_dist = df_dist[~df_dist[COL_DESTINO].apply(
                    lambda x: "TRANSBORDO" in normalizar_texto(x) if pd.notna(x) else False
                )]

        massa_total_dist = df_dist["MASSA_FLOAT"].sum()
        st.markdown(f"### Total de resíduos coletados: **{formatar_br(massa_total_dist, auto_precision=False, casas_override=0)} t**")

        agg_destino = df_dist.groupby(COL_DESTINO)["MASSA_FLOAT"].sum().reset_index()
        agg_destino = agg_destino.sort_values("MASSA_FLOAT", ascending=False)
        agg_destino["Percentual (%)"] = (agg_destino["MASSA_FLOAT"] / massa_total_dist) * 100 if massa_total_dist > 0 else 0
        agg_destino["Massa (t)"] = agg_destino["MASSA_FLOAT"].apply(formatar_numero_br)
        agg_destino["Percentual (%)"] = agg_destino["Percentual (%)"].apply(lambda x: formatar_numero_br(x, 2))

        st.dataframe(
            agg_destino.rename(columns={COL_DESTINO: "Tipo de Unidade (SNIS)"})[["Tipo de Unidade (SNIS)", "Massa (t)", "Percentual (%)"]],
            use_container_width=True
        )

        st.markdown("#### 📊 Principais destinos (gráfico)")
        top_destinos = agg_destino.head(10)
        fig, ax = plt.subplots(figsize=(10, 6))
        ax.barh(top_destinos[COL_DESTINO], top_destinos["MASSA_FLOAT"], color='steelblue')
        ax.set_xlabel('Massa (t)')
        ax.set_title('Top 10 destinos de resíduos')
        ax.xaxis.set_major_formatter(FuncFormatter(formatar_eixo_abreviado))
        plt.tight_layout()
        st.pyplot(fig)
        plt.close(fig)

        st.caption("Nota: a soma das massas pode exceder o total coletado devido a duplicidades nas rotas (ex.: transbordo e destino final).")

        # =========================================================
        # 3. 🏳️ Coleta de RSU pelos estados
        # =========================================================
        st.markdown("---")
        st.subheader(f"🏳️ Coleta de RSU pelos estados do Brasil ({ano_selecionado})")

        ocultar_transbordo_est = st.checkbox("Ocultar transbordos", value=False, key="ocultar_transbordo_est")

        df_estados = df_mun_dest.copy()
        if ocultar_transbordo_est:
            if 'IS_TRANSBORDO' in df_estados.columns:
                df_estados = df_estados[~df_estados['IS_TRANSBORDO']]
            else:
                df_estados = df_estados[~df_estados[COL_DESTINO].apply(
                    lambda x: "TRANSBORDO" in normalizar_texto(x) if pd.notna(x) else False
                )]

        massa_total_est = df_estados["MASSA_FLOAT"].sum()
        agg_estados = df_estados.groupby("UF")["MASSA_FLOAT"].sum().reset_index()
        agg_estados = agg_estados.sort_values("MASSA_FLOAT", ascending=False)
        agg_estados["%"] = (agg_estados["MASSA_FLOAT"] / massa_total_est) * 100 if massa_total_est > 0 else 0
        agg_estados["% acumulado"] = agg_estados["%"].cumsum()

        agg_estados["Massa (t)"] = agg_estados["MASSA_FLOAT"].apply(formatar_numero_br)
        agg_estados["%"] = agg_estados["%"].apply(lambda x: formatar_numero_br(x, 2))
        agg_estados["% acumulado"] = agg_estados["% acumulado"].apply(lambda x: formatar_numero_br(x, 2))

        col1, col2 = st.columns([2, 1])
        with col1:
            st.dataframe(
                agg_estados.rename(columns={"UF": "Estado"})[["Estado", "Massa (t)", "%", "% acumulado"]],
                use_container_width=True
            )
        with col2:
            fig, ax = plt.subplots(figsize=(6, 8))
            top_estados = agg_estados.head(10)
            ax.barh(top_estados["UF"], top_estados["MASSA_FLOAT"], color='forestgreen')
            ax.set_xlabel('Massa (t)')
            ax.set_title('Top 10 estados')
            ax.xaxis.set_major_formatter(FuncFormatter(formatar_eixo_abreviado))
            plt.tight_layout()
            st.pyplot(fig)
            plt.close(fig)

    # =========================================================
    # 4. 🏆 RANKING MUNICIPAL (continua idêntico, pois já usa dados agregados)
    # =========================================================
    if municipio == municipios[0]:
        st.markdown("---")
        st.header(f"🏆 Mapeamento de Coleta Seletiva de Orgânicos ({ano_selecionado})")
        st.markdown("""
        Lista de todos os municípios que declararam possuir **coleta seletiva de resíduos orgânicos**,
        com a massa coletada e a **receita potencial anual com créditos de carbono** (compostagem - UNFCCC).
        """)

        with st.spinner("Consultando dados..."):
            mask_organicos = df_clean[COL_TIPO_COLETA].astype(str).str.contains(
                "seletiva.*orgânico|orgânico.*seletiva", case=False, na=False, regex=True)
            df_org_ranking = df_clean[mask_organicos].copy()

            if df_org_ranking.empty:
                st.info("Nenhum município registrou coleta seletiva de resíduos orgânicos.")
            else:
                df_org_ranking["MASSA_FLOAT_RANK"] = pd.to_numeric(df_org_ranking[COL_MASSA], errors="coerce").fillna(0)

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
                col_m2.metric("Massa p/ Compostagem", f"{formatar_br(pct_comp, auto_precision=False, casas_override=1)}%")
                col_m3.metric("Massa p/ Aterro", f"{formatar_br(pct_aterro, auto_precision=False, casas_override=1)}%")

                ranking_data = df_org_ranking.groupby([COL_MUNICIPIO, "UF", COL_DESTINO])["MASSA_FLOAT_RANK"].sum().reset_index()

                mapeamento = []
                preco = st.session_state.preco_carbono
                cambio = st.session_state.taxa_cambio

                for (mun, uf), grupo in ranking_data.groupby([COL_MUNICIPIO, "UF"]):
                    massa_total_local = grupo["MASSA_FLOAT_RANK"].sum()
                    destinos = ", ".join(sorted(grupo[COL_DESTINO].unique()))
                    
                    grupo["MCF"] = grupo[COL_DESTINO].apply(lambda x: determinar_mcf_por_destino(x, 'organico'))
                    grupo_aterro = grupo[grupo["MCF"] > 0]
                    massa_aterro_local = grupo_aterro["MASSA_FLOAT_RANK"].sum()
                    
                    if massa_aterro_local > 0:
                        mcf_medio = (grupo_aterro["MASSA_FLOAT_RANK"] * grupo_aterro["MCF"]).sum() / massa_aterro_local
                    else:
                        mcf_medio = 0.8
                    
                    receita_anual = 0.0
                    if massa_aterro_local > 0:
                        df_mun_caract = df_clean[df_clean[COL_MUNICIPIO] == mun]
                        doc_pond, docf_pond, k_pond = calcular_doc_k_ponderado(df_mun_caract)
                        
                        co2eq_aterro = calcular_co2eq_aterro_20anos(massa_aterro_local, mcf_medio, k_pond, doc_pond, docf_pond)
                        co2eq_compostagem = calcular_co2eq_compostagem_UNFCCC(massa_aterro_local)
                        evitado_20anos = co2eq_aterro - co2eq_compostagem
                        receita_anual = (evitado_20anos / ANOS_PROJECAO) * preco * cambio

                    massa_total_municipio = df_clean[df_clean[COL_MUNICIPIO] == mun]['MASSA_COLETADA'].sum()
                    pct_org = (massa_total_local / massa_total_municipio) * 100 if massa_total_municipio > 0 else 0

                    mapeamento.append({
                        "Município": mun,
                        "UF": uf,
                        "Massa Total (t/ano)": massa_total_local,
                        "Massa para Aterro (t/ano)": massa_aterro_local,
                        "% da massa total": pct_org,
                        "Tipo(s) de Unidade (SNIS)": destinos,
                        "Receita Potencial (R$/ano)": receita_anual
                    })

                df_mapeamento = pd.DataFrame(mapeamento).sort_values("Massa Total (t/ano)", ascending=False)

                st.dataframe(
                    df_mapeamento.style.format({
                        "Massa Total (t/ano)": lambda x: formatar_numero_br(x, None),
                        "Massa para Aterro (t/ano)": lambda x: formatar_numero_br(x, None),
                        "% da massa total": lambda x: formatar_br(x, auto_precision=False, casas_override=2) + '%',
                        "Receita Potencial (R$/ano)": lambda x: f"R$ {formatar_numero_br(x, None)}"
                    }),
                    use_container_width=True,
                    height=600
                )

                st.caption("""
                - **Baseline (aterro)**: alinhado à UNFCCC A6.4-AMT-003 (Application B) – CH₄ apenas, φ=0.85, OX=0.383, GWP_CH4=28.
                - **Cenário de compostagem**: UNFCCC TOOL13 / AMS-III.F – CH₄=0.002, N₂O=0.0002, GWP_CH4=28, GWP_N2O=265.
                - **DOC e k**: calculados dinamicamente a partir da caracterização dos resíduos do SNIS (quando disponível).
                - **MCF**: ponderado pelos diferentes destinos (aterro sanitário, controlado, lixão) de acordo com a Tabela 8 do anexo.
                - **% da massa total**: percentual da massa total de RSU do município que é composta por orgânicos da coleta seletiva.
                - Receita potencial anual considerando o preço atual do carbono.
                """)

    # =========================================================
    # 5. ♻️ ORGÂNICOS
    # =========================================================
    st.markdown("---")
    st.subheader(f"♻️ Destinação da Coleta Seletiva de Resíduos Orgânicos ({ano_selecionado})")
    df_organicos = df_mun_dest[df_mun_dest[COL_TIPO_COLETA].astype(str).str.contains(
        "seletiva.*orgânico|orgânico.*seletiva", case=False, na=False, regex=True)].copy()

    if not df_organicos.empty:
        df_organicos["MASSA_FLOAT"] = pd.to_numeric(df_organicos[COL_MASSA], errors="coerce").fillna(0)

        ocultar_transbordo_org = st.checkbox("Ocultar transbordos", value=False, key="ocultar_transbordo_org")

        df_mun_org = df_mun_dest.copy()
        if ocultar_transbordo_org:
            if 'IS_TRANSBORDO' in df_organicos.columns:
                df_organicos = df_organicos[~df_organicos['IS_TRANSBORDO']]
                df_mun_org = df_mun_org[~df_mun_org['IS_TRANSBORDO']]
            else:
                df_organicos = df_organicos[~df_organicos[COL_DESTINO].apply(
                    lambda x: "TRANSBORDO" in normalizar_texto(x) if pd.notna(x) else False
                )]
                df_mun_org = df_mun_org[~df_mun_org[COL_DESTINO].apply(
                    lambda x: "TRANSBORDO" in normalizar_texto(x) if pd.notna(x) else False
                )]

        total_organicos = df_organicos["MASSA_FLOAT"].sum()
        massa_total_geral_org = df_mun_org["MASSA_FLOAT"].sum()

        st.markdown(f"### Total de orgânicos coletados seletivamente: **{formatar_br(total_organicos, auto_precision=False, casas_override=2)} t**")

        st.markdown("#### 📊 Composição da destinação dos orgânicos")
        agg_org_pie = df_organicos.groupby(COL_DESTINO)["MASSA_FLOAT"].sum().reset_index()
        agg_org_pie = agg_org_pie.sort_values("MASSA_FLOAT", ascending=False)
        fig_pie, ax_pie = plt.subplots(figsize=(10, 8))
        cores_pie = plt.cm.Set3(np.linspace(0, 1, len(agg_org_pie)))
        wedges, texts, autotexts = ax_pie.pie(
            agg_org_pie["MASSA_FLOAT"],
            labels=None,
            autopct=lambda p: f'{p:.1f}%' if p > 1 else '',
            startangle=90,
            colors=cores_pie,
            textprops={'fontsize': 9},
            pctdistance=0.7,
        )
        ax_pie.legend(wedges, agg_org_pie[COL_DESTINO],
                      title="Destino",
                      loc="center left",
                      bbox_to_anchor=(1, 0, 0.5, 1),
                      fontsize=9)
        ax_pie.axis('equal')
        plt.tight_layout()
        st.pyplot(fig_pie)
        plt.close(fig_pie)

        st.markdown("#### 📋 Tabela – Destino da coleta de recicláveis orgânicos")
        agg_org = df_organicos.groupby(COL_DESTINO)["MASSA_FLOAT"].sum().reset_index()
        agg_org = agg_org.sort_values("MASSA_FLOAT", ascending=False)
        agg_org["% do tipo"] = (agg_org["MASSA_FLOAT"] / total_organicos) * 100 if total_organicos > 0 else 0
        agg_org["% do total no ano"] = (agg_org["MASSA_FLOAT"] / massa_total_geral_org) * 100 if massa_total_geral_org > 0 else 0

        linhas = []
        for _, row in agg_org.iterrows():
            linhas.append({
                "Destino": row[COL_DESTINO],
                "Massa Anual (t)": formatar_numero_br(row["MASSA_FLOAT"], 2),
                "% do tipo": formatar_numero_br(row["% do tipo"], 2),
                "% do total no ano": formatar_numero_br(row["% do total no ano"], 4)
            })

        perc_total_tipo = (total_organicos / massa_total_geral_org) * 100 if massa_total_geral_org > 0 else 0
        linhas.append({
            "Destino": "Total do tipo",
            "Massa Anual (t)": formatar_numero_br(total_organicos, 2),
            "% do tipo": "100,00%",
            "% do total no ano": formatar_numero_br(perc_total_tipo, 4)
        })

        linhas.append({
            "Destino": "Total no ano",
            "Massa Anual (t)": formatar_numero_br(massa_total_geral_org, 2),
            "% do tipo": " - ",
            "% do total no ano": "100,00%"
        })

        df_resumo = pd.DataFrame(linhas)
        st.dataframe(df_resumo, use_container_width=True)

    else:
        st.info("ℹ️ Sem registros de coleta seletiva de orgânicos.")

    # =========================================================
    # 6. 🌳 PODAS E GALHADAS
    # =========================================================
    st.markdown("---")
    st.subheader(f"🌳 Destinação da coleta de podas e galhadas ({ano_selecionado})")
    df_podas = df_mun_dest[df_mun_dest[COL_TIPO_COLETA].astype(str).str.contains("áreas verdes públicas", case=False, na=False)].copy()

    if not df_podas.empty:
        df_podas["MASSA_FLOAT"] = pd.to_numeric(df_podas[COL_MASSA], errors="coerce").fillna(0)

        ocultar_transbordo_podas = st.checkbox("Ocultar transbordos", value=False, key="ocultar_transbordo_podas")

        df_mun_podas = df_mun_dest.copy()
        if ocultar_transbordo_podas:
            if 'IS_TRANSBORDO' in df_podas.columns:
                df_podas = df_podas[~df_podas['IS_TRANSBORDO']]
                df_mun_podas = df_mun_podas[~df_mun_podas['IS_TRANSBORDO']]
            else:
                df_podas = df_podas[~df_podas[COL_DESTINO].apply(
                    lambda x: "TRANSBORDO" in normalizar_texto(x) if pd.notna(x) else False
                )]
                df_mun_podas = df_mun_podas[~df_mun_podas[COL_DESTINO].apply(
                    lambda x: "TRANSBORDO" in normalizar_texto(x) if pd.notna(x) else False
                )]

        total_podas = df_podas["MASSA_FLOAT"].sum()
        massa_total_geral_podas = df_mun_podas["MASSA_FLOAT"].sum()

        st.markdown(f"### Total de podas e galhadas coletadas: **{formatar_br(total_podas, auto_precision=False, casas_override=2)} t**")

        col1, col2 = st.columns(2)
        with col1:
            st.metric("Participação no total", f"{formatar_br((total_podas/massa_total_geral_podas)*100 if massa_total_geral_podas>0 else 0, auto_precision=False, casas_override=2)}%")
        with col2:
            destino_principal = df_podas.groupby(COL_DESTINO)["MASSA_FLOAT"].sum().idxmax() if not df_podas.empty else "N/A"
            st.metric("Destino principal", destino_principal)

        st.markdown("#### 📋 Tabela – Destino da coleta de podas e galhadas")
        agg_podas = df_podas.groupby(COL_DESTINO)["MASSA_FLOAT"].sum().reset_index()
        agg_podas = agg_podas.sort_values("MASSA_FLOAT", ascending=False)
        agg_podas["% do tipo"] = (agg_podas["MASSA_FLOAT"] / total_podas) * 100 if total_podas > 0 else 0
        agg_podas["% do total no ano"] = (agg_podas["MASSA_FLOAT"] / massa_total_geral_podas) * 100 if massa_total_geral_podas > 0 else 0

        linhas_podas = []
        for _, row in agg_podas.iterrows():
            linhas_podas.append({
                "Destino": row[COL_DESTINO],
                "Massa Anual (t)": formatar_numero_br(row["MASSA_FLOAT"], 2),
                "% do tipo": formatar_numero_br(row["% do tipo"], 2),
                "% do total no ano": formatar_numero_br(row["% do total no ano"], 4)
            })

        perc_total_tipo_podas = (total_podas / massa_total_geral_podas) * 100 if massa_total_geral_podas > 0 else 0
        linhas_podas.append({
            "Destino": "Total do tipo",
            "Massa Anual (t)": formatar_numero_br(total_podas, 2),
            "% do tipo": "100,00%",
            "% do total no ano": formatar_numero_br(perc_total_tipo_podas, 4)
        })

        linhas_podas.append({
            "Destino": "Total no ano",
            "Massa Anual (t)": formatar_numero_br(massa_total_geral_podas, 2),
            "% do tipo": " - ",
            "% do total no ano": "100,00%"
        })

        df_resumo_podas = pd.DataFrame(linhas_podas)
        st.dataframe(df_resumo_podas, use_container_width=True)

    else:
        st.info("ℹ️ Sem registros de coleta de podas e galhadas.")

    # =========================================================
    # Rodapé da aba tradicional
    # =========================================================
    st.markdown("---")
    st.caption(f"""
    Fonte: SNIS (ano {ano_selecionado}) | **Metodologia: UNFCCC A6.4-AMT-003 (2025) + TOOL13 (AMS-III.F)** | IPCC AR5 (GWP-100)
    Baseline (aterro): CH₄ apenas, φ=0.85, OX=0.383, GWP_CH4=28 | Compostagem: CH₄=0.002, N₂O=0.0002, GWP_CH4=28, GWP_N2O=265
    DOC/k: ponderados pela caracterização dos resíduos do SNIS (quando disponível) | Cotações em tempo real via Yahoo Finance e APIs de câmbio.
    Dados processados a partir dos Parquets gerados pelo Colab (com IS_TRANSBORDO e agregados oficiais).
    """)

# ======================== ABA DE IA ========================
# (Esta aba permanece exatamente igual, pois não depende da fonte dos dados,
#  apenas do DataFrame 'df' que já foi preparado com as colunas necessárias)
# ============================================================
# ... (todo o código da aba IA é IDÊNTICO ao original, pois as funções e colunas
#      são as mesmas, apenas a origem dos dados mudou) ...
# ============================================================
# Para não repetir todo o código, mantenha a aba IA exatamente como no script original,
# pois ela já está desenhada para trabalhar com o DataFrame 'df' que contém as colunas
# esperadas (MUNICÍPIO, UF, etc.). A única adaptação foi na carga dos dados.

# ======================== ABA DIAGNÓSTICO ========================
# (Também permanece idêntica, pois usa o DataFrame 'df' e as funções de cálculo)
# ============================================================
# ... (mantenha o código da aba diagnóstico exatamente como estava) ...

# =========================================================
# AUTORIA E USO
# =========================================================
st.markdown("---")
st.subheader("📬 Autoria e uso")

st.markdown("""
Este aplicativo foi desenvolvido para apoiar a gestão de resíduos sólidos, 
mapear oportunidades de compostagem e auxiliar municípios a se prepararem para o mercado de créditos de carbono.

**Potencial de uso:**  
- Mapeamento de municípios com coleta seletiva de orgânicos.  
- Estimativa de emissões evitadas com compostagem.  
- Projeção de receitas com créditos de carbono (metodologia UNFCCC).  
- Identificação de prioridades para expansão da coleta seletiva.
""")

# =========================================================
# RODAPÉ GERAL DO APP
# =========================================================
st.markdown("---")
st.caption("""
**Composta.IA** | Ferramenta de apoio à gestão de resíduos sólidos e créditos de carbono  
Dados: SNIS (2023/2024) processados via Parquet | Metodologia: UNFCCC A6.4-AMT-003 (2025) + TOOL13 (AMS-III.F) | IPCC AR5 (GWP-100)
""")
