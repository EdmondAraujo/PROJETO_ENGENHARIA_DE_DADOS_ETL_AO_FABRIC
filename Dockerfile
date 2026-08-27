# =============================================================================
# SISTEMA DE APURAÇÃO DE RENTABILIDADE - DOCKERFILE
# Imagem Streamlit + Python 3.11-slim + Microsoft ODBC Driver 17
# =============================================================================
FROM python:3.11-slim

# Evita prompts interativos durante apt-get
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# --- 1. Dependências do Sistema Operacional ---
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    gnupg2 \
    unixodbc \
    unixodbc-dev \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# --- 2. Instalação do Microsoft ODBC Driver 17 para SQL Server (Debian 12/bookworm) ---
# Documentação oficial: https://learn.microsoft.com/en-us/sql/connect/odbc/linux-mac/installing-the-microsoft-odbc-driver-for-sql-server
RUN curl https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor > /usr/share/keyrings/microsoft-prod.gpg \
    && curl https://packages.microsoft.com/config/debian/12/prod.list > /etc/apt/sources.list.d/mssql-release.list \
    && apt-get update \
    && ACCEPT_EULA=Y apt-get install -y --no-install-recommends msodbcsql17 \
    && rm -rf /var/lib/apt/lists/*

# Opcional: instalar mssql-tools para debug (sqlcmd)
# RUN ACCEPT_EULA=Y apt-get install -y mssql-tools18 && echo 'export PATH="$PATH:/opt/mssql-tools18/bin"' >> ~/.bashrc

# --- 3. Diretório de trabalho ---
WORKDIR /app

# --- 4. Dependências Python (cache otimizado) ---
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# --- 5. Código da aplicação ---
COPY . .

# --- 6. Exposição de porta ---
EXPOSE 8501

# --- 7. Healthcheck (verifica se Streamlit está respondendo) ---
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl --fail http://localhost:8501/_stcore/health || exit 1

# --- 8. Comando de inicialização ---
CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0", "--server.headless=true"]
