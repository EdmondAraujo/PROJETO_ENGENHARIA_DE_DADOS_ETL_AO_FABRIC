# -*- coding: utf-8 -*-
"""
ETL — ANP: Importações/Exportações (barris) x Produção Nacional de Petróleo (barris)
Cruzamento com a Fase de Desenvolvimento e Produção (campos), 2020–2025.

Fontes oficiais ANP:
  1. Importações e exportações de petróleo (barris):
     https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-estatisticos/de/ie/importacoes-exportacoes-b.xlsx
  2. Produção nacional de petróleo e LGN (barris) — tabela BRASIL / PETRÓLEO TOTAL:
     https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-estatisticos/de/ppg/producao-petroleo-b.xls
  3. Dados Abertos — Fase de Desenvolvimento e Produção (campos):
     https://www.gov.br/anp/pt-br/centrais-de-conteudo/dados-abertos/arquivos/arquivos-fase-de-desenvolvimento-e-producao/informacoes-sobre-campos/extracao-campo.csv

Saídas (data/processed):
  fato_mensal_2020_2025.csv   — série mensal (produção, importação, exportação, balança)
  fato_anual_2020_2025.csv    — agregado anual + variações YoY + indicadores
  dim_campos_fase_anual.csv   — nº de campos por ano x fase (Produção / Desenvolvimento)
  dim_campos.csv              — dimensão dos campos (bacia, operador, ambiente, datas)
"""
import io
import sys
import unicodedata
from pathlib import Path
from typing import Optional

import pandas as pd

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

RAW = Path("data/raw")
OUT = Path("data/processed")
OUT.mkdir(parents=True, exist_ok=True)

MESES_PT = {
    "janeiro": 1, "fevereiro": 2, "marco": 3, "abril": 4, "maio": 5,
    "junho": 6, "julho": 7, "agosto": 8, "setembro": 9, "outubro": 10,
    "novembro": 11, "dezembro": 12,
}
ANOS_ALVO = list(range(2020, 2026))


def _normalizar(txt: str) -> str:
    return unicodedata.normalize("NFKD", str(txt)).encode("ascii", "ignore").decode().strip().lower()


def _titulo_acima(bruto: pd.DataFrame, h: int, max_linhas: int = 6) -> str:
    """Coleta as linhas de texto acima do cabeçalho, podendo atravessar um
    separador 'xxxx'. Retorna as até max_linhas linhas mais próximas."""
    linhas, cruzou_sep, r = [], False, h - 1
    while r >= 0 and len(linhas) < max_linhas:
        vals = [str(v).strip() for v in bruto.iloc[r].dropna().tolist() if str(v).strip()]
        if any("xxx" in v.lower() for v in vals):
            if cruzou_sep:
                break
            cruzou_sep = True
            r -= 1
            continue
        if vals and not vals[0].startswith(("(", "(tudo")):
            linhas.append(vals[0])
        r -= 1
    return " | ".join(reversed(linhas))


def extrair_tabelas_mensais(caminho: Path, aba: Optional[str] = None) -> list[dict]:
    """
    Percorre a planilha da ANP e extrai todas as tabelas mensais (ANO x Mês).
    Layout padrão ANP: linha com célula exatamente 'ANO'; abaixo, linha com
    'Mês/MÊS/Meses' seguida dos anos; seguem os meses até 'Total do Ano'.
    O título é reconstruído a partir das linhas de texto acima do cabeçalho.
    Retorna lista de dicts: {'titulo': str, 'tabela': DataFrame longo}.
    """
    bruto = pd.read_excel(caminho, **({"sheet_name": aba} if aba else {}), header=None)

    cabecalhos = []
    for i in range(len(bruto)):
        for c in range(bruto.shape[1]):
            if str(bruto.iat[i, c]).strip().upper() == "ANO":
                linha_seg = bruto.iloc[i + 1]
                cols_lbl = [
                    cl for cl in range(bruto.shape[1])
                    if _normalizar(linha_seg.iat[cl]) in ("mes", "meses")
                ]
                cabecalhos.append((i, c, cols_lbl[0] if cols_lbl else c - 1))

    resultados = []
    for h, c_ano, c_lbl in cabecalhos:
        anos = pd.to_numeric(
            bruto.iloc[h + 1].iloc[c_ano:], errors="coerce"
        ).round().astype("Int64").tolist()

        registros, vazias_consecutivas = [], 0
        for r in range(h + 2, len(bruto)):
            rotulo = _normalizar(bruto.iat[r, c_lbl])
            if rotulo.startswith(("total", "med")):
                break
            if rotulo in MESES_PT:
                valores = pd.to_numeric(
                    bruto.iloc[r].iloc[c_ano:], errors="coerce"
                ).tolist()
                registros.extend(
                    {"ANO": int(a), "MES_NUM": MESES_PT[rotulo], "BARRIS": float(v)}
                    for a, v in zip(anos, valores)
                    if pd.notna(a) and pd.notna(v)
                )
                vazias_consecutivas = 0
            else:
                vazias_consecutivas += 1
                if vazias_consecutivas > 25:
                    break

        if registros:
            resultados.append({
                "titulo": _titulo_acima(bruto, h),
                "tabela": pd.DataFrame(registros),
            })
    return resultados


