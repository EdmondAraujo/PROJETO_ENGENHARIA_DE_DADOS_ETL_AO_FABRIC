# 02 — Fontes de dados, metodologia e validação

## Fontes oficiais utilizadas

Os três arquivos de referência do trabalho correspondem a publicações oficiais
da ANP, baixados em 25/08/2026 (dados “atualizados em 31/7/2026”):

### 1. Dados Estatísticos — Importações & Exportações (barris)
- **Arquivo**: `data/raw/importacoes-exportacoes-b.xlsx` (XLSX, 1 aba, ~1.200 linhas, 19 tabelas empilhadas)
- **URL**: https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-estatisticos/de/ie/importacoes-exportacoes-b.xlsx
- **Conteúdo relevante ao projeto**:
  - `Importação de petróleo - 2000-2026 (b)` — tabela mensal
  - `Exportação de petróleo - 2000-2026 (b)` — tabela mensal
- **Notas da própria fonte**: petróleo inclui óleo e condensado; não inclui LGN;
  dados de comércio exterior: Secretaria de Comércio Exterior (Secex).

### 2. Dados Estatísticos — Produção Nacional de Petróleo e LGN (barris)
- **Arquivo**: `data/raw/producao-petroleo-b.xls` (XLS legado)
- **URL**: https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-estatisticos/de/ppg/producao-petroleo-b.xls
- **Tabela usada**: primeira do arquivo — filtros `BRASIL` / `PETRÓLEO TOTAL (b)`,
  série mensal 2000–2026. A segunda tabela (LGN) não entra no cruzamento.

### 3. Dados Abertos — Fase de Desenvolvimento e Produção (campos)
- **Arquivo**: `data/raw/extracao-campo.csv` (442 campos × 15 colunas)
- **URL**: https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos/arquivos/arquivos-fase-de-desenvolvimento-e-producao/informacoes-sobre-campos/extracao-campo.csv
- **Colunas**: código/nome do campo, bacia, estado, operador, ambiente (mar/terra),
  rodada, contrato, situação (`Produção`, `Desenvolvimento`, `Em Devolução`,
  `Em devolução, licitado`), datas de assinatura, término de fase, início e
  término de produção.

## Metodologia de extração

As planilhas da ANP são relatórios formatados para leitura humana: várias
tabelas empilhadas na mesma aba, títulos fora da grade, separadores visuais
(`xxxx...`) e notas de rodapé. O ETL (`scripts/01_extracao_transformacao.py`)
implementa um parser genérico:

1. Localiza toda linha cuja célula contém exatamente `ANO` → cabeçalho de tabela;
2. Na linha seguinte identifica a coluna `Mês/MÊS/Meses` e as colunas-anos numéricas;
3. Consome as linhas seguintes enquanto o rótulo for um mês válido
   (`janeiro…dezembro`, acento-insensível), parando em `Total do Ano` /
   `Média do Ano`;
4. Reconstrói o título de cada tabela pelas linhas de texto acima do cabeçalho
   (atravessando no máximo um separador visual);
5. Seleciona a tabela correta por prefixo do título
   (`Importação de petróleo`, `Exportação de petróleo`, `PETRÓLEO TOTAL`);
6. Filtra os anos-alvo (2020–2025), valida completude (72 meses, zero nulos) e
   grava CSVs UTF-8 com ponto decimal.

### Derivação das fases contratuais por ano

Para cada ano Y:
- **Campos em Produção** = campos com `SITUACAO_CAMPO = 'Produção'`,
  `DATA_INICIO_PRODUCAO ≤ 31/12/Y` e `TERMINO_FASE > 31/12/Y`;
- **Campos em Desenvolvimento** = campos com `SITUACAO_CAMPO = 'Desenvolvimento'`
  e produção já iniciada até Y;
- Campos `Em Devolução` / `Em devolução, licitado` ficam fora dos dois
  quantitativos (regra documentada e facilmente ajustável no script).

## Validação contra publicações oficiais

| Métrica | Valor calculado | Valor oficial ANP | Referência |
|---|---|---|---|
| Produção 2025 | 3,77 mi bbl/d | **3,770 mi bbl/d** | Boletim Mensal dez/2025 (recorde histórico) |
| Produção 2024 | 3,36 mi bbl/d | 3,4 mi bbl/d | Anuário Estatístico 2025 |
| Exportação 2024 | 1,74 mi bbl/d | 1,7 mi bbl/d | Anuário Estatístico 2025 |
| Importação 2024 | 282 mil bbl/d | **282 mil bbl/d** | Anuário Estatístico 2025 |
| Produção 2023 | 1,242 bi bbl | ≈197,4 mi m³ (=1,242 bi bbl) | Conversão 1 m³ = 6,2898 bbl |

Divergências menores (<1%) decorrem de arredondamento nas publicações.

## Dicionário de dados (saídas)

### `fato_mensal_2020_2025.csv`
| Coluna | Tipo | Descrição |
|---|---|---|
| DATA | date (ISO) | Primeiro dia do mês |
| ANO / TRIMESTRE / MES_NUM / MES_NOME | int/text | Atributos de tempo |
| PRODUCAO_BARRIS | double | Produção nacional de petróleo no mês (barris) |
| IMPORTACAO_BARRIS | double | Importação de petróleo no mês (barris) |
| EXPORTACAO_BARRIS | double | Exportação de petróleo no mês (barris) |
| BALANCA_COMERCIAL_BARRIS | double | Exportação − Importação (barris) |

### `fato_anual_2020_2025.csv`
Acumula o fato mensal por ano e acrescenta `*_YOY_PCT` (variação % ano contra
ano), `COBERTURA_EXPORT_PCT` (exportação ÷ produção) e
`DEPENDENCIA_IMPORT_PCT` (importação ÷ produção), além das colunas de fases
contratuais.

### `cosmosdb/cruzamento_anp_2020_2025.json`
Um documento por ano (`id = anp-petroleo-YYYY`, partition `/ano`) com blocos
`producao`, `comercio_exterior`, `fases_contratuais`, `indicadores` e série
`mensal`.

## Limitações conhecidas

- O CSV oficial de campos não traz volumes produzidos por campo — por isso o
  volume vem da planilha de produção nacional e a dimensão de fases contribui
  com quantitativos e contexto contratual.
- Séries 2026 existem parcialmente nas fontes; o escopo do projeto é 2020–2025.
