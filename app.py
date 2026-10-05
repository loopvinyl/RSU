# =========================================================
# RSU BRASIL — MONITORAMENTO DA GESTÃO DE RESÍDUOS SÓLIDOS URBANOS
# Subsídio ao Ministério do Meio Ambiente (MMA) — PNRS / PLANARES / SINISA
# v2.4 — filtro de transbordo agora com feedback visual explícito
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
            f"ℹ️ O filtro 'Excluir transbordo' **não se aplica** a esta aba. "
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
            "no cômputo de destinação final, **a massa é contada duas vezes**, inflando "
            "os totais."
        )
        st.markdown(
            "**Afeta:** Painel Nacional · Coleta e Cobertura · Destinação Final · "
            "Recuperação de Materiais  \n"
            "**Não afeta:** Análise Territorial · Inclusão Socioprodutiva."
        )

# =========================================================
# ABAS (6 abas)
# =========================================================
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "🇧🇷 Painel Nacional",
    "🗺️ Análise Territorial",
    "🚛 Coleta e Cobertura",
    "🏭 Destinação Final",
    "♻️ Recuperação de Materiais",
    "👥 Inclusão Socioprodutiva",
])

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

    # ----- LINHA 1: População e referência SINISA -----
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("🏙️ Municípios que reportaram", f"{n_mun:,}".replace(",", "."))
    c2.metric("👥 População coberta", f"{fmt_br(pop_total)} hab")
    c3.metric("⚖️ Massa coletada (SINISA)", f"{fmt_br(massa_total)} t/ano",
              help="Campo GTR1028 — massa que ENTRA no sistema de coleta. "
                   "Referencial oficial da PNRS, **não depende do destino final**.")
    c4.metric("📊 Per capita", f"{fmt_br(per_cap, 0)} kg/hab/ano",
              help=f"= {fmt_br(per_cap_dia, 2)} kg/hab/dia")

    # ----- LINHA 2: Massa ROTEADA (é aqui que o filtro atua) -----
    st.markdown("##### 🔀 Massa por rota de destinação")
    st.caption("Os valores abaixo são calculados a partir das **rotas de coleta e destinação** "
               "(aba `Manejo_Coleta_e_Destinação`) e **reagem ao filtro 'Excluir transbordo'**.")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("🗺️ Massa com destino declarado", f"{fmt_br(massa_rota_filtro)} t/ano",
              help="Σ GTR1008 (rotas filtradas). É este valor que muda com o filtro.")
    if excluir_transbordo:
        c2.metric("🚫 Massa removida (transbordo)", f"{fmt_br(massa_removida)} t/ano",
                  delta=f"-{fmt_br(massa_removida)} t",
                  delta_color="inverse",
                  help="Massa que passava por 'Unidade de Transbordo' e foi excluída.")
    else:
        c2.metric("📦 Transbordo incluído", f"{fmt_br(massa_removida)} t/ano",
                  help="Ative o filtro acima para remover esta massa (evita dupla contagem).")
    dif = massa_total - massa_rota_filtro
    c3.metric("📐 Diferença (coleta × rota)", f"{fmt_br(dif)} t",
              help="Massa coletada (SINISA) − massa roteada (após filtro). "
                   "Diferença positiva grande = rotas não detalhadas; "
                   "negativa = duplicidade.")
    c4.metric("♻️ Taxa de recuperação", f"{fmt_br(taxa_recup, 2)}%",
              help="(Massa recuperada / Massa total) × 100 — PLANARES: 48% até 2040")

    # ----- LINHA 3: Conformidade PNRS -----
    st.markdown("##### ✅ Conformidade com a PNRS")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("✅ Massa p/ destinação adequada", f"{fmt_br(pct_ad, 1)}%")
    c2.metric("🚨 Massa p/ destinação inadequada", f"{fmt_br(pct_in, 1)}%",
              help="Aterro controlado + Lixão/vazadouro")
    c3.metric("⚠️ Municípios com lixão ativo", f"{n_mun_lixao:,}".replace(",", "."))
    c4.metric("📚 Municípios c/ estudo de caracterização",
              f"{(dr['ESTUDO_CARACT'].astype(str).str.strip()=='Sim').sum():,}".replace(",", "."))

    # ----- LINHA 4: Inclusão e frota -----
    st.markdown("##### 👥 Inclusão socioprodutiva e frota")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("🏭 Cooperativas/associações", f"{fmt_br(n_coop)}")
    c2.metric("👷 Catadores organizados", f"{fmt_br(dr['CATADORES_ORG'].sum())}")
    c3.metric("🚶 Catadores informais", f"{fmt_br(dr['CATADORES_INFO'].sum())}")
    c4.metric("🚛 Veículos na frota", f"{fmt_br(dr['N_VEICULOS'].sum())}")

    # ----- Diagnóstico (expander) -----
    with st.expander("🔬 Diagnóstico: por que a massa coletada (SINISA) ≠ massa roteada?"):
        st.markdown(f"""
        - **Massa coletada (GTR1028):** {fmt_br(massa_total)} t
          → campo oficial do SINISA, calculado **antes** da destinação.
        - **Massa roteada (Σ GTR1008):** {fmt_br(massa_rota_bruta)} t (sem filtro) /
          {fmt_br(massa_rota_filtro)} t (com filtro)
          → soma das rotas de coleta com destino declarado.
        - **Diferença:** {fmt_br(dif)} t ({(dif/massa_total*100 if massa_total>0 else 0):.1f}%)

        **Como interpretar:**

        | Situação | Significado |
        |---|---|
        | Diferença **positiva grande** | Municípios declararam massa coletada mas não detalharam rotas de destino (dado ausente no SINISA). |
        | Diferença **negativa grande** | Rotas duplicadas — geralmente porque o transbordo não foi excluído. Ative o filtro. |
        | Diferença **próxima de zero** | Dados consistentes entre as duas abas. |

        ℹ️ Por isso os dois números aparecem separados: **um é o referencial oficial da PNRS**
        (não muda com filtros), o outro é o detalhamento por rota (muda com o filtro).
        """)

    # ----- Comparação temporal -----
    if ano_comp != "—" and ano_comp in dados:
        st.markdown("---")
        st.subheader(f"📈 Evolução {ano_comp} → {ano_sel}")
        dr_c = filtrar(dados[ano_comp]["residuos"])
        dc_c = filtrar_transbordo(filtrar(dados[ano_comp]["coleta"]), excluir_transbordo)
        pop_c   = dr_c["POP_TOTAL"].sum()
        massa_c = dr_c["MASSA_TOTAL"].sum()
        recup_c = dr_c["MASSA_RECUPERADA"].sum()
        pc_c    = (massa_c / pop_c * 1000) if pop_c > 0 else 0
        tx_c    = (recup_c / massa_c * 100) if massa_c > 0 else 0
        if not dc_c.empty and "MASSA_ROTA" in dc_c.columns:
            mt_c = dc_c["MASSA_ROTA"].sum()
            mad_c = dc_c[dc_c["CATEGORIA"] == "Adequado"]["MASSA_ROTA"].sum()
            pct_ad_c = (mad_c / mt_c * 100) if mt_c > 0 else 0
        else:
            pct_ad_c = 0

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Massa coletada (SINISA)", f"{fmt_br(massa_total)} t",
                  delta=f"{fmt_br(massa_total - massa_c)} t")
        c2.metric("Per capita", f"{fmt_br(per_cap, 0)} kg/hab/ano",
                  delta=f"{fmt_br(per_cap - pc_c, 0)} kg/hab/ano")
        c3.metric("Taxa de recuperação", f"{fmt_br(taxa_recup, 2)}%",
                  delta=f"{fmt_br(taxa_recup - tx_c, 2)} p.p.")
        c4.metric("% destinação adequada", f"{fmt_br(pct_ad, 1)}%",
                  delta=f"{fmt_br(pct_ad - pct_ad_c, 1)} p.p.")

    st.caption("📌 Fonte: SINISA — Sistema Nacional de Informações sobre Saneamento "
               "(módulo Resíduos Sólidos). Dados autorreportados pelos municípios.")

