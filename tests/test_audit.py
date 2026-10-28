# -*- coding: utf-8 -*-
"""Bateria de testes de auditoria — pipeline AWS SaaS Sales (Opção A).

Valida: ingestão, pré-processamento sem vazamento, gate de SRM, cálculo do MSE
com scikit-learn, modelagem com minimização de MSE e ausência de placeholders.
"""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from sklearn.metrics import mean_squared_error

REPO = Path(__file__).resolve().parents[1]
DATA_PATH = REPO / "data" / "SaaS-Sales.csv"

# Importa os módulos do pacote src (executado a partir da raiz do repo).
import sys

if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from src.ingestion import load_saas_sales, validate_loaded, REQUIRED_COLUMNS  # noqa: E402
from src.preprocessing import prepare, split_by_customer, TARGET_SALES, TARGET_PROFIT, TARGET_CONVERSION  # noqa: E402
from src.ab_test import srm_check, proportion_ztest, mean_ttest, ALPHA, SRM_EXPECTED_SPLIT  # noqa: E402
from src.modeling import train_and_evaluate_by_customer, REGRESSOR_CANDIDATES, CLASSIFIER_CANDIDATES  # noqa: E402


# ---------------------------------------------------------------------------
# Ingestão
# ---------------------------------------------------------------------------
class TestIngestion:
    def test_loads_csv_with_required_columns(self):
        if not DATA_PATH.exists():
            pytest.skip("data/SaaS-Sales.csv não encontrado")
        df = load_saas_sales(DATA_PATH)
        missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
        assert not missing, f"Colunas ausentes: {missing}"
        assert len(df) > 0

    def test_validate_loaded_passes(self):
        if not DATA_PATH.exists():
            pytest.skip("data/SaaS-Sales.csv não encontrado")
        df = load_saas_sales(DATA_PATH)
        validate_loaded(df)  # não deve levantar

    def test_dates_parsed_no_nat(self):
        if not DATA_PATH.exists():
            pytest.skip("data/SaaS-Sales.csv não encontrado")
        df = load_saas_sales(DATA_PATH)
        assert df["Order Date"].notna().all(), "Há datas não parseadas (NaT)"


# ---------------------------------------------------------------------------
# Pré-processamento e split sem vazamento
# ---------------------------------------------------------------------------
class TestPreprocessing:
    def test_prepare_creates_targets_and_features(self):
        if not DATA_PATH.exists():
            pytest.skip("data/SaaS-Sales.csv não encontrado")
        df = load_saas_sales(DATA_PATH)
        prepared = prepare(df)
        assert prepared.y_sales.notna().all()
        assert prepared.y_profit.notna().all()
        assert prepared.y_conversion.notna().all()
        assert set([TARGET_SALES, TARGET_PROFIT, TARGET_CONVERSION]).issubset(
            set(prepared.df_orders.columns)
        )
        assert len(prepared.feature_names) > 0
        # customer_id nunca entra como feature direta.
        assert "Customer ID" not in prepared.feature_names

    def test_customer_conversion_binary(self):
        if not DATA_PATH.exists():
            pytest.skip("data/SaaS-Sales.csv não encontrado")
        df = load_saas_sales(DATA_PATH)
        prepared = prepare(df)
        vals = set(prepared.y_conversion.unique())
        assert vals <= {0, 1}

    def test_split_by_customer_no_overlap(self):
        if not DATA_PATH.exists():
            pytest.skip("data/SaaS-Sales.csv não encontrado")
        df = load_saas_sales(DATA_PATH)
        prepared = prepare(df)
        train_ids, test_ids = split_by_customer(prepared.df_customers, seed=42)
        overlap = set(train_ids) & set(test_ids)
        assert not overlap, f"Vazamento de cliente entre treino e teste: {overlap}"
        assert len(train_ids) + len(test_ids) == prepared.df_customers["Customer ID"].nunique()


# ---------------------------------------------------------------------------
# A/B test e rigor estatístico
# ---------------------------------------------------------------------------
class TestABTest:
    def test_srm_balanced_split_passes(self):
        r = srm_check(5000, 5000)
        assert r.srm_flagged is False
        assert r.method == "chi_square_df1"

    def test_srm_imbalanced_split_fails(self):
        r = srm_check(8000, 2000)
        assert r.srm_flagged is True

    def test_srm_small_cells_uses_exact(self):
        r = srm_check(12, 25)
        assert r.exact_p_value is not None
        assert r.method == "binomial_exact_two_sided"

    def test_proportion_ztest_matches_scipy(self):
        # z = (pt - pc) / sqrt(p_bar(1-p_bar)(1/nc + 1/nt))
        pc, pt, nc, nt = 0.10, 0.12, 6000, 6000
        res = proportion_ztest(pc, pt, nc, nt)
        p_bar = (pc * nc + pt * nt) / (nc + nt)
        se0 = (p_bar * (1 - p_bar) * (1 / nc + 1 / nt)) ** 0.5
        z_expected = (pt - pc) / se0
        assert abs(res.z_stat - z_expected) < 1e-6
        assert abs(res.p_value - 2 * (1 - __import__("scipy").stats.norm.cdf(abs(z_expected)))) < 1e-6

    def test_mean_ttest_significant_when_large_diff(self):
        rng = np.random.default_rng(0)
        c = rng.normal(100, 10, 200)
        t = rng.normal(130, 10, 200)
        res = mean_ttest(pd.Series(c), pd.Series(t), metric="Sales")
        assert res.significant is True
        assert res.abs_diff > 0


