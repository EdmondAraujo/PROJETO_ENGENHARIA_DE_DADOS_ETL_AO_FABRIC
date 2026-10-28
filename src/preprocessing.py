#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
src/preprocessing.py — Camada 2: limpeza, transformação e engenharia de atributos SaaS.

Transforma o CSV bruto (nível de pedido / order-level) em:
  a) uma tabela modelo por pedido (order-level) com features não vazantes, e
  b) uma tabela resumo por cliente (customer-level) usada para o alvo de
     conversão (high_value) e para o split sem vazamento do A/B test.

Regras de negócio SaaS aplicadas:
  - Segment (SMB / Strategic / Enterprise) é usado como proxy de subscription tier.
  - Um cliente é considerado "convertido" (high_value=1) quando seu total de
    vendas (CLV proxy) está acima da mediana de todos os clientes.
  - customer_id é identificador: nunca entra como feature preditiva direta.
  - O split treino/teste é feito por Customer ID para evitar que pedidos do
    mesmo cliente apareçam simultaneamente em treino e teste (data leakage).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

import numpy as np
import pandas as pd

# Targets suportados pelo pipeline de modelagem.
TARGET_SALES = "Sales"
TARGET_PROFIT = "Profit"
TARGET_CONVERSION = "high_value"

# Colunas categóricas de baixa cardinalidade (seguras para one-hot).
CATEGORICAL_COLUMNS = ["Segment", "Industry", "Region", "Subregion", "Product"]

# Colunas numéricas brutas usadas como features (exclui targets e IDs).
NUMERIC_FEATURE_COLUMNS = ["Quantity", "Discount"]

# Coluna de data (já parseada na ingestão).
DATE_COLUMN = "Order Date"

# Identificadores (NUNCA features diretas).
ID_COLUMNS = ["Row ID", "Order ID", "Customer ID", "Customer", "Contact Name",
              "License", "Date Key"]

# Colunas que são targets (não entram em X).
TARGET_COLUMNS = [TARGET_SALES, TARGET_PROFIT, TARGET_CONVERSION]


@dataclass
class PreparedData:
    """Contêiner dos dados preparados para modelagem e A/B test."""

    # Tabela por pedido (order-level), já com features de data e alvos.
    df_orders: pd.DataFrame
    # Features prontas para modelagem (X) — alvos já separados.
    X: pd.DataFrame
    # Alvos.
    y_sales: pd.Series
    y_profit: pd.Series
    y_conversion: pd.Series
    # Resumo por cliente (customer-level) com alvo de conversão.
    df_customers: pd.DataFrame
    # Lista de nomes das feature colunas usadas em X.
    feature_names: list


def _add_date_features(df: pd.DataFrame) -> pd.DataFrame:
    """Extrai atributos de calendário a partir de Order Date (sem vazamento)."""
    out = df.copy()
    dt = out[DATE_COLUMN]
    out["order_month"] = dt.dt.month
    out["order_quarter"] = dt.dt.quarter
    out["order_day_of_week"] = dt.dt.dayofweek
    out["order_is_weekend"] = (dt.dt.dayofweek >= 5).astype(int)
    # Dias desde a primeira ordem do dataset (referência fixa, não vazante).
    ref = dt.min()
    out["days_since_first_order"] = (dt - ref).dt.days
    return out


def _build_customer_summary(df: pd.DataFrame) -> pd.DataFrame:
    """Agrega pedidos por Customer ID (grain do cliente).

    Retorna uma linha por cliente com: totais, contagem, ticket médio, primeira
    e última ordem, recência, frequência, segmento/indústria/região do cliente
    (moda) e o alvo binário de conversão high_value.
    """
    agg = (
        df.groupby("Customer ID")
        .agg(
            total_sales=(TARGET_SALES, "sum"),
            n_orders=(TARGET_SALES, "size"),
            avg_order_value=(TARGET_SALES, "mean"),
            total_profit=(TARGET_PROFIT, "sum"),
            first_order=(DATE_COLUMN, "min"),
            last_order=(DATE_COLUMN, "max"),
            total_quantity=("Quantity", "sum"),
            avg_discount=("Discount", "mean"),
        )
        .reset_index()
    )

    # Dimensões do cliente (primeira ocorrência / moda).
    dims = (
        df.sort_values(DATE_COLUMN)
        .groupby("Customer ID")
        .first()[["Segment", "Industry", "Region", "Subregion"]]
        .reset_index()
    )
    agg = agg.merge(dims, on="Customer ID", how="left")

    # Recência em dias a partir da última ordem do dataset (janela fixa).
    max_date = df[DATE_COLUMN].max()
    agg["recency_days"] = (max_date - agg["last_order"]).dt.days

    # Alvo de conversão SaaS: cliente de alto valor (acima da mediana de CLV).
    # Usa limiar estrito (>) para evitar desbalanceamento excessivo de classes.
    median_sales = agg["total_sales"].median()
    agg[TARGET_CONVERSION] = (agg["total_sales"] > median_sales).astype(int)

    return agg


