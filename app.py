# =============================================================================
# SISTEMA DE APURAÇÃO DE RENTABILIDADE FÍSICA - VAREJO E ATACADO
# Frontend: Streamlit | Backend: Microsoft SQL Server | Conexão: pyodbc
# Autor: Arquitetura Corporativa / Engenharia Financeira
# Python 3.11+ | 4 Abas com Governança e Separação de Funções
# =============================================================================

import os
import io
import time
import traceback
from datetime import datetime
from decimal import Decimal

import pandas as pd
import numpy as np
import numpy_financial as npf
import streamlit as st
import pyodbc
from dotenv import load_dotenv

# Carrega variáveis de ambiente do arquivo .env (se existir)
load_dotenv()

# ---------------------------------------------------------------------------
# CONFIGURAÇÃO GLOBAL DA PÁGINA
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Rentabilidade Física | Varejo & Atacado",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Mapeamento de colunas esperadas no CSV / DataFrame em sessão
COLUNAS_PLANO_CONTAS = [
    "Periodo",
    "Tipo_Dado",
    "Capex_1_00",
    "Receita_Bruta_2_00",
    "Deducoes_2_03",
    "Custos_Variaveis_3_00",
    "Despesas_Fixas_4_00",
]

COLUNAS_NUMERICAS = [
    "Capex_1_00",
    "Receita_Bruta_2_00",
    "Deducoes_2_03",
    "Custos_Variaveis_3_00",
    "Despesas_Fixas_4_00",
]

# Estado inicial da sessão
if "df_lancamentos" not in st.session_state:
    st.session_state.df_lancamentos = pd.DataFrame(columns=COLUNAS_PLANO_CONTAS)

if "calculo_executado" not in st.session_state:
    st.session_state.calculo_executado = False

if "df_resultado" not in st.session_state:
    st.session_state.df_resultado = pd.DataFrame()

if "kpis" not in st.session_state:
    st.session_state.kpis = {}

if "ultimo_projeto_id" not in st.session_state:
    st.session_state.ultimo_projeto_id = None

if "ultimo_projeto_nome" not in st.session_state:
    st.session_state.ultimo_projeto_nome = ""

# =============================================================================
# FUNÇÕES AUXILIARES - CONEXÃO E BANCO DE DADOS
# =============================================================================

def init_connection():
    """
    Inicializa e retorna uma conexão pyodbc com o SQL Server.

    Lê obrigatoriamente as credenciais das variáveis de ambiente (via python-dotenv / os.environ).
    Nenhuma senha é exposta no código-fonte.

    Variáveis esperadas no .env:
        DB_SERVER, DB_DATABASE, DB_UID, DB_PWD, DB_PORT, DB_DRIVER

    Returns:
        pyodbc.Connection: Conexão aberta com o banco.

    Raises:
        ValueError: Se alguma variável obrigatória não estiver definida.
        pyodbc.Error: Se a conexão falhar.
    """
    server = os.environ.get("DB_SERVER")
    database = os.environ.get("DB_DATABASE")
    uid = os.environ.get("DB_UID")
    pwd = os.environ.get("DB_PWD")
    port = os.environ.get("DB_PORT", "1433")
    driver = os.environ.get("DB_DRIVER", "ODBC Driver 17 for SQL Server")
    timeout = os.environ.get("DB_TIMEOUT", "30")
    encrypt = os.environ.get("DB_ENCRYPT", "yes")
    trust_cert = os.environ.get("DB_TRUST_CERT", "yes")

    # Validação de variáveis obrigatórias
    faltantes = []
    for var_name, var_val in [
        ("DB_SERVER", server),
        ("DB_DATABASE", database),
        ("DB_UID", uid),
        ("DB_PWD", pwd),
    ]:
        if not var_val:
            faltantes.append(var_name)

    if faltantes:
        raise ValueError(
            f"Variáveis de ambiente obrigatórias não definidas: {', '.join(faltantes)}. "
            f"Verifique o arquivo .env e o docker-compose.yml (env_file)."
        )

    # Monta string de conexão ODBC
    # Formato: DRIVER={ODBC Driver 17 for SQL Server};SERVER=host,port;DATABASE=db;UID=user;PWD=pass;Encrypt=yes;TrustServerCertificate=yes;
    conn_str = (
        f"DRIVER={{{driver}}};"
        f"SERVER={server},{port};"
        f"DATABASE={database};"
        f"UID={uid};"
        f"PWD={pwd};"
        f"Encrypt={encrypt};"
        f"TrustServerCertificate={trust_cert};"
        f"Connection Timeout={timeout};"
    )

    conn = pyodbc.connect(conn_str)
    return conn


