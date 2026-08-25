# -*- coding: utf-8 -*-
"""
Gera o documento JSON consolidado do cruzamento ANP 2020–2025,
pronto para ingestão no Azure Cosmos DB for NoSQL via Microsoft Fabric.

Estrutura de documento (1 por ano):
{
  "id": "anp-petroleo-2020",
  "tipo": "cruzamento_anual",
  "fonte": "ANP",
  "ano": 2020,
  "producao": {...},
  "comercio_exterior": {...},
  "fases": {...},
  "indicadores": {...},
  "mensal": [ ... ]
}
"""
import io
import json
import sys
from pathlib import Path

import pandas as pd

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

OUT = Path("data/processed")
DEST = Path("data/processed/cosmosdb")
DEST.mkdir(parents=True, exist_ok=True)

fato = pd.read_csv(OUT / "fato_mensal_2020_2025.csv", decimal=",")
fase = pd.read_csv(OUT / "dim_campos_fase_anual.csv")
anual = pd.read_csv(OUT / "fato_anual_2020_2025.csv", decimal=",")

documentos = []
for _, linha in anual.iterrows():
    ano = int(linha["ANO"])
    meses = fato[fato["ANO"] == ano]
    documentos.append({
        "id": f"anp-petroleo-{ano}",
        "tipo": "cruzamento_anual_petroleo",
        "fonte": "ANP - Dados Estatisticos / Fase de Desenvolvimento e Producao",
        "ano": ano,
        "producao": {
            "total_barris": float(linha["PRODUCAO_BARRIS"]),
            "variacao_yoy_pct": None if pd.isna(linha["PRODUCAO_BARRIS_YOY_PCT"]) else float(linha["PRODUCAO_BARRIS_YOY_PCT"]),
        },
        "comercio_exterior": {
            "exportacao_barris": float(linha["EXPORTACAO_BARRIS"]),
            "importacao_barris": float(linha["IMPORTACAO_BARRIS"]),
            "balanca_comercial_barris": float(linha["BALANCA_COMERCIAL_BARRIS"]),
            "exportacao_yoy_pct": None if pd.isna(linha["EXPORTACAO_BARRIS_YOY_PCT"]) else float(linha["EXPORTACAO_BARRIS_YOY_PCT"]),
            "importacao_yoy_pct": None if pd.isna(linha["IMPORTACAO_BARRIS_YOY_PCT"]) else float(linha["IMPORTACAO_BARRIS_YOY_PCT"]),
        },
        "fases_contratuais": {
            "campos_em_producao": int(linha["CAMPOS_EM_PRODUCAO"]),
            "campos_em_desenvolvimento": int(linha["CAMPOS_EM_DESENVOLVIMENTO"]),
            "campos_total_fase_producao": int(linha["CAMPOS_TOTAL_FASE"]),
        },
        "indicadores": {
            "cobertura_exportacao_pct": float(linha["COBERTURA_EXPORT_PCT"]),
            "dependencia_importacao_pct": float(linha["DEPENDENCIA_IMPORT_PCT"]),
            "producao_media_bbl_dia": float(linha["PRODUCAO_BARRIS"]) / 365.25,
            "producao_por_campo_barris": float(linha["PRODUCAO_BARRIS"]) / int(linha["CAMPOS_EM_PRODUCAO"]),
        },
        "mensal": [
            {
                "mes": int(r["MES_NUM"]),
                "producao_barris": float(r["PRODUCAO_BARRIS"]),
                "importacao_barris": float(r["IMPORTACAO_BARRIS"]),
                "exportacao_barris": float(r["EXPORTACAO_BARRIS"]),
                "balanca_comercial_barris": float(r["BALANCA_COMERCIAL_BARRIS"]),
            }
            for _, r in meses.iterrows()
        ],
    })

arquivo = DEST / "cruzamento_anp_2020_2025.json"
with open(arquivo, "w", encoding="utf-8") as f:
    json.dump(documentos, f, ensure_ascii=False, indent=2)

print(f"JSON gerado: {arquivo} ({len(documentos)} documentos)")
print(json.dumps(documentos[-1], ensure_ascii=False, indent=2)[:1200])
