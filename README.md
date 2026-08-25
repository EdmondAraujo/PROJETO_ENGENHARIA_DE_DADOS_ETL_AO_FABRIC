# Cruzamento ANP — Produção × Importações/Exportações de Petróleo (2020–2025)

> **Power BI (intranet) → Microsoft Fabric → Azure Cosmos DB → Análise por Agente de IA**

Projeto completo que cruza os **dados estatísticos da ANP** (importações e exportações
de petróleo em barris) com a **produção nacional** e a **Fase de Desenvolvimento e
Produção** (campos contratados), no período **2020–2025**, e entrega:

1. **Modelo Power BI** pronto para publicação em página web **intranet**;
2. **Código Microsoft Fabric** para levar o resultado ao **Azure Cosmos DB for NoSQL**,
   seguindo o modelo *“Análise de Agente com Power BI e Microsoft Fabric”*
   (BI empresarial construído/analisado com IA);
3. **Documentação técnica detalhada** para publicação no GitHub.

---

## 📊 Resultado do cruzamento (validado contra números oficiais ANP)

| Ano | Produção (bi bbl) | Exportação (mi bbl) | Importação (mi bbl) | Cobertura export. | Campos em Produção | Campos em Desenv. |
|----:|------------------:|--------------------:|--------------------:|------------------:|-------------------:|------------------:|
| 2020 | 1,076 | 500,4 | 49,1  | 46,5% | 275 | 1  |
| 2021 | 1,060 | 482,9 | 59,6  | 45,5% | 280 | 4  |
| 2022 | 1,103 | 491,2 | 100,3 | 44,5% | 288 | 5  |
| 2023 | 1,242 | 581,9 | 105,9 | 46,9% | 292 | 6  |
| 2024 | 1,229 | 637,3 | 103,2 | 51,9% | 297 | 8  |
| 2025 | 1,376 | 701,8 | 89,9  | 51,0% | 301 | 11 |

**Validação** (confronto com valores publicados pela ANP):
- Produção 2025: **3,77 mi bbl/dia** ✔️ (Boletim Mensal dez/2025 — recorde histórico)
- Produção 2024: 3,36 mi bbl/dia ✔️ · Exportação 2024: 1,74 mi bbl/dia ✔️
- Importação 2024: **282 mil bbl/dia** ✔️ (Anuário Estatístico 2025)
- Campos ativos derivados do CSV oficial `extracao-campo.csv` (dados abertos).

---

## 🗂️ Estrutura do repositório

```
├── data/
│   ├── raw/                          # Arquivos originais baixados da ANP
│   │   ├── importacoes-exportacoes-b.xlsx
│   │   ├── producao-petroleo-b.xls
│   │   └── extracao-campo.csv
│   └── processed/                    # Dados consolidados (entrada do Power BI)
│       ├── fato_mensal_2020_2025.csv     # 72 meses × produção/import/export/balança
│       ├── fato_anual_2020_2025.csv      # agregado anual + YoY + indicadores
│       ├── dim_campos_fase_anual.csv     # nº campos por ano × fase contratual
│       ├── dim_campos.csv                # dimensão completa dos 442 campos
│       ├── dim_campos_bacia.csv          # campos em produção por bacia × ambiente
│       └── cosmosdb/cruzamento_anp_2020_2025.json   # documentos p/ Cosmos DB
├── scripts/
│   ├── 01_extracao_transformacao.py  # ETL: planilhas ANP → CSVs consolidados
│   └── 02_gera_json_cosmosdb.py      # CSVs → JSON documents (Cosmos DB)
├── powerbi/
│   ├── consultas-m/consultas_powerbi.m   # Power Query M das 6 tabelas
│   └── dax/
│       ├── medidas.dax                   # 18 medidas DAX do cruzamento
│       └── tabela_calendario.dax         # Calendário (alternativa em DAX)
├── web/
│   ├── index.html                        # Página intranet que hospeda o relatório
│   ├── embed.js                          # Integração powerbi-client (embed)
│   └── api-token-exemplo/                # Endpoint C# que emite Embed Token
├── fabric/
│   ├── notebook_01_ingestao_lakehouse.ipynb   # CSVs → tabelas Delta
│   ├── notebook_02_sync_cosmosdb.ipynb        # Delta → Cosmos DB (Entra ID)
│   ├── pipeline_pl_cruzamento_anp_cosmosdb.json  # Pipeline agendado
│   ├── data_agent_config.json                 # Config do Agente de Análise
│   └── requirements.txt
└── docs/
    ├── 01-arquitetura.md             # Visão end-to-end + fluxos
    ├── 02-fontes-de-dados.md         # Fontes, metodologia e validação
    ├── 03-modelo-powerbi.md          # Modelagem, medidas e páginas do relatório
    ├── 04-embed-web-interna.md       # Como publicar na intranet (com segurança)
    ├── 05-fabric-cosmosdb.md         # Passo a passo Fabric → Cosmos DB
    └── 06-agente-analise.md          # Modelo "Análise de Agente" aplicado
```

