# =========================================================
# RSU BRASIL — MONITORAMENTO DA GESTÃO DE RESÍDUOS SÓLIDOS URBANOS
# Subsídio ao Ministério do Meio Ambiente (MMA) — PNRS / PLANARES / SINISA
# v2.5 — abas reordenadas por impacto + bloco comparativo dos dois indicadores
# =========================================================
from pathlib import Path
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# ---------------------------------------------------------
# CONFIGURAÇÃO
# ---------------------------------------------------------
st.set_page_config(
    page_title="RSU Brasil — Monitoramento (MMA)",
    page_icon="♻️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------
# CONSTANTES
# ---------------------------------------------------------
ANOS = ["2023", "2024"]
ARQUIVOS = {"2023": "rsuBrasil_2023.xlsx", "2024": "rsuBrasil_2024.xlsx"}
ABAS = {
    "residuos":     "Manejo_Resíduos_Sólidos_Urbanos",
    "coleta":       "Manejo_Coleta_e_Destinação",
    "veiculos":     "Manejo_Veículos",
    "cooperativas": "Manejo_Cooperativas",
}
DESTINO_ADEQUADO = {
    "Aterro sanitário",
    "Unidade de compostagem",
    "Unidade de triagem (galpão ou usina)",
    "Unidade de coprocessamento",
    "Unidade de manejo de resíduos de áreas verdes (galhadas e podas)",
    "Área de Transbordo e Triagem de resíduos da construção civil e volumosos (ATT)",
    "Aterro de inertes",
}
DESTINO_INADEQUADO = {"Aterro controlado", "Lixão ou vazadouro"}
DESTINO_NEUTRO    = {"Unidade de Transbordo"}
CORES_REGIAO = {
    "Norte": "#1f9e89", "Nordeste": "#f39c12",
    "Centro-Oeste": "#8e44ad", "Sudeste": "#2980b9", "Sul": "#27ae60",
}

# ---------------------------------------------------------
# HELPERS
# ---------------------------------------------------------
def _resolver_caminho(nome):
    for p in [Path(nome), Path("data") / nome, Path("dados") / nome]:
        if p.exists(): return str(p)
    return None

def _limpar_colunas(df):
    cols = []
    for i, c in enumerate(df.columns):
        cols.append(str(c).strip() if not pd.isna(c) else f"_col_{i}")
    df.columns = cols
    return df

def fmt_br(x, casas=0):
    if pd.isna(x) or x is None: return "–"
    try: x = float(x)
    except (ValueError, TypeError): return str(x)
    if casas == 0:
        return f"{x:,.0f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{x:,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")

def to_num(s): return pd.to_numeric(s, errors="coerce")

def classificar_destino(tipo):
    if pd.isna(tipo): return "Não informado"
    t = str(tipo).strip()
    if t in DESTINO_ADEQUADO:   return "Adequado"
    if t in DESTINO_INADEQUADO: return "Inadequado"
    if t in DESTINO_NEUTRO:     return "Transbordo"
    tl = t.lower()
    if "aterro sanitário" in tl: return "Adequado"
    if "lixão" in tl or "vazadouro" in tl: return "Inadequado"
    if "controlado" in tl: return "Inadequado"
    if "compostagem" in tl: return "Adequado"
    if "triagem" in tl: return "Adequado"
    return "Outros"

def filtrar_transbordo(df, excluir):
    """Remove rotas cujo destino é 'Unidade de Transbordo'."""
    if not excluir or df is None or df.empty:
        return df
    if "UNIDADE_DEST" not in df.columns:
        return df
    mask = df["UNIDADE_DEST"].astype(str).str.contains(
        "Transbordo", case=False, na=False, regex=False
    )
    return df[~mask].copy()

# ---------------------------------------------------------
# AVISO DINÂMICO DENTRO DE CADA ABA
# ---------------------------------------------------------
def aviso_filtro_transbordo(afetada, motivo_nao_afeta=None):
    if afetada:
        if excluir_transbordo:
            st.success(
                "🚫 **Filtro 'Excluir transbordo' ATIVO** — "
                "as métricas desta aba **não incluem** rotas cujo destino é "
                "'Unidade de Transbordo'. Sem dupla contagem."
            )
        else:
            st.info(
                "ℹ️ **Filtro 'Excluir transbordo' INATIVO** — "
                "rotas para 'Unidade de Transbordo' **estão sendo contadas** "
                "nesta aba. Ative o filtro acima para evitar dupla contagem."
            )
    else:
        st.caption(
            f"⚪ O filtro 'Excluir transbordo' **não se aplica** a esta aba. "
            f"{motivo_nao_afeta or ''}"
        )

