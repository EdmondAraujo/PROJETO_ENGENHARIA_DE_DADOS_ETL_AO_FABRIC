#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
src/ingestion.py — Camada 1: ingestão e validação do dataset AWS SaaS Sales.

Carrega o CSV local (extraído do zip do Kaggle nnthanh101/aws-saas-sales),
valida o schema obrigatório e devolve um DataFrame bruto e tipificado.
"""

from __future__ import annotations

from pathlib import Path
from typing import List

import pandas as pd

# Colunas obrigatórias do dataset nnthanh101/aws-saas-sales.
REQUIRED_COLUMNS: List[str] = [
    "Row ID",
    "Order ID",
    "Order Date",
    "Date Key",
    "Contact Name",
    "Country",
    "City",
    "Region",
    "Subregion",
    "Customer",
    "Customer ID",
    "Industry",
    "Segment",
    "Product",
    "License",
    "Sales",
    "Quantity",
    "Discount",
    "Profit",
]

# Colunas que devem ser numéricas após a leitura.
NUMERIC_COLUMNS: List[str] = [
    "Row ID",
    "Date Key",
    "Customer ID",
    "Sales",
    "Quantity",
    "Discount",
    "Profit",
]

# Colunas de data.
DATE_COLUMNS: List[str] = ["Order Date"]


def load_saas_sales(path: Path) -> pd.DataFrame:
    """Carrega o CSV do AWS SaaS Sales e valida o schema obrigatório.

    Parâmetros
    ----------
    path : Path
        Caminho do arquivo CSV (ex.: data/SaaS-Sales.csv).

    Retorna
    -------
    pd.DataFrame
        DataFrame bruto com tipos ajustados.

    Levanta
    -------
    FileNotFoundError
        Se o arquivo não existir.
    ValueError
        Se colunas obrigatórias estiverem ausentes.
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Arquivo de dados não encontrado: {path}")

    df = pd.read_csv(path)

    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(
            "Colunas obrigatórias ausentes no dataset: "
            + ", ".join(missing)
            + f". Colunas encontradas: {list(df.columns)}"
        )

    # Tipagem numérica (força, com erros virando NaN para auditoria posterior).
    for col in NUMERIC_COLUMNS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    # Parse de datas.
    for col in DATE_COLUMNS:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], format="%m/%d/%Y", errors="coerce")

    return df


def validate_loaded(df: pd.DataFrame) -> None:
    """Validações mínimas de integridade após o carregamento.

    Levanta ValueError se o dataset estiver vazio ou sem dados utilizáveis.
    """
    if df.empty:
        raise ValueError("O dataset carregado está vazio.")
    n_rows, n_cols = df.shape
    if n_rows < 10:
        raise ValueError(
            f"O dataset tem poucas linhas ({n_rows}) para modelagem confiável."
        )
    null_report = df.isnull().sum()
    null_cols = null_report[null_report > 0]
    if not null_cols.empty:
        print(
            "[aviso] Colunas com valores ausentes após a leitura: "
            + ", ".join(f"{c}={int(n)}" for c, n in null_cols.items())
        )
