# 06 — Análise de Agente (IA) sobre o cruzamento ANP

## O modelo aplicado

O artigo de referência — *“Análise de Agente com Power BI e Microsoft Fabric:
a abordagem com IA para criar BI empresarial”* — descreve a evolução do BI
tradicional para **analytics aumentado por agentes**: além do relatório
consumido por pessoas, um **agente de IA** consulta o mesmo dado curado e responde
perguntas em linguagem natural, com governança.

Neste projeto, o padrão foi materializado em três camadas complementares:

```
┌─────────────────────────────────────────────────────────────┐
│ 1. BI visual      → Power BI na intranet (docs/03 e 04)     │
│ 2. Dado curado    → Lakehouse Delta + Cosmos DB (docs/05)   │
│ 3. Agente analítico → Fabric Data Agent / AI Foundry Agent  │
└─────────────────────────────────────────────────────────────┘
```

## Por que o Cosmos DB no meio?

| Necessidade do agente | Como o Cosmos DB atende |
|---|---|
| Leitura pontual de “ficha do ano” com latência baixa | 1 documento por ano, `point-read` por id/partition |
| Contexto estruturado para RAG tabular | JSON aninhado (produção/comércio/fases/indicadores/mensal) pronto para prompt |
| Memória auditável | Documentos versionados por upsert; fonte citada dentro do próprio documento |
| Consultas agregadas ocasionais | SQL API (`SELECT ... FROM c WHERE c.ano = @ano`) |

## Implementação

### Opção A — Fabric Data Agent (nativo)

1. No workspace Fabric: **Create → Data Agent**;
2. Conecte as fontes:
   - Tabelas Delta do Lakehouse (`fato_mensal`, `fato_anual`,
     `dim_fases_campos`, `dim_campos`);
   - (opcional) container Cosmos DB via shortcut/mirroring;
3. Cole em **Instructions** o bloco `instrucoes_sistema` de
   [`fabric/data_agent_config.json`](../fabric/data_agent_config.json);
4. Adicione os `exemplos_perguntas` como few-shots para guiar respostas;
5. Publique e teste no playground do agente.

### Opção B — Azure AI Foundry Agent + Function/MCP

1. Crie um Agent no AI Foundry Project;
2. Registre uma *tool* que executa as consultas Cosmos DB
   (SDK `azure-cosmos`, mesma credencial Entra do notebook 02);
3. Use o mesmo `instrucoes_sistema` como system prompt;
4. Exponha o agente também ao Teams/Web interno via API do projeto.

## Exemplos reais (dados deste repositório)

**P:** “Qual foi a produção de petróleo em 2025 e a variação vs 2024?”
**R:** “Em 2025 o Brasil produziu 1,376 bilhão de barris (+11,97% vs 2024),
média de 3,77 milhões bbl/dia — recorde da série. Fonte: ANP.”

**P:** “Quantos campos estavam em produção em cada ano?”
**R:** “275 (2020), 280 (2021), 288 (2022), 292 (2023), 297 (2024) e 301 (2025)
campos na fase de produção; em desenvolvimento: 1→11 no período.
Fonte: ANP Dados Abertos — Fase de Desenvolvimento e Produção.”

**P:** “A dependência de importação já ficou abaixo de 10%?”
**R:** “Sim — apenas em 2025 (6,5%). Em 2024 foi 8,4%; nos demais anos variou
entre 9,2% e 10,7%.” *(valores derivados do fato anual)*

## Guardrails implementados

- Instruções restringem o agente às fontes conectadas (proibido inventar valores);
- Toda resposta deve citar fonte e período;
- Escopo recusado fora de petróleo/ANP;
- Dados públicos — sem risco PII/LGPD; ainda assim, logs de conversa retidos
  conforme política interna.

## Roadmap sugerido

1. Publicar o Data Agent no Teams corporativo;
2. Adicionar fontes complementares (boletim mensal PDF → lakehouse);
3. Avaliação automática das respostas (golden set das perguntas acima);
4. Copilot no próprio relatório Power BI (F-sku habilita Copilot no workspace).