# ---------------------------------------------------------
# CARREGAMENTO
# ---------------------------------------------------------
@st.cache_data(show_spinner="Carregando dados do SINISA...")
def carregar_ano(ano):
    caminho = _resolver_caminho(ARQUIVOS[ano])
    if caminho is None: return None
    dfs = {}
    for chave, aba in ABAS.items():
        try:
            df = pd.read_excel(caminho, sheet_name=aba, header=12)
            dfs[chave] = _limpar_colunas(df)
        except Exception as e:
            st.warning(f"⚠️ Erro na aba {aba} ({ano}): {e}")
            dfs[chave] = pd.DataFrame()
    return dfs

@st.cache_data(show_spinner="Consolidando dados municipais...")
def consolidar_ano(ano):
    dfs = carregar_ano(ano)
    if dfs is None: return None
    dr = dfs["residuos"].copy(); dc = dfs["coleta"].copy()
    dv = dfs["veiculos"].copy(); dk = dfs["cooperativas"].copy()

    if not dr.empty:
        dr = dr.rename(columns={
            "Cod_IBGE":"COD_IBGE","Nom_Mun":"MUNICIPIO","UF":"UF","Nom_Região":"REGIAO",
            "DFE0001":"POP_TOTAL","DFE0002":"POP_URBANA","DFE0003":"POP_RURAL",
            "OGM4006":"DOM_TOTAL","OGM4004":"DOM_URB","OGM4005":"DOM_RURAL","OGM0005":"AREA_KM2",
            "GTR1025":"MASSA_DOMICILIAR","GTR1026":"MASSA_SELETIVA","GTR1027":"MASSA_LIMPEZA",
            "GTR1028":"MASSA_TOTAL","GTR1029":"MASSA_RECUPERADA","GTR1207":"N_VEICULOS",
            "GTR1309*":"N_COOP","GTR1310":"CATADORES_ORG","GTR1311":"CATADORES_INFO",
            "GTR1500*":"ESTUDO_CARACT",
        })
        for c in ["POP_TOTAL","POP_URBANA","POP_RURAL","DOM_TOTAL","AREA_KM2",
                  "MASSA_DOMICILIAR","MASSA_SELETIVA","MASSA_LIMPEZA","MASSA_TOTAL",
                  "MASSA_RECUPERADA","N_VEICULOS","N_COOP","CATADORES_ORG","CATADORES_INFO"]:
            if c in dr.columns: dr[c] = to_num(dr[c])
        dr["ANO"] = ano

    if not dc.empty:
        dc = dc.rename(columns={
            "Cod_IBGE":"COD_IBGE","Nom_Mun":"MUNICIPIO","UF":"UF","Nom_Região":"REGIAO",
            "GTR1000":"COD_ROTA","GTR1001*":"TIPO_COLETA","GTR1002*":"ABRANGENCIA",
            "GTR1003*":"EXECUTOR","GTR1004*":"MASSA_PUBLICA","GTR1005*":"MASSA_PRIVADA",
            "GTR1006*":"MASSA_COOP_CONTR","GTR1007*":"MASSA_COOP_NAO","GTR1008":"MASSA_ROTA",
            "Cod_IBGE_Mun_Dest":"COD_IBGE_DEST","GTR1010*":"MUN_DEST","GTR1011*":"UNIDADE_DEST",
            "GTR1012*":"EXEC_DEST","GTR1013*":"NOME_UNIDADE","GTR1017":"CARACT_SERVICO",
            "GTR1018":"PAPEL_RECUP","GTR1019":"PLASTICO_RECUP","GTR1020":"METAL_RECUP",
            "GTR1021":"VIDRO_RECUP","GTR1022":"OUTROS_RECUP","GTR1023*":"TOTAL_RECUP",
            "GTR1024":"REJEITOS",
        })
        for cand in ["Fluxo de resíduos",
                     "Na rota declarada os resíduos são enviados para outro município?"]:
            if cand in dc.columns:
                dc = dc.rename(columns={cand: "ENVIADO_OUTRO"}); break
        for c in ["MASSA_PUBLICA","MASSA_PRIVADA","MASSA_COOP_CONTR","MASSA_COOP_NAO",
                  "MASSA_ROTA","PAPEL_RECUP","PLASTICO_RECUP","METAL_RECUP","VIDRO_RECUP",
                  "OUTROS_RECUP","TOTAL_RECUP","REJEITOS"]:
            if c in dc.columns: dc[c] = to_num(dc[c])
        dc["CATEGORIA"] = (dc["UNIDADE_DEST"].apply(classificar_destino)
                           if "UNIDADE_DEST" in dc.columns else "Não informado")
        dc["ANO"] = ano

    if not dv.empty:
        dv = dv.rename(columns={
            "Cod_IBGE":"COD_IBGE","Nom_Mun":"MUNICIPIO","UF":"UF",
            "GTR1201*":"TIPO_VEICULO","GTR1202*":"FAIXA_IDADE",
            "GTR1203*":"PROPRIETARIO","GTR1204*":"QTD",
        })
        if "QTD" in dv.columns: dv["QTD"] = to_num(dv["QTD"])
        dv["ANO"] = ano

    if not dk.empty:
        dk = dk.rename(columns={
            "Cod_IBGE":"COD_IBGE","Nom_Mun":"MUNICIPIO","UF":"UF",
            "GTR1300":"COD_COOP","GTR1302*":"NOME_COOP","GTR1303*":"SERVICOS",
            "GTR1304*":"VINCULO","GTR1305":"REMUNERACAO","GTR1306*":"N_TRIAGEM",
            "GTR1307*":"N_TOTAL","GTR1308":"CNPJ_COOP",
        })
        for c in ["REMUNERACAO","N_TRIAGEM","N_TOTAL"]:
            if c in dk.columns: dk[c] = to_num(dk[c])
        dk["ANO"] = ano

    return {"residuos": dr, "coleta": dc, "veiculos": dv, "cooperativas": dk}

