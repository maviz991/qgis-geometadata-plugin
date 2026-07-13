// geoserver.js - Painel de publicação GeoServer (RF01 completo + RF04 + RF02 de
// requisitos_v2.md). Por decisão de negócio, só camadas que já existem no banco
// PostgreSQL podem ser publicadas (registro lógico) - upload de arquivo local (RF03)
// não é suportado. Depende de app.js (bridge/gnBridge/gsBridge globais, initCustomSelects,
// _showActionLoading/_hideActionLoading) já carregado antes deste script.

var _gsLayerInfo = null;
var _gsNameTimer = null;
var _gsLastPublishWorkspace = null; // capturado em confirmGsPublish(), usado ao montar o "name" (ws:layer) pro link automático em Distribuição

function _initGsBridge() {
    gsBridge.gs_workspaces_ready.connect(function (workspaces, error) {
        _renderGsWorkspaces(workspaces, error);
    });
    gsBridge.gs_datastores_ready.connect(function (datastores, error) {
        _renderGsDatastores(datastores, error);
    });
    gsBridge.gs_publish_done.connect(function (success, message, publishedName, wmsUrl, wfsUrl) {
        _hideActionLoading();
        if (!success) {
            Modal.alert(message || 'Falha ao publicar no GeoServer.', 'Erro', 'error');
            return;
        }
        // Publicado - leva o usuário direto pra Distribuição já com WMS+WFS vinculados e a
        // miniatura gerada (_applyPendingGsDistLayerIfAny, em geonetwork.js, roda assim
        // que o formulário do editor terminar de carregar pra essa camada).
        if (wmsUrl && _gsLastPublishWorkspace) {
            window._pendingGsDistLayer = {
                wms_url: wmsUrl,
                wfs_url: wfsUrl || '',
                name: _gsLastPublishWorkspace + ':' + publishedName,
                title: publishedName
            };
        }
        navigate('editor');
    });
}

// Chamado por onPanelLoaded() (app.js) quando o painel "geoserver" acabou de carregar.
function _onGeoServerPanelLoaded() {
    if (!document.getElementById('gs-layer-card')) return;
    _loadGsLayerInfo();
    _loadGsWorkspaces();
}

// Chamado por app.js quando a camada ativa do QGIS muda (bridge.layer_changed). Nome
// distinto de _onActiveLayerChanged (GN) de propósito - as duas funções coexistem no
// mesmo escopo global e uma declaração igual sobrescreveria a outra silenciosamente.
function _onGsActiveLayerChanged() {
    if (document.getElementById('gs-layer-card')) {
        _loadGsLayerInfo();
    }
}

function _loadGsLayerInfo() {
    var card = document.getElementById('gs-layer-card');
    var form = document.getElementById('gs-publish-form');
    if (!card) return;
    card.innerHTML = '<div class="gs-empty">Detectando camada ativa...</div>';
    if (form) form.style.display = 'none';
    gsBridge.get_active_layer_publish_info(function (info) {
        _gsLayerInfo = info;
        _renderGsLayerCard(info);
    });
}

function _renderGsLayerCard(info) {
    var card = document.getElementById('gs-layer-card');
    var form = document.getElementById('gs-publish-form');
    if (!card) return; // painel já foi trocado

    if (!info || !info.publishable) {
        card.innerHTML = '<div class="gs-empty gs-warning">' + escHtml((info && info.reason) || 'Nenhuma camada ativa suportada.') + '</div>';
        if (form) form.style.display = 'none';
        return;
    }

    card.innerHTML =
        '<div class="gs-layer-detected">' +
        '<span class="gs-layer-badge">PostgreSQL</span>' +
        '<div class="gs-layer-detected-info">' +
        '<strong>' + escHtml(info.name) + '</strong>' +
        '<small>' + escHtml(info.schema) + '.' + escHtml(info.table) + '</small>' +
        '</div></div>';

    if (form) form.style.display = 'block';

    var nameEl = document.getElementById('gs-layer-name');
    if (nameEl && !nameEl.value) {
        nameEl.value = info.name;
        onGsLayerNameInput(info.name);
    }
    var titleEl = document.getElementById('gs-layer-title');
    if (titleEl && !titleEl.value) {
        titleEl.value = info.title || info.name;
    }
    _updateGsPublishButton();
}

function _loadGsWorkspaces() {
    var wrap = document.getElementById('gs-workspace-wrap');
    if (!wrap) return;
    wrap.innerHTML = '<select id="gs-workspace" onchange="onGsWorkspaceChange(this.value)"><option value="">Carregando...</option></select>';
    gsBridge.list_workspaces();
}