def prepare(df: pd.DataFrame) -> PreparedData:
    """Executa todo o pré-processamento e devolve os dados preparados.

    Passos:
      1. Remove linhas com targets ausentes.
      2. Cria atributos de calendário (order-level).
      3. Constrói o resumo por cliente (customer-level) com alvo high_value.
      4. Junta as features estáticas do cliente ao pedido (apenas dimensões
         categóricas: segmento, indústria, região). **Não** junta agregados
         de vendas do cliente (total_sales, avg_order_value), pois vazariam o
         alvo de regressão para a linha do pedido e tornariam a classificação
         trivial.
      5. Separa X (features) dos alvos y_sales, y_profit, y_conversion.
    """
    work = df.copy()

    # 1. Limpeza de targets.
    before = len(work)
    work = work.dropna(subset=[TARGET_SALES, TARGET_PROFIT]).copy()
    dropped = before - len(work)
    if dropped:
        print(f"[preprocessamento] {dropped} linha(s) removida(s) por target ausente.")

    # 2. Atributos de data (order-level).
    work = _add_date_features(work)

    # 3. Resumo por cliente (grain = Customer ID).
    df_customers = _build_customer_summary(work)

    # 4. Junta dimensões estáticas do cliente ao pedido (não-vazante para
    #    regressão por linha: não usamos total_sales / avg_order_value do
    #    cliente como feature, pois são proxies diretos do alvo).
    #    n_orders e recency_days são agregados sobre todo o histórico do
    #    cliente e podem carregar sinal do alvo; portanto também são excluídos
    #    de X para evitar vazamento indireto.
    cust_dims = df_customers[
        ["Customer ID", "Segment", "Industry", "Region", "Subregion",
         TARGET_CONVERSION]
    ]
    work = work.merge(cust_dims, on="Customer ID", how="left", suffixes=("", "_cust"))

    # Alvo de conversão por pedido (herdado do cliente).
    work[TARGET_CONVERSION] = work[TARGET_CONVERSION].astype(int)

    # 5. Separa X dos alvos.
    feature_cols = NUMERIC_FEATURE_COLUMNS + [
        "order_month", "order_quarter", "order_day_of_week", "order_is_weekend",
        "days_since_first_order",
    ] + CATEGORICAL_COLUMNS

    X = work[feature_cols].copy()
    y_sales = work[TARGET_SALES].astype(float)
    y_profit = work[TARGET_PROFIT].astype(float)
    y_conversion = work[TARGET_CONVERSION].astype(int)

    feature_names = list(X.columns)

    return PreparedData(
        df_orders=work,
        X=X,
        y_sales=y_sales,
        y_profit=y_profit,
        y_conversion=y_conversion,
        df_customers=df_customers,
        feature_names=feature_names,
    )


def split_by_customer(
    df_customers: pd.DataFrame,
    seed: int = 42,
    test_size: float = 0.2,
) -> Tuple[pd.Index, pd.Index]:
    """Divide os Customer IDs em treino e teste (sem vazamento de cliente).

    Retorna (train_customer_ids, test_customer_ids) como pd.Index.
    """
    rng = np.random.default_rng(seed)
    ids = df_customers["Customer ID"].unique()
    rng.shuffle(ids)
    n_test = max(1, int(round(len(ids) * test_size)))
    test_ids = ids[:n_test]
    train_ids = ids[n_test:]
    return pd.Index(train_ids), pd.Index(test_ids)