def filtrar_anos(df: pd.DataFrame) -> pd.DataFrame:
    return df[df["ANO"].isin(ANOS_ALVO)].reset_index(drop=True)


def _linha_titulo(titulo: str) -> list[str]:
    return [ln.strip() for ln in titulo.split("|") if ln.strip()]


# --------------------------------------------------------------------------- #
# 1) Importações e Exportações de petróleo (barris)
# --------------------------------------------------------------------------- #
print("[1/4] Extraindo importações/exportações de petróleo (barris)...")
tabelas_ie = extrair_tabelas_mensais(RAW / "importacoes-exportacoes-b.xlsx")
for t in tabelas_ie:
    print(f"      -> {t['titulo'].split(' | ')[-1]} ({len(t['tabela'])} linhas)")

tab_imp = next(t["tabela"] for t in tabelas_ie
               if any(ln.startswith("Importação de petróleo") for ln in _linha_titulo(t["titulo"])))
tab_exp = next(t["tabela"] for t in tabelas_ie
               if any(ln.startswith("Exportação de petróleo") for ln in _linha_titulo(t["titulo"])))
imp_mensal = filtrar_anos(tab_imp).rename(columns={"BARRIS": "IMPORTACAO_BARRIS"})
exp_mensal = filtrar_anos(tab_exp).rename(columns={"BARRIS": "EXPORTACAO_BARRIS"})

# --------------------------------------------------------------------------- #
# 2) Produção nacional de petróleo (barris) — BRASIL / PETRÓLEO TOTAL
# --------------------------------------------------------------------------- #
print("[2/4] Extraindo produção nacional de petróleo (barris)...")
tabelas_prod = extrair_tabelas_mensais(RAW / "producao-petroleo-b.xls")
for t in tabelas_prod:
    print(f"      -> {t['titulo'].split(' | ')[-1]} ({len(t['tabela'])} linhas)")

tab_prod = next(t["tabela"] for t in tabelas_prod
                if "PETRÓLEO TOTAL" in t["titulo"]
                or any(ln.startswith("Produção nacional de petróleo") for ln in _linha_titulo(t["titulo"])))
prod_mensal = filtrar_anos(tab_prod).rename(columns={"BARRIS": "PRODUCAO_BARRIS"})

