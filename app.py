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
Este aplicativo interpreta os **tipos de coleta executada** e o **destino final** informados pelos municípios
e avalia o **potencial técnico para compostagem e vermicompostagem**
de resíduos sólidos urbanos, com foco em **para onde o resíduo está indo**.
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
# FUNÇÕES DE COTAÇÃO AUTOMÁTICA DO CARBONO E CÂMBIO (mantidas iguais)
# =============================================================================
# ... (todo o bloco de funções de cotação e formatação permanece idêntico) ...
# Incluo aqui as funções obter_cotacao_carbono_investing, obter_cotacao_carbono,
# obter_cotacao_euro_real, calcular_valor_creditos, formatar_br, br_format,
# formatar_numero_br, formatar_massa_br, normalizar_texto, classificar_tipo_aterro.
# (Vou omitir o texto completo por brevidade, mas você deve manter todo o código existente)
# =============================================================================

# ------------------------- COLE AQUI TODAS AS FUNÇÕES DE COTAÇÃO E FORMATAÇÃO ORIGINAIS -------------------------
# (mantenha exatamente como estava no script anterior, sem alterações)

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

# =========================================================
# Classificação de coleta (ATUALIZADA com compostagem/vermicompostagem)
# =========================================================
def classificar_coleta(texto):
    if pd.isna(texto):
        return ("Não informado", False, False, "Tipo não informado")
    t = str(texto).lower()
    # ATENÇÃO: "compostagem" e "vermicompostagem" inseridas antes de "orgânica"
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
# PARÂMETROS PARA CÁLCULO (mantidos iguais)
# =========================================================
# ... (todo o bloco de parâmetros T_ORGANICO, DOC_ORGANICO, etc. permanece o mesmo)
# =========================================================

# --------------------------------------------------------
# Inclua aqui TODOS os parâmetros T_ORGANICO, DOC_ORGANICO, k_ano_ORGANICO, etc.
# e as funções de cálculo de emissões (calcular_emissoes_aterro_entrada_continua,
# calcular_ch4_total_aterro_20anos, calcular_emissoes_...).
# NENHUMA ALTERAÇÃO nessa parte. Apenas certifique-se de que estão presentes.
# =========================================================

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
# Limpeza
# =========================================================
df_clean = df.dropna(subset=[COL_MUNICIPIO])
df_clean[COL_MUNICIPIO] = df_clean[COL_MUNICIPIO].astype(str).str.strip()

# =========================================================
# Interface: seleção de município
# =========================================================
municipios = ["BRASIL – Todos os municípios"] + sorted(df_clean[COL_MUNICIPIO].unique())
municipio = st.selectbox("Selecione o município:", municipios)

df_mun = df_clean.copy() if municipio == municipios[0] else df_clean[df_clean[COL_MUNICIPIO] == municipio]
st.subheader(f"🇧🇷 Brasil — Síntese Nacional de RSU ({ano_selecionado})" if municipio == municipios[0] else f"📍 {municipio} - Ano {ano_selecionado}")

# =========================================================
# 🔄 NOVA SEÇÃO PRINCIPAL: Destinação final dos resíduos coletados
# =========================================================
st.markdown("---")
st.subheader("🗺️ Para onde o resíduo está indo? (Destinação Final)")

# Coluna de massa numérica
df_mun["MASSA_FLOAT"] = pd.to_numeric(df_mun[COL_MASSA], errors="coerce").fillna(0)

# Agrupar por destino
destinacao = df_mun.groupby(COL_DESTINO).agg(
    Massa_Total=("MASSA_FLOAT", "sum")
).reset_index()
destinacao = destinacao.sort_values("Massa_Total", ascending=False)

# Para cada destino, calcular a massa potencial (apta para compostagem/vermi)
def calcular_massa_potencial_por_destino(destino):
    mask = (df_mun[COL_DESTINO] == destino)
    if not mask.any():
        return 0.0, 0.0
    subset = df_mun[mask]
    comp = subset[subset[COL_TIPO_COLETA].apply(
        lambda x: classificar_coleta(x)[1] if pd.notna(x) else False)].MASSA_FLOAT.sum()
    vermi = subset[subset[COL_TIPO_COLETA].apply(
        lambda x: classificar_coleta(x)[2] if pd.notna(x) else False)].MASSA_FLOAT.sum()
    return comp, vermi

