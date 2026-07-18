import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import os
import unicodedata

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
# FUNÇÕES DE FORMATAÇÃO BRASILEIRA (PADRÃO)
# =========================================================
def formatar_numero_br(valor, casas_decimais=None):
    if pd.isna(valor) or valor is None:
        return "N/A"
    try:
        valor = float(valor)
        if casas_decimais is None:
            if valor == int(valor):
                casas_decimais = 0
            else:
                casas_decimais = 2
        if casas_decimais == 0:
            return f"{valor:,.0f}".replace(",", "X").replace(".", ",").replace("X", ".")
        else:
            formato = f"{{:,.{casas_decimais}f}}"
            return formato.format(valor).replace(",", "X").replace(".", ",").replace("X", ".")
    except (ValueError, TypeError):
        return "N/A"

def formatar_metric(valor, casas=None):
    return formatar_numero_br(valor, casas)

# =========================================================
# FUNÇÃO SEGURA PARA FORMATAR EIXOS DE GRÁFICOS
# =========================================================
def aplicar_formatacao(fig):
    """Aplica formatação brasileira nos eixos do gráfico, ignorando erros."""
    if fig is None:
        return
    try:
        fig.update_yaxis(tickformat=',.0f')
        fig.update_xaxis(tickformat=',.0f')
    except Exception:
        pass  # Silencia erros para não quebrar o app

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
# FUNÇÃO PARA LER ABA (BUSCA AUTOMÁTICA DO HEADER)
# =========================================================
def ler_aba(caminho, nome_aba):
    try:
        df_raw = pd.read_excel(caminho, sheet_name=nome_aba, header=None)
        header_idx = None
        for i, row in df_raw.iterrows():
            row_str = row.astype(str).str.upper()
            if row_str.str.contains("CÓDIGO DO IBGE", na=False).any() and \
               (row_str.str.contains("MUNICÍPIO", na=False).any() or row_str.str.contains("MUNICIPIO", na=False).any()):
                header_idx = i
                break
        if header_idx is None:
            for i, row in df_raw.iterrows():
                if row.astype(str).str.contains("MUNICÍPIO", case=False, na=False).any():
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
        st.error(f"Erro ao ler a aba '{nome_aba}': {e}")
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

ufs = sorted(df_res["UF"].dropna().unique()) if "UF" in df_res.columns else []
uf_selecionada = st.sidebar.selectbox("UF (opcional)", ["Todas"] + ufs)

