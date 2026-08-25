# 03 — Modelo Power BI (modelagem, DAX e relatório)

## 1. Criar o projeto no Power BI Desktop

1. Abra o **Power BI Desktop** → `Transformar dados` → `Editor do Power Query`.
2. Crie uma **Consulta Nula**, renomeie para `Parametros`, abra o
   **Editor Avançado** e cole o primeiro bloco de
   [`powerbi/consultas-m/consultas_powerbi.m`](../powerbi/consultas-m/consultas_powerbi.m),
   ajustando `CAMINHO_DADOS` para a pasta `data/processed/` local
   (ou caminho OneLake — ver §5).
3. Repita para cada bloco: `FatoMensal`, `FatoAnual`, `DimFasesCampos`,
   `DimCampos`, `DimCalendario`.
4. `Página Inicial` → `Fechar e Aplicar`.

> Em ambiente corporativo com Fabric, substitua `File.Contents` por
> `Csv.Document(Web.Contents("https://onelake..."))` apontando para o Lakehouse
> (mesmos arquivos publicados pelo pipeline) — mantém um único ponto de verdade.

## 2. Relacionamentos (Exibição de Modelo)

| De (tabela*coluna) | Para | Cardinalidade | Direção |
|---|---|---|---|
| Calendario[Data] | FatoMensal[DATA] | 1:* | Única |
| DimCampos[SITUACAO_CAMPO] | — | sem relação física (dimensão de apoio) | — |
| DimFasesCampos[ANO] | FatoMensal[ANO] | **sem relação física** — contexto via `TREATAS` | — |

`DimFasesCampos` é anual enquanto o fato é mensal; usar `TREATAS` nas medidas
evita ambiguidade many-to-many e mantém filtros corretos em visuais mistos.

## 3. Medidas DAX

Cole as medidas de [`powerbi/dax/medidas.dax`](../powerbi/dax/medidas.dax)
na tabela `FatoMensal`. Principais:

| Medida | Fórmula-resumo | Uso no relatório |
|---|---|---|
| Produção (bi bbl) | Σ produção ÷ 10⁹ | Cards e linhas |
| Exportação / Importação (bi bbl) | Σ ÷ 10⁹ | Cards e colunas empilhadas |
| Balança Comercial (bi bbl) | Σ(export−import) ÷ 10⁹ | Coluna/linha combinada |
| Cobertura Exportação % | export ÷ produção | Indicador-chave do cruzamento |
| Dependência Importação % | import ÷ produção | Indicador-chave |
| Produção Média (bbl/dia) | média ponderada dias/mês | Comparação com boletins ANP |
| Variação YoY Produção/Export/Import % | vs. `SAMEPERIODLASTYEAR` | Títulos de cartões, tooltips |
| Campos em Produção / Desenvolvimento | `MAX` + `TREATAS(VALUES(FatoMensal[ANO]), DimFasesCampos[ANO])` | Linha secundária nos gráficos |
| Produção Média por Campo (mi bbl/ano) | produção ÷ campos ativos | Análise de produtividade |

## 4. Layout sugerido do relatório (3 páginas)

### Página 1 — Visão Executiva (2020–2025)
- Cartões: Produção (bi bbl), Exportação, Importação, Balança Comercial,
  Variação YoY da produção.
- Gráfico combinado: colunas (produção) × linha (exportação e importação).
- Rosca: Cobertura Exportação % do ano selecionado.

### Página 2 — Cruzamento Mensal
- Segmentações: Ano, Trimestre, Mês.
- Matriz: meses × [Produção, Importação, Exportação, Balança].
- Área mensal: evolução das três séries em barris.
- KPI condicional na dependência de importação (>15% vermelho).

### Página 3 — Fases Contratuais e Campos
- Colunas agrupadas: nº de campos em Produção × Desenvolvimento por ano.
- Mapa/tabela de `DimCampos`: operador, bacia, ambiente, início de produção.
- Dispersão: campos em produção × produção total (produtividade por campo).

## 5. Publicação

1. `Publicar` → workspace dedicado (ex.: `WS_ANP_Petroleo`);
2. Atribua o workspace a uma **capacity** (Fabric F-SKU ou P/EM);
3. Configure refresh agendado alinhado ao pipeline (dia 5, após carga);
4. Siga [docs/04-embed-web-interna.md](04-embed-web-interna.md) para exibir na
   página interna.

## 6. Checklist de qualidade antes de publicar

- [ ] 72 linhas em `FatoMensal`; nenhum nulo nas colunas de barris;
- [ ] Total 2025 confere com Boletim ANP (3,77 mi bbl/d);
- [ ] Medida `Cobertura Exportação %` ≈ 51% em 2025;
- [ ] Segmentação de ano filtra também os cartões de fases contratuais;
- [ ] Nenhum dado sensível no relatório (fonte é pública).