function _renderGsWorkspaces(workspaces, error) {
    var wrap = document.getElementById('gs-workspace-wrap');
    if (!wrap) return; // painel já foi trocado
    if (error) {
        wrap.innerHTML = '<select id="gs-workspace"><option value="">Erro ao carregar workspaces</option></select>';
        Modal.alert(error, 'Erro', 'error');
        return;
    }
    var options = '<option value="">Selecione um workspace...</option>';
    (workspaces || []).forEach(function (ws) {
        options += '<option value="' + escHtml(ws) + '">' + escHtml(ws) + '</option>';
    });
    wrap.innerHTML = '<select id="gs-workspace" onchange="onGsWorkspaceChange(this.value)">' + options + '</select>';
    initCustomSelects();
    onGsWorkspaceChange('');
}

function onGsWorkspaceChange(workspace) {
    var dsWrap = document.getElementById('gs-datastore-wrap');
    if (!dsWrap) return;
    if (!workspace) {
        dsWrap.innerHTML = '<select id="gs-datastore" onchange="_updateGsPublishButton()" disabled><option value="">Selecione um workspace primeiro</option></select>';
        initCustomSelects();
        _updateGsPublishButton();
        return;
    }
    dsWrap.innerHTML = '<select id="gs-datastore" onchange="_updateGsPublishButton()"><option value="">Carregando...</option></select>';
    initCustomSelects();
    gsBridge.list_datastores(workspace);
}

function _renderGsDatastores(datastores, error) {
    var dsWrap = document.getElementById('gs-datastore-wrap');
    if (!dsWrap) return; // painel já foi trocado
    if (error) {
        dsWrap.innerHTML = '<select id="gs-datastore"><option value="">Erro ao carregar datastores</option></select>';
        initCustomSelects();
        Modal.alert(error, 'Erro', 'error');
        return;
    }
    var options = '<option value="">Selecione um datastore...</option>';
    (datastores || []).forEach(function (ds) {
        options += '<option value="' + escHtml(ds) + '">' + escHtml(ds) + '</option>';
    });
    dsWrap.innerHTML = '<select id="gs-datastore" onchange="_updateGsPublishButton()">' + options + '</select>';
    initCustomSelects();
    _updateGsPublishButton();
}

function onGsLayerNameInput(name) {
    clearTimeout(_gsNameTimer);
    _gsNameTimer = setTimeout(function () {
        gsBridge.sanitize_layer_name(name, function (sanitized) {
            var preview = document.getElementById('gs-layer-name-preview');
            if (preview) preview.textContent = sanitized ? ('Nome final: ' + sanitized) : '';
            var nameEl = document.getElementById('gs-layer-name');
            if (nameEl) nameEl.dataset.sanitized = sanitized;
            _updateGsPublishButton();
        });
    }, 200);
}

function _updateGsPublishButton() {
    var btn = document.getElementById('gs-publish-btn');
    if (!btn) return;
    var ws = document.getElementById('gs-workspace');
    var ds = document.getElementById('gs-datastore');
    var nameEl = document.getElementById('gs-layer-name');
    var ok = !!(_gsLayerInfo && _gsLayerInfo.publishable &&
        ws && ws.value && ds && ds.value && nameEl && nameEl.value.trim());
    btn.disabled = !ok;
}

function confirmGsPublish() {
    if (!_gsLayerInfo || !_gsLayerInfo.publishable) return;
    var ws = document.getElementById('gs-workspace');
    var ds = document.getElementById('gs-datastore');
    var nameEl = document.getElementById('gs-layer-name');
    if (!ws || !ws.value || !ds || !ds.value || !nameEl || !nameEl.value.trim()) return;

    var workspace = ws.value;
    var datastore = ds.value;
    var publishedName = nameEl.dataset.sanitized || nameEl.value.trim();
    var titleEl = document.getElementById('gs-layer-title');
    var title = (titleEl && titleEl.value.trim()) || publishedName;
    // Resumo/palavras-chave: os mesmos valores que get_active_layer_publish_info() já
    // calculou e devolveu (ver _renderGsLayerCard) - mandados explicitamente de volta em
    // vez do Python buscar de novo, pra não ter duas buscas divergindo entre si.
    var abstract = _gsLayerInfo.abstract || '';
    var keywords = _gsLayerInfo.keywords || [];

    Modal.confirm(
        'Publicar a camada "' + escHtml(_gsLayerInfo.name) + '" como "' + escHtml(publishedName) +
        '" no workspace "' + escHtml(workspace) + '" (datastore "' + escHtml(datastore) + '")?',
        function () {
            _gsLastPublishWorkspace = workspace;
            _showActionLoading('Publicando no GeoServer...');
            gsBridge.publish_layer(workspace, datastore, publishedName, title, abstract, keywords);
        },
        'Confirmar Publicação'
    );
}
