import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import os
import requests

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
# CARREGAMENTO DOS ARQUIVOS (DIRETÓRIO LOCAL)
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

st.sidebar.success("✅ Arquivos encontrados no diretório!")

# =========================================================
# FUNÇÃO PARA LER ABA INTELIGENTEMENTE
# =========================================================
def ler_aba(caminho, nome_aba):
    """
    Lê uma aba do Excel, identificando a linha de cabeçalho.
    """
    try:
        df_raw = pd.read_excel(caminho, sheet_name=nome_aba, header=None)
        header_idx = None
        for i, row in df_raw.iterrows():
            if row.astype(str).str.contains("CÓDIGO DO IBGE|RESPONDEU AO MÓDULO", case=False, na=False).any():
                header_idx = i
                break
        if header_idx is not None:
            df = pd.read_excel(caminho, sheet_name=nome_aba, header=header_idx)
        else:
            df = pd.read_excel(caminho, sheet_name=nome_aba, header=0)
        df = df.dropna(how="all")
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
# PRÉ-PROCESSAMENTO
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

ufs = sorted(df_res["UF"].dropna().unique()) if "UF" in df_res.columns else []
uf_selecionada = st.sidebar.selectbox("UF (opcional)", ["Todas"] + ufs)

municipios = sorted(df_res["MUNICIPIO"].dropna().unique()) if "MUNICIPIO" in df_res.columns else []
municipio_selecionado = st.sidebar.selectbox("Município (opcional)", ["Todos"] + municipios)

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
        - **Resíduos Sólidos Urbanos**: dados gerais dos municípios.
        - **Coleta e Destinação**: rotas de coleta, massas e destinos.
        - **Veículos**: frota utilizada.
        - **Cooperativas**: informações sobre catadores.
        """)

    st.markdown("---")
    st.subheader("🧹 Qualidade dos Dados - Colunas com valores nulos")
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

        if "POP_TOTAL" in df_res_filt.columns:
            fig_pop = px.histogram(
                df_res_filt,
                x="POP_TOTAL",
                title="Distribuição da População",
                labels={"POP_TOTAL": "População"},
                nbins=50,
                color_discrete_sequence=["#2E86C1"]
            )
            st.plotly_chart(fig_pop, use_container_width=True)

        if "MASSA_TOTAL_RSU" in df_res_filt.columns and "MUNICIPIO" in df_res_filt.columns:
            top10 = df_res_filt.nlargest(10, "MASSA_TOTAL_RSU")
            fig_top = px.bar(
                top10,
                x="MUNICIPIO",
                y="MASSA_TOTAL_RSU",
                title=f"Top 10 municípios - {ano_base}",
                labels={"MASSA_TOTAL_RSU": "Massa (t)"},
                color="UF" if "UF" in top10.columns else None
            )
            fig_top.update_layout(xaxis_tickangle=45)
            st.plotly_chart(fig_top, use_container_width=True)

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

        st.subheader("🔍 Amostra das rotas")
        st.dataframe(df_col_filt.head(100), use_container_width=True)

# =========================================================
# TAB 4 - DESTINAÇÃO (COM MAPA COROPLÉTICO CORRIGIDO)
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
                fig_dest = px.pie(
                    destinos,
                    values="Quantidade",
                    names="Destino",
                    title="Distribuição dos tipos de destino (rotas)"
                )
                st.plotly_chart(fig_dest, use_container_width=True)

        # ========== MAPA COROPLÉTICO COM GEOJSON ==========
        if "UF" in df_col_filt.columns and "MASSA_ROTA" in df_col_filt.columns:
            st.subheader("🗺️ Mapa da Massa Coletada por Estado")
            uf_mass = df_col_filt.groupby("UF")["MASSA_ROTA"].sum().reset_index()
            # Garantir que há dados
            if uf_mass.empty:
                st.warning("Sem dados para gerar o mapa.")
            else:
                try:
                    # Baixar GeoJSON do Brasil
                    geojson_url = "https://raw.githubusercontent.com/codeforamerica/click_that_hood/master/public/data/brazil-states.geojson"
                    response = requests.get(geojson_url, timeout=10)
                    response.raise_for_status()
                    geojson_data = response.json()

                    # Mapear siglas para IDs do GeoJSON (geralmente código IBGE)
                    sigla_to_id = {}
                    for feature in geojson_data['features']:
                        props = feature['properties']
                        sigla = props.get('sigla', '').upper()
                        id_ = feature.get('id') or props.get('id')
                        if sigla and id_:
                            sigla_to_id[sigla] = id_

                    uf_mass['id'] = uf_mass['UF'].map(sigla_to_id)
                    uf_mass = uf_mass.dropna(subset=['id'])

                    if uf_mass.empty:
                        st.warning("Nenhum estado pôde ser mapeado. Exibindo gráfico de barras.")
                        fig_bar = px.bar(uf_mass, x="UF", y="MASSA_ROTA", title="Massa coletada por estado")
                        st.plotly_chart(fig_bar, use_container_width=True)
                    else:
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
                except Exception as e:
                    st.warning(f"Erro ao gerar o mapa: {e}. Exibindo gráfico de barras como alternativa.")
                    fig_bar = px.bar(uf_mass.sort_values("MASSA_ROTA", ascending=False), x="UF", y="MASSA_ROTA", title="Massa coletada por estado")
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

# =========================================================
# RODAPÉ
# =========================================================
st.markdown("---")
st.caption(f"📅 Dados do SNIS - {ano_base} | Desenvolvido com Streamlit e Plotly")
