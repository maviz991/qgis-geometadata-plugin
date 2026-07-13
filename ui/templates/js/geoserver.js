// geoserver.js - Painel de publicação GeoServer (RF01 completo + RF04 + RF02 de
// requisitos_v2.md). Por decisão de negócio, só camadas que já existem no banco
// PostgreSQL podem ser publicadas (registro lógico) - upload de arquivo local (RF03)
// não é suportado. Depende de app.js (bridge/gnBridge/gsBridge globais, initCustomSelects,
// _showActionLoading/_hideActionLoading) já carregado antes deste script.

var _gsLayerInfo = null;
var _gsNameTimer = null;
var _gsLastPublishWorkspace = null; // capturado em confirmGsPublish(), usado ao montar o "name" (ws:layer) pro link automático em Distribuição
var _gsTableCheckState = null; // null = não checado/checando, true = tabela encontrada no datastore, false = não encontrada
var _gsAutoDetectRunning = false;
var _gsPendingAutoDatastore = null; // datastore a selecionar assim que a lista de datastores do workspace escolhido carregar

function _initGsBridge() {
    gsBridge.gs_workspaces_ready.connect(function (workspaces, error) {
        _renderGsWorkspaces(workspaces, error);
    });
    gsBridge.gs_datastores_ready.connect(function (datastores, error) {
        _renderGsDatastores(datastores, error);
    });
    gsBridge.gs_featuretypes_ready.connect(function (names, error) {
        _renderGsTableCheck(names, error);
    });
    gsBridge.gs_find_datastore_progress.connect(function (msg) {
        _setGsAutoDetectStatus(msg);
    });
    gsBridge.gs_find_datastore_done.connect(function (matches, error) {
        _onGsAutoDetectDone(matches, error);
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
    card.innerHTML = '<span class="gs-status-text">Detectando camada ativa...</span>';
    if (form) form.style.display = 'none';
    _setGsTableCheck(null, ''); // camada mudou - qualquer checagem de tabela anterior não vale mais
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
        card.innerHTML = '<span class="gs-status-text gs-warning-text">' + escHtml((info && info.reason) || 'Nenhuma camada ativa suportada.') + '</span>';
        if (form) form.style.display = 'none';
        return;
    }

    card.innerHTML =
        '<span class="gs-layer-badge">PostgreSQL</span>' +
        '<span class="gs-layer-detected-name">' + escHtml(info.name) +
        '<small>' + escHtml(info.schema) + '.' + escHtml(info.table) + '</small></span>';

    if (form) form.style.display = 'grid';

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
    _setGsTableCheck(null, ''); // troca de workspace invalida qualquer checagem anterior
    if (!workspace) {
        dsWrap.innerHTML = '<select id="gs-datastore" onchange="onGsDatastoreChange(this.value)" disabled><option value="">Selecione um workspace primeiro</option></select>';
        initCustomSelects();
        _updateGsPublishButton();
        return;
    }
    dsWrap.innerHTML = '<select id="gs-datastore" onchange="onGsDatastoreChange(this.value)"><option value="">Carregando...</option></select>';
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
    dsWrap.innerHTML = '<select id="gs-datastore" onchange="onGsDatastoreChange(this.value)">' + options + '</select>';
    initCustomSelects();
    _updateGsPublishButton();

    // Se veio de "Detectar automaticamente", seleciona o datastore encontrado assim que
    // a lista termina de carregar pra esse workspace (ver autoDetectGsDatastore()).
    if (_gsPendingAutoDatastore) {
        var target = _gsPendingAutoDatastore;
        _gsPendingAutoDatastore = null;
        if ((datastores || []).indexOf(target) !== -1) {
            _clickGsSuggestionItem('gs-datastore-wrap', target);
        }
    }
}

// Ao escolher o datastore, confere na hora se a tabela da camada ativa está mesmo
// visível ali (list=all - a mesma lista que a tela "Publicar" do GeoServer usa). Evita
// o 400 "no attributes were specified" que só aparecia depois do clique em Publicar,
// quando o Schema do datastore é diferente do schema real da tabela no banco.
function onGsDatastoreChange(datastore) {
    _updateGsPublishButton();
    var wsEl = document.getElementById('gs-workspace');
    var workspace = wsEl ? wsEl.value : '';
    if (!datastore || !workspace || !_gsLayerInfo || !_gsLayerInfo.table) {
        _setGsTableCheck(null, '');
        return;
    }
    _setGsTableCheck(null, 'Verificando se a tabela "' + _gsLayerInfo.table + '" existe neste datastore...');
    gsBridge.list_featuretypes(workspace, datastore);
}

function _renderGsTableCheck(names, error) {
    if (!_gsLayerInfo || !_gsLayerInfo.table) return;
    if (error) {
        _setGsTableCheck(null, ''); // não trava o fluxo por causa de um erro na checagem em si
        return;
    }
    var table = _gsLayerInfo.table.toLowerCase();
    var found = (names || []).some(function (n) { return (n || '').toLowerCase() === table; });
    _setGsTableCheck(found,
        found
            ? 'Tabela "' + _gsLayerInfo.table + '" encontrada neste datastore.'
            : 'Tabela "' + _gsLayerInfo.table + '" não foi encontrada neste datastore. Confira se escolheu o workspace/datastore certo (ex.: Schema do datastore diferente do schema da tabela) antes de publicar.'
    );
}

function _setGsTableCheck(state, message) {
    _gsTableCheckState = state;
    var el = document.getElementById('gs-datastore-check');
    if (el) {
        el.textContent = message;
        el.className = 'gs-name-preview' + (state === false ? ' gs-warning-text' : '');
    }
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
        ws && ws.value && ds && ds.value && nameEl && nameEl.value.trim() &&
        _gsTableCheckState !== false); // só bloqueia com confirmação NEGATIVA - "desconhecido"/checando não trava
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

// ─── "Detectar automaticamente" (workspace/datastore) ──────────────────────────
// Varre todos os workspaces/datastores do GeoServer procurando onde a tabela da camada
// ativa está visível. Mais lento que o resto (1 chamada por workspace + 1 por datastore
// de cada um), por isso mostra progresso e não é a via padrão - só um atalho pra quem
// não sabe o workspace/datastore certo.
function autoDetectGsDatastore() {
    if (_gsAutoDetectRunning) return;
    if (!_gsLayerInfo || !_gsLayerInfo.publishable) return;
    _gsAutoDetectRunning = true;
    var btn = document.querySelector('.gs-autodetect-link');
    if (btn) btn.disabled = true;
    var candidates = document.getElementById('gs-autodetect-candidates');
    if (candidates) candidates.style.display = 'none';
    _setGsAutoDetectStatus('Procurando em todos os workspaces/datastores... isso pode demorar alguns segundos.');
    gsBridge.find_datastore_for_active_layer();
}

function _setGsAutoDetectStatus(msg) {
    var el = document.getElementById('gs-autodetect-status');
    if (el) el.textContent = msg || '';
}

function _onGsAutoDetectDone(matches, error) {
    _gsAutoDetectRunning = false;
    var btn = document.querySelector('.gs-autodetect-link');
    if (btn) btn.disabled = false;

    if (error) {
        _setGsAutoDetectStatus('');
        Modal.alert(error, 'Erro', 'error');
        return;
    }
    if (!matches || !matches.length) {
        _setGsAutoDetectStatus('Tabela "' + ((_gsLayerInfo && _gsLayerInfo.table) || '') + '" não foi encontrada em nenhum workspace/datastore visível no GeoServer.');
        return;
    }
    if (matches.length === 1) {
        _setGsAutoDetectStatus('Encontrado: ' + matches[0].workspace + ' / ' + matches[0].datastore + '. Selecionando...');
        _selectGsWorkspaceDatastore(matches[0].workspace, matches[0].datastore);
        return;
    }
    _setGsAutoDetectStatus('Encontrado em ' + matches.length + ' datastores diferentes - escolha um:');
    _renderGsAutoDetectCandidates(matches);
}

function _renderGsAutoDetectCandidates(matches) {
    var wrap = document.getElementById('gs-autodetect-candidates');
    if (!wrap) return;
    wrap.innerHTML = matches.map(function (m, i) {
        return '<button type="button" class="gs-autodetect-candidate" onclick="_pickGsAutoDetectCandidate(' + i + ')">' +
            escHtml(m.workspace) + ' / ' + escHtml(m.datastore) + '</button>';
    }).join('');
    wrap.style.display = 'flex';
    wrap._gsCandidates = matches; // guarda a lista original (não confiar em reparse do HTML)
}

function _pickGsAutoDetectCandidate(idx) {
    var wrap = document.getElementById('gs-autodetect-candidates');
    var m = wrap && wrap._gsCandidates && wrap._gsCandidates[idx];
    if (!m) return;
    wrap.style.display = 'none';
    _setGsAutoDetectStatus('Selecionando ' + m.workspace + ' / ' + m.datastore + '...');
    _selectGsWorkspaceDatastore(m.workspace, m.datastore);
}

// Seleciona programaticamente workspace + datastore nos custom-selects, disparando os
// mesmos handlers que um clique manual do usuário dispararia (onGsWorkspaceChange,
// depois onGsDatastoreChange já com a checagem de tabela).
function _selectGsWorkspaceDatastore(workspace, datastore) {
    _gsPendingAutoDatastore = datastore;
    if (!_clickGsSuggestionItem('gs-workspace-wrap', workspace)) {
        _gsPendingAutoDatastore = null;
        _setGsAutoDetectStatus('Encontrado em ' + workspace + ' / ' + datastore + ', mas não consegui selecionar automaticamente - selecione manualmente acima.');
    }
}

function _clickGsSuggestionItem(wrapId, value) {
    var wrap = document.getElementById(wrapId);
    if (!wrap) return false;
    var items = wrap.querySelectorAll('.suggestion-item');
    for (var i = 0; i < items.length; i++) {
        if (items[i].dataset.value === value) {
            items[i].click();
            return true;
        }
    }
    return false;
}