---

## 🚀 Início rápido

### 1) Regenerar os dados consolidados

```bash
pip install -r fabric/requirements.txt
python scripts/01_extracao_transformacao.py   # ETL → data/processed/*.csv
python scripts/02_gera_json_cosmosdb.py       # → data/processed/cosmosdb/*.json
```

### 2) Montar o modelo Power BI

Siga **[docs/03-modelo-powerbi.md](docs/03-modelo-powerbi.md)**:
cole as consultas M (`powerbi/consultas-m/consultas_powerbi.m`) no Editor do
Power Query, crie as medidas DAX (`powerbi/dax/medidas.dax`), monte as páginas
sugeridas e publique no workspace.

### 3) Publicar na página web interna

Siga **[docs/04-embed-web-interna.md](docs/04-embed-web-interna.md)**:
hospede `web/index.html` no servidor interno e configure o endpoint de
Embed Token (`web/api-token-exemplo/Program.cs`).

### 4) Levar o resultado ao Azure Cosmos DB via Fabric

Siga **[docs/05-fabric-cosmosdb.md](docs/05-fabric-cosmosdb.md)**:
crie workspace/Lakehouse na Fabric, suba os notebooks
(`fabric/notebook_01...ipynb` e `notebook_02...ipynb`), provisione o container
do Cosmos DB e agende o pipeline.

### 5) Habilitar a análise por Agente de IA

Siga **[docs/06-agente-analise.md](docs/06-agente-analise.md)** usando
`fabric/data_agent_config.json`.

---

## 🔗 Fontes oficiais (ANP)

| Dado | Arquivo local | URL oficial |
|---|---|---|
| Importações & Exportações de petróleo (barris) | `data/raw/importacoes-exportacoes-b.xlsx` | [gov.br/anp — dados estatísticos IE (b)](https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-estatisticos/de/ie/importacoes-exportacoes-b.xlsx) |
| Produção nacional de petróleo e LGN (barris) | `data/raw/producao-petroleo-b.xls` | [gov.br/anp — produção petróleo (b)](https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-estatisticos/de/ppg/producao-petroleo-b.xls) |
| Fase de Desenvolvimento e Produção (campos) | `data/raw/extracao-campo.csv` | [gov.br/anp — dados abertos FDP](https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos/arquivos/arquivos-fase-de-desenvolvimento-e-producao/informacoes-sobre-campos/extracao-campo.csv) |

Dados atualizados mensalmente pela ANP (arquivos capturados em 25/08/2026,
referência “atualizado em 31/7/2026”).

---

## 🧠 Decisões técnicas (resumo)

- **Planilhas ANP** têm layout “relatório” (tabelas empilhadas, títulos fora da
  grade). O ETL detecta cada tabela pelo cabeçalho `ANO`, valida meses e anos e
  rejeita linhas de total/notas.
- **Granularidade**: fato mensal (72 registros) cruzado com dimensão anual de
  fases contratuais via `TREATAS` (evita relacionamento many-to-many).
- **Cosmos DB**: 1 documento por ano (partition key `/ano`), autenticação
  **somente Entra ID** (sem chaves primárias no código).
- **Embed interno**: padrão *app owns data* (Power BI Embedded) com Service
  Principal + capacity Fabric/Premium — não usa “Publish to web”.

## ⚖️ Licença e uso

Dados públicos da ANP (dados abertos do governo brasileiro). Código deste
repositório: uso livre para fins internos e educacionais.
