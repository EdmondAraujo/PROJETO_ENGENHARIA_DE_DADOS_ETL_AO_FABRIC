# 📊 Sistema de Apuração de Rentabilidade Física — Varejo e Atacado

> **Aplicação corporativa web para análise de viabilidade e rentabilidade de projetos físicos nos canais de Varejo e Atacado, com governança em 4 camadas, cálculo financeiro completo (VPL, TIR, Payback Descontado, ROIC) e persistência transacional em Microsoft SQL Server.**

![Python](https://img.shields.io/badge/Python-3.11%2B-blue?logo=python)
![Streamlit](https://img.shields.io/badge/Streamlit-1.39-red?logo=streamlit)
![SQL Server](https://img.shields.io/badge/SQL%20Server-2019%2B-CC2927?logo=microsoftsqlserver)
![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?logo=docker)

---

## 📑 Índice

1. [Descrição Geral](#-descrição-geral)
2. [Requisitos de Sistema](#-requisitos-de-sistema)
3. [Instalação e Inicialização com Docker](#-instalação-e-inicialização-com-docker)
4. [Guia de Layout do CSV](#-guia-de-layout-do-csv)
5. [Estrutura de Pastas Sugerida](#-estrutura-de-pastas-sugerida)
6. [Arquitetura e Fluxo de Governança](#-arquitetura-e-fluxo-de-governança)
7. [Motor de Cálculo Financeiro](#-motor-de-cálculo-financeiro)
8. [Troubleshooting](#-troubleshooting)

---

## 📖 Descrição Geral

### Propósito do Sistema

O sistema apoia a **tomada de decisão de investimentos físicos** (lojas, centros de distribuição, expansões) nos canais **Varejo** e **Atacado**, respeitando a separação de funções corporativa. Ele centraliza:

- **Carga padronizada** do plano de contas via CSV ou template de homologação.
- **Conferência e edição auditável** com validações de integridade.
- **Parametrização governada** (nome do projeto, canal, escala temporal, TMA).
- **Cálculo financeiro completo** e **persistência transacional** no SQL Server.
- **Demonstrativo executivo** com KPIs, DRE horizontal e alertas setoriais de risco.
- **Área exclusiva de TI/DevOps** para diagnóstico de infraestrutura sem exposição de credenciais.

### Stack Tecnológica

| Camada | Tecnologia | Versão / Detalhe |
|---|---|---|
| **Frontend** | Streamlit | 1.39+ |
| **Linguagem** | Python | 3.11+ |
| **Backend / BD** | Microsoft SQL Server | 2019+ |
| **Conectividade** | pyodbc + Microsoft ODBC Driver 17 | unixodbc no Linux |
| **Cálculo Financeiro** | numpy-financial (TIR), numpy, pandas | VPL, Payback Descontado, ROIC |
| **Segurança** | python-dotenv + os.environ | Credenciais via `.env`, nunca no código |
| **Conteinerização** | Docker + Docker Compose | Imagem `python:3.11-slim` |

### Governança em 4 Camadas (Abas)

| Aba | Função | Perfil Corporativo |
|---|---|---|
| **1. Carga de Informações** | Upload de CSV + Template de Demonstração (4 períodos) | Operacional / Controladoria |
| **2. Conferência e Edição** | `st.data_editor` com validação e homologação em Session State | Controladoria / Auditoria |
| **3. Parâmetros do Sistema** | Definição de Nome, Canal, Escala, TMA + Gatilho transacional | Gerência / Diretoria |
| **4. Demonstrativo & Resultados** | KPIs, DRE horizontal, Alertas de Risco, Área TI/DevOps | Diretoria / TI / Infra |

---

## 💻 Requisitos de Sistema

### Dependências Python (`requirements.txt`)

```
streamlit==1.39.0
pandas==2.2.3
numpy==1.26.4
numpy-financial==1.0.0
pyodbc==5.1.0
python-dotenv==1.0.1
openpyxl==3.1.5
```

Instalação local (sem Docker):

```bash
pip install -r requirements.txt
```

### Bibliotecas de Sistema (Docker)

Instaladas automaticamente no `Dockerfile`:

- `unixodbc`, `unixodbc-dev`, `gcc`, `g++`, `curl`, `gnupg2`
- **Microsoft ODBC Driver 17 for SQL Server** (`msodbcsql17`) via repositório oficial Microsoft para Debian 12 (bookworm)

### Requisitos de Infraestrutura

- **Docker Engine** 24+ e **Docker Compose** v2+ (ou `docker-compose` standalone)
- **Microsoft SQL Server** 2019+ acessível (instância corporativa ou local via container — ver `docker-compose.yml` comentado)
- Porta **8501** livre para o Streamlit (mapeada no `docker-compose.yml`)
- Porta **1433** para SQL Server (se usar container local de BD)

---

## 🚀 Instalação e Inicialização com Docker

### Passo 1 — Clonar o Repositório

```bash
git clone https://github.com/seu-usuario/rentabilidade-varejo-atacado.git
cd rentabilidade-varejo-atacado
```

### Passo 2 — Configurar o Arquivo `.env`

Copie o modelo e preencha com suas credenciais **reais** (nunca commite o `.env`):

**Windows (PowerShell):**
```powershell
Copy-Item .env.example .env
notepad .env
```

**Linux / macOS:**
```bash
cp .env.example .env
nano .env
```

Conteúdo esperado no `.env`:

```env
DB_SERVER=localhost
DB_DATABASE=DB_RENTABILIDADE
DB_UID=sa
DB_PWD=SuaSenhaForte@123
DB_PORT=1433
DB_DRIVER=ODBC Driver 17 for SQL Server
DB_TIMEOUT=30
DB_ENCRYPT=yes
DB_TRUST_CERT=yes
```

> **Segurança:** O `docker-compose.yml` injeta essas variáveis via `env_file: .env` em tempo de execução. Nenhuma senha fica exposta no `app.py` — a função `init_connection()` (`app.py:85`) lê exclusivamente de `os.environ`.

### Passo 3 — Criar o Banco e Rodar o Script SQL

#### Opção A — SQL Server Corporativo (recomendado em produção)

1. Conecte-se à instância via **SQL Server Management Studio (SSMS)** ou **Azure Data Studio**.
2. Crie o banco (se não existir):

   ```sql
   CREATE DATABASE DB_RENTABILIDADE;
   GO
   ```

3. Abra o arquivo `schema.sql` e execute-o no contexto do banco criado (botão **Execute** ou `F5`).

   O script cria:
   - `TB_PROJETOS` (com checks para `Varejo/Atacado`, `Mensal/Anual`, TMA 0–100)
   - `TB_LANCAMENTOS_FINANCEIROS` (FK com `ON DELETE CASCADE`, `UNIQUE` por projeto/período/tipo)
   - Índices otimizados (`IX_TB_LANCAMENTOS_ID_PROJETO`, `IX_TB_LANCAMENTOS_PERIODO`, `IX_TB_LANCAMENTOS_PROJETO_PERIODO`, etc.)

   Verificação:

   ```sql
   SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA = 'dbo';
   SELECT * FROM dbo.TB_PROJETOS;
   ```

#### Opção B — SQL Server Local via Docker (desenvolvimento)

Descomente o serviço `db` no `docker-compose.yml` e ajuste o `DB_SERVER` no `.env` para `db`:

```env
DB_SERVER=db
```

O compose subirá automaticamente o SQL Server 2022 e montará o `schema.sql` como init script.

### Passo 4 — Construir e Iniciar os Contêineres

Na raiz do projeto (onde estão `Dockerfile` e `docker-compose.yml`):

```bash
# Construir a imagem e subir em foreground (logs visíveis)
docker compose up --build

# OU em background (detached)
docker compose up --build -d

# Ver logs
docker compose logs -f app
# ou
docker logs rentabilidade-app --tail 100 -f

# Verificar saúde do container
docker ps
docker inspect rentabilidade-app --format='{{json .State.Health}}'
```

> **Comando exato** para build + start conforme solicitado: **`docker compose up --build`**

A aplicação ficará disponível em: **http://localhost:8501**

### Passo 5 — Validar a Instalação

1. Acesse `http://localhost:8501`.
2. Na **Aba 1**, clique em **"Carregar Template de Demonstração"** e verifique os 4 períodos.
3. Na **Aba 4** (após executar na Aba 3), use a **Área Técnica / DevOps** para:
   - **Verificar Status Conexão ODBC** — testa `SELECT 1` e lista drivers/tabelas.
   - **Revalidar Variáveis .env** — confere injeção sem expor senha.
   - **Logs de Depuração** — exibe versões e diagnóstico do contêiner.

Parar os contêineres:

```bash
docker compose down        # para e remove containers/rede
docker compose down -v     # também remove volumes (se usar db local)
```

---

## 📂 Guia de Layout do CSV

O CSV de entrada deve conter **exatamente** as colunas abaixo (nomes case-sensitive, sem acentos). O separador é autodetectado (`sep=None, engine="python"`), aceitando vírgula `,` ou ponto-e-vírgula `;`.

| Coluna | Tipo SQL | Tipo CSV | Descrição Corporativa | Exemplo | Obrigatório |
|---|---|---|---|---|---|
| `Periodo` | `INT` | Inteiro > 0 | Período sequencial do fluxo (mês ou ano conforme escala) | `1`, `2`, `3` | Sim |
| `Tipo_Dado` | `VARCHAR(20)` | `Realizado` ou `Projetado` | Natureza do dado: histórico confirmado vs projeção | `Realizado` | Sim |
| `Capex_1_00` | `DECIMAL(18,2)` | Numérico (R$) | **1.00 Capex** — Investimento em ativo imobilizado (saída de caixa) | `500000.00` | Sim |
| `Receita_Bruta_2_00` | `DECIMAL(18,2)` | Numérico (R$) | **2.00 Receita Bruta** — Faturamento total sem deduções | `320000.00` | Sim |
| `Deducoes_2_03` | `DECIMAL(18,2)` | Numérico (R$) | **2.03 Deduções** — Impostos sobre venda, devoluções, descontos | `38400.00` | Sim |
| `Custos_Variaveis_3_00` | `DECIMAL(18,2)` | Numérico (R$) | **3.00 Custos Variáveis** — Custos proporcionais à receita (CMV, comissões) | `128000.00` | Sim |
| `Despesas_Fixas_4_00` | `DECIMAL(18,2)` | Numérico (R$) | **4.00 Despesas Fixas** — Custos fixos operacionais (aluguel, folha fixa) | `45000.00` | Sim |

### Exemplo de CSV Válido

```csv
Periodo,Tipo_Dado,Capex_1_00,Receita_Bruta_2_00,Deducoes_2_03,Custos_Variaveis_3_00,Despesas_Fixas_4_00
1,Realizado,500000.00,0.00,0.00,0.00,15000.00
2,Realizado,50000.00,320000.00,38400.00,128000.00,45000.00
3,Projetado,0.00,450000.00,54000.00,180000.00,48000.00
4,Projetado,0.00,580000.00,69600.00,232000.00,52000.00
```

### Template de Demonstração (em memória)

Gerado pela função `gerar_template_demo()` (`app.py:380`):

| Período | Tipo | Capex | Receita Bruta | Deduções | Custos Variáveis | Despesas Fixas | Observação |
|---|---|---|---|---|---|---|---|
| 1 | Realizado | R$ 500.000,00 | R$ 0,00 | R$ 0,00 | R$ 0,00 | R$ 15.000,00 | Investimento inicial |
| 2 | Realizado | R$ 50.000,00 | R$ 320.000,00 | R$ 38.400,00 | R$ 128.000,00 | R$ 45.000,00 | Início da operação |
| 3 | Projetado | R$ 0,00 | R$ 450.000,00 | R$ 54.000,00 | R$ 180.000,00 | R$ 48.000,00 | Crescimento |
| 4 | Projetado | R$ 0,00 | R$ 580.000,00 | R$ 69.600,00 | R$ 232.000,00 | R$ 52.000,00 | Maturação |

- Valores crescentes e alternância `Realizado`/`Projetado` para testar filtros e cálculos.
- Ativado pelo botão **"Carregar Template de Demonstração/Homologação"** na **Aba 1** (persiste em `st.session_state.df_lancamentos`).

### Validações na Carga

- Verificação de colunas obrigatórias (`validar_dataframe()` em `app.py:420`).
- Detecção de campos nulos e textos em colunas numéricas (`pd.to_numeric(..., errors="coerce")`).
- `Tipo_Dado` restrito a `Realizado`/`Projetado` e `Periodo > 0`.
- Na **Aba 2**, o botão **"Homologar Alterações de Dados"** revalida antes de salvar na sessão global.

---

## 📁 Estrutura de Pastas Sugerida

```
rentabilidade-varejo-atacado/
│
├── app.py                  # Aplicação Streamlit principal (4 abas, motor de cálculo)
├── schema.sql              # DDL SQL Server: TB_PROJETOS + TB_LANCAMENTOS_FINANCEIROS + índices
├── requirements.txt        # Dependências Python (streamlit, pandas, pyodbc, etc.)
├── Dockerfile              # Imagem python:3.11-slim + ODBC Driver 17
├── docker-compose.yml      # Orquestração (app + env_file .env + rede bridge)
├── .env.example            # Modelo de variáveis de ambiente (versionado)
├── .env                    # Credenciais reais (NÃO versionado — adicione ao .gitignore)
├── .gitignore              # Deve conter: .env, __pycache__/, .venv/, *.log
├── README.md               # Esta documentação
│
├── .opencode/              # (opcional) Configurações do OpenCode
├── data/                   # (opcional) Exemplos de CSVs para teste
│   └── exemplo_lancamentos.csv
├── tests/                  # (opcional) Testes automatizados
│   └── test_calculo.py
└── docs/                   # (opcional) Documentação adicional
    └── arquitetura.md
```

### Boas Práticas de Versionamento

- **Versionar:** `app.py`, `schema.sql`, `Dockerfile`, `docker-compose.yml`, `requirements.txt`, `.env.example`, `README.md`.
- **Nunca versionar:** `.env` (credenciais), `__pycache__/`, `.venv/`, `*.pyc`, `*.log`.
- Exemplo de `.gitignore`:

  ```gitignore
  # Credenciais
  .env

  # Python
  __pycache__/
  *.py[cod]
  .venv/
  venv/
  *.egg-info/

  # OS
  .DS_Store
  Thumbs.db

  # Logs
  *.log
  ```

---

## 🏗️ Arquitetura e Fluxo de Governança

```
┌─────────────┐     ┌──────────────┐     ┌─────────────────┐
│  Usuário    │────▶│  Streamlit   │────▶│  Session State  │
│  (Browser)  │◀────│  (app.py)    │◀────│  (df_lancamentos│
└─────────────┘     └──────┬───────┘     │   + kpis)       │
                          │              └─────────────────┘
                          │ pyodbc (init_connection)
                          │ credenciais via os.environ (.env)
                          ▼
                   ┌──────────────┐
                   │  SQL Server  │
                   │ TB_PROJETOS  │──FK CASCADE──▶ TB_LANCAMENTOS_FINANCEIROS
                   └──────────────┘
                          ▲
                   ┌──────────────┐
                   │  Docker      │
                   │  python:3.11 │ + ODBC Driver 17
                   │  compose     │ env_file: .env
                   └──────────────┘
```

### Detalhes Técnicos Relevantes

- **`init_connection()`** (`app.py:85`): Lê `DB_SERVER`, `DB_DATABASE`, `DB_UID`, `DB_PWD`, `DB_PORT`, `DB_DRIVER` de `os.environ` (carregadas via `load_dotenv()`). Valida faltantes e monta string ODBC com `Encrypt`/`TrustServerCertificate`.
- **`inserir_projeto_e_lancamentos()`** (`app.py:140`): Transação explícita (`autocommit=False`, `executemany`, `commit`/`rollback`) com `SCOPE_IDENTITY()` para recuperar `id_projeto`.
- **Modo Offline Resiliente** (`app.py:580`): Se o banco estiver indisponível, o cálculo financeiro ainda executa e exibe resultados; a falha de persistência é reportada sem bloquear o fluxo (útil para homologação sem BD).

---

## 🧮 Motor de Cálculo Financeiro

Implementado em `calcular_metricas()` (`app.py:260`):

| Linha Calculada | Fórmula |
|---|---|
| **Receita Líquida** | `Receita_Bruta_2_00 - Deducoes_2_03` |
| **Margem de Contribuição** | `Receita_Líquida - Custos_Variaveis_3_00` |
| **Fluxo de Caixa Líquido** | `Margem - Despesas_Fixas_4_00 - Capex_1_00` |
| **Fluxo Descontado** | `FCL / (1 + TMA)^Periodo` |
| **Fluxo Descontado Acumulado** | `cumsum(Fluxo_Descontado)` |

| KPI | Método |
|---|---|
| **VPL** | `soma(Fluxo_Descontado)` |
| **TIR** | `numpy_financial.irr(Fluxo_Caixa_Liquido)` — taxa que zera o VPL |
| **Payback Descontado** | Interpolação linear no período em que `Acumulado >= 0`; `None` se nunca recupera |
| **ROIC Operacional** | `(Margem - Despesas Fixas do último período) / Capex_Total × 100` |
| **Giro do Ativo** | `Receita_Líquida_Total / Capex_Total` |

### Alertas de Risco Operacional (Aba 4)

| Condição | Severidade | Mensagem |
|---|---|---|
| `Giro < 1.2` e `Canal = Varejo` | `st.warning` | Giro do Ativo abaixo do threshold setorial de Varejo |
| `TIR < 5%` e `Canal = Atacado` | `st.error` | TIR crítica abaixo do piso de Atacado |
| `VPL < 0` | `st.error` | Projeto destrói valor à TMA informada |
| `Payback = None` | `st.warning` | Investimento não recuperado no horizonte |
| `ROIC < 0` | `st.warning` | Último período com prejuízo operacional |

---

## 🔧 Troubleshooting

| Problema | Causa Provável | Solução |
|---|---|---|
| `Variáveis de ambiente obrigatórias não definidas` | `.env` não criado ou não montado | `cp .env.example .env` e preencher; verificar `env_file` no compose |
| `Login failed for user 'sa'` | Senha incorreta ou usuário sem permissão | Conferir `DB_PWD` e `DB_UID`; testar via SSMS |
| `TCP Provider: No connection could be made` | SQL Server inacessível / porta bloqueada | Verificar `DB_SERVER`/`DB_PORT`, firewall, se instância está rodando |
| `Driver not found` / `Can't open lib` | ODBC Driver não instalado | Rebuild: `docker compose up --build`; verificar `Dockerfile` |
| `UNIQUE constraint failed` ao criar projeto | Nome de projeto duplicado | Escolher outro nome (constraint `UQ_TB_PROJETOS_NOME`) |
| CSV não carrega / colunas ausentes | Cabeçalho com nomes diferentes ou encoding | Usar nomes exatos de `COLUNAS_PLANO_CONTAS`; salvar CSV em UTF-8 |
| TIR = N/D | Fluxos sem inversão de sinal (só negativos ou só positivos) | Incluir pelo menos um período com Capex negativo e outros positivos |

### Comandos Úteis

```bash
# Ver drivers ODBC dentro do container
docker exec rentabilidade-app odbcinst -q -d
docker exec rentabilidade-app cat /etc/odbcinst.ini

# Testar conexão SQL via sqlcmd (se mssql-tools instalado)
docker exec -it rentabilidade-app /opt/mssql-tools18/bin/sqlcmd -S localhost,1433 -U sa -P 'SuaSenha' -Q "SELECT 1"

# Reiniciar do zero
docker compose down -v
docker compose up --build -d
docker compose logs -f
```

---

## 📄 Licença

Uso corporativo interno. Todos os direitos reservados.

## 👥 Contato

- **Engenharia Financeira & Arquitetura de Soluções** — time de rentabilidade física
- **DevOps / Infraestrutura** — diagnósticos via **Aba 4 > Área Técnica** (`st.expander` exclusivo)

---

*Gerado para Python 3.11+ | Streamlit | SQL Server | Docker | python-dotenv | pyodbc*