if "POP_TOTAL" in df_res.columns:
    pop_min = int(df_res["POP_TOTAL"].min()) if not df_res["POP_TOTAL"].isna().all() else 0
    pop_max = int(df_res["POP_TOTAL"].max()) if not df_res["POP_TOTAL"].isna().all() else 10000000
    pop_range = st.sidebar.slider("Faixa de população (milhares)", 
                                  min_value=max(0, pop_min//1000), 
                                  max_value=pop_max//1000,
                                  value=(max(0, pop_min//1000), pop_max//1000))
    st.sidebar.caption(
        "📌 **Como usar:** mova os limites do controle deslizante para selecionar a faixa de população (em milhares de habitantes) "
        "dos municípios que você deseja analisar. Os valores mínimo e máximo são definidos automaticamente com base nos dados "
        "carregados. Ao reduzir o intervalo, apenas os municípios com população dentro da faixa escolhida serão considerados nos "
        "indicadores, tabelas e gráficos, o que permite, por exemplo, analisar exclusivamente cidades de médio ou grande porte."
    )
    pop_min_filt = pop_range[0] * 1000
    pop_max_filt = pop_range[1] * 1000
else:
    pop_min_filt, pop_max_filt = 0, 1e12

def filtrar_df(df):
    if df is None:
        return df
    if "UF" in df.columns and uf_selecionada != "Todas":
        df = df[df["UF"] == uf_selecionada]
    if "POP_TOTAL" in df.columns:
        # Mantém São Paulo (COD_IBGE 3550308) independente da faixa populacional
        cond = ((df["POP_TOTAL"] >= pop_min_filt) & (df["POP_TOTAL"] <= pop_max_filt)) | (df["COD_IBGE"] == 3550308)
        df = df[cond]
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
# TAB 1 - VISÃO GERAL (COM OPÇÃO DE EXCLUIR TRANSBORDO)
# =========================================================
with tab1:
    st.header("📌 Visão Geral dos Dados")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total de municípios", 
          f"{df_res_filt.shape[0]:,}".replace(",", ".") if df_res_filt is not None else "0")
    
    
    with col2:
        if "UF" in df_res_filt.columns:
            st.metric("Unidades Federativas (UF)", df_res_filt["UF"].nunique())
    with col3:
        if "POP_TOTAL" in df_res_filt.columns:
            pop_total = df_res_filt["POP_TOTAL"].sum()
            st.metric("População total", formatar_metric(pop_total, 0))

    if df_res_filt is not None and not df_res_filt.empty:
        st.markdown("---")
        
        # ===== NOVO: checkbox para excluir transbordo nos indicadores =====
        usar_dados_coleta = st.checkbox(
            "Excluir transbordos dos indicadores (usar dados das rotas de coleta)",
            value=False,
            help="Quando ativado, os indicadores são calculados a partir das rotas de coleta, excluindo destinos do tipo 'Transbordo' para evitar dupla contagem."
        )
        st.markdown("---")

        st.subheader("📊 Indicadores de Gestão")

        # --- Determinação das massas conforme a escolha ---
        if usar_dados_coleta and df_col_filt is not None and not df_col_filt.empty:
            # Usa dados das rotas de coleta, excluindo transbordo
            df_rotas = df_col_filt.copy()
            if "TIPO_DESTINO" in df_rotas.columns:
                df_rotas['destino_norm'] = df_rotas['TIPO_DESTINO'].astype(str).apply(
                    lambda x: unicodedata.normalize('NFKD', x).encode('ASCII', 'ignore').decode('utf-8').upper().strip()
                    if pd.notna(x) else ''
                )
                df_rotas = df_rotas[~df_rotas['destino_norm'].str.contains('TRANSBORDO', na=False)]
                df_rotas = df_rotas.drop(columns=['destino_norm'])

            if "MASSA_ROTA" in df_rotas.columns:
                massa_total_ton = df_rotas["MASSA_ROTA"].sum()
                # Massa seletiva: rotas cujo tipo de coleta contenha "seletiva"
                if "TIPO_COLETA" in df_rotas.columns:
                    mask_seletiva = df_rotas["TIPO_COLETA"].astype(str).str.contains("seletiva", case=False, na=False)
                    massa_seletiva = df_rotas.loc[mask_seletiva, "MASSA_ROTA"].sum()
                else:
                    massa_seletiva = 0
                if massa_total_ton == 0 or pd.isna(massa_total_ton):
                    usar_dados_coleta = False  # fallback
                    st.warning("Dados de coleta insuficientes. Usando dados agregados dos municípios.")
            else:
                usar_dados_coleta = False
                st.warning("Coluna 'MASSA_ROTA' não encontrada. Usando dados agregados.")

        if not usar_dados_coleta:
            # Usa os dados agregados da tabela de resíduos (comportamento original)
            if "MASSA_TOTAL_RSU" in df_res_filt.columns:
                massa_total_ton = df_res_filt["MASSA_TOTAL_RSU"].sum()
            else:
                massa_total_ton = 0
            if "MASSA_SELETIVA" in df_res_filt.columns:
                massa_seletiva = df_res_filt["MASSA_SELETIVA"].sum()
            else:
                massa_seletiva = 0

        # --- Cálculos e exibição (idênticos ao original) ---
        if massa_total_ton > 0 and pop_total > 0:
            massa_total_kg = massa_total_ton * 1000
            per_capita_ano = massa_total_kg / pop_total
            per_capita_dia = per_capita_ano / 365

            col1, col2 = st.columns(2)
            with col1:
                st.metric(
                    "Geração per capita (kg/hab/ano)",
                    formatar_metric(per_capita_ano, 2),
                    help="Calculado como: Massa total de RSU (kg) / População total. Fonte: SNIS."
                )
                st.caption("📌 **Fórmula:** Massa total (kg) ÷ População total = kg/hab/ano")
                st.caption(f"📌 **Dados usados:** Massa total = {formatar_metric(massa_total_ton, 0)} t = {formatar_metric(massa_total_kg, 0)} kg; População = {formatar_metric(pop_total, 0)} hab")

            with col2:
                st.metric(
                    "Geração per capita (kg/hab/dia)",
                    formatar_metric(per_capita_dia, 3),
                    help="Calculado como: Geração anual (kg/hab/ano) / 365 dias. Fonte: SNIS."
                )
                st.caption("📌 **Fórmula:** Geração anual (kg/hab/ano) ÷ 365 = kg/hab/dia")
                st.caption(f"📌 **Cálculo:** {formatar_metric(per_capita_ano, 4)} kg/hab/ano ÷ 365 = {formatar_metric(per_capita_dia, 4)} kg/hab/dia")

        # Taxa de coleta seletiva
        if massa_total_ton > 0:
            taxa_cobertura = (massa_seletiva / massa_total_ton) * 100 if massa_total_ton > 0 else 0
            st.metric(
                "Taxa de coleta seletiva (%)",
                formatar_metric(taxa_cobertura, 2),
                help="Percentual da massa total que é coletada seletivamente. Fonte: SNIS."
            )
            st.caption("📌 **Fórmula:** (Massa coletada seletivamente ÷ Massa total de RSU) × 100")
            st.caption(f"📌 **Dados:** Massa seletiva = {formatar_metric(massa_seletiva, 0)} t; Massa total = {formatar_metric(massa_total_ton, 0)} t")

        # Ranking de maior e menor massa (inalterado)
        if "MASSA_TOTAL_RSU" in df_res_filt.columns and "MUNICIPIO" in df_res_filt.columns:
            df_rank = df_res_filt.dropna(subset=["MASSA_TOTAL_RSU"])
            if not df_rank.empty:
                maior = df_rank.loc[df_rank["MASSA_TOTAL_RSU"].idxmax()]
                menor = df_rank.loc[df_rank["MASSA_TOTAL_RSU"].idxmin()]
                col1, col2 = st.columns(2)
                col1.metric(
                    "🏆 Maior massa",
                    f"{maior['MUNICIPIO']} ({maior['UF']})",
                    f"{formatar_metric(maior['MASSA_TOTAL_RSU'], 0)} t"
                )
                col2.metric(
                    "📉 Menor massa",
                    f"{menor['MUNICIPIO']} ({menor['UF']})",
                    f"{formatar_metric(menor['MASSA_TOTAL_RSU'], 0)} t"
                )
                col1.caption(f"📌 Fonte: SNIS - município com maior massa declarada.")
                col2.caption(f"📌 Fonte: SNIS - município com menor massa declarada.")

    st.markdown("---")
    
    # Gráficos (exatamente como estavam)
    if "UF" in df_res_filt.columns:
        st.markdown("**Distribuição dos municípios por estado.** Este gráfico mostra quantos municípios estão presentes na base de dados para cada Unidade Federativa. Permite identificar a cobertura do SNIS e eventuais discrepâncias regionais.")
        uf_counts = df_res_filt["UF"].value_counts().reset_index()
        uf_counts.columns = ["UF", "Quantidade"]
        fig_uf = px.bar(uf_counts, x="UF", y="Quantidade", title="Número de municípios por UF",
                        color="Quantidade", color_continuous_scale="Blues", height=500)
        aplicar_formatacao(fig_uf)
        if fig_uf is not None:
            fig_uf.update_layout(xaxis_tickangle=45, margin=dict(l=20, r=20, t=40, b=20))
            st.plotly_chart(fig_uf, use_container_width=True)

    if "POP_TOTAL" in df_res_filt.columns:
        st.markdown("**Distribuição da população dos municípios.** O histograma agrupa os municípios por faixas de população. Ajuda a entender se a base é composta majoritariamente por municípios pequenos, médios ou grandes, influenciando a interpretação de médias per capita.")
        fig_pop = px.histogram(df_res_filt, x="POP_TOTAL", nbins=50, 
                               title="Distribuição da população dos municípios",
                               labels={"POP_TOTAL": "População"},
                               color_discrete_sequence=["#2E86C1"], height=500)
        aplicar_formatacao(fig_pop)
        if fig_pop is not None:
            st.plotly_chart(fig_pop, use_container_width=True)

    if "UF" in df_res_filt.columns and "MASSA_TOTAL_RSU" in df_res_filt.columns:
        st.markdown("**Top 10 UF com maior massa de RSU.** Agrega a massa total de resíduos sólidos urbanos declarada por município, somando por estado. Reflete tanto o tamanho da população quanto a intensidade da geração de resíduos em cada UF.")
        uf_massa = df_res_filt.groupby("UF")["MASSA_TOTAL_RSU"].sum().reset_index()
        uf_massa = uf_massa.sort_values("MASSA_TOTAL_RSU", ascending=False).head(10)
        fig_massa = px.bar(uf_massa, x="UF", y="MASSA_TOTAL_RSU", title="Top 10 UFs - Massa total de RSU",
                           labels={"MASSA_TOTAL_RSU": "Massa (t)"},
                           color="MASSA_TOTAL_RSU", color_continuous_scale="Greens", height=500)
        aplicar_formatacao(fig_massa)
        if fig_massa is not None:
            fig_massa.update_layout(xaxis_tickangle=45, margin=dict(l=20, r=20, t=40, b=20))
            st.plotly_chart(fig_massa, use_container_width=True)

# =========================================================
# TAB 2 - MUNICÍPIOS (INALTERADA)
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
            st.markdown("**Dados municipais.** Tabela interativa com as colunas selecionadas. Use-a para explorar os valores brutos de cada município, ordenar e filtrar visualmente. Os números são exibidos com separador de milhar brasileiro.")
            df_tab = df_res_filt[cols_para_exibir].copy()
            for col in df_tab.columns:
                if col not in ["MUNICIPIO", "UF", "MACRO"]:
                    df_tab[col] = df_tab[col].apply(lambda x: formatar_metric(x, 0) if pd.notna(x) else "")
            st.dataframe(df_tab, use_container_width=True, height=400, hide_index=True)

        if "POP_TOTAL" in df_res_filt.columns and "MASSA_TOTAL_RSU" in df_res_filt.columns:
            st.markdown("**População × Massa de RSU.** Cada ponto representa um município. A relação esperada é positiva (mais habitantes geram mais resíduos). Pontos muito afastados da tendência podem indicar erros de declaração ou particularidades locais.")
            fig_scatter = px.scatter(df_res_filt, x="POP_TOTAL", y="MASSA_TOTAL_RSU", 
                                     hover_data=["MUNICIPIO", "UF"],
                                     title="Relação População vs Massa de RSU",
                                     labels={"POP_TOTAL": "População", "MASSA_TOTAL_RSU": "Massa (t)"},
                                     color="UF" if "UF" in df_res_filt.columns else None, height=500)
            aplicar_formatacao(fig_scatter)
            if fig_scatter is not None:
                st.plotly_chart(fig_scatter, use_container_width=True)

# =========================================================
# TAB 3 - ROTAS DE COLETA (INALTERADA)
# =========================================================
with tab3:
    st.header("🚚 Análise das Rotas de Coleta")
    if df_col_filt is not None and not df_col_filt.empty:
        col1, col2, col3 = st.columns(3)
        col1.metric("Total de rotas", df_col_filt.shape[0])
        if "MASSA_ROTA" in df_col_filt.columns:
            col2.metric("Massa total nas rotas", f"{formatar_metric(df_col_filt['MASSA_ROTA'].sum(), 0)} t")
        if "TIPO_COLETA" in df_col_filt.columns:
            col3.metric("Tipos de coleta distintos", df_col_filt["TIPO_COLETA"].nunique())

        if "TIPO_COLETA" in df_col_filt.columns:
            st.markdown("**Frequência dos tipos de coleta.** Mostra quantas rotas são classificadas em cada categoria (ex.: coleta domiciliar, seletiva, etc.). Reflete a diversidade ou predominância de certos modelos de coleta no conjunto de dados.")
            freq = df_col_filt["TIPO_COLETA"].value_counts().reset_index()
            freq.columns = ["Tipo", "Quantidade"]
            fig_freq = px.bar(freq, x="Tipo", y="Quantidade", title="Frequência dos tipos de coleta",
                              color="Quantidade", color_continuous_scale="Viridis", height=500)
            aplicar_formatacao(fig_freq)
            if fig_freq is not None:
                fig_freq.update_layout(xaxis_tickangle=45, margin=dict(l=20, r=20, t=40, b=20))
                st.plotly_chart(fig_freq, use_container_width=True)

        if "MASSA_ROTA" in df_col_filt.columns and "TIPO_COLETA" in df_col_filt.columns:
            st.markdown("**Massa coletada por tipo de coleta.** O gráfico de rosca revela a participação de cada tipo de coleta na massa total registrada. A coleta domiciliar (convencional) costuma dominar; a fatia da coleta seletiva indica o avanço da reciclagem.")
            mass_tipo = df_col_filt.groupby("TIPO_COLETA")["MASSA_ROTA"].sum().reset_index()
            mass_tipo = mass_tipo.sort_values("MASSA_ROTA", ascending=False)
            fig_pie = px.pie(mass_tipo, values="MASSA_ROTA", names="TIPO_COLETA", 
                             title="Massa coletada por tipo de coleta", hole=0.4, height=500)
            if fig_pie is not None:
                st.plotly_chart(fig_pie, use_container_width=True)

        st.subheader("🔍 Amostra das rotas")
        st.markdown("**Amostra de 100 rotas.** Visualização parcial da tabela de rotas de coleta. Útil para inspecionar dados brutos, verificar preenchimento e consistência dos campos. Colunas numéricas são formatadas no padrão brasileiro.")
        df_amostra = df_col_filt.head(100).copy()
        for col in df_amostra.columns:
            if col not in ["COD_IBGE", "MUNICIPIO", "UF", "MACRO", "TIPO_COLETA", "TIPO_DESTINO"]:
                df_amostra[col] = df_amostra[col].apply(lambda x: formatar_metric(x, 0) if pd.notna(x) and isinstance(x, (int, float)) else x)
        st.dataframe(df_amostra, use_container_width=True, height=300, hide_index=True)

# =========================================================
# TAB 4 - DESTINAÇÃO (INALTERADA)
# =========================================================
with tab4:
    st.header("♻️ Análise da Destinação dos Resíduos")
    
    excluir_transbordo = st.checkbox(
        "Excluir rotas de transbordo da análise (recomendado para evitar dupla contagem)", 
        value=True
    )

    df_destino = df_col_filt.copy()
    if excluir_transbordo:
        if "TIPO_DESTINO" in df_destino.columns:
            df_destino['destino_norm'] = df_destino['TIPO_DESTINO'].astype(str).apply(
                lambda x: unicodedata.normalize('NFKD', x).encode('ASCII', 'ignore').decode('utf-8').upper().strip()
                if pd.notna(x) else ''
            )
            df_destino = df_destino[~df_destino['destino_norm'].str.contains('TRANSBORDO', na=False)]
            df_destino = df_destino.drop(columns=['destino_norm'])
        else:
            st.warning("Coluna 'TIPO_DESTINO' não encontrada.")

    if df_destino is not None and not df_destino.empty:
        if "TIPO_DESTINO" in df_destino.columns:
            destinos = df_destino["TIPO_DESTINO"].value_counts().reset_index()
            destinos.columns = ["Destino", "Quantidade"]
            if "MASSA_ROTA" in df_destino.columns:
                st.markdown("**Massa destinada por tipo de destino.** Exibe a quantidade de resíduos (em toneladas) encaminhada para cada tipo de unidade (aterro, lixão, reciclagem, etc.). A exclusão de transbordos evita que a mesma carga seja contada múltiplas vezes.")
                mass_dest = df_destino.groupby("TIPO_DESTINO")["MASSA_ROTA"].sum().reset_index()
                mass_dest = mass_dest.sort_values("MASSA_ROTA", ascending=False)
                fig_dest = px.bar(mass_dest, x="TIPO_DESTINO", y="MASSA_ROTA", 
                                  title="Massa destinada por tipo (dados de coleta)",
                                  labels={"MASSA_ROTA": "Massa (t)"},
                                  color="MASSA_ROTA", color_continuous_scale="Viridis", height=500)
                aplicar_formatacao(fig_dest)
                if fig_dest is not None:
                    fig_dest.update_layout(xaxis_tickangle=45, margin=dict(l=20, r=20, t=40, b=20))
                    st.plotly_chart(fig_dest, use_container_width=True)
                
                st.markdown("**Percentual da massa destinada por tipo.** Este gráfico mostra a distribuição percentual da massa total encaminhada para cada destino. Facilita a comparação relativa entre as diferentes formas de destinação, independentemente do volume absoluto.")
                mass_dest['Percentual'] = (mass_dest['MASSA_ROTA'] / mass_dest['MASSA_ROTA'].sum()) * 100
                fig_perc = px.bar(mass_dest, x="TIPO_DESTINO", y="Percentual",
                                  title="Percentual da massa destinada por tipo",
                                  labels={"Percentual": "Percentual (%)", "TIPO_DESTINO": "Tipo de Destino"},
                                  color="Percentual", color_continuous_scale="Viridis", height=500)
                if fig_perc is not None:
                    fig_perc.update_layout(yaxis_tickformat='.1f')
                    fig_perc.update_layout(xaxis_tickangle=45, margin=dict(l=20, r=20, t=40, b=20))
                    st.plotly_chart(fig_perc, use_container_width=True)
            else:
                fig_dest = px.pie(destinos, values="Quantidade", names="Destino",
                                  title="Distribuição dos tipos de destino (contagem de rotas)", height=500)
                if fig_dest is not None:
                    st.plotly_chart(fig_dest, use_container_width=True)

        st.subheader("📊 Distribuição da Massa por Estado")
        
        if "MASSA_ROTA" in df_destino.columns:
            uf_mass = df_destino.groupby("UF")["MASSA_ROTA"].sum().reset_index()
        else:
            uf_mass = pd.DataFrame()
        
        if uf_mass.empty or uf_mass["MASSA_ROTA"].sum() == 0:
            if "MASSA_TOTAL_RSU" in df_res_filt.columns and "UF" in df_res_filt.columns:
                uf_mass = df_res_filt.groupby("UF")["MASSA_TOTAL_RSU"].sum().reset_index()
                uf_mass.columns = ["UF", "MASSA_ROTA"]
                st.info("📊 Exibindo massa total de RSU (dados da tabela de resíduos, pois 'MASSA_ROTA' não tem dados suficientes)")
            else:
                uf_mass = pd.DataFrame()
        
        if not uf_mass.empty:
            uf_mass = uf_mass.dropna(subset=["UF", "MASSA_ROTA"])
            uf_mass = uf_mass[uf_mass["MASSA_ROTA"] > 0]
            if not uf_mass.empty:
                st.markdown("**Massa coletada por estado (destinação).** Agregação da massa por UF, permitindo comparar o volume total de resíduos que chega aos destinos finais em cada estado. Pode diferir dos totais da aba Visão Geral quando se usam fontes de dados distintas (tabela de resíduos vs. coleta).")
                fig_bar = px.bar(
                    uf_mass.sort_values("MASSA_ROTA", ascending=False),
                    x="UF",
                    y="MASSA_ROTA",
                    title="Massa coletada por estado",
                    labels={"MASSA_ROTA": "Massa (t)"},
                    color="MASSA_ROTA",
                    color_continuous_scale="Viridis",
                    height=500
                )
                aplicar_formatacao(fig_bar)
                if fig_bar is not None:
                    fig_bar.update_layout(margin=dict(l=20, r=20, t=40, b=20))
                    st.plotly_chart(fig_bar, use_container_width=True)
            else:
                st.info("Todos os valores de massa são zero ou nulos. Não há dados para exibir.")
        else:
            st.warning("Não foi possível encontrar uma coluna de massa para a análise.")
    else:
        st.info("Nenhum dado disponível para a análise de destinação.")

# =========================================================
# TAB 5 - COMPARAÇÃO 2023 vs 2024 (INALTERADA)
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
    
    if not np.isnan(massas["2023"]) and not np.isnan(massas["2024"]) and massas["2023"] > 0:
        var_massa = ((massas["2024"] - massas["2023"]) / massas["2023"]) * 100
        st.metric(
            "Variação da massa total",
            f"{formatar_metric(var_massa, 2)}%",
            help="Calculado como: ((Massa 2024 - Massa 2023) / Massa 2023) × 100"
        )
        st.caption("📌 **Fórmula:** (Massa 2024 - Massa 2023) ÷ Massa 2023 × 100")
        st.caption(f"📌 **Dados:** 2023 = {formatar_metric(massas['2023'], 0)} t; 2024 = {formatar_metric(massas['2024'], 0)} t")
    
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**Massa total de RSU por ano.** Comparação direta da soma nacional (ou filtrada) da massa de resíduos. A variação pode refletir mudanças populacionais, econômicas ou de cobertura da base de dados.")
        fig_massa = px.bar(x=list(massas.keys()), y=list(massas.values()),
                           title="Massa total de RSU (t)",
                           labels={"x": "Ano", "y": "Massa (t)"},
                           color=list(massas.keys()),
                           color_discrete_sequence=["#1f77b4", "#ff7f0e"],
                           height=500)
        aplicar_formatacao(fig_massa)
        if fig_massa is not None:
            st.plotly_chart(fig_massa, use_container_width=True)

    with col2:
        st.markdown("**População total por ano.** Evolução do somatório da população dos municípios da base. Alterações podem decorrer de crescimento vegetativo, migração ou simplesmente de diferenças na quantidade de municípios declarantes entre os anos.")
        fig_pop = px.bar(x=list(pops.keys()), y=list(pops.values()),
                         title="População total",
                         labels={"x": "Ano", "y": "População"},
                         color=list(pops.keys()),
                         color_discrete_sequence=["#2ca02c", "#d62728"],
                         height=500)
        aplicar_formatacao(fig_pop)
        if fig_pop is not None:
            st.plotly_chart(fig_pop, use_container_width=True)
    
    if "TIPO_COLETA" in df_col_2023.columns and "TIPO_COLETA" in df_col_2024.columns:
        st.subheader("📋 Evolução dos Tipos de Coleta")
        st.markdown("**Comparação da quantidade de rotas por tipo entre 2023 e 2024.** Permite identificar mudanças na estrutura de coleta, como aumento de rotas seletivas ou alterações na classificação dos serviços.")
        freq_2023 = df_col_2023["TIPO_COLETA"].value_counts().reset_index()
        freq_2023.columns = ["Tipo", "2023"]
        freq_2024 = df_col_2024["TIPO_COLETA"].value_counts().reset_index()
        freq_2024.columns = ["Tipo", "2024"]
        freq_comp = pd.merge(freq_2023, freq_2024, on="Tipo", how="outer").fillna(0)
        fig_comp = go.Figure()
        fig_comp.add_trace(go.Bar(x=freq_comp["Tipo"], y=freq_comp["2023"], name="2023", marker_color="#1f77b4"))
        fig_comp.add_trace(go.Bar(x=freq_comp["Tipo"], y=freq_comp["2024"], name="2024", marker_color="#ff7f0e"))
        fig_comp.update_layout(title="Comparação de tipos de coleta", xaxis_tickangle=45, barmode="group",
                               height=500, margin=dict(l=20, r=20, t=40, b=20))
        aplicar_formatacao(fig_comp)
        st.plotly_chart(fig_comp, use_container_width=True)

# =========================================================
# RODAPÉ - METODOLOGIA E FONTES
# =========================================================
st.markdown("---")
st.subheader("📌 Metodologia e Fontes para Auditoria")
st.markdown("""
- **Fonte dos dados:** SNIS (Sistema Nacional de Informações sobre Saneamento) – Módulo Manejo de Resíduos Sólidos, anos 2023 e 2024.  
- **Período de referência:** Dados anuais declarados pelos municípios.  
- **Indicadores calculados:**  
  - **Geração per capita (kg/hab/ano):** Massa total de RSU (convertida para kg) ÷ População total.  
  - **Geração per capita (kg/hab/dia):** Geração per capita anual ÷ 365 dias.  
  - **Taxa de coleta seletiva (%):** (Massa de resíduos coletada seletivamente ÷ Massa total de RSU) × 100.  
  - **Variação da massa total:** ((Massa 2024 - Massa 2023) ÷ Massa 2023) × 100.  
- **Transbordos:** Por padrão, rotas com destino "Transbordo" são excluídas para evitar dupla contagem. O usuário pode optar por incluí-las via checkbox.  
- **Conversões:** Massas em toneladas são convertidas para kg para o cálculo per capita (1 t = 1000 kg).  
- **Arredondamentos:** Valores exibidos com duas casas decimais, exceto per capita diária (três casas) para melhor precisão.
""")
st.caption(f"📅 Dados do SNIS - {ano_base} | Desenvolvido com Streamlit e Plotly | Arquivos locais.")
