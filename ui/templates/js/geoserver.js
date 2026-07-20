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
var _gsStyleFilePath = ''; // caminho do .sld escolhido (fonte 'file' da aba Estilos) - o conteúdo é relido no Python na hora de publicar/aplicar
var _gsStyleNameTimer = null; // debounce da sanitização do nome do estilo (mesmo padrão de _gsNameTimer)
var _gsPendingExistingStyle = null; // valor ('ws:nome' ou 'nome') a selecionar quando a lista de estilos existentes carregar - mesmo padrão de _gsPendingDraftWorkspace
var _gsDbHasStyle = false; // true se o banco já resolveu o estilo (info.saved_style_source) - evita o rascunho local pisar em cima (prioridade: banco > rascunho, igual _gsDbHasWorkspace)
var _gsLayerInfoInFlightLayer = null; // nome da camada com um get_active_layer_publish_info já pedido, ainda sem resposta - ver _requestGsLayerInfo
var _gsLayerInfoPending = []; // [{expectedLayer, onReady}] - quem pediu get_active_layer_publish_info e ainda espera resposta (ver gs_layer_info_ready, _initGsBridge)

// Pede get_active_layer_publish_info de forma assíncrona (resultado chega pelo sinal
// gs_layer_info_ready, ver _initGsBridge) - dois lugares no app chamam essa mesma info
// (_loadGsLayerInfo aqui e checkGsPublishStatus, geonetwork.js), por isso um registro de
// pendências em vez de currying um callback só por cima do bridge. Evita disparar uma
// SEGUNDA chamada ao Python (e portanto uma segunda ida ao banco) enquanto já existe uma
// em voo pedida pra essa MESMA camada - a resposta única atende os dois pedidos.
function _requestGsLayerInfo(uuidHint, expectedLayer, onReady) {
    _gsLayerInfoPending.push({ expectedLayer: expectedLayer, onReady: onReady });
    if (_gsLayerInfoInFlightLayer === expectedLayer) return;
    _gsLayerInfoInFlightLayer = expectedLayer;
    gsBridge.get_active_layer_publish_info(uuidHint || '');
}

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
        var snapObj = _gsCollectFormState();
        if (message) {
            // Sucesso com `message` = a camada publicou mas o ESTILO falhou - o banco ficou
            // sem os campos de estilo de propósito (ver GeoServerBridge._on_publish_done),
            // então o snapshot também fica sem, pro badge acusar a pendência ("Modificado")
            // em vez de "Sincronizado".
            snapObj.style_source = '';
            snapObj.style_name = '';
        }
        _gsSyncSnapshot = JSON.stringify(snapObj);
        _gsCaptureSnapshotRawNames();
        _gsSyncIsPublished = true; // publicação de verdade - GeoServer já tem isso
        _gsApplyFieldLockState();
        _gsInvalidatePendingLiveCheck(); // ver definição - descarta checagem ao vivo desatualizada de antes da publicação
        _flashGsRefreshBtn(); // ver definição - deixa o botão "↻" visível por uns instantes, momento onde erros de rede mais apareceram nos testes
        if (message) {
            _checkGsSyncNow();
            Modal.alert(message, 'Publicado com Ressalvas', 'warning');
        } else {
            setGsBadge((_isLogged ? 'sys' : 'db') + '_synced');
        }
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
            _gsCaptureSnapshotRawNames();
            _gsSyncIsPublished = false; // "Continuar Depois" salva no banco, mas o GeoServer ainda não sabe disso
            _gsApplyFieldLockState();
            _gsInvalidatePendingLiveCheck(); // ver definição - descarta checagem ao vivo desatualizada de antes do salvamento
            _flashGsRefreshBtn();
            var tierPrefix = _isLogged ? 'sys' : 'db';
            setGsBadge(tierPrefix + '_synced');
            _gsLastCheckedLayerKey = null; // idem publish_done acima - invalida o cache do badge combinado do editor
            Modal.alert('Dados gravados no Banco de dados.<br>A camada não foi publicada no GeoServer - publique em "Serviços > Publicar Camada".', tierPrefix === 'sys' ? 'Sincronizado' : 'Sincronizado (DB)', 'warning');
        } else {
            Modal.alert('Rascunho salvo localmente nesta máquina, mas não deu pra gravar no banco agora.', 'Salvo (local)', 'info');
        }
    });
    // Resultado de check_gs_sync (verificação AO VIVO contra o GeoServer, ver
    // _checkGsSyncOnline) - roda em background no lado Python (QThread, RNF02) e chega por
    // sinal, não por callback direto, já que a chamada de rede não pode travar a UI.
    gsBridge.gs_sync_checked.connect(function (result) {
        _onGsSyncChecked(result);
    });
    // Resultado de get_active_layer_publish_info (banco + potencialmente GeoNetwork, ver
    // _GsActiveLayerInfoWorker) - mesmo motivo do check_gs_sync acima, roda em background
    // agora (antes era síncrono e travava a UI toda vez que o painel GS abria ou a camada
    // mudava). Ver _requestGsLayerInfo - dois lugares pedem essa info (_loadGsLayerInfo,
    // aqui, e checkGsPublishStatus, geonetwork.js), por isso um registro de pendências em
    // vez de um callback só.
    gsBridge.gs_layer_info_ready.connect(function (info) {
        _gsLayerInfoInFlightLayer = null;
        var pending = _gsLayerInfoPending;
        _gsLayerInfoPending = [];
        pending.forEach(function (entry) {
            if (_activeLayerName !== entry.expectedLayer) return; // camada trocou enquanto carregava - resposta obsoleta pra esse pedido
            entry.onReady(info);
        });
    });
    // Lista de estilos existentes (aba Estilos, fonte 'existing') - ver _gsLoadStylesList.
    gsBridge.gs_styles_ready.connect(function (styles, error) {
        _renderGsStyleOptions(styles, error);
    });
    // "Serviços > Atualizar Estilo" (ver tryUpdateGsStyle) - aplica o estilo a uma camada
    // JÁ publicada, sem republicar o FeatureType.
    gsBridge.gs_style_updated.connect(function (success, error) {
        _hideActionLoading();
        if (!success) {
            // Força uma checagem AO VIVO na hora - se a falha foi porque a camada não
            // existe de verdade nesse destino (ver _gs_augment_404, geoserver_workers.py),
            // o badge corrige sozinho pra "Não Encontrado" em vez de ficar preso em
            // "Modificado" até o próximo login/reabertura do painel (a checagem ao vivo,
            // normalmente, só roda nesses dois momentos - ver _checkGsSyncOnline).
            _gsForceLiveRecheck();
            Modal.alert(error || 'Falha ao aplicar o estilo no GeoServer.', 'Erro', 'error');
            return;
        }
        // O bridge já gravou os campos de estilo no registro do banco (quando havia
        // registro) - realinha o snapshot local pro badge não acusar "Modificado" só por
        // causa do estilo recém-aplicado.
        if (_gsLayerInfo) {
            var appliedStyle = _gsCollectFormState();
            _gsLayerInfo.saved_style_source = appliedStyle.style_source;
            _gsLayerInfo.saved_style_name = appliedStyle.style_name;
        }
        _gsInvalidatePendingLiveCheck(); // ver definição - descarta checagem ao vivo desatualizada de antes de aplicar o estilo
        _flashGsRefreshBtn();
        try {
            var snap = JSON.parse(_gsSyncSnapshot);
            var cur = _gsCollectFormState();
            snap.style_source = cur.style_source;
            snap.style_name = cur.style_name;
            _gsSyncSnapshot = JSON.stringify(snap);
            _checkGsSyncNow();
        } catch (e) { /* sem snapshot ainda (null) - nada a realinhar */ }
        Modal.alert('Estilo aplicado como padrão da camada no GeoServer.', 'Estilo Atualizado', 'success');
    });
    // "Serviços > Atualizar Camada" / banner "Atualização disponível" (ver
    // pullGsLayerFromServer) - PULL: busca o que está DE FATO publicado no GeoServer e
    // substitui o formulário local por isso.
    gsBridge.gs_layer_pulled.connect(function (success, data, error) {
        _hideActionLoading();
        if (!success) {
            // Idem gs_style_updated acima - reverifica ao vivo na hora em vez de esperar
            // o próximo login/reabertura do painel.
            _gsForceLiveRecheck();
            Modal.alert(error || 'Falha ao buscar os dados publicados no GeoServer.', 'Erro', 'error');
            return;
        }
        var titleEl = document.getElementById('gs-layer-title');
        var abstractEl = document.getElementById('gs-layer-abstract');
        if (titleEl) titleEl.value = data.title || '';
        if (abstractEl) abstractEl.value = data.abstract || '';
        _gsKeywords = (data.keywords || []).slice();
        _renderGsKeywords();
        // Estilo: só sabemos o NOME do estilo ao vivo (não o corpo SLD), então vira fonte
        // 'existing' - mesmo raciocínio de _on_layer_pulled (bridge). '_gsApplyStyleChoice'
        // com source 'existing'/'none' sempre sobrescreve (sem "if vazio"), o que é o que
        // queremos aqui (usuário já confirmou que quer trazer o servidor por cima).
        if (data.default_style) {
            _gsApplyStyleChoice('existing', data.default_style, data.default_style_workspace || '');
        } else {
            _gsApplyStyleChoice('none', '', '');
        }
        _gsAdditionalStyles = (data.additional_styles || []).map(function (s) {
            return { source: 'existing', mode: 'existing', existing_name: s.name || '', existing_workspace: s.style_workspace || '' };
        });
        _renderGsAdditionalStyles();
        // Preenchimento programático não dispara input/change (o que aciona o rascunho
        // por debounce) - salva na hora, mesmo motivo de pullGsAbstractKeywordsFromGn.
        _saveGsDraftNow();
        _gsSyncHasRecord = true;
        _gsSyncSnapshot = JSON.stringify(_gsCollectFormState());
        _gsCaptureSnapshotRawNames();
        _gsSyncIsPublished = true;
        _gsInvalidatePendingLiveCheck(); // ver definição - senão uma checagem em voo de ANTES do pull chega depois com "Modificado" desatualizado e o banner "Atualização disponível" reaparece
        _flashGsRefreshBtn();
        setGsBadge((_isLogged ? 'sys' : 'db') + '_synced');
        _gsLastCheckedLayerKey = null; // idem publish_done/destination_saved - invalida o cache do badge combinado do editor
        updateGsFormProgress();
        Modal.alert('Formulário atualizado com o que está publicado no GeoServer agora.', 'Camada Atualizada', 'success');
    });
}

