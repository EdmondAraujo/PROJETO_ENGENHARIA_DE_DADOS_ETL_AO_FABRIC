// ============================================================================
// Endpoint interno de embed token — Power BI Embedded ("app owns data")
// ============================================================================
// Referência: https://learn.microsoft.com/power-bi/developer/embedded/embed-sample-for-customers
//
// Pré-requisitos no Azure:
//   1. Registrar um App no Entra ID e criar um segredo (ou usar certificado)
//   2. No tenant do Power BI, habilitar "Allow service principals to use
//      Power BI APIs" no Admin Portal
//   3. Adicionar o Service Principal como membro do workspace do relatório
//   4. Criar uma Capacity (Fabric F / Power BI Premium P ou Em/A) e atribuir
//      o workspace a ela — obrigatório para Service Principal
//
// Variáveis de ambiente esperadas:
//   PBI_TENANT_ID, PBI_CLIENT_ID, PBI_CLIENT_SECRET,
//   PBI_WORKSPACE_ID, PBI_REPORT_ID
// ============================================================================

using Azure.Identity;
using Microsoft.PowerBI.Api;
using Microsoft.Rest;
using System.Text.Json;

var builder = WebApplication.CreateBuilder(args);
var app = builder.Build();

string TenantId = Environment.GetEnvironmentVariable("PBI_TENANT_ID")!;
string ClientId = Environment.GetEnvironmentVariable("PBI_CLIENT_ID")!;
string ClientSecret = Environment.GetEnvironmentVariable("PBI_CLIENT_SECRET")!;
string WorkspaceId = Environment.GetEnvironmentVariable("PBI_WORKSPACE_ID")!;
string ReportId = Environment.GetEnvironmentVariable("PBI_REPORT_ID")!;

app.MapGet("/api/powerbi/embed-token", async () =>
{
    var credencial = new ClientSecretCredential(TenantId, ClientId, ClientSecret);

    using var clientePowerBi = new PowerBIClient(
        new Uri("https://api.powerbi.com/"),
        new TokenCredentials(credencial.GetToken(
            new Azure.Core.TokenRequestContext(
                new[] { "https://analysis.windows.net/powerbi/api/.default" })).Token));

    var relatorio = await clientePowerBi.Reports.GetReportInGroupAsync(
        Guid.Parse(WorkspaceId), Guid.Parse(ReportId));

    var embedToken = await clientePowerBi.Reports.GenerateTokenInGroupAsync(
        Guid.Parse(WorkspaceId),
        Guid.Parse(ReportId),
        new GenerateTokenRequest(accessLevel: "view"));

    return Results.Json(new
    {
        reportId = relatorio.Id.ToString(),
        embedUrl = relatorio.EmbedUrl,
        token = embedToken.Token
    });
});

app.Run();
