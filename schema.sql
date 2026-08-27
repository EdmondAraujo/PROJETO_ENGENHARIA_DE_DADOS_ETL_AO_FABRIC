-- =============================================================================
-- SISTEMA DE APURAÇÃO DE RENTABILIDADE FÍSICA - VAREJO E ATACADO
-- Script DDL para Microsoft SQL Server 2019+
-- Autor: Arquitetura Corporativa / Engenharia Financeira
-- Data: 2026-08-27
-- Descrição: Criação das tabelas TB_PROJETOS e TB_LANCAMENTOS_FINANCEIROS
--            com relacionamentos, constraints e índices otimizados.
-- =============================================================================

-- Garante que o script seja executado no banco correto (ajuste conforme .env)
-- USE [DB_RENTABILIDADE];
-- GO

SET ANSI_NULLS ON;
GO
SET QUOTED_IDENTIFIER ON;
GO

-- =============================================
-- 1. TABELA DE PROJETOS (TB_PROJETOS)
-- =============================================
IF OBJECT_ID('dbo.TB_LANCAMENTOS_FINANCEIROS', 'U') IS NOT NULL
    DROP TABLE dbo.TB_LANCAMENTOS_FINANCEIROS;
GO

IF OBJECT_ID('dbo.TB_PROJETOS', 'U') IS NOT NULL
    DROP TABLE dbo.TB_PROJETOS;
GO

CREATE TABLE dbo.TB_PROJETOS (
    id_projeto      INT IDENTITY(1,1) PRIMARY KEY,
    nome            NVARCHAR(150) NOT NULL,
    canal           VARCHAR(20) NOT NULL
                        CONSTRAINT CK_TB_PROJETOS_CANAL CHECK (canal IN ('Varejo', 'Atacado')),
    escala_temporal VARCHAR(10) NOT NULL
                        CONSTRAINT CK_TB_PROJETOS_ESCALA CHECK (escala_temporal IN ('Mensal', 'Anual')),
    tma_percentual  DECIMAL(5,2) NOT NULL
                        CONSTRAINT CK_TB_PROJETOS_TMA CHECK (tma_percentual >= 0 AND tma_percentual <= 100),
    data_criacao    DATETIME2 DEFAULT GETDATE() NOT NULL,
    CONSTRAINT UQ_TB_PROJETOS_NOME UNIQUE (nome)
);
GO

-- Índice adicional para buscas por canal (relatórios setoriais)
CREATE INDEX IX_TB_PROJETOS_CANAL ON dbo.TB_PROJETOS(canal);
GO
CREATE INDEX IX_TB_PROJETOS_DATA_CRIACAO ON dbo.TB_PROJETOS(data_criacao DESC);
GO

-- =============================================
-- 2. TABELA DE LANÇAMENTOS FINANCEIROS
-- =============================================
CREATE TABLE dbo.TB_LANCAMENTOS_FINANCEIROS (
    id_lancamento       INT IDENTITY(1,1) PRIMARY KEY,
    id_projeto          INT NOT NULL,
    Periodo             INT NOT NULL
                            CONSTRAINT CK_TB_LANCAMENTOS_PERIODO CHECK (Periodo > 0),
    Tipo_Dado           VARCHAR(20) NOT NULL
                            CONSTRAINT CK_TB_LANCAMENTOS_TIPODADO CHECK (Tipo_Dado IN ('Realizado', 'Projetado')),
    Capex_1_00          DECIMAL(18,2) NOT NULL DEFAULT 0.00,
    Receita_Bruta_2_00  DECIMAL(18,2) NOT NULL DEFAULT 0.00,
    Deducoes_2_03       DECIMAL(18,2) NOT NULL DEFAULT 0.00,
    Custos_Variaveis_3_00 DECIMAL(18,2) NOT NULL DEFAULT 0.00,
    Despesas_Fixas_4_00 DECIMAL(18,2) NOT NULL DEFAULT 0.00,
    data_insercao       DATETIME2 DEFAULT GETDATE() NOT NULL,

    -- Chave estrangeira com exclusão em cascata
    CONSTRAINT FK_TB_LANCAMENTOS_PROJETO
        FOREIGN KEY (id_projeto)
        REFERENCES dbo.TB_PROJETOS(id_projeto)
        ON DELETE CASCADE
        ON UPDATE CASCADE,

    -- Evita duplicidade de lançamento para mesmo projeto/periodo/tipo
    CONSTRAINT UQ_TB_LANCAMENTOS_PROJETO_PERIODO_TIPO
        UNIQUE (id_projeto, Periodo, Tipo_Dado)
);
GO

-- =============================================
-- 3. ÍNDICES PARA OTIMIZAÇÃO
-- =============================================

-- Índice principal para consultas por projeto (JOIN mais frequente)
CREATE INDEX IX_TB_LANCAMENTOS_ID_PROJETO
    ON dbo.TB_LANCAMENTOS_FINANCEIROS(id_projeto);
GO

-- Índice para consultas por período (séries temporais)
CREATE INDEX IX_TB_LANCAMENTOS_PERIODO
    ON dbo.TB_LANCAMENTOS_FINANCEIROS(Periodo);
GO

-- Índice composto para consultas temporais por projeto (fluxo de caixa ordenado)
CREATE INDEX IX_TB_LANCAMENTOS_PROJETO_PERIODO
    ON dbo.TB_LANCAMENTOS_FINANCEIROS(id_projeto, Periodo);
GO

-- Índice para filtro por tipo de dado (Realizado vs Projetado)
CREATE INDEX IX_TB_LANCAMENTOS_TIPO_DADO
    ON dbo.TB_LANCAMENTOS_FINANCEIROS(Tipo_Dado);
GO

-- =============================================
-- 4. DADOS DE HOMOLOGAÇÃO (OPCIONAL - para testes)
-- =============================================
-- Descomente para inserir projeto de exemplo:
-- INSERT INTO dbo.TB_PROJETOS (nome, canal, escala_temporal, tma_percentual)
-- VALUES ('Projeto Piloto Varejo Mensal', 'Varejo', 'Mensal', 12.00);
-- GO

PRINT 'Schema criado com sucesso: TB_PROJETOS e TB_LANCAMENTOS_FINANCEIROS';
GO
