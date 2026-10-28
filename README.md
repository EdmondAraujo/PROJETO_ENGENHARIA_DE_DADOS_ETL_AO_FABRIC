# Pipeline AWS SaaS Sales (Opção A — Pure Python CLI + scikit-learn)

Pipeline completo, production-grade, para ingestão do **AWS SaaS Sales dataset**
(Kaggle: [nnthanh101/aws-saas-sales](https://www.kaggle.com/datasets/nnthanh101/aws-saas-sales)),
modelagem de métricas de funil/conversão SaaS, execução de testes A/B com rigor
estatístico e um **loop de minimização do Mean Squared Error (MSE)**.

---

## Stack escolhida (Passo 1)

**Opção A** — script Python puro de CLI com `pandas`, `numpy`, `scikit-learn` e
`scipy`. A **Opção B** foi implementada como um **único produto Streamlit**
(`app.py`) sobre os mesmos módulos de `src/`, sem reescrever estatística nem ML.

---

## Produto (Opção B) — interface Streamlit

O aplicativo `app.py` entrega o pipeline completo via navegador:

```bash
streamlit run app.py
```

Funcionalidades da interface:
1. **Upload de CSV** do dataset Kaggle (ou leitura padrão de `data/SaaS-Sales.csv`).
2. **Visão geral dos dados** — amostra, estatísticas descritivas e distribuição por segmento (proxy de tier).
3. **A/B Test** — gate de SRM (chi-quadrado + binomial exato em células <= 30), z-test de conversão, t-test de ticket médio e veredito executivo (SHIP / KEEP_RUNNING / ITERATE / RERUN).
4. **Modelagem (MSE)** — GridSearchCV (5-fold, `neg_mean_squared_error` para regressão e scorer MSE de probabilidade/Brier para classificação) sobre Ridge / RandomForest / GradientBoosting; seleção do menor MSE de CV; avaliação no hold-out com **MSE, RMSE, R²**; gráfico comparativo treino vs teste e recomendação do modelo com menor MSE.
5. **Relatório Executivo** — markdown gerado automaticamente com download.

Requisitos adicionais (já incluídos em `requirements.txt`): `streamlit`, `plotly`.

---

## Pré-requisitos

---

## Estrutura do repositório

```
├── README.md                    Este arquivo
├── requirements.txt             Dependências versionadas
├── main.py                      CLI (argparse): orquestra o pipeline
├── data/
│   └── SaaS-Sales.csv           Dataset extraído do zip do Kaggle
├── src/
│   ├── __init__.py
│   ├── ingestion.py             Carrega e valida o CSV do Kaggle
│   ├── preprocessing.py         Limpeza, features SaaS, alvo de conversão
│   ├── ab_test.py               Split 50/50, gate SRM, z-test, t-test
│   ├── modeling.py              GridSearchCV + CV otimizando neg MSE
│   ├── report.py                Relatório executivo em markdown
│   └── pipeline.py              Orquestração end-to-end
└── tests/
    ├── __init__.py
    └── test_audit.py            Bateria de auditoria (pytest)
```

---

## Pré-requisitos

Python 3.9+ e:

```bash
pip install -r requirements.txt
```

## Executar o pipeline

Coloque o dataset em `data/SaaS-Sales.csv` (extraído do zip baixado do Kaggle) e rode:

```bash
python main.py
```

Saída: um **relatório executivo em markdown** no terminal com:
1. Dataset — shape, período, ticket médio, segmentos (proxy de tier).
2. A/B Test — gate de SRM (chi-quadrado + binomial exato em células <= 30),
   z-test de conversão, t-test de ticket médio, veredito executivo.
3. Modelagem Preditiva — loop de minimização de MSE (Ridge / RandomForest /
   GradientBoosting via GridSearchCV, 5-fold CV), seleção do menor MSE de CV,
   avaliação no hold-out: **MSE, RMSE, R²** (treino vs teste) + diagnóstico de
   overfitting; classificação de conversão (MSE de probabilidade/Brier,
   acurácia, ROC AUC).
4. Recomendação executiva e notas metodológicas.

Códigos de saída: `0` = sucesso; `2` = gate de SRM falhou (leituras de negócio do
A/B suprimidas; a modelagem ainda roda).

Opções:
```bash
python main.py --data data/SaaS-Sales.csv --seed 42      # padrão
python main.py --no-ab                                   # só ingestão + modelagem
python main.py --seed 123                                # outra seed
```

## Executar os testes de auditoria

```bash
pip install pytest
python -m pytest tests/ -q
```

---

## Contrato de integridade (ordem de execução)

1. **Ingestão** → valida schema obrigatório (`Customer ID`, `Sales`, `Profit`,
   `Order Date`, `Segment`, …) antes de seguir.
2. **Pré-processamento** → `customer_id` é identificador, **não entra como feature**.
   Split treino/teste **por Customer ID** (um cliente nunca aparece nos dois
   conjuntos — sem vazamento).
3. **A/B test** → hash determinístico do `Customer ID` (50/50, reprodutível).
   **Gate de SRM primeiro**: qui-quadrado (df=1); se alguma célula <= 30, o
   teste binomial exato bicaudal é o gate. Métricas de negócio só se o SRM passar.
4. **Modelagem** → GridSearchCV com `scoring='neg_mean_squared_error'` para regressão (Sales/Profit) e scorer customizado de MSE de probabilidade (Brier) para classificação (Conversão), sobre Ridge / RandomForest / GradientBoosting; seleção do **menor MSE de CV**;
   avaliação final no hold-out intocado com
   `sklearn.metrics.mean_squared_error`. Relato de **MSE, RMSE, R²**.
5. **Relatório** → markdown no terminal.

---

## Alvos modelados (minimização de MSE)

| Alvo | Tipo | Métrica principal |
|------|------|-------------------|
| `Sales` | Regressão | MSE / RMSE / R² |
| `Profit` | Regressão | MSE / RMSE / R² |
| `high_value` (conversão binária por cliente) | Classificação (probabilidade) | MSE de probabilidade (Brier) / Acurácia / ROC AUC |

Ambos os alvos de regressão e o de converção são otimizados buscando o **menor
erro quadrático médio (MSE)**.

---

## Auditoria

O módulo `tests/test_audit.py` valida:
- Carregamento e schema do dataset (colunas do Kaggle, datas parseadas sem NaT).
- Ausência de vazamento de cliente entre treino e teste.
- Gate de SRM (balanceado passa, desbalanceado falha, células pequenas usam
  binomial exato).
- Cálculo do MSE idêntico a `sklearn.metrics.mean_squared_error` e não-negativo.
- MSE de teste ≥ 0, R² ≤ 1, melhor modelo escolhido pelo menor MSE de CV.
- Ausência de `# TODO` / placeholders no código-fonte.

---

## Notas metodológicas

- MSE calculado com `sklearn.metrics.mean_squared_error` (média dos quadrados dos
  resíduos), não reimplementado manualmente.
- OneHotEncoder / StandardScaler ajustados **apenas no treino**, dentro de cada
  fold do GridSearchCV (sem data leakage).
- O hold-out de teste é intocado até a avaliação final.
- O gate de SRM é executado **antes** de qualquer métrica de negócio.
- Seed fixa (`--seed`, default 42) para reprodutibilidade total.
