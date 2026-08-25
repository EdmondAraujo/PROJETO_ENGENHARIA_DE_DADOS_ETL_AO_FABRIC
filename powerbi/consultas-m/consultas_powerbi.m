// ============================================================================
// Consultas Power Query (M) — Cruzamento ANP 2020–2025
// ============================================================================
// Como usar no Power BI Desktop:
//   1. Transformar dados > Editor do Power Query > Nova Fonte > Consulta Nula
//   2. Abrir o "Editor Avançado" e colar cada bloco como uma consulta
//      (renomeie a consulta com o nome indicado no cabeçalho de cada bloco)
//   3. Ajuste o parâmetro CAMINHO_DADOS (consulta "Parametros"):
//        - Local:  pasta ...\data\processed\  (com barra invertida final)
//        - Fabric: caminho abfss do OneLake (exemplo em docs/03)
// ============================================================================

// ---------------------------------------------------------------------------
// Consulta: Parametros
// ---------------------------------------------------------------------------
let
    CAMINHO_DADOS = "C:\projetos\anp-powerbi-fabric-cosmosdb\data\processed\",
    Resultado = [CaminhoDados = CAMINHO_DADOS]
in
    Resultado

// ---------------------------------------------------------------------------
// Consulta: FatoMensal
// Série mensal 2020–2025: produção nacional x importação x exportação (barris)
// ---------------------------------------------------------------------------
let
    Fonte = Csv.Document(
        File.Contents(Parametros[CaminhoDados] & "fato_mensal_2020_2025.csv"),
        [Delimiter = ",", Columns = 9, Encoding = 65001, QuoteStyle = QuoteStyle.None]
    ),
    Cabecalhos = Table.PromoteHeaders(Fonte, [PromoteAllScalars = true]),
    Tipagem = Table.TransformColumnTypes(
        Cabecalhos,
        {
            {"DATA", type date},
            {"ANO", Int64.Type},
            {"TRIMESTRE", Int64.Type},
            {"MES_NUM", Int64.Type},
            {"MES_NOME", type text},
            {"PRODUCAO_BARRIS", type number},
            {"IMPORTACAO_BARRIS", type number},
            {"EXPORTACAO_BARRIS", type number},
            {"BALANCA_COMERCIAL_BARRIS", type number}
        }
    )
in
    Tipagem

// ---------------------------------------------------------------------------
// Consulta: FatoAnual
// Agregado anual com variações YoY e indicadores de cruzamento
// ---------------------------------------------------------------------------
let
    Fonte = Csv.Document(
        File.Contents(Parametros[CaminhoDados] & "fato_anual_2020_2025.csv"),
        [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.None]
    ),
    Cabecalhos = Table.PromoteHeaders(Fonte, [PromoteAllScalars = true]),
    Tipagem = Table.TransformColumnTypes(
        Cabecalhos,
        {
            {"ANO", Int64.Type},
            {"PRODUCAO_BARRIS", type number},
            {"IMPORTACAO_BARRIS", type number},
            {"EXPORTACAO_BARRIS", type number},
            {"BALANCA_COMERCIAL_BARRIS", type number},
            {"CAMPOS_EM_PRODUCAO", Int64.Type},
            {"CAMPOS_EM_DESENVOLVIMENTO", Int64.Type},
            {"CAMPOS_TOTAL_FASE", Int64.Type},
            {"PRODUCAO_BARRIS_YOY_PCT", type number},
            {"IMPORTACAO_BARRIS_YOY_PCT", type number},
            {"EXPORTACAO_BARRIS_YOY_PCT", type number},
            {"COBERTURA_EXPORT_PCT", type number},
            {"DEPENDENCIA_IMPORT_PCT", type number}
        }
    )
in
    Tipagem

// ---------------------------------------------------------------------------
// Consulta: DimFasesCampos
// Quantidade de campos por ano nas fases Produção / Desenvolvimento
// ---------------------------------------------------------------------------
let
    Fonte = Csv.Document(
        File.Contents(Parametros[CaminhoDados] & "dim_campos_fase_anual.csv"),
        [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.None]
    ),
    Cabecalhos = Table.PromoteHeaders(Fonte, [PromoteAllScalars = true]),
    Tipagem = Table.TransformColumnTypes(
        Cabecalhos,
        {
            {"ANO", Int64.Type},
            {"CAMPOS_EM_PRODUCAO", Int64.Type},
            {"CAMPOS_EM_DESENVOLVIMENTO", Int64.Type},
            {"CAMPOS_TOTAL_FASE", Int64.Type}
        }
    )
in
    Tipagem

// ---------------------------------------------------------------------------
// Consulta: DimCampos
// Dimensão dos campos da Fase de Desenvolvimento e Produção (dados abertos ANP)
// ---------------------------------------------------------------------------
let
    Fonte = Csv.Document(
        File.Contents(Parametros[CaminhoDados] & "dim_campos.csv"),
        [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.None]
    ),
    Cabecalhos = Table.PromoteHeaders(Fonte, [PromoteAllScalars = true]),
    Tipagem = Table.TransformColumnTypes(
        Cabecalhos,
        {
            {"CODIGO_CAMPO", Int64.Type},
            {"CAMPO", type text},
            {"SIGLA_CAMPO", type text},
            {"BACIA", type text},
            {"ESTADO", type text},
            {"OPERADOR", type text},
            {"AMBIENTE", type text},
            {"RODADA", type text},
            {"NOME_CONTRATO", type text},
            {"NUMERO_CONTRATO", type text},
            {"SITUACAO_CAMPO", type text},
            {"DATA_ASSINATURA", type text},
            {"TERMINO_FASE", type text},
            {"DATA_INICIO_PRODUCAO", type date},
            {"DATA_TERMINO_PRODUCAO", type text}
        },
        "pt-BR"
    )
in
    Tipagem

// ---------------------------------------------------------------------------
// Consulta: DimCalendario  (tabela calculada — ver também versão DAX)
// Gerada aqui em M para manter todo o ETL num único lugar
// ---------------------------------------------------------------------------
let
    Inicio = #date(2020, 1, 1),
    Fim = #date(2025, 12, 31),
    Datas = List.Dates(Inicio, Duration.Days(Fim - Inicio) + 1, #duration(1, 0, 0, 0)),
    Tabela = Table.FromList(Datas, Splitter.SplitByNothing(), {"Data"}),
    Tipada = Table.TransformColumnTypes(Tabela, {{"Data", type date}}),
    Atributos = Table.AddColumn(Tipada, "Ano", each Date.Year([Data]), Int64.Type),
    MesNum = Table.AddColumn(Atributos, "MesNum", each Date.Month([Data]), Int64.Type),
    MesNome = Table.AddColumn(MesNum, "MesNome", each Date.ToText([Data], "MMM", "pt-BR"), type text),
    AnoMes = Table.AddColumn(MesNome, "AnoMes", each Date.ToText([Data], "yyyy-MM"), type text),
    Trimestre = Table.AddColumn(AnoMes, "Trimestre", each "T" & Text.From(Date.QuarterOfYear([Data])), type text)
in
    Trimestre