// Chamado por onPanelLoaded() (app.js) quando o painel "geoserver" acabou de carregar.
function _onGeoServerPanelLoaded() {
    if (!document.getElementById('gs-layer-card')) return;
    // Skeleton também no carregamento inicial do painel, não só na troca de camada ativa
    // (_onGsActiveLayerChanged) - mesmo raciocínio de _onEditorPanelLoaded (geonetwork.js).
    // _renderGsLayerCard (via _loadGsLayerInfo mais abaixo) remove assim que os dados
    // chegarem, incondicionalmente, mesmo pra camada não publicável.
    _applyGsSkeleton();
    _gsKeywords = [];
    _renderGsKeywords();
    // Estado de estilo é por camada/painel - o HTML recém-carregado já está nos defaults
    // (fonte 'qgis'), só os globais precisam voltar ao zero.
    _gsStyleFilePath = '';
    _gsPendingExistingStyle = null;
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

// - Rascunho local (workspace/datastore/nome/título/resumo/palavras-chave) ────
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
    var styleSrcEl = document.getElementById('gs-style-source');
    var styleNameEl = document.getElementById('gs-style-name');
    var styleExEl = document.getElementById('gs-style-existing');
    var styleFileBtn = document.getElementById('gs-style-file-btn');
    var styleExVal = (styleExEl && styleExEl.value) || '';
    var styleExSep = styleExVal.indexOf(':');
    var d = {
        workspace: wsEl ? wsEl.value : '',
        datastore: dsEl ? dsEl.value : '',
        published_name: nameEl ? nameEl.value.trim() : '',
        title: titleEl ? titleEl.value.trim() : '',
        abstract: abstractEl ? abstractEl.value.trim() : '',
        keywords: _gsKeywords.slice(),
        // Aba Estilos: guarda a ESCOLHA crua (fonte, nome digitado, caminho do arquivo,
        // estilo existente) - o preparo/sanitização acontece na hora de publicar/salvar.
        style_source: styleSrcEl ? styleSrcEl.value : '',
        style_name: styleNameEl ? styleNameEl.value.trim() : '',
        style_file: _gsStyleFilePath,
        style_file_name: (_gsStyleFilePath && styleFileBtn) ? styleFileBtn.textContent : '',
        style_existing_name: styleExSep >= 0 ? styleExVal.slice(styleExSep + 1) : styleExVal,
        style_existing_workspace: styleExSep >= 0 ? styleExVal.slice(0, styleExSep) : '',
        // Estilos adicionais (chips) - sem isso, quem só adiciona um estilo adicional e
        // navega pra outro painel (ou fecha o QGIS) antes de publicar/"Continuar Depois"
        // perdia a lista inteira: _loadGsDraft não tinha de onde restaurá-la.
        style_additional: _gsAdditionalStyles.slice()
    };
    // Estilo não entra em hasContent de propósito: a fonte default ('qgis') existe em
    // qualquer formulário recém-aberto - contaria como "conteúdo" e salvaria rascunho
    // de um formulário intocado.
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

// Roda DEPOIS de _loadGsLayerInfo()/_renderGsLayerCard() - nome/workspace/datastore/
// estilo só entram se o banco (info.saved_*) deixou vazio (banco tem prioridade nesses -
// ver comentário mais abaixo sobre o nome). Título/resumo/palavras-chave são a exceção: o
// rascunho SEMPRE sobrepõe quando existe, mesmo com banco preenchido - ver comentário
// junto desses campos abaixo.
function _loadGsDraft(callback) {
    if (typeof gsBridge === 'undefined') { if (callback) callback(); return; }
    gsBridge.load_draft(function (draft) {
        if (draft) {
            var nameEl = document.getElementById('gs-layer-name');
            if (nameEl && !nameEl.value && draft.published_name) {
                nameEl.value = draft.published_name;
                onGsLayerNameInput(draft.published_name);
            }
            // Título/resumo/palavras-chave: diferente do nome/workspace/destino (banco
            // sempre vence, ver acima), esses são só texto descritivo, sem nenhuma
            // restrição técnica pra respeitar - o rascunho é sempre uma edição MAIS
            // RECENTE que o que está salvo (autosave roda a cada input, debounce de
            // 1.5s), então ele sobrepõe mesmo com o campo já preenchido pelo banco.
            // Bug corrigido aqui: editar o título de uma camada JÁ publicada e trocar de
            // aba (ou fechar o plugin) antes de "Continuar Depois"/republicar descartava
            // a edição em silêncio - a condição antiga (`!titleEl.value`) só aplicava o
            // rascunho num campo VAZIO, o que nunca acontece numa camada já publicada.
            var titleEl = document.getElementById('gs-layer-title');
            if (titleEl && draft.title) titleEl.value = draft.title;
            var abstractEl = document.getElementById('gs-layer-abstract');
            if (abstractEl && draft.abstract) abstractEl.value = draft.abstract;
            if (draft.keywords && draft.keywords.length) {
                _gsKeywords = draft.keywords.slice();
                _renderGsKeywords();
            }
            if (!_gsDbHasWorkspace && draft.workspace) {
                _gsQueueWorkspaceDatastore(draft.workspace, draft.datastore);
            }
            // Estilo do rascunho: só entra se o banco não resolveu (_gsDbHasStyle, mesma
            // prioridade banco > rascunho dos outros campos).
            if (!_gsDbHasStyle && draft.style_source) {
                _gsApplyStyleChoice(
                    draft.style_source,
                    draft.style_source === 'existing' ? (draft.style_existing_name || '') : (draft.style_name || ''),
                    draft.style_existing_workspace || ''
                );
                if (draft.style_source === 'file' && draft.style_file) {
                    _gsStyleFilePath = draft.style_file;
                    var fileBtn = document.getElementById('gs-style-file-btn');
                    if (fileBtn && draft.style_file_name) fileBtn.textContent = draft.style_file_name;
                }
            }
            // Estilos adicionais do rascunho - só entra se nada já veio do banco (mesma
            // prioridade banco > rascunho do workspace/estilo principal, acima).
            if (!_gsAdditionalStyles.length && draft.style_additional && draft.style_additional.length) {
                _gsAdditionalStyles = draft.style_additional.slice();
                _renderGsAdditionalStyles();
            }
            // Reavalia o badge: título/resumo/palavras-chave do rascunho podem ter acabado
            // de sobrepor o que o banco preencheu (ver acima) - ou, numa camada nunca salva
            // de verdade, o rascunho preencheu campos que o banco deixou vazios. Em
            // qualquer um dos casos, _gsSyncSnapshot (capturado em _renderGsLayerCard, a
            // partir do banco ou do estado pós-auto-preenchimento) continua intocado, então
            // _checkGsSyncNow() aqui compara direito contra a fonte de verdade e vira
            // "Modificado" quando for o caso.
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
    _applyGsSkeleton();                    // feedback visual imediato na troca de camada
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
    dismissGsUpdateBanner(); // camada mudou - o banner da camada anterior não vale mais aqui
    _gsSyncSnapshot = null;
    _gsSyncSnapshotRawName = '';
    _gsSyncSnapshotRawStyleName = '';
    _clickGsSuggestionItem('gs-workspace-wrap', ''); // volta workspace/datastore pra "Selecione..."
    _gsResetStyleControls(); // estilo também é por camada
    _loadGsLayerInfo(function () {
        _loadGsDraft();
    });
}

// Aplica shimmer animado nos campos de texto do painel GeoServer enquanto os dados carregam.
function _applyGsSkeleton() {
    ['gs-layer-name', 'gs-layer-title', 'gs-layer-abstract'].forEach(function (id) {
        var el = document.getElementById(id);
        if (el) el.classList.add('skeleton-field');
    });
}

// Remove o skeleton quando os dados reais começam a ser preenchidos.
function _removeGsSkeleton() {
    ['gs-layer-name', 'gs-layer-title', 'gs-layer-abstract'].forEach(function (id) {
        var el = document.getElementById(id);
        if (el) el.classList.remove('skeleton-field');
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
        'Isso vai descartar as alterações não salvas do destino de publicação. Continuar?',
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
            _gsResetStyleControls(); // volta a aba Estilos pro default ('qgis') - _loadGsLayerInfo reaplica o salvo, se houver
            _loadGsLayerInfo(function () { updateGsFormProgress(); }); // recarrega do banco (ou vazio) - sem rascunho
        },
        'Descartar Alterações'
    );
}

function _loadGsLayerInfo(callback) {
    var card = document.getElementById('gs-layer-card');
    if (!card) return;
    _gsFieldLockOverride = {}; // camada mudou - override de desbloqueio da camada anterior não vale mais
    // Esqueleto no formato final (badge + nome + schema.tabela, mesma estrutura que
    // _renderGsLayerCard monta quando os dados chegam) em vez de texto "Detectando..." -
    // mesmo raciocínio de _applyGsSkeleton (já ocupa o espaço da UI, sem salto de layout
    // quando o resultado chega).
    card.innerHTML =
        '<div class="gs-layer-detected-row">' +
        '<span class="gs-layer-badge skeleton-field" style="width:78px;">&nbsp;</span>' +
        '<div class="gs-layer-detected-info">' +
        '<span class="gs-layer-detected-name skeleton-field" style="display:inline-block;width:170px;">&nbsp;</span>' +
        '<small class="gs-layer-detected-schema skeleton-field" style="display:inline-block;width:130px;">&nbsp;</small>' +
        '</div></div>';
    _setGsTableCheck(null, ''); // camada mudou - qualquer checagem de tabela anterior não vale mais
    _setGsPullGnButtonState(false);
    var badge = document.getElementById('gs-sync-badge');
    if (badge) badge.style.display = 'none';
    dismissGsUpdateBanner();
    _gsSyncSnapshot = null;
    _gsSyncSnapshotRawName = '';
    _gsSyncSnapshotRawStyleName = '';
    _gsDbHasWorkspace = false;
    _gsDbHasStyle = false;
    updateGsFormProgress();
    // Dica de uuid do GN: usada como fallback quando a busca local (banco/sidecar) não
    // encontra nada - ex.: tabela auxiliar do plugin ainda não existe nesse banco (ver
    // docs_projeto/bugs.md, Bug 1). Só usa se o editor GN já confirmou sync pra ESSA
    // mesma camada nesta sessão (_gnSyncUuidLayerName, em geonetwork.js) - senão manda
    // vazio, pra não arriscar puxar o uuid de outra camada.
    var uuidHint = (window._gnSyncUuidLayerName === _activeLayerName && window._gnSyncUuid) ? window._gnSyncUuid : '';
    // get_active_layer_publish_info identifica a camada lendo iface.activeLayer() de novo
    // do lado Python, no momento em que o slot roda - não pelo que estava ativo quando a
    // chamada foi disparada. Trocar de camada rápido o bastante enquanto essa chamada
    // ainda está em voo faz a resposta chegar depois já pra outra camada, aplicando o
    // destino/metadado ERRADO no formulário (mesma corrida de _loadFormForLayer, geonetwork.js).
    _requestGsLayerInfo(uuidHint, _activeLayerName, function (info) {
        _gsLayerInfo = info;
        _renderGsLayerCard(info);
        if (callback) callback();
    });
}

function _renderGsLayerCard(info) {
    var card = document.getElementById('gs-layer-card');
    if (!card) return; // painel já foi trocado
    _removeGsSkeleton(); // remove skeleton antes de preencher os dados reais

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
    // ainda sobrar vazio. Faltando isso, cai pro nome REAL da tabela no banco (info.table)
    // - não pro nome da camada no QGIS (info.name), que pode ter sido renomeada localmente
    // e não bater com a tabela de verdade. O Nome publicado precisa ser idêntico ao nome
    // da tabela (é assim que o GeoServer localiza os dados) - ver confirmGsPublish.
    var nameEl = document.getElementById('gs-layer-name');
    if (nameEl && !nameEl.value) {
        var defaultName = info.saved_published_name || info.table || info.name;
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
    // Prévia só-consulta do link de metadados (aba Identificação) - mesmo uuid/URL que
    // register_postgis_featuretype vai de fato gravar na publicação (ver
    // GeoServerBridge._resolve_metadata_link_url/_build_metadata_link_url) - não editável
    // aqui de propósito, é só pra confirmar visualmente se vai ou não ser criado.
    var metaLinkBox = document.getElementById('gs-metadata-link-preview');
    if (metaLinkBox) {
        if (info.metadata_link_url) {
            metaLinkBox.innerHTML = 'Será vinculado ao publicar: <a href="' + escHtml(info.metadata_link_url) + '" target="_blank">' + escHtml(info.metadata_link_url) + '</a>';
        } else {
            metaLinkBox.textContent = 'Nenhum metadado salvo pra essa camada ainda - o link de metadados não será criado ao publicar.';
        }
    }
    _gsDbHasWorkspace = !!info.saved_workspace;
    if (info.saved_workspace) {
        _gsQueueWorkspaceDatastore(info.saved_workspace, info.saved_datastore);
    }
    // Estilo salvo no banco (info.saved_style_*): restaura a escolha. Registro antigo/sem
    // estilo (source vazio) vira 'none' - o snapshot correspondente tem style_source '' e
    // _gsCollectFormState mapeia 'none' -> '', então os dois batem. Camada nunca salva no
    // banco mantém o default do HTML ('qgis' - gerar do estilo do QGIS).
    _gsDbHasStyle = !!info.saved_style_source;
    if (info.saved_workspace) {
        _gsApplyStyleChoice(
            info.saved_style_source || 'none',
            info.saved_style_name || '',
            info.saved_style_workspace || ''
        );
        if (info.saved_style_additional_json) {
            try {
                _gsAdditionalStyles = JSON.parse(info.saved_style_additional_json);
                _renderGsAdditionalStyles();
            } catch (e) {
                console.error('GeoMetadata [Estilos Adicionais] erro no parse: ', e);
            }
        } else {
            _gsAdditionalStyles = [];
            _renderGsAdditionalStyles();
        }
    } else {
        _gsAdditionalStyles = [];
        _renderGsAdditionalStyles();
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
    _gsCaptureSnapshotRawNames();
    _gsSyncIsPublished = !!info.saved_published;
    _gsApplyFieldLockState();
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
        // Sem toast aqui de propósito - list_workspaces() já falha (sem sessão) toda vez
        // que o painel GS abre deslogado, então isso disparava um Modal.alert automático
        // (não motivado por clique nenhum do usuário) a cada visita. O dropdown já avisa
        // "Erro ao carregar workspaces" (ou preserva o destino conhecido, ver acima) - é
        // aviso suficiente pra um estado que só se resolve fazendo login.
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
    // A lista de estilos existentes é global + DO WORKSPACE - trocar o workspace muda a
    // lista. Só recarrega se a fonte 'existing' está ativa (senão carrega sob demanda em
    // onGsStyleSourceChange).
    var styleSrcEl = document.getElementById('gs-style-source');
    if (styleSrcEl && styleSrcEl.value === 'existing') _gsLoadStylesList();
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
            ? 'Tabela "' + _gsLayerInfo.table + '" encontrada no Workspace + Datastore acima.'
            : 'Tabela "' + _gsLayerInfo.table + '" não foi encontrada no Workspace + Datastore acima. Confira se escolheu o workspace/datastore certo antes de publicar.'
    );
}

function _setGsTableCheck(state, message) {
    _gsTableCheckState = state;
    var el = document.getElementById('gs-datastore-check');
    if (el) {
        el.textContent = message;
        el.className = 'gs-status-box' + (state === false ? ' gs-warning-text' : '');
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
            _gsResyncSnapshotNameIfUnchanged();
            _gsUpdateNameMismatchWarning();
        });
    }, 200);
}

// ─── Nome da camada publicada: precisa bater com o nome da tabela ──────────────
// O GeoServer localiza os dados pelo nome da tabela no datastore - se o Nome
// publicado divergir (mesmo por causa da sanitização, ex.: tabela começa com
// número ou tem acento), a camada publica "vazia"/sem encontrar a tabela certa.
// Ver confirmGsPublish (bloqueia publicar) e _gsToggleFieldLock/_gsApplyFieldLockState
// (trava o campo depois de publicado de verdade).

function _gsUpdateNameMismatchWarning() {
    var el = document.getElementById('gs-layer-name');
    var warn = document.getElementById('gs-layer-name-mismatch');
    if (!el || !warn) return;
    var table = _gsLayerInfo && _gsLayerInfo.table;
    var current = el.dataset.sanitized || el.value.trim();
    var mismatch = !!table && !el.readOnly && !!current && current !== table;
    warn.style.display = mismatch ? '' : 'none';
}

function _gsUseTableNameForLayerName() {
    var el = document.getElementById('gs-layer-name');
    var table = _gsLayerInfo && _gsLayerInfo.table;
    if (!el || !table) return;
    el.value = table;
    onGsLayerNameInput(table);
}

// ─── Cadeado de Nome/Título - trava depois que a camada foi publicada de
// verdade (_gsSyncIsPublished), pra evitar edição acidental. Mudar o Nome
// depois de publicado não RENOMEIA o FeatureType existente no GeoServer - cria
// uma referência nova (mesma lógica de _gsCollectFormState/confirmGsPublish,
// que sempre trata o Nome atual como alvo de publish/update), deixando a
// publicação antiga órfã (WMS/WFS antigos param de funcionar). Por isso o
// desbloqueio pede confirmação explícita em vez de só destravar direto.
var _gsFieldLockOverride = {}; // fieldId -> true quando o usuário confirmou destravar nesta sessão/camada

function _gsToggleFieldLock(fieldId) {
    var el = document.getElementById(fieldId);
    if (!el || !el.readOnly) return; // só faz sentido a partir do estado travado
    var isName = fieldId === 'gs-layer-name';
    var msg = isName
        ? 'O Nome da camada publicada precisa ser idêntico ao nome da tabela no banco de dados. Mudar esse valor NÃO renomeia a camada já publicada no GeoServer - cria uma referência nova, deixando a publicação atual (WMS/WFS já em uso) órfã. Tem certeza que quer editar mesmo assim?'
        : 'Esse título já está publicado no Geohab. Mudar aqui só atualiza de verdade lá na próxima publicação/atualização da camada. Quer editar mesmo assim?';
    Modal.confirm(msg, function () {
        _gsFieldLockOverride[fieldId] = true;
        _gsApplyFieldLockState();
    }, 'Editar campo bloqueado');
}

function _gsApplyFieldLockState() {
    var shouldLock = !!_gsSyncIsPublished;
    ['gs-layer-name', 'gs-layer-title'].forEach(function (fieldId) {
        var el = document.getElementById(fieldId);
        var lockBtn = document.getElementById(fieldId + '-lock');
        if (!el) return;
        var locked = shouldLock && !_gsFieldLockOverride[fieldId];
        el.readOnly = locked;
        if (lockBtn) {
            // Só mostra o ícone quando já existe publicação de verdade - antes disso o
            // campo é sempre livre e o cadeado não tem propósito nenhum ali.
            lockBtn.style.display = shouldLock ? '' : 'none';
            lockBtn.textContent = locked ? '🔒' : '🔓';
            lockBtn.style.cursor = locked ? 'pointer' : 'default';
            lockBtn.disabled = !locked;
        }
    });
    _gsUpdateNameMismatchWarning();
}

function _gsRawNameNow() {
    var nameEl = document.getElementById('gs-layer-name');
    return nameEl ? nameEl.value.trim() : '';
}

function _gsRawStyleNameNow() {
    var el = document.getElementById('gs-style-name');
    return el ? el.value.trim() : '';
}

// Captura os nomes CRUS (camada publicada + estilo) no momento em que _gsSyncSnapshot é
// capturado - sempre os dois juntos, pra _gsResyncSnapshotNameIfUnchanged conseguir
// distinguir "só a sanitização assíncrona resolveu" de "o usuário digitou outro nome".
function _gsCaptureSnapshotRawNames() {
    _gsSyncSnapshotRawName = _gsRawNameNow();
    _gsSyncSnapshotRawStyleName = _gsRawStyleNameNow();
}

// A sanitização (RF04, sanitize_layer_name) é assíncrona no lado JS (vai e volta pelo
// QWebChannel, mesmo sendo uma função síncrona/regex no Python) e só resolve ~200ms depois
// do nome ter sido preenchido - seja por auto-preenchimento (_renderGsLayerCard chama
// onGsLayerNameInput pro nome default sem esperar isso terminar), rascunho ou digitação.
// O snapshot de comparação (_gsSyncSnapshot) pode ter sido capturado ANTES dessa resposta
// chegar, com o nome CRU (nameEl.dataset.sanitized ainda vazio nesse instante, ver
// _gsCollectFormState) - sem isso, a checagem seguinte (_checkGsSyncNow) comparava um nome
// sanitizado (aqui) contra o nome cru (no snapshot) e acusava "Modificado" à toa só por
// causa da normalização (minúsculas/underscore), inclusive numa camada sem NENHUM registro
// salvo no banco (que devia mostrar "Não Encontrado"). Só reajusta o snapshot se o nome
// CRU não mudou desde a captura (_gsSyncSnapshotRawName) - se mudou (usuário digitou um
// nome diferente, ou um rascunho aplicou outro nome nesse meio-tempo), é uma edição de
// verdade, e _checkGsSyncNow deve continuar acusando normalmente.
function _gsResyncSnapshotNameIfUnchanged() {
    if (_gsSyncSnapshot === null) return;
    var nameEl = document.getElementById('gs-layer-name');
    var rawNow = nameEl ? nameEl.value.trim() : '';
    var rawStyleNow = _gsRawStyleNameNow();
    try {
        var snap = JSON.parse(_gsSyncSnapshot);
        if (rawNow === _gsSyncSnapshotRawName) {
            snap.published_name = nameEl ? (nameEl.dataset.sanitized || nameEl.value.trim()) : snap.published_name;
        }
        // Mesmo ajuste pro nome efetivo do ESTILO: ele depende do campo próprio (quando
        // preenchido) E do nome da camada (fallback quando vazio) - só reajusta quando os
        // dois nomes crus não mudaram desde a captura (aí a diferença só pode ser a
        // sanitização resolvendo) e o snapshot é de estilo criado pelo plugin
        // ('qgis'/'file' - 'existing'/'' não passam por sanitização nenhuma).
        if (rawNow === _gsSyncSnapshotRawName && rawStyleNow === _gsSyncSnapshotRawStyleName &&
            (snap.style_source === 'qgis' || snap.style_source === 'file')) {
            snap.style_name = _gsEffectiveStyleName();
        }
        _gsSyncSnapshot = JSON.stringify(snap);
    } catch (e) { /* snapshot sempre é um objeto JSON aqui - não deveria acontecer */ }
    _checkGsSyncNow();
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

// ─── Aba Estilos (SLD) ─────────────────────────────────────────────────────────
// Fontes: 'qgis' (exporta a simbologia atual da camada via saveSldStyle, no Python),
// 'file' (arquivo .sld local, escolhido via QFileDialog nativo), 'existing' (estilo já
// cadastrado no GeoServer - global ou do workspace) e 'none' (não mexer no estilo). Nos
// modos 'qgis'/'file' o estilo é criado/atualizado no workspace de publicação e vira o
// estilo PADRÃO da camada; estilos adicionais ficam pra uma próxima versão.

function onGsStyleSourceChange(value) {
    var nameGroup = document.getElementById('gs-style-name-group');
    var fileBtn = document.getElementById('gs-style-file-btn');
    var existingGroup = document.getElementById('gs-style-existing-group');
    if (nameGroup) nameGroup.style.display = (value === 'qgis' || value === 'file') ? '' : 'none';
    if (fileBtn) fileBtn.style.display = (value === 'file') ? '' : 'none';
    if (existingGroup) existingGroup.style.display = (value === 'existing') ? '' : 'none';
    if (value === 'existing') _gsLoadStylesList();
    // Fonte 'qgis': botão "Escolher arquivo..." escondido - sem essa classe o
    // input de nome fica preso na 2ª coluna do grid (mesma posição de quando o
    // botão aparece), ocupando só metade da linha em vez da largura toda.
    var row = fileBtn ? fileBtn.closest('.gs-addstyle-row') : null;
    if (row) row.classList.toggle('gs-addstyle-row--solo', value !== 'file');
}

// Mesmo padrão de onGsLayerNameInput (RF04): sanitização assíncrona com debounce +
// preview + dataset.sanitized. Campo vazio = "usa o nome da camada publicada" - nesse
// caso NÃO chama o sanitizador (sanitize_layer_name('') devolve o fallback 'camada',
// que não é o que o vazio significa aqui).
function onGsStyleNameInput(name) {
    clearTimeout(_gsStyleNameTimer);
    var el = document.getElementById('gs-style-name');
    var preview = document.getElementById('gs-style-name-preview');
    if (!(name || '').trim()) {
        if (el) el.dataset.sanitized = '';
        if (preview) preview.textContent = '';
        _gsResyncSnapshotNameIfUnchanged();
        return;
    }
    _gsStyleNameTimer = setTimeout(function () {
        gsBridge.sanitize_layer_name(name, function (sanitized) {
            var previewEl = document.getElementById('gs-style-name-preview');
            if (previewEl) previewEl.textContent = sanitized ? ('Nome final: ' + sanitized) : '';
            var nameEl = document.getElementById('gs-style-name');
            if (nameEl) nameEl.dataset.sanitized = sanitized;
            _gsResyncSnapshotNameIfUnchanged();
        });
    }, 200);
}

// Nome EFETIVO do estilo padrão que o formulário representa agora - '' quando a fonte é
// 'none' (ou nada selecionável ainda). Entra no estado de comparação do badge
// (_gsCollectFormState) e espelha a regra do Python (derive_style_fields/
// _prepare_style_task): campo vazio nos modos 'qgis'/'file' cai pro nome da camada.
function _gsEffectiveStyleName() {
    var srcEl = document.getElementById('gs-style-source');
    var src = srcEl ? srcEl.value : 'none';
    if (!src || src === 'none') return '';
    if (src === 'existing') {
        var exEl = document.getElementById('gs-style-existing');
        var v = (exEl && exEl.value) || '';
        var sep = v.indexOf(':');
        return sep >= 0 ? v.slice(sep + 1) : v;
    }
    var nameEl = document.getElementById('gs-style-name');
    var raw = nameEl ? nameEl.value.trim() : '';
    if (raw) return (nameEl.dataset.sanitized || raw);
    var layerNameEl = document.getElementById('gs-layer-name');
    return layerNameEl ? (layerNameEl.dataset.sanitized || layerNameEl.value.trim()) : '';
}

function pickGsSldFile() {
    if (typeof gsBridge === 'undefined' || !gsBridge.pick_sld_file) return;
    gsBridge.pick_sld_file(function (res) {
        if (!res || res.cancelled) return;
        if (!res.ok) {
            Modal.alert(res.error || 'Arquivo SLD inválido.', 'Erro', 'error');
            return;
        }
        _gsStyleFilePath = res.path;
        var btn = document.getElementById('gs-style-file-btn');
        if (btn) btn.textContent = res.filename;
        // Escolha via QFileDialog não dispara input/change no painel - agenda na mão
        // (mesmo motivo de gsAddKeyword/gsRemoveKeyword).
        _gsOnFieldChanged();
        _scheduleGsDraftSave();
    });
}

function _gsSetExistingStatus(msg) {
    var el = document.getElementById('gs-style-existing-status');
    if (el) el.textContent = msg || '';
}

// Carrega (ou recarrega) a lista de estilos existentes pro select da fonte 'existing' -
// globais + do workspace atualmente escolhido na aba Destino. Preserva a seleção atual
// pra reaplicar quando a resposta chegar (mesmo padrão de _gsPendingDraftWorkspace).
function _gsLoadStylesList() {
    var wrap = document.getElementById('gs-style-existing-wrap');
    if (!wrap || typeof gsBridge === 'undefined' || !gsBridge.list_styles) return;
    var current = document.getElementById('gs-style-existing');
    if (current && current.value) _gsPendingExistingStyle = current.value;
    wrap.innerHTML = '<select id="gs-style-existing"><option value="">Carregando estilos...</option></select>';
    initCustomSelects();
    _gsSetExistingStatus('');
    var wsEl = document.getElementById('gs-workspace');
    gsBridge.list_styles(wsEl ? wsEl.value : '');
}

function _renderGsStyleOptions(styles, error) {
    var wrap = document.getElementById('gs-style-existing-wrap');
    if (!wrap) return; // painel já foi trocado
    if (error) {
        // Sem sessão a REST nem lista estilos - preserva o valor já conhecido (banco/
        // rascunho) como opção única em vez de perder a seleção (mesma lógica de
        // _renderGsWorkspaces/_gsApplyKnownWorkspaceDatastore).
        if (_gsPendingExistingStyle) {
            var known = _gsPendingExistingStyle;
            _gsPendingExistingStyle = null;
            var sep = known.indexOf(':');
            _gsSeedExistingStyle(sep >= 0 ? known.slice(sep + 1) : known, sep >= 0 ? known.slice(0, sep) : '');
        } else {
            wrap.innerHTML = '<select id="gs-style-existing"><option value="">—</option></select>';
            initCustomSelects();
        }
        _gsSetExistingStatus('Não foi possível listar os estilos do GeoServer (faça login no Geohab e tente de novo).');
        return;
    }
    var options = '<option value="">Selecione um estilo...</option>';
    (styles || []).forEach(function (s) {
        var value = (s.workspace ? s.workspace + ':' : '') + s.name;
        var label = s.workspace ? (s.workspace + ' : ' + s.name) : s.name;
        options += '<option value="' + escHtml(value) + '">' + escHtml(label) + '</option>';
    });

    if (wrap) wrap.innerHTML = '<select id="gs-style-existing">' + options + '</select>';
    var wrapAdd = document.getElementById('gs-add-style-existing-wrap');
    if (wrapAdd) wrapAdd.innerHTML = '<select id="gs-add-style-existing">' + options + '</select>';

    initCustomSelects();
    if (_gsPendingExistingStyle) {
        var target = _gsPendingExistingStyle;
        _gsPendingExistingStyle = null;
        if (!_clickGsSuggestionItem('gs-style-existing-wrap', target)) {
            // O estilo conhecido não apareceu na lista recém-buscada (ex.: essa recarga
            // rodou com um workspace diferente do que o estilo está associado, timing
            // entre a checagem de login e a seleção de workspace, ou o estilo foi mesmo
            // removido/renomeado) - preserva o valor conhecido como opção própria em vez
            // de deixar a seleção sumir silenciosamente (mesmo padrão do branch de erro
            // logo acima). Sem isso, a seleção que estava correta (vinda do banco) se
            // perdia sempre que essa lista recarregava depois (ex.: ao logar).
            var sep = target.indexOf(':');
            _gsSeedExistingStyle(sep >= 0 ? target.slice(sep + 1) : target, sep >= 0 ? target.slice(0, sep) : '');
        }
    }
    if (_gsPendingExistingAddStyle) {
        var targetAdd = _gsPendingExistingAddStyle;
        _gsPendingExistingAddStyle = null;
        _clickGsSuggestionItem('gs-add-style-existing-wrap', targetAdd);
    }
    _gsSetExistingStatus((styles && styles.length) ? '' : 'Nenhum estilo cadastrado no GeoServer ainda.');
}

// Preserva um estilo existente já conhecido (banco/rascunho) como única opção do select,
// sem depender da lista completa (REST, exige login) ter carregado - análogo de
// _gsApplyKnownWorkspaceDatastore pro estilo.
function _gsSeedExistingStyle(name, styleWorkspace) {
    var wrap = document.getElementById('gs-style-existing-wrap');
    if (!wrap || !name) return;
    var value = (styleWorkspace ? styleWorkspace + ':' : '') + name;
    var label = styleWorkspace ? (styleWorkspace + ' : ' + name) : name;
    wrap.innerHTML = '<select id="gs-style-existing"><option value="' + escHtml(value) + '" selected>' +
        escHtml(label) + '</option></select>';
    initCustomSelects();
}

// Aplica uma escolha de estilo conhecida (banco em _renderGsLayerCard, rascunho em
// _loadGsDraft) nos controles da aba Estilos - "if vazio" no nome, igual aos outros
// campos restaurados. Dispara os mesmos handlers de um clique manual quando possível.
function _gsApplyStyleChoice(source, name, styleWorkspace) {
    var srcEl = document.getElementById('gs-style-source');
    if (!srcEl) return;
    if (srcEl.value !== source) {
        if (!_clickGsSuggestionItem('gs-style-source-wrap', source)) {
            // custom select ainda não inicializado (lista de workspaces não respondeu) -
            // aplica no select nativo e chama o handler na mão.
            srcEl.value = source;
            onGsStyleSourceChange(source);
        }
    } else {
        onGsStyleSourceChange(source); // garante a visibilidade dos grupos coerente
    }
    if (source === 'existing') {
        _gsSeedExistingStyle(name, styleWorkspace || '');
        // O clique na fonte acima já disparou _gsLoadStylesList ANTES do seed (o select
        // ainda estava vazio, então nada foi capturado como pendente) - deixa o valor
        // conhecido pendente pra lista real reaplicar quando chegar, senão a resposta
        // substituiria o select semeado e perderia a seleção restaurada.
        if (name) _gsPendingExistingStyle = (styleWorkspace ? styleWorkspace + ':' : '') + name;
    } else if (source === 'qgis' || source === 'file') {
        var nameEl = document.getElementById('gs-style-name');
        if (nameEl && !nameEl.value && name) {
            nameEl.value = name;
            // dataset.sanitized direto, SEM passar por onGsStyleNameInput (RF04) - esse
            // `name` vem do banco (info.saved_style_name), já é o nome sanitizado de
            // verdade usado na última publicação, não precisa resanitizar. A sanitização
            // assíncrona (debounce de 200ms + ida-e-volta no QWebChannel) só existe pra
            // digitação do usuário; se disparada aqui, _checkGsSyncOnline (chamado logo
            // em seguida por _renderGsLayerCard) manda o nome CRU pro check_gs_sync antes
            // da resposta sanitizada chegar - a checagem ao vivo comparava esse nome cru
            // contra o que está de fato publicado no GeoServer (já sanitizado) e acusava
            // "Modificado" à toa. Diferente de _gsResyncSnapshotNameIfUnchanged (mesma
            // race, mas só corrigida até agora no nível banco/_checkGsSyncNow) - a
            // checagem ao vivo é fire-and-forget e fica em cache por 60s, então o
            // resultado errado persistia até a próxima checagem forçada.
            nameEl.dataset.sanitized = name;
            var previewEl = document.getElementById('gs-style-name-preview');
            if (previewEl) previewEl.textContent = 'Nome final: ' + name;
        }
    }
}

// Volta a aba Estilos pro estado default (fonte 'qgis', sem nome/arquivo/existente) -
// usado na troca de camada ativa e no "Descartar Alterações".
function _gsResetStyleControls() {
    _gsStyleFilePath = '';
    _gsPendingExistingStyle = null;
    var fileBtn = document.getElementById('gs-style-file-btn');
    if (fileBtn) fileBtn.textContent = 'Escolher arquivo...';
    var nameEl = document.getElementById('gs-style-name');
    if (nameEl) { nameEl.value = ''; nameEl.dataset.sanitized = ''; }
    var preview = document.getElementById('gs-style-name-preview');
    if (preview) preview.textContent = '';
    var wrap = document.getElementById('gs-style-existing-wrap');
    if (wrap) {
        wrap.innerHTML = '<select id="gs-style-existing"><option value="">Selecione a fonte "estilo existente" para carregar...</option></select>';
        initCustomSelects();
    }
    _gsSetExistingStatus('');
    _gsApplyStyleChoice('qgis', '', '');
}

// --- Estilos Adicionais ---
var _gsAdditionalStyles = [];
var _gsAddStyleFilePath = null;
var _gsPendingExistingAddStyle = null;

function onGsAddStyleSourceChange(value) {
    var fileGroup = document.getElementById('gs-add-style-file-group');
    var existingGroup = document.getElementById('gs-add-style-existing-group');
    if (fileGroup) fileGroup.style.display = (value === 'file') ? '' : 'none';
    if (existingGroup) existingGroup.style.display = (value === 'existing') ? '' : 'none';
    if (value === 'existing') _gsLoadAddStylesList();
}

function onGsAddStyleNameInput(name) {
    var el = document.getElementById('gs-add-style-name');
    if (!(name || '').trim()) {
        if (el) el.dataset.sanitized = '';
        return;
    }
    // Simplificando timeout pra não precisar variavel global isolada
    setTimeout(function () {
        if (typeof gsBridge !== 'undefined' && gsBridge.sanitize_layer_name) {
            gsBridge.sanitize_layer_name(name, function (sanitized) {
                if (el) el.dataset.sanitized = sanitized;
            });
        }
    }, 200);
}

function pickGsAddSldFile() {
    if (typeof gsBridge === 'undefined' || !gsBridge.pick_sld_file) return;
    gsBridge.pick_sld_file(function (res) {
        if (!res || res.cancelled) return;
        if (!res.ok) {
            Modal.alert(res.error || 'Arquivo SLD inválido.', 'Erro', 'error');
            return;
        }
        _gsAddStyleFilePath = res.path;
        var btn = document.getElementById('gs-add-style-file-btn');
        if (btn) btn.textContent = res.filename;
    });
}

function _gsLoadAddStylesList() {
    var wrap = document.getElementById('gs-add-style-existing-wrap');
    if (!wrap || typeof gsBridge === 'undefined' || !gsBridge.list_styles) return;
    var current = document.getElementById('gs-add-style-existing');
    if (current && current.value) _gsPendingExistingAddStyle = current.value;

    wrap.innerHTML = '<select id="gs-add-style-existing"><option value="">Carregando estilos...</option></select>';
    initCustomSelects();

    var wsEl = document.getElementById('gs-workspace');
    gsBridge.list_styles(wsEl ? wsEl.value : '');
}

function gsAddAdditionalStyle() {
    var srcEl = document.getElementById('gs-add-style-source');
    var source = srcEl ? srcEl.value : '';
    if (!source) return;

    var styleObj = { source: source };

    if (source === 'existing') {
        var exEl = document.getElementById('gs-add-style-existing');
        var v = (exEl && exEl.value) || '';
        if (!v) {
            Modal.alert('Selecione um estilo existente primeiro.', 'Aviso', 'warning');
            return;
        }
        var sep = v.indexOf(':');
        styleObj.existing_workspace = sep >= 0 ? v.slice(0, sep) : '';
        styleObj.existing_name = sep >= 0 ? v.slice(sep + 1) : v;
        styleObj.mode = 'existing';
    } else if (source === 'file') {
        if (!_gsAddStyleFilePath) {
            Modal.alert('Selecione um arquivo .sld primeiro.', 'Aviso', 'warning');
            return;
        }
        var nameEl = document.getElementById('gs-add-style-name');
        var rawName = nameEl ? nameEl.value.trim() : '';
        var name = (nameEl && nameEl.dataset.sanitized) ? nameEl.dataset.sanitized : rawName;
        if (!name) {
            Modal.alert('Informe o nome do estilo.', 'Aviso', 'warning');
            return;
        }
        styleObj.file_path = _gsAddStyleFilePath;
        styleObj.name = name;
        styleObj.mode = 'create';
    }

    var checkName = styleObj.name || styleObj.existing_name;
    for (var i = 0; i < _gsAdditionalStyles.length; i++) {
        var existing = _gsAdditionalStyles[i];
        if ((existing.name || existing.existing_name) === checkName) {
            Modal.alert('Um estilo com esse nome já foi adicionado.', 'Aviso', 'warning');
            return;
        }
    }

    _gsAdditionalStyles.push(styleObj);
    _renderGsAdditionalStyles();
    _scheduleGsDraftSave();

    _gsAddStyleFilePath = null;
    var btn = document.getElementById('gs-add-style-file-btn');
    if (btn) btn.textContent = 'Escolher arquivo...';
    var inpName = document.getElementById('gs-add-style-name');
    if (inpName) { inpName.value = ''; inpName.dataset.sanitized = ''; }
}

function gsRemoveAdditionalStyle(idx) {
    _gsAdditionalStyles.splice(idx, 1);
    _renderGsAdditionalStyles();
    _scheduleGsDraftSave();
}

function _renderGsAdditionalStyles() {
    var box = document.getElementById('gs-additional-styles-chips');
    if (!box) return;
    box.innerHTML = _gsAdditionalStyles.map(function (s, i) {
        var label = '';
        if (s.source === 'existing') {
            label = (s.existing_workspace ? s.existing_workspace + ':' : '') + s.existing_name;
        } else {
            label = s.name + ' (arquivo)';
        }
        return '<span class="keyword-chip">' + escHtml(label) +
            '<button onclick="gsRemoveAdditionalStyle(' + i + ')" data-title="Remover">×</button></span>';
    }).join('');
}
// ----------------------------

// Configuração da aba Estilos no formato que o Python espera (_prepare_style_task/
// derive_style_fields, ver geoserver_bridge.py) - serializada como JSON em
// confirmGsPublish/saveGsDraftNow/tryUpdateGsStyle.
function _gsCollectStyleConfig() {
    var srcEl = document.getElementById('gs-style-source');
    var src = srcEl ? srcEl.value : 'none';
    var cfg = { source: src, additional: _gsAdditionalStyles.slice() };
    if (!src || src === 'none') {
        cfg.source = '';
        return cfg;
    }
    if (src === 'existing') {
        var exEl = document.getElementById('gs-style-existing');
        var v = (exEl && exEl.value) || '';
        var sep = v.indexOf(':');
        cfg.existing_name = sep >= 0 ? v.slice(sep + 1) : v;
        cfg.existing_workspace = sep >= 0 ? v.slice(0, sep) : '';
    } else {
        var nameEl = document.getElementById('gs-style-name');
        var raw = nameEl ? nameEl.value.trim() : '';
        cfg.name = raw || _gsEffectiveStyleName();
        cfg.file_path = (src === 'file') ? _gsStyleFilePath : '';
    }
    return cfg;
}

// Aviso RN04 (requisitos_v2.md): a conversão QGIS -> SLD é best-effort - simbologia
// complexa pode não ter equivalente. Entra nos modais de confirmação quando a fonte é
// 'qgis', antes de qualquer exportação acontecer.
function _gsStyleBestEffortNote(style) {
    return style.source === 'qgis'
        ? '<br><br>⚠️ A conversão do estilo do QGIS para SLD é aproximada - simbologias complexas (regras data-driven, efeitos, mesclagem) podem não ser traduzidas perfeitamente.'
        : '';
}

// Descrição curta do estilo pros modais de confirmação (Publicar/Atualizar Estilo).
function _gsDescribeStyle(style) {
    if (style.source === 'existing') {
        return '"' + escHtml((style.existing_workspace ? style.existing_workspace + ':' : '') + style.existing_name) + '" (já existente no GeoServer)';
    }
    var name = escHtml(style.name || '');
    return style.source === 'file'
        ? ('"' + name + '" (do arquivo .sld)')
        : ('"' + name + '" (gerado do estilo atual do QGIS)');
}

// Valida a configuração da aba Estilos antes de publicar/atualizar - retorna a mensagem
// de erro ('' = ok). Compartilhada entre confirmGsPublish e tryUpdateGsStyle.
function _gsValidateStyleConfig(style) {
    if (style.source === 'file' && !style.file_path) {
        return 'Escolha o arquivo .sld na aba Estilos antes de continuar.';
    }
    if (style.source === 'existing' && !style.existing_name) {
        return 'Escolha um estilo existente na aba Estilos antes de continuar.';
    }
    return '';
}

// "Serviços > Atualizar Estilo" (main.html) - aplica o estilo da aba Estilos a uma camada
// JÁ publicada, sem republicar o FeatureType (publicar de novo daria "já existe"). Mesmo
// pré-requisito de tryPublishGeoServerLayer: painel "Configurar Camada" aberto.
function tryUpdateGsStyle() {
    if (!document.getElementById('gs-layer-card')) {
        Modal.alert('Abra "Serviços > Configurar Camada" antes de atualizar o estilo.', 'Ação Necessária', 'warning');
        return;
    }
    if (!_gsLayerInfo || !_gsLayerInfo.publishable) {
        Modal.alert((_gsLayerInfo && _gsLayerInfo.reason) || 'Nenhuma camada publicável ativa no QGIS.', 'Aviso', 'warning');
        return;
    }
    var d = _gsCollectFormState();
    if (!d.workspace || !d.published_name) {
        Modal.alert('Preencha o Workspace (aba Destino) e o Nome da camada publicada (aba Identificação) antes de atualizar o estilo.', 'Aviso', 'warning');
        return;
    }
    // Essa ação faz um PUT usando o Nome da camada publicada como identificador da
    // camada JÁ existente no GeoServer - se o campo foi alterado desde a última
    // publicação/salvamento conhecida, o PUT tentaria achar uma camada com o nome NOVO
    // (que não existe) em vez de atualizar a que já existe com o nome ANTIGO, e o
    // GeoServer devolve 404 (confuso: "a camada existe", só que com outro nome).
    var knownName = _gsLayerInfo.saved_published_name || _gsLayerInfo.name;
    if (knownName && d.published_name !== knownName) {
        Modal.alert(
            'O "Nome da camada publicada" foi alterado ("' + escHtml(knownName) + '" → "' + escHtml(d.published_name) +
            '"). Essa ação atualiza o estilo de uma camada JÁ publicada pelo nome ATUAL no GeoServer - renomear não é ' +
            'suportado por aqui.<br><br>Desfaça a alteração nesse campo (aba Identificação) antes de atualizar o estilo, ' +
            'ou publique como uma camada nova em "Serviços > Publicar Camada".',
            'Nome Alterado', 'warning'
        );
        return;
    }
    var style = _gsCollectStyleConfig();
    if (!style.source) {
        Modal.alert('Escolha um estilo na aba Estilos antes de atualizar - a fonte "Não definir" não tem o que aplicar.', 'Aviso', 'warning');
        return;
    }
    var styleError = _gsValidateStyleConfig(style);
    if (styleError) {
        Modal.alert(styleError, 'Aviso', 'warning');
        return;
    }
    Modal.confirm(
        'Aplicar o estilo ' + _gsDescribeStyle(style) + ' como estilo padrão da camada "' +
        escHtml(d.workspace) + ':' + escHtml(d.published_name) + '"?<br><br>' +
        'A camada precisa já estar publicada no GeoServer - isso não republica a camada, só troca o estilo.' +
        _gsStyleBestEffortNote(style),
        function () {
            _showActionLoading('Aplicando estilo no GeoServer...');
            gsBridge.update_style(d.workspace, d.datastore, d.published_name, d.title, d.abstract, d.keywords, JSON.stringify(style));
        },
        'Atualizar Estilo'
    );
}

// "Serviços > Atualizar Camada" / banner "Atualização disponível" (ver setGsBadge) -
// análogo, do lado GeoServer, do "Atualizar agora" do editor GN: PULL, não push. Busca
// o que está DE FATO publicado no GeoServer agora (título/resumo/palavras-chave +
// estilo padrão/adicionais) e substitui o formulário local por isso. Existe pro caso em
// que o formulário/banco LOCAL ficou pra trás em relação ao que foi publicado de
// verdade - ex.: um técnico salvou só o destino no banco ("Continuar Depois") e outro
// técnico, em outra máquina, completou e publicou depois; ao reabrir essa camada, o
// primeiro técnico veria "Modificado" e, se essa ação empurrasse o formulário LOCAL
// (desatualizado) pro servidor, sobrescreveria o trabalho de quem publicou por último.
// Por isso a direção certa é trazer o servidor pra cá, não o contrário.
function pullGsLayerFromServer() {
    if (!document.getElementById('gs-layer-card')) {
        Modal.alert('Abra "Serviços > Configurar Camada" antes de atualizar a camada.', 'Ação Necessária', 'warning');
        return;
    }
    // Diferente do menu (sempre disponível) e do banner (gated por _isLogged em
    // setGsBadge, mas só reavaliado quando o badge recomputa), essa checagem aqui cobre
    // as duas entradas - a busca no GeoServer (fetch_published_featuretype/
    // fetch_layer_styles) exige sessão ativa; sem isso, o clique só falharia com
    // "Sessão não foi inicializada" vindo do Python.
    if (!_isLogged) {
        Modal.alert('Faça login no Geohab antes de atualizar a camada - essa ação busca os dados direto do GeoServer.', 'Login Necessário', 'warning');
        return;
    }
    if (!_gsLayerInfo || !_gsLayerInfo.publishable) {
        Modal.alert((_gsLayerInfo && _gsLayerInfo.reason) || 'Nenhuma camada publicável ativa no QGIS.', 'Aviso', 'warning');
        return;
    }
    var d = _gsCollectFormState();
    if (!d.workspace || !d.datastore || !d.published_name) {
        Modal.alert('Preencha Workspace/Datastore (aba Destino) e o Nome da camada publicada (aba Identificação) antes de atualizar.', 'Aviso', 'warning');
        return;
    }
    Modal.confirm(
        'Isso vai substituir título/resumo/palavras-chave/estilo do formulário atual pelo que está DE FATO publicado agora em "' +
        escHtml(d.workspace) + ':' + escHtml(d.published_name) + '" no GeoServer.<br><br>' +
        'Alterações locais não salvas nesses campos serão perdidas. Continuar?',
        function () {
            _showActionLoading('Buscando dados publicados no GeoServer...');
            gsBridge.pull_layer_from_server(d.workspace, d.datastore, d.published_name);
        },
        'Atualizar Camada'
    );
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
    var styleSrcEl = document.getElementById('gs-style-source');
    var styleSource = (styleSrcEl && styleSrcEl.value !== 'none') ? styleSrcEl.value : '';
    return {
        workspace: ws ? ws.value : '',
        datastore: ds ? ds.value : '',
        published_name: publishedName,
        title: (titleEl && titleEl.value.trim()) || publishedName,
        abstract: (abstractEl && abstractEl.value.trim()) || '',
        keywords: _gsKeywords.slice(),
        // 'none' vira '' de propósito: é como registros sem estilo ficam no banco
        // (geoserver_publish_xml sem style_source) - assim formulário e snapshot batem.
        // A ORDEM das chaves importa: os snapshots são comparados como string JSON
        // (_checkGsSyncNow), então style_source/style_name sempre por último, na mesma
        // ordem de _gsSnapshotFromSaved/_onGsSyncChecked.
        style_source: styleSource,
        style_name: _gsEffectiveStyleName(),
        style_additional: _gsAdditionalStyles.slice()
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
var _gsSyncSnapshotRawName = ''; // nome CRU (nameEl.value, sem sanitização) no momento em que _gsSyncSnapshot foi capturado - ver _gsResyncSnapshotNameIfUnchanged
var _gsSyncSnapshotRawStyleName = ''; // idem, pro nome CRU do estilo (aba Estilos) - o nome efetivo do estilo passa pela mesma sanitização assíncrona
var _gsSyncIsPublished = false; // esse snapshot veio de uma publicação de verdade (true) ou só de um "Continuar Depois" (false) - só afeta o tooltip/toast, não o rótulo do badge
var _gsSyncHasRecord = false; // true = existe algo salvo no banco (info.saved_workspace) - falso = _gsSyncSnapshot é o estado pós-auto-preenchimento
var _gsOnlineLastCheckedKey = null; // ver _checkGsSyncOnline - cache por camada+destino, mesmo padrão de _gnLastCheckedLayerKey (geonetwork.js)
var _gsOnlineLastCheckedAt = 0;
var _gsOnlineExpectedKey = null; // key (camada+destino) da última checagem AO VIVO disparada - ver _checkGsSyncOnline/_onGsSyncChecked
var _gsOnlineInFlightKey = null; // key com uma checagem AO VIVO já pedida ao Python, ainda sem resposta - evita disparar check_gs_sync de novo pra mesma key antes da primeira voltar (duas em voo faziam o worker mais velho no Python perder a referência e nunca emitir, ou uma resposta desatualizada chegar por último e sobrescrever o badge com estado errado) - ver _checkGsSyncOnline/_onGsSyncChecked

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
    sys_modified: 'Modificado',
    error: 'Erro ao verificar'
};

var _GS_SYNC_TOOLTIPS = {
    offline: 'Destino de publicação ainda não salvo em lugar nenhum.',
    db_not_found: 'Nenhum destino salvo no banco ainda (sem login no Geohab).',
    db_modified: 'Editado desde o último salvamento no banco (sem login no Geohab).',
    sys_not_found: 'Nenhum destino de publicação salvo ainda.',
    sys_modified: 'Editado desde o último salvamento/publicação.',
    error: 'Não foi possível verificar contra o GeoServer agora.'
    // db_synced/sys_synced não têm entrada fixa aqui - ver _gsPublishTooltip (texto curto,
    // pro hover - não confundir com _gsPublishModalMessage, versão rica do modal).
};

// Mesmo padrão de _GN_SYNC_MODALS (geonetwork.js): frase inicial + callout ⚠️ quando o
// nível é banco (sem login, não dá pra confirmar contra o GeoServer de verdade) +
// próximos passos quando há mais de uma opção. db_synced/sys_synced sempre "success" -
// "Sincronizado" cobre publicado de verdade no GeoServer OU só salvo no banco via
// "Continuar Depois", mas isso é uma nuance de TEXTO (ver _gsPublishModalMessage), não de
// severidade do modal - por isso não têm "message" fixo aqui, só título/tipo.
var _GS_SYNC_MODALS = {
    offline: { title: 'Não salvo', type: 'info', message: 'Destino de publicação ainda não salvo em lugar nenhum.<br><br>Use "Arquivo > Continuar Depois" pra salvar sem publicar, ou publique direto em "Serviços > Publicar Camada".' },
    db_not_found: { title: 'Não Encontrado (DB)', type: 'warning', message: 'Nenhum destino de publicação salvo no banco pra esta camada ainda.<br><br>⚠️ Verificado sem login no Geohab.<br>Faça login para verificação Online.<br><br>Use:<br>"Arquivo > Continuar Depois" pra salvar no banco, ou<br>faça login e publique direto em "Serviços > Publicar Camada".' },
    db_modified: { title: 'Modificado (DB)', type: 'warning', message: 'O formulário atual foi editado desde o último salvamento no banco.<br><br>⚠️ Verificado sem login no Geohab.<br>Faça login para verificação Online.<br><br>Use:<br>"Arquivo > Continuar Depois" pra salvar, ou<br>"Arquivo > Descartar Alterações" pra voltar ao último salvo.' },
    db_synced: { title: 'Sincronizado (DB)', type: 'success' },
    sys_not_found: { title: 'Não Encontrado (Geohab)', type: 'warning', message: 'Nenhum destino de publicação salvo pra esta camada ainda.<br><br>Use "Arquivo > Continuar Depois" pra salvar sem publicar, ou publique direto em "Serviços > Publicar Camada".' },
    sys_modified: { title: 'Modificado', type: 'warning', message: 'Você tem alterações não salvas.<br><br>Use: <br>"Arquivo > Continuar Depois" pra salvar sem publicar, ou <br>"Serviços > Publicar Camada" para publicar no Geohab.' },
    sys_synced: { title: 'Sincronizado', type: 'success' },
    error: { title: 'Erro ao verificar', type: 'error', message: 'Não foi possível verificar o status agora (falha de rede ao consultar o GeoServer). Clique no botão "↻" ao lado do badge pra tentar de novo.' }
};

// Tooltip CURTO (hover, texto plano - ver initGlobalTooltips/app.js, que joga isso direto
// num textContent, então nada de HTML/<br> aqui) pro estado _synced - muda conforme
// isPublished porque "Sincronizado" cobre publicado de verdade no GeoServer ou só salvo no
// banco via "Continuar Depois". Compartilhado com o sufixo GS do badge combinado do editor
// (geonetwork.js, ver checkGsPublishStatus) - por isso recebe isPublished como parâmetro em
// vez de ler _gsSyncIsPublished direto (esse global só existe aqui, no painel GS).
function _gsPublishTooltip(tierPrefix, isPublished) {
    var levelNote = tierPrefix === 'sys' ? '' : ' (sem login)';
    return isPublished
        ? ('Publicada no GeoServer' + levelNote + '.')
        : ('Bate com o banco, mas ainda não foi publicada no GeoServer' + levelNote + '.');
}

// Mensagem RICA (HTML, mesmo padrão de _GN_SYNC_MODALS.db_synced) do modal pro estado
// _synced (ver onGsSyncBadgeClick) - versão longa de _gsPublishTooltip acima, com o mesmo
// callout ⚠️ de nível banco e o próximo passo quando ainda não foi publicada de verdade.
function _gsPublishModalMessage(tierPrefix, isPublished) {
    var loginNote = tierPrefix === 'sys' ? '' : '<br><br>⚠️ Verificado sem login no Geohab.<br>Faça login para verificação Online.';
    if (isPublished) {
        return 'Essa camada já foi publicada no GeoServer.' + loginNote;
    }
    return 'O formulário atual bate com o que está salvo no banco, mas ainda não foi publicada no GeoServer.' + loginNote;
}

// Botão "↻" (ver refreshGsSync) fica escondido na maior parte do tempo - só aparece (1)
// no estado 'error' (única situação onde recarregar de verdade ajuda) ou (2) por uma
// janela curta logo após publicar/salvar/puxar/atualizar estilo (_flashGsRefreshBtn) -
// foi exatamente nesses momentos que os erros de rede intermitentes (SSL/403) mais
// apareceram nos testes. Mesmo padrão de _gnUpdateRefreshBtnVisibility (geonetwork.js).
var _gsRefreshVisibleUntil = 0;
function _gsUpdateRefreshBtnVisibility(state) {
    var btn = document.getElementById('gs-refresh-btn');
    if (!btn) return;
    btn.style.display = (state === 'error' || Date.now() < _gsRefreshVisibleUntil) ? 'inline-flex' : 'none';
}
function _flashGsRefreshBtn() {
    _gsRefreshVisibleUntil = Date.now() + 8000;
    var badge = document.getElementById('gs-sync-badge');
    var state = badge ? badge.className.replace('gn-sync-badge', '').trim() : '';
    _gsUpdateRefreshBtnVisibility(state);
    setTimeout(function () {
        var b = document.getElementById('gs-sync-badge');
        var s = b ? b.className.replace('gn-sync-badge', '').trim() : '';
        _gsUpdateRefreshBtnVisibility(s);
    }, 8000);
}

function setGsBadge(state) {
    var badge = document.getElementById('gs-sync-badge');
    var label = document.getElementById('gs-sync-label');
    if (!badge || !label) return;
    badge.className = 'gn-sync-badge ' + state;
    badge.style.display = 'flex';
    _gsUpdateRefreshBtnVisibility(state);
    badge.dataset.title = (state === 'sys_synced' || state === 'db_synced')
        ? _gsPublishTooltip(state.split('_')[0], _gsSyncIsPublished)
        : (_GS_SYNC_TOOLTIPS[state] || '');
    label.textContent = _GS_SYNC_LABELS[state] || state;

    // Banner "Atualização disponível" (mesmo padrão visual de #gn-update-banner no editor
    // GN, classe .gn-update-banner reaproveitada - CSS já é global à página) - só faz
    // sentido quando: (1) a camada JÁ está publicada de verdade (_gsSyncIsPublished) -
    // sem isso não há nada pra buscar no GeoServer, o caminho certo é "Publicar Camada"
    // (já indicado no modal do badge, ver _GS_SYNC_MODALS); (2) o estado é
    // especificamente 'sys_modified', não 'db_modified' - "Atualizar Camada" (pull) exige
    // sessão ativa (fetch_published_featuretype/fetch_layer_styles chamam
    // _get_rest_session()), e 'db_modified' significa "ainda sem login" (ver
    // _checkGsSyncNow) - mostrar o banner nesse estado deixava o botão clicável só pra
    // falhar com "Sessão não foi inicializada" na hora.
    var updateBanner = document.getElementById('gs-update-banner');
    if (updateBanner) {
        var showBanner = (state === 'sys_modified') && _gsSyncIsPublished;
        updateBanner.style.display = showBanner ? 'flex' : 'none';
    }
}

// Botão "Atualizar agora" do banner (ver setGsBadge) - reusa a mesma ação e confirmação
// do menu "Serviços > Atualizar Camada", só entrando por um atalho visível direto no
// painel quando a divergência já foi detectada.
function applyGsLayerUpdate() {
    pullGsLayerFromServer();
}

function dismissGsUpdateBanner() {
    var banner = document.getElementById('gs-update-banner');
    if (banner) banner.style.display = 'none';
}

function _gsSnapshotFromSaved(info) {
    var adds = [];
    if (info && info.saved_style_additional_json) {
        try {
            adds = JSON.parse(info.saved_style_additional_json);
        } catch (e) {
            console.error(e);
        }
    }
    return JSON.stringify({
        workspace: (info && info.saved_workspace) || '',
        datastore: (info && info.saved_datastore) || '',
        published_name: (info && info.saved_published_name) || '',
        title: (info && info.saved_title) || '',
        abstract: (info && info.saved_abstract) || '',
        keywords: (info && info.saved_keywords) || [],
        style_source: (info && info.saved_style_source) || '',
        style_name: (info && info.saved_style_name) || '',
        style_additional: adds
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
// Chamada também pelo badge combinado do editor de metadados (checkGsPublishStatus,
// geonetwork.js), não só pelo painel "Configurar Camada" - por isso não depende de
// #gs-layer-card existir; sem o painel GS aberto não tem "formulário na tela" pra
// comparar, então usa o que já está salvo no banco (info.saved_*) como base.
//
// Chamada "fire and forget" - check_gs_sync roda em background no lado Python (QThread,
// RNF02) e o resultado chega depois pelo sinal gs_sync_checked (ver _onGsSyncChecked
// abaixo), não por um callback direto aqui: a primeira versão chamava a REST API do
// GeoServer direto no slot pyqtSlot (síncrono), o que travava o painel GS inteiro
// enquanto esperava a resposta de rede.
function _checkGsSyncOnline(info) {
    if (!_isLogged || typeof gsBridge === 'undefined' || !gsBridge.check_gs_sync) return;
    if (!info || !info.saved_workspace || !info.saved_datastore || !info.saved_published_name) return;
    var ws = info.saved_workspace, ds = info.saved_datastore, name = info.saved_published_name;
    var key = _activeLayerName + '|' + ws + '|' + ds + '|' + name;
    if (_gsOnlineLastCheckedKey === key && (Date.now() - _gsOnlineLastCheckedAt) < _GN_RECHECK_STALE_MS) return;
    if (_gsOnlineInFlightKey === key) return; // já pedido, esperando resposta - ver _gsOnlineInFlightKey
    _gsOnlineExpectedKey = key;
    _gsOnlineInFlightKey = key;
    var d, styleJson;
    if (document.getElementById('gs-layer-card')) {
        d = _gsCollectFormState();
        styleJson = JSON.stringify(_gsCollectStyleConfig());
    } else {
        d = {
            title: info.saved_title || '', abstract: info.saved_abstract || '', keywords: info.saved_keywords || []
        };
        var savedStyle = { source: info.saved_style_source || '', name: info.saved_style_name || '' };
        if (info.saved_style_additional_json) {
            try { savedStyle.additional = JSON.parse(info.saved_style_additional_json); } catch (e) { }
        }
        styleJson = JSON.stringify(savedStyle);
    }
    gsBridge.check_gs_sync(ws, ds, name, d.title, d.abstract, d.keywords, styleJson);
}

// Força uma nova checagem AO VIVO agora, ignorando o cache de 60s (_gsOnlineLastCheckedKey/
// _GN_RECHECK_STALE_MS) - normalmente a checagem ao vivo só roda quando o painel/camada
// carrega ou quando o login muda (ver _onGsAuthStateChangedForSync), então o badge podia
// ficar preso num "Modificado" desatualizado até um desses dois momentos acontecerem de
// novo. Chamada depois de uma falha em "Atualizar Camada"/"Atualizar Estilo" (ver
// _initGsBridge) - se a falha foi porque o destino salvo não existe mais de verdade no
// GeoServer, o badge corrige sozinho pra "Não Encontrado" na hora, em vez do usuário só
// descobrir isso pelo texto de erro da chamada REST.
function _gsForceLiveRecheck() {
    _gsOnlineLastCheckedKey = null;
    _checkGsSyncOnline(_gsLayerInfo);
}

// Botão "↻" ao lado do badge (geoserver.html) - único jeito de sair do estado "Erro ao
// verificar"/de um resultado desatualizado (falha de rede/SSL/403 intermitente na
// checagem ao vivo contra o GeoServer/GeoNetwork) sem fechar e reabrir o plugin inteiro.
function refreshGsSync() {
    if (!document.getElementById('gs-layer-card')) return;
    _gsOnlineInFlightKey = null; // libera mesmo se uma checagem anterior ainda não respondeu (ex.: presa num erro de rede lento)
    _checkGsSyncNow(); // nível banco - local, instantâneo, sem custo de rede
    _gsForceLiveRecheck(); // nível sistema - ignora o cache de 60s e força uma checagem de verdade
}

// Chamada por publish/"Continuar Depois"/pull/atualizar estilo (ver _initGsBridge) assim
// que qualquer uma dessas ações CONFIRMA um estado novo de verdade (setGsBadge('..._synced')
// logo em seguida) - descarta qualquer checagem AO VIVO (check_gs_sync) que já estava em
// voo ANTES da ação terminar. Sem isso, uma resposta atrasada (pedida um pouco antes,
// ainda refletindo o estado ANTIGO) podia chegar DEPOIS e sobrescrever o badge recém-
// confirmado com "Modificado" - é o banner "Atualização disponível" reaparecendo logo
// depois de um pull que acabou de sincronizar tudo. Só zera _gsOnlineExpectedKey
// (_onGsSyncChecked descarta por key não bater, ver ali) - o cache de 60s
// (_gsOnlineLastCheckedKey) tem que zerar junto, senão fica com o timestamp de uma
// checagem que nunca vai ser aceita, e a próxima tentativa de verdade é pulada por
// "já verificado recentemente".
function _gsInvalidatePendingLiveCheck() {
    _gsOnlineExpectedKey = null;
    _gsOnlineLastCheckedKey = null;
}

// Sinal gs_sync_checked (ver _initGsBridge) - resultado de check_gs_sync, chegando de
// forma assíncrona (não como retorno/callback direto de uma chamada). Valida contra
// _gsOnlineExpectedKey (camada+destino no momento em que _checkGsSyncOnline disparou a
// checagem) em vez de comparar só contra _gsLayerInfo - isso porque quem pediu a checagem
// pode ter sido o painel GS OU o badge combinado do editor de metadados
// (checkGsPublishStatus, geonetwork.js), e o segundo caso não tem #gs-layer-card/
// _gsLayerInfo pra validar contra. Atualiza os dois lugares que dependem desse resultado,
// cada um só se estiver de fato na tela agora.
function _onGsSyncChecked(result) {
    if (!result) return;
    var state = result.state;
    var key = _activeLayerName + '|' + result.workspace + '|' + result.datastore + '|' + result.published_name;
    if (_gsOnlineInFlightKey === key) _gsOnlineInFlightKey = null; // libera a key ANTES do check de obsolescência abaixo - senão uma resposta descartada por ser antiga travava novas checagens pra essa key pra sempre
    if (key !== _gsOnlineExpectedKey) return; // resposta obsoleta ou não solicitada por essa checagem

    if (state && state !== 'error') {
        _gsOnlineLastCheckedKey = key;
        _gsOnlineLastCheckedAt = Date.now();
    }

    // Painel "Configurar Camada" aberto pra essa mesma camada/destino - atualiza o
    // snapshot/badge dele.
    if (document.getElementById('gs-layer-card') && _gsLayerInfo &&
        result.workspace === _gsLayerInfo.saved_workspace &&
        result.datastore === _gsLayerInfo.saved_datastore &&
        result.published_name === _gsLayerInfo.saved_published_name) {
        if (state === 'sys_synced') {
            _gsSyncHasRecord = true;
            _gsSyncSnapshot = JSON.stringify(_gsCollectFormState());
            _gsCaptureSnapshotRawNames();
            _gsSyncIsPublished = true;
            setGsBadge('sys_synced');
        } else if (state === 'sys_modified') {
            // Diverge do que está DE FATO publicado agora - monta o snapshot a partir do
            // conteúdo AO VIVO (não do banco), pra digitação seguinte (_checkGsSyncNow,
            // local) continuar comparando contra a fonte mais confiável disponível.
            // Estilo fica FORA da checagem ao vivo (fetch_published_featuretype não sabe
            // de estilo) - copia os campos de estilo do formulário atual pro snapshot,
            // senão todo compare local seguinte acusaria "Modificado" só pela ausência
            // das chaves style_* no snapshot.
            _gsSyncHasRecord = true;
            var liveStyle = _gsCollectFormState();
            _gsSyncSnapshot = JSON.stringify({
                workspace: result.workspace, datastore: result.datastore, published_name: result.published_name,
                title: result.title || '', abstract: result.abstract || '', keywords: result.keywords || [],
                style_source: liveStyle.style_source, style_name: liveStyle.style_name,
                style_additional: liveStyle.style_additional
            });
            _gsCaptureSnapshotRawNames();
            _gsSyncIsPublished = true;
            setGsBadge('sys_modified');
        } else if (state === 'sys_not_found') {
            // O banco achava que estava publicado, mas não existe mais lá (removido, ou
            // nunca chegou a publicar de verdade - só "Continuar Depois").
            _gsSyncHasRecord = false;
            _gsSyncIsPublished = false;
            setGsBadge('sys_not_found');
        } else if (state === 'error') {
            // Falha de rede/SSL/403 intermitente na checagem ao vivo - não mexe em
            // _gsSyncSnapshot/_gsSyncHasRecord/_gsSyncIsPublished (não sabemos nada de
            // novo, só que a tentativa falhou); só troca o badge visualmente pra avisar
            // e liberar o botão "↻" (ver _gsUpdateRefreshBtnVisibility/refreshGsSync).
            setGsBadge('error');
        }
        updateGsFormProgress();
        _gsApplyFieldLockState();
    }

    // Badge combinado do editor GN (_gsBadgeState, ver checkGsPublishStatus/geonetwork.js) -
    // reflete o mesmo resultado ao vivo, mesmo com o painel GS fechado (é o próprio motivo
    // dessa checagem existir aqui: sem isso, o editor continuava mostrando "GeoServer:
    // Publicado" pra uma camada cujo resumo mudou direto no GeoServer, ou que só foi salva
    // no banco sem republicar de verdade).
    if (state && state !== 'error' && typeof _gsLastCheckedLayerKey !== 'undefined') {
        _gsLastBadgeState = state;
        _gsLastBadgePublished = (state === 'sys_synced' || state === 'sys_modified');
        _gsLastCheckedLayerKey = _activeLayerName;
        _gsLastCheckedAt = Date.now();
        if (document.getElementById('f-title')) {
            _gsBadgeState = state;
            _refreshGnBadgeLabel();
        }
    }
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
        var syncedEntry = _GS_SYNC_MODALS[state];
        Modal.alert(
            _gsPublishModalMessage(tierPrefix, _gsSyncIsPublished),
            syncedEntry.title,
            syncedEntry.type
        );
        return;
    }
    var entry = _GS_SYNC_MODALS[state];
    if (!entry) return;
    Modal.alert(entry.message, entry.title, entry.type);
}

// Progresso de preenchimento do painel GS - mesmo componente circular do editor GN
// (updateFormProgress), cobrindo TODOS os campos editáveis das duas abas (Destino:
// workspace/datastore/nome; Identificação: título/resumo/palavras-chave), não só os 3
// obrigatórios pra publicar (workspace/datastore/nome, ver confirmGsPublish) - antes
// título/resumo/palavras-chave não entravam na conta, então o círculo podia mostrar 100%
// com esses campos vazios. Lê os valores BRUTOS do DOM (não _gsCollectFormState(), cujo
// `title` cai pro published_name quando vazio - contaria como preenchido mesmo sem o
// usuário ter digitado nada ali).
function updateGsFormProgress() {
    var wsEl = document.getElementById('gs-workspace');
    var dsEl = document.getElementById('gs-datastore');
    var nameEl = document.getElementById('gs-layer-name');
    var titleEl = document.getElementById('gs-layer-title');
    var abstractEl = document.getElementById('gs-layer-abstract');
    var required = [
        wsEl && wsEl.value,
        dsEl && dsEl.value,
        nameEl && nameEl.value.trim(),
        titleEl && titleEl.value.trim(),
        abstractEl && abstractEl.value.trim(),
        _gsKeywords.length > 0
    ];
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
    // O Nome publicado precisa ser IDÊNTICO ao nome da tabela no banco - é assim que o
    // GeoServer localiza os dados (ver register_postgis_featuretype, nativeName vs name).
    // Divergir aqui publica uma camada "vazia"/sem achar a tabela certa.
    if (_gsLayerInfo.table && d.published_name !== _gsLayerInfo.table) {
        Modal.alert(
            'O Nome da camada publicada ("' + escHtml(d.published_name) + '") precisa ser idêntico ao nome ' +
            'da tabela no banco ("' + escHtml(_gsLayerInfo.table) + '") - é assim que o GeoServer localiza os ' +
            'dados. Ajuste o campo (aba Identificação, botão "Usar nome da tabela") antes de publicar.',
            'Aviso', 'warning'
        );
        return;
    }
    if (_gsTableCheckState === false) {
        Modal.alert('A tabela "' + escHtml(_gsLayerInfo.table) + '" não foi encontrada nesse datastore. Confira o Workspace/Datastore escolhidos (aba Destino) antes de publicar.', 'Aviso', 'warning');
        return;
    }
    var style = _gsCollectStyleConfig();
    var styleError = _gsValidateStyleConfig(style);
    if (styleError) {
        Modal.alert(styleError, 'Aviso', 'warning');
        return;
    }

    Modal.confirm(
        'Publicar a camada "' + escHtml(_gsLayerInfo.name) + '" como "' + escHtml(d.published_name) +
        '" no workspace "' + escHtml(d.workspace) + '" (datastore "' + escHtml(d.datastore) + '")?' +
        (style.source ? ('<br><br>Estilo padrão: ' + _gsDescribeStyle(style) + '.') : '') +
        _gsStyleBestEffortNote(style),
        function () {
            _gsLastPublishWorkspace = d.workspace;
            _showActionLoading('Publicando no GeoServer...');
            gsBridge.publish_layer(d.workspace, d.datastore, d.published_name, d.title, d.abstract, d.keywords, JSON.stringify(style));
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
        'Deseja realmente salvar o destino de publicação da camada atual no banco de dados?<br><br>Isso não publica a camada no GeoServer ainda.',
        function () {
            _saveGsDraftNow(); // garante que o rascunho local (arquivo) também está com o mais recente
            gsBridge.save_destination_now(d.workspace, d.datastore, d.published_name, d.title, d.abstract, d.keywords,
                JSON.stringify(_gsCollectStyleConfig()));
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
    _setGsAutoDetectSpinner(true);
    _setGsAutoDetectStatus('Procurando em todos os workspaces/datastores... isso pode demorar alguns segundos.');
    gsBridge.find_datastore_for_active_layer();
}

function _setGsAutoDetectSpinner(show) {
    var spinner = document.getElementById('gs-autodetect-spinner');
    if (spinner) spinner.style.display = show ? '' : 'none';
    _updateGsAutodetectBoxVisibility();
}

function _setGsAutoDetectStatus(msg) {
    var el = document.getElementById('gs-autodetect-status');
    if (el) el.textContent = msg || '';
    _updateGsAutodetectBoxVisibility();
}

// Caixa de status (borda tracejada) só aparece quando há algo pra mostrar -
// spinner rodando, texto de status, ou lista de candidatos.
function _updateGsAutodetectBoxVisibility() {
    var box = document.getElementById('gs-autodetect-box');
    if (!box) return;
    var spinner = document.getElementById('gs-autodetect-spinner');
    var status = document.getElementById('gs-autodetect-status');
    var candidates = document.getElementById('gs-autodetect-candidates');
    var spinnerOn = spinner && spinner.style.display !== 'none';
    var hasStatus = status && status.textContent.trim();
    var hasCandidates = candidates && candidates.style.display !== 'none';
    box.style.display = (spinnerOn || hasStatus || hasCandidates) ? '' : 'none';
}

function _onGsAutoDetectDone(matches, error) {
    _gsAutoDetectRunning = false;
    var btn = document.querySelector('.gs-autodetect-btn');
    if (btn) btn.disabled = false;
    _setGsAutoDetectSpinner(false);

    if (error) {
        _setGsAutoDetectStatus('');
        Modal.alert(error, 'Erro', 'error');
        return;
    }
    if (!matches || !matches.length) {
        _setGsAutoDetectStatus('Tabela "' + ((_gsLayerInfo && _gsLayerInfo.table) || '') + '" não foi encontrada em nenhum Workspace/Datastore visível no Geohab.');
        return;
    }
    if (matches.length === 1) {
        _setGsAutoDetectStatus('Encontrado em: ' + matches[0].workspace + ' + ' + matches[0].datastore);
        _selectGsWorkspaceDatastore(matches[0].workspace, matches[0].datastore);
        return;
    }
    _setGsAutoDetectStatus('Encontrado em: ' + matches.length + ' datastores diferentes - escolha um:');
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
    _updateGsAutodetectBoxVisibility();
}

function _pickGsAutoDetectCandidate(idx) {
    var wrap = document.getElementById('gs-autodetect-candidates');
    var m = wrap && wrap._gsCandidates && wrap._gsCandidates[idx];
    if (!m) return;
    wrap.style.display = 'none';
    _updateGsAutodetectBoxVisibility();
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
