# 01 — Arquitetura da solução

## Visão geral

A solução conecta três mundos em um fluxo único de dados públicos:

1. **Extração** dos dados oficiais da ANP (planilhas estatísticas + dados abertos
   da Fase de Desenvolvimento e Produção);
2. **Curadoria** local em CSVs/JSON padronizados (ETL Python reprodutível);
3. **Consumo analítico** via Power BI publicado na intranet corporativa;
4. **Materialização** do resultado no **Azure Cosmos DB for NoSQL** através do
   **Microsoft Fabric**, servindo como fonte para o **Agente de Análise** (IA).

## Fluxo end-to-end

```mermaid
flowchart TD
    subgraph ANP["ANP — fontes oficiais"]
        A1["Importações/Exportações\n(barris) XLSX"]
        A2["Produção nacional\n(barris) XLS"]
        A3["Fase de Desenvolvimento\ne Produção — campos CSV"]
    end

    subgraph ETL["ETL local (Python)"]
        B1["01_extracao_transformacao.py\n→ CSVs consolidados"]
        B2["02_gera_json_cosmosdb.py\n→ JSON documents"]
    end

    subgraph PBI["Power BI Service"]
        C1["Modelo semântico\n(FatoMensal, Calendario,\nDimFasesCampos, DimCampos)"]
        C2["Relatório\n3 páginas"]
    end

    subgraph WEB["Intranet"]
        D1["Página interna\n(index.html + powerbi-client)"]
        D2["API Embed Token\n(Service Principal)"]
    end

    subgraph FABRIC["Microsoft Fabric"]
        E1["Lakehouse\n(tabelas Delta)"]
        E2["Pipeline agendado\n(notebooks 01 e 02)"]
        E3["Data Agent / Agente IA"]
    end

    COSMOS["Azure Cosmos DB for NoSQL\ncontainer: cruzamento_petroleo\npartition: /ano"]

    A1 --> B1
    A2 --> B1
    A3 --> B1
    B1 --> C1
    C1 --> C2
    C2 --> D1
    D2 -.emite token.-> D1
    B1 --> E1
    B2 --> COSMOS
    E1 -->|"notebook 02"| COSMOS
    E2 --> E1
    E1 --> E3
    COSMOS --> E3
```

## Camadas e responsabilidades

| Camada | Componente | Responsabilidade |
|---|---|---|
| Fonte | Planilhas ANP | Dados brutos oficiais, atualização mensal |
| Ingestão | `scripts/*.py` | Parsing do layout “relatório”, tipagem, validações |
| Armazenamento curado | `data/processed/` | Fato mensal/anual + dimensões + JSON Cosmos |
| Analítico | Modelo semântico Power BI | Medidas DAX do cruzamento; governança via workspace |
| Apresentação | Página intranet | Embed seguro do relatório (`app owns data`) |
| Nuvem | Fabric Lakehouse + Pipeline | Reprocessamento agendado na nuvem |
| NoSQL | Cosmos DB container | Documentos por ano; baixa latência p/ agentes |
| IA | Fabric Data Agent / AI Foundry | Perguntas em linguagem natural sobre o cruzamento |

## Princípios adotados

- **Reprodutibilidade**: todo dado derivado nasce de script versionado — nenhum
  valor foi digitado manualmente.
- **Validação dupla**: os totais anuais são confrontados com números publicados
  pela própria ANP (Boletim Mensal, Anuário Estatístico).
- **Segurança**: embed interno com Service Principal + capacity; acesso ao
  Cosmos DB somente via Entra ID (RBAC), sem chaves primárias em código.
- **Baixo acoplamento**: a página web só depende do endpoint interno de token;
  o Cosmos DB é alimentado pelo pipeline da Fabric, não pela página.

## Frequência de atualização

| Processo | Frequência | Gatilho |
|---|---|---|
| Publicação ANP | Mensal (dia subsequente ao mês de referência) | — |
| ETL local → CSVs | Sob demanda / CI | Execução manual ou pipeline GitHub Actions |
| Refresh Power BI | Diário (após carga) | Gateway/agendamento do dataset |
| Pipeline Fabric → Cosmos DB | Mensal (dia 5, 04h UTC) | ScheduleTrigger do pipeline |
