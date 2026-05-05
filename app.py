
**📈 Para Compostagem de Podas e Galhadas:**
- **Emissões Evitadas:** {formatar_br(co2eq_total_evitado_compostagem_20anos)} tCO₂e
- **Preço do Carbono:** {moeda_carbono} {formatar_br(preco_carbono)}/tCO₂eq
- **Cálculo:** {formatar_br(co2eq_total_evitado_compostagem_20anos)} × {formatar_br(preco_carbono)} = {moeda_carbono} {formatar_br(valor_total_euros_20anos_comp)}

**💰 Em Reais (com câmbio):**
- **Taxa de câmbio:** 1 Euro = R$ {formatar_br(taxa_cambio)}
- **Preço em Reais:** R$ {formatar_br(preco_carbono_reais)}/tCO₂eq
- **Cálculo:** {formatar_br(co2eq_total_evitado_compostagem_20anos)} × {formatar_br(preco_carbono_reais)} = R$ {formatar_br(valor_total_reais_20anos_comp)}

**📅 Média Anual (dividindo por 20 anos):**
- **Emissões anuais:** {formatar_br(media_anual_evitado_compostagem)} tCO₂e/ano
- **Valor anual em Euro:** {moeda_carbono} {formatar_br(valor_medio_anual_euros_comp)}/ano
- **Valor anual em Real:** R$ {formatar_br(valor_medio_anual_reais_comp)}/ano

**⚠️ IMPORTANTE para podas e galhadas:**
- **Somente compostagem** (sem vermicompostagem)
- **Fatores de emissão reduzidos** para materiais lignocelulósicos
- **Constante de decaimento reduzida** (k = {k_ano_PODAS} ano⁻¹)
- **Período de compostagem estendido** ({DIAS_COMPOSTAGEM_PODAS} dias)
- **Menor geração de CH₄** devido à natureza aeróbica dos resíduos
- **⚠️ APENAS CH₄:** Este cálculo considera somente emissões de metano (CH₄)
""")

# Nota sobre atualização automática
st.info(f"""
**🔄 Atualização Automática - Podas e Galhadas:**
- As cotações são atualizadas automaticamente toda vez que você acessa o app
- Preço atual do carbono: **{moeda_carbono} {formatar_br(preco_carbono)}/tCO₂eq**
- Taxa de câmbio atual: **1 Euro = R$ {formatar_br(taxa_cambio)}**
- **Emissões Evitadas totais (podas):** {formatar_br(co2eq_total_evitado_compostagem_20anos)} tCO₂e
- **Valor total dos créditos (podas):** {moeda_carbono} {formatar_br(valor_total_euros_20anos_comp)} (ou R$ {formatar_br(valor_total_reais_20anos_comp)})

**🌳 Características específicas das podas:**
- **Tipo de resíduo:** Materiais lignocelulósicos (madeira, galhos)
- **DOC reduzido:** {DOC_PODAS} (vs {DOC_ORGANICO} para orgânicos)
- **Decomposição mais lenta:** k = {k_ano_PODAS} ano⁻¹ (vs {k_ano_ORGANICO} ano⁻¹)
- **Menor produção de CH₄:** Fatores de emissão reduzidos
- **Somente compostagem:** Não recomendada vermicompostagem
- **⚠️ APENAS CH₄:** Este cálculo considera somente emissões de metano (CH₄)
""")

else:
st.info("✅ Não há massa de podas e galhadas destinada a aterros. Todo o material já está sendo direcionado para tratamentos adequados!")

else:
st.info("✅ Não há massa de podas e galhadas destinada a aterros. Todo o material já está sendo direcionado para tratamentos adequados!")

# Nota específica sobre podas e galhadas
st.info("""
**🌳 Importante para podas e galhadas:**
- Podas e galhadas são **materiais lignocelulósicos** (madeira, galhos)
- Têm **decomposição mais lenta** que resíduos orgânicos alimentares
- **Baixo teor de nitrogênio**, ideal para compostagem (não vermicompostagem)
- **Alta relação C/N**, exigindo processo de compostagem mais longo
- **Menor produção de CH₄** devido à natureza aeróbica dos resíduos
- **Somente compostagem** é recomendada (sem vermicompostagem)
- **⚠️ APENAS CH₄:** Este cálculo considera somente emissões de metano (CH₄)
""")

else:
st.info("Não há dados de podas e galhadas para o município selecionado.")

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