# --------------------------------------------------------------------------- #
# 3) Consolidação do fato mensal 2020–2025
# --------------------------------------------------------------------------- #
print("[3/4] Consolidando fato mensal 2020–2025...")
fato = (
    prod_mensal.merge(imp_mensal, on=["ANO", "MES_NUM"], how="outer")
    .merge(exp_mensal, on=["ANO", "MES_NUM"], how="outer")
    .sort_values(["ANO", "MES_NUM"])
    .reset_index(drop=True)
)
fato["BALANCA_COMERCIAL_BARRIS"] = fato["EXPORTACAO_BARRIS"] - fato["IMPORTACAO_BARRIS"]
fato["DATA"] = pd.to_datetime(
    fato["ANO"].astype(str) + "-" + fato["MES_NUM"].astype(str).str.zfill(2) + "-01"
)
meses_nomes = {v: k.capitalize() for k, v in MESES_PT.items()}
fato["MES_NOME"] = fato["MES_NUM"].map(meses_nomes)
fato["TRIMESTRE"] = ((fato["MES_NUM"] - 1) // 3) + 1

ordem = ["DATA", "ANO", "TRIMESTRE", "MES_NUM", "MES_NOME",
         "PRODUCAO_BARRIS", "IMPORTACAO_BARRIS", "EXPORTACAO_BARRIS",
         "BALANCA_COMERCIAL_BARRIS"]
fato = fato[ordem]
assert len(fato) == 72, f"Esperado 72 meses, obtido {len(fato)}"
assert fato[["PRODUCAO_BARRIS", "IMPORTACAO_BARRIS", "EXPORTACAO_BARRIS"]].isna().sum().sum() == 0
fato.to_csv(OUT / "fato_mensal_2020_2025.csv", index=False, encoding="utf-8-sig")
print(fato.groupby("ANO")[["PRODUCAO_BARRIS", "IMPORTACAO_BARRIS",
                            "EXPORTACAO_BARRIS"]].sum().div(1e6).round(1).to_string())

# --------------------------------------------------------------------------- #
# 4) Campos na Fase de Desenvolvimento e Produção → contagem anual por fase
# --------------------------------------------------------------------------- #
print("[4/4] Processando campos (Fase de Desenvolvimento e Produção)...")
campos = pd.read_csv(RAW / "extracao-campo.csv", encoding="utf-8-sig")
campos["INICIO_PRODUCAO_DT"] = pd.to_datetime(
    campos["DATA_INICIO_PRODUCAO"], format="%d/%m/%Y", errors="coerce"
)
campos["TERMINO_FASE_DT"] = pd.to_datetime(
    campos["TERMINO_FASE"], format="%d/%m/%Y", errors="coerce"
)

linhas_fase = []
for ano in ANOS_ALVO:
    ref = pd.Timestamp(year=ano, month=12, day=31)
    ativos = campos[campos["INICIO_PRODUCAO_DT"].notna() & (campos["INICIO_PRODUCAO_DT"] <= ref)]
    em_producao = ativos[
        (ativos["SITUACAO_CAMPO"] == "Produção") & (ativos["TERMINO_FASE_DT"] > ref)
    ]
    em_desenvolvimento = ativos[ativos["SITUACAO_CAMPO"] == "Desenvolvimento"]
    linhas_fase.append({
        "ANO": ano,
        "CAMPOS_EM_PRODUCAO": int(len(em_producao)),
        "CAMPOS_EM_DESENVOLVIMENTO": int(len(em_desenvolvimento)),
        "CAMPOS_TOTAL_FASE": int(len(em_producao) + len(em_desenvolvimento)),
    })

dim_fase = pd.DataFrame(linhas_fase)
dim_fase.to_csv(OUT / "dim_campos_fase_anual.csv", index=False, encoding="utf-8-sig")

campos_saida = campos.drop(columns=["INICIO_PRODUCAO_DT", "TERMINO_FASE_DT"])
campos_saida.to_csv(OUT / "dim_campos.csv", index=False, encoding="utf-8-sig")

por_bacia = (
    campos[campos["SITUACAO_CAMPO"] == "Produção"]
    .groupby(["BACIA", "AMBIENTE"], as_index=False)["CAMPO"].count()
    .rename(columns={"CAMPO": "CAMPOS_EM_PRODUCAO"})
)
por_bacia.to_csv(OUT / "dim_campos_bacia.csv", index=False, encoding="utf-8-sig")

# --------------------------------------------------------------------------- #
# 5) Agregado anual + indicadores de cruzamento
# --------------------------------------------------------------------------- #
anual = fato.groupby("ANO", as_index=False)[
    ["PRODUCAO_BARRIS", "IMPORTACAO_BARRIS", "EXPORTACAO_BARRIS", "BALANCA_COMERCIAL_BARRIS"]
].sum()
anual = anual.merge(dim_fase, on="ANO", how="left")
for coluna in ["PRODUCAO_BARRIS", "IMPORTACAO_BARRIS", "EXPORTACAO_BARRIS"]:
    anual[f"{coluna}_YOY_PCT"] = anual[coluna].pct_change() * 100
anual["COBERTURA_EXPORT_PCT"] = anual["EXPORTACAO_BARRIS"] / anual["PRODUCAO_BARRIS"] * 100
anual["DEPENDENCIA_IMPORT_PCT"] = anual["IMPORTACAO_BARRIS"] / anual["PRODUCAO_BARRIS"] * 100
anual.to_csv(OUT / "fato_anual_2020_2025.csv", index=False, encoding="utf-8-sig")

print("\n=== CRUZAMENTO ANUAL (produção x comércio exterior x fases) ===")
visao = anual[["ANO", "PRODUCAO_BARRIS", "EXPORTACAO_BARRIS", "IMPORTACAO_BARRIS",
               "COBERTURA_EXPORT_PCT", "CAMPOS_EM_PRODUCAO", "CAMPOS_EM_DESENVOLVIMENTO"]]
print(visao.to_string(index=False))

print("\nArquivos gerados em data/processed:")
for arq in sorted(OUT.glob("*.csv")):
    print(" -", arq.name)