# ---------------------------------------------------------
# TAB 2 — ANÁLISE TERRITORIAL
# ---------------------------------------------------------
with tab2:
    st.subheader("🗺️ Análise Territorial — Região e Estado")
    aviso_filtro_transbordo(
        afetada=False,
        motivo_nao_afeta="Esta aba usa dados agregados por município "
                         "(aba 'Manejo_Resíduos_Sólidos_Urbanos'), que não possui "
                         "coluna de destino final."
    )

    reg = dr.groupby("REGIAO", dropna=False).agg(
        MUNICIPIOS=("COD_IBGE", "nunique"),
        POPULACAO=("POP_TOTAL", "sum"),
        MASSA=("MASSA_TOTAL", "sum"),
        RECUPERADA=("MASSA_RECUPERADA", "sum"),
    ).reset_index()
    reg["PER_CAPITA"] = (reg["MASSA"] / reg["POPULACAO"] * 1000).round(0)
    reg["TAXA_RECUP"] = (reg["RECUPERADA"] / reg["MASSA"] * 100).round(2)

    c1, c2 = st.columns(2)
    with c1:
        fig = px.bar(reg.sort_values("MASSA"),
                     x="MASSA", y="REGIAO", orientation="h",
                     color="REGIAO", color_discrete_map=CORES_REGIAO,
                     title="Massa total coletada por região (t/ano)",
                     labels={"MASSA": "Massa (t/ano)", "REGIAO": ""})
        fig.update_layout(showlegend=False, height=380)
        st.plotly_chart(fig, use_container_width=True)
    with c2:
        fig = px.bar(reg.sort_values("PER_CAPITA"),
                     x="PER_CAPITA", y="REGIAO", orientation="h",
                     color="REGIAO", color_discrete_map=CORES_REGIAO,
                     title="Per capita por região (kg/hab/ano)",
                     labels={"PER_CAPITA": "kg/hab/ano", "REGIAO": ""})
        fig.update_layout(showlegend=False, height=380)
        st.plotly_chart(fig, use_container_width=True)

    st.markdown("#### 📋 Indicadores consolidados por região")
    st.dataframe(reg.style.format({
        "MUNICIPIOS": "{:,.0f}", "POPULACAO": "{:,.0f}",
        "MASSA": "{:,.0f}", "RECUPERADA": "{:,.0f}",
        "PER_CAPITA": "{:,.0f}", "TAXA_RECUP": "{:.2f}%",
    }), use_container_width=True)

    st.markdown("---")
    st.markdown("#### 🏆 Ranking por Estado (UF)")
    uf = dr.groupby("UF", dropna=False).agg(
        MUNICIPIOS=("COD_IBGE", "nunique"),
        POPULACAO=("POP_TOTAL", "sum"),
        MASSA=("MASSA_TOTAL", "sum"),
        RECUPERADA=("MASSA_RECUPERADA", "sum"),
    ).reset_index()
    uf["PER_CAPITA"] = (uf["MASSA"] / uf["POPULACAO"] * 1000).round(0)
    uf["TAXA_RECUP"] = (uf["RECUPERADA"] / uf["MASSA"] * 100).round(2)
    uf = uf.sort_values("MASSA", ascending=False)

    fig = px.treemap(uf.head(27), path=["UF"], values="MASSA",
                     color="TAXA_RECUP", color_continuous_scale="RdYlGn",
                     title="Massa por UF (cor = taxa de recuperação %)")
    st.plotly_chart(fig, use_container_width=True)

    st.dataframe(uf.style.format({
        "MUNICIPIOS": "{:,.0f}", "POPULACAO": "{:,.0f}",
        "MASSA": "{:,.0f}", "RECUPERADA": "{:,.0f}",
        "PER_CAPITA": "{:,.0f}", "TAXA_RECUP": "{:.2f}%",
    }), use_container_width=True, height=400)

