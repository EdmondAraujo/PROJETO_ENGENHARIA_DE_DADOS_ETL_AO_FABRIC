#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
app.py — Produto Streamlit (Opção B) integrado ao pipeline AWS SaaS Sales.

Interface leve sobre os mesmos módulos de src/ usados pela CLI (main.py):
  - ingestão e validação do CSV do Kaggle
  - pré-processamento e engenharia de atributos SaaS
  - A/B test com gate de SRM (chi-quadrado + binomial exato em células <= 30)
  - modelagem preditiva com loop de minimização de MSE (GridSearchCV + CV)
  - relatório executivo em markdown

Execução:
    streamlit run app.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Garante import dos módulos src/ quando executado via streamlit run.
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import hashlib

import pandas as pd
import streamlit as st
import plotly.graph_objects as go
from plotly.colors import qualitative as plotly_qualitative  # noqa: E402

from src.ingestion import load_saas_sales, validate_loaded  # noqa: E402
from src.preprocessing import prepare  # noqa: E402
from src.ab_test import (  # noqa: E402
    run_ab_test,
    ALPHA,
    SRM_EXPECTED_SPLIT,
)
from src.modeling import train_and_evaluate_by_customer  # noqa: E402
from src.report import build_executive_report  # noqa: E402

DEFAULT_DATA_PATH = ROOT / "data" / "SaaS-Sales.csv"


# ---------------------------------------------------------------------------
# Configuração da página
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="AWS SaaS Sales — Pipeline de Crescimento",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("AWS SaaS Sales — Pipeline de Crescimento (Mínimo MSE)")
st.caption(
    "Ingestão do dataset Kaggle nnthanh101/aws-saas-sales · A/B test com gate de SRM · "
    "Modelagem preditiva com minimização de Mean Squared Error (MSE) · Relatório executivo."
)


# ---------------------------------------------------------------------------
# Sidebar — controles
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("⚙️ Configuração")

    uploaded = st.file_uploader(
        "Enviar CSV do AWS SaaS Sales",
        type=["csv"],
        help="Se não enviar, usa data/SaaS-Sales.csv (extraído do zip do Kaggle).",
    )

    seed = st.number_input("Seed aleatória (reprodutibilidade)", min_value=0, value=42, step=1)
    test_size = st.slider("Proporção de teste (hold-out)", 0.1, 0.4, 0.2, 0.05)
    run_ab = st.toggle("Executar teste A/B", value=True)

    st.divider()
    st.markdown("### Sobre")
    st.markdown(
        "- **Opção B** (este app): interface sobre os mesmos módulos de `src/` da CLI.\n"
        "- **Opção A** (CLI): `python main.py --data data/SaaS-Sales.csv`.\n"
        "- Gate de SRM roda **antes** de qualquer métrica de negócio.\n"
        "- Split treino/teste por `Customer ID` (sem vazamento de cliente)."
    )


# ---------------------------------------------------------------------------
# Carregamento de dados
# ---------------------------------------------------------------------------
@st.cache_data(show_spinner="Carregando e validando o dataset...")
def carregar_dados(file_bytes: bytes | None, path: Path, seed: int):
    """Carrega CSV (upload ou padrão) e prepara os dados. Retorna (df, prepared, msg)."""
    if file_bytes is not None:
        import io

        df = pd.read_csv(io.BytesIO(file_bytes))
    else:
        df = load_saas_sales(path)

    validate_loaded(df)
    prepared = prepare(df)
    # Fingerprint dos dados para invalidar cache quando os dados mudam.
    data_fingerprint = hashlib.sha256(
        pd.util.hash_pandas_object(df, index=True).values.tobytes()
    ).hexdigest()[:16]
    return df, prepared, data_fingerprint, None


data_source = DEFAULT_DATA_PATH
file_bytes = uploaded.getvalue() if uploaded is not None else None

try:
    df, prepared, data_fingerprint, err = carregar_dados(file_bytes, data_source, int(seed))
