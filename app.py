
- **IRD = 100%** → 100% da massa coletada tem destino documentado rota a rota (ideal)
- **IRD atual ({fmt_br(irid, 2)}%)** → {fmt_br(gap)} t sem destino final rastreado
- **IRD < 80%** → município com problema grave de rastreabilidade

ℹ️ **Por que isso importa para o MMA:** o IRD mede a **qualidade do reporte** — não
a massa física. Municípios com IRD baixo precisam de apoio técnico para documentar
corretamente a cadeia de custódia dos resíduos. É um **KPI objetivo** de monitoramento,
independente de interpretação.
""")

# ---------- Top 15 municípios com maior gap ----------
if not dc.empty and not dr.empty:
with st.expander("🏴 Top 15 municípios com maior gap de rastreabilidade (massa coletada − massa roteada)"):
    dr_gap = dr[["COD_IBGE","MUNICIPIO","UF","MASSA_TOTAL"]].copy()
    dc_gap = dc.groupby("COD_IBGE", dropna=False)["MASSA_ROTA"].sum().reset_index()
    dc_gap = dc_gap.rename(columns={"MASSA_ROTA": "MASSA_ROTEADA"})
    dr_gap = dr_gap.merge(dc_gap, on="COD_IBGE", how="left").fillna({"MASSA_ROTEADA": 0})
    dr_gap["GAP"] = dr_gap["MASSA_TOTAL"] - dr_gap["MASSA_ROTEADA"]
    dr_gap["IRD_%"] = (dr_gap["MASSA_ROTEADA"] / dr_gap["MASSA_TOTAL"] * 100).round(2)
    dr_gap = dr_gap[dr_gap["MASSA_TOTAL"] > 0]
    top_gap = dr_gap.nlargest(15, "GAP")[
        ["MUNICIPIO","UF","MASSA_TOTAL","MASSA_ROTEADA","GAP","IRD_%"]
    ]
    st.markdown(
        "**Municípios com maior massa coletada não rastreada até o destino final.** "
        "Lista prioritária para capacitação técnica e auditoria de reporte."
    )
    st.dataframe(top_gap.style.format({
        "MASSA_TOTAL": "{:,.0f}",
        "MASSA_ROTEADA": "{:,.0f}",
        "GAP": "{:,.0f}",
        "IRD_%": "{:.2f}%",
    }), use_container_width=True, hide_index=True)

st.markdown("---")

# =========================================================
# 📊 BLOCO 2 — INDICADORES GERAIS
# =========================================================
st.markdown("### 🌎 Indicadores gerais de monitoramento")

c1, c2, c3, c4 = st.columns(4)
c1.metric("🏙️ Municípios que reportaram", f"{n_mun:,}".replace(",", "."))
c2.metric("👥 População coberta", f"{fmt_br(pop_total)} hab")
c3.metric("📊 Per capita", f"{fmt_br(per_cap, 0)} kg/hab/ano",
      help=f"= {fmt_br(per_cap_dia, 2)} kg/hab/dia")
c4.metric("♻️ Taxa de recuperação", f"{fmt_br(taxa_recup, 2)}%",
      help="(Massa recuperada / Massa total) × 100 — PLANARES: 48% até 2040")

c1, c2, c3, c4 = st.columns(4)
c1.metric("✅ Massa p/ destinação adequada", f"{fmt_br(pct_ad, 1)}%")
c2.metric("🚨 Massa p/ destinação inadequada", f"{fmt_br(pct_in, 1)}%",
      help="Aterro controlado + Lixão/vazadouro")
c3.metric("⚠️ Municípios com lixão ativo", f"{n_mun_lixao:,}".replace(",", "."))
c4.metric("📚 Municípios c/ estudo de caracterização",
      f"{(dr['ESTUDO_CARACT'].astype(str).str.strip()=='Sim').sum():,}".replace(",", "."))

c1, c2, c3, c4 = st.columns(4)
c1.metric("🏭 Cooperativas/associações", f"{fmt_br(n_coop)}")
c2.metric("👷 Catadores organizados", f"{fmt_br(dr['CATADORES_ORG'].sum())}")
c3.metric("🚶 Catadores informais", f"{fmt_br(dr['CATADORES_INFO'].sum())}")
c4.metric("🚛 Veículos na frota", f"{fmt_br(dr['N_VEICULOS'].sum())}")

# ---------- Comparação temporal ----------
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
# TAB 2 — COLETA E COBERTURA
# ---------------------------------------------------------
with tab2:
st.subheader("🚛 Coleta e Cobertura")
aviso_filtro_transbordo(afetada=True)

dc_tab = filtrar_transbordo(dc, excluir_transbordo)

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
# TAB 3 — DESTINAÇÃO FINAL
# ---------------------------------------------------------
with tab3:
st.subheader("🏭 Destinação Final — Conformidade com a PNRS")
aviso_filtro_transbordo(afetada=True)

dc_tab = filtrar_transbordo(dc, excluir_transbordo)

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
# TAB 4 — RECUPERAÇÃO DE MATERIAIS
# ---------------------------------------------------------
with tab4:
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
# TAB 5 — ANÁLISE TERRITORIAL (não afetada pelo filtro)
# ---------------------------------------------------------
with tab5:
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
# TAB 6 — INCLUSÃO SOCIOPRODUTIVA (não afetada pelo filtro)
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
**RSU Brasil — Monitoramento da Gestão de Resíduos Sólidos Urbanos** · v2.5
Fonte: **SINISA** · Metodologia alinhada à **PNRS (Lei 12.305/2010)**, **Decreto 10.936/2022**
e **PLANARES (Decreto 11.043/2022)**. Ferramenta de apoio ao **Ministério do Meio Ambiente (MMA)**.
""")
