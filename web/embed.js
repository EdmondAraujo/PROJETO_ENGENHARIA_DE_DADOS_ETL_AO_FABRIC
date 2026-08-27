(function () {
  "use strict";

  var ENDPOINT_TOKEN = "/api/powerbi/embed-token";
  var CONTEINER_ID = "conteiner-relatorio";
  var ERRO_ID = "mensagem-erro";

  function exibirErro() {
    document.getElementById(CONTEINER_ID).style.display = "none";
    document.getElementById(ERRO_ID).style.display = "block";
  }

  function incorporarRelatorio(dados) {
    var modelos = window.powerbi.models;
    var config = {
      type: "report",
      id: dados.reportId,
      embedUrl: dados.embedUrl,
      tokenType: modelos.TokenType.Embed,
      accessToken: dados.token,
      settings: {
        panes: { filters: { visible: false }, pageNavigation: { visible: true } },
        background: modelos.BackgroundType.Transparent
      }
    };
    window.powerbi.embed(document.getElementById(CONTEINER_ID), config);
  }

  fetch(ENDPOINT_TOKEN, { credentials: "include" })
    .then(function (r) {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    })
    .then(incorporarRelatorio)
    .catch(exibirErro);
})();