except FileNotFoundError as exc:
    st.error(str(exc))
    st.stop()
except ValueError as exc:
    st.error(f"Erro de validação: {exc}")
    st.stop()
except Exception as exc:  # pragma: no cover
    st.error(f"Erro inesperado ao carregar dados: {type(exc).__name__}: {exc}")
    st.stop()

# Invalida caches quando os dados mudam.
if "data_fingerprint" not in st.session_state or st.session_state["data_fingerprint"] != data_fingerprint:
    st.session_state["data_fingerprint"] = data_fingerprint
    # Limpa caches de A/B e modelagem quando os dados mudam.
    keys_to_pop = [k for k in st.session_state.keys() if k.startswith("ab_") or k.startswith("model_")]
    for k in keys_to_pop:
        st.session_state.pop(k, None)

# ---------------------------------------------------------------------------
# Abas do produto
# ---------------------------------------------------------------------------
tab_dados, tab_ab, tab_modelo, tab_relatorio = st.tabs(
    ["1. Dados", "2. A/B Test", "3. Modelagem (MSE)", "4. Relatório Executivo"]
)

# ===========================================================================
# Aba 1 — Dados
# ===========================================================================
with tab_dados:
    st.subheader("Dataset — AWS SaaS Sales")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Pedidos (linhas)", f"{len(df):,}")
    c2.metric("Colunas", df.shape[1])
    c3.metric("Clientes únicos", f"{prepared.df_customers['Customer ID'].nunique():,}")
    c4.metric("Período", f"{df['Order Date'].min():%d/%m/%Y} → {df['Order Date'].max():%d/%m/%Y}")

    st.markdown("### Amostra dos dados")
    st.dataframe(df.head(10), use_container_width=True)

    st.markdown("### Distribuição por Segmento (proxy de subscription tier)")
    seg = df["Segment"].value_counts().sort_index()
    fig_seg = go.Figure(
        data=[go.Bar(x=seg.index.astype(str), y=seg.values,
                     marker_color=plotly_qualitative.Plotly[: len(seg)])]
    )
    fig_seg.update_layout(
        xaxis_title="Segmento", yaxis_title="Número de pedidos", showlegend=False, height=350
    )
    st.plotly_chart(fig_seg, use_container_width=True)

    st.markdown("### Estatísticas descritivas")
    st.dataframe(df[["Sales", "Profit", "Quantity", "Discount"]].describe(), use_container_width=True)