massas_pot = destinacao[COL_DESTINO].apply(calcular_massa_potencial_por_destino)
destinacao["Massa_Potencial_Compostagem"] = massas_pot.apply(lambda x: x[0])
destinacao["Massa_Potencial_Vermicompostagem"] = massas_pot.apply(lambda x: x[1])

# Indicador se o destino já é tratamento biológico
def ja_eh_tratamento(destino):
    d = str(destino).lower()
    return "compostagem" in d or "vermicompostagem" in d

destinacao["Ja_Biologico"] = destinacao[COL_DESTINO].apply(ja_eh_tratamento)

# Formatar para exibição
df_view = destinacao.copy()
df_view["Massa Total (t)"] = df_view["Massa_Total"].apply(formatar_numero_br)
df_view["Potencial Compostagem (t)"] = df_view["Massa_Potencial_Compostagem"].apply(formatar_massa_br)
df_view["Potencial Vermi (t)"] = df_view["Massa_Potencial_Vermicompostagem"].apply(formatar_massa_br)
df_view["Já é Tratamento Biológico?"] = df_view["Ja_Biologico"].apply(lambda x: "✅ Sim" if x else "❌ Não")

st.dataframe(
    df_view[[COL_DESTINO, "Massa Total (t)", "Potencial Compostagem (t)",
             "Potencial Vermi (t)", "Já é Tratamento Biológico?"]],
    use_container_width=True
)

# =========================================================
# 💡 Potencial total de desvio (apenas para destinos não biológicos)
# =========================================================
mascara_nao_biologico = ~destinacao["Ja_Biologico"]
total_massa_desviavel = destinacao.loc[mascara_nao_biologico, "Massa_Total"].sum()
total_comp_desviavel = destinacao.loc[mascara_nao_biologico, "Massa_Potencial_Compostagem"].sum()
total_vermi_desviavel = destinacao.loc[mascara_nao_biologico, "Massa_Potencial_Vermicompostagem"].sum()

st.markdown("---")
st.subheader("📦 Potencial de Desvio para Tratamento Biológico")
col1, col2, col3 = st.columns(3)
with col1:
    st.metric("Massa total em destinos não biológicos", formatar_massa_br(total_massa_desviavel))
with col2:
    st.metric("Massa que poderia ser compostada", formatar_massa_br(total_comp_desviavel))
with col3:
    st.metric("Massa que poderia ser vermicompostada", formatar_massa_br(total_vermi_desviavel))

# =========================================================
# 🌱 Cálculo de emissões evitadas (toda a massa potencial desviada)
# =========================================================
# Vamos classificar cada registro potencial em "organico" ou "podas" conforme o tipo de coleta
def classificar_tipo_organico(texto):
    if pd.isna(texto):
        return "organico"  # default
    t = str(texto).lower()
    if any(p in t for p in ["poda", "galhada", "verde"]):
        return "podas"
    return "organico"

