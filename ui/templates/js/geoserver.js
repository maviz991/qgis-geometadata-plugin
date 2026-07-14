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
var _gsDbHasWorkspace = false; // true se o destino salvo no banco (info.saved_workspace) já resolveu - evita o rascunho local pisar em cima (prioridade: banco > rascunho local)
var _gsKeywords = []; // estado das palavras-chave da aba Identificação (namespaced pra não colidir com `keywords` do editor GN, mesmo escopo global)
var _gsDraftTimer = null;
var _gsWorkspaceListFailed = false; // true = list_workspaces() já respondeu com erro (tipicamente sem sessão) - ver _gsQueueWorkspaceDatastore/_gsApplyKnownWorkspaceDatastore

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
        _gsSyncHasRecord = true;
        _gsSyncSnapshot = JSON.stringify(_gsCollectFormState());
        _gsSyncIsPublished = true; // publicação de verdade - GeoServer já tem isso
        setGsBadge((_isLogged ? 'sys' : 'db') + '_synced');
        // Invalida o cache do status GS no badge combinado do editor (ver
        // _gsLastCheckedLayerKey, geonetwork.js) - senão, ao navegar pro editor logo em
        // seguida, ele reaproveitaria um resultado de ANTES da publicação (< 60s de cache).
        _gsLastCheckedLayerKey = null;
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
            _gsSyncHasRecord = true;
            _gsSyncSnapshot = JSON.stringify(_gsCollectFormState());
            _gsSyncIsPublished = false; // "Continuar Depois" salva no banco, mas o GeoServer ainda não sabe disso
            var tierPrefix = _isLogged ? 'sys' : 'db';
            setGsBadge(tierPrefix + '_synced');
            _gsLastCheckedLayerKey = null; // idem publish_done acima - invalida o cache do badge combinado do editor
            Modal.alert('Workspace/datastore/nome/título/resumo/palavras-chave gravados no banco.<br><br>Isso ainda NÃO foi publicado no GeoServer - publique em "Serviços > Publicar Camada" quando quiser que valha lá.', tierPrefix === 'sys' ? 'Sincronizado' : 'Sincronizado (DB)', 'warning');
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
    // Prioridade de preenchimento: online (GN, dentro de info.title/abstract/keywords já
    // resolvido no lado Python) > banco (info.saved_*, get_active_layer_publish_info) >
    // rascunho local - nessa ordem, independente de estar logado ou não (o banco só
    // depende da credencial da própria camada, não de sessão GeoServer/GeoNetwork). Por
    // isso _loadGsLayerInfo() roda primeiro e só depois _loadGsDraft() entra, preenchendo
    // apenas os campos que o banco deixou vazios (camada nunca salva/publicada de verdade).
    _loadGsLayerInfo(function () {
        _loadGsDraft();
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
        panelEl.addEventListener('input', _gsOnFieldChanged);
        panelEl.addEventListener('change', _gsOnFieldChanged);
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

// Roda DEPOIS de _loadGsLayerInfo()/_renderGsLayerCard() - só preenche o que o banco
// (info.saved_*) deixou vazio ("if vazio", mesma lógica de antes, só que agora o banco é
// quem tem prioridade e o rascunho é o último recurso, não o primeiro).
function _loadGsDraft(callback) {
    if (typeof gsBridge === 'undefined') { if (callback) callback(); return; }
    gsBridge.load_draft(function (draft) {
        if (draft) {
            var nameEl = document.getElementById('gs-layer-name');
            if (nameEl && !nameEl.value && draft.published_name) {
                nameEl.value = draft.published_name;
                onGsLayerNameInput(draft.published_name);
            }
            var titleEl = document.getElementById('gs-layer-title');
            if (titleEl && !titleEl.value && draft.title) titleEl.value = draft.title;
            var abstractEl = document.getElementById('gs-layer-abstract');
            if (abstractEl && !abstractEl.value && draft.abstract) abstractEl.value = draft.abstract;
            if (!_gsKeywords.length && draft.keywords && draft.keywords.length) {
                _gsKeywords = draft.keywords.slice();
                _renderGsKeywords();
            }
            if (!_gsDbHasWorkspace && draft.workspace) {
                _gsQueueWorkspaceDatastore(draft.workspace, draft.datastore);
            }
            // O rascunho pode ter preenchido campos que o banco deixou vazios (camada
            // nunca salva de verdade) - reavalia o badge (_gsSyncSnapshot já é o estado
            // "vazio" nesse caso, ver _renderGsLayerCard, então isso vira "Modificado").
            _markGsModifiedIfNeeded();
            updateGsFormProgress();
        }
        if (callback) callback();
    });
}

// Seleciona workspace/datastore assim que possível: na hora, se a lista de workspaces já
// carregou (clica no item do custom-select, disparando onGsWorkspaceChange normalmente);
// se a lista já FALHOU (sem sessão, ver _gsWorkspaceListFailed), aplica o valor conhecido
// direto, sem esperar - nada mais vai chamar essa lista de novo; senão enfileira em
// _gsPendingDraftWorkspace pra _renderGsWorkspaces() aplicar quando a resposta chegar (com
// sucesso ou erro). Usado tanto pelo rascunho local quanto pelo destino salvo no banco
// (info.saved_*) - get_active_layer_publish_info e list_workspaces() são duas chamadas
// assíncronas independentes, então essa função pode rodar ANTES ou DEPOIS da lista
// resolver, nessa ordem ou na outra.
function _gsQueueWorkspaceDatastore(workspace, datastore) {
    if (!workspace) return;
    if (_gsWorkspaceListFailed) {
        _gsApplyKnownWorkspaceDatastore(workspace, datastore);
        return;
    }
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

// Preserva um workspace/datastore já conhecido (banco ou rascunho) como única opção do
// select, sem depender da lista completa (REST do GeoServer) ter carregado - usado quando
// a lista já falhou (sem sessão) ou falha DEPOIS dessa camada já ter enfileirado um valor
// conhecido (ver _gsQueueWorkspaceDatastore/_renderGsWorkspaces, as duas ordens de corrida
// possíveis entre list_workspaces() e get_active_layer_publish_info()). Sem isso, o campo
// ficava vazio enquanto o snapshot de comparação tinha o valor real salvo no banco - e o
// badge acusava "Modificado (DB)" à toa numa camada que não mudou nada.
function _gsApplyKnownWorkspaceDatastore(workspace, datastore) {
    var wrap = document.getElementById('gs-workspace-wrap');
    if (!wrap) return;
    wrap.innerHTML = '<select id="gs-workspace" onchange="onGsWorkspaceChange(this.value)">' +
        '<option value="' + escHtml(workspace) + '" selected>' + escHtml(workspace) + '</option></select>';
    var dsWrap = document.getElementById('gs-datastore-wrap');
    if (dsWrap) {
        dsWrap.innerHTML = datastore
            ? '<select id="gs-datastore" onchange="onGsDatastoreChange(this.value)"><option value="' + escHtml(datastore) + '" selected>' + escHtml(datastore) + '</option></select>'
            : '<select id="gs-datastore" onchange="onGsDatastoreChange(this.value)" disabled><option value="">Selecione um workspace primeiro</option></select>';
    }
    initCustomSelects();
    _updateGsPublishButton();
    _markGsModifiedIfNeeded();
    updateGsFormProgress();
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
    var badge = document.getElementById('gs-sync-badge');
    if (badge) badge.style.display = 'none';
    _gsSyncSnapshot = null;
    _clickGsSuggestionItem('gs-workspace-wrap', ''); // volta workspace/datastore pra "Selecione..."
    _loadGsLayerInfo(function () {
        _loadGsDraft();
    });
}

// Chamado por tryResetForm() (app.js - dispatcher genérico do menu Arquivo > Descartar
// Alterações, que decide entre isso e _tryGnResetForm conforme o painel aberto). Descarta
// o rascunho local (arquivo) e qualquer edição não salva, voltando o formulário pro que
// está de fato salvo no banco (ou vazio/auto-preenchido, se a camada nunca foi salva) -
// mesmo reset de campos de _onGsActiveLayerChanged acima, só que sem chamar _loadGsDraft()
// depois (é justamente o rascunho que está sendo descartado aqui).
function tryGsResetForm() {
    if (!document.getElementById('gs-layer-card')) return;
    if (!_gsLayerInfo || !_gsLayerInfo.publishable) {
        Modal.alert('Nenhuma camada publicável no painel GeoServer agora.', 'Aviso', 'warning');
        return;
    }
    Modal.confirm(
        'Isso vai descartar as alterações não salvas do destino de publicação (workspace/datastore/nome/título/resumo/palavras-chave). Continuar?',
        function () {
            if (typeof gsBridge !== 'undefined') gsBridge.clear_draft();
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
            _loadGsLayerInfo(function () { updateGsFormProgress(); }); // recarrega do banco (ou vazio) - sem rascunho
        },
        'Descartar Alterações'
    );
}

function _loadGsLayerInfo(callback) {
    var card = document.getElementById('gs-layer-card');
    if (!card) return;
    card.innerHTML = '<span class="gs-status-text">Detectando camada ativa...</span>';
    _setGsTableCheck(null, ''); // camada mudou - qualquer checagem de tabela anterior não vale mais
    _setGsPullGnButtonState(false);
    var badge = document.getElementById('gs-sync-badge');
    if (badge) badge.style.display = 'none';
    _gsSyncSnapshot = null;
    _gsDbHasWorkspace = false;
    updateGsFormProgress();
    // Dica de uuid do GN: usada como fallback quando a busca local (banco/sidecar) não
    // encontra nada - ex.: tabela auxiliar do plugin ainda não existe nesse banco (ver
    // docs_projeto/bugs.md, Bug 1). Só usa se o editor GN já confirmou sync pra ESSA
    // mesma camada nesta sessão (_gnSyncUuidLayerName, em geonetwork.js) - senão manda
    // vazio, pra não arriscar puxar o uuid de outra camada.
    var uuidHint = (window._gnSyncUuidLayerName === _activeLayerName && window._gnSyncUuid) ? window._gnSyncUuid : '';
    gsBridge.get_active_layer_publish_info(uuidHint, function (info) {
        _gsLayerInfo = info;
        _renderGsLayerCard(info);
        if (callback) callback();
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

    // Prioridade: banco (info.saved_*, última publicação/salvamento de verdade) primeiro -
    // esta função roda ANTES de _loadGsDraft(), que só entra depois preenchendo o que
    // ainda sobrar vazio. Faltando também o banco, cai pro nome puro da camada/título do
    // metadado (info.title, que já veio do GN online quando disponível - ver
    // GeoServerBridge._load_layer_metadata).
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
    // Resumo/palavras-chave salvos (info.saved_*) também precisam entrar aqui, senão o
    // formulário fica incompleto em relação ao que está no banco - e o badge de status
    // (abaixo) acusava "Modificado" à toa numa camada já publicada, só porque esses dois
    // campos ficavam vazios enquanto o snapshot de comparação tinha os valores reais.
    var abstractEl = document.getElementById('gs-layer-abstract');
    if (abstractEl && !abstractEl.value && info.saved_abstract) {
        abstractEl.value = info.saved_abstract;
    }
    if (!_gsKeywords.length && info.saved_keywords && info.saved_keywords.length) {
        _gsKeywords = info.saved_keywords.slice();
        _renderGsKeywords();
    }
    _gsDbHasWorkspace = !!info.saved_workspace;
    if (info.saved_workspace) {
        _gsQueueWorkspaceDatastore(info.saved_workspace, info.saved_datastore);
    }
    _setGsPullGnButtonState(!!(info.abstract || (info.keywords && info.keywords.length)));
    _updateGsPublishButton();

    // Badge de status: compara o formulário atual contra o que está salvo no banco (ou,
    // se nada foi salvo ainda, contra o estado JÁ COM os defaults de auto-preenchimento
    // aplicados acima - nome/título/resumo/palavras-chave puxados de info.name/info.title/
    // etc. NÃO contam como "modificado", só divergir DESSES valores conta. Usar um
    // snapshot vazio aqui era o bug: comparava contra {} enquanto o formulário já tinha
    // esses defaults, então toda camada nunca salva no banco aparecia como "Modificado"
    // por causa só do auto-preenchimento, mesmo sem o usuário ter digitado nada). Se o
    // workspace/datastore ainda estão sendo selecionados de forma assíncrona (fila em
    // _gsQueueWorkspaceDatastore), o "change" disparado por essa seleção reavalia de novo
    // via _gsOnFieldChanged - não precisa esperar aqui.
    _gsSyncHasRecord = !!info.saved_workspace;
    _gsSyncSnapshot = _gsSyncHasRecord ? _gsSnapshotFromSaved(info) : JSON.stringify(_gsCollectFormState());
    _gsSyncIsPublished = !!info.saved_published;
    _checkGsSyncNow();
    updateGsFormProgress();

    // Nível sistema de verdade: o badge (checagem acima) só compara contra o BANCO
    // (geoserver_publish_xml), que registra apenas a última publicação/salvamento - se o
    // usuário editou o resumo e só clicou "Continuar Depois" (sem republicar), o banco
    // bate com o formulário mas o GeoServer AO VIVO continua com o conteúdo antigo. Só
    // logado dá pra confirmar isso de verdade (REST do GeoServer, ver check_gs_sync) -
    // atualiza o badge/snapshot com o resultado quando terminar.
    _checkGsSyncOnline(info);
}

function _loadGsWorkspaces() {
    var wrap = document.getElementById('gs-workspace-wrap');
    if (!wrap) return;
    _gsWorkspaceListFailed = false;
    wrap.innerHTML = '<select id="gs-workspace" onchange="onGsWorkspaceChange(this.value)"><option value="">Carregando...</option></select>';
    gsBridge.list_workspaces();
}

function _renderGsWorkspaces(workspaces, error) {
    var wrap = document.getElementById('gs-workspace-wrap');
    if (!wrap) return; // painel já foi trocado
    if (error) {
        // Sem sessão, a REST API do GeoServer nem deixa listar workspaces (ver
        // GeoServerService.list_workspaces - exige api_session). Se já sabemos o
        // workspace/datastore salvo no banco ou vindo do rascunho pra essa camada
        // (_gsPendingDraftWorkspace/_gsPendingAutoDatastore, ver _gsQueueWorkspaceDatastore),
        // preserva os dois em vez de deixar os campos vazios (senão o formulário
        // "esquecia" o destino já salvo e o badge acusava "Modificado (DB)" à toa).
        // _gsWorkspaceListFailed cobre a corrida em que get_active_layer_publish_info
        // ainda não tinha resolvido nesse momento - _gsQueueWorkspaceDatastore aplica na
        // hora quando ela resolver depois, em vez de enfileirar pra ninguém consumir.
        _gsWorkspaceListFailed = true;
        if (_gsPendingDraftWorkspace) {
            var knownWs = _gsPendingDraftWorkspace;
            var knownDs = _gsPendingAutoDatastore;
            _gsPendingDraftWorkspace = null;
            _gsPendingAutoDatastore = null;
            _gsApplyKnownWorkspaceDatastore(knownWs, knownDs);
        } else {
            wrap.innerHTML = '<select id="gs-workspace"><option value="">Erro ao carregar workspaces</option></select>';
        }
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
        // Mesma lógica de _renderGsWorkspaces acima: preserva o datastore já
        // conhecido (salvo no banco ou rascunho) em vez de deixar o campo vazio e
        // gerar um falso "Modificado (DB)".
        if (_gsPendingAutoDatastore) {
            var knownDs = _gsPendingAutoDatastore;
            _gsPendingAutoDatastore = null;
            dsWrap.innerHTML = '<select id="gs-datastore" onchange="onGsDatastoreChange(this.value)">' +
                '<option value="' + escHtml(knownDs) + '" selected>' + escHtml(knownDs) + '</option></select>';
            initCustomSelects();
            _updateGsPublishButton();
            _markGsModifiedIfNeeded();
            updateGsFormProgress();
        } else {
            dsWrap.innerHTML = '<select id="gs-datastore"><option value="">Erro ao carregar datastores</option></select>';
            initCustomSelects();
        }
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

// ─── Badge de status (Não salvo/Salvo/Modificado/Sincronizado) + progresso ─────────
// Mesmo componente visual e mesma lógica do editor de metadados GN (setGnBadge/
// checkGnSync/updateFormProgress, geonetwork.js) - aqui comparando contra o que está
// salvo em geoserver_publish_xml (info.saved_*) em vez do GeoNetwork. "Sincronizado" só
// quer dizer "o formulário bate com o banco" - publicado de verdade ou só salvo via
// "Continuar Depois" são os dois a mesma cor/rótulo de badge (senão é status virando
// descrição, com um estado só pra essa nuance); a diferença fica no TOOLTIP/toast
// (_gsPublishTooltip, ver setGsBadge/onGsSyncBadgeClick), não no rótulo em si.

var _gsSyncSnapshot = null; // JSON do estado comparado (salvo no banco, salvo AO VIVO se o nível sistema já confirmou - ver _checkGsSyncOnline, ou o estado pós-auto-preenchimento se nada salvo ainda) - null = ainda não checou (layer info não carregou)
var _gsSyncIsPublished = false; // esse snapshot veio de uma publicação de verdade (true) ou só de um "Continuar Depois" (false) - só afeta o tooltip/toast, não o rótulo do badge
var _gsSyncHasRecord = false; // true = existe algo salvo no banco (info.saved_workspace) - falso = _gsSyncSnapshot é o estado pós-auto-preenchimento
var _gsOnlineLastCheckedKey = null; // ver _checkGsSyncOnline - cache por camada+destino, mesmo padrão de _gnLastCheckedLayerKey (geonetwork.js)
var _gsOnlineLastCheckedAt = 0;

// Vocabulário de status compartilhado com o GN (ver _GN_SYNC_LABELS, geonetwork.js) - o
// nível (sys_/db_) reflete só se há sessão ativa (_isLogged) no momento da checagem, já
// que a comparação em si (contra geoserver_publish_xml) não depende de login pra
// funcionar (ver GeoServerService.load_publish_destination).
var _GS_SYNC_LABELS = {
    offline: 'Não salvo',
    db_not_found: 'Não Encontrado (DB)',
    db_synced: 'Sincronizado (DB)',
    db_modified: 'Modificado (DB)',
    sys_not_found: 'Não Encontrado (Geohab)',
    sys_synced: 'Sincronizado',
    sys_modified: 'Modificado'
};

var _GS_SYNC_TOOLTIPS = {
    offline: 'Destino de publicação ainda não salvo em lugar nenhum. Use "Arquivo > Continuar Depois" ou publique pra salvar.',
    db_not_found: 'Nenhum destino de publicação salvo no banco pra esta camada ainda (verificado sem login).',
    db_modified: 'Editado localmente desde o último salvamento no banco (verificado sem login).',
    sys_not_found: 'Nenhum destino de publicação salvo pra esta camada ainda.',
    sys_modified: 'Editado localmente desde o último salvamento/publicação.'
    // db_synced/sys_synced não têm entrada fixa aqui - ver _gsPublishTooltip (o texto
    // muda conforme _gsSyncIsPublished, então é calculado na hora em vez de um dict).
};

var _GS_SYNC_MODALS = {
    offline: { title: 'Não salvo', type: 'info', message: 'Destino de publicação ainda não salvo em lugar nenhum.<br><br>Use "Arquivo > Continuar Depois" pra salvar sem publicar, ou publique direto em "Serviços > Publicar Camada".' },
    db_not_found: { title: 'Não Encontrado (DB)', type: 'info', message: 'Nenhum destino de publicação salvo no banco pra esta camada ainda (verificado sem login).<br><br>Use "Arquivo > Continuar Depois" pra salvar, ou faça login e publique direto em "Serviços > Publicar Camada".' },
    db_modified: { title: 'Modificado (DB)', type: 'warning', message: 'Você tem alterações não salvas (verificado sem login).<br><br>Use "Arquivo > Continuar Depois" pra salvar, ou publique em "Serviços > Publicar Camada" pra sincronizar.' },
    sys_not_found: { title: 'Não Encontrado (Geohab)', type: 'info', message: 'Nenhum destino de publicação salvo pra esta camada ainda.<br><br>Use "Arquivo > Continuar Depois" pra salvar sem publicar, ou publique direto em "Serviços > Publicar Camada".' },
    sys_modified: { title: 'Modificado', type: 'warning', message: 'Você tem alterações não salvas.<br><br>Use "Arquivo > Continuar Depois" pra salvar sem publicar, ou publique em "Serviços > Publicar Camada" pra sincronizar.' }
    // db_synced/sys_synced não têm entrada fixa aqui - ver onGsSyncBadgeClick (a mensagem
    // muda conforme _gsSyncIsPublished, chamando _gsPublishTooltip).
};

// "Sincronizado" cobre dois fatos distintos (bate com o banco; publicado de verdade no
// GeoServer ou não) - o rótulo do badge não distingue os dois (ver comentário acima), mas
// o tooltip/toast precisa deixar claro qual é o caso. Compartilhado com o sufixo GS do
// badge combinado do editor (geonetwork.js, ver checkGsPublishStatus) - por isso recebe
// isPublished como parâmetro em vez de ler _gsSyncIsPublished direto (esse global só
// existe aqui, no painel GS).
function _gsPublishTooltip(tierPrefix, isPublished) {
    var levelNote = tierPrefix === 'sys' ? '' : ' (verificado sem login - o GeoServer pode ter uma versão diferente)';
    return isPublished
        ? ('Essa camada já foi publicada no GeoServer' + levelNote + '.')
        : ('O formulário atual bate com o que está salvo no banco, mas ainda NÃO foi publicado no GeoServer' + levelNote + '. Publique em "Serviços > Publicar Camada" quando quiser que valha lá.');
}

function setGsBadge(state) {
    var badge = document.getElementById('gs-sync-badge');
    var label = document.getElementById('gs-sync-label');
    if (!badge || !label) return;
    badge.className = 'gn-sync-badge ' + state;
    badge.style.display = 'flex';
    badge.dataset.title = (state === 'sys_synced' || state === 'db_synced')
        ? _gsPublishTooltip(state.split('_')[0], _gsSyncIsPublished)
        : (_GS_SYNC_TOOLTIPS[state] || '');
    label.textContent = _GS_SYNC_LABELS[state] || state;
}

function _gsSnapshotFromSaved(info) {
    return JSON.stringify({
        workspace: (info && info.saved_workspace) || '',
        datastore: (info && info.saved_datastore) || '',
        published_name: (info && info.saved_published_name) || '',
        title: (info && info.saved_title) || '',
        abstract: (info && info.saved_abstract) || '',
        keywords: (info && info.saved_keywords) || []
    });
}

// Compara o formulário atual contra o snapshot (salvo no banco, ou o estado pós-auto-
// preenchimento se nada foi salvo ainda - ver _gsSyncHasRecord/_renderGsLayerCard) e
// escolhe o rótulo certo. O nível (sys_/db_) só reflete se há sessão agora (_isLogged) - a
// comparação em si é sempre contra o banco (geoserver_publish_xml), que não depende de
// login (ver load_publish_destination).
function _checkGsSyncNow() {
    if (_gsSyncSnapshot === null) {
        setGsBadge('offline');
        return;
    }
    var tierPrefix = _isLogged ? 'sys' : 'db';
    var current = JSON.stringify(_gsCollectFormState());
    if (current !== _gsSyncSnapshot) {
        setGsBadge(tierPrefix + '_modified');
        return;
    }
    if (!_gsSyncHasRecord) {
        setGsBadge(tierPrefix + '_not_found');
        return;
    }
    setGsBadge(tierPrefix + '_synced'); // publicado ou só salvo via "Continuar Depois" - mesmo rótulo, ver _gsPublishTooltip
}

// Confere ao vivo (REST do GeoServer, via check_gs_sync) se o formulário bate com o que
// está DE FATO publicado agora - não só com o banco (_checkGsSyncNow acima). Só faz
// sentido logado e com destino conhecido (workspace/datastore/nome, ver info.saved_*);
// silenciosamente não faz nada fora disso (o badge fica no nível banco, calculado por
// _checkGsSyncNow). Cacheia por 60s (mesma janela de _GN_RECHECK_STALE_MS, geonetwork.js)
// por camada+destino, pra não bater no GeoServer de novo a cada revisita do painel.
function _checkGsSyncOnline(info) {
    if (!_isLogged || typeof gsBridge === 'undefined' || !gsBridge.check_gs_sync) return;
    if (!info || !info.saved_workspace || !info.saved_datastore || !info.saved_published_name) return;
    var ws = info.saved_workspace, ds = info.saved_datastore, name = info.saved_published_name;
    var key = _activeLayerName + '|' + ws + '|' + ds + '|' + name;
    if (_gsOnlineLastCheckedKey === key && (Date.now() - _gsOnlineLastCheckedAt) < _GN_RECHECK_STALE_MS) return;
    var d = _gsCollectFormState();
    gsBridge.check_gs_sync(ws, ds, name, d.title, d.abstract, d.keywords, function (result) {
        // A camada/destino pode ter trocado enquanto a checagem rodava - só aplica se
        // ainda for a mesma (evita aplicar um resultado velho numa camada errada).
        if (!document.getElementById('gs-layer-card') || !_gsLayerInfo) return;
        if (_gsLayerInfo.saved_workspace !== ws || _gsLayerInfo.saved_datastore !== ds ||
            _gsLayerInfo.saved_published_name !== name) return;

        var state = result && result.state;
        if (state === 'sys_synced') {
            _gsSyncHasRecord = true;
            _gsSyncSnapshot = JSON.stringify(_gsCollectFormState());
            _gsSyncIsPublished = true;
            setGsBadge('sys_synced');
        } else if (state === 'sys_modified') {
            // Diverge do que está DE FATO publicado agora - monta o snapshot a partir do
            // conteúdo AO VIVO (não do banco), pra digitação seguinte (_checkGsSyncNow,
            // local) continuar comparando contra a fonte mais confiável disponível.
            _gsSyncHasRecord = true;
            _gsSyncSnapshot = JSON.stringify({
                workspace: ws, datastore: ds, published_name: name,
                title: result.title || '', abstract: result.abstract || '', keywords: result.keywords || []
            });
            _gsSyncIsPublished = true;
            setGsBadge('sys_modified');
        } else if (state === 'sys_not_found') {
            // O banco achava que estava publicado, mas não existe mais lá (removido, ou
            // nunca chegou a publicar de verdade - só "Continuar Depois").
            _gsSyncHasRecord = false;
            _gsSyncIsPublished = false;
            setGsBadge('sys_not_found');
        }
        // 'error' (rede fora, etc.) - mantém o que _checkGsSyncNow (banco) já mostrou, sem
        // piorar a UX por causa de uma falha de rede momentânea.
        if (state && state !== 'error') {
            _gsOnlineLastCheckedKey = key;
            _gsOnlineLastCheckedAt = Date.now();
        }
        updateGsFormProgress();
    });
}

// Chamado por _onAuthStateChangedForSync (geonetwork.js) quando o login muda de verdade -
// o nível (sys_/db_) do badge do painel GS depende de _isLogged, então recalcula na hora
// (_checkGsSyncNow, local) e, se acabou de logar, dispara também a checagem AO VIVO contra
// o GeoServer de verdade (_checkGsSyncOnline) - sem esse gancho, o usuário logava e o
// badge ficava em "Sincronizado (DB)" até sair e voltar (revisitar) pro painel.
function _onGsAuthStateChangedForSync() {
    if (!document.getElementById('gs-layer-card')) return;
    if (_gsSyncSnapshot !== null) {
        _checkGsSyncNow();
    }
    if (_isLogged) {
        _checkGsSyncOnline(_gsLayerInfo);
    }
    // Se a lista de workspaces/datastores já tinha falhado por falta de sessão
    // (_gsWorkspaceListFailed, ver _renderGsWorkspaces/_gsApplyKnownWorkspaceDatastore) e
    // acabamos de logar, recarrega a lista de verdade agora - preserva o workspace/
    // datastore atualmente selecionados (o valor conhecido vindo do banco/rascunho) pra
    // reaplicar assim que a lista real terminar de carregar, em vez de perder a seleção
    // ou deixar o usuário preso ao valor "só conhecido" mesmo já logado.
    if (_isLogged && _gsWorkspaceListFailed) {
        var wsEl = document.getElementById('gs-workspace');
        var dsEl = document.getElementById('gs-datastore');
        var currentWs = wsEl ? wsEl.value : '';
        var currentDs = dsEl ? dsEl.value : '';
        if (currentWs) {
            _gsPendingDraftWorkspace = currentWs;
            _gsPendingAutoDatastore = currentDs || null;
        }
        _loadGsWorkspaces();
    }
}

// Chamado a cada input/change do formulário (mesmo espírito de _markGnModifiedIfNeeded,
// geonetwork.js) - _checkGsSyncNow já recalcula tudo do zero a cada chamada (mais simples
// que o toggle baseline/modified do GN, que precisa de um snapshot fixo entre chamadas).
function _markGsModifiedIfNeeded() {
    if (_gsSyncSnapshot === null) return;
    _checkGsSyncNow();
}

function onGsSyncBadgeClick() {
    var badge = document.getElementById('gs-sync-badge');
    if (!badge) return;
    var state = badge.className.replace('gn-sync-badge', '').trim();
    if (state === 'sys_synced' || state === 'db_synced') {
        var tierPrefix = state.split('_')[0];
        Modal.alert(
            _gsPublishTooltip(tierPrefix, _gsSyncIsPublished),
            tierPrefix === 'sys' ? 'Sincronizado' : 'Sincronizado (DB)',
            _gsSyncIsPublished ? 'success' : 'warning'
        );
        return;
    }
    var entry = _GS_SYNC_MODALS[state];
    if (!entry) return;
    Modal.alert(entry.message, entry.title, entry.type);
}

// Progresso dos campos "obrigatórios" pra publicar (Workspace/Datastore/Nome) - mesmo
// componente circular do editor GN (updateFormProgress), só com os 3 campos do GS.
function updateGsFormProgress() {
    var d = _gsCollectFormState();
    var required = [d.workspace, d.datastore, d.published_name];
    var filledCount = required.filter(function (v) { return !!v; }).length;
    var pct = Math.round((filledCount / required.length) * 100);

    var spinner = document.getElementById('gs-progress-spinner');
    var text = document.getElementById('gs-progress-text');
    if (spinner && text) {
        spinner.style.setProperty('--progress', pct);
        text.textContent = pct + '%';
        if (pct >= 100) spinner.classList.add('completed');
        else spinner.classList.remove('completed');
    }
}

// Chamado a cada input/change do painel (junto com _scheduleGsDraftSave, ver
// _wireGsDraftListeners) - feedback imediato (não debounced), igual updateFormProgress/
// _markGnModifiedIfNeeded no editor GN.
function _gsOnFieldChanged() {
    _markGsModifiedIfNeeded();
    updateGsFormProgress();
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