# ===========================================================================
# Aba 2 — A/B Test
# ===========================================================================
with tab_ab:
    st.subheader("A/B Test — Saúde do Experimento")

    if not run_ab:
        st.info("Teste A/B desativado na barra lateral.")
        st.session_state.pop(f"ab_{data_fingerprint}_{int(seed)}", None)
    else:
        cache_key = f"ab_{data_fingerprint}_{int(seed)}"
        if cache_key not in st.session_state:
            with st.spinner("Executando A/B test com gate de SRM..."):
                st.session_state[cache_key] = run_ab_test(
                    prepared.df_customers, prepared.df_orders, seed=int(seed)
                )
        ab = st.session_state[cache_key]

        srm = ab.srm
        st.markdown("### Gate de SRM (Sample Ratio Mismatch)")
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Clientes Control", f"{srm.observed_control:,}")
        m2.metric("Clientes Treatment", f"{srm.observed_treatment:,}")
        m3.metric("Esperado (50/50)", f"{srm.expected_control:,.0f} / {srm.expected_treatment:,.0f}")
        m4.metric("Método", srm.method.replace("_", " ").title())

        st.write(
            f"**Chi²:** {srm.chi2:.4f}  |  **p-value:** {srm.p_value:.6f}"
            + (f"  |  **Binomial exato (células ≤ 30):** p={srm.exact_p_value:.6f}" if srm.exact_p_value is not None else "")
        )
        if srm.srm_flagged:
            st.error(f"🚫 Gate SRM **FALHOU** — amostra desbalanceada. Métricas de negócio suprimidas. Veredito: RERUN.")
        else:
            st.success("✅ Gate SRM **APROVADO** — split íntegro.")

        st.divider()
        st.markdown("### Resultados (apenas se SRM aprovado)")
        if srm.srm_flagged:
            st.warning("Leituras de negócio suprimidas por integridade de tráfego.")
        else:
            conv = ab.conversion
            ms = ab.mean_sales
            c1, c2, c3 = st.columns(3)
            c1.metric("Conversão Control", f"{conv.control_rate*100:.2f}%")
            c2.metric("Conversão Treatment", f"{conv.treatment_rate*100:.2f}%")
            c3.metric("Lift absoluto", f"{conv.abs_lift*100:+.2f} pp")

            st.write(
                f"- **z:** {conv.z_stat:.4f}  |  **p-value:** {conv.p_value:.6f}  |  "
                f"**Significativo (α={ALPHA}):** {'Sim' if conv.significant else 'Não'}"
            )
            st.write(
                f"- **IC 95% do lift:** [{conv.ci_low*100:+.2f} pp, {conv.ci_high*100:+.2f} pp]"
            )

            st.markdown("#### Ticket médio (Sales por pedido, Welch t-test)")
            c4, c5, c6 = st.columns(3)
            c4.metric("Média Control", f"${ms.control_mean:,.2f}")
            c5.metric("Média Treatment", f"${ms.treatment_mean:,.2f}")
            c6.metric("Diferença", f"${ms.abs_diff:+,.2f}")
            st.write(
                f"- **t:** {ms.t_stat:.4f}  |  **p-value:** {ms.p_value:.6f}  |  "
                f"**Significativo:** {'Sim' if ms.significant else 'Não'}"
            )
            st.write(f"- **IC 95%:** [${ms.ci_low:+,.2f}, ${ms.ci_high:+,.2f}]")

            st.markdown(f"### Veredito Executivo: **{ab.decision}**")
            decisoes = {
                "SHIP": "Resultado significativo e consistente: considerar rollout para 100% do tráfego.",
                "KEEP_RUNNING": "Sinal significativo, mas power/amostra insuficiente: continuar coleta.",
                "ITERATE": "Sem evidência suficiente: iterar a variação e reavaliar o MDE.",
                "RERUN": "Falha de integridade do split: auditar assignment antes de decidir.",
            }
            st.info(decisoes.get(ab.decision, ""))