# ---------------------------------------------------------
# TAB 3 — COLETA E COBERTURA
# ---------------------------------------------------------
with tab3:
    st.subheader("🚛 Coleta e Cobertura")
    aviso_filtro_transbordo(afetada=True)

    dc_tab = filtrar_transbordo(dc, excluir_transbordo)

    # Cards de massa roteada (reagem ao filtro)
    massa_bruta = dc["MASSA_ROTA"].sum() if not dc.empty and "MASSA_ROTA" in dc.columns else 0
    massa_filt  = dc_tab["MASSA_ROTA"].sum() if not dc_tab.empty and "MASSA_ROTA" in dc_tab.columns else 0
    c1, c2, c3 = st.columns(3)
    c1.metric("🗺️ Massa com destino declarado", f"{fmt_br(massa_filt)} t/ano")
    c2.metric("📦 Massa bruta (sem filtro)", f"{fmt_br(massa_bruta)} t/ano")
    c3.metric("🚫 Redução pelo filtro",
              f"{fmt_br(massa_bruta - massa_filt)} t" if excluir_transbordo else "—")

    if dc_tab.empty:
        st.info("Sem dados de coleta para o filtro selecionado.")
    else:
        tipos = dc_tab.groupby("TIPO_COLETA", dropna=False).agg(
            ROTAS=("COD_ROTA", "nunique"),
            MASSA=("MASSA_ROTA", "sum"),
            MUNICIPIOS=("COD_IBGE", "nunique"),
        ).reset_index().sort_values("MASSA", ascending=False)
        tipos["%"] = (tipos["MASSA"] / tipos["MASSA"].sum() * 100).round(2)

        c1, c2 = st.columns(2)
        with c1:
            fig = px.pie(tipos, names="TIPO_COLETA", values="MASSA",
                         title="Massa por tipo de coleta", hole=0.45)
            fig.update_traces(textposition="inside", textinfo="percent+label")
            fig.update_layout(height=450, showlegend=False)
            st.plotly_chart(fig, use_container_width=True)
        with c2:
            fig = px.bar(tipos.head(8).sort_values("MASSA"),
                         x="MASSA", y="TIPO_COLETA", orientation="h",
                         title="Massa por tipo de coleta (t/ano)",
                         labels={"MASSA": "t/ano", "TIPO_COLETA": ""})
            fig.update_layout(height=450, showlegend=False)
            st.plotly_chart(fig, use_container_width=True)

        st.dataframe(tipos.style.format({
            "MASSA": "{:,.0f}", "ROTAS": "{:,.0f}",
            "MUNICIPIOS": "{:,.0f}", "%": "{:.2f}%",
        }), use_container_width=True)

        st.markdown("---")
        st.markdown("#### 📍 Abrangência do serviço")
        abr = dc_tab.groupby("ABRANGENCIA", dropna=False)["MASSA_ROTA"].sum().reset_index()
        st.dataframe(abr.style.format({"MASSA_ROTA": "{:,.0f}"}),
                     use_container_width=True)

        st.markdown("---")
        st.markdown("#### 🏆 Top 15 municípios por massa coletada")
        top15 = dr.sort_values("MASSA_TOTAL", ascending=False).head(15)[
            ["MUNICIPIO","UF","POP_TOTAL","MASSA_TOTAL","MASSA_RECUPERADA"]].copy()
        top15["PER_CAPITA"] = (top15["MASSA_TOTAL"] / top15["POP_TOTAL"] * 1000).round(0)
        top15["% RECUP"] = (top15["MASSA_RECUPERADA"] / top15["MASSA_TOTAL"] * 100).round(2)
        st.dataframe(top15.style.format({
            "POP_TOTAL": "{:,.0f}", "MASSA_TOTAL": "{:,.0f}",
            "MASSA_RECUPERADA": "{:,.0f}", "PER_CAPITA": "{:,.0f}",
            "% RECUP": "{:.2f}%",
        }), use_container_width=True)