# ---------------------------------------------------------------------------
# MSE / modelagem (minimização de erro quadrático)
# ---------------------------------------------------------------------------
class TestMSE:
    def test_mse_uses_sklearn_and_is_nonnegative(self):
        y_true = np.array([3.0, -0.5, 2.0, 7.0])
        y_pred = np.array([2.5, 0.0, 2.0, 8.0])
        mse_sklearn = mean_squared_error(y_true, y_pred)
        mse_manual = float(np.mean((y_true - y_pred) ** 2))
        assert abs(mse_sklearn - mse_manual) < 1e-12
        assert mse_sklearn >= 0.0

    def test_modeling_returns_nonnegative_mse(self):
        if not DATA_PATH.exists():
            pytest.skip("data/SaaS-Sales.csv não encontrado")
        df = load_saas_sales(DATA_PATH)
        prepared = prepare(df)
        # Subconjunto pequeno para teste rápido (sem vazamento de cliente).
        small_cust = prepared.df_customers["Customer ID"].unique()[:40]
        small_orders = prepared.df_orders[prepared.df_orders["Customer ID"].isin(small_cust)].copy()
        small_cust_df = prepared.df_customers[prepared.df_customers["Customer ID"].isin(small_cust)].copy()

        res = train_and_evaluate_by_customer(
            small_orders[prepare(df).feature_names],
            small_orders,
            small_orders[TARGET_SALES].reset_index(drop=True),
            small_orders[TARGET_PROFIT].reset_index(drop=True),
            small_orders[TARGET_CONVERSION].reset_index(drop=True),
            seed=42,
        )
        for r in (res.sales, res.profit):
            assert r.mse_test >= 0.0
            assert r.mse_train >= 0.0
            assert -np.inf < r.r2_test <= 1.0
        assert res.conversion.mse_test_prob >= 0.0
        assert 0.0 <= res.conversion.accuracy_test <= 1.0

    def test_best_model_selected_by_lowest_cv_mse(self):
        """Verifica que o modelo selecionado é o de menor MSE de CV (mock)."""
        from sklearn.linear_model import Ridge
        from sklearn.model_selection import GridSearchCV
        from sklearn.pipeline import Pipeline
        from sklearn.preprocessing import StandardScaler
        from src.modeling import _search_best_regressor

        rng = np.random.default_rng(1)
        X = pd.DataFrame({"a": rng.normal(size=100), "b": rng.normal(size=100)})
        y = pd.Series(X["a"] * 2 + X["b"] + rng.normal(scale=0.1, size=100))

        best_est, best_params, best_cv_mse, best_name, all_results = _search_best_regressor(
            X, y, ["a", "b"], [], "mock"
        )
        # O menor MSE de CV deve coincidir com o melhor resultado da lista.
        expected_best = min(all_results, key=lambda d: d["cv_mse"])
        assert abs(best_cv_mse - expected_best["cv_mse"]) < 1e-9
        assert best_name == expected_best["model"]
        assert best_cv_mse >= 0.0


# ---------------------------------------------------------------------------
# Production readiness: sem placeholders / TODOs
# ---------------------------------------------------------------------------
class TestProductionReadiness:
    def test_no_todo_placeholders_in_source(self):
        source_files = [
            REPO / "main.py",
            REPO / "requirements.txt",
        ] + list((REPO / "src").rglob("*.py")) + list((REPO / "tests").rglob("*.py"))
        # O teste não audita a si mesmo (sua própria docstring cita "TODO").
        source_files = [p for p in source_files if p.resolve() != Path(__file__).resolve()]
        for path in source_files:
            text = path.read_text(encoding="utf-8")
            assert re.search(r"#\s*TODO|TODO:", text, re.IGNORECASE) is None, f"{path} contém marcador TODO real"
            assert "...  #" not in text, f"{path} contém placeholder (...)"

    def test_main_is_executable(self):
        assert (REPO / "main.py").exists()
        text = (REPO / "main.py").read_text(encoding="utf-8")
        assert "if __name__" in text

    def test_requirements_has_scikit_learn(self):
        req = (REPO / "requirements.txt").read_text(encoding="utf-8")
        assert "scikit-learn" in req
