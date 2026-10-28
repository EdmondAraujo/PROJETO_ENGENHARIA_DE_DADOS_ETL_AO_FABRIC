#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
src/modeling.py — Camada 4: predição e loop de minimização do MSE.

Constrói, para cada alvo, um sklearn.Pipeline (pré-processamento + modelo) e
executa GridSearchCV com scoring='neg_mean_squared_error' sobre validação
cruzada (KFold) restrita ao treino. Seleciona o modelo de menor MSE de CV e
avalia no hold-out (teste), reportando MSE, RMSE e R².

Precauções contra data leakage:
  - O split treino/teste é feito por Customer ID (um cliente nunca aparece
    simultaneamente em treino e teste).
  - OneHotEncoder/StandardScaler são ajustados APENAS no treino, dentro de
    cada fold do GridSearchCV (via sklearn.Pipeline).
  - O hold-out de teste é intocado até a avaliação final.
  - Para o alvo de conversão, a saída é probabilidade e o erro quadrado
    (MSE/Brier score) é calculado entre probabilidade prevista e 0/1 real.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import math

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_squared_error, r2_score, accuracy_score, roc_auc_score
from sklearn.model_selection import GridSearchCV, KFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from .preprocessing import (  # noqa: E402
    CATEGORICAL_COLUMNS,
    NUMERIC_FEATURE_COLUMNS,
    TARGET_CONVERSION,
    TARGET_PROFIT,
    TARGET_SALES,
    split_by_customer,
)

RANDOM_SEED = 42
CV_FOLDS = 5
TEST_SIZE = 0.2


def _brier_scorer(estimator: object, X: pd.DataFrame, y: pd.Series) -> float:
    """Scorer customizado: negativo do MSE de probabilidade (Brier score).

    GridSearchCV maximiza o score, então retornamos -MSE(y, predict_proba).
    Assim a seleção do classificador é feita pelo erro quadrático sobre a
    probabilidade prevista, não sobre a classe prevista (alinhado ao contrato
    de minimização de MSE de probabilidade prometido no README).
    """
    prob = estimator.predict_proba(X)[:, 1]
    return -float(mean_squared_error(y, prob))

# Ordem de preferência dos modelos candidatos (regressão).
REGRESSOR_CANDIDATES: List[Tuple[object, dict]] = [
    (
        "Ridge",
        Ridge(),
        {"regressor__alpha": [0.1, 1.0, 10.0, 100.0]},
    ),
    (
        "RandomForest",
        RandomForestRegressor(random_state=RANDOM_SEED, n_jobs=-1),
        {
            "regressor__n_estimators": [100, 300],
            "regressor__max_depth": [None, 10, 20],
            "regressor__min_samples_split": [2, 5],
        },
    ),
    (
        "GradientBoosting",
        GradientBoostingRegressor(random_state=RANDOM_SEED),
        {
            "regressor__n_estimators": [100, 200],
            "regressor__learning_rate": [0.05, 0.1],
            "regressor__max_depth": [3, 5],
        },
    ),
]

# Candidatos para classificação de conversão.
CLASSIFIER_CANDIDATES: List[Tuple[object, dict]] = [
    (
        "RandomForest",
        RandomForestClassifier(random_state=RANDOM_SEED, n_jobs=-1),
        {
            "classifier__n_estimators": [100, 300],
            "classifier__max_depth": [None, 10, 20],
            "classifier__min_samples_split": [2, 5],
        },
    ),
    (
        "GradientBoosting",
        GradientBoostingClassifier(random_state=RANDOM_SEED),
        {
            "classifier__n_estimators": [100, 200],
            "classifier__learning_rate": [0.05, 0.1],
            "classifier__max_depth": [3, 5],
        },
    ),
]


@dataclass
class RegressionResult:
    target: str
    best_model_name: str
    best_params: dict
    best_cv_mse: float  # menor MSE de CV (neg_mean_squared_error invertido)
    mse_train: float
    rmse_train: float
    r2_train: float
    mse_test: float
    rmse_test: float
    r2_test: float
    overfitting_ratio: float  # mse_test / mse_train


@dataclass
class ClassificationResult:
    target: str
    best_model_name: str
    best_params: dict
    best_cv_mse: float  # MSE de CV sobre probabilidade (Brier)
    mse_test_prob: float  # MSE entre probabilidade prevista e 0/1 (teste)
    accuracy_test: float
    roc_auc_test: Optional[float]


@dataclass
class ModelingResults:
    sales: RegressionResult
    profit: RegressionResult
    conversion: ClassificationResult


def _build_preprocessor(numeric_features: List[str],
                        categorical_features: List[str]) -> ColumnTransformer:
    """Pré-processador: escala numéricas e one-hot categóricas (handle_unknown ignore)."""
    numeric_transformer = Pipeline([
        ("scaler", StandardScaler()),
    ])
    categorical_transformer = Pipeline([
        ("onehot", OneHotEncoder(handle_unknown="ignore", sparse_output=False)),
    ])
    return ColumnTransformer([
        ("num", numeric_transformer, numeric_features),
        ("cat", categorical_transformer, categorical_features),
    ])