# ---------------------------------------------------------
# TAB 4 — DESTINAÇÃO FINAL
# ---------------------------------------------------------
with tab4:
    st.subheader("🏭 Destinação Final — Conformidade com a PNRS")
    aviso_filtro_transbordo(afetada=True)

    dc_tab = filtrar_transbordo(dc, excluir_transbordo)

    # Cards que MOSTRAM o efeito do filtro
    massa_bruta = dc["MASSA_ROTA"].sum() if not dc.empty and "MASSA_ROTA" in dc.columns else 0
    massa_filt  = dc_tab["MASSA_ROTA"].sum() if not dc_tab.empty and "MASSA_ROTA" in dc_tab.columns else 0
    massa_remov = massa_bruta - massa_filt
    pct_remov   = (massa_remov / massa_bruta * 100) if massa_bruta > 0 else 0

    c1, c2, c3 = st.columns(3)
    c1.metric("⚖️ Massa com destino declarado", f"{fmt_br(massa_filt)} t/ano",
              help="Σ GTR1008 após o filtro atual.")
    c2.metric("📦 Massa bruta (sem filtro)", f"{fmt_br(massa_bruta)} t/ano",
              help="Σ GTR1008 sem qualquer filtro de destino.")
    if excluir_transbordo:
        c3.metric("🚫 Redução pelo filtro",
                  f"{fmt_br(massa_remov)} t",
                  delta=f"-{fmt_br(pct_remov, 1)}%",
                  delta_color="inverse",
                  help="Massa que passava por transbordo (dupla contagem) e foi excluída.")
    else:
        c3.metric("🚫 Redução pelo filtro", "—",
                  help="Ative 'Excluir transbordo' acima para remover a dupla contagem.")

    if dc_tab.empty:
        st.info("Sem dados de destinação para o filtro.")
    else:
        dest = dc_tab.groupby("UNIDADE_DEST", dropna=False).agg(
            MASSA=("MASSA_ROTA", "sum"),
            ROTAS=("COD_ROTA", "nunique"),
            MUNICIPIOS=("COD_IBGE", "nunique"),
        ).reset_index()
        dest["CATEGORIA"] = dest["UNIDADE_DEST"].apply(classificar_destino)
        dest = dest.sort_values("MASSA", ascending=False)
        dest["%"] = (dest["MASSA"] / dest["MASSA"].sum() * 100).round(2)

        cat = dest.groupby("CATEGORIA")["MASSA"].sum().reset_index()
        cat["%"] = (cat["MASSA"] / cat["MASSA"].sum() * 100).round(2)
        adeq = cat[cat["CATEGORIA"] == "Adequado"]["%"].sum()
        inad = cat[cat["CATEGORIA"] == "Inadequado"]["%"].sum()
        transb = cat[cat["CATEGORIA"] == "Transbordo"]["%"].sum() if "Transbordo" in cat["CATEGORIA"].values else 0

        c1, c2, c3 = st.columns(3)
        c1.metric("✅ Destinação adequada", f"{fmt_br(adeq, 1)}%")
        c2.metric("🚨 Destinação inadequada", f"{fmt_br(inad, 1)}%")
        c3.metric("📦 Transbordo (etapa intermediária)", f"{fmt_br(transb, 1)}%",
                  help="Se > 0%, o filtro 'Excluir transbordo' está inativo.")

        c1, c2 = st.columns(2)
        with c1:
            fig = px.pie(dest, names="UNIDADE_DEST", values="MASSA",
                         title="Massa por unidade de destino", hole=0.45)
            fig.update_traces(textposition="inside", textinfo="percent+label")
            fig.update_layout(height=500, showlegend=False)
            st.plotly_chart(fig, use_container_width=True)
        with c2:
            fig = px.bar(dest.sort_values("MASSA"),
                         x="MASSA", y="UNIDADE_DEST", orientation="h",
                         color="CATEGORIA",
                         color_discrete_map={
                             "Adequado": "#27ae60", "Inadequado": "#e74c3c",
                             "Transbordo": "#f39c12", "Outros": "#95a5a6",
                             "Não informado": "#bdc3c7",
                         },
                         title="Massa por tipo de unidade (t/ano)",
                         labels={"MASSA": "t/ano", "UNIDADE_DEST": ""})
            fig.update_layout(height=500)
            st.plotly_chart(fig, use_container_width=True)

        st.dataframe(dest.style.format({
            "MASSA": "{:,.0f}", "ROTAS": "{:,.0f}",
            "MUNICIPIOS": "{:,.0f}", "%": "{:.2f}%",
        }), use_container_width=True)

        st.markdown("---")
        st.markdown("#### ⚠️ Municípios que ainda destinam para Lixão/Vazadouro")
        lix = dc_tab[dc_tab["UNIDADE_DEST"].astype(str)
                     .str.contains("Lixão|Vazadouro", case=False, na=False)]
        if lix.empty:
            st.success("✅ Nenhum município do filtro destina para lixão/vazadouro.")
        else:
            resumo_lix = lix.groupby(["MUNICIPIO","UF"], dropna=False).agg(
                MASSA=("MASSA_ROTA","sum"),
                ROTAS=("COD_ROTA","nunique"),
            ).reset_index().sort_values("MASSA", ascending=False)
            st.metric("Municípios com lixão ativo", resumo_lix.shape[0])
            st.dataframe(resumo_lix.style.format({"MASSA":"{:,.0f}","ROTAS":"{:,.0f}"}),
                         use_container_width=True, height=350)

        st.markdown("---")
        st.markdown("#### 🔀 Fluxos intermunicipais (exportação de resíduos)")
        if "ENVIADO_OUTRO" in dc_tab.columns:
            fluxo = dc_tab.groupby("ENVIADO_OUTRO", dropna=False)["MASSA_ROTA"].sum().reset_index()
            st.dataframe(fluxo.style.format({"MASSA_ROTA":"{:,.0f}"}),
                         use_container_width=True)
            if "MUN_DEST" in dc_tab.columns:
                sub = dc_tab[dc_tab["ENVIADO_OUTRO"].astype(str)
                             .str.strip().str.lower() == "sim"].copy()
                if not sub.empty:
                    sub["UF_DEST"] = sub["MUN_DEST"].astype(str).str.extract(r"/([A-Z]{2})$")[0].fillna("?")
                    sk = sub.groupby(["UF","UF_DEST"], dropna=False)["MASSA_ROTA"].sum().reset_index()
                    sk = sk[sk["MASSA_ROTA"] > 0].sort_values("MASSA_ROTA", ascending=False).head(60)
                    if not sk.empty:
                        labels = list(pd.unique(sk[["UF","UF_DEST"]].values.ravel()))
                        idx = {l: i for i, l in enumerate(labels)}
                        fig = go.Figure(go.Sankey(
                            node=dict(label=labels, pad=12, thickness=16),
                            link=dict(
                                source=[idx[u] for u in sk["UF"]],
                                target=[idx[v] for v in sk["UF_DEST"]],
                                value=sk["MASSA_ROTA"].tolist(),
                            ),
                        ))
                        fig.update_layout(title="Fluxo de massa entre UFs (t/ano)", height=520)
                        st.plotly_chart(fig, use_container_width=True)

