// geoserver.js - Painel de publicação GeoServer (Fase 1 de requisitos_v2.md: RF01
// listar workspaces/datastores, RF04 validação de nome). Depende de app.js
// (bridge/gnBridge/gsBridge globais) já carregado antes deste script.

function _initGsBridge() {
    gsBridge.gs_workspaces_ready.connect(function (workspaces, error) {
        _renderGsWorkspaces(workspaces, error);
    });
}

// Chamado por onPanelLoaded() (app.js) quando o painel "geoserver" acabou de carregar.
function _onGeoServerPanelLoaded() {
    var list = document.getElementById('gs-workspace-list');
    if (!list) return;
    list.innerHTML = '<div class="gs-empty">Carregando workspaces...</div>';
    gsBridge.list_workspaces();
}

function _renderGsWorkspaces(workspaces, error) {
    var list = document.getElementById('gs-workspace-list');
    if (!list) return; // painel já foi trocado
    if (error) {
        list.innerHTML = '<div class="gs-empty gs-error">' + escHtml(error) + '</div>';
        return;
    }
    if (!workspaces || !workspaces.length) {
        list.innerHTML = '<div class="gs-empty">Nenhum workspace encontrado.</div>';
        return;
    }
    list.innerHTML = workspaces.map(function (ws) {
        return '<div class="gs-workspace-item">' + escHtml(ws) + '</div>';
    }).join('');
}
