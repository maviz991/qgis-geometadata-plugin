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
var _gsPendingDraftWorkspace = null; // workspace a selecionar assim que a lista de workspaces carregar (rascunho ou destino salvo)
var _gsDraftHasWorkspace = false; // true se o rascunho local já resolveu e tinha um workspace - evita o destino salvo (banco) pisar em cima
var _gsKeywords = []; // estado das palavras-chave da aba Identificação (namespaced pra não colidir com `keywords` do editor GN, mesmo escopo global)
var _gsDraftTimer = null;

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
        // Publicado - o destino já foi gravado no banco (GeoServerBridge._on_publish_done),
        // então o rascunho local não faz mais sentido aqui.
        gsBridge.clear_draft();
        // Leva o usuário direto pra Distribuição já com WMS+WFS vinculados e a miniatura
        // gerada (_applyPendingGsDistLayerIfAny, em geonetwork.js, roda assim que o
        // formulário do editor terminar de carregar pra essa camada).
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
    gsBridge.gs_destination_saved.connect(function (dbOk) {
        if (dbOk) {
            Modal.alert('Workspace/datastore/nome/título/resumo/palavras-chave gravados no banco - você pode continuar preenchendo depois, mesmo sem publicar ainda.', 'Salvo', 'success');
        } else {
            Modal.alert('Rascunho salvo localmente nesta máquina, mas não deu pra gravar no banco agora (a coluna geoserver_publish_xml pode ainda não existir nesse ambiente).', 'Salvo (local)', 'info');
        }
    });
}

// Chamado por onPanelLoaded() (app.js) quando o painel "geoserver" acabou de carregar.
function _onGeoServerPanelLoaded() {
    if (!document.getElementById('gs-layer-card')) return;
    _gsKeywords = [];
    _renderGsKeywords();
    var destinoBtn = document.querySelector('.tab-link[onclick*="gs-destino"]');
    showTab('gs-destino', destinoBtn);
    _wireGsDraftListeners();
    _loadGsWorkspaces();
    // Rascunho local primeiro (rápido, arquivo local) - só depois dele resolver é que
    // _loadGsLayerInfo() roda, pra "destino salvo no banco" (info.saved_*) só entrar como
    // fallback quando o rascunho NÃO tinha workspace/datastore, nunca por cima dele.
    _loadGsDraft(function () {
        _loadGsLayerInfo();
    });
}

// ─── Rascunho local (workspace/datastore/nome/título/resumo/palavras-chave) ────
// Arquivo próprio do GS (gsBridge.save_draft/load_draft) - não usa o rascunho do editor
// GN, que é sobre o metadado MGB, não sobre onde/como publicar no GeoServer.

function _wireGsDraftListeners() {
    var panelEl = document.querySelector('.geoserver-panel');
    if (panelEl && !panelEl.hasAttribute('data-gs-draft-listener')) {
        panelEl.addEventListener('input', _scheduleGsDraftSave);
        panelEl.addEventListener('change', _scheduleGsDraftSave);
        panelEl.setAttribute('data-gs-draft-listener', 'true');
    }
}

function _scheduleGsDraftSave() {
    clearTimeout(_gsDraftTimer);
    _gsDraftTimer = setTimeout(_saveGsDraftNow, 1500);
}

// Chamado pelo debounce (1.5s) e também na hora, sem esperar, ao trocar de painel
// (_onGsBeforePanelUnload) - evita perder até 1.5s de digitação numa troca rápida.
function _saveGsDraftNow() {
    clearTimeout(_gsDraftTimer);
    if (!document.getElementById('gs-layer-card')) return; // painel não existe mais
    var wsEl = document.getElementById('gs-workspace');
    var dsEl = document.getElementById('gs-datastore');
    var nameEl = document.getElementById('gs-layer-name');
    var titleEl = document.getElementById('gs-layer-title');
    var abstractEl = document.getElementById('gs-layer-abstract');
    var d = {
        workspace: wsEl ? wsEl.value : '',
        datastore: dsEl ? dsEl.value : '',
        published_name: nameEl ? nameEl.value.trim() : '',
        title: titleEl ? titleEl.value.trim() : '',
        abstract: abstractEl ? abstractEl.value.trim() : '',
        keywords: _gsKeywords.slice()
    };
    var hasContent = d.workspace || d.datastore || d.published_name || d.title || d.abstract || d.keywords.length;
    if (!hasContent) return; // não sobrescreve o arquivo com formulário vazio
    gsBridge.save_draft(JSON.stringify(d));
}

