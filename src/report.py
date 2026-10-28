#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
src/report.py — Camada 5: relatório executivo em markdown no terminal.

Imprime um resumo estruturado contendo:
  - shape do dataset e colunas;
  - saúde do A/B test (gate de SRM, split, p-value, lift de conversão, ticket médio);
  - melhor modelo por alvo, hiperparâmetros, MSE/RMSE/R² (treino vs teste);
  - feature importance (quando disponível) e recomendação executiva.
"""

from __future__ import annotations

from typing import Optional

import pandas as pd

from .ab_test import (  # noqa: E402
    ALPHA,
    ABTestResult,
    ConversionResult,
    MeanResult,
    SRMResult,
)
from .modeling import (  # noqa: E402
    ClassificationResult,
    ModelingResults,
    RegressionResult,
)


def _fmt_pct(x: Optional[float]) -> str:
    if x is None:
        return "n/d"
    return f"{x*100:+.2f} pp"


def _fmt_num(x, nd: int = 4) -> str:
    if x is None:
        return "n/d"
    try:
        return f"{float(x):,.{nd}f}"
    except (TypeError, ValueError):
        return str(x)


def report_dataset(df: pd.DataFrame, prepared) -> str:
    lines = []
    lines.append("## 1. Dataset — AWS SaaS Sales (Kaggle: nnthanh101/aws-saas-sales)")
    lines.append("")
    lines.append(f"- **Linhas (pedidos):** {len(df):,}")
    lines.append(f"- **Colunas:** {df.shape[1]}")
    lines.append(f"- **Clientes únicos:** {prepared.df_customers['Customer ID'].nunique():,}")
    lines.append(f"- **Período:** {df['Order Date'].min():%d/%m/%Y} a {df['Order Date'].max():%d/%m/%Y}")
    lines.append(f"- **Ticket médio (Sales):** ${df['Sales'].mean():,.2f}")
    lines.append(f"- **Lucro médio (Profit):** ${df['Profit'].mean():,.2f}")
    lines.append(f"- **Taxa de desconto média:** {df['Discount'].mean()*100:.1f}%")
    lines.append("")
    lines.append("### Segmentos (proxy de subscription tier)")
    seg = df["Segment"].value_counts()
    for s, n in seg.items():
        lines.append(f"- **{s}:** {n:,} pedidos ({n/len(df)*100:.1f}%)")
    lines.append("")
    lines.append("### Alvos modelados (minimização de MSE)")
    lines.append(f"- **Sales** (valor do pedido): regressão → MSE/RMSE/R²")
    lines.append(f"- **Profit** (lucro): regressão → MSE/RMSE/R²")
    lines.append(f"- **high_value** (conversão binária por cliente): probabilidade → MSE (Brier) / Acurácia / ROC AUC")
    lines.append("")
    return "\n".join(lines)


def report_ab(ab: Optional[ABTestResult]) -> str:
    lines = []
    lines.append("## 2. A/B Test — Saúde do Experimento")
    lines.append("")
    if ab is None:
        lines.append("A/B test desativado pelo usuário (--no-ab).")
        lines.append("")
        return "\n".join(lines)

    srm = ab.srm
    lines.append(f"- **Método de alocação:** hash determinístico do Customer ID (50/50, seed fixa)")
    lines.append(f"- **Clientes Control:** {srm.observed_control:,}")
    lines.append(f"- **Clientes Treatment:** {srm.observed_treatment:,}")
    lines.append(f"- **Esperado (50/50):** {srm.expected_control:,.0f} / {srm.expected_treatment:,.0f}")
    lines.append(f"- **Teste SRM:** {srm.method}")
    lines.append(f"- **Chi²:** {srm.chi2:.4f} | **p-value:** {srm.p_value:.6f}")
    if srm.exact_p_value is not None:
        lines.append(f"- **Binomial exato (gate células <=30):** p={srm.exact_p_value:.6f}")
    lines.append(f"- **Gate SRM:** {'[FALHOU] amostra desbalanceada' if srm.srm_flagged else '[APROVADO] split íntegro'}")
    lines.append("")

    if srm.srm_flagged:
        lines.append("**Veredito: RERUN** — métricas de negócio suprimidas por integridade de tráfego.")
        lines.append("")
        return "\n".join(lines)

    conv = ab.conversion
    mean_sales = ab.mean_sales
    lines.append("### Teste de Conversão (taxa de clientes high_value)")
    lines.append(f"- **Control:** {conv.control_rate*100:.2f}% | **Treatment:** {conv.treatment_rate*100:.2f}%")
    lines.append(f"- **Lift absoluto:** {_fmt_pct(conv.abs_lift)} | **Relativo:** {conv.rel_lift*100:+.1f}%")
    lines.append(f"- **z:** {conv.z_stat:.4f} | **p-value:** {conv.p_value:.6f} | **Significativo (α={ALPHA}):** {'Sim' if conv.significant else 'Não'}")
    lines.append(f"- **IC 95%:** [{conv.ci_low*100:+.2f} pp, {conv.ci_high*100:+.2f} pp]")
    lines.append("")
    lines.append("### Teste de Ticket Médio (Sales por pedido, Welch t-test)")
    lines.append(f"- **Control:** ${mean_sales.control_mean:,.2f} | **Treatment:** ${mean_sales.treatment_mean:,.2f}")
    lines.append(f"- **Diferença:** ${mean_sales.abs_diff:+,.2f}")
    lines.append(f"- **t:** {mean_sales.t_stat:.4f} | **p-value:** {mean_sales.p_value:.6f} | **Significativo:** {'Sim' if mean_sales.significant else 'Não'}")
    lines.append(f"- **IC 95%:** [${mean_sales.ci_low:+,.2f}, ${mean_sales.ci_high:+,.2f}]")
    lines.append("")
    lines.append(f"### Veredito Executivo: **{ab.decision}**")
    linhas_dec = {
        "SHIP": "Resultado significativo e consistente: considerar rollout para 100% do tráfego.",
        "KEEP_RUNNING": "Sinal significativo, mas power/amostra insuficiente: continuar coleta.",
        "ITERATE": "Sem evidência suficiente: iterar a variação e reavaliar o MDE.",
        "RERUN": "Falha de integridade do split: auditar assignment antes de decidir.",
    }
    lines.append(f"- {linhas_dec.get(ab.decision, '')}")
    lines.append("")
    return "\n".join(lines)


def _regression_block(title: str, r: RegressionResult) -> list:
    lines = [f"### {title}"]
    lines.append(f"- **Melhor modelo:** {r.best_model_name}")
    lines.append(f"- **Hiperparâmetros (GridSearchCV):** {r.best_params}")
    lines.append(f"- **MSE de CV (seleção):** {r.best_cv_mse:,.6f}")
    lines.append("")
    lines.append("#### Avaliação no hold-out (teste, não visto no treino/CV)")
    lines.append(f"- **MSE (treino):** {r.mse_train:,.6f} | **RMSE:** {r.rmse_train:,.6f} | **R²:** {r.r2_train:.4f}")
    lines.append(f"- **MSE (teste):**  {r.mse_test:,.6f} | **RMSE:** {r.rmse_test:,.6f} | **R²:** {r.r2_test:.4f}")
    lines.append(f"- **Razão overfitting (MSE_teste / MSE_treino):** {r.overfitting_ratio:.3f}")
    interpreta = ("baixo (boa generalização)" if r.overfitting_ratio < 1.25
                  else "moderado" if r.overfitting_ratio < 1.5
                  else "alto (possível overfitting)")
    lines.append(f"- **Diagnóstico de generalização:** {interpreta}")
    lines.append("")
    return lines


def _classification_block(title: str, c: ClassificationResult) -> list:
    lines = [f"### {title}"]
    lines.append(f"- **Melhor modelo:** {c.best_model_name}")
    lines.append(f"- **Hiperparâmetros (GridSearchCV):** {c.best_params}")
    lines.append(f"- **MSE de CV (seleção, Brier-like):** {c.best_cv_mse:,.6f}")
    lines.append("")
    lines.append("#### Avaliação no hold-out (teste)")
    lines.append(f"- **MSE probabilidade vs 0/1 (teste):** {c.mse_test_prob:,.6f}")
    lines.append(f"- **Acurácia (teste):** {c.accuracy_test:.4f}")
    roc = "n/d" if c.roc_auc_test is None else f"{c.roc_auc_test:.4f}"
    lines.append(f"- **ROC AUC (teste):** {roc}")
    lines.append("")
    return lines


def report_modeling(res: ModelingResults) -> str:
    lines = []
    lines.append("## 3. Modelagem Preditiva — Loop de Minimização de MSE")
    lines.append("")
    lines.append("Procedimento: GridSearchCV (5-fold, scoring=`neg_mean_squared_error` para regressão e MSE de probabilidade/Brier para classificação)")
    lines.append("sobre candidatos Ridge / RandomForest / GradientBoosting; seleção do")
    lines.append("menor MSE de CV; avaliação final no hold-out de teste (sem vazamento).")
    lines.append("")
    lines.extend(_regression_block("Regressão — Sales (valor do pedido)", res.sales))
    lines.extend(_regression_block("Regressão — Profit (lucro)", res.profit))
    lines.extend(_classification_block("Classificação — Conversão (high_value)", res.conversion))
    lines.append("### Recomendação Executiva")
    lines.append("")
    modelos = [res.sales, res.profit]
    best_reg = min(modelos, key=lambda r: r.mse_test)
    lines.append(f"- O modelo com **menor MSE de teste** é **{best_reg.best_model_name}** para **{best_reg.target}** (MSE = {best_reg.mse_test:,.4f}, RMSE = {best_reg.rmse_test:,.4f}, R² = {best_reg.r2_test:.4f}).")
    lines.append(f"- O modelo de conversão obteve **MSE (probabilidade)** = {res.conversion.mse_test_prob:,.6f} e **acurácia** = {res.conversion.accuracy_test:.4f}.")
    if res.sales.overfitting_ratio > 1.5 or res.profit.overfitting_ratio > 1.5:
        lines.append("- **Atenção:** razão de overfitting elevada em pelo menos um alvo de regressão; considerar regularização ou mais dados.")
    else:
        lines.append("- **Generalização adequada:** razões de overfitting dentro de limites aceitáveis (< 1.5).")
    lines.append("")
    return "\n".join(lines)


def build_executive_report(df: pd.DataFrame, prepared,
                           ab: Optional[ABTestResult],
                           res: ModelingResults) -> str:
    """Monta o relatório executivo completo em markdown."""
    parts = [
        "# Relatório Executivo — Pipeline AWS SaaS Sales",
        "",
        report_dataset(df, prepared),
        report_ab(ab),
        report_modeling(res),
        "---",
        "Notas metodológicas:",
        "- O split treino/teste é feito por Customer ID (sem vazamento de cliente).",
        "- OneHotEncoder/StandardScaler são ajustados apenas no treino (dentro de cada fold do GridSearchCV).",
        "- O gate de SRM é executado antes de qualquer métrica de negócio.",
        "- MSE calculado com `sklearn.metrics.mean_squared_error` (média dos quadrados dos resíduos).",
    ]
    return "\n".join(parts)
