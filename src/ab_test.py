#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
src/ab_test.py — Camada 3: A/B test e rigor estatístico.

Particiona os clientes em Control / Treatment (50/50) via hash determinístico
do Customer ID (sem viés de espiamento). Executa, nesta ordem:
  1. Gate de SRM (Sample Ratio Mismatch): chi-quadrado (df=1) sobre a alocação;
     quando alguma célula tem <= 30 observações, o teste binomial exato
     bicaudal é o gate (substitui o qui-quadrado assintótico).
  2. Se o SRM passar: z-test de duas proporções (taxa de conversão high_value)
     com IC 95% (Wald) e t-test de diferença de médias (Sales por grupo).

Qualquer leitura de negócio só é emitida após o gate de SRM passar.
"""

from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, asdict
from typing import Optional, Tuple

import numpy as np
import pandas as pd
from scipy import stats

# Parâmetros fixos do experimento.
ALPHA = 0.05
SRM_EXPECTED_SPLIT = (0.5, 0.5)
SRM_MIN_CELL_EXACT = 30  # abaixo disso, o binomial exato é o gate


def assign_group(customer_ids: pd.Series, seed: int = 42) -> pd.Series:
    """Atribui 'control' / 'Treatment' (50/50) por hash determinístico do ID.

    O mesmo customer_id cai sempre no mesmo grupo entre runs (seed fixa).
    """
    def _hash(u: str) -> int:
        return int.from_bytes(
            hashlib.md5(f"{seed}:{u}".encode()).digest()[:4], "big"
        ) % 2

    mapped = customer_ids.astype(str).map(lambda u: "control" if _hash(u) == 0 else "treatment")
    return mapped


@dataclass
class SRMResult:
    observed_control: int
    observed_treatment: int
    expected_control: float
    expected_treatment: float
    chi2: float
    p_value: float
    exact_p_value: Optional[float]
    srm_flagged: bool
    method: str


@dataclass
class ConversionResult:
    metric: str
    control_rate: float
    treatment_rate: float
    abs_lift: float
    rel_lift: float
    z_stat: float
    p_value: float
    ci_low: float
    ci_high: float
    significant: bool


@dataclass
class MeanResult:
    metric: str
    control_mean: float
    treatment_mean: float
    abs_diff: float
    t_stat: float
    p_value: float
    ci_low: float
    ci_high: float
    significant: bool


@dataclass
class ABTestResult:
    srm: SRMResult
    conversion: Optional[ConversionResult]
    mean_sales: Optional[MeanResult]
    decision: str  # "RERUN" | "SHIP" | "KEEP_RUNNING" | "ITERATE"


def srm_check(n_control: int, n_treatment: int) -> SRMResult:
    """Gate de integridade do split 50/50.

    Retorna SRMResult com o método usado e o flag srm_flagged.
    """
    total = n_control + n_treatment
    if total == 0:
        return SRMResult(
            observed_control=0,
            observed_treatment=0,
            expected_control=0.0,
            expected_treatment=0.0,
            chi2=0.0,
            p_value=1.0,
            exact_p_value=None,
            srm_flagged=True,
            method="chi_square_df1",
        )
    exp_c = total * SRM_EXPECTED_SPLIT[0]
    exp_t = total * SRM_EXPECTED_SPLIT[1]
    chi2, p = stats.chisquare(f_obs=[n_control, n_treatment], f_exp=[exp_c, exp_t])
    exact_p = None
    method = "chi_square_df1"
    if min(n_control, n_treatment) <= SRM_MIN_CELL_EXACT:
        exact_p = float(stats.binomtest(n_control, total, 0.5).pvalue)
        method = "binomial_exact_two_sided"
    # Em células pequenas, o exato é o gate; caso contrário, o qui-quadrado.
    flagged = (exact_p < ALPHA) if exact_p is not None else (p < ALPHA)
    return SRMResult(
        observed_control=n_control,
        observed_treatment=n_treatment,
        expected_control=float(exp_c),
        expected_treatment=float(exp_t),
        chi2=float(chi2),
        p_value=float(p),
        exact_p_value=exact_p,
        srm_flagged=bool(flagged),
        method=method,
    )


def _proportion_ztest(
    pc: float, pt: float, nc: int, nt: int
) -> Tuple[float, float, float, float, float]:
    """z-test bicaudal de duas proporções (SE pooled) + IC Wald (SE unpooled)."""
    if nc <= 0 or nt <= 0:
        raise ValueError("Braço vazio: teste de proporção indeterminado.")
    delta = pt - pc
    p_bar = (pc * nc + pt * nt) / (nc + nt)
    se0 = math.sqrt(p_bar * (1 - p_bar) * (1 / nc + 1 / nt))
    z = delta / se0 if se0 > 0 else 0.0
    p_val = 2.0 * (1.0 - stats.norm.cdf(abs(z)))
    se1 = math.sqrt(pc * (1 - pc) / nc + pt * (1 - pt) / nt)
    z_crit = stats.norm.ppf(1 - ALPHA / 2)
    ci_low = delta - z_crit * se1
    ci_high = delta + z_crit * se1
    return z, p_val, ci_low, ci_high, delta


def proportion_ztest(
    rate_control: float, rate_treatment: float, n_control: int, n_treatment: int
) -> ConversionResult:
    z, p_val, ci_low, ci_high, delta = _proportion_ztest(
        rate_control, rate_treatment, n_control, n_treatment
    )
    pc, pt = rate_control, rate_treatment
    return ConversionResult(
        metric="visitor_to_paid_high_value",
        control_rate=float(pc),
        treatment_rate=float(pt),
        abs_lift=float(delta),
        rel_lift=float(delta / pc) if pc > 0 else 0.0,
        z_stat=float(z),
        p_value=float(p_val),
        ci_low=float(ci_low),
        ci_high=float(ci_high),
        significant=bool(p_val < ALPHA),
    )


def _ttest_ind(
    values_c: np.ndarray, values_t: np.ndarray
) -> Tuple[float, float, float, float, float]:
    """t-test de duas amostras independentes (Welch) + IC da diferença."""
    n_c = len(values_c)
    n_t = len(values_t)
    if n_c < 2 or n_t < 2:
        raise ValueError("Amostra insuficiente para t-test (mínimo 2 por braço).")
    mean_c = float(np.mean(values_c))
    mean_t = float(np.mean(values_t))
    t_stat, p_val = stats.ttest_ind(values_t, values_c, equal_var=False)
    # IC de Welch para a diferença (treatment - control).
    se = math.sqrt(np.var(values_t, ddof=1) / n_t + np.var(values_c, ddof=1) / n_c)
    df = _welch_df(values_t, values_c)
    t_crit = stats.t.ppf(1 - ALPHA / 2, df) if df and df > 0 else stats.norm.ppf(1 - ALPHA / 2)
    ci_low = (mean_t - mean_c) - t_crit * se
    ci_high = (mean_t - mean_c) + t_crit * se
    return t_stat, p_val, ci_low, ci_high, (mean_t - mean_c)


def _welch_df(a: np.ndarray, b: np.ndarray) -> float:
    va, vb = np.var(a, ddof=1), np.var(b, ddof=1)
    na, nb = len(a), len(b)
    num = (va / na + vb / nb) ** 2
    den = (va / na) ** 2 / (na - 1) + (vb / nb) ** 2 / (nb - 1)
    if den == 0:
        return float(na + nb - 2)
    return num / den


def mean_ttest(
    values_control: pd.Series, values_treatment: pd.Series, metric: str = "Sales"
) -> MeanResult:
    t_stat, p_val, ci_low, ci_high, diff = _ttest_ind(
        values_control.to_numpy(dtype=float), values_treatment.to_numpy(dtype=float)
    )
    return MeanResult(
        metric=metric,
        control_mean=float(np.mean(values_control)),
        treatment_mean=float(np.mean(values_treatment)),
        abs_diff=float(diff),
        t_stat=float(t_stat),
        p_value=float(p_val),
        ci_low=float(ci_low),
        ci_high=float(ci_high),
        significant=bool(p_val < ALPHA),
    )


def decide(srm: SRMResult,
           conversion: Optional[ConversionResult],
           mean_sales: Optional[MeanResult]) -> str:
    """Matriz de decisão executiva (mesma ordem do contrato auditável).

    SRM falhado => RERUN (integridade do tráfego primeiro).
    """
    if srm.srm_flagged:
        return "RERUN"
    # Sem SRM: avalia significância da conversão e do ticket médio.
    conv_sig = conversion is not None and conversion.significant
    sales_sig = mean_sales is not None and mean_sales.significant
    if conv_sig and sales_sig:
        return "SHIP"
    if conv_sig or sales_sig:
        return "KEEP_RUNNING"
    return "ITERATE"


def run_ab_test(df_customers: pd.DataFrame, df_orders: pd.DataFrame,
                seed: int = 42) -> ABTestResult:
    """Executa o A/B test completo sobre customer-level + order-level.

    Particionamento: cada Customer ID vai para control ou treatment (hash).
    As métricas de negócio (conversão high_value, média de Sales) são
    agregadas por grupo a partir dos pedidos dos clientes de cada braço.
    """
    # Atribui grupo a cada cliente.
    df_customers = df_customers.copy()
    df_customers["ab_group"] = assign_group(df_customers["Customer ID"], seed=seed)

    # Contagem de clientes por braço (para SRM).
    n_control = int((df_customers["ab_group"] == "control").sum())
    n_treatment = int((df_customers["ab_group"] == "treatment").sum())
    srm = srm_check(n_control, n_treatment)

    conversion = None
    mean_sales = None

    if not srm.srm_flagged:
        # Junta grupo do cliente aos pedidos.
        orders = df_orders.merge(
            df_customers[["Customer ID", "ab_group"]],
            on="Customer ID", how="left"
        )
        oc = orders[orders["ab_group"] == "control"]
        ot = orders[orders["ab_group"] == "treatment"]

        # Taxa de conversão: fração de pedidos de clientes high_value (proxy).
        # Como high_value é atributo do cliente, usamos a taxa de clientes
        # high_value entre os clientes de cada braço (mais correto para A/B).
        conv_c = float(df_customers[df_customers["ab_group"] == "control"][
                           "high_value"].mean())
        conv_t = float(df_customers[df_customers["ab_group"] == "treatment"][
                           "high_value"].mean())
        conversion = proportion_ztest(conv_c, conv_t, n_control, n_treatment)

        # Ticket médio (Sales) por pedido, por braço.
        mean_sales = mean_ttest(oc["Sales"], ot["Sales"], metric="Sales")

    decision = decide(srm, conversion, mean_sales)
    return ABTestResult(srm=srm, conversion=conversion, mean_sales=mean_sales,
                        decision=decision)


def srm_result_to_dict(srm: SRMResult) -> dict:
    d = asdict(srm)
    d["srm_flagged"] = bool(d["srm_flagged"])
    return d