# ---------------------------------------------------------
# TAB 5 — RECUPERAÇÃO DE MATERIAIS
# ---------------------------------------------------------
with tab5:
    st.subheader("♻️ Recuperação de Materiais e Coleta Seletiva")
    aviso_filtro_transbordo(afetada=True)

    dc_tab = filtrar_transbordo(dc, excluir_transbordo)

    if dc_tab.empty or dr.empty:
        st.info("Sem dados para o filtro.")
    else:
        materiais = ["PAPEL_RECUP","PLASTICO_RECUP","METAL_RECUP","VIDRO_RECUP","OUTROS_RECUP"]
        existentes = [c for c in materiais if c in dc_tab.columns]
        if existentes:
            total_mat = dc_tab[existentes].sum().reset_index()
            total_mat.columns = ["Material", "Massa (t)"]
            mapa = {"PAPEL_RECUP":"Papel/Papelão","PLASTICO_RECUP":"Plástico",
                    "METAL_RECUP":"Metal","VIDRO_RECUP":"Vidro","OUTROS_RECUP":"Outros"}
            total_mat["Material"] = total_mat["Material"].map(mapa)
            total_mat["%"] = (total_mat["Massa (t)"] / total_mat["Massa (t)"].sum() * 100).round(2)

            c1, c2 = st.columns(2)
            with c1:
                fig = px.pie(total_mat, names="Material", values="Massa (t)",
                             title="Composição dos recicláveis recuperados", hole=0.45)
                fig.update_traces(textposition="inside", textinfo="percent+label")
                fig.update_layout(height=420, showlegend=False)
                st.plotly_chart(fig, use_container_width=True)
            with c2:
                st.dataframe(total_mat.style.format({"Massa (t)":"{:,.0f}","%":"{:.2f}%"}),
                             use_container_width=True)

        st.markdown("---")
        st.markdown("#### 🏆 Taxa de recuperação por município (top 15 e bottom 15)")
        tmp = dr[(dr["MASSA_TOTAL"] > 0) & (dr["POP_TOTAL"] > 0)].copy()
        tmp["TAXA_RECUP"] = (tmp["MASSA_RECUPERADA"] / tmp["MASSA_TOTAL"] * 100).round(2)
        top15 = tmp.nlargest(15, "TAXA_RECUP")[
            ["MUNICIPIO","UF","MASSA_TOTAL","MASSA_RECUPERADA","TAXA_RECUP"]]
        bot15 = tmp.nsmallest(15, "TAXA_RECUP")[
            ["MUNICIPIO","UF","MASSA_TOTAL","MASSA_RECUPERADA","TAXA_RECUP"]]
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**🟢 Top 15 — melhores taxas**")
            st.dataframe(top15.style.format({
                "MASSA_TOTAL":"{:,.0f}","MASSA_RECUPERADA":"{:,.0f}","TAXA_RECUP":"{:.2f}%"
            }), use_container_width=True, hide_index=True)
        with c2:
            st.markdown("**🔴 Bottom 15 — piores taxas**")
            st.dataframe(bot15.style.format({
                "MASSA_TOTAL":"{:,.0f}","MASSA_RECUPERADA":"{:,.0f}","TAXA_RECUP":"{:.2f}%"
            }), use_container_width=True, hide_index=True)