# ---------------------------------------------------------
# CARREGAR
# ---------------------------------------------------------
dados = {a: consolidar_ano(a) for a in ANOS}
dados = {a: d for a, d in dados.items() if d is not None}
if not dados:
    st.error("❌ Nenhum arquivo Excel encontrado. Coloque `rsuBrasil_2023.xlsx` e "
             "`rsuBrasil_2024.xlsx` na raiz do repositório (ou em `data/`).")
    st.stop()
ANOS_DISP = list(dados.keys())

# ---------------------------------------------------------
# HEADER
# ---------------------------------------------------------
st.title("♻️ RSU Brasil — Monitoramento da Gestão de Resíduos Sólidos Urbanos")
st.markdown("""
Painel de **monitoramento** dos RSU brasileiros, com base nos microdados do **SINISA**.
Subsidia o acompanhamento da **PNRS (Lei 12.305/2010)**, do **PLANARES (Decreto 11.043/2022)**
e das metas de universalização e recuperação.
""")

# ---------------------------------------------------------
# FILTROS DA SIDEBAR
# ---------------------------------------------------------
st.sidebar.header("⚙️ Filtros globais")
ano_sel = st.sidebar.selectbox("Ano de referência:", ANOS_DISP, index=len(ANOS_DISP)-1)
ano_comp = st.sidebar.selectbox("Comparar com:",
    ["—"] + [a for a in ANOS_DISP if a != ano_sel])
uf_sel = st.sidebar.selectbox("Estado (UF):",
    ["BRASIL – Todos"] + sorted(dados[ano_sel]["residuos"]["UF"].dropna().unique().tolist()))
reg_sel = st.sidebar.selectbox("Região:",
    ["Todas"] + sorted(dados[ano_sel]["residuos"]["REGIAO"].dropna().unique().tolist()))

def filtrar(df, col_uf="UF", col_reg="REGIAO"):
    if df.empty: return df
    if uf_sel != "BRASIL – Todos" and col_uf in df.columns:
        df = df[df[col_uf] == uf_sel]
    if reg_sel != "Todas" and col_reg in df.columns:
        df = df[df[col_reg] == reg_sel]
    return df

dr = filtrar(dados[ano_sel]["residuos"])
dc = filtrar(dados[ano_sel]["coleta"])

