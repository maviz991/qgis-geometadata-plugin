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
var _gsPendingSyncedBaselineCapture = false; // ver _gsCaptureSyncedBaselineIfPending
var _gsMetadataLinkUrl = ''; // URL completa do Link de Metadados (fallback "sem camada ativa") - ver gs_layer_pulled/_saveGsDraftNow/_loadGsDraft
var _gsSyncSourceIsDb = false; // true só quando _gsSyncHasRecord veio do banco de verdade (info.saved_workspace, _renderGsLayerCard) - ver _checkGsSyncNow

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
    gsBridge.gs_published_featuretypes_ready.connect(function (names, error) {
        _renderGsLayerPickerFiltered(names, error);
    });
    gsBridge.gs_find_datastore_progress.connect(function (msg) {
        _setGsAutoDetectStatus(msg);
    });
    gsBridge.gs_find_datastore_done.connect(function (matches, error) {
        _onGsAutoDetectDone(matches, error);
    });
    gsBridge.gs_metadata_updated.connect(function (success, message) {
        _hideActionLoading();
        if (success) {
            _gsForceLiveRecheck();
            // message vazia = sucesso completo, sem ressalvas (mesma convenção de
            // gs_publish_done/_GsUpdateMetadataWorker) - só o estilo falhando preenche
            // message aqui, com os metadados já atualizados de verdade.
            Modal.alert(message || 'Dados atualizados no GeoServer.', message ? 'Atualizado com Ressalvas' : 'Atualizado', message ? 'warning' : 'success');
        } else {
            Modal.alert(message, 'Erro', 'error');
        }
    });

    gsBridge.gs_publish_done.connect(function (success, message, publishedName, wmsUrl, wfsUrl) {
        _hideActionLoading();
        if (!success) {
            Modal.alert(message || 'Falha ao publicar no GeoServer.', 'Erro', 'error');
            return;
        }
        // Publicado - o destino já foi gravado no banco (GeoServerBridge._on_publish_done),
        // então o rascunho local não faz mais sentido aqui. clearTimeout aqui é
        // necessário: se o usuário editou um campo e clicou "Publicar" dentro de 1.5s
        // (debounce de _scheduleGsDraftSave), o timer pendente disparava DEPOIS desse
        // clear_draft() e recriava o rascunho que acabou de ser apagado.
        clearTimeout(_gsDraftTimer);
        gsBridge.clear_draft();
        _gsInvalidatePendingLiveCheck(); // ver definição - descarta checagem ao vivo desatualizada de antes da publicação
        _flashGsRefreshBtn(); // ver definição - deixa o botão "↻" visível por uns instantes, momento onde erros de rede mais apareceram nos testes
        if (message) {
            Modal.alert(message, 'Publicado com Ressalvas', 'warning');
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
        // Re-busca do banco em vez de reconstruir o snapshot na mão a partir do formulário
        // (como era antes) - o formulário tem campos que só resolvem de forma assíncrona
        // (nome sanitizado via RF04, ~200ms depois de preenchidos) e o snapshot podia ser
        // capturado antes disso terminar, deixando o badge preso em "Modificado" mesmo com
        // a publicação tendo dado certo (usuário só via "Sincronizado" de verdade fechando
        // e reabrindo o plugin, que força tudo a vir fresco do banco). _loadGsLayerInfo()
        // relê get_active_layer_publish_info() - a MESMA fonte de verdade usada ao reabrir
        // o plugin - e _renderGsLayerCard() (chamado por ela) já monta o snapshot a partir
        // de info.saved_* (via _gsSnapshotFromSaved), nunca do formulário cru, então não
        // sofre dessa corrida; cobre style_source/style_name vazios sozinho no caso
        // "Publicado com Ressalvas" também, já que _on_publish_done (Python) só grava esses
        // campos no banco quando o estilo realmente aplicou. O navigate('editor') PRECISA
        // esperar esse callback - _renderGsLayerCard() (chamado por _loadGsLayerInfo) só
        // atualiza o estado de sync se #gs-layer-card ainda existir; navegar ANTES da
        // resposta assíncrona chegar destruía o painel GS e a atualização virava um no-op
        // silencioso (era exatamente por causa dessa ordem que o badge só corrigia sozinho
        // fechando e reabrindo o plugin de novo).
        _loadGsLayerInfo(function () {
            _loadGsDraft();
            navigate('editor');
        });
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
    // "Serviços > Baixar Camada" / banner "Atualização disponível" (ver
    // pullGsLayerFromServer) - PULL: busca o que está DE FATO publicado no GeoServer e
    // substitui o formulário local por isso.
    gsBridge.gs_layer_pulled.connect(function (success, data, error) {
        _hideActionLoading();
        if (!success) {
            // Reverifica ao vivo na hora em vez de esperar o próximo login/reabertura do
            // painel (mesmo padrão de gs_metadata_updated/gs_publish_done em caso de erro).
            _gsForceLiveRecheck();
            Modal.alert(error || 'Falha ao buscar os dados publicados no GeoServer.', 'Erro', 'error');
            return;
        }
        var titleEl = document.getElementById('gs-layer-title');
        var abstractEl = document.getElementById('gs-layer-abstract');
        if (titleEl) titleEl.value = data.title || '';
        if (abstractEl) abstractEl.value = data.abstract || '';
        
        // No fluxo via WMS/WFS, o workspace, datastore e nome vêm preenchidos do worker.
        // Se a camada não estava ativa, a UI pode estar vazia, então preenchemos agora.
        // _gsApplyKnownWorkspaceDatastore semeia os dois diretamente (opção única, sem
        // depender de list_workspaces()/list_datastores() já ter respondido) - a versão
        // anterior usava _clickGsSuggestionItem('gs-workspace-wrap', ...) sem checar o
        // retorno: se a lista de workspaces ainda não tinha carregado (comum logo após
        // abrir o painel sem camada ativa), o clique falhava em silêncio e #gs-workspace
        // ficava vazio bem no momento em que _gsApplyStyleChoice('existing', ...) (abaixo)
        // chamava _gsLoadStylesList() - que busca só estilos GLOBAIS sem um workspace,
        // perdendo o estilo padrão sempre que ele vive dentro de um workspace (o caso mais
        // comum). Estilos adicionais (_gsAdditionalStyles) não dependiam dessa lista, por
        // isso vinham certos mesmo com esse bug - só o padrão sumia.
        if (data.workspace) {
            _gsApplyKnownWorkspaceDatastore(data.workspace, data.datastore || '');
        }
        if (data.published_name) {
            var nameEl = document.getElementById('gs-layer-name');
            if (nameEl) {
                nameEl.value = data.published_name;
                nameEl.dataset.sanitized = data.published_name;
            }
        }
        
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
        
        // uuid do metadado GN: prioriza o que veio JUNTO com o pull (data.metadata_uuid -
        // extraído do metadataLink REAL já gravado nessa camada no GeoServor, ver
        // GeoServerService._extract_metadata_uuid/fetch_published_featuretype) em vez de
        // _gnSyncUuid cru (variável de sessão setada pelo editor GN em "Baixar Metadado" -
        // podia ser de OUTRO registro qualquer puxado antes no GN, sem relação nenhuma com
        // ESSA camada específica; usuário confirmou ver dois UUIDs diferentes pra mesma
        // camada, um existindo de verdade no GN e outro não). Também RESSINCRONIZA
        // _gnSyncUuid com esse valor de verdade - próximas ações (Atualizar Dados,
        // _gsTryNoActiveLayerUpdate) e o rascunho (_saveGsDraftNow, logo abaixo) passam a
        // usar o uuid certo daqui pra frente, não só a prévia.
        if (typeof _gnSyncUuid !== 'undefined' && data.metadata_uuid) {
            _gnSyncUuid = data.metadata_uuid;
        }
        // Pedido do usuário: se esse pull CONFIRMOU um metadado vinculado no GeoNetwork
        // (data.metadata_uuid só vem preenchido depois de uma verificação/busca reversa
        // de verdade - ver _resolve_gn_metadata_uuid, geoserver_workers.py), oferece
        // popular o Editor de Metadados com esse registro automaticamente na próxima vez
        // que ele carregar (mesmo padrão de window._pendingGsDistLayer - GS publica ->
        // vincula Distribuição no GN - só que na direção oposta: GS puxa -> popula o GN).
        // _applyPendingGnPullIfAny (geonetwork.js) sempre confirma antes de sobrescrever o
        // formulário (reusa pullGnRecord, mesmo aviso de sempre) - nunca substitui nada
        // sem perguntar.
        if (data.metadata_uuid) {
            window._pendingGnPullUuid = data.metadata_uuid;
        }
        // Mesmo formato de link clicável que a prévia com camada ativa usa
        // (_renderGsLayerCard, info.metadata_link_url) - antes essa aqui só mostrava
        // "UUID xxx" cru, sem link nenhum, inconsistente com a outra.
        _gsMetadataLinkUrl = data.metadata_link_url || _gsMetadataLinkUrl;
        var metaLinkBox = document.getElementById('gs-metadata-link-preview');
        if (metaLinkBox) {
            if (_gsMetadataLinkUrl) {
                metaLinkBox.innerHTML = 'Será vinculado ao atualizar: <a href="' + escHtml(_gsMetadataLinkUrl) + '" target="_blank">' + escHtml(_gsMetadataLinkUrl) + '</a>';
            } else if (typeof _gnSyncUuid !== 'undefined' && _gnSyncUuid) {
                // Fallback raro: uuid restaurado de um rascunho antigo (salvo antes desse
                // fix) sem a URL completa junto - mostra ao menos o uuid cru.
                metaLinkBox.innerHTML = 'Será vinculado ao atualizar: UUID ' + escHtml(_gnSyncUuid);
            }
        }
        
        // _gsSyncHasRecord/_gsSyncIsPublished PRECISAM ser setados ANTES de
        // _saveGsDraftNow() - synced_tier (rascunho, ver Bug 45) é calculado a partir
        // desses dois flags NO MOMENTO do save; salvar antes de setá-los (like era antes)
        // gravava synced_tier vazio sempre que o pull era o PRIMEIRO dessa camada (flags
        // ainda no valor pré-pull, false/false) - o badge "Sincronizado" recém-obtido se
        // perdia ao navegar pra outro painel e voltar, ou reabrir o plugin (voltava
        // "Modificado" sem motivo, já que o rascunho não tinha como saber que era pra
        // restaurar sincronizado).
        _gsSyncHasRecord = true;
        _gsSyncSnapshot = JSON.stringify(_gsCollectFormState());
        _gsCaptureSnapshotRawNames();
        _gsSyncIsPublished = true;
        // Faltava aqui (bug: pull nunca travava Nome/Título com cadeado, mesmo confirmando
        // que a camada JÁ está publicada de verdade no GeoServer - único outro chamador de
        // _gsApplyFieldLockState() era o handler de sucesso de "Publicar Camada", nunca o
        // de pull). _gsSyncIsPublished acabou de virar true incondicionalmente em QUALQUER
        // pull bem-sucedido, então Nome sempre trava (usuário pediu explicitamente isso) e
        // Título trava junto quando a camada já tinha um de verdade.
        _gsApplyFieldLockState();
        _gsInvalidatePendingLiveCheck(); // ver definição - senão uma checagem em voo de ANTES do pull chega depois com "Modificado" desatualizado e o banner "Atualização disponível" reaparece
        // Preenchimento programático não dispara input/change (o que aciona o rascunho
        // por debounce) - salva na hora, mesmo motivo de pullGsAbstractKeywordsFromGn.
        _saveGsDraftNow();
        _flashGsRefreshBtn();
        setGsBadge((_isLogged ? 'sys' : 'db') + '_synced');
        _gsLastCheckedLayerKey = null; // idem publish_done/destination_saved - invalida o cache do badge combinado do editor
        updateGsFormProgress();
        // Sincroniza o seletor "Selecionar camada publicada" (aba Destino) com o destino
        // que acabou de ser puxado - incondicional, não só quando data.workspace vem
        // preenchido (só acontece se _GsPullLayerByWmsNameWorker/redetecção rodaram; o
        // caminho mais comum de "Serviços > Baixar Camada"/"Atualizar agora" com destino
        // já conhecido não redetecta nada, então essa sincronização não rodaria sozinha
        // sem essa chamada explícita aqui). Workspace/Datastore/Nome já estão todos
        // aplicados no formulário nesse ponto - lê o estado atual, não precisa de dado
        // extra do pull.
        var pickerWs = document.getElementById('gs-workspace');
        var pickerDs = document.getElementById('gs-datastore');
        _gsRefreshLayerPickerForDestination(pickerWs ? pickerWs.value : '', pickerDs ? pickerDs.value : '');
        Modal.alert('Formulário atualizado com o que está publicado no GeoServer agora.', 'Camada Atualizada', 'success');
    });
    // Resultado de search_geoserver (fire-and-forget, RNF02 - antes era bloqueante na main
    // thread e travava a tela ao abrir a busca ou digitar enquanto a 1ª busca da sessão
    // ainda estava em voo). Três consumidores possíveis, cada um só atualiza se o próprio
    // elemento existir na tela agora: a aba "Recursos associados" do editor GN
    // (#dist-suggestions, searchGeoServer/geonetwork.js), a busca de camadas do painel GS
    // via modal (#gs-search-results, openGsSearchModal) e o seletor embutido na aba
    // Destino (#gs-layer-picker-wrap, _renderGsLayerPicker, mais abaixo neste arquivo).
    gsBridge.gs_search_ready.connect(function (results, error) {
        if (document.getElementById('dist-suggestions')) {
            var spinner = document.getElementById('dist-spinner');
            if (spinner) spinner.style.display = 'none';
            _distSugg = results || [];
            renderDistSugg();
        }
        if (document.getElementById('gs-search-results')) {
            _renderGsSearchResults(results, error);
        }
        if (document.getElementById('gs-layer-picker-wrap')) {
            _renderGsLayerPicker(results, error);
        }
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
    // Popula o seletor "Selecionar camada publicada" (aba Destino) - mesma busca (WMS
    // GetCapabilities, pública, sem exigir login) do modal "Baixar Camada"/aba Recursos
    // associados do GN, só que direto aqui, sem precisar abrir nada - pedido do usuário
    // pra deixar essa aba 100% independente de camada QGIS ativa. Cacheada no lado Python
    // (GeoServerBridge._geoserver_layers_cache) - só a 1ª chamada da sessão bate na rede.
    if (typeof gsBridge !== 'undefined' && gsBridge.search_geoserver) gsBridge.search_geoserver('');
    // Prioridade de preenchimento: online (GN, dentro de info.title/abstract/keywords já
    // resolvido no lado Python) > banco (info.saved_*, get_active_layer_publish_info) >
    // rascunho local - nessa ordem, independente de estar logado ou não (o banco só
    // depende da credencial da própria camada, não de sessão GeoServer/GeoNetwork). Por
    // isso _loadGsLayerInfo() roda primeiro e só depois _loadGsDraft() entra, preenchendo
    // apenas os campos que o banco deixou vazios (camada nunca salva/publicada de verdade).
    _loadGsLayerInfo(function () {
        _loadGsDraft();
        _applyPendingGsPullIfAny();
    });
}

// Caminho oposto de window._pendingGnPullUuid (geonetwork.js - GS puxa, popula o GN): um
// pull de metadado no editor GN pode ter achado um link WMS/WFS já gravado (Distribuição)
// apontando pra uma camada publicada no GeoServer - se achou, oferece popular o painel GS
// com ela também, na próxima vez que abrir (mesmo padrão de "pendente + só aplica quando
// o painel termina de carregar" já usado nos outros dois casos). Pedido do usuário: "o
// caminho oposto é verdade também". Confirmação condicional ao estado do badge de sync
// (mesmo raciocínio de _applyPendingGnPullIfAny em geonetwork.js): se o painel GS já está
// sincronizado, popula direto (nada a perder); senão confirma com mensagem específica.
function _applyPendingGsPullIfAny() {
    var wsLayerName = window._pendingGsPullWsLayerName;
    window._pendingGsPullWsLayerName = null;
    if (!wsLayerName) return;
    if (!document.getElementById('gs-layer-card')) return; // painel já foi trocado
    if (!_isLogged) return; // sem sessão não dá pra buscar no GeoServer mesmo
    var sep = wsLayerName.indexOf(':');
    if (sep < 0) return;
    var workspace = wsLayerName.slice(0, sep);
    var name = wsLayerName.slice(sep + 1);
    // Já é esse mesmo destino no formulário (ex.: puxou no GN um registro que já
    // corresponde à camada ativa/já preenchida) - nada a fazer, evita perguntar à toa.
    if (_gsCurrentLayerPickerKey() === wsLayerName) return;
    if (_gsIsSyncedNow()) {
        _doPullGsLayerByName(workspace, name);
        return;
    }
    Modal.confirm(
        'O metadado que você acabou de puxar no Geohab está vinculado à camada "<strong>' +
        escHtml(wsLayerName) + '</strong>" no GeoServer. O painel de Configurar Camada tem ' +
        'conteúdo ainda não sincronizado - trazer essa camada vai substituir o que está no ' +
        'formulário agora. Continuar?',
        function () { _doPullGsLayerByName(workspace, name); },
        'Camada Vinculada Encontrada'
    );
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
        style_additional: _gsAdditionalStyles.slice(),
        // Marca se ESTE estado reflete um pull confirmado (Baixar Camada) - usado só pelo
        // fallback "sem camada ativa" em _loadGsDraft pra restaurar o badge de status
        // depois de fechar/reabrir o plugin. Sem camada ativa, save_publish_destination
        // nunca roda (exige um QgsMapLayer de verdade pra abrir a conexão no banco), então
        // não existe registro nenhum pra _renderGsLayerCard recalcular o badge a partir
        // dele - o painel reabria "cru" (_gsSyncSnapshot nunca inicializado,
        // _markGsModifiedIfNeeded silenciosamente não fazia nada) até puxar de novo.
        synced_tier: (_gsSyncHasRecord && _gsSyncIsPublished) ? (_isLogged ? 'sys' : 'db') : '',
        // uuid do metadado GN (_gnSyncUuid, geonetwork.js, mesmo escopo global) associado a
        // este destino - também é variável JS pura, perdida ao fechar/reabrir. Persistido
        // aqui pra "Atualizar Metadados" (fallback sem camada ativa) continuar sabendo pra
        // qual registro montar o Link de Metadados mesmo depois de reabrir o plugin (ver
        // update_layer_metadata/_build_metadata_link_url).
        metadata_uuid: (typeof _gnSyncUuid !== 'undefined' && _gnSyncUuid) || '',
        // URL completa (não só o uuid) - permite restaurar o link CLICÁVEL na prévia sem
        // precisar puxar de novo (ver _loadGsDraft/gs_layer_pulled).
        metadata_link_url: _gsMetadataLinkUrl || ''
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
                // NÃO usa onGsLayerNameInput() aqui - essa função existe pra pré-visualizar
                // a sanitização (RF04: minúsculas/sem acento) de um nome NOVO que o usuário
                // está digitando pra publicar, então gsBridge.sanitize_layer_name() sempre
                // devolve minúsculo. draft.published_name aqui já É o nome de uma camada
                // JÁ publicada (veio de um pull) - passar pela "pré-visualização de
                // sanitização" TROCAVA o valor usado de fato (_gsCollectFormState()
                // prioriza dataset.sanitized sobre .value) pela versão minúscula, mesmo
                // com o campo mostrando a capitalização certa na tela - "Atualizar agora"
                // então tentava um nome diferente do real no GeoServer (ex.:
                // "Favela_Moinho_Muro" na tela, "favela_moinho_muro" no PUT/GET -> [GS-404]
                // mesmo a camada existindo). dataset.sanitized setado direto, mesmo padrão
                // do handler gs_layer_pulled (pull de verdade) - sem re-sanitizar um nome
                // que já é exato.
                nameEl.dataset.sanitized = draft.published_name;
                var namePreview = document.getElementById('gs-layer-name-preview');
                if (namePreview) namePreview.textContent = 'Nome final: ' + draft.published_name;
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
            // Sem registro no banco (_gsSyncHasRecord ainda false aqui - _renderGsLayerCard
            // não roda esse trecho sem camada ativa), mas o rascunho veio de um pull
            // confirmado (draft.synced_tier) - usa o próprio estado recém-restaurado como
            // baseline (mesma ideia do "pull baseline" do GN, Bug 40), em vez de deixar o
            // badge sem status nenhum até o usuário puxar de novo. A flag é setada ANTES de
            // _gsQueueWorkspaceDatastore (logo abaixo) de propósito - workspace/datastore
            // podem resolver de forma SÍNCRONA (_gsWorkspaceListFailed) ou ASSÍNCRONA (lista
            // ainda carregando); setando a flag primeiro, o settling point que rodar
            // primeiro (síncrono aqui mesmo, ou um dos assíncronos em
            // _gsApplyKnownWorkspaceDatastore/_renderGsWorkspaces/_renderGsDatastores) já
            // encontra a flag `true` e captura no momento CERTO - capturar cedo demais
            // (workspace/datastore ainda vazios/"Carregando...") gravava um baseline
            // incompleto, e quando a lista finalmente respondia e preenchia os campos de
            // verdade, a comparação seguinte acusava "Modificado" à toa (ver
            // _gsCaptureSyncedBaselineIfPending).
            if (!_gsSyncHasRecord && draft.synced_tier) {
                _gsSyncHasRecord = true;
                _gsSyncIsPublished = true;
                // Esse baseline vem de um PULL (REST do GeoServer), nunca do banco - sem
                // isso, _checkGsSyncNow rotulava esse estado como "db_*" (ver comentário
                // lá) mesmo sem nenhum registro em geoserver_publish_xml, mostrando
                // "Sincronizado (banco)" quando o usuário reabria o plugin sem estar
                // logado - afirmação falsa (nem banco nem GeoServer foram checados de
                // verdade nesse momento).
                _gsSyncSourceIsDb = false;
                _gsPendingSyncedBaselineCapture = true;
            }
            if (!_gsDbHasWorkspace && draft.workspace) {
                _gsQueueWorkspaceDatastore(draft.workspace, draft.datastore);
            } else {
                _gsCaptureSyncedBaselineIfPending(); // nada pra restaurar/aguardar - resolve na hora
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
            // Restaura _gnSyncUuid (geonetwork.js) se ainda não tiver um nesta sessão - ver
            // comentário em _saveGsDraftNow. Só entra se vazio: um pull do GN feito DEPOIS
            // de abrir o painel GS (mais recente que o rascunho) não deve ser sobrescrito.
            if (draft.metadata_uuid && typeof _gnSyncUuid !== 'undefined' && !_gnSyncUuid) {
                _gnSyncUuid = draft.metadata_uuid;
                _gsMetadataLinkUrl = draft.metadata_link_url || '';
                // Reflete na prévia também (mesmo formato de link clicável de
                // gs_layer_pulled) - sem isso, o uuid restaurava certo internamente (pra
                // "Atualizar Dados" funcionar), mas a aba Identificação ficava sem mostrar
                // nada até puxar de novo.
                var restoredMetaLinkBox = document.getElementById('gs-metadata-link-preview');
                if (restoredMetaLinkBox) {
                    restoredMetaLinkBox.innerHTML = _gsMetadataLinkUrl
                        ? ('Será vinculado ao atualizar: <a href="' + escHtml(_gsMetadataLinkUrl) + '" target="_blank">' + escHtml(_gsMetadataLinkUrl) + '</a>')
                        : ('Será vinculado ao atualizar: UUID ' + escHtml(_gnSyncUuid));
                }
            }
            // Reavalia o badge: título/resumo/palavras-chave do rascunho podem ter acabado
            // de sobrepor o que o banco preencheu (ver acima) - ou, numa camada nunca salva
            // de verdade, o rascunho preencheu campos que o banco deixou vazios. Em
            // qualquer um dos casos, _gsSyncSnapshot (capturado em _renderGsLayerCard, a
            // partir do banco ou do estado pós-auto-preenchimento) continua intocado, então
            // _checkGsSyncNow() aqui compara direito contra a fonte de verdade e vira
            // "Modificado" quando for o caso.
            updateGsFormProgress();
        }
        // _checkGsSyncNow() (não _markGsModifiedIfNeeded()) de propósito, e FORA do
        // `if (draft)` acima - roda sempre, mesmo sem draft nenhum (usuário nunca salvou
        // nada) ou sem camada ativa/synced_tier pra restaurar. _markGsModifiedIfNeeded()
        // tem uma guarda (`if (_gsSyncSnapshot === null) return;`) pensada pra digitação
        // (evita recomputar a cada tecla antes do formulário carregar) - mas como TODOS os
        // outros chamadores de _checkGsSyncNow() têm essa mesma guarda (ou já garantem um
        // snapshot não-nulo), o caso "sem camada ativa e sem rascunho nenhum" nunca batia
        // em lugar nenhum que de fato mostrasse o badge 'offline' ("Não salvo") - o painel
        // ficava sem badge nenhum na tela (display:none de _loadGsLayerInfo, nunca
        // desfeito). _checkGsSyncNow() aqui, sempre, garante que pelo menos um estado
        // (mesmo que seja 'offline') apareça.
        _checkGsSyncNow();
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
    if (!workspace) { _gsCaptureSyncedBaselineIfPending(); return; } // nada pra restaurar - resolve na hora (defesa extra, ver _loadGsDraft)
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
            _gsCaptureSyncedBaselineIfPending(); // clique falhou - nada mais vai resolver isso, encerra aqui
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
    if (!wrap) { _gsCaptureSyncedBaselineIfPending(); return; } // painel já foi trocado - nada mais vai resolver isso
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
    // Esse caminho monta o <select> via innerHTML direto (não dispara 'change' nenhum),
    // então onGsDatastoreChange() nunca roda sozinho aqui - chama o filtro do seletor
    // "Selecionar camada publicada" manualmente, senão ele ficava preso na lista completa
    // (sem filtro) sempre que o destino resolve por esse caminho (ex.: sem sessão REST).
    _gsRefreshLayerPickerForDestination(workspace, datastore);
    // Workspace E datastore acabaram de ser aplicados de forma síncrona (opção única,
    // sem depender de lista nenhuma) - settling point real pro baseline adiado (ver
    // _gsCaptureSyncedBaselineIfPending). Precisa vir ANTES de _markGsModifiedIfNeeded()
    // pra já comparar contra o snapshot certo, não contra null.
    _gsCaptureSyncedBaselineIfPending();
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
    _gsResetWorkspaceDatastoreSelection(); // volta workspace/datastore pra "Selecione..."
    _gsResetStyleControls(); // estilo também é por camada
    _loadGsLayerInfo(function () {
        _loadGsDraft();
        _applyPendingGsPullIfAny();
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
            _gsResetWorkspaceDatastoreSelection(); // volta workspace/datastore pra "Selecione..."
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
        // Mesmo retângulo tracejado usado pros outros avisos do painel (.gs-status-box,
        // ver #gs-layer-name-mismatch/#gs-autodetect-box) - antes era um <span> solto, sem
        // destaque nenhum, deixando esse aviso (o mais comum: nenhuma camada ativa, ou
        // camada não vem do PostgreSQL) se perder no meio da aba.
        card.innerHTML = '<div class="gs-status-box gs-warning-text">' + escHtml((info && info.reason) || 'Nenhuma camada ativa suportada.') + '</div>';
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
        if (info.saved_published_name) {
            // Nome de uma camada JÁ publicada (banco) - precisa ficar EXATO, sem passar
            // pela pré-visualização de sanitização (onGsLayerNameInput/RF04, sempre
            // minúscula) - senão dataset.sanitized (fonte usada de fato por
            // _gsCollectFormState() pra "Atualizar agora"/publicar) diverge do nome real
            // no GeoServer mesmo com a tela mostrando a capitalização certa (mesma causa
            // do [GS-404] corrigido em _loadGsDraft() acima, ver docs_projeto/bugs.md).
            nameEl.dataset.sanitized = defaultName;
            var defaultPreview = document.getElementById('gs-layer-name-preview');
            if (defaultPreview) defaultPreview.textContent = 'Nome final: ' + defaultName;
        } else {
            // Nome NUNCA publicado (vem da tabela/camada QGIS) - aqui sim a
            // pré-visualização de sanitização é o comportamento certo, o nome final
            // publicado pode legitimamente diferir (RF04).
            onGsLayerNameInput(defaultName);
        }
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

    // Banco inacessível agora (ver _GsActiveLayerInfoWorker/fetch_saved_records) -
    // info.saved_* vêm todos vazios, mas isso NÃO significa "nada salvo pra essa camada",
    // só que não deu pra confirmar. Badge normal (abaixo) acusaria "Não Encontrado" ou
    // "Modificado" silenciosamente, escondendo que a causa é só conectividade - mostra
    // "Erro ao verificar" direto e pula a checagem AO VIVO (sem baseline confiável pra
    // comparar contra agora).
    if (info.db_error) {
        _gsSyncHasRecord = false;
        _gsSyncSnapshot = null;
        setGsBadge('error');
        updateGsFormProgress();
        return;
    }

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
    _gsSyncSourceIsDb = _gsSyncHasRecord; // registro de verdade no banco (geoserver_publish_xml) - ver _checkGsSyncNow
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
    _gsCaptureSyncedBaselineIfPending(); // workspace salvo não existe mais na lista - nada mais vai resolver isso
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
            _gsCaptureSyncedBaselineIfPending(); // datastore acabou de ser aplicado - settling point
            _markGsModifiedIfNeeded();
            updateGsFormProgress();
        } else {
            dsWrap.innerHTML = '<select id="gs-datastore"><option value="">Erro ao carregar datastores</option></select>';
            initCustomSelects();
            _gsCaptureSyncedBaselineIfPending(); // sem datastore conhecido pra aplicar - nada mais vai resolver isso
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
    // Settling point do baseline adiado (ver _gsCaptureSyncedBaselineIfPending) - a lista
    // de datastores terminou de carregar e o valor pendente (se algum) já foi aplicado
    // (ou não existia mais na lista) - de qualquer forma, o formulário não vai mudar mais
    // por causa dessa restauração específica.
    _gsCaptureSyncedBaselineIfPending();
}

// Ao escolher o datastore, confere na hora se a tabela da camada ativa está mesmo
// visível ali (list=all - a mesma lista que a tela "Publicar" do GeoServer usa). Evita
// o 400 "no attributes were specified" que só aparecia depois do clique em Publicar,
// quando o Schema do datastore é diferente do schema real da tabela no banco.
function onGsDatastoreChange(datastore) {
    _updateGsPublishButton();
    var wsEl = document.getElementById('gs-workspace');
    var workspace = wsEl ? wsEl.value : '';
    _gsRefreshLayerPickerForDestination(workspace, datastore);
    if (!datastore || !workspace || !_gsLayerInfo || !_gsLayerInfo.table) {
        _setGsTableCheck(null, '');
        return;
    }
    _setGsTableCheck(null, 'Verificando se a tabela "' + _gsLayerInfo.table + '" existe neste datastore...');
    gsBridge.list_featuretypes(workspace, datastore);
}

// Filtra o seletor "Selecionar camada publicada" (aba Destino) pro Workspace/Datastore
// atual - pedido do usuário: sem isso a lista mostra TODAS as camadas do GeoServer
// inteiro, mesmo as de outros datastores. Com os dois preenchidos, busca só as JÁ
// PUBLICADAS nesse datastore específico (list_published_featuretypes, REST - sem título,
// só o nome técnico, já que essa lista não vem do WMS); sem os dois, volta pra lista
// completa de sempre (search_geoserver, cacheada, resposta instantânea a partir da 2ª vez).
function _gsRefreshLayerPickerForDestination(workspace, datastore) {
    if (!document.getElementById('gs-layer-picker-wrap') || typeof gsBridge === 'undefined') return;
    if (workspace && datastore) {
        var wrap = document.getElementById('gs-layer-picker-wrap');
        if (wrap) {
            wrap.innerHTML = '<select id="gs-layer-picker"><option value="">Carregando camadas desse datastore...</option></select>';
        }
        if (gsBridge.list_published_featuretypes) gsBridge.list_published_featuretypes(workspace, datastore);
    } else if (gsBridge.search_geoserver) {
        gsBridge.search_geoserver('');
    }
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

// Mesmo estilo de traço (stroke="currentColor", cantos arredondados) dos outros ícones
// SVG inline do app (ver _LP_INNER_VECTOR/_LP_INNER_RASTER, app.js) - substituem o emoji
// 🔒/🔓 anterior, que destoava do resto da UI (peso/cor/alinhamento inconsistentes com
// os demais ícones, todos vetoriais).
var _GS_LOCK_ICON_LOCKED =
    '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
    '<rect x="4" y="11" width="16" height="10" rx="2"></rect>' +
    '<path d="M7.5 11V7.5a4.5 4.5 0 0 1 9 0V11"></path>' +
    '</svg>';
var _GS_LOCK_ICON_UNLOCKED =
    '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
    '<rect x="4" y="11" width="16" height="10" rx="2"></rect>' +
    '<path d="M7.5 11V7.5a4.5 4.5 0 0 1 8.5-2"></path>' +
    '</svg>';

// Tooltip do cadeado (data-title, ver initGlobalTooltips/app.js - mesmo sistema dos
// badges de sync, não o title nativo do navegador) - texto curto explicando o PORQUÊ do
// campo estar travado (versão resumida das mensagens de _gsToggleFieldLock acima) e o que
// o clique faz; sem tooltip nenhum já destravado (nada pra explicar/clicar).
var _GS_LOCK_TOOLTIP_LOCKED = {
    'gs-layer-name': 'Nome já publicado - precisa bater com a tabela no banco. Clique para editar mesmo assim (risco: publicação atual fica órfã).',
    'gs-layer-title': 'Título já publicado no Geohab. Clique para editar mesmo assim.'
};

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
            lockBtn.innerHTML = locked ? _GS_LOCK_ICON_LOCKED : _GS_LOCK_ICON_UNLOCKED;
            lockBtn.style.cursor = locked ? 'pointer' : 'default';
            lockBtn.disabled = !locked;
            lockBtn.dataset.title = locked ? (_GS_LOCK_TOOLTIP_LOCKED[fieldId] || '') : '';
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
    // Estilos ADICIONAIS (_gsAdditionalStyles) são um array à parte do estilo principal
    // acima - sem isso, "Descartar Alterações"/"Limpar Rascunho" não tocavam nele, e os
    // chips continuavam visíveis com o conteúdo antigo até navegar pra outro painel e
    // voltar (único outro caminho que passa por aqui, ver _renderGsLayerCard/linha ~714-719
    // - reseta pra [] quando não há estilo adicional salvo).
    _gsAdditionalStyles = [];
    _renderGsAdditionalStyles();
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
// confirmGsPublish/saveGsDraftNow/_gsTryNoActiveLayerUpdate.
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

// Descrição curta do estilo pro modal de confirmação de "Publicar Camada".
function _gsDescribeStyle(style) {
    if (style.source === 'existing') {
        return '"' + escHtml((style.existing_workspace ? style.existing_workspace + ':' : '') + style.existing_name) + '" (já existente no GeoServer)';
    }
    var name = escHtml(style.name || '');
    return style.source === 'file'
        ? ('"' + name + '" (do arquivo .sld)')
        : ('"' + name + '" (gerado do estilo atual do QGIS)');
}

// Valida a configuração da aba Estilos antes de publicar (confirmGsPublish, camada
// ativa) - retorna a mensagem de erro ('' = ok).
function _gsValidateStyleConfig(style) {
    if (style.source === 'file' && !style.file_path) {
        return 'Escolha o arquivo .sld na aba Estilos antes de continuar.';
    }
    if (style.source === 'existing' && !style.existing_name) {
        return 'Escolha um estilo existente na aba Estilos antes de continuar.';
    }
    return '';
}

// Fallback comum "sem camada ativa" pra Publicar Camada/Atualizar Estilo - GS não tem
// como CRIAR (POST/register_postgis_featuretype) sem uma camada QGIS real (schema/
// tabela/SRS vêm de lá), então aqui é sempre ATUALIZAÇÃO (PUT) do que já está publicado -
// mesma filosofia do "Publicar Metadados" no GN (cria OU atualiza, mesma ação, o backend
// decide, sem o usuário precisar escolher). Por isso os dois menus levam pro MESMO lugar
// nesse cenário - não é bug, é intencional: um único fluxo "atualizar o que já existe",
// alcançável a partir de qualquer um dos dois. O que muda é o texto/título do confirm,
// DINÂMICO conforme o que de fato vai ser enviado (só dados / dados + estilo) - refletir
// o resultado real, em vez de sempre dizer "metadados e Estilo" mesmo sem nenhum estilo
// configurado na aba. Retorna true se assumiu o clique (chamador deve parar por aí),
// false se não é esse cenário (há camada ativa - chamador segue no fluxo normal dele).
function _gsTryNoActiveLayerUpdate() {
    if (_gsLayerInfo && _gsLayerInfo.publishable) return false;
    var d2 = _gsCollectFormState();
    if (!(d2.workspace && d2.datastore && d2.published_name)) {
        Modal.alert((_gsLayerInfo && _gsLayerInfo.reason) || 'Nenhuma camada publicável ativa no QGIS.', 'Aviso', 'warning');
        return true;
    }
    var style = _gsCollectStyleConfig();
    var hasStyle = !!(style && style.source && style.source !== 'none');
    var actionLabel = hasStyle ? 'Atualizar Dados e Estilo' : 'Atualizar Dados';
    var whatText = hasStyle
        ? 'os metadados (Título/Resumo/Palavras-chave) e o estilo'
        : 'os metadados (Título/Resumo/Palavras-chave)';
    var extraNote = hasStyle ? '' :
        '<br><br><small>Nenhum estilo configurado na aba Estilos - só os metadados serão enviados.</small>';
    Modal.confirm(
        'Nenhuma camada ativa no QGIS. Como o destino já é conhecido, deseja atualizar ' +
        whatText + ' dessa camada no GeoServer?' + extraNote,
        function () {
            _showActionLoading('Atualizando ' + (hasStyle ? 'dados e estilo' : 'dados') + ' no GeoServer...');
            // _gnSyncUuid (geonetwork.js, mesmo escopo global) vem de um pull do GN
            // (pullGnRecord) - sem ele, o Link de Metadados nunca era setado nesse fluxo
            // sem camada ativa (não dá pra resolver via persistence_service.load(layer),
            // que exige um QgsMapLayer). Também pode ter sido restaurado do rascunho GS
            // (ver _loadGsDraft).
            gsBridge.update_layer_metadata(
                d2.workspace, d2.datastore, d2.published_name,
                d2.title, d2.abstract, d2.keywords, style ? JSON.stringify(style) : '',
                (typeof _gnSyncUuid !== 'undefined' && _gnSyncUuid) || ''
            );
        },
        actionLabel
    );
    return true;
}

// "Serviços > Baixar Camada" / banner "Atualização disponível" (ver setGsBadge) -
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
        // Navega pro painel em vez de só avisar "abra X antes" (pedido do usuário, mesmo
        // padrão de _requireEditorOpen/geonetwork.js) - a ação em si não dispara sozinha,
        // só leva pra UI certa; usuário clica "Baixar Camada" de novo já no painel.
        navigate('geoserver');
        return;
    }
    // Login exigido logo aqui, ANTES de abrir busca/confirm - baixar uma camada de verdade
    // sempre bate na API REST administrativa do GeoServer (fetch_published_featuretype/
    // fetch_layer_styles), que exige sessão autenticada mesmo pra camadas "públicas" (ao
    // contrário do WMS GetCapabilities usado só pra listar em openGsSearchModal - por isso
    // a busca em si continua sem exigir login, só não faz sentido abrir a busca pra um
    // resultado que não vai poder ser puxado de qualquer forma sem logar depois).
    if (!_isLogged) {
        Modal.alert('Faça login no Geohab antes de baixar a camada - essa ação busca os dados direto do GeoServer.', 'Login Necessário', 'warning');
        return;
    }
    if (!_gsLayerInfo || !_gsLayerInfo.publishable) {
        // Sem camada PostGIS ativa - igual o "Baixar Metadado" do GN (openGnSearchModal):
        // sempre abre a busca, sem atalho de re-baixar um destino já conhecido direto.
        openGsSearchModal();
        return;
    }
    _gsPullKnownDestination();
}

// Puxa DIRETO o destino já preenchido no formulário (Workspace/Datastore/Nome, aba
// Destino/Identificação) - sem busca, sem escolha, só confirma e traz o que está DE FATO
// publicado agora. Usado pelo fim de pullGsLayerFromServer() (camada ativa já preenche o
// destino sozinha) e por applyGsLayerUpdate() (banner "Atualizar agora" - a divergência já
// foi detectada contra ESSE destino específico, não faz sentido oferecer buscar outra
// camada ali, ver Bug 50/52).
function _gsPullKnownDestination() {
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
        'Baixar Camada'
    );
}

// Busca de camadas direto no GeoServer (independe de camada QGIS ativa ou de um pull do
// GN antes) - mesmo padrão visual/estrutural de openGnSearchModal (geonetwork.js), reusando
// gsBridge.search_geoserver (já existente, usado hoje pela aba "Recursos associados" do
// editor GN pra linkar WMS/WFS a um metadado) em vez de criar uma busca nova do zero. Não
// exige login pra BUSCAR (WMS GetCapabilities é público) - só pra efetivamente puxar os
// dados (pull_gs_layer_by_wms_name usa a sessão REST, ver pullGsLayerByName).
var _gsSearchTimer = null;

function openGsSearchModal() {
    if (typeof gsBridge === 'undefined') return;
    // Mesmo badge de openGnSearchModal (geonetwork.js) - a listagem (WMS GetCapabilities)
    // é pública e funciona sem login, mas baixar (pull) uma camada de fato exige sessão
    // ativa (ver checagem de _isLogged em pullGsLayerByName/pullGsLayerFromServer).
    var loginBadge = _isLogged ? '' :
        '<span class="modal-info-badge" onclick="Modal.close();navigate(\'login\')" ' +
        'data-title="A listagem de camadas é pública, mas baixar (pull) uma camada exige login. Clique pra entrar.">' +
        'Não Autenticado</span>';
    var bodyHtml =
        '<div class="search-wrap">' +
        '<input type="text" id="gs-search-input" class="modal-search-input" placeholder="Buscar camada publicada no GeoServer...">' +
        '<span class="search-spinner" id="gs-search-spinner" style="display:none"></span>' +
        '</div>' +
        '<div id="gs-search-results" class="gn-search-results"></div>';
    Modal.show({ title: 'Buscar Camada no GeoServer', message: bodyHtml, headerBadge: loginBadge, buttons: [{ label: 'Fechar', primary: false, onClick: null }] });

    var input = document.getElementById('gs-search-input');
    if (!input) return;
    input.focus();
    input.addEventListener('input', function () {
        clearTimeout(_gsSearchTimer);
        var q = input.value.trim();
        var spinner = document.getElementById('gs-search-spinner');
        if (spinner) spinner.style.display = q ? 'block' : 'none';
        // Fire-and-forget (RNF02) - resposta chega em gs_search_ready, conectado em
        // _initGsBridge, que chama _renderGsSearchResults quando #gs-search-results existir.
        _gsSearchTimer = setTimeout(function () { gsBridge.search_geoserver(q); }, 300);
    });
    // Lista inicial (sem termo) - mesmo comportamento de abrir e já ver algo, em vez de
    // uma caixa vazia até o usuário digitar. Só a 1ª busca da sessão bate na rede de
    // verdade (timeout de até 60s, ver _GsSearchLayersWorker) - spinner + mensagem aqui
    // pra não parecer travado nesse meio-tempo (buscas seguintes, já cacheadas, respondem
    // na hora e o spinner nem chega a aparecer por tempo perceptível).
    var initialSpinner = document.getElementById('gs-search-spinner');
    if (initialSpinner) initialSpinner.style.display = 'block';
    var resultsBox = document.getElementById('gs-search-results');
    if (resultsBox) resultsBox.innerHTML = '<div class="suggestion-item" style="color:var(--fg-muted);cursor:default;">Carregando camadas do GeoServer...</div>';
    gsBridge.search_geoserver('');
}

function _renderGsSearchResults(results, error) {
    var spinner = document.getElementById('gs-search-spinner');
    if (spinner) spinner.style.display = 'none';
    var box = document.getElementById('gs-search-results');
    if (!box) return; // modal já foi fechado
    if (error) {
        box.innerHTML = '<div class="suggestion-item" style="color:var(--fg-muted);cursor:default;">Falha ao buscar no GeoServer: ' + escHtml(error) + '</div>';
        return;
    }
    if (!results || !results.length) {
        box.innerHTML = '<div class="suggestion-item" style="color:var(--fg-muted);cursor:default;">Nenhum resultado.</div>';
        return;
    }
    box.innerHTML = results.map(function (r) {
        return '<div class="suggestion-item" onclick="pullGsLayerByName(\'' + escHtml(r.workspace || '') + '\', \'' +
            escHtml((r.name || '').split(':').pop()) + '\')">' +
            '<span><b>' + escHtml(r.workspace || '') + '</b> - ' + escHtml(r.title || r.name || '') + '</span>' +
            '</div>';
    }).join('');
}

// Puxa uma camada escolhida na busca (openGsSearchModal) - reusa pull_gs_layer_by_wms_name
// (já descobre o datastore automaticamente) e o mesmo handler gs_layer_pulled de sempre,
// exatamente como o caminho "via Metadado" (pullGsLayerFromServer). Exige login aqui (não
// na busca) - fetch_published_featuretype/fetch_layer_styles usam a sessão REST.
// Puxa de fato (sem confirmação nenhuma) - separado de pullGsLayerByName() pra
// _applyPendingGsPullIfAny() poder decidir SE pergunta antes (e com que mensagem) sem
// duplicar essa lógica toda.
function _doPullGsLayerByName(workspace, name) {
    _showActionLoading('Buscando datastore e dados publicados no GeoServer...');
    gsBridge.pull_gs_layer_by_wms_name(workspace + ':' + name);
}

// Puxa manualmente (busca/clique do usuário) - sempre confirma antes, mensagem genérica
// (o usuário escolheu isso de propósito, não precisa de contexto extra).
function pullGsLayerByName(workspace, name) {
    if (!_isLogged) {
        Modal.alert('Faça login no Geohab antes de baixar a camada - essa ação busca os dados direto do GeoServer.', 'Login Necessário', 'warning');
        return;
    }
    Modal.close();
    var wsLayerName = workspace + ':' + name;
    Modal.confirm(
        'Isso vai trazer o que está DE FATO publicado agora em "<strong>' + escHtml(wsLayerName) + '</strong>" ' +
        '(título/resumo/palavras-chave/estilo), substituindo o formulário atual. Continuar?',
        function () { _doPullGsLayerByName(workspace, name); },
        'Baixar Camada'
    );
}

// true se o badge de sync do painel GS está em qualquer estado "Sincronizado" (sys_/db_) -
// mesmo raciocínio de _gnIsSyncedNow (geonetwork.js): usado por _applyPendingGsPullIfAny
// (auto-populate cross-link) pra decidir se precisa perguntar antes de sobrescrever.
function _gsIsSyncedNow() {
    var badge = document.getElementById('gs-sync-badge');
    if (!badge || badge.style.display === 'none') return false;
    var state = badge.className.replace('gn-sync-badge', '').trim();
    return state.indexOf('_synced') !== -1;
}

// Seletor "Selecionar camada publicada" (aba Destino) - dropdown com busca embutida
// (initCustomSelects, mesmo componente do Workspace/Estilo existente - listas com mais de
// 6 opções ganham a caixa de busca automaticamente) listando TODAS as camadas do
// GeoServer, populado pelo mesmo resultado de gsBridge.search_geoserver() já usado pelo
// modal "Baixar Camada"/aba Recursos associados do GN (ver gs_search_ready, mais acima) -
// pedido do usuário: deixar a aba Destino "100% independente", sem precisar abrir um
// modal separado nem ter camada QGIS ativa pra escolher/puxar uma camada.
// "workspace:nome_publicado" do destino ATUALMENTE no formulário (mesma chave usada nos
// values do seletor) - usado pra pré-selecionar a opção certa depois de (re)montar a
// lista (persistência pedida pelo usuário: a seleção não deve resetar sozinha).
function _gsCurrentLayerPickerKey() {
    var wsEl = document.getElementById('gs-workspace');
    var nameEl = document.getElementById('gs-layer-name');
    var workspace = wsEl ? wsEl.value : '';
    var name = nameEl ? (nameEl.dataset.sanitized || nameEl.value.trim()) : '';
    return (workspace && name) ? (workspace + ':' + name) : '';
}

function _renderGsLayerPicker(results, error) {
    var wrap = document.getElementById('gs-layer-picker-wrap');
    if (!wrap) return; // painel/aba já foi trocado
    if (error) {
        wrap.innerHTML = '<select id="gs-layer-picker"><option value="">Falha ao buscar: ' + escHtml(error) + '</option></select>';
        initCustomSelects();
        return;
    }
    var current = _gsCurrentLayerPickerKey();
    var options = '<option value="">Selecione uma camada...</option>';
    (results || []).forEach(function (r) {
        var name = (r.name || '').split(':').pop();
        var workspace = r.workspace || '';
        if (!name || !workspace) return;
        var value = workspace + ':' + name;
        var label = workspace + ' - ' + (r.title || name);
        options += '<option value="' + escHtml(value) + '"' + (value === current ? ' selected' : '') + '>' + escHtml(label) + '</option>';
    });
    wrap.innerHTML = '<select id="gs-layer-picker" data-force-search="1" onchange="onGsLayerPickerChange(this.value)">' + options + '</select>';
    initCustomSelects();
}

// Mesma lista, mas filtrada só pras camadas JÁ PUBLICADAS no Workspace/Datastore
// atualmente escolhidos (gsBridge.list_published_featuretypes, REST - sem título, só o
// nome técnico, diferente da busca via WMS que _renderGsLayerPicker usa) - disparada por
// _gsRefreshLayerPickerForDestination sempre que os dois campos têm valor.
function _renderGsLayerPickerFiltered(names, error) {
    var wrap = document.getElementById('gs-layer-picker-wrap');
    if (!wrap) return; // painel/aba já foi trocado
    if (error) {
        wrap.innerHTML = '<select id="gs-layer-picker"><option value="">Falha ao buscar: ' + escHtml(error) + '</option></select>';
        initCustomSelects();
        return;
    }
    var wsEl = document.getElementById('gs-workspace');
    var workspace = wsEl ? wsEl.value : '';
    var current = _gsCurrentLayerPickerKey();
    var uniqueNames = (names || []).filter(function (n, i, arr) { return n && arr.indexOf(n) === i; }).sort();
    var options = uniqueNames.length
        ? '<option value="">Selecione uma camada...</option>'
        : '<option value="">Nenhuma camada publicada nesse datastore</option>';
    uniqueNames.forEach(function (name) {
        var value = workspace + ':' + name;
        options += '<option value="' + escHtml(value) + '"' + (value === current ? ' selected' : '') + '>' + escHtml(name) + '</option>';
    });
    wrap.innerHTML = '<select id="gs-layer-picker" data-force-search="1" onchange="onGsLayerPickerChange(this.value)">' + options + '</select>';
    initCustomSelects();
}

// Escolheu uma camada no seletor da aba Destino - reusa pullGsLayerByName (mesma ação do
// modal/aba Recursos associados: confirma, resolve o datastore sozinho, traz workspace/
// datastore/nome/título/resumo/palavras-chave/estilo/link de metadados - tudo pelo mesmo
// caminho já existente, sem lógica nova de pull aqui).
function onGsLayerPickerChange(value) {
    if (!value) return;
    var sep = value.indexOf(':');
    if (sep < 0) return;
    pullGsLayerByName(value.slice(0, sep), value.slice(sep + 1));
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
    sys_offline: 'Não verificado',
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
    sys_offline: 'Sincronizado da última vez (pull do GeoServer), mas sem sessão agora pra confirmar de novo. Faça login pra verificar.',
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
    sys_offline: { title: 'Não verificado', type: 'info', message: 'Esse destino veio de um pull do GeoServer confirmado numa sessão anterior (Workspace/Datastore/Nome à direita), mas não tem sessão ativa agora pra confirmar de novo contra o GeoServer.<br><br>Faça login pra verificar se ainda está sincronizado.' },
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
    // especificamente 'sys_modified', não 'db_modified' - "Baixar Camada" (pull) exige
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

// Botão "Atualizar agora" do banner (ver setGsBadge) - a divergência já foi detectada
// contra um destino ESPECÍFICO e conhecido (já preenchido no formulário), diferente do
// menu "Serviços > Baixar Camada" (pullGsLayerFromServer), que sem camada ativa abre uma
// busca (Bug 50 - não faz sentido oferecer buscar OUTRA camada aqui, o banner já sabe
// exatamente qual). Chama _gsPullKnownDestination() direto, sem login-gate/navigate
// próprios - o banner só aparece dentro do próprio painel GeoServer já aberto e logado
// (setGsBadge/_checkGsSyncOnline exigem sessão pra chegar no estado 'sys_modified').
function applyGsLayerUpdate() {
    _gsPullKnownDestination();
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
// login (ver load_publish_destination). EXCEÇÃO: o baseline "sem camada ativa" restaurado
// de um pull antigo (_gsSyncSourceIsDb false - ver _loadGsDraft/synced_tier, Bug 45/52)
// não tem NENHUM registro no banco por trás (save_publish_destination exige um
// QgsMapLayer de verdade) - é 100% dependente da sessão REST do GeoServer. Sem login,
// rotular isso como "db_*" seria afirmar uma confirmação que nunca existiu (nem contra o
// banco, que não tem essa linha, nem contra o GeoServer, que exige login) - cai pro
// mesmo "offline" usado quando não há snapshot nenhum.
function _checkGsSyncNow() {
    if (_gsSyncSnapshot === null) {
        setGsBadge('offline');
        return;
    }
    if (!_isLogged && !_gsSyncSourceIsDb) {
        setGsBadge('sys_offline');
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
// novo. Chamada depois de uma falha em "Baixar Camada"/"Atualizar Estilo" (ver
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
        // A busca de camadas (modal "Baixar Camada"/seletor "Selecionar camada
        // publicada") pode ter rodado a 1ª vez ANTES de logar - WMS GetCapabilities
        // anônimo enxerga um subconjunto menor (segurança de dados por workspace do
        // GeoServer), e o cache (GeoServerBridge._geoserver_layers_cache) fica preso
        // nesse resultado incompleto pro resto da sessão (usuário reportou: sempre os
        // mesmos ~25 itens, digitar um nome que existe de verdade não acha). Login é um
        // gatilho claro de "a lista pode estar incompleta agora" - descarta e busca de
        // novo.
        if (typeof gsBridge !== 'undefined' && gsBridge.invalidate_gs_search_cache) {
            gsBridge.invalidate_gs_search_cache();
            gsBridge.search_geoserver('');
        }
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

// Captura o baseline (_gsSyncSnapshot) do "pull baseline" sem camada ativa (Bug 45/52,
// ver _loadGsDraft) - SÓ quando workspace/datastore já estiverem de fato resolvidos no
// DOM, não na hora em que draft.synced_tier é lido. _gsQueueWorkspaceDatastore (chamado
// pouco antes, em _loadGsDraft) pode ser TOTALMENTE assíncrono (lista de workspaces/
// datastores ainda não carregou - o caso comum logo após reabrir o plugin): capturar o
// snapshot ali mesmo, de forma síncrona, guardava um baseline com workspace/datastore
// ainda vazios/"Carregando..." - quando a lista finalmente respondia e preenchia os
// campos de verdade (instantes depois), o próximo _markGsModifiedIfNeeded() comparava o
// formulário (agora certo) contra esse baseline incompleto e acusava "Modificado" à toa,
// mesmo sem nenhuma edição real do usuário. Por isso a captura de verdade é ADIADA (flag
// _gsPendingSyncedBaselineCapture, setada em _loadGsDraft) até essa função ser chamada de
// algum dos pontos onde workspace/datastore REALMENTE terminaram de se resolver -
// _gsApplyKnownWorkspaceDatastore, _renderGsDatastores (sucesso e erro) e os dois
// desfechos síncronos de _gsQueueWorkspaceDatastore/_renderGsWorkspaces quando não há
// datastore nenhum pra esperar. Idempotente - só age na primeira chamada (flag zera).
function _gsCaptureSyncedBaselineIfPending() {
    if (!_gsPendingSyncedBaselineCapture) return;
    _gsPendingSyncedBaselineCapture = false;
    _gsSyncSnapshot = JSON.stringify(_gsCollectFormState());
    _gsCaptureSnapshotRawNames();
    _markGsModifiedIfNeeded();
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

    if (_gsTryNoActiveLayerUpdate()) return;

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
            // metadata_uuid: mesmo uuid já usado pra montar a prévia do "Link de
            // Metadados" (aba Identificação, _gsLayerInfo.metadata_uuid - ver
            // _on_layer_info_ready/geoserver_bridge.py) - sem passar isso, publish_layer
            // recalculava o link do zero só a partir do banco/sidecar local, divergindo da
            // prévia sempre que o uuid só estava disponível via um pull do GN feito nesta
            // sessão (fluxo comum: a camada existe no GeoServer antes do metadado).
            gsBridge.publish_layer(d.workspace, d.datastore, d.published_name, d.title, d.abstract, d.keywords, JSON.stringify(style), (_gsLayerInfo && _gsLayerInfo.metadata_uuid) || '');
        },
        'Confirmar Publicação'
    );
}

// "Serviços > Publicar Camada" (main.html) - mesmo padrão de tryExportGeohab() (GN,
// "Catálogo > Publicar Metadado", via _requireEditorOpen): sem o painel aberto, NAVEGA
// pra "Configurar Camada" em vez de só avisar "abra X antes" - mas para por aí, não
// dispara a publicação sozinho: quem publica de fato é um clique deliberado do usuário
// já vendo o formulário preenchido, não algo automático escondido atrás de um item de
// menu (pedido explícito do usuário pra esse caso, diferente dos demais itens do header).
function tryPublishGeoServerLayer() {
    if (!document.getElementById('gs-layer-card')) {
        navigate('geoserver');
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

// Volta workspace/datastore pra "Selecione..." de forma garantida - usado por
// _onGsActiveLayerChanged/tryGsResetForm/tryClearDraft (app.js) quando o destino precisa
// ser esquecido de vez. _clickGsSuggestionItem('gs-workspace-wrap', '') sozinho FALHA
// silenciosamente sempre que o wrap está no estado "destino conhecido, lista de
// workspaces não carregou" (_gsApplyKnownWorkspaceDatastore, ver _gsWorkspaceListFailed -
// sem sessão, ex.: busca no GeoServer sem login) - esse markup tem só UMA opção (o
// workspace conhecido), sem nenhum item de valor "" pra clicar; o campo visível ficava
// travado mostrando o workspace antigo mesmo depois de "limpar". Reconstrói o dropdown do
// zero (mesmo HTML de _loadGsWorkspaces/erro em _renderGsWorkspaces) quando o clique falha,
// garantindo o estado vazio independente de qual markup estava montado até então.
function _gsResetWorkspaceDatastoreSelection() {
    if (_clickGsSuggestionItem('gs-workspace-wrap', '')) return;
    var wrap = document.getElementById('gs-workspace-wrap');
    if (!wrap) return;
    wrap.innerHTML = '<select id="gs-workspace" onchange="onGsWorkspaceChange(this.value)"><option value="">Selecione um workspace...</option></select>';
    initCustomSelects();
    onGsWorkspaceChange('');
}