// Chamado por loadPanel() (app.js) antes de trocar o HTML do painel - nome distinto de
// _onBeforePanelUnload (GN) de propósito, mesmo escopo global (mesmo motivo de
// _onGsActiveLayerChanged vs _onActiveLayerChanged, já resolvido antes nesta sessão).
function _onGsBeforePanelUnload() {
    if (document.getElementById('gs-layer-card')) {
        _saveGsDraftNow();
    }
}

function _loadGsDraft(callback) {
    _gsDraftHasWorkspace = false;
    if (typeof gsBridge === 'undefined') { if (callback) callback(); return; }
    gsBridge.load_draft(function (draft) {
        if (draft) {
            var nameEl = document.getElementById('gs-layer-name');
            if (nameEl && draft.published_name) {
                nameEl.value = draft.published_name;
                onGsLayerNameInput(draft.published_name);
            }
            var titleEl = document.getElementById('gs-layer-title');
            if (titleEl && draft.title) titleEl.value = draft.title;
            var abstractEl = document.getElementById('gs-layer-abstract');
            if (abstractEl && draft.abstract) abstractEl.value = draft.abstract;
            if (draft.keywords && draft.keywords.length) {
                _gsKeywords = draft.keywords.slice();
                _renderGsKeywords();
            }
            if (draft.workspace) {
                _gsDraftHasWorkspace = true;
                _gsQueueWorkspaceDatastore(draft.workspace, draft.datastore);
            }
        }
        if (callback) callback();
    });
}

// Seleciona workspace/datastore assim que possível: na hora, se a lista de workspaces já
// carregou (clica no item do custom-select, disparando onGsWorkspaceChange normalmente);
// senão enfileira em _gsPendingDraftWorkspace pra _renderGsWorkspaces() aplicar depois.
// Usado tanto pelo rascunho local quanto pelo destino salvo no banco (info.saved_*).
function _gsQueueWorkspaceDatastore(workspace, datastore) {
    if (!workspace) return;
    var wsSelect = document.getElementById('gs-workspace');
    var alreadyPopulated = wsSelect && wsSelect.options.length > 1;
    _gsPendingAutoDatastore = datastore || null;
    if (alreadyPopulated) {
        if (!_clickGsSuggestionItem('gs-workspace-wrap', workspace)) {
            _gsPendingAutoDatastore = null;
        }
    } else {
        _gsPendingDraftWorkspace = workspace;
    }
}

// Chamado por app.js quando a camada ativa do QGIS muda (bridge.layer_changed). Nome
// distinto de _onActiveLayerChanged (GN) de propósito - as duas funções coexistem no
// mesmo escopo global e uma declaração igual sobrescreveria a outra silenciosamente.
function _onGsActiveLayerChanged() {
    if (!document.getElementById('gs-layer-card')) return;
    // Rascunho/nome/título/resumo/palavras-chave são por camada - limpa antes de trocar,
    // senão o que foi digitado pra camada anterior vazaria pra essa (mesmo espírito de
    // resetEditorForm() no editor GN antes de _loadFormForLayer).
    _gsKeywords = [];
    _renderGsKeywords();
    var nameEl = document.getElementById('gs-layer-name');
    if (nameEl) { nameEl.value = ''; nameEl.dataset.sanitized = ''; }
    var titleEl = document.getElementById('gs-layer-title');
    if (titleEl) titleEl.value = '';
    var abstractEl = document.getElementById('gs-layer-abstract');
    if (abstractEl) abstractEl.value = '';
    var preview = document.getElementById('gs-layer-name-preview');
    if (preview) preview.textContent = '';
    _clickGsSuggestionItem('gs-workspace-wrap', ''); // volta workspace/datastore pra "Selecione..."
    _loadGsDraft(function () {
        _loadGsLayerInfo();
    });
}