# ===========================================================================
# Aba 3 — Modelagem (MSE)
# ===========================================================================
with tab_modelo:
    st.subheader("Modelagem Preditiva — Loop de Minimização de MSE")

    model_cache_key = f"model_{data_fingerprint}_{int(seed)}_{test_size}"
    if model_cache_key not in st.session_state:
        try:
            with st.spinner("Treinando modelos com GridSearchCV (5-fold, MSE de probabilidade/Brier)..."):
                st.session_state[model_cache_key] = train_and_evaluate_by_customer(
                    prepared.X,
                    prepared.df_orders,
                    prepared.y_sales,
                    prepared.y_profit,
                    prepared.y_conversion,
                    seed=int(seed),
                    test_size=test_size,
                )
        except Exception as exc:
            st.error(f"Erro durante o treinamento: {type(exc).__name__}: {exc}")
            st.stop()
    res = st.session_state[model_cache_key]

    st.markdown(
        "Procedimento: GridSearchCV sobre **Ridge / RandomForest / GradientBoosting**; "
        "seleção do **menor MSE de CV**; avaliação final no hold-out (sem vazamento de cliente)."
    )

    # Cards dos três alvos
    st.markdown("### Resultados por alvo")

    def regressao_card(title: str, r):
        with st.container(border=True):
            st.markdown(f"#### {title}")
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Melhor modelo", r.best_model_name)
            c2.metric("MSE teste", f"{r.mse_test:,.4f}")
            c3.metric("RMSE teste", f"{r.rmse_test:,.4f}")
            c4.metric("R² teste", f"{r.r2_test:.4f}")
            st.write(f"**Hiperparâmetros:** `{r.best_params}`")
            st.write(f"**MSE de CV (seleção):** {max(0.0, r.best_cv_mse):,.6f}")
            st.write(
                f"**Treino:** MSE={r.mse_train:,.4f} | RMSE={r.rmse_train:,.4f} | R²={r.r2_train:.4f}"
            )
            st.write(
                f"**Razão overfitting (teste/treino):** {r.overfitting_ratio:.3f}  "
                f"→ {'baixo (boa generalização)' if r.overfitting_ratio < 1.25 else 'moderado' if r.overfitting_ratio < 1.5 else 'alto (possível overfitting)'}"
            )

    regressao_card("Regressão — Sales (valor do pedido)", res.sales)
    regressao_card("Regressão — Profit (lucro)", res.profit)

    st.markdown("#### Classificação — Conversão (high_value)")
    with st.container(border=True):
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Melhor modelo", res.conversion.best_model_name)
        c2.metric("MSE probabilidade (teste)", f"{res.conversion.mse_test_prob:.6f}")
        c3.metric("Acurácia (teste)", f"{res.conversion.accuracy_test:.4f}")
        c4.metric("ROC AUC (teste)", "n/d" if res.conversion.roc_auc_test is None else f"{res.conversion.roc_auc_test:.4f}")
        st.write(f"**Hiperparâmetros:** `{res.conversion.best_params}`")
        st.write(f"**MSE de CV (seleção):** {max(0.0, res.conversion.best_cv_mse):,.6f}")

    # Gráfico comparativo MSE treino vs teste (regressões)
    st.markdown("### Comparativo MSE — Treino vs Teste")
    modelos = ["Sales (Ridge)" if res.sales.best_model_name == "Ridge" else f"Sales ({res.sales.best_model_name})",
               "Profit (GradientBoosting)" if res.profit.best_model_name == "GradientBoosting" else f"Profit ({res.profit.best_model_name})"]
    fig = go.Figure()
    fig.add_trace(go.Bar(name="MSE Treino", x=modelos, y=[res.sales.mse_train, res.profit.mse_train], marker_color="#4c78a8"))
    fig.add_trace(go.Bar(name="MSE Teste", x=modelos, y=[res.sales.mse_test, res.profit.mse_test], marker_color="#f58518"))
    fig.update_layout(barmode="group", yaxis_title="MSE", height=400, legend_title="Conjunto")
    st.plotly_chart(fig, use_container_width=True)

    # Curva de otimização (MSE de CV por modelo candidato) — placeholder informativo
    st.markdown("### Seleção pelo menor MSE de CV")
    cv_data = {
        "Alvo": ["Sales", "Profit", "Conversão"],
        "Modelo selecionado": [res.sales.best_model_name, res.profit.best_model_name, res.conversion.best_model_name],
        "MSE de CV": [res.sales.best_cv_mse, res.profit.best_cv_mse, res.conversion.best_cv_mse],
    }
    st.dataframe(pd.DataFrame(cv_data), use_container_width=True, hide_index=True)

    melhor = min([res.sales, res.profit], key=lambda r: r.mse_test)
    st.success(
        f"🏆 Menor MSE de teste: **{melhor.best_model_name}** para **{melhor.target}** "
        f"(MSE = {melhor.mse_test:,.4f}, RMSE = {melhor.rmse_test:,.4f}, R² = {melhor.r2_test:.4f})"
    )

# ===========================================================================
# Aba 4 — Relatório Executivo
# ===========================================================================
with tab_relatorio:
    st.subheader("Relatório Executivo")
    ab_obj = st.session_state.get(f"ab_{data_fingerprint}_{int(seed)}") if run_ab else None
    texto = build_executive_report(df, prepared, ab_obj, res)
    st.markdown(texto)
    st.download_button(
        label="Baixar relatório (markdown)",
        data=texto,
        file_name="relatorio_executivo_saas_sales.md",
        mime="text/markdown",
    )
