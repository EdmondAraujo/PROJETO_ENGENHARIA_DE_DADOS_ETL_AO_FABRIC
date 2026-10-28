#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
src/pipeline.py — Camada 6: orquestração do pipeline end-to-end.

Ordem de execução (contrato de integridade):
  1. ingestion.load_saas_sales + validate_loaded
  2. preprocessing.prepare (features + targets + customer-level)
  3. ab_test.run_ab_test (gate de SRM primeiro; negócio só se aprovado)
  4. modeling.train_and_evaluate_by_customer (loop de minimização de MSE)
  5. report.build_executive_report (markdown no terminal)
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import pandas as pd

from .ingestion import load_saas_sales, validate_loaded
from .preprocessing import prepare
from .ab_test import run_ab_test
from .modeling import train_and_evaluate_by_customer
from .report import build_executive_report


def run_pipeline(data_path: Path,
                 run_ab: bool = True,
                 seed: int = 42) -> int:
    """Executa o pipeline completo e imprime o relatório executivo.

    Retorna código de saída:
      0 — sucesso.
      1 — erro de dados/infraestrutura.
      2 — gate de SRM falhou (A/B bloqueado; modelagem ainda pode rodar).
    """
    try:
        # 1. Ingestão.
        df = load_saas_sales(data_path)
        validate_loaded(df)

        # 2. Pré-processamento e engenharia de atributos.
        prepared = prepare(df)

        # 3. A/B test (opcional).
        ab: Optional[object] = None
        if run_ab:
            ab = run_ab_test(prepared.df_customers, prepared.df_orders, seed=seed)
            if ab.srm.srm_flagged:
                print("\n[!] Gate de SRM FALHOU — leituras de negócio do A/B suprimidas.")
                print("    O pipeline continua com a modelagem preditiva (alvos independentes do split A/B).")

        # 4. Modelagem com minimização de MSE (split rigoroso por Customer ID).
        res = train_and_evaluate_by_customer(
            prepared.X,
            prepared.df_orders,
            prepared.y_sales,
            prepared.y_profit,
            prepared.y_conversion,
            seed=seed,
        )

        # 5. Relatório executivo.
        print("\n")
        print(build_executive_report(df, prepared, ab, res))

        exit_code = 2 if (ab is not None and ab.srm.srm_flagged) else 0
        return exit_code

    except FileNotFoundError as exc:
        print(f"ERRO: {exc}")
        return 1
    except ValueError as exc:
        print(f"ERRO de validação: {exc}")
        return 1
    except Exception as exc:  # pragma: no cover - rede/ambiente
        print(f"ERRO inesperado: {type(exc).__name__}: {exc}")
        return 1
