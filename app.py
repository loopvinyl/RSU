import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import io
import os

# =========================================================
# CONFIGURAÇÃO DA PÁGINA
# =========================================================
st.set_page_config(
    page_title="📊 Análise SNIS - Resíduos Sólidos",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("📊 Análise Exploratória do SNIS - Resíduos Sólidos Urbanos")
st.markdown("""
**Ferramenta interativa** para explorar os dados dos anos 2023 e 2024 do SNIS (Módulo Manejo de Resíduos Sólidos).
Navegue pelas abas para entender a estrutura, distribuições e principais indicadores.
""")

# =========================================================
# CARREGAMENTO DOS DADOS (UPLOAD OU LOCAL)
# =========================================================
st.sidebar.header("📂 Carregar arquivos")

uploaded_2023 = st.sidebar.file_uploader("Arquivo 2023 (rsuBrasil_2023.xlsx)", type=["xlsx"])
uploaded_2024 = st.sidebar.file_uploader("Arquivo 2024 (rsuBrasil_2024.xlsx)", type=["xlsx"])

# Se não houver upload, tenta carregar do diretório local (para desenvolvimento)
if uploaded_2023 is None and uploaded_2024 is None:
    if os.path.exists("rsuBrasil_2023.xlsx") and os.path.exists("rsuBrasil_2024.xlsx"):
        st.sidebar.info("📁 Usando arquivos locais (mesmo diretório)")
        path_2023 = "rsuBrasil_2023.xlsx"
        path_2024 = "rsuBrasil_2024.xlsx"
    else:
        st.sidebar.warning("⚠️ Faça upload dos arquivos ou coloque-os no diretório.")
        st.stop()
else:
    # Salvar uploads em disco temporário (ou ler direto)
    if uploaded_2023 is not None:
        path_2023 = "temp_2023.xlsx"
        with open(path_2023, "wb") as f:
            f.write(uploaded_2023.getbuffer())
    else:
        path_2023 = None
    if uploaded_2024 is not None:
        path_2024 = "temp_2024.xlsx"
        with open(path_2024, "wb") as f:
            f.write(uploaded_2024.getbuffer())
    else:
        path_2024 = None

# =========================================================
# FUNÇÕES DE LEITURA INTELIGENTE
# =========================================================
def ler_aba_inteligente(caminho, aba, header_row=None):
    """
    Lê uma aba do Excel identificando automaticamente onde estão os dados.
    """
    try:
        # Primeiro, ler sem header para verificar as primeiras linhas
        df_raw = pd.read_excel(caminho, sheet_name=aba, header=None)
        # Procurar a linha que contém "CÓDIGO DO IBGE" (indicador de cabeçalho)
        header_idx = None
        for i, row in df_raw.iterrows():
            if row.astype(str).str.contains("CÓDIGO DO IBGE", case=False, na=False).any():
                header_idx = i
                break
        if header_idx is not None:
            df = pd.read_excel(caminho, sheet_name=aba, header=header_idx)
        else:
            # Fallback: usar header=0 se parecer dados
            df = pd.read_excel(caminho, sheet_name=aba, header=0)
        # Remover linhas completamente vazias
        df = df.dropna(how="all")
        return df
    except Exception as e:
        st.error(f"Erro ao ler aba {aba}: {e}")
        return None

@st.cache_data
def carregar_dados(ano, caminho):
    """
    Carrega as abas principais: Resíduos e Coleta.
    """
    if caminho is None:
        return None, None
    df_residuos = ler_aba_inteligente(caminho, "Manejo_Resíduos_Sólidos_Urbanos")
    df_coleta = ler_aba_inteligente(caminho, "Manejo_Coleta_e_Destinação")
    return df_residuos, df_coleta

# Carregar os dados
df_res_2023, df_col_2023 = carregar_dados(2023, path_2023)
df_res_2024, df_col_2024 = carregar_dados(2024, path_2024)

if df_res_2023 is None or df_res_2024 is None:
    st.error("❌ Não foi possível carregar os dados. Verifique os arquivos.")
    st.stop()

# =========================================================
# PRÉ-PROCESSAMENTO
# =========================================================
def padronizar_colunas(df):
    """Renomeia colunas comuns para facilitar a análise."""
    if df is None:
        return df
    # Mapeamento de nomes comuns baseado na análise
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
        elif "Massa total anual" in col_str and "domiciliares" in col_str and "seletiva" not in col_str:
            col_map[col] = "MASSA_DOMICILIAR"
        elif "Massa total anual" in col_str and "seletiva" in col_str:
            col_map[col] = "MASSA_SELETIVA"
        elif "Massa total anual" in col_str and "limpeza" in col_str:
            col_map[col] = "MASSA_LIMPEZA"
        elif "Massa total anual de resíduos sólidos urbanos" in col_str:
            col_map[col] = "MASSA_TOTAL_RSU"
        elif "Tipo de coleta executada" in col_str:
            col_map[col] = "TIPO_COLETA"
        elif "Tipo de unidade de destino" in col_str:
            col_map[col] = "TIPO_DESTINO"
        elif "Massa de resíduos sólidos total coletada" in col_str:
            col_map[col] = "MASSA_ROTA"
    df = df.rename(columns=col_map)
    return df

def converter_numericas(df):
    """Converte colunas numéricas (que vieram como objeto) para float."""
    if df is None:
        return df
    for col in df.columns:
        if col not in ["COD_IBGE", "MUNICIPIO", "UF", "MACRO", "TIPO_COLETA", "TIPO_DESTINO"]:
            # Tenta converter para numérico
            df[col] = pd.to_numeric(df[col], errors="coerce")
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
# FUNÇÕES AUXILIARES PARA ANÁLISE
# =========================================================
def resumo_dataframe(df, nome):
    if df is None:
        return pd.DataFrame()
    buffer = io.StringIO()
    df.info(buf=buffer)
    info_str = buffer.getvalue()
    stats = {
        "Nome": nome,
        "Linhas": df.shape[0],
        "Colunas": df.shape[1],
        "Memória (MB)": df.memory_usage(deep=True).sum() / 1e6,
        "Nulos (%)": (df.isna().sum().sum() / (df.shape[0]*df.shape[1])) * 100,
    }
    return stats

def colunas_numericas(df):
    return df.select_dtypes(include=np.number).columns.tolist()

def colunas_categoricas(df):
    return df.select_dtypes(include="object").columns.tolist()

# =========================================================
# SIDEBAR - FILTROS GLOBAIS
# =========================================================
st.sidebar.markdown("---")
st.sidebar.subheader("🔍 Filtros")

# Selecionar ano base para análises
ano_base = st.sidebar.selectbox("Ano para análise detalhada", [2023, 2024], index=1)

# Definir os dataframes ativos
if ano_base == 2023:
    df_res = df_res_2023
    df_col = df_col_2023
else:
    df_res = df_res_2024
    df_col = df_col_2024

# Filtros de UF e município (se disponíveis)
ufs = sorted(df_res["UF"].dropna().unique()) if "UF" in df_res.columns else []
uf_selecionada = st.sidebar.selectbox("UF (opcional)", ["Todas"] + ufs)

municipios = sorted(df_res["MUNICIPIO"].dropna().unique()) if "MUNICIPIO" in df_res.columns else []
municipio_selecionado = st.sidebar.selectbox("Município (opcional)", ["Todos"] + municipios)

# Aplicar filtros
def filtrar_df(df):
    if df is None:
        return df
    if "UF" in df.columns and uf_selecionada != "Todas":
        df = df[df["UF"] == uf_selecionada]
    if "MUNICIPIO" in df.columns and municipio_selecionado != "Todos":
        df = df[df["MUNICIPIO"] == municipio_selecionado]
    return df

df_res_filt = filtrar_df(df_res)
df_col_filt = filtrar_df(df_col)

# =========================================================
# ABAS PRINCIPAIS
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

    col1, col2 = st.columns(2)
    with col1:
        st.subheader(f"📊 {ano_base} - Resumo dos Municípios")
        st.metric("Total de municípios", df_res_filt.shape[0] if df_res_filt is not None else 0)
        if "UF" in df_res_filt.columns:
            st.metric("Estados representados", df_res_filt["UF"].nunique())
        if "POP_TOTAL" in df_res_filt.columns:
            pop_total = df_res_filt["POP_TOTAL"].sum()
            st.metric("População total (estimada)", f"{pop_total:,.0f}".replace(",", "."))

    with col2:
        st.subheader("📦 Abas disponíveis")
        st.markdown("""
        - **Resíduos Sólidos Urbanos**: dados gerais dos municípios (população, massas, caracterização).
        - **Coleta e Destinação**: rotas de coleta, massas por tipo, destinos.
        - **Veículos**: frota utilizada.
        - **Cooperativas**: informações sobre catadores e associações.
        """)

    st.markdown("---")
    st.subheader("🧹 Qualidade dos Dados")

    # Estatísticas de nulos para a aba Resíduos
    if df_res_filt is not None:
        nulos = df_res_filt.isna().sum()
        nulos = nulos[nulos > 0].sort_values(ascending=False)
        if not nulos.empty:
            fig_nulos = px.bar(
                x=nulos.index,
                y=nulos.values,
                title="Colunas com valores nulos (Resíduos)",
                labels={"x": "Coluna", "y": "Número de nulos"},
                color=nulos.values,
                color_continuous_scale="Reds"
            )
            fig_nulos.update_layout(xaxis_tickangle=45, height=400)
            st.plotly_chart(fig_nulos, use_container_width=True)
        else:
            st.success("✅ Nenhum valor nulo encontrado!")

    # Comparativo rápido entre anos
    st.markdown("---")
    st.subheader("📊 Comparativo Rápido 2023 vs 2024")

    # Total de municípios e massa (se disponível)
    if "MASSA_TOTAL_RSU" in df_res_2023.columns and "MASSA_TOTAL_RSU" in df_res_2024.columns:
        total_massa_2023 = df_res_2023["MASSA_TOTAL_RSU"].sum()
        total_massa_2024 = df_res_2024["MASSA_TOTAL_RSU"].sum()
        diff_massa = total_massa_2024 - total_massa_2023
        pct_massa = (diff_massa / total_massa_2023) * 100 if total_massa_2023 > 0 else 0

        col1, col2, col3 = st.columns(3)
        col1.metric("2023", f"{total_massa_2023:,.0f} t".replace(",", "."))
        col2.metric("2024", f"{total_massa_2024:,.0f} t".replace(",", "."))
        col3.metric("Variação", f"{diff_massa:+,.0f} t ({pct_massa:+.1f}%)".replace(",", "."))

# =========================================================
# TAB 2 - MUNICÍPIOS
# =========================================================
with tab2:
    st.header("🏙️ Análise por Município")

    if df_res_filt is not None and not df_res_filt.empty:
        # Selecionar colunas para exibir
        cols_disponiveis = df_res_filt.columns.tolist()
        cols_para_exibir = st.multiselect(
            "Selecione as colunas para exibir na tabela",
            cols_disponiveis,
            default=[c for c in ["MUNICIPIO", "UF", "POP_TOTAL", "MASSA_TOTAL_RSU", "MASSA_SELETIVA"] if c in cols_disponiveis]
        )

        if cols_para_exibir:
            # Tabela com formatação
            df_tab = df_res_filt[cols_para_exibir].copy()
            # Formatar números
            for col in df_tab.columns:
                if col not in ["MUNICIPIO", "UF", "MACRO"]:
                    df_tab[col] = df_tab[col].apply(lambda x: f"{x:,.0f}" if pd.notna(x) else "")
            st.dataframe(df_tab, use_container_width=True, height=500)

        # Gráficos de distribuição
        st.subheader("📊 Distribuição de Massa e População")

        # Histograma de população
        if "POP_TOTAL" in df_res_filt.columns:
            fig_pop = px.histogram(
                df_res_filt,
                x="POP_TOTAL",
                title="Distribuição da População dos Municípios",
                labels={"POP_TOTAL": "População"},
                nbins=50,
                color_discrete_sequence=["#2E86C1"]
            )
            st.plotly_chart(fig_pop, use_container_width=True)

        # Top 10 municípios por massa
        if "MASSA_TOTAL_RSU" in df_res_filt.columns and "MUNICIPIO" in df_res_filt.columns:
            top10 = df_res_filt.nlargest(10, "MASSA_TOTAL_RSU")
            fig_top = px.bar(
                top10,
                x="MUNICIPIO",
                y="MASSA_TOTAL_RSU",
                title=f"Top 10 municípios - {ano_base}",
                labels={"MASSA_TOTAL_RSU": "Massa (t)"},
                color="UF" if "UF" in top10.columns else None,
                hover_data=["POP_TOTAL"] if "POP_TOTAL" in top10.columns else None
            )
            fig_top.update_layout(xaxis_tickangle=45)
            st.plotly_chart(fig_top, use_container_width=True)

# =========================================================
# TAB 3 - ROTAS DE COLETA
# =========================================================
with tab3:
    st.header("🚚 Análise das Rotas de Coleta")

    if df_col_filt is not None and not df_col_filt.empty:
        # Estatísticas básicas
        col1, col2, col3 = st.columns(3)
        col1.metric("Total de rotas", df_col_filt.shape[0])
        if "MASSA_ROTA" in df_col_filt.columns:
            col2.metric("Massa total nas rotas", f"{df_col_filt['MASSA_ROTA'].sum():,.0f} t".replace(",", "."))
        if "TIPO_COLETA" in df_col_filt.columns:
            col3.metric("Tipos de coleta distintos", df_col_filt["TIPO_COLETA"].nunique())

        st.subheader("📊 Distribuição por Tipo de Coleta")
        if "TIPO_COLETA" in df_col_filt.columns:
            # Frequência
            freq = df_col_filt["TIPO_COLETA"].value_counts().reset_index()
            freq.columns = ["Tipo", "Quantidade"]
            fig_freq = px.bar(
                freq,
                x="Tipo",
                y="Quantidade",
                title="Frequência dos tipos de coleta",
                color="Quantidade",
                color_continuous_scale="Blues"
            )
            fig_freq.update_layout(xaxis_tickangle=45)
            st.plotly_chart(fig_freq, use_container_width=True)

            # Massa por tipo (se disponível)
            if "MASSA_ROTA" in df_col_filt.columns:
                mass_tipo = df_col_filt.groupby("TIPO_COLETA")["MASSA_ROTA"].sum().reset_index()
                mass_tipo = mass_tipo.sort_values("MASSA_ROTA", ascending=False)
                fig_mass = px.pie(
                    mass_tipo,
                    values="MASSA_ROTA",
                    names="TIPO_COLETA",
                    title="Massa coletada por tipo",
                    hole=0.4
                )
                st.plotly_chart(fig_mass, use_container_width=True)

        # Tabela com amostra das rotas
        st.subheader("🔍 Amostra das rotas")
        st.dataframe(df_col_filt.head(100), use_container_width=True)

# =========================================================
# TAB 4 - DESTINAÇÃO
# =========================================================
with tab4:
    st.header("♻️ Análise da Destinação dos Resíduos")

    if df_col_filt is not None and not df_col_filt.empty:
        if "TIPO_DESTINO" in df_col_filt.columns:
            # Distribuição por destino
            destinos = df_col_filt["TIPO_DESTINO"].value_counts().reset_index()
            destinos.columns = ["Destino", "Quantidade"]
            # Massa por destino (se disponível)
            if "MASSA_ROTA" in df_col_filt.columns:
                mass_dest = df_col_filt.groupby("TIPO_DESTINO")["MASSA_ROTA"].sum().reset_index()
                mass_dest = mass_dest.sort_values("MASSA_ROTA", ascending=False)
                fig_dest = px.bar(
                    mass_dest,
                    x="TIPO_DESTINO",
                    y="MASSA_ROTA",
                    title="Massa destinada por tipo",
                    labels={"MASSA_ROTA": "Massa (t)"},
                    color="MASSA_ROTA",
                    color_continuous_scale="Viridis"
                )
                fig_dest.update_layout(xaxis_tickangle=45)
                st.plotly_chart(fig_dest, use_container_width=True)
            else:
                # Apenas contagem
                fig_dest = px.pie(
                    destinos,
                    values="Quantidade",
                    names="Destino",
                    title="Distribuição dos tipos de destino (rotas)"
                )
                st.plotly_chart(fig_dest, use_container_width=True)

        # Mapa coroplético (por UF) se houver massa
        if "UF" in df_col_filt.columns and "MASSA_ROTA" in df_col_filt.columns:
            st.subheader("🗺️ Mapa da Massa Coletada por Estado")
            uf_mass = df_col_filt.groupby("UF")["MASSA_ROTA"].sum().reset_index()
            # Usar siglas para mapear
            fig_map = px.choropleth(
                uf_mass,
                locations="UF",
                locationmode="Brazil-states",
                color="MASSA_ROTA",
                hover_name="UF",
                title="Massa coletada por estado (2024)",
                color_continuous_scale="Greens",
                labels={"MASSA_ROTA": "Massa (t)"}
            )
            fig_map.update_layout(geo=dict(bgcolor="rgba(0,0,0,0)"))
            st.plotly_chart(fig_map, use_container_width=True)

# =========================================================
# TAB 5 - COMPARAÇÃO 2023 vs 2024
# =========================================================
with tab5:
    st.header("📈 Comparação entre 2023 e 2024")

    # Métricas agregadas
    def get_metric(df, col):
        if df is not None and col in df.columns:
            return df[col].sum()
        return np.nan

    massas = {
        "2023": get_metric(df_res_2023, "MASSA_TOTAL_RSU"),
        "2024": get_metric(df_res_2024, "MASSA_TOTAL_RSU")
    }
    pops = {
        "2023": get_metric(df_res_2023, "POP_TOTAL"),
        "2024": get_metric(df_res_2024, "POP_TOTAL")
    }

    col1, col2 = st.columns(2)
    with col1:
        fig_massa = px.bar(
            x=list(massas.keys()),
            y=list(massas.values()),
            title="Massa total de RSU (t)",
            labels={"x": "Ano", "y": "Massa (t)"},
            color=list(massas.keys()),
            color_discrete_sequence=["#1f77b4", "#ff7f0e"]
        )
        st.plotly_chart(fig_massa, use_container_width=True)

    with col2:
        fig_pop = px.bar(
            x=list(pops.keys()),
            y=list(pops.values()),
            title="População total",
            labels={"x": "Ano", "y": "População"},
            color=list(pops.keys()),
            color_discrete_sequence=["#2ca02c", "#d62728"]
        )
        st.plotly_chart(fig_pop, use_container_width=True)

    # Comparação de distribuição de tipos de coleta
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
        fig_comp.update_layout(
            title="Comparação de tipos de coleta",
            xaxis_tickangle=45,
            barmode="group"
        )
        st.plotly_chart(fig_comp, use_container_width=True)

    st.info("💡 Explore as outras abas para análises mais detalhadas por município, rotas e destinos.")

# =========================================================
# RODAPÉ
# =========================================================
st.markdown("---")
st.caption(f"📅 Dados do SNIS - {ano_base} | Desenvolvido com Streamlit e Plotly")