# ---------------------------------------------------------
# TAB 6 — INCLUSÃO SOCIOPRODUTIVA
# ---------------------------------------------------------
with tab6:
    st.subheader("👥 Inclusão Socioprodutiva de Catadores e Frota")
    aviso_filtro_transbordo(
        afetada=False,
        motivo_nao_afeta="Esta aba usa o cadastro de cooperativas e a frota de "
                         "veículos, que não possuem coluna de destino final."
    )

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("🏭 Cooperativas/associações", f"{fmt_br(dr['N_COOP'].sum())}")
    c2.metric("👷 Catadores organizados", f"{fmt_br(dr['CATADORES_ORG'].sum())}")
    c3.metric("🚶 Catadores informais", f"{fmt_br(dr['CATADORES_INFO'].sum())}")
    c4.metric("🚛 Veículos na frota", f"{fmt_br(dr['N_VEICULOS'].sum())}")

    st.markdown("---")
    st.markdown("#### 🏆 Top 15 municípios por catadores organizados")
    top_cat = dr.nlargest(15, "CATADORES_ORG")[
        ["MUNICIPIO","UF","N_COOP","CATADORES_ORG","CATADORES_INFO"]]
    st.dataframe(top_cat.style.format({
        "N_COOP":"{:,.0f}","CATADORES_ORG":"{:,.0f}","CATADORES_INFO":"{:,.0f}"
    }), use_container_width=True, hide_index=True)

    st.markdown("---")
    st.markdown("#### 🚛 Frota de veículos — distribuição por tipo e idade")
    dv = dados[ano_sel]["veiculos"]
    if not dv.empty and "TIPO_VEICULO" in dv.columns:
        dv_f = filtrar(dv)
        c1, c2 = st.columns(2)
        with c1:
            t = dv_f.groupby("TIPO_VEICULO", dropna=False)["QTD"].sum().reset_index() \
                    .sort_values("QTD", ascending=False)
            fig = px.bar(t, x="QTD", y="TIPO_VEICULO", orientation="h",
                         title="Veículos por tipo",
                         labels={"QTD":"unidades","TIPO_VEICULO":""})
            fig.update_layout(height=380, showlegend=False)
            st.plotly_chart(fig, use_container_width=True)
        with c2:
            f = dv_f.groupby("FAIXA_IDADE", dropna=False)["QTD"].sum().reset_index() \
                    .sort_values("QTD", ascending=False)
            fig = px.bar(f, x="FAIXA_IDADE", y="QTD",
                         title="Veículos por faixa de idade",
                         labels={"QTD":"unidades","FAIXA_IDADE":""})
            fig.update_layout(height=380, showlegend=False)
            st.plotly_chart(fig, use_container_width=True)

    st.markdown("---")
    st.markdown("#### 🏭 Cooperativas — serviços prestados")
    dk = dados[ano_sel]["cooperativas"]
    if not dk.empty and "SERVICOS" in dk.columns:
        dk_f = filtrar(dk)
        servicos_contados = {"Triagem": 0, "Coleta": 0, "Educação ambiental": 0,
                             "Compostagem": 0, "Recebimento de óleo de cozinha": 0}
        for s in dk_f["SERVICOS"].dropna():
            for k in servicos_contados:
                if k.lower() in str(s).lower():
                    servicos_contados[k] += 1
        df_serv = pd.DataFrame(list(servicos_contados.items()),
                               columns=["Serviço","Nº de cooperativas"]) \
                    .sort_values("Nº de cooperativas", ascending=False)
        fig = px.bar(df_serv, x="Nº de cooperativas", y="Serviço", orientation="h",
                     title="Serviços prestados pelas cooperativas/associações")
        fig.update_layout(height=350, showlegend=False)
        st.plotly_chart(fig, use_container_width=True)

# ---------------------------------------------------------
# RODAPÉ
# ---------------------------------------------------------
st.markdown("---")
st.caption("""
**RSU Brasil — Monitoramento da Gestão de Resíduos Sólidos Urbanos** · v2.4
Fonte: **SINISA** · Metodologia alinhada à **PNRS (Lei 12.305/2010)**, **Decreto 10.936/2022**
e **PLANARES (Decreto 11.043/2022)**. Ferramenta de apoio ao **Ministério do Meio Ambiente (MMA)**.
""")
