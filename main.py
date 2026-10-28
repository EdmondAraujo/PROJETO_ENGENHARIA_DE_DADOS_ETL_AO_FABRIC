#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
main.py — Pipeline AWS SaaS Sales (Opção A: Pure Python CLI).

Executa, em ordem de integridade:
  1. Ingestão do dataset AWS SaaS Sales (CSV local em data/).
  2. Pré-processamento e engenharia de atributos SaaS (funil por cliente).
  3. A/B test com gate de SRM (chi-quadrado + binomial exato em células pequenas).
  4. Loop de modelagem preditiva com minimização de MSE (GridSearchCV + CV):
        - Regressão Sales  (valor do pedido / ticket)
        - Regressão Profit (lucro)
        - Classificação de conversão (probabilidade, avaliada com MSE)
  5. Relatório executivo em markdown no terminal (MSE, RMSE, R²).

Não há placeholders nem marcadores pendentes. Dependências mínimas: pandas,
numpy, scikit-learn, scipy.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Garante import dos módulos src/ quando executado como script.
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.pipeline import run_pipeline  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Pipeline AWS SaaS Sales — ingestão, A/B test e modelagem com minimização de MSE."
    )
    parser.add_argument(
        "--data",
        type=Path,
        default=ROOT / "data" / "SaaS-Sales.csv",
        help="Caminho do CSV do AWS SaaS Sales (padrão: data/SaaS-Sales.csv).",
    )
    parser.add_argument(
        "--no-ab",
        action="store_true",
        help="Desativa o módulo de A/B test (apenas ingestão + modelagem).",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Seed aleatória para reprodutibilidade (default: 42).",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    # Força UTF-8 no terminal (Windows/cp1252 não rende setas e emojis).
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    data_path: Path = args.data
    if not data_path.exists():
        print(f"ERRO: arquivo de dados não encontrado: {data_path}")
        print("      Baixe o dataset nnthanh101/aws-saas-sales do Kaggle e coloque em data/SaaS-Sales.csv")
        return 1

    print("=" * 72)
    print("PIPELINE AWS SAAS SALES — Opção A (Pure Python CLI + scikit-learn)")
    print("=" * 72)
    print(f"Arquivo de dados : {data_path}")
    print(f"Seed             : {args.seed}")
    print(f"A/B test         : {'desativado' if args.no_ab else 'ativado'}")
    print("=" * 72)

    return run_pipeline(
        data_path=data_path,
        run_ab=not args.no_ab,
        seed=args.seed,
    )


if __name__ == "__main__":
    sys.exit(main())