def _search_best_regressor(X_train: pd.DataFrame, y_train: pd.Series,
                           numeric_features: List[str],
                           categorical_features: List[str],
                           target_name: str) -> Tuple[object, dict, float, List[dict]]:
    """Executa GridSearchCV para cada regressor e retorna o melhor por MSE de CV."""
    preprocessor = _build_preprocessor(numeric_features, categorical_features)
    cv = KFold(n_splits=CV_FOLDS, shuffle=True, random_state=RANDOM_SEED)

    best_estimator = None
    best_params = {}
    best_cv_mse = np.inf
    all_results: List[dict] = []

    for name, estimator, param_grid in REGRESSOR_CANDIDATES:
        pipe = Pipeline([
            ("preprocessor", preprocessor),
            ("regressor", estimator),
        ])
        search = GridSearchCV(
            pipe,
            param_grid,
            cv=cv,
            scoring="neg_mean_squared_error",
            n_jobs=-1,
            refit=True,
        )
        search.fit(X_train, y_train)
        cv_mse = -float(search.best_score_)

        all_results.append({
            "model": name,
            "best_params": search.best_params_,
            "cv_mse": cv_mse,
        })

        if cv_mse < best_cv_mse:
            best_cv_mse = cv_mse
            best_estimator = search.best_estimator_
            best_params = search.best_params_
            best_model_name = name

    return best_estimator, best_params, best_cv_mse, best_model_name, all_results


def _search_best_classifier(X_train: pd.DataFrame, y_train: pd.Series,
                            numeric_features: List[str],
                            categorical_features: List[str],
                            target_name: str) -> Tuple[object, dict, float, str, List[dict]]:
    """GridSearchCV para classificação, otimizando MSE de probabilidade (Brier).

    Usa scoring customizado baseado em predict_proba (neg MSE sobre a
    probabilidade da classe positiva), de modo que a seleção do melhor
    classificador seja feita pelo erro quadrático de probabilidade (Brier),
    não pela classe prevista.
    """
    preprocessor = _build_preprocessor(numeric_features, categorical_features)
    cv = KFold(n_splits=CV_FOLDS, shuffle=True, random_state=RANDOM_SEED)

    best_estimator = None
    best_params = {}
    best_cv_mse = np.inf
    best_model_name = ""
    all_results: List[dict] = []

    for name, estimator, param_grid in CLASSIFIER_CANDIDATES:
        pipe = Pipeline([
            ("preprocessor", preprocessor),
            ("classifier", estimator),
        ])
        search = GridSearchCV(
            pipe,
            param_grid,
            cv=cv,
            scoring=_brier_scorer,
            n_jobs=-1,
            refit=True,
        )
        search.fit(X_train, y_train)
        cv_mse = -float(search.best_score_)

        all_results.append({
            "model": name,
            "best_params": search.best_params_,
            "cv_mse": cv_mse,
        })

        if cv_mse < best_cv_mse:
            best_cv_mse = cv_mse
            best_estimator = search.best_estimator_
            best_params = search.best_params_
            best_model_name = name

    return best_estimator, best_params, best_cv_mse, best_model_name, all_results


def _evaluate_regressor(estimator: object,
                        X_train: pd.DataFrame, y_train: pd.Series,
                        X_test: pd.DataFrame, y_test: pd.Series,
                        target: str, best_model_name: str,
                        best_params: dict, best_cv_mse: float) -> RegressionResult:
    """Avalia o regressor selecionado no treino e no hold-out (teste)."""
    y_train_pred = estimator.predict(X_train)
    y_test_pred = estimator.predict(X_test)

    mse_train = float(mean_squared_error(y_train, y_train_pred))
    rmse_train = float(math.sqrt(mse_train))
    r2_train = float(r2_score(y_train, y_train_pred))

    mse_test = float(mean_squared_error(y_test, y_test_pred))
    rmse_test = float(math.sqrt(mse_test))
    r2_test = float(r2_score(y_test, y_test_pred))

    overfitting_ratio = float(mse_test / mse_train) if mse_train > 0 else float("inf")

    return RegressionResult(
        target=target,
        best_model_name=best_model_name,
        best_params=best_params,
        best_cv_mse=float(best_cv_mse),
        mse_train=mse_train,
        rmse_train=rmse_train,
        r2_train=r2_train,
        mse_test=mse_test,
        rmse_test=rmse_test,
        r2_test=r2_test,
        overfitting_ratio=overfitting_ratio,
    )