# =========================================================
# 🌐 FILTRO GLOBAL — ANTES DAS ABAS
# =========================================================
with st.container(border=True):
    c1, c2 = st.columns([1, 2.2])
    with c1:
        st.markdown("### 🚫 Filtro de rotas")
        excluir_transbordo = st.checkbox(
            "**Excluir transbordo** (aplica-se a todas as abas)",
            value=False,
            key="exc_tb_global",
        )
    with c2:
        st.markdown("**O que este filtro faz?**")
        st.markdown(
            "Remove rotas cujo destino final é **'Unidade de Transbordo'**.\n\n"
            "**Por que é importante:** o transbordo **não é** destinação final — é uma "
            "estação de transferência. O SINISA registra a rota *'município → transbordo'* "
            "e a rota *'transbordo → aterro'* **separadamente**. Se você incluir transbordo "
            "no cômputo de destinação final, **a massa é contada duas vezes**."
        )
        st.markdown(
            "**🟢 Abas afetadas:** Painel Nacional · Coleta e Cobertura · "
            "Destinação Final · Recuperação de Materiais  \n"
            "**⚪ Abas não afetadas:** Análise Territorial · Inclusão Socioprodutiva"
        )

# =========================================================
# ABAS — REORDENADAS: afetadas primeiro, não-afetadas depois
# =========================================================
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "🇧🇷 Painel Nacional 🟢",
    "🚛 Coleta e Cobertura 🟢",
    "🏭 Destinação Final 🟢",
    "♻️ Recuperação de Materiais 🟢",
    "🗺️ Análise Territorial ⚪",
    "👥 Inclusão Socioprodutiva ⚪",
])

st.caption(
    "🟢 = abas influenciadas pelo filtro 'Excluir transbordo'  ·  "
    "⚪ = abas que **não** sofrem impacto do filtro"
)