def inserir_projeto_e_lancamentos(
    nome: str,
    canal: str,
    escala: str,
    tma: float,
    df: pd.DataFrame,
):
    """
    Insere um projeto e seus lançamentos financeiros de forma transacional.

    - Cria registro em TB_PROJETOS e recupera o ID gerado (SCOPE_IDENTITY).
    - Insere todos os lançamentos em TB_LANCAMENTOS_FINANCEIROS com executemany.
    - Utiliza transação explícita: commit apenas se tudo ocorrer com sucesso,
      rollback em caso de qualquer erro.

    Args:
        nome: Nome do projeto.
        canal: 'Varejo' ou 'Atacado'.
        escala: 'Mensal' ou 'Anual'.
        tma: Taxa Mínima de Atratividade em % (ex: 12.00).
        df: DataFrame com colunas do plano de contas.

    Returns:
        int: ID do projeto recém-criado.

    Raises:
        Exception: Qualquer erro de banco com rollback automático.
    """
    conn = init_connection()
    try:
        conn.autocommit = False
        cursor = conn.cursor()

        # 1. Inserir projeto
        cursor.execute(
            """
            INSERT INTO dbo.TB_PROJETOS (nome, canal, escala_temporal, tma_percentual)
            VALUES (?, ?, ?, ?)
            """,
            (nome, canal, escala, tma),
        )
        # Recupera ID gerado
        cursor.execute("SELECT SCOPE_IDENTITY()")
        id_projeto = int(cursor.fetchval())

        # 2. Preparar dados para inserção em massa
        registros = []
        for _, row in df.iterrows():
            registros.append(
                (
                    id_projeto,
                    int(row["Periodo"]),
                    str(row["Tipo_Dado"]),
                    float(row["Capex_1_00"]),
                    float(row["Receita_Bruta_2_00"]),
                    float(row["Deducoes_2_03"]),
                    float(row["Custos_Variaveis_3_00"]),
                    float(row["Despesas_Fixas_4_00"]),
                )
            )

        # 3. Inserção transacional em massa
        cursor.executemany(
            """
            INSERT INTO dbo.TB_LANCAMENTOS_FINANCEIROS
                (id_projeto, Periodo, Tipo_Dado, Capex_1_00, Receita_Bruta_2_00,
                 Deducoes_2_03, Custos_Variaveis_3_00, Despesas_Fixas_4_00)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            registros,
        )

        conn.commit()
        return id_projeto

    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


def testar_conexao_odbc():
    """
    Testa a conectividade ODBC com o SQL Server e retorna diagnóstico.

    Returns:
        tuple[bool, str]: (sucesso, mensagem_diagnostico)
    """
    try:
        conn = init_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT 1 AS teste_conexao;")
        row = cursor.fetchone()
        # Lista drivers disponíveis
        drivers = pyodbc.drivers()
        # Verifica tabelas existentes
        cursor.execute(
            "SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA='dbo' ORDER BY TABLE_NAME"
        )
        tabelas = [r[0] for r in cursor.fetchall()]
        conn.close()
        msg = (
            f"✅ Conexão ODBC estabelecida com sucesso.\n"
            f"- Teste SELECT 1: {row[0]}\n"
            f"- Drivers ODBC disponíveis: {drivers}\n"
            f"- Tabelas no schema dbo: {tabelas if tabelas else 'nenhuma (execute schema.sql)'}\n"
            f"- Variáveis .env: DB_SERVER={os.environ.get('DB_SERVER')}, "
            f"DB_DATABASE={os.environ.get('DB_DATABASE')}, "
            f"DB_UID={os.environ.get('DB_UID')}, DB_PORT={os.environ.get('DB_PORT')}"
        )
        return True, msg
    except Exception as e:
        drivers = []
        try:
            drivers = pyodbc.drivers()
        except Exception:
            pass
        msg = (
            f"❌ Falha na conexão ODBC:\n{str(e)}\n"
            f"- Drivers disponíveis: {drivers}\n"
            f"- Verifique .env, firewall, se o SQL Server está acessível e se o driver ODBC 17 está instalado.\n"
            f"- Traceback:\n{traceback.format_exc()}"
        )
        return False, msg


# =============================================================================
# FUNÇÕES AUXILIARES - CÁLCULO FINANCEIRO
# =============================================================================

def formatar_moeda(valor: float) -> str:
    """Formata valor numérico como moeda brasileira R$ 1.234,56."""
    try:
        if pd.isna(valor):
            return "R$ 0,00"
        # Formato: R$ 1.234,56 (ponto milhar, vírgula decimal)
        formatted = f"R$ {valor:,.2f}"
        # Converte para padrão BR: troca , por X temporário, . por ,, X por .
        # Ex: 1234.56 -> "R$ 1,234.56" -> "R$ 1.234,56"
        formatted = formatted.replace(",", "X").replace(".", ",").replace("X", ".")
        return formatted
    except Exception:
        return str(valor)


def calcular_metricas(df: pd.DataFrame, tma_percentual: float, canal: str):
    """
    Motor de cálculo financeiro centralizado.

    Calcula para cada período:
        - Receita Líquida = Receita_Bruta - Deduções
        - Margem de Contribuição = Receita Líquida - Custos Variáveis
        - Fluxo de Caixa Líquido = Margem - Despesas Fixas - Capex
        - Fluxo Descontado = FCL / (1 + TMA)^periodo
        - Fluxo Descontado Acumulado (soma acumulada)

    KPIs:
        - VPL (Valor Presente Líquido) = soma dos fluxos descontados
        - TIR (Taxa Interna de Retorno) via numpy_financial.irr
        - Payback Descontado exato (interpolação linear)
        - ROIC Operacional = Lucro Operacional último período / Capex total

    Args:
        df: DataFrame com colunas do plano de contas (ordenado por Periodo).
        tma_percentual: TMA em % (ex: 12.0 para 12%).
        canal: 'Varejo' ou 'Atacado' (para alertas setoriais).

    Returns:
        tuple[pd.DataFrame, dict]: (df_resultado_detalhado, kpis)
    """
    df_calc = df.copy()
    df_calc = df_calc.sort_values("Periodo").reset_index(drop=True)

    tma = tma_percentual / 100.0

    # --- Linhas calculadas ---
    df_calc["Receita_Liquida"] = df_calc["Receita_Bruta_2_00"] - df_calc["Deducoes_2_03"]
    df_calc["Margem_Contribuicao"] = df_calc["Receita_Liquida"] - df_calc["Custos_Variaveis_3_00"]
    # Fluxo de Caixa Líquido = Margem - Despesas Fixas - Capex (Capex é saída de caixa)
    df_calc["Fluxo_Caixa_Liquido"] = (
        df_calc["Margem_Contribuicao"] - df_calc["Despesas_Fixas_4_00"] - df_calc["Capex_1_00"]
    )
    # Fluxo Descontado
    df_calc["Fluxo_Descontado"] = df_calc.apply(
        lambda r: r["Fluxo_Caixa_Liquido"] / ((1 + tma) ** int(r["Periodo"])), axis=1
    )
    df_calc["Fluxo_Descontado_Acumulado"] = df_calc["Fluxo_Descontado"].cumsum()

    # --- KPIs ---
    # VPL = soma dos fluxos descontados
    vpl = float(df_calc["Fluxo_Descontado"].sum())

    # TIR: usa série de fluxos não descontados [FCL período 1, 2, ...]
    # numpy_financial.irr espera array com investimento inicial negativo
    fluxos = df_calc["Fluxo_Caixa_Liquido"].tolist()
    try:
        tir_decimal = npf.irr(fluxos)
        if tir_decimal is None or np.isnan(tir_decimal) or np.isinf(tir_decimal):
            tir_percentual = None
        else:
            tir_percentual = float(tir_decimal * 100)
    except Exception:
        tir_percentual = None

    # Payback Descontado exato (interpolação)
    payback = None
    acumulado = df_calc["Fluxo_Descontado_Acumulado"].tolist()
    for i in range(len(acumulado)):
        if acumulado[i] >= 0:
            if i == 0:
                payback = float(df_calc.iloc[i]["Periodo"])
            else:
                # Interpolação linear entre período anterior (negativo) e atual (positivo)
                anterior = acumulado[i - 1]
                atual = acumulado[i]
                fracao = abs(anterior) / (atual - anterior) if (atual - anterior) != 0 else 0
                payback = float(df_calc.iloc[i - 1]["Periodo"] + fracao)
            break
    # Se nunca ficou positivo, payback = None (não recuperado)

    # ROIC Operacional = Lucro operacional líquido do último período / Capex total acumulado
    # Lucro operacional líquido = Margem - Despesas Fixas (sem Capex, pois Capex é investimento)
    capex_total = float(df_calc["Capex_1_00"].sum())
    ultimo_idx = len(df_calc) - 1
    lucro_operacional_ultimo = float(
        df_calc.iloc[ultimo_idx]["Margem_Contribuicao"] - df_calc.iloc[ultimo_idx]["Despesas_Fixas_4_00"]
    )
    if capex_total != 0:
        roic = (lucro_operacional_ultimo / capex_total) * 100
    else:
        roic = 0.0

    # Giro do Ativo = Receita Líquida total / Capex total (aprox. Ativo)
    receita_liquida_total = float(df_calc["Receita_Liquida"].sum())
    giro_ativo = (receita_liquida_total / capex_total) if capex_total != 0 else 0

    kpis = {
        "VPL": vpl,
        "TIR": tir_percentual,
        "Payback": payback,
        "ROIC": roic,
        "Giro_Ativo": giro_ativo,
        "Capex_Total": capex_total,
        "Receita_Liquida_Total": receita_liquida_total,
    }

    return df_calc, kpis


def gerar_template_demo() -> pd.DataFrame:
    """
    Gera DataFrame de demonstração/homologação com 4 períodos.

    - Período 1: Capex inicial elevado, sem receita (fase de investimento), Realizado
    - Períodos 2-4: receitas/despesas crescentes, alternando Realizado/Projetado

    Returns:
        pd.DataFrame com colunas do plano de contas.
    """
    dados = [
        {
            "Periodo": 1,
            "Tipo_Dado": "Realizado",
            "Capex_1_00": 500000.00,
            "Receita_Bruta_2_00": 0.00,
            "Deducoes_2_03": 0.00,
            "Custos_Variaveis_3_00": 0.00,
            "Despesas_Fixas_4_00": 15000.00,
        },
        {
            "Periodo": 2,
            "Tipo_Dado": "Realizado",
            "Capex_1_00": 50000.00,
            "Receita_Bruta_2_00": 320000.00,
            "Deducoes_2_03": 38400.00,
            "Custos_Variaveis_3_00": 128000.00,
            "Despesas_Fixas_4_00": 45000.00,
        },
        {
            "Periodo": 3,
            "Tipo_Dado": "Projetado",
            "Capex_1_00": 0.00,
            "Receita_Bruta_2_00": 450000.00,
            "Deducoes_2_03": 54000.00,
            "Custos_Variaveis_3_00": 180000.00,
            "Despesas_Fixas_4_00": 48000.00,
        },
        {
            "Periodo": 4,
            "Tipo_Dado": "Projetado",
            "Capex_1_00": 0.00,
            "Receita_Bruta_2_00": 580000.00,
            "Deducoes_2_03": 69600.00,
            "Custos_Variaveis_3_00": 232000.00,
            "Despesas_Fixas_4_00": 52000.00,
        },
    ]
    return pd.DataFrame(dados, columns=COLUNAS_PLANO_CONTAS)


def validar_dataframe(df: pd.DataFrame):
    """
    Valida DataFrame do plano de contas.

    Verifica:
        - Colunas obrigatórias presentes
        - Sem campos nulos
        - Colunas numéricas contêm apenas valores numéricos válidos
        - Periodo > 0 e Tipo_Dado em ('Realizado', 'Projetado')

    Returns:
        tuple[bool, str]: (válido, mensagem)
    """
    if df.empty:
        return False, "A tabela está vazia. Carregue um CSV ou use o Template de Demonstração."

    # Verifica colunas
    faltantes = [c for c in COLUNAS_PLANO_CONTAS if c not in df.columns]
    if faltantes:
        return False, f"Colunas obrigatórias ausentes: {faltantes}"

    # Verifica nulos
    if df[COLUNAS_PLANO_CONTAS].isnull().any().any():
        nulos = df[COLUNAS_PLANO_CONTAS].isnull().sum()
        detalhes = ", ".join([f"{c}: {n}" for c, n in nulos.items() if n > 0])
        return False, f"Existem campos nulos/vazios: {detalhes}"

    # Verifica numéricos
    for col in COLUNAS_NUMERICAS + ["Periodo"]:
        # Tenta converter para numérico
        convertido = pd.to_numeric(df[col], errors="coerce")
        if convertido.isnull().any():
            linhas = df[convertido.isnull()].index.tolist()
            return False, f"Coluna '{col}' contém valores não numéricos nas linhas: {linhas}"

    # Valida Tipo_Dado
    tipos_invalidos = df[~df["Tipo_Dado"].isin(["Realizado", "Projetado"])]
    if not tipos_invalidos.empty:
        return False, f"Tipo_Dado inválido encontrado. Permitidos: 'Realizado' ou 'Projetado'. Linhas: {tipos_invalidos.index.tolist()}"

    # Valida Periodo > 0
    if (pd.to_numeric(df["Periodo"]) <= 0).any():
        return False, "Todos os valores de 'Periodo' devem ser maiores que zero."

    return True, "Validação concluída com sucesso."


# =============================================================================
# SIDEBAR - INFORMAÇÕES CORPORATIVAS
# =============================================================================
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/3135/3135679.png", width=80)
    st.title("Governança Corporativa")
    st.markdown("""
    **Sistema de Apuração de Rentabilidade Física**
    
    - **Canais:** Varejo & Atacado
    - **Escalas:** Mensal / Anual
    - **Stack:** Python 3.11 + Streamlit + SQL Server
    - **Segurança:** Credenciais via `.env` (pyodbc)
    """)
    st.divider()
    st.caption("Separação de funções em 4 camadas (Abas).")
    # Indicador de dados carregados
    if not st.session_state.df_lancamentos.empty:
        st.success(f"📦 {len(st.session_state.df_lancamentos)} lançamento(s) em memória.")
    else:
        st.info("Nenhum dado carregado. Vá para a Aba 1.")

    # Status do cálculo
    if st.session_state.calculo_executado:
        st.success(f"✅ Projeto '{st.session_state.ultimo_projeto_nome}' calculado (ID: {st.session_state.ultimo_projeto_id})")
    st.divider()
    st.caption("© 2026 Engenharia Financeira & DevOps")

# =============================================================================
# TÍTULO PRINCIPAL
# =============================================================================
st.title("📊 Apuração de Rentabilidade Física")
st.subheader("Varejo e Atacado — Sistema Corporativo de Análise de Investimentos")
st.markdown("---")

# =============================================================================
# CRIAÇÃO DAS 4 ABAS (CAMADAS DE GOVERNANÇA)
# =============================================================================
tab1, tab2, tab3, tab4 = st.tabs(
    [
        "📥 1. Carga de Informações",
        "📝 2. Conferência e Edição",
        "⚙️ 3. Parâmetros do Sistema",
        "📈 4. Demonstrativo & Resultados",
    ]
)

# ---------------------------------------------------------------------------
# ABA 1: CARGA DE INFORMAÇÕES
# ---------------------------------------------------------------------------
with tab1:
    st.header("📥 Carga de Informações — Plano de Contas")
    st.markdown(
        "Faça upload de um arquivo **CSV** com as colunas do plano de contas estruturado, "
        "ou utilize o **Template de Demonstração** para homologação."
    )

    col_a, col_b = st.columns([2, 1])

    with col_a:
        st.subheader("Upload de Arquivo CSV")
        arquivo = st.file_uploader(
            "Selecione o arquivo .csv",
            type=["csv"],
            help="O CSV deve conter as colunas: Periodo, Tipo_Dado, Capex_1_00, Receita_Bruta_2_00, Deducoes_2_03, Custos_Variaveis_3_00, Despesas_Fixas_4_00",
        )

        if arquivo is not None:
            try:
                # Tenta ler com separador vírgula e ponto-e-vírgula (comum no Brasil)
                # Primeiro tenta com vírgula
                df_upload = pd.read_csv(arquivo, sep=None, engine="python")
                # Normaliza nomes de colunas (strip espaços)
                df_upload.columns = [c.strip() for c in df_upload.columns]

                # Verifica se colunas esperadas estão presentes
                colunas_encontradas = [c for c in COLUNAS_PLANO_CONTAS if c in df_upload.columns]
                if len(colunas_encontradas) < len(COLUNAS_PLANO_CONTAS):
                    st.warning(
                        f"⚠️ Colunas esperadas: {COLUNAS_PLANO_CONTAS}\n\n"
                        f"Colunas encontradas: {list(df_upload.columns)}\n\n"
                        f"Ajuste o CSV ou use o template."
                    )
                else:
                    # Filtra e ordena colunas
                    df_upload = df_upload[COLUNAS_PLANO_CONTAS]
                    # Converte numéricos
                    for col in COLUNAS_NUMERICAS + ["Periodo"]:
                        df_upload[col] = pd.to_numeric(df_upload[col], errors="coerce")

                    valido, msg = validar_dataframe(df_upload)
                    if valido:
                        st.session_state.df_lancamentos = df_upload.copy()
                        st.session_state.calculo_executado = False
                        st.success(f"✅ Arquivo carregado com {len(df_upload)} registros. Validação: {msg}")
                    else:
                        st.error(f"❌ Falha na validação: {msg}")
                        st.dataframe(df_upload, use_container_width=True)

                st.dataframe(df_upload, use_container_width=True)

            except Exception as e:
                st.error(f"Erro ao ler o CSV: {e}")
                st.code(traceback.format_exc())

        # Preview dos dados em sessão
        if not st.session_state.df_lancamentos.empty:
            st.divider()
            st.subheader("📋 Dados Atuais em Memória (Session State)")
            st.dataframe(st.session_state.df_lancamentos, use_container_width=True)
            csv_mem = st.session_state.df_lancamentos.to_csv(index=False).encode("utf-8")
            st.download_button(
                "⬇️ Baixar CSV atual",
                data=csv_mem,
                file_name="lancamentos_atuais.csv",
                mime="text/csv",
            )

    with col_b:
        st.subheader("Template de Demonstração")
        st.markdown(
            "Sem arquivo pronto? Carregue dados de **homologação** com 4 períodos "
            "(Capex inicial + receitas crescentes, alternando Realizado/Projetado)."
        )

        if st.button(
            "📄 Carregar Template de Demonstração/Homologação",
            type="primary",
            use_container_width=True,
        ):
            df_demo = gerar_template_demo()
            st.session_state.df_lancamentos = df_demo.copy()
            st.session_state.calculo_executado = False
            st.success("✅ Template carregado na sessão com 4 períodos!")
            st.rerun()

        # Exibe preview do template (sempre visível como referência)
        with st.expander("👁️ Visualizar estrutura do template", expanded=False):
            st.dataframe(gerar_template_demo(), use_container_width=True)
            st.caption(
                "**Período 1:** Capex R$ 500.000 + Despesas R$ 15.000 (investimento inicial, Realizado) | "
                "**Período 2:** Receita R$ 320.000, Capex adicional R$ 50.000 (Realizado) | "
                "**Períodos 3-4:** Receitas crescentes R$ 450k → R$ 580k (Projetado)"
            )

        st.divider()
        st.info(
            "**Guia de Colunas:**\n"
            "- `Periodo` (INT): Período sequencial (1, 2, 3...)\n"
            "- `Tipo_Dado` (VARCHAR): 'Realizado' ou 'Projetado'\n"
            "- `Capex_1_00`: Investimento em ativo (saída)\n"
            "- `Receita_Bruta_2_00`: Receita total\n"
            "- `Deducoes_2_03`: Impostos/devoluções\n"
            "- `Custos_Variaveis_3_00`: Custos proporcionais à venda\n"
            "- `Despesas_Fixas_4_00`: Custos fixos operacionais"
        )

# ---------------------------------------------------------------------------
# ABA 2: CONFERÊNCIA E EDIÇÃO (CAMADA DE CORREÇÕES)
# ---------------------------------------------------------------------------
with tab2:
    st.header("📝 Conferência e Edição — Camada de Correções")
    st.markdown(
        "Revise, edite, adicione ou remova lançamentos antes da homologação. "
        "As alterações são mantidas em **Session State** até confirmação."
    )

    if st.session_state.df_lancamentos.empty:
        st.warning("⚠️ Nenhum dado carregado. Vá para a **Aba 1** e faça upload ou carregue o template.")
    else:
        st.subheader("Tabela Interativa (st.data_editor)")

        # Configuração de colunas para o data_editor
        column_config = {
            "Periodo": st.column_config.NumberColumn(
                "Período", min_value=1, step=1, required=True, help="Período sequencial (inteiro > 0)"
            ),
            "Tipo_Dado": st.column_config.SelectboxColumn(
                "Tipo de Dado", options=["Realizado", "Projetado"], required=True
            ),
            "Capex_1_00": st.column_config.NumberColumn(
                "Capex 1.00 (R$)", format="%.2f", required=True, help="Investimento inicial"
            ),
            "Receita_Bruta_2_00": st.column_config.NumberColumn(
                "Receita Bruta 2.00 (R$)", format="%.2f", required=True
            ),
            "Deducoes_2_03": st.column_config.NumberColumn(
                "Deduções 2.03 (R$)", format="%.2f", required=True
            ),
            "Custos_Variaveis_3_00": st.column_config.NumberColumn(
                "Custos Variáveis 3.00 (R$)", format="%.2f", required=True
            ),
            "Despesas_Fixas_4_00": st.column_config.NumberColumn(
                "Despesas Fixas 4.00 (R$)", format="%.2f", required=True
            ),
        }

        # st.data_editor com edição em tempo real
        df_editado = st.data_editor(
            st.session_state.df_lancamentos,
            num_rows="dynamic",  # Permite adicionar/excluir linhas
            column_config=column_config,
            use_container_width=True,
            key="editor_lancamentos",
            hide_index=False,
        )

        st.caption("💡 Dicas: Clique em uma célula para editar | Use o botão '+' para adicionar linha | Selecione linha e pressione Delete para excluir.")

        col_btn1, col_btn2, col_btn3 = st.columns([2, 1, 1])

        with col_btn1:
            if st.button(
                "✅ Homologar Alterações de Dados",
                type="primary",
                use_container_width=True,
            ):
                # Validação antes de salvar na sessão global
                valido, msg = validar_dataframe(df_editado)
                if not valido:
                    st.error(f"❌ Validação falhou: {msg}")
                    st.warning("Corrija os dados destacados antes de homologar.")
                else:
                    # Normaliza tipos
                    for col in COLUNAS_NUMERICAS:
                        df_editado[col] = pd.to_numeric(df_editado[col], errors="coerce")
                    df_editado["Periodo"] = pd.to_numeric(df_editado["Periodo"], errors="coerce").astype(int)
                    st.session_state.df_lancamentos = df_editado.copy().reset_index(drop=True)
                    st.session_state.calculo_executado = False
                    st.success(f"✅ Alterações homologadas! {len(df_editado)} registros salvos na sessão global.")
                    st.balloons()

        with col_btn2:
            if st.button("↩️ Descartar Edições", use_container_width=True):
                st.rerun()

        with col_btn3:
            if st.button("🗑️ Limpar Todos os Dados", use_container_width=True):
                st.session_state.df_lancamentos = pd.DataFrame(columns=COLUNAS_PLANO_CONTAS)
                st.session_state.calculo_executado = False
                st.warning("Dados limpos da sessão.")
                st.rerun()

        # Resumo rápido
        if not df_editado.empty:
            st.divider()
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Total Períodos", len(df_editado))
            c2.metric("Capex Total", formatar_moeda(df_editado["Capex_1_00"].sum()))
            c3.metric("Receita Bruta Total", formatar_moeda(df_editado["Receita_Bruta_2_00"].sum()))
            c4.metric("Realizado / Projetado", f"{(df_editado['Tipo_Dado']=='Realizado').sum()} / {(df_editado['Tipo_Dado']=='Projetado').sum()}")

# ---------------------------------------------------------------------------
# ABA 3: PARÂMETROS DO SISTEMA (GATILHO DE EXECUÇÃO)
# ---------------------------------------------------------------------------
with tab3:
    st.header("⚙️ Parâmetros do Sistema — Gatilho de Execução")
    st.markdown(
        "Defina os parâmetros corporativos do projeto e execute o **motor de cálculo** com commit transacional no SQL Server."
    )

    if st.session_state.df_lancamentos.empty:
        st.warning("⚠️ Carregue e homologue os dados nas Abas 1 e 2 antes de configurar os parâmetros.")
    else:
        st.info(f"📦 {len(st.session_state.df_lancamentos)} lançamento(s) prontos para processamento.")

        with st.form("form_parametros"):
            st.subheader("Configuração do Projeto")

            col_p1, col_p2 = st.columns(2)

            with col_p1:
                nome_projeto = st.text_input(
                    "Nome do Projeto *",
                    placeholder="Ex: Expansão Varejo Sudeste 2026",
                    help="Nome único do projeto (constraint UNIQUE no banco)",
                )
                canal = st.selectbox(
                    "Canal de Venda *",
                    options=["Varejo", "Atacado"],
                    help="Define regras de alerta setorial (Giro do Ativo, TIR)",
                )

            with col_p2:
                escala = st.selectbox(
                    "Escala do Tempo *",
                    options=["Mensal", "Anual"],
                    help="Mensal: TMA ao mês | Anual: TMA ao ano",
                )
                tma = st.number_input(
                    "Taxa Mínima de Atratividade (TMA %) *",
                    min_value=0.0,
                    max_value=100.0,
                    value=12.0,
                    step=0.5,
                    format="%.2f",
                    help="Taxa de desconto para VPL e Payback Descontado. Ex: 12% a.a.",
                )

            st.divider()

            # Preview dos dados que serão commitados
            with st.expander("👁️ Prévia dos lançamentos a serem persistidos", expanded=False):
                st.dataframe(st.session_state.df_lancamentos, use_container_width=True)

            # Botão central de execução
            submitted = st.form_submit_button(
                "🚀 Executar Sistema de Cálculo e Commitar no Banco",
                type="primary",
                use_container_width=True,
            )

            if submitted:
                # Validações de formulário
                if not nome_projeto or not nome_projeto.strip():
                    st.error("❌ O campo 'Nome do Projeto' é obrigatório.")
                    st.stop()
                if tma is None or tma < 0:
                    st.error("❌ TMA inválida.")
                    st.stop()

                # Valida dados novamente
                valido, msg = validar_dataframe(st.session_state.df_lancamentos)
                if not valido:
                    st.error(f"❌ Dados inválidos: {msg}. Retorne à Aba 2.")
                    st.stop()

                # Barra de progresso simulada
                progress = st.progress(0, text="Iniciando...")
                try:
                    progress.progress(15, text="Validando conexão com SQL Server...")
                    time.sleep(0.5)

                    progress.progress(35, text="Persistindo projeto no banco (transação)...")
                    # Tenta persistir no banco
                    try:
                        id_projeto = inserir_projeto_e_lancamentos(
                            nome=nome_projeto.strip(),
                            canal=canal,
                            escala=escala,
                            tma=float(tma),
                            df=st.session_state.df_lancamentos,
                        )
                        st.session_state.ultimo_projeto_id = id_projeto
                        st.session_state.ultimo_projeto_nome = nome_projeto.strip()
                        db_sucesso = True
                        db_msg = f"Projeto ID {id_projeto} persistido com {len(st.session_state.df_lancamentos)} lançamentos."
                    except ValueError as ve:
                        # Erro de .env / configuração -> permite cálculo sem persistência
                        db_sucesso = False
                        db_msg = f"⚠️ Cálculo executado SEM persistência (modo offline): {ve}"
                        st.session_state.ultimo_projeto_id = None
                        st.session_state.ultimo_projeto_nome = nome_projeto.strip() + " (offline)"
                    except Exception as db_e:
                        db_sucesso = False
                        # Se for erro de UNIQUE (nome duplicado), informa claramente
                        err_str = str(db_e)
                        if "UNIQUE" in err_str.upper() or "UQ_TB_PROJETOS_NOME" in err_str:
                            st.error(f"❌ Já existe um projeto com o nome '{nome_projeto}'. Escolha outro nome.")
                            progress.empty()
                            st.stop()
                        db_msg = f"⚠️ Falha ao persistir no banco (cálculo continuará offline): {db_e}"
                        st.session_state.ultimo_projeto_id = None
                        st.session_state.ultimo_projeto_nome = nome_projeto.strip() + " (offline)"

                    progress.progress(65, text="Executando motor de cálculo financeiro...")
                    time.sleep(0.3)

                    # Motor de cálculo (sempre executa, mesmo offline)
                    df_resultado, kpis = calcular_metricas(
                        st.session_state.df_lancamentos, float(tma), canal
                    )
                    # Guarda no session_state para Aba 4
                    st.session_state.df_resultado = df_resultado
                    st.session_state.kpis = kpis
                    st.session_state.kpis["TMA"] = float(tma)
                    st.session_state.kpis["Canal"] = canal
                    st.session_state.kpis["Escala"] = escala
                    st.session_state.kpis["Nome_Projeto"] = nome_projeto.strip()
                    st.session_state.calculo_executado = True

                    progress.progress(100, text="Concluído!")

                    # Feedback
                    if db_sucesso:
                        st.success(f"✅ {db_msg}")
                    else:
                        st.warning(db_msg)
                        with st.expander("Detalhes do erro de banco", expanded=False):
                            st.code(err_str if 'err_str' in locals() else db_msg)

                    st.success(
                        f"📊 Cálculo finalizado! VPL: {formatar_moeda(kpis['VPL'])} | "
                        f"TIR: {kpis['TIR']:.2f}% | Payback: {kpis['Payback']:.2f} períodos" if kpis["TIR"] is not None and kpis["Payback"] is not None
                        else f"📊 Cálculo finalizado! VPL: {formatar_moeda(kpis['VPL'])}"
                    )
                    st.info("👉 Vá para a **Aba 4: Demonstrativo & Resultados** para visualizar o relatório completo.")
                    st.balloons()

                except Exception as e:
                    progress.empty()
                    st.error(f"❌ Erro inesperado durante a execução: {e}")
                    st.code(traceback.format_exc())
                finally:
                    time.sleep(0.5)
                    try:
                        progress.empty()
                    except Exception:
                        pass

        # Status pós-execução
        if st.session_state.calculo_executado:
            st.divider()
            st.success(
                f"✅ Última execução: Projeto **'{st.session_state.kpis.get('Nome_Projeto','')}'** | "
                f"Canal: {st.session_state.kpis.get('Canal','')} | "
                f"VPL: {formatar_moeda(st.session_state.kpis.get('VPL',0))}"
            )

# ---------------------------------------------------------------------------
# ABA 4: DEMONSTRATIVO & RESULTADOS (OUTPUT FINAL E GOVERNANÇA TI)
# ---------------------------------------------------------------------------
with tab4:
    st.header("📈 Demonstrativo & Resultados — Output Final")

    if not st.session_state.calculo_executado or st.session_state.df_resultado.empty:
        st.warning(
            "⚠️ Nenhum cálculo executado. Configure os parâmetros na **Aba 3** e clique em "
            "**'Executar Sistema de Cálculo e Commitar no Banco'**."
        )
        st.info("💡 Dica: Use o Template de Demonstração na Aba 1 para testar rapidamente.")
        st.stop()

    # Recupera dados do cálculo
    df_res = st.session_state.df_resultado
    kpis = st.session_state.kpis
    tma_val = kpis.get("TMA", 12.0)
    canal_val = kpis.get("Canal", "Varejo")
    nome_proj = kpis.get("Nome_Projeto", "Projeto")

    st.caption(f"Projeto: **{nome_proj}** | Canal: **{canal_val}** | Escala: **{kpis.get('Escala','')}** | TMA: **{tma_val:.2f}%**")

    # =========================================================
    # 1. CARDS DE KPIs NO TOPO
    # =========================================================
    st.subheader("🎯 Indicadores Chave (KPIs)")

    col_kpi1, col_kpi2, col_kpi3, col_kpi4 = st.columns(4)

    with col_kpi1:
        vpl_val = kpis["VPL"]
        delta_vpl = "Viável ✅" if vpl_val > 0 else "Inviável ❌"
        st.metric(
            label="VPL — Valor Presente Líquido",
            value=formatar_moeda(vpl_val),
            delta=delta_vpl,
            delta_color="normal" if vpl_val > 0 else "inverse",
            help=f"VPL descontado à TMA de {tma_val:.2f}%. VPL > 0 indica viabilidade.",
        )

    with col_kpi2:
        tir_val = kpis["TIR"]
        if tir_val is None:
            st.metric(label="TIR — Taxa Interna de Retorno", value="N/D", delta="Fluxo sem inversão", help="TIR não calculável (fluxos sem variação de sinal)")
        else:
            delta_tir = "Acima da TMA ✅" if tir_val > tma_val else "Abaixo da TMA ❌"
            st.metric(
                label="TIR — Taxa Interna de Retorno",
                value=f"{tir_val:.2f} %",
                delta=delta_tir,
                delta_color="normal" if tir_val > tma_val else "inverse",
                help="TIR calculada via numpy_financial.irr sobre Fluxo de Caixa Líquido.",
            )

    with col_kpi3:
        payback_val = kpis["Payback"]
        if payback_val is None:
            st.metric(label="Payback Descontado", value="Não recuperado", delta="> horizonte", delta_color="inverse")
        else:
            st.metric(
                label="Payback Descontado (períodos)",
                value=f"{payback_val:.2f}",
                delta=f"Período {payback_val:.1f}",
                help="Período exato (com interpolação) em que o Fluxo Descontado Acumulado fica positivo.",
            )

    with col_kpi4:
        roic_val = kpis["ROIC"]
        st.metric(
            label="ROIC Operacional (último período)",
            value=f"{roic_val:.2f} %",
            delta=f"Capex: {formatar_moeda(kpis['Capex_Total'])}",
            help="ROIC = Lucro Operacional (Margem - Despesas Fixas) do último período / Capex Total.",
        )

    # =========================================================
    # 2. DRE DO INVESTIMENTO ESTRUTURADA (TABELA HORIZONTAL)
    # =========================================================
    st.divider()
    st.subheader("📋 DRE do Investimento — Fluxo Temporal Completo")

    # Monta tabela horizontal: linhas = contas, colunas = períodos
    # Inclui linhas originais + calculadas
    contas_ordem = [
        ("Capex_1_00", "(-) Capex 1.00 (Investimento)"),
        ("Receita_Bruta_2_00", "(+) Receita Bruta 2.00"),
        ("Deducoes_2_03", "(-) Deduções 2.03"),
        ("Receita_Liquida", "(=) Receita Líquida"),
        ("Custos_Variaveis_3_00", "(-) Custos Variáveis 3.00"),
        ("Margem_Contribuicao", "(=) Margem de Contribuição"),
        ("Despesas_Fixas_4_00", "(-) Despesas Fixas 4.00"),
        ("Fluxo_Caixa_Liquido", "(=) Fluxo de Caixa Líquido"),
        ("Fluxo_Descontado", "(=) Fluxo Descontado (TMA)"),
        ("Fluxo_Descontado_Acumulado", "(=) Fluxo Descontado Acumulado"),
    ]

    # Cria DataFrame pivoteado: índice = conta, colunas = Período X
    dre_data = {}
    for col_key, label in contas_ordem:
        valores = []
        for _, row in df_res.iterrows():
            valores.append(float(row[col_key]))
        dre_data[label] = valores

    periodos_labels = [f"Período {int(p)} ({t})" for p, t in zip(df_res["Periodo"], df_res["Tipo_Dado"])]
    df_dre = pd.DataFrame.from_dict(dre_data, orient="index", columns=periodos_labels)

    # Adiciona coluna TOTAL
    df_dre["TOTAL"] = df_res[[c for c, _ in contas_ordem]] .sum() if False else 0  # placeholder
    # Calcula total correto por linha
    for label in df_dre.index:
        col_key = [k for k, v in contas_ordem if v == label][0]
        df_dre.loc[label, "TOTAL"] = float(df_res[col_key].sum())

    # Formatação moeda para exibição
    df_dre_formatado = df_dre.copy()
    for col in df_dre_formatado.columns:
        df_dre_formatado[col] = df_dre_formatado[col].apply(formatar_moeda)

    st.dataframe(df_dre_formatado, use_container_width=True, height=420)

    # Gráfico de fluxo acumulado
    st.subheader("📊 Evolução do Fluxo Descontado Acumulado")
    chart_df = pd.DataFrame(
        {
            "Período": df_res["Periodo"].astype(str),
            "Fluxo Descontado Acumulado": df_res["Fluxo_Descontado_Acumulado"],
            "Fluxo Caixa Líquido": df_res["Fluxo_Caixa_Liquido"],
        }
    ).set_index("Período")
    st.bar_chart(chart_df, use_container_width=True)

    # Botão de download da DRE
    csv_dre = df_dre.to_csv(encoding="utf-8-sig")
    st.download_button(
        "⬇️ Baixar DRE Completa (CSV)",
        data=csv_dre.encode("utf-8-sig"),
        file_name=f"DRE_{nome_proj.replace(' ', '_')}.csv",
        mime="text/csv",
    )

    # =========================================================
    # 3. ALERTAS DE RISCO OPERACIONAL
    # =========================================================
    st.divider()
    st.subheader("⚠️ Alertas de Risco Operacional")

    alertas = 0

    # Regra 1: Giro do Ativo < 1.2 no Varejo
    giro = kpis.get("Giro_Ativo", 0)
    if canal_val == "Varejo" and giro < 1.2:
        st.warning(
            f"⚠️ **Giro do Ativo abaixo do threshold setorial (Varejo):** "
            f"Giro atual **{giro:.2f}** < 1.2. Indica baixa eficiência na geração de receita sobre o ativo investido. "
            f"Receita Líquida Total: {formatar_moeda(kpis['Receita_Liquida_Total'])} | Capex Total: {formatar_moeda(kpis['Capex_Total'])}"
        )
        alertas += 1
    elif canal_val == "Varejo":
        st.success(f"✅ Giro do Ativo dentro do padrão setorial (Varejo): {giro:.2f} ≥ 1.2")

    # Regra 2: TIR < 5% em projetos de Atacado
    tir_val = kpis.get("TIR")
    if canal_val == "Atacado" and tir_val is not None and tir_val < 5.0:
        st.error(
            f"🚨 **TIR crítica em projeto de Atacado:** TIR **{tir_val:.2f}%** < 5%. "
            f"Rentabilidade abaixo do piso setorial para Atacado. Recomenda-se revisão de premissas de receita/custo ou TMA ({tma_val:.2f}%)."
        )
        alertas += 1
    elif canal_val == "Atacado" and tir_val is not None:
        st.success(f"✅ TIR dentro do padrão setorial (Atacado): {tir_val:.2f}% ≥ 5%")

    # Regra 3: VPL negativo
    if kpis["VPL"] < 0:
        st.error(
            f"🚨 **VPL Negativo:** {formatar_moeda(kpis['VPL'])} à TMA de {tma_val:.2f}%. "
            f"O projeto destrói valor. Avaliar redução de Capex, aumento de margem ou postergação."
        )
        alertas += 1
    else:
        st.success(f"✅ VPL positivo: {formatar_moeda(kpis['VPL'])} — projeto cria valor à TMA de {tma_val:.2f}%.")

    # Regra 4: Payback não recuperado
    if kpis["Payback"] is None:
        st.warning(
            "⚠️ **Payback não recuperado** no horizonte analisado: Fluxo Descontado Acumulado permanece negativo até o último período. "
            "Considere estender o horizonte ou revisar premissas."
        )
        alertas += 1

    # Regra 5: ROIC negativo no último período
    if kpis["ROIC"] < 0:
        st.warning(f"⚠️ **ROIC negativo no último período:** {kpis['ROIC']:.2f}%. Último período ainda opera com prejuízo.")

    if alertas == 0:
        st.success("✅ Nenhuma violação setorial detectada. Todos os parâmetros dentro dos thresholds corporativos.")

    # =========================================================
    # 4. ÁREA DE GOVERNANÇA DE TI / DEVOPS (EXCLUSIVO TÉCNICA)
    # =========================================================
    st.divider()

    # Container estilizado com borda e aviso
    st.markdown(
        """
        <div style="
            border: 2px solid #FF4B4B;
            border-radius: 10px;
            padding: 16px;
            background-color: #FFF0F0;
            margin-bottom: 12px;
        ">
            <h4 style="color:#FF4B4B; margin:0;">⚠️ ACESSO EXCLUSIVO: ÁREA TÉCNICA / INFRAESTRUTURA</h4>
            <p style="margin:4px 0 0 0; color:#333; font-size: 0.9em;">
                Esta seção é restrita à equipe de Engenharia, DevOps e TI. Ações aqui afetam diagnóstico de contêiner,
                conectividade ODBC e validação de variáveis de ambiente. Uso auditado.
            </p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    with st.expander("🔧 Governança de TI / DevOps — Ferramentas de Infraestrutura", expanded=False):
        st.markdown("**Ações rápidas de diagnóstico e infraestrutura** (execução sob demanda, sem expor credenciais):")

        col_ti1, col_ti2, col_ti3 = st.columns(3)

        with col_ti1:
            if st.button("🔍 Verificar Status Conexão ODBC", use_container_width=True, key="btn_odbc"):
                with st.spinner("Testando conexão ODBC..."):
                    sucesso, diagnostico = testar_conexao_odbc()
                    if sucesso:
                        st.success(diagnostico)
                    else:
                        st.error(diagnostico)

        with col_ti2:
            if st.button("📋 Revalidar Variáveis .env", use_container_width=True, key="btn_env"):
                st.subheader("Variáveis de Ambiente (.env)")
                env_vars = {
                    "DB_SERVER": os.environ.get("DB_SERVER", "❌ NÃO DEFINIDO"),
                    "DB_DATABASE": os.environ.get("DB_DATABASE", "❌ NÃO DEFINIDO"),
                    "DB_UID": os.environ.get("DB_UID", "❌ NÃO DEFINIDO"),
                    "DB_PWD": "***" if os.environ.get("DB_PWD") else "❌ NÃO DEFINIDO",
                    "DB_PORT": os.environ.get("DB_PORT", "1433 (default)"),
                    "DB_DRIVER": os.environ.get("DB_DRIVER", "ODBC Driver 17 for SQL Server (default)"),
                    "DB_TIMEOUT": os.environ.get("DB_TIMEOUT", "30 (default)"),
                    "DB_ENCRYPT": os.environ.get("DB_ENCRYPT", "yes (default)"),
                    "DB_TRUST_CERT": os.environ.get("DB_TRUST_CERT", "yes (default)"),
                }
                # Exibe sem expor senha
                for k, v in env_vars.items():
                    if "NÃO DEFINIDO" in str(v):
                        st.error(f"**{k}**: {v}")
                    else:
                        st.success(f"**{k}**: {v}")

                # Lista drivers ODBC
                try:
                    drivers = pyodbc.drivers()
                    st.info(f"**Drivers ODBC instalados no contêiner:** {drivers if drivers else 'Nenhum driver encontrado!'}")
                except Exception as e:
                    st.error(f"Erro ao listar drivers: {e}")

                st.caption("ℹ️ Para alterar, edite o arquivo `.env` na raiz e reinicie: `docker compose up --build -d`")

        with col_ti3:
            if st.button("📜 Logs de Depuração do Contêiner", use_container_width=True, key="btn_logs"):
                st.subheader("Diagnóstico do Contêiner")
                import platform
                import sys

                info = {
                    "Python": platform.python_version(),
                    "Platform": platform.platform(),
                    "Streamlit": st.__version__,
                    "Pandas": pd.__version__,
                    "NumPy": np.__version__,
                    "pyodbc": pyodbc.version,
                    "Timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "CWD": os.getcwd(),
                    "Projeto em sessão": nome_proj,
                    "ID Projeto (DB)": str(st.session_state.ultimo_projeto_id),
                    "Registros em memória": str(len(st.session_state.df_lancamentos)),
                }
                st.json(info)

                # Logs simulados
                st.text_area(
                    "Logs (stdout simulado)",
                    value=(
                        f"[{datetime.now()}] INFO: Container rentabilidade-app rodando em 0.0.0.0:8501\n"
                        f"[{datetime.now()}] INFO: Healthcheck: /_stcore/health -> 200 OK\n"
                        f"[{datetime.now()}] INFO: Session State: {len(st.session_state.df_lancamentos)} registros | Calculo={st.session_state.calculo_executado}\n"
                        f"[{datetime.now()}] INFO: Para logs reais, execute: docker logs rentabilidade-app --tail 100 -f"
                    ),
                    height=140,
                )
                st.caption("💡 Em produção, acesse logs completos via `docker logs rentabilidade-app` ou `docker compose logs -f app`")

        st.divider()
        st.markdown("**Links Rápidos (documentação):**")
        st.markdown(
            "- [Microsoft ODBC Driver for SQL Server - Linux](https://learn.microsoft.com/en-us/sql/connect/odbc/linux-mac/installing-the-microsoft-odbc-driver-for-sql-server)\n"
            "- [Streamlit Docs](https://docs.streamlit.io/)\n"
            "- [pyodbc Wiki](https://github.com/mkleehammer/pyodbc/wiki)"
        )
        st.warning("🔒 Todas as ações desta área são logadas para auditoria. Acesso restrito a perfis DevOps/Infra.")

# =============================================================================
# RODAPÉ
# =============================================================================
st.divider()
st.caption("Sistema de Apuração de Rentabilidade Física — Varejo & Atacado | Python 3.11 • Streamlit • SQL Server • Docker | Governança Corporativa em 4 Camadas")