def _evaluate_classifier(estimator: object,
                         X_train: pd.DataFrame, y_train: pd.Series,
                         X_test: pd.DataFrame, y_test: pd.Series,
                         target: str, best_model_name: str,
                         best_params: dict, best_cv_mse: float) -> ClassificationResult:
    """Avalia o classificador: MSE sobre probabilidade (Brier), accuracy, ROC AUC."""
    y_test_prob = estimator.predict_proba(X_test)[:, 1]
    y_test_pred = estimator.predict(X_test)

    mse_test_prob = float(mean_squared_error(y_test, y_test_prob))
    accuracy_test = float(accuracy_score(y_test, y_test_pred))

    try:
        roc_auc = float(roc_auc_score(y_test, y_test_prob))
    except ValueError:
        roc_auc = None

    return ClassificationResult(
        target=target,
        best_model_name=best_model_name,
        best_params=best_params,
        best_cv_mse=float(best_cv_mse),
        mse_test_prob=mse_test_prob,
        accuracy_test=accuracy_test,
        roc_auc_test=roc_auc,
    )


def train_and_evaluate_by_customer(X_full: pd.DataFrame,
                                   df_orders_with_cid: pd.DataFrame,
                                   y_sales: pd.Series, y_profit: pd.Series,
                                   y_conversion: pd.Series,
                                   seed: int = RANDOM_SEED,
                                   test_size: float = TEST_SIZE) -> ModelingResults:
    """Versão com split rigoroso por Customer ID (recomendada).

    df_orders_with_cid deve conter a coluna 'Customer ID' alinhada com X_full
    (mesma ordem/índice). Divide os Customer IDs em treino/teste, filtra X e y
    de acordo, e então executa o loop de modelagem. Assim, nenhum cliente
    aparece nos dois conjuntos — sem data leakage.
    """
    # Alinha customer_id ao índice de X_full.
    cid = df_orders_with_cid["Customer ID"].reset_index(drop=True)
    X_aligned = X_full.reset_index(drop=True)
    ys_s = y_sales.reset_index(drop=True)
    ys_p = y_profit.reset_index(drop=True)
    ys_c = y_conversion.reset_index(drop=True)

    # Monta df temporário para split por cliente.
    tmp = pd.DataFrame({
        "Customer ID": cid,
        TARGET_SALES: ys_s,
        TARGET_PROFIT: ys_p,
        TARGET_CONVERSION: ys_c,
    })
    for c in X_aligned.columns:
        tmp[c] = X_aligned[c].values

    train_ids, test_ids = split_by_customer(tmp, seed=seed, test_size=test_size)

    train_mask = tmp["Customer ID"].isin(train_ids)
    test_mask = tmp["Customer ID"].isin(test_ids)

    train_df = tmp[train_mask].reset_index(drop=True)
    test_df = tmp[test_mask].reset_index(drop=True)

    X_train = train_df[X_aligned.columns]
    X_test = test_df[X_aligned.columns]
    y_s_train = train_df[TARGET_SALES]
    y_s_test = test_df[TARGET_SALES]
    y_p_train = train_df[TARGET_PROFIT]
    y_p_test = test_df[TARGET_PROFIT]
    y_c_train = train_df[TARGET_CONVERSION]
    y_c_test = test_df[TARGET_CONVERSION]

    numeric_features = [c for c in NUMERIC_FEATURE_COLUMNS if c in X_train.columns]
    categorical_features = [c for c in CATEGORICAL_COLUMNS if c in X_train.columns]
    for extra in ["order_month", "order_quarter", "order_day_of_week",
                  "order_is_weekend", "days_since_first_order",
                  "n_orders", "avg_order_value", "recency_days"]:
        if extra in X_train.columns and extra not in numeric_features:
            numeric_features.append(extra)

    # --- Regressão Sales ---
    best_est_s, best_params_s, best_cv_mse_s, best_name_s, _ = _search_best_regressor(
        X_train, y_s_train, numeric_features, categorical_features, TARGET_SALES
    )
    res_sales = _evaluate_regressor(
        best_est_s, X_train, y_s_train, X_test, y_s_test,
        TARGET_SALES, best_name_s, best_params_s, best_cv_mse_s
    )

    # --- Regressão Profit ---
    best_est_p, best_params_p, best_cv_mse_p, best_name_p, _ = _search_best_regressor(
        X_train, y_p_train, numeric_features, categorical_features, TARGET_PROFIT
    )
    res_profit = _evaluate_regressor(
        best_est_p, X_train, y_p_train, X_test, y_p_test,
        TARGET_PROFIT, best_name_p, best_params_p, best_cv_mse_p
    )

    # --- Classificação de conversão ---
    stratify_arg = y_c_train if y_c_train.nunique() > 1 else None
    best_est_c, best_params_c, best_cv_mse_c, best_name_c, _ = _search_best_classifier(
        X_train, y_c_train, numeric_features, categorical_features, TARGET_CONVERSION
    )
    res_conversion = _evaluate_classifier(
        best_est_c, X_train, y_c_train, X_test, y_c_test,
        TARGET_CONVERSION, best_name_c, best_params_c, best_cv_mse_c
    )

    return ModelingResults(sales=res_sales, profit=res_profit,
                           conversion=res_conversion)