# ---------------------------------------------------------
# TAB 1 — PAINEL NACIONAL
# ---------------------------------------------------------
with tab1:
    st.subheader(f"Painel Nacional — SINISA {ano_sel}")
    aviso_filtro_transbordo(afetada=True)

    dc_tab = filtrar_transbordo(dc, excluir_transbordo)

    # ---------- Números de referência (SINISA — invariantes) ----------
    pop_total   = dr["POP_TOTAL"].sum()
    massa_total = dr["MASSA_TOTAL"].sum()             # GTR1028 (aba resíduos)
    massa_recup = dr["MASSA_RECUPERADA"].sum()
    n_mun       = dr["COD_IBGE"].nunique()
    n_coop      = dr["N_COOP"].sum()
    per_cap     = (massa_total / pop_total * 1000) if pop_total > 0 else 0
    per_cap_dia = per_cap / 365
    taxa_recup  = (massa_recup / massa_total * 100) if massa_total > 0 else 0

    # ---------- Números de rota (MUDAM com o filtro) ----------
    massa_rota_bruta  = dc["MASSA_ROTA"].sum() if not dc.empty and "MASSA_ROTA" in dc.columns else 0
    massa_rota_filtro = dc_tab["MASSA_ROTA"].sum() if not dc_tab.empty and "MASSA_ROTA" in dc_tab.columns else 0
    massa_removida    = massa_rota_bruta - massa_rota_filtro
    irid              = (massa_rota_filtro / massa_total * 100) if massa_total > 0 else 0

    if not dc_tab.empty and "MASSA_ROTA" in dc_tab.columns:
        mt   = dc_tab["MASSA_ROTA"].sum()
        mad  = dc_tab[dc_tab["CATEGORIA"] == "Adequado"]["MASSA_ROTA"].sum()
        mina = dc_tab[dc_tab["CATEGORIA"] == "Inadequado"]["MASSA_ROTA"].sum()
        pct_ad = (mad  / mt * 100) if mt > 0 else 0
        pct_in = (mina / mt * 100) if mt > 0 else 0
        n_mun_lixao = dc_tab[dc_tab["UNIDADE_DEST"].astype(str)
                             .str.contains("Lixão|Vazadouro", case=False, na=False)]["COD_IBGE"].nunique()
    else:
        pct_ad = pct_in = n_mun_lixao = 0

    # =========================================================
    # 📊 BLOCO 1 — COMPARAÇÃO METODOLÓGICA DOS DOIS INDICADORES
    # =========================================================
    st.markdown("### 📊 Os dois indicadores de massa — leitura comparada")
    st.markdown(
        "O SINISA produz **duas medições distintas** da mesma realidade, "
        "em **duas abas diferentes** do formulário. Elas **não devem ser somadas** — "
        "são visões complementares, não universos paralelos."
    )

    with st.container(border=True):
        c1, c2 = st.columns(2)
        with c1:
            st.metric(
                "⚖️ Massa coletada (SINISA)",
                f"{fmt_br(massa_total)} t/ano",
                help="Campo GTR1028 — referencial oficial da PNRS. "
                     "Não depende do destino."
            )
            st.caption(
                "**O que é:** soma, por município, da massa total anual de RSU coletados.\n\n"
                "**Fonte:** aba `Manejo_Resíduos_Sólidos_Urbanos`, coluna `GTR1028`.\n\n"
                "**Pergunta que responde:** *\"Quanto o município coletou no ano?\"*\n\n"
                "**Uso no monitoramento:** indicador de **geração/coleta** — base das "
                "metas PLANARES de universalização.\n\n"
                "**Estabilidade:** **não muda** com filtros de destino (é a referência oficial)."
            )
        with c2:
            st.metric(
                "🗺️ Massa com destino declarado",
                f"{fmt_br(massa_rota_filtro)} t/ano",
                help="Σ GTR1008 após o filtro atual. É este valor que reage ao filtro."
            )
            st.caption(
                "**O que é:** soma, rota por rota, da massa efetivamente destinada a "
                "uma unidade final (aterro, compostagem, triagem, lixão etc.).\n\n"
                "**Fonte:** aba `Manejo_Coleta_e_Destinação`, coluna `GTR1008`.\n\n"
                "**Pergunta que responde:** *\"Rota por rota, quanto foi e para onde foi?\"*\n\n"
                "**Uso no monitoramento:** indicador de **rastreabilidade de destino** — "
                "base da conformidade com o art. 9º da PNRS.\n\n"
                "**Estabilidade:** **muda** com o filtro 'Excluir transbordo'."
            )

    # ---------- Gap + IRD + interpretação ----------
    gap = massa_total - massa_rota_filtro
    pct_gap = (gap / massa_total * 100) if massa_total > 0 else 0

    c1, c2, c3 = st.columns(3)
    c1.metric("📐 Diferença entre os dois", f"{fmt_br(gap)} t",
              delta=f"{fmt_br(pct_gap, 2)}% do total",
              delta_color="off",
              help="Massa coletada − Massa roteada. "
                   "Positiva = rotas não detalhadas; negativa = duplicidade.")
    c2.metric("📊 Índice de Rastreabilidade de Destino (IRD)",
              f"{fmt_br(irid, 2)}%",
              help="IRD = (Σ GTR1008 / Σ GTR1028) × 100. "
                   "Mede qual % da massa coletada tem destino documentado rota a rota.")
    c3.metric("🚫 Massa removida pelo filtro",
              f"{fmt_br(massa_removida)} t" if excluir_transbordo else "—",
              help="Ative o filtro 'Excluir transbordo' para remover dupla contagem.")

    with st.expander("🔬 Interpretação: por que os dois números são diferentes?", expanded=True):
        st.markdown(f"""
        **Os dois indicadores vêm de abas diferentes do SINISA e respondem a perguntas diferentes.**

        | Indicador | Fonte no SINISA | Pergunta |
        |---|---|---|
        | **⚖️ Massa coletada** = {fmt_br(massa_total)} t | `GTR1028` (aba Resíduos) | *Quanto coletou?* |
        | **🗺️ Massa com destino** = {fmt_br(massa_rota_filtro)} t | `Σ GTR1008` (aba Coleta) | *Quanto foi rastreado até o destino?* |
        | **📐 Diferença** = {fmt_br(gap)} t ({fmt_br(pct_gap, 2)}%) | — | *Qual parcela ficou sem rastreabilidade?* |

        ### 📌 Como interpretar a diferença

        | Situação | Significado | Ação sugerida |
        |---|---|---|
        | Diferença **positiva grande** | Municípios declararam massa coletada mas **não detalharam rotas de destino** — dado ausente no SINISA | 📚 Capacitação técnica + cobrança de preenchimento |
        | Diferença **negativa grande** | Rotas **duplicadas** — geralmente porque o transbordo não foi excluído | 🚫 Ativar o filtro 'Excluir transbordo' |
        | Diferença **próxima de zero** | Dados **consistentes** entre as duas abas | ✅ Manter monitoramento |

        ### 🎯 IRD — Índice de Rastreabilidade de Destino