function _loadGsLayerInfo() {
    var card = document.getElementById('gs-layer-card');
    if (!card) return;
    card.innerHTML = '<span class="gs-status-text">Detectando camada ativa...</span>';
    _setGsTableCheck(null, ''); // camada mudou - qualquer checagem de tabela anterior não vale mais
    _setGsPullGnButtonState(false);
    // Dica de uuid do GN: usada como fallback quando a busca local (banco/sidecar) não
    // encontra nada - ex.: tabela auxiliar do plugin ainda não existe nesse banco (ver
    // docs_projeto/bugs.md, Bug 1). Só usa se o editor GN já confirmou sync pra ESSA
    // mesma camada nesta sessão (_gnSyncUuidLayerName, em geonetwork.js) - senão manda
    // vazio, pra não arriscar puxar o uuid de outra camada.
    var uuidHint = (window._gnSyncUuidLayerName === _activeLayerName && window._gnSyncUuid) ? window._gnSyncUuid : '';
    gsBridge.get_active_layer_publish_info(uuidHint, function (info) {
        _gsLayerInfo = info;
        _renderGsLayerCard(info);
    });
}

function _renderGsLayerCard(info) {
    var card = document.getElementById('gs-layer-card');
    if (!card) return; // painel já foi trocado

    if (!info || !info.publishable) {
        card.innerHTML = '<span class="gs-status-text gs-warning-text">' + escHtml((info && info.reason) || 'Nenhuma camada ativa suportada.') + '</span>';
        _updateGsPublishButton();
        return;
    }

    card.innerHTML =
        '<div class="gs-layer-detected-row">' +
        '<span class="gs-layer-badge">PostgreSQL</span>' +
        '<div class="gs-layer-detected-info">' +
        '<span class="gs-layer-detected-name">' + escHtml(info.name) + '</span>' +
        '<small class="gs-layer-detected-schema">' + escHtml(info.schema) + '.' + escHtml(info.table) + '</small>' +
        '</div></div>';

    // "if vazio" - se o rascunho local (_loadGsDraft, chamado ANTES desta função) já
    // preencheu, não mexe; senão cai pro destino salvo no banco (última publicação) e,
    // faltando isso também, pro nome puro da camada/título do metadado.
    var nameEl = document.getElementById('gs-layer-name');
    if (nameEl && !nameEl.value) {
        var defaultName = info.saved_published_name || info.name;
        nameEl.value = defaultName;
        onGsLayerNameInput(defaultName);
    }
    var titleEl = document.getElementById('gs-layer-title');
    if (titleEl && !titleEl.value) {
        titleEl.value = info.saved_title || info.title || info.name;
    }
    if (!_gsDraftHasWorkspace && info.saved_workspace) {
        _gsQueueWorkspaceDatastore(info.saved_workspace, info.saved_datastore);
    }
    _setGsPullGnButtonState(!!(info.abstract || (info.keywords && info.keywords.length)));
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

    // Workspace pendente (rascunho local ou destino salvo, ver _gsQueueWorkspaceDatastore)
    // que chegou antes da lista terminar de carregar - seleciona em vez de resetar pra vazio.
    if (_gsPendingDraftWorkspace) {
        var target = _gsPendingDraftWorkspace;
        _gsPendingDraftWorkspace = null;
        if ((workspaces || []).indexOf(target) !== -1) {
            _clickGsSuggestionItem('gs-workspace-wrap', target);
            return;
        }
        _gsPendingAutoDatastore = null; // workspace salvo não existe mais - datastore pendente também não faz sentido
    }
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

// ─── Resumo (puxar do GN) e palavras-chave (aba Identificação) ─────────────────

function _setGsPullGnButtonState(hasData) {
    var btn = document.getElementById('gs-pull-gn-btn');
    if (!btn) return;
    btn.disabled = !hasData;
    btn.title = hasData ? '' : 'Nenhum resumo/palavra-chave encontrado (nem rascunho local, nem salvo, nem publicado no GeoNetwork) para esta camada.';
}

// Apesar do nome (mantido pelo botão "Puxar do GeoNetwork"), a fonte real é a que o
// Python decidir que é a melhor disponível - rascunho local do editor GN (funciona
// offline, sem login) > metadado salvo (banco/sidecar) > GeoNetwork publicado (ver
// GeoServerBridge._load_layer_metadata). Cobre o fluxo de preencher tudo antes de logar.
function pullGsAbstractKeywordsFromGn() {
    if (!_gsLayerInfo) return;
    var abstractEl = document.getElementById('gs-layer-abstract');
    var titleEl = document.getElementById('gs-layer-title');
    var hasSourceData = !!(_gsLayerInfo.abstract || (_gsLayerInfo.keywords && _gsLayerInfo.keywords.length));
    if (!hasSourceData) {
        Modal.alert('Nenhum metadado encontrado (rascunho local, salvo ou no GeoNetwork) para esta camada.', 'Aviso', 'warning');
        return;
    }
    var hasCurrentContent = !!((abstractEl && abstractEl.value.trim()) || _gsKeywords.length);
    var apply = function () {
        if (abstractEl) abstractEl.value = _gsLayerInfo.abstract || '';
        if (titleEl) titleEl.value = _gsLayerInfo.title || _gsLayerInfo.name || '';
        _gsKeywords = (_gsLayerInfo.keywords || []).slice();
        _renderGsKeywords();
        // Preenchimento programático não dispara input/change (o que aciona o rascunho por
        // debounce) - sem isso, o rascunho antigo (de antes do pull) ficava no arquivo e
        // "revertia" o que acabou de ser puxado na próxima vez que o painel abrisse.
        _saveGsDraftNow();
    };
    if (hasCurrentContent) {
        Modal.confirm('Isso vai substituir o título/resumo/palavras-chave já preenchidos aqui pelos do GeoNetwork. Continuar?', apply, 'Puxar do GeoNetwork');
    } else {
        apply();
    }
}

function gsAddKeyword() {
    var inp = document.getElementById('gs-kw-input');
    if (!inp) return;
    var val = inp.value.trim();
    if (!val) { inp.value = ''; return; }
    val = val.charAt(0).toUpperCase() + val.slice(1);
    if (_gsKeywords.indexOf(val) !== -1) { inp.value = ''; return; }
    _gsKeywords.push(val);
    inp.value = '';
    _renderGsKeywords();
    _scheduleGsDraftSave(); // clique no botão "+" não dispara input/change - agenda na mão
}

function gsRemoveKeyword(i) {
    _gsKeywords.splice(i, 1);
    _renderGsKeywords();
    _scheduleGsDraftSave(); // clique no "×" do chip não dispara input/change - agenda na mão
}

function _renderGsKeywords() {
    var box = document.getElementById('gs-keyword-chips');
    if (!box) return;
    box.innerHTML = _gsKeywords.map(function (kw, i) {
        return '<span class="keyword-chip">' + escHtml(kw) +
            '<button onclick="gsRemoveKeyword(' + i + ')" data-title="Remover">×</button></span>';
    }).join('');
}

// Junta o que está de fato nos campos da tela agora (editáveis - podem ter sido
// preenchidos via rascunho, "Puxar do GeoNetwork" ou digitados à mão). Usado tanto por
// confirmGsPublish() quanto por saveGsDraftNow() ("Continuar Depois"), pra não duplicar
// a leitura dos mesmos campos em dois lugares.
function _gsCollectFormState() {
    var ws = document.getElementById('gs-workspace');
    var ds = document.getElementById('gs-datastore');
    var nameEl = document.getElementById('gs-layer-name');
    var titleEl = document.getElementById('gs-layer-title');
    var abstractEl = document.getElementById('gs-layer-abstract');
    var publishedName = nameEl ? (nameEl.dataset.sanitized || nameEl.value.trim()) : '';
    return {
        workspace: ws ? ws.value : '',
        datastore: ds ? ds.value : '',
        published_name: publishedName,
        title: (titleEl && titleEl.value.trim()) || publishedName,
        abstract: (abstractEl && abstractEl.value.trim()) || '',
        keywords: _gsKeywords.slice()
    };
}

// Chamado por tryPublishGeoServerLayer() (Serviços > Publicar Camada, ver app.js/
// main.html) - esse painel não tem mais botão próprio de publicar (é o "editor de
// camada", igual o Editor de Metadados não tem botão de publicar dentro dele), então
// valida e avisa por toast em vez de só desabilitar um botão que não existe mais.
function confirmGsPublish() {
    if (!_gsLayerInfo || !_gsLayerInfo.publishable) {
        Modal.alert((_gsLayerInfo && _gsLayerInfo.reason) || 'Nenhuma camada publicável ativa no QGIS.', 'Aviso', 'warning');
        return;
    }
    var d = _gsCollectFormState();
    if (!d.workspace || !d.datastore) {
        Modal.alert('Escolha o Workspace e o Datastore (aba Destino) antes de publicar.', 'Aviso', 'warning');
        return;
    }
    if (!d.published_name) {
        Modal.alert('Preencha o Nome da camada publicada (aba Identificação) antes de publicar.', 'Aviso', 'warning');
        return;
    }
    if (_gsTableCheckState === false) {
        Modal.alert('A tabela "' + escHtml(_gsLayerInfo.table) + '" não foi encontrada nesse datastore. Confira o Workspace/Datastore escolhidos (aba Destino) antes de publicar.', 'Aviso', 'warning');
        return;
    }

    Modal.confirm(
        'Publicar a camada "' + escHtml(_gsLayerInfo.name) + '" como "' + escHtml(d.published_name) +
        '" no workspace "' + escHtml(d.workspace) + '" (datastore "' + escHtml(d.datastore) + '")?',
        function () {
            _gsLastPublishWorkspace = d.workspace;
            _showActionLoading('Publicando no GeoServer...');
            gsBridge.publish_layer(d.workspace, d.datastore, d.published_name, d.title, d.abstract, d.keywords);
        },
        'Confirmar Publicação'
    );
}

// "Serviços > Publicar Camada" (main.html) - mesmo padrão de tryExportGeohab() (GN,
// "Catálogo > Publicar Metadado"): só funciona com o painel já aberto; senão, avisa pra
// abrir "Configurar Camada" primeiro em vez de navegar sozinho (usuário decide quando
// quer ver a tela, igual o editor de metadado não abre nada sozinho).
function tryPublishGeoServerLayer() {
    if (!document.getElementById('gs-layer-card')) {
        Modal.alert('Abra "Serviços > Configurar Camada" antes de publicar.', 'Ação Necessária', 'warning');
        return;
    }
    confirmGsPublish();
}

// "Continuar Depois" do painel GeoServer: grava o destino atual no banco (geoserver_
// publish_xml) SEM publicar de verdade - só exige o Workspace preenchido (bem menos
// restritivo que confirmGsPublish(), que exige tudo + a checagem de tabela).
function saveGsDraftNow() {
    if (!_gsLayerInfo || !_gsLayerInfo.publishable) {
        Modal.alert('Nenhuma camada publicável no painel GeoServer agora.', 'Aviso', 'warning');
        return;
    }
    var d = _gsCollectFormState();
    if (!d.workspace) {
        Modal.alert('Escolha ao menos o Workspace antes de "Continuar Depois".', 'Aviso', 'warning');
        return;
    }
    // Mesmo padrão de confirmação do editor GN (_tryGnSaveMetadata) - "Continuar Depois"
    // sempre pergunta antes de gravar no banco, nos dois domínios.
    Modal.confirm(
        'Deseja realmente salvar o destino de publicação (workspace/datastore/nome/título/' +
        'resumo/palavras-chave) no banco de dados? Isso não publica a camada no GeoServer ainda.',
        function () {
            _saveGsDraftNow(); // garante que o rascunho local (arquivo) também está com o mais recente
            gsBridge.save_destination_now(d.workspace, d.datastore, d.published_name, d.title, d.abstract, d.keywords);
        },
        'Confirmar Salvamento'
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
    var btn = document.querySelector('.gs-autodetect-btn');
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
    var btn = document.querySelector('.gs-autodetect-btn');
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
