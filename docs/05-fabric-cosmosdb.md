# 05 — Microsoft Fabric → Azure Cosmos DB for NoSQL (passo a passo)

Este módulo leva o resultado do cruzamento Power BI para o **Azure Cosmos DB**,
seguindo o modelo *“Análise de Agente com Power BI e Microsoft Fabric”*: o dado
curado vira documento JSON no Cosmos DB, pronto para agentes de IA e consultas
de baixa latência.

## Componentes

| Artefato | Papel |
|---|---|
| `fabric/notebook_01_ingestao_lakehouse.ipynb` | Lê os CSVs em `Files/dados_brutos/` e grava tabelas **Delta** no Lakehouse |
| `fabric/notebook_02_sync_cosmosdb.ipynb` | Lê as tabelas Delta, monta 1 documento JSON por ano e faz **upsert** no Cosmos DB via Entra ID |
| `fabric/pipeline_pl_cruzamento_anp_cosmosdb.json` | Pipeline Data Factory Gen2 que encadeia os notebooks com gatilho mensal |
| `fabric/data_agent_config.json` | Instruções/fontes para o Fabric Data Agent (ver docs/06) |

## Pré-requisitos

1. **Workspace Fabric** com capacidade atribuída (mesmo workspace do relatório
   simplifica governança);
2. **Lakehouse** criado: `lh_anp_petroleo`;
3. **Conta Azure Cosmos DB for NoSQL** (ex.: `cosmos-anp`) na mesma região da
   capacidade, quando possível;
4. **Service Principal** (ou identidade gerenciada do workspace) com a role
   `Cosmos DB Built-in Data Contributor` no recurso do Cosmos;
5. **Key Vault** para o secret do SPN (`kv-anp`, secret `cosmos-sp-secret`).

## Passo 1 — Subir os arquivos

Faça upload dos CSVs de `data/processed/` para
`lh_anp_petroleo → Files → dados_brutos/`
(OU crie um **shortcut** OneLake/ADLS apontando para o storage corporativo onde
o ETL deposita os CSVs — preferível em produção).

## Passo 2 — Notebook 01 (ingestão)

1. New notebook no workspace; anexe ao Lakehouse `lh_anp_petroleo`;
2. Importe o conteúdo de `notebook_01_ingestao_lakehouse.ipynb`;
3. Execute — cria/atualiza as tabelas Delta:
   `fato_mensal`, `fato_anual`, `dim_fases_campos`, `dim_campos`;
4. Confira a saída de validação (soma anual de produção).

## Passo 3 — Provisionar o Cosmos DB

```bash
# CLI alternativa (ou faça pelo portal)
az cosmosdb create --name cosmos-anp --resource-group rg-anp
az cosmosdb sql database create --account-name cosmos-anp --name anp -g rg-anp
az cosmosdb sql container create \
  --account-name cosmos-anp --database-name anp -g rg-anp \
  --name cruzamento_petroleo --partition-key-path /ano \
  --throughput 400
```

Conceder RBAC ao Service Principal:

```bash
az cosmosdb sql role assignment create \
  --account-name cosmos-anp -g rg-anp \
  --role-definition-name "Cosmos DB Built-in Data Contributor" \
  --scope "/" \
  --assignee-principal-type ServicePrincipal \
  --assignee-object-id <object-id-do-SPN>
```

## Passo 4 — Notebook 02 (sync)

Edite no notebook:
- `COSMOS_ENDPOINT` (Keys → URI da conta);
- `TENANT_ID` / `CLIENT_ID` do SPN;
- Key Vault/secret conforme seu ambiente.

Execute: o notebook lê as tabelas Delta, constrói os documentos (mesmo schema do
`data/processed/cosmosdb/cruzamento_anp_2020_2025.json`) e faz `upsert_item`.
O smoke test final consulta o container e imprime o resumo por ano.

> **Por que upsert?** Execuções repetidas são idempotentes: reprocessar o mesmo
> ano substitui o documento sem duplicar (id = `anp-petroleo-YYYY`).

## Passo 5 — Pipeline agendado

Crie um pipeline no workspace e replique as atividades do
[`pipeline_pl_cruzamento_anp_cosmosdb.json`](../fabric/pipeline_pl_cruzamento_anp_cosmosdb.json):

```
tg_mensal_anp (dia 5, 04h UTC)
   └─ ingestao_lakehouse (notebook 01)
        └─ sync_cosmosdb (notebook 02)   [onSuccess]
```

Políticas: timeout 1h, retry 2× intervalo 3 min na etapa de sync.

## Alternativas nativas (quando usar)

| Recurso | Quando escolher |
|---|---|
| **Cosmos DB artifact dentro da Fabric** | Provisiona banco/container direto do portal Fabric (mesma experiência unificada); o notebook continua sendo o carregador |
| **Mirroring for Cosmos DB** (Cosmos → Fabric/OneLake) | Sentido inverso: expor o Cosmos como tabela somente-leitura na Fabric p/ Spark/SQL sem mover dados |
| **Copy Activity nativo Cosmos↔OneLake** | Cargas simples sem transformação — nosso caso precisa montar documento aninhado, por isso notebook |

## Custos e dimensionamento

- Container em **serverless** ou 400 RU/s manual atende folgado: são 6 documentos
  (~50 KB cada). Upsert mensal ≈ centenas de RUs.
- Consultas de agente (`SELECT ... WHERE c.ano=@ano`) consomem ~2–3 RU por leitura.

## Segurança

- Nenhuma chave primária em código — apenas Entra ID (RBAC);
- Secret do SPN exclusivamente via Key Vault;
- Habilitar diagnostic logs da conta Cosmos para auditoria de escrita;
- Private Endpoint se a política exigir rede privada.