# Filtrar apenas registros com potencial e destino não biológico
df_potencial = df_mun[mascara_nao_biologico & (
    df_mun[COL_TIPO_COLETA].apply(lambda x: classificar_coleta(x)[1] if pd.notna(x) else False)
)].copy()
if not df_potencial.empty:
    df_potencial["tipo_organico"] = df_potencial[COL_TIPO_COLETA].apply(classificar_tipo_organico)
    # Para cada registro, calcular emissões (aterro vs compostagem e vs vermicompostagem)
    # Precisamos do MCF individual de cada registro, baseado no destino real
    df_potencial["MCF"] = df_potencial[COL_DESTINO].apply(
        lambda d: determinar_mcf_por_destino(d, df_potencial.loc[df_potencial[COL_DESTINO]==d, "tipo_organico"].values[0] if len(df_potencial.loc[df_potencial[COL_DESTINO]==d])>0 else 'organico')
    )
    # Corrigir: determinar MCF conhecendo o tipo_organico do próprio registro
    df_potencial["MCF"] = df_potencial.apply(
        lambda row: determinar_mcf_por_destino(row[COL_DESTINO], row["tipo_organico"]), axis=1
    )

    # Inicializar totais
    co2eq_aterro_total = 0.0
    co2eq_evitado_comp_total = 0.0
    co2eq_evitado_vermi_total = 0.0
    massa_total_desviada = 0.0

    resultados_detalhados = []
    for _, row in df_potencial.iterrows():
        massa_t = row["MASSA_FLOAT"]
        mcf = row["MCF"]
        tipo = row["tipo_organico"]
        if massa_t <= 0 or mcf <= 0:
            continue
        res = calcular_emissoes_totais_entrada_continua(massa_t, mcf, tipo)
        co2eq_aterro_total += res['co2eq_aterro_total']
        co2eq_evitado_comp_total += res['co2eq_evitado_compostagem']
        co2eq_evitado_vermi_total += res['co2eq_evitado_vermicompostagem']
        massa_total_desviada += massa_t
        resultados_detalhados.append({
            "Destino": row[COL_DESTINO],
            "Tipo de coleta": row[COL_TIPO_COLETA],
            "Massa (t)": formatar_massa_br(massa_t),
            "Tipo": tipo.capitalize(),
            "MCF": formatar_numero_br(mcf, 2),
            "Linha de Base (tCO₂e)": formatar_numero_br(res['co2eq_aterro_total'], 1),
            "Evitado Compostagem (tCO₂e)": formatar_numero_br(res['co2eq_evitado_compostagem'], 1),
            "Evitado Vermicompostagem (tCO₂e)": formatar_numero_br(res['co2eq_evitado_vermicompostagem'], 1),
        })

    st.markdown("---")
    st.subheader("📊 Projeção de Emissões Evitadas – Todo o Potencial Desviado (20 anos)")
    st.markdown(f"""
    Abaixo, a soma de todos os registros com potencial de tratamento biológico
    que **hoje são destinados a locais inadequados** (aterros, lixões, etc.).
    A projeção considera entrada contínua da massa atual durante {ANOS_PROJECAO_CREDITOS} anos
    e o decaimento acumulado no aterro, conforme IPCC 2006.
    """)

    col_a, col_b, col_c, col_d = st.columns(4)
    with col_a:
        st.metric("Massa total desviável (t/ano)", formatar_massa_br(massa_total_desviada))
    with col_b:
        st.metric("Linha de base total (tCO₂e)", formatar_numero_br(co2eq_aterro_total, 1))
    with col_c:
        st.metric("Evitado com Compostagem", formatar_numero_br(co2eq_evitado_comp_total, 1) + " tCO₂e")
    with col_d:
        st.metric("Evitado com Vermicompostagem", formatar_numero_br(co2eq_evitado_vermi_total, 1) + " tCO₂e")

    # Tabela detalhada (opcional, pode expandir)
    with st.expander("🔍 Detalhamento por destino e tipo de coleta"):
        st.dataframe(pd.DataFrame(resultados_detalhados), use_container_width=True)

    # Gráfico de emissões acumuladas (agregado)
    # ... (pode ser adicionado posteriormente)
else:
    st.info("✅ Nenhum resíduo com potencial de tratamento biológico está sendo destinado a locais inadequados.")

# =========================================================
# Mantenho as seções existentes de orgânicos e podas como análises complementares
# =========================================================
st.markdown("---")
st.subheader("🔎 Análises Específicas por Tipo de Resíduo")
# (Aqui você pode colocar as seções de "Destinação da Coleta Seletiva de Resíduos Orgânicos" 
#  e "Destinação das Podas e Galhadas" exatamente como estavam, sem alterações.)

# =========================================================
# Rodapé
# =========================================================
st.markdown("---")
st.caption(f"""
Fonte: SNIS – Sistema Nacional de Informações sobre Saneamento (ano {ano_selecionado}) | 
Metodologia: IPCC 2006, Yang et al. (2017) - Parâmetros ajustados por tipo de resíduo | 
Cotações atualizadas automaticamente via Investing.com e APIs de câmbio | 
Projeção de créditos de carbono: 20 anos com entrada contínua e decaimento acumulado | 
**RESÍDUOS ORGÂNICOS:** k = {k_ano_ORGANICO} ano⁻¹, DOC = {DOC_ORGANICO}, TOC = {TOC_YANG_ORGANICO} | 
**PODAS E GALHADAS:** k = {k_ano_PODAS} ano⁻¹, DOC = {DOC_PODAS}, TOC = {TOC_YANG_PODAS} |
**⚠️ APENAS CH₄:** Este cálculo considera somente emissões de metano (CH₄), não incluindo N₂O
""")
