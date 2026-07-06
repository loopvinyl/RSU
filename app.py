import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import os
import requests

# =========================================================
# CONFIGURAÇÃO DA PÁGINA
# =========================================================
st.set_page_config(
    page_title="📊 SNIS Resíduos - Análise Interativa",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("📊 Análise Interativa do SNIS - Resíduos Sólidos Urbanos")
st.markdown("""
Explore os dados dos anos **2023 e 2024** do SNIS (Módulo Manejo de Resíduos Sólidos).  
Utilize os filtros e gráficos interativos para entender a situação dos resíduos no Brasil.
""")

# =========================================================
# CARREGAMENTO DOS ARQUIVOS (LOCAL)
# =========================================================
ARQUIVO_2023 = "rsuBrasil_2023.xlsx"
ARQUIVO_2024 = "rsuBrasil_2024.xlsx"

def verificar_arquivos():
    if not os.path.exists(ARQUIVO_2023):
        st.error(f"❌ Arquivo {ARQUIVO_2023} não encontrado. Coloque-o no mesmo diretório do app.")
        return False
    if not os.path.exists(ARQUIVO_2024):
        st.error(f"❌ Arquivo {ARQUIVO_2024} não encontrado. Coloque-o no mesmo diretório do app.")
        return False
    return True

if not verificar_arquivos():
    st.stop()

st.sidebar.success("✅ Arquivos encontrados!")

# =========================================================
# FUNÇÃO INTELIGENTE PARA LER ABAS (CORRIGIDA)
# =========================================================
def ler_aba(caminho, nome_aba):
    """
    Lê uma aba do Excel, identificando com precisão a linha de cabeçalho.
    """
    try:
        df_raw = pd.read_excel(caminho, sheet_name=nome_aba, header=None)
        header_idx = None
        # Procurar linha que contém "CÓDIGO DO IBGE" E ("MUNICÍPIO" ou "MUNICIPIO")
        for i, row in df_raw.iterrows():
            row_str = row.astype(str).str.upper()
            if row_str.str.contains("CÓDIGO DO IBGE", na=False).any() and \
               (row_str.str.contains("MUNICÍPIO", na=False).any() or row_str.str.contains("MUNICIPIO", na=False).any()):
                header_idx = i
                break
        if header_idx is None:
            # Fallback: procurar por "MUNICÍPIO" sozinho
            for i, row in df_raw.iterrows():
                if row.astype(str).str.contains("MUNICÍPIO", case=False, na=False).any():
                    header_idx = i
                    break
        if header_idx is not None:
            df = pd.read_excel(caminho, sheet_name=nome_aba, header=header_idx)
        else:
            df = pd.read_excel(caminho, sheet_name=nome_aba, header=0)
        # Remover linhas completamente vazias
        df = df.dropna(how="all")
        # Remover colunas com todos os valores nulos
        df = df.dropna(axis=1, how="all")
        return df
    except Exception as e:
        st.error(f"Erro ao ler a aba '{nome_aba}' do arquivo {caminho}: {e}")
        return None

# =========================================================
# CARREGAR DADOS COM CACHE
# =========================================================
@st.cache_data
def carregar_dados(ano):
    caminho = ARQUIVO_2023 if ano == 2023 else ARQUIVO_2024
    df_res = ler_aba(caminho, "Manejo_Resíduos_Sólidos_Urbanos")
    df_col = ler_aba(caminho, "Manejo_Coleta_e_Destinação")
    return df_res, df_col

df_res_2023, df_col_2023 = carregar_dados(2023)
df_res_2024, df_col_2024 = carregar_dados(2024)

if df_res_2023 is None or df_res_2024 is None:
    st.error("❌ Não foi possível carregar os dados. Verifique os arquivos.")
    st.stop()

# =========================================================
# PRÉ-PROCESSAMENTO (PADRONIZAÇÃO DE COLUNAS)
# =========================================================
def padronizar_colunas(df):
    if df is None:
        return df
    col_map = {}
    for col in df.columns:
        col_str = str(col).strip()
        if "CÓDIGO DO IBGE" in col_str:
            col_map[col] = "COD_IBGE"
        elif "MUNICÍPIO" in col_str:
            col_map[col] = "MUNICIPIO"
        elif "UF" in col_str and col_str != "UF":
            col_map[col] = "UF"
        elif "MACRORREGIÃO" in col_str:
            col_map[col] = "MACRO"
        elif "POPULAÇÃO TOTAL" in col_str:
            col_map[col] = "POP_TOTAL"
        elif "POPULAÇÃO URBANA" in col_str:
            col_map[col] = "POP_URBANA"
        elif "POPULAÇÃO RURAL" in col_str:
            col_map[col] = "POP_RURAL"
        elif "Massa total anual proveniente das rotas de coleta de resíduos sólidos domiciliares" in col_str:
            col_map[col] = "MASSA_DOMICILIAR"
        elif "Massa total anual proveniente das rotas de coleta seletiva" in col_str:
            col_map[col] = "MASSA_SELETIVA"
        elif "Massa total anual proveniente das rotas de coleta de resíduos sólidos de limpeza urbana" in col_str:
            col_map[col] = "MASSA_LIMPEZA"
        elif "Massa total anual de resíduos sólidos urbanos" in col_str:
            col_map[col] = "MASSA_TOTAL_RSU"
        elif "Tipo de coleta executada" in col_str:
            col_map[col] = "TIPO_COLETA"
        elif "Tipo de unidade de destino" in col_str:
            col_map[col] = "TIPO_DESTINO"
        elif "Massa de resíduos sólidos total coletada" in col_str:
            col_map[col] = "MASSA_ROTA"
        elif "Quantidade total de veículos" in col_str:
            col_map[col] = "QTD_VEICULOS"
    if col_map:
        df = df.rename(columns=col_map)
    return df

def converter_numericas(df):
    if df is None:
        return df
    for col in df.columns:
        if col in ["COD_IBGE", "MUNICIPIO", "UF", "MACRO", "TIPO_COLETA", "TIPO_DESTINO", "NATUREZA JURÍDICA", "CNPJ"]:
            continue
        if df[col].dtype == object:
            try:
                df[col] = pd.to_numeric(df[col], errors="coerce")
            except:
                pass
    return df

df_res_2023 = padronizar_colunas(df_res_2023)
df_res_2023 = converter_numericas(df_res_2023)
df_res_2024 = padronizar_colunas(df_res_2024)
df_res_2024 = converter_numericas(df_res_2024)

df_col_2023 = padronizar_colunas(df_col_2023)
df_col_2023 = converter_numericas(df_col_2023)
df_col_2024 = padronizar_colunas(df_col_2024)
df_col_2024 = converter_numericas(df_col_2024)

# =========================================================
# SIDEBAR - FILTROS GLOBAIS
# =========================================================
st.sidebar.markdown("---")
st.sidebar.subheader("🔍 Filtros")

ano_base = st.sidebar.selectbox("Ano para análise detalhada", [2023, 2024], index=1)

if ano_base == 2023:
    df_res = df_res_2023
    df_col = df_col_2023
else:
    df_res = df_res_2024
    df_col = df_col_2024

# Filtros de UF
ufs = sorted(df_res["UF"].dropna().unique()) if "UF" in df_res.columns else []
uf_selecionada = st.sidebar.selectbox("UF (opcional)", ["Todas"] + ufs)

# Filtro de população (slider)
if "POP_TOTAL" in df_res.columns:
    pop_min = int(df_res["POP_TOTAL"].min()) if not df_res["POP_TOTAL"].isna().all() else 0
    pop_max = int(df_res["POP_TOTAL"].max()) if not df_res["POP_TOTAL"].isna().all() else 10000000
    pop_range = st.sidebar.slider("Faixa de população (milhares)", 
                                  min_value=pop_min//1000, 
                                  max_value=pop_max//1000,
                                  value=(pop_min//1000, pop_max//1000))
    pop_min_filt = pop_range[0] * 1000
    pop_max_filt = pop_range[1] * 1000
else:
    pop_min_filt, pop_max_filt = 0, 1e12

# Aplicar filtros
def filtrar_df(df):
    if df is None:
        return df
    if "UF" in df.columns and uf_selecionada != "Todas":
        df = df[df["UF"] == uf_selecionada]
    if "POP_TOTAL" in df.columns:
        df = df[(df["POP_TOTAL"] >= pop_min_filt) & (df["POP_TOTAL"] <= pop_max_filt)]
    return df

df_res_filt = filtrar_df(df_res)
df_col_filt = filtrar_df(df_col)

# =========================================================
# ABAS
# =========================================================
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📌 Visão Geral",
    "🏙️ Municípios",
    "🚚 Rotas de Coleta",
    "♻️ Destinação",
    "📈 Comparação 2023↔2024"
])

# =========================================================
# TAB 1 - VISÃO GERAL
# =========================================================
with tab1:
    st.header("📌 Visão Geral dos Dados")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total de municípios", df_res_filt.shape[0] if df_res_filt is not None else 0)
    with col2:
        if "UF" in df_res_filt.columns:
            st.metric("Estados representados", df_res_filt["UF"].nunique())
    with col3:
        if "POP_TOTAL" in df_res_filt.columns:
            pop_total = df_res_filt["POP_TOTAL"].sum()
            st.metric("População total", f"{pop_total:,.0f}".replace(",", "."))

    st.markdown("---")
    
    # Gráfico 1: Distribuição de municípios por UF (barras)
    if "UF" in df_res_filt.columns:
        uf_counts = df_res_filt["UF"].value_counts().reset_index()
        uf_counts.columns = ["UF", "Quantidade"]
        fig_uf = px.bar(uf_counts, x="UF", y="Quantidade", title="Número de municípios por UF",
                        color="Quantidade", color_continuous_scale="Blues")
        fig_uf.update_layout(xaxis_tickangle=45)
        st.plotly_chart(fig_uf, use_container_width=True)

    # Gráfico 2: Distribuição de população (histograma)
    if "POP_TOTAL" in df_res_filt.columns:
        fig_pop = px.histogram(df_res_filt, x="POP_TOTAL", nbins=50, 
                               title="Distribuição da população dos municípios",
                               labels={"POP_TOTAL": "População"},
                               color_discrete_sequence=["#2E86C1"])
        st.plotly_chart(fig_pop, use_container_width=True)

    # Gráfico 3: Massa total de RSU por UF (top 10)
    if "UF" in df_res_filt.columns and "MASSA_TOTAL_RSU" in df_res_filt.columns:
        uf_massa = df_res_filt.groupby("UF")["MASSA_TOTAL_RSU"].sum().reset_index()
        uf_massa = uf_massa.sort_values("MASSA_TOTAL_RSU", ascending=False).head(10)
        fig_massa = px.bar(uf_massa, x="UF", y="MASSA_TOTAL_RSU", title="Top 10 UFs - Massa total de RSU",
                           labels={"MASSA_TOTAL_RSU": "Massa (t)"},
                           color="MASSA_TOTAL_RSU", color_continuous_scale="Greens")
        st.plotly_chart(fig_massa, use_container_width=True)

# =========================================================
# TAB 2 - MUNICÍPIOS
# =========================================================
with tab2:
    st.header("🏙️ Análise por Município")

    if df_res_filt is not None and not df_res_filt.empty:
        cols_disponiveis = df_res_filt.columns.tolist()
        cols_para_exibir = st.multiselect(
            "Selecione as colunas para exibir na tabela",
            cols_disponiveis,
            default=[c for c in ["MUNICIPIO", "UF", "POP_TOTAL", "MASSA_TOTAL_RSU", "MASSA_SELETIVA"] if c in cols_disponiveis]
        )
        if cols_para_exibir:
            df_tab = df_res_filt[cols_para_exibir].copy()
            for col in df_tab.columns:
                if col not in ["MUNICIPIO", "UF", "MACRO"]:
                    df_tab[col] = df_tab[col].apply(lambda x: f"{x:,.0f}" if pd.notna(x) else "")
            st.dataframe(df_tab, use_container_width=True, height=500)

        # Gráfico de dispersão: População vs Massa de RSU
        if "POP_TOTAL" in df_res_filt.columns and "MASSA_TOTAL_RSU" in df_res_filt.columns:
            fig_scatter = px.scatter(df_res_filt, x="POP_TOTAL", y="MASSA_TOTAL_RSU", 
                                     hover_data=["MUNICIPIO", "UF"],
                                     title="Relação População vs Massa de RSU",
                                     labels={"POP_TOTAL": "População", "MASSA_TOTAL_RSU": "Massa (t)"},
                                     color="UF" if "UF" in df_res_filt.columns else None,
                                     trendline="ols")
            st.plotly_chart(fig_scatter, use_container_width=True)

# =========================================================
# TAB 3 - ROTAS DE COLETA
# =========================================================
with tab3:
    st.header("🚚 Análise das Rotas de Coleta")

    if df_col_filt is not None and not df_col_filt.empty:
        col1, col2, col3 = st.columns(3)
        col1.metric("Total de rotas", df_col_filt.shape[0])
        if "MASSA_ROTA" in df_col_filt.columns:
            col2.metric("Massa total nas rotas", f"{df_col_filt['MASSA_ROTA'].sum():,.0f} t".replace(",", "."))
        if "TIPO_COLETA" in df_col_filt.columns:
            col3.metric("Tipos de coleta distintos", df_col_filt["TIPO_COLETA"].nunique())

        if "TIPO_COLETA" in df_col_filt.columns:
            freq = df_col_filt["TIPO_COLETA"].value_counts().reset_index()
            freq.columns = ["Tipo", "Quantidade"]
            fig_freq = px.bar(freq, x="Tipo", y="Quantidade", title="Frequência dos tipos de coleta",
                              color="Quantidade", color_continuous_scale="Viridis")
            fig_freq.update_layout(xaxis_tickangle=45)
            st.plotly_chart(fig_freq, use_container_width=True)

        if "MASSA_ROTA" in df_col_filt.columns and "TIPO_COLETA" in df_col_filt.columns:
            mass_tipo = df_col_filt.groupby("TIPO_COLETA")["MASSA_ROTA"].sum().reset_index()
            mass_tipo = mass_tipo.sort_values("MASSA_ROTA", ascending=False)
            fig_pie = px.pie(mass_tipo, values="MASSA_ROTA", names="TIPO_COLETA", 
                             title="Massa coletada por tipo de coleta", hole=0.4)
            st.plotly_chart(fig_pie, use_container_width=True)

        st.subheader("🔍 Amostra das rotas")
        st.dataframe(df_col_filt.head(100), use_container_width=True)

# =========================================================
# TAB 4 - DESTINAÇÃO (COM MAPA COROPLÉTICO)
# =========================================================
with tab4:
    st.header("♻️ Análise da Destinação dos Resíduos")

    if df_col_filt is not None and not df_col_filt.empty:
        if "TIPO_DESTINO" in df_col_filt.columns:
            destinos = df_col_filt["TIPO_DESTINO"].value_counts().reset_index()
            destinos.columns = ["Destino", "Quantidade"]
            if "MASSA_ROTA" in df_col_filt.columns:
                mass_dest = df_col_filt.groupby("TIPO_DESTINO")["MASSA_ROTA"].sum().reset_index()
                mass_dest = mass_dest.sort_values("MASSA_ROTA", ascending=False)
                fig_dest = px.bar(mass_dest, x="TIPO_DESTINO", y="MASSA_ROTA", 
                                  title="Massa destinada por tipo",
                                  labels={"MASSA_ROTA": "Massa (t)"},
                                  color="MASSA_ROTA", color_continuous_scale="Viridis")
                fig_dest.update_layout(xaxis_tickangle=45)
                st.plotly_chart(fig_dest, use_container_width=True)
            else:
                fig_dest = px.pie(destinos, values="Quantidade", names="Destino",
                                  title="Distribuição dos tipos de destino")
                st.plotly_chart(fig_dest, use_container_width=True)

        # Mapa coroplético (via GeoJSON)
        if "UF" in df_col_filt.columns and "MASSA_ROTA" in df_col_filt.columns:
            st.subheader("🗺️ Mapa da Massa Coletada por Estado")
            uf_mass = df_col_filt.groupby("UF")["MASSA_ROTA"].sum().reset_index()
            if not uf_mass.empty:
                try:
                    geojson_url = "https://raw.githubusercontent.com/codeforamerica/click_that_hood/master/public/data/brazil-states.geojson"
                    response = requests.get(geojson_url, timeout=10)
                    response.raise_for_status()
                    geojson_data = response.json()
                    
                    # Mapear siglas para IDs (usando propriedade "sigla")
                    sigla_to_id = {}
                    for feature in geojson_data['features']:
                        props = feature['properties']
                        sigla = props.get('sigla', '').upper()
                        id_ = feature.get('id') or props.get('id')
                        if sigla and id_:
                            sigla_to_id[sigla] = id_
                    
                    uf_mass['id'] = uf_mass['UF'].map(sigla_to_id)
                    uf_mass = uf_mass.dropna(subset=['id'])
                    
                    if not uf_mass.empty:
                        fig_map = px.choropleth(
                            uf_mass,
                            geojson=geojson_data,
                            locations='id',
                            color='MASSA_ROTA',
                            hover_name='UF',
                            title="Massa coletada por estado",
                            color_continuous_scale="Greens",
                            labels={"MASSA_ROTA": "Massa (t)"}
                        )
                        fig_map.update_geos(fitbounds="locations", visible=False)
                        st.plotly_chart(fig_map, use_container_width=True)
                    else:
                        st.warning("Não foi possível mapear os estados. Exibindo gráfico de barras.")
                        fig_bar = px.bar(uf_mass.sort_values("MASSA_ROTA", ascending=False), 
                                         x="UF", y="MASSA_ROTA", title="Massa coletada por estado")
                        st.plotly_chart(fig_bar, use_container_width=True)
                except Exception as e:
                    st.warning(f"Erro no mapa: {e}. Exibindo gráfico de barras.")
                    fig_bar = px.bar(uf_mass.sort_values("MASSA_ROTA", ascending=False), 
                                     x="UF", y="MASSA_ROTA", title="Massa coletada por estado")
                    st.plotly_chart(fig_bar, use_container_width=True)

# =========================================================
# TAB 5 - COMPARAÇÃO 2023 vs 2024
# =========================================================
with tab5:
    st.header("📈 Comparação entre 2023 e 2024")

    def get_metric(df, col):
        if df is not None and col in df.columns:
            return df[col].sum()
        return np.nan

    massas = {"2023": get_metric(df_res_2023, "MASSA_TOTAL_RSU"),
              "2024": get_metric(df_res_2024, "MASSA_TOTAL_RSU")}
    pops = {"2023": get_metric(df_res_2023, "POP_TOTAL"),
            "2024": get_metric(df_res_2024, "POP_TOTAL")}

    col1, col2 = st.columns(2)
    with col1:
        fig_massa = px.bar(x=list(massas.keys()), y=list(massas.values()),
                           title="Massa total de RSU (t)",
                           labels={"x": "Ano", "y": "Massa (t)"},
                           color=list(massas.keys()),
                           color_discrete_sequence=["#1f77b4", "#ff7f0e"])
        st.plotly_chart(fig_massa, use_container_width=True)

    with col2:
        fig_pop = px.bar(x=list(pops.keys()), y=list(pops.values()),
                         title="População total",
                         labels={"x": "Ano", "y": "População"},
                         color=list(pops.keys()),
                         color_discrete_sequence=["#2ca02c", "#d62728"])
        st.plotly_chart(fig_pop, use_container_width=True)

    # Comparação de tipos de coleta
    if "TIPO_COLETA" in df_col_2023.columns and "TIPO_COLETA" in df_col_2024.columns:
        st.subheader("📋 Evolução dos Tipos de Coleta")
        freq_2023 = df_col_2023["TIPO_COLETA"].value_counts().reset_index()
        freq_2023.columns = ["Tipo", "2023"]
        freq_2024 = df_col_2024["TIPO_COLETA"].value_counts().reset_index()
        freq_2024.columns = ["Tipo", "2024"]
        freq_comp = pd.merge(freq_2023, freq_2024, on="Tipo", how="outer").fillna(0)

        fig_comp = go.Figure()
        fig_comp.add_trace(go.Bar(x=freq_comp["Tipo"], y=freq_comp["2023"], name="2023", marker_color="#1f77b4"))
        fig_comp.add_trace(go.Bar(x=freq_comp["Tipo"], y=freq_comp["2024"], name="2024", marker_color="#ff7f0e"))
        fig_comp.update_layout(title="Comparação de tipos de coleta", xaxis_tickangle=45, barmode="group")
        st.plotly_chart(fig_comp, use_container_width=True)

# =========================================================
# RODAPÉ
# =========================================================
st.markdown("---")
st.caption(f"📅 Dados do SNIS - {ano_base} | Desenvolvido com Streamlit e Plotly | Arquivos locais.")
