// geonetwork.js - Editor de metadados GN (GeoNetwork): formulário, contatos, sync,
// busca/pull, distribuição. Depende de app.js (bridge/gnBridge/gsBridge globais,
// Modal, escHtml, updateCustomSelect, initCustomSelects, initGlobalTooltips,
// updateFormProgress-adjacent helpers) já carregado antes deste script.

// ── Draft: preserva estado do formulário entre navegações e fechamento ─────────
var _draftTimer = null;

function _scheduleDraftSave() {
    clearTimeout(_draftTimer);
    _draftTimer = setTimeout(_saveDraftNow, 1500);
}

// Salva na hora, sem o debounce de 1.5s - usado depois de ações explícitas (pull do GN,
// importar XML local) que não podem ficar pendentes até uma eventual troca de camada
// disparar o timer sob a chave da camada errada.
function _saveDraftNow() {
    // O timer de debounce (1.5s) pode disparar depois que o usuário já navegou pra
    // outro painel - sem essa checagem, collectFormData() aciona o guard de "Ação
    // Necessária" à toa, já que o editor não existe mais no DOM.
    if (!document.getElementById("f-title")) { clearTimeout(_draftTimer); return; }
    var d = collectFormData();
    if (!d || typeof gnBridge === 'undefined') return;
    // Não sobrescreve o arquivo com formulário vazio
    var hasContent = d.title || (d.contacts && d.contacts.length > 0) ||
        (d.MD_Keywords && d.MD_Keywords.length > 0) || d.abstract;
    if (!hasContent) return;
    _editorDraft = d;
    clearTimeout(_draftTimer);
    gnBridge.save_draft(JSON.stringify(d));
}

var _suggBoxMap = {
    "search-suggestions": "contact-search",
    "proc-suggestions": "proc-search",
    "meta-suggestions": "meta-search",
    "dist-suggestions": "dist-search"
};

document.addEventListener("click", function (e) {
    Object.keys(_suggBoxMap).forEach(function (boxId) {
        var box = document.getElementById(boxId);
        if (!box || box.style.display === "none") return;
        var input = document.getElementById(_suggBoxMap[boxId]);
        if (input && input.contains(e.target)) return;
        if (box.contains(e.target)) return;
        box.style.display = "none";
    });
    closeSuggestions();
});

// ── Ganchos chamados pelo app-shell (app.js) ────────────────────────────────────
// (indicador de carregamento _showActionLoading/_hideActionLoading é genérico, mora em app.js)

function _initGnBridge() {
    // toast cobre sucesso E erro de publicar (export_geohab); save_metadata só emite
    // local_save_succeeded no sucesso (erro dela hoje só mostra diálogo nativo do Qt,
    // por isso o timeout de segurança em _showActionLoading).
    bridge.toast.connect(function () { _hideActionLoading(); });

    gnBridge.gn_publish_succeeded.connect(function (uuid) {
        _hideActionLoading();
        var uidEl = document.getElementById('f-metadataId');
        if (uidEl) uidEl.value = uuid;
        if (typeof gnBridge !== 'undefined') gnBridge.clear_draft(); // save no DB/sidecar já é a fonte da verdade agora
        _gnSyncUuid = uuid || null;
        _gnSyncUuidLayerName = uuid ? _activeLayerName : null;
        setGnBadge('sys_synced'); // publicar exige login - sempre nível sistema
    });

    // Save local (Continuar Depois) confirmado - recheca contra o GN na hora, sem
    // esperar reabrir a camada (não força "Sincronizado": um save local sozinho não
    // significa que bate com o GN, o checkGnSync decide o estado certo).
    gnBridge.local_save_succeeded.connect(function (uuid) {
        _hideActionLoading();
        if (!uuid) return;
        var data = collectFormData();
        checkGnSync(uuid, (data && data.dateStamp) || '');
    });

    gnBridge.gn_metadata_search_ready.connect(function (results) {
        _renderGnSearchResults(results);
    });

    gnBridge.gn_contacts_ready.connect(function (key, q, results) {
        _gnLoading[key] = false;
        var gnList = (results || []);
        if (key === 'main') {
            var inp = document.getElementById('contact-search');
            if (!inp || inp.value.trim() !== q) return;
            _gnResults = gnList;
            _renderContactSuggestions(q);
        } else {
            var inp2 = document.getElementById(key + '-search');
            if (!inp2 || inp2.value.trim() !== q) return;
            _setSuggGn(key, gnList);
            _renderForSuggestions(key, q);
        }
    });

    gnBridge.gn_contact_enriched.connect(function (key, idx, data) {
        var arr = (key === 'main') ? contacts : _sArr(key);
        if (!arr || !arr[idx]) return;
        var d = arr[idx].data;
        Object.keys(data).forEach(function (k) { if (data[k]) d[k] = data[k]; });
        if (key === 'main') renderContacts();
        else renderFor(key);
    });
}

// Chamado por loadPanel() (app.js) antes de trocar o HTML do painel - captura o
// estado do formulário se o editor estava aberto.
function _onBeforePanelUnload() {
    if (document.getElementById("f-title")) {
        _editorDraft = collectFormData();
    }
}

// Chamado por bridge.layer_changed (via app.js) quando a camada ativa do QGIS muda.
function _onActiveLayerChanged(name) {
    dismissGnUpdateBanner();
    if (document.getElementById('f-title')) {
        resetEditorForm();
        var badge = document.getElementById('gn-sync-badge');
        if (badge) badge.style.display = 'none';
        _gsBadgeState = null;
        _loadFormForLayer(null);
        checkGsPublishStatus();
    }
}

// Chamado por onPanelLoaded() (app.js) quando o painel "editor" acabou de carregar.
function _onEditorPanelLoaded() {
    // Se tem um vínculo GS pendente (recém-publicado no GeoServer, ver geoserver.js), já
    // abre direto na aba Distribuição - evita o "flash" de Identificação seguido de troca
    // de aba alguns instantes depois, que dava a impressão de ter ido pra home do editor.
    var _initialTabId = window._pendingGsDistLayer ? 'distribuicao' : 'identificacao';
    var _initialTabBtn = document.querySelector('.tab-link[onclick*="' + _initialTabId + '"]') || document.querySelector('.tab-link');
    showTab(_initialTabId, _initialTabBtn);
    var _d = new Date(); _d.setHours(_d.getHours() - 3);
    var now = _d.toISOString().slice(0, 16);
    var ds = document.getElementById("f-dateStamp");
    if (ds && !ds.value) ds.value = now;
    var uid = document.getElementById("f-metadataId");
    if (uid && !uid.value) uid.value = generateUUID();
    contacts = [];
    procContacts = [];
    metaContacts = [];
    keywords = [];
    distResources = [];
    renderContacts();
    renderKeywords();
    renderDistResources();
    initMetaAuthor();
    setTimeout(initCustomSelects, 50);

    // Carrega formulário: draft de sessão > draft de arquivo > metadado salvo
    var _sessionDraft = _editorDraft;
    _editorDraft = null;
    setTimeout(function () { _loadFormForLayer(_sessionDraft); }, 60);
    checkGsPublishStatus(); // status de publicação no GeoServer da camada ativa (ver geoserver.js)

    // Rastreio de progresso e auto-save por eventos de input/change
    setTimeout(updateFormProgress, 100);
    var containerPanel = document.getElementById("tab-identificacao").parentNode;
    if (containerPanel && !containerPanel.hasAttribute('data-progress-listener')) {
        containerPanel.addEventListener('input', updateFormProgress);
        containerPanel.addEventListener('change', updateFormProgress);
        containerPanel.setAttribute('data-progress-listener', 'true');
    }
    if (containerPanel && !containerPanel.hasAttribute('data-draft-listener')) {
        containerPanel.addEventListener('input', _scheduleDraftSave);
        containerPanel.addEventListener('change', _scheduleDraftSave);
        containerPanel.setAttribute('data-draft-listener', 'true');
    }
    if (containerPanel && !containerPanel.hasAttribute('data-sync-listener')) {
        containerPanel.addEventListener('input', _markGnModifiedIfNeeded);
        containerPanel.addEventListener('change', _markGnModifiedIfNeeded);
        containerPanel.setAttribute('data-sync-listener', 'true');
    }

    var thumbInput = document.getElementById('f-thumbnail_url');
    if (thumbInput) {
        thumbInput.addEventListener('input', _updateThumbnailPreview);
        thumbInput.addEventListener('change', _updateThumbnailPreview);
    }
}

// ─── Ações de exportação (chamadas pelo header) ───────────────────────────────

function tryExportXml() {
    var data = collectFormData();
    if (!data) return;
    var missing = validateForm(data, true); // silent: não toca o DOM agora
    if (missing.length > 0) {
        showValidationError(missing);
        requestAnimationFrame(function () { validateForm(data, false); }); // bordas vermelhas após modal abrir
        return;
    }
    gnBridge.export_xml(data);
}

function tryExportGeohab() {
    var data = collectFormData();
    if (!data) return;
    var missing = validateForm(data, true);
    if (missing.length > 0) {
        showValidationError(missing);
        requestAnimationFrame(function () { validateForm(data, false); });
        return;
    }
    Modal.confirmOptions({
        title: 'Confirmar publicação',
        message: 'Publicar "' + (data.title || '') + '" no catálogo Geohab?',
        confirmLabel: 'Publicar',
        options: [
            { value: 'NOTHING', label: 'Nenhum', hint: 'Rejeita a publicação se já existir um metadado com mesmo UUID.' },
            { value: 'OVERWRITE', label: 'Sobrescrever metadados com o mesmo UUID', hint: 'Atualiza o registro existente com este UUID.' },
            { value: 'GENERATEUUID', label: 'Gerar UUID para o metadado inserido', hint: 'Sempre cria um registro novo, com um UUID novo.' }
        ],
        defaultIndex: 0,
        onConfirm: function (uuidProcessing) {
            data.uuidProcessing = uuidProcessing;
            _showActionLoading('Publicando no Geohab...');
            gnBridge.export_geohab(data);
        }
    });
}

// Chamado por trySaveMetadata() (app.js - dispatcher genérico do menu Arquivo >
// Continuar Depois, que decide entre isso e _tryGsSaveDestination conforme o painel
// aberto). Nome com _ na frente de propósito, pra não colidir com o dispatcher.
function _tryGnSaveMetadata() {
    var data = collectFormData();
    if (!data) return;
    Modal.confirm('Deseja realmente salvar as alterações no banco de dados?', function () {
        _showActionLoading('Salvando...');
        gnBridge.save_metadata(data);
    }, 'Confirmar Salvamento');
}

// Chamado por tryResetForm() (app.js - dispatcher genérico do menu Arquivo > Descartar
// Alterações, que decide entre isso e tryGsResetForm conforme o painel aberto). Nome com
// _ na frente de propósito, pra não colidir com o dispatcher (mesmo motivo de
// _tryGnSaveMetadata acima).
function _tryGnResetForm() {
    if (!_requireEditorOpen('descartar as alterações')) return;
    Modal.confirm('Isso vai descartar as alterações não salvas deste formulário. Continuar?', function () {
        if (typeof gnBridge !== 'undefined') gnBridge.clear_draft();
        _editorDraft = null;
        resetEditorForm();
        _loadFormForLayer(null);
    }, 'Descartar Alterações');
}

function tryImportXml() {
    if (!_requireEditorOpen('importar um metadado')) return;
    if (typeof gnBridge === 'undefined') return;
    gnBridge.import_xml_file(function (data) {
        if (!data) return; // usuário cancelou o diálogo, ou o arquivo não pôde ser lido
        Modal.confirm('Isso vai substituir os dados atuais do formulário. Continuar?', function () {
            resetEditorForm();
            populateForm(data);
            _saveDraftNow();
            checkGnSync(data.metadata_uuid, data.dateStamp || '');
            // Modal.confirm chama close() logo depois desse callback retornar - abrir o
            // alert de sucesso na hora faria ele "piscar" (mesmo overlay reaproveitado).
            // Adiando pro próximo tick, o close() do confirm já rodou antes.
            setTimeout(function () {
                Modal.alert('Metadado importado com sucesso.<br>Confira os campos preenchidos no formulário.', 'Importado', 'success');
            }, 0);
        }, 'Importar Metadado');
    });
}

// ─── Formulário ───────────────────────────────────────────────────────────────

function resetEditorForm() {
    document.querySelectorAll('[id^="f-"]').forEach(function (el) { el.value = ''; });
    contacts = []; procContacts = []; metaContacts = []; keywords = []; distResources = [];
    renderContacts(); renderKeywords(); renderDistResources();
    renderFor('proc'); renderFor('meta');
    var uid = document.getElementById('f-metadataId');
    if (uid) uid.value = generateUUID();
    updateFormProgress();
    _updateThumbnailPreview();
}

// Mostra uma prévia pequena da miniatura (URL da aba Classificação) logo abaixo do
// campo - só se a imagem realmente carregar, pra não deixar um ícone de imagem quebrada
// à mostra quando a URL for inválida ou ainda não tiver sido preenchida.
function _updateThumbnailPreview() {
    var wrap = document.getElementById('thumb-preview-wrap');
    var img = document.getElementById('f-thumbnail-preview');
    var input = document.getElementById('f-thumbnail_url');
    if (!wrap || !img || !input) return;
    var url = input.value.trim();
    if (!url) {
        wrap.style.display = 'none';
        img.removeAttribute('src');
        return;
    }
    img.onload = function () { wrap.style.display = 'block'; };
    img.onerror = function () { wrap.style.display = 'none'; };
    img.src = url;
}

// Prioridade: draft (edições não salvas) > metadado salvo (DB/sidecar) > vazio.
// Em todo caminho de saída (mesmo o "vazio", quando a camada não tem metadado nenhum
// ainda) chama _applyPendingGsDistLayerIfAny() - garante que um vínculo GS pendente
// (ver geoserver.js) seja aplicado exatamente uma vez, não importa qual ramo resolveu.
//
// gnBridge.load_draft()/load_layer_metadata() identificam a camada lendo
// iface.activeLayer() DE NOVO do lado Python, no momento em que o slot roda - não pelo
// que estava ativo quando a chamada foi disparada daqui. Trocar de camada rápido o
// bastante enquanto uma dessas chamadas ainda está em voo faz a resposta chegar depois já
// pra outra camada, aplicando o XML/rascunho ERRADO no formulário ("puxou um XML de algum
// lugar" mesmo numa camada sem nada salvo). _expectedLayer trava a camada de quando a
// chamada foi feita; se _activeLayerName já mudou quando a resposta chega, descarta.
function _loadFormForLayer(sessionDraft) {
    if (sessionDraft) {
        populateForm(sessionDraft);
        checkGnSync(sessionDraft.metadata_uuid, sessionDraft.dateStamp || '');
        _applyPendingGsDistLayerIfAny();
        return;
    }
    if (typeof gnBridge === 'undefined') { _applyPendingGsDistLayerIfAny(); return; }
    var _expectedLayer = _activeLayerName;
    gnBridge.load_draft(function (draft) {
        if (_activeLayerName !== _expectedLayer) return; // camada trocou enquanto carregava - resposta obsoleta
        if (draft) {
            populateForm(draft);
            checkGnSync(draft.metadata_uuid, draft.dateStamp || '');
            _applyPendingGsDistLayerIfAny();
        } else {
            gnBridge.load_layer_metadata(function (saved) {
                if (_activeLayerName !== _expectedLayer) return; // idem
                if (saved) populateForm(saved);
                checkGnSync(saved && saved.metadata_uuid, (saved && saved.dateStamp) || '');
                _applyPendingGsDistLayerIfAny();
            });
        }
    });
}

// ─── Sincronização com o GeoNetwork (badge + busca manual + auto-check) ────────

var _gnSyncUuid = null;
var _gnSyncUuidLayerName = null; // qual camada esse uuid corresponde - usado pelo GS (geoserver.js) como
// dica de fallback quando a busca local (banco/sidecar) não acha nada,
// só quando bate com a camada ativa (evita puxar uuid de outra camada)
var _gnSearchTimer = null;
// Retrato (JSON) do formulário no momento exato em que o badge virou "Sincronizado" OU
// "Não encontrado no Geohab" - comparado a cada input/change pra saber se o conteúdo
// atual bate de novo com esse ponto de partida, mesmo que o usuário tenha revertido a
// edição manualmente (sem usar nenhum botão de Descartar/Publicar/Puxar). _gnSyncBaseline
// guarda QUAL desses dois estados é o "limpo" a voltar quando o conteúdo bate de novo.
var _gnSyncSnapshot = null;
var _gnSyncBaseline = null; // uma das chaves de _GN_MODIFIED_FOR abaixo

// Cache do último resultado de verdade (Geohab/banco) por camada - reaproveitado quando o
// usuário só troca de painel e volta pra ESSA MESMA camada, em vez de bater no Geohab/
// banco de novo toda vez (isso que fazia a troca de painel parecer lenta - ver setGnBadge/
// checkGnSync). Só expira depois de _GN_RECHECK_STALE_MS ou quando a camada muda de
// verdade (a comparação de chave já cuida disso sozinha, ver checkGnSync).
var _GN_RECHECK_STALE_MS = 60000;
var _gnLastCheckedLayerKey = null;
var _gnLastCheckedAt = 0;
var _gnLastBadgeState = null;

// Vocabulário de status compartilhado entre GN e GS (ver _GS_SYNC_LABELS, geoserver.js) -
// 3 níveis de conectividade (prefixo do estado), maior confiança primeiro, + 2 estados
// universais sem nível (checking/error). O nível não muda a lógica de comparação, só diz
// QUAL fonte foi usada pra comparar - por isso "Modificado" tem uma mensagem diferente em
// cada nível (ver _GN_SYNC_TOOLTIPS/onGnSyncBadgeClick), mesmo sendo sempre o mesmo
// mecanismo de "diverge do snapshot" (_markGnModifiedIfNeeded):
//   sys_*     - logado no Geohab, comparado contra a busca ao vivo no GeoNetwork.
//   db_*      - sem sessão, comparado contra a cópia persistida (banco/sidecar).
//   offline_* - sem sessão nem camada ativa pra identificar, só o rascunho local.
var _GN_SYNC_LABELS = {
    checking: 'Verificando…',
    error: 'Erro ao verificar',
    offline_saved: 'Salvo (Offline)',
    offline_modified: 'Modificado (Offline)',
    db_not_found: 'Não Encontrado (DB)',
    db_modified: 'Modificado (DB)',
    db_synced: 'Sincronizado (DB)',
    sys_not_found: 'Não Encontrado (Geohab)',
    sys_update_available: 'Atualização disponível',
    sys_modified: 'Modificado',
    sys_synced: 'Sincronizado'
};

var _GN_SYNC_TOOLTIPS = {
    checking: 'Verificando sincronização...',
    error: 'Não foi possível verificar o status agora.',
    offline_saved: 'Rascunho salvo só nesta máquina - sem conexão com banco ou Geohab pra confirmar.',
    offline_modified: 'Editado desde o último rascunho local - sem conexão com banco ou Geohab agora.',
    db_not_found: 'Nenhum metadado salvo no banco ainda (sem login no Geohab).',
    db_modified: 'Editado desde o último salvamento no banco (sem login no Geohab).',
    db_synced: 'Bate com o banco de dados (sem login no Geohab pra confirmar lá também).',
    sys_not_found: 'UUID salvo, mas não encontrado no Geohab (nunca publicado ou removido de lá).',
    sys_update_available: 'Existe uma versão mais nova no Geohab.',
    sys_modified: 'Editado desde a última sincronização com o Geohab.',
    sys_synced: 'Sincronizado com o que está publicado no Geohab.'
};

// Baseline -> estado "modificado" correspondente, usado por _markGnModifiedIfNeeded pra
// alternar só dentro do mesmo nível (nunca pula de db_synced pra sys_modified, por ex.).
// checking/error/sys_update_available não têm baseline aqui - _markGnModifiedIfNeeded não
// mexe neles (nada pra "divergir de", ver comentário na função).
var _GN_MODIFIED_FOR = {
    sys_synced: 'sys_modified',
    db_synced: 'db_modified',
    offline_saved: 'offline_modified'
};

function setGnBadge(state) {
    var badge = document.getElementById('gn-sync-badge');
    var label = document.getElementById('gn-sync-label');
    if (!badge || !label) return;
    badge.className = 'gn-sync-badge ' + state;
    badge.style.display = 'flex';
    _refreshGnBadgeLabel();
    if (_GN_MODIFIED_FOR[state]) {
        var snap = collectFormData();
        if (snap) {
            _gnSyncSnapshot = JSON.stringify(snap);
            _gnSyncBaseline = state;
        }
    }

    // Guarda o último resultado de verdade (não 'checking') pra essa camada - reaproveitado
    // por checkGnSync() se o usuário só trocar de painel e voltar, sem precisar bater no
    // Geohab/banco de novo (ver comentário em _gnLastCheckedLayerKey).
    if (state !== 'checking') {
        _gnLastCheckedLayerKey = _activeLayerName;
        _gnLastCheckedAt = Date.now();
        _gnLastBadgeState = state;
    }

    var banner = document.getElementById('gn-update-banner');
    if (banner) banner.style.display = (state === 'sys_update_available') ? 'flex' : 'none';
}

// Reescreve o texto/tooltip do badge GN com base no estado atual.
// O status GeoServer NÃO entra aqui - fica exclusivamente no badge/painel GeoServer.
function _refreshGnBadgeLabel() {
    var badge = document.getElementById('gn-sync-badge');
    var label = document.getElementById('gn-sync-label');
    if (!badge || !label || badge.style.display === 'none') return;
    var state = badge.className.replace('gn-sync-badge', '').trim();
    if (!state) return;
    label.textContent = _GN_SYNC_LABELS[state] || state;
    badge.dataset.title = _GN_SYNC_TOOLTIPS[state] || '';
}

// Chamado a cada input/change do formulário. Compara o conteúdo atual contra o retrato
// do último ponto de partida conhecido (o baseline capturado em setGnBadge - synced ou
// not_found, de QUALQUER nível): se bater de novo, volta sozinho pro estado de origem
// (mesmo sem clicar em Descartar); se divergir, vira o "modificado" desse MESMO nível
// (_GN_MODIFIED_FOR) - nunca pula de nível sozinho. Não interfere em checking/error/
// sys_update_available (não têm baseline em _GN_MODIFIED_FOR).
function _markGnModifiedIfNeeded() {
    if (_gnSyncSnapshot === null || _gnSyncBaseline === null) return;
    var badge = document.getElementById('gn-sync-badge');
    if (!badge) return;
    var modifiedState = _GN_MODIFIED_FOR[_gnSyncBaseline];
    if (!modifiedState) return;
    var isBaseline = badge.classList.contains(_gnSyncBaseline);
    var isModified = badge.classList.contains(modifiedState);
    if (!isBaseline && !isModified) return;
    var current = collectFormData();
    if (!current) return;
    var matches = JSON.stringify(current) === _gnSyncSnapshot;
    if (matches && isModified) {
        setGnBadge(_gnSyncBaseline);
    } else if (!matches && isBaseline) {
        setGnBadge(modifiedState);
    }
}

function checkGnSync(uuid, dateStamp) {
    _gnSyncUuid = uuid || null;
    _gnSyncUuidLayerName = uuid ? _activeLayerName : null;

    // Se já verificamos ESSA MESMA camada recentemente (< _GN_RECHECK_STALE_MS atrás),
    // reaplica o resultado guardado na hora em vez de bater no Geohab/banco de novo - é o
    // que fazia trocar de painel e voltar parecer lento, já que isso rodava do zero toda
    // vez mesmo sem a camada ter mudado. Ações explícitas (salvar/publicar/puxar) já
    // chamam setGnBadge diretamente com o resultado real, atualizando esse cache também.
    if (_gnLastCheckedLayerKey === _activeLayerName && _gnLastBadgeState &&
        (Date.now() - _gnLastCheckedAt) < _GN_RECHECK_STALE_MS) {
        setGnBadge(_gnLastBadgeState);
        return;
    }

    if (typeof gnBridge === 'undefined') {
        setGnBadge('offline_saved');
        return;
    }
    // Sessão é checada de verdade do lado Python (check_gn_sync olha
    // self._dialog.plugin.api_session ao vivo) - não usar _isLogged aqui, é só um cache de
    // UI que pode ficar desatualizado logo após login/reconexão. O NÍVEL (sistema/banco/
    // offline) também é decidido lá - mesmo sem uuid conhecido aqui (camada nova, sem
    // draft nem save ainda), o nível banco ainda consegue achar um registro salvo pela
    // identidade da própria camada (ver check_gn_sync, ui/geonetwork_bridge.py).
    setGnBadge('checking');
    var _expectedLayer = _activeLayerName;
    gnBridge.check_gn_sync(uuid || '', dateStamp || '', function (result) {
        if (_activeLayerName !== _expectedLayer) return; // camada trocou enquanto verificava - resposta obsoleta
        setGnBadge(result);
    });
}

// Sufixo com o status GS (_gsBadgeState) pra anexar no modal do badge combinado - mesmo
// clique, mesmo badge, só acrescenta o parágrafo do GeoServer quando aplicável.
function _gsStatusModalSuffix() {
    if (!_gsBadgeState) return '';
    return '<br><br><b>' + _GS_STATUS_LABELS[_gsBadgeState] + '</b><br>' + _gsStatusTooltip(_gsBadgeState);
}

// Título/tipo/mensagem do modal pra cada estado (ver _GN_SYNC_LABELS pro rótulo curto do
// badge) - cada nível tem uma mensagem própria, mesmo quando o "resultado" (ex.:
// Modificado) é conceitualmente parecido em mais de um nível, porque a orientação de
// próximo passo muda com o que está disponível (login vs. banco vs. só rascunho).
var _GN_SYNC_MODALS = {
    error: { title: 'Erro ao verificar', type: 'error', message: 'Não foi possível verificar o status agora. Tente de novo em alguns instantes.' },
    offline_saved: { title: 'Salvo (Offline)', type: 'info', message: 'Rascunho salvo localmente nesta máquina.<br><br>⚠️Sem conexão com o banco de dados nem com o Geohab agora - abra o editor com uma camada do banco ativa, ou faça login, pra confirmar contra um registro de verdade.' },
    offline_modified: { title: 'Modificado (Offline)', type: 'warning', message: 'Editado localmente desde o último rascunho salvo nesta máquina.<br><br>⚠️Sem conexão com o banco nem com o Geohab.' },
    db_not_found: { title: 'Não Encontrado (DB)', type: 'warning', message: 'Nenhum metadado salvo no banco de dados pra esta camada ainda.<br><br>⚠️ Verificado sem login no Geohab.<br>Faça login para verificação Online.<br><br>Use: <br>"Arquivo > Continuar Depois" pra salvar no banco, ou <br>"Arquivo > Publicar Metadado" pra publicar direto no Geohab.' },
    db_modified: { title: 'Modificado (DB)', type: 'warning', message: 'O formulário atual foi editado localmente desde a última vez que foi salvo no banco de dados.<br><br>⚠️ Verificado sem login no Geohab.<br>Faça login para verificação Online.<br><br>Use:<br>"Arquivo > Continuar Depois" pra salvar, ou <br>"Arquivo > Descartar Alterações" pra voltar ao último salvo.' },
    db_synced: { title: 'Sincronizado (DB)', type: 'success', message: 'O formulário atual bate com o que está salvo no banco de dados.<br><br>⚠️ Verificado sem login no Geohab.<br>Faça login para verificação Online.' },
    sys_not_found: { title: 'Não encontrado no Geohab', type: 'warning', message: 'Este metadado tem um UUID salvo localmente ou no banco, mas não foi encontrado no catálogo Geohab (nunca publicado, ou removido de lá).<br><br>Para publicar, use "Catálogo > Publicar Metadado".<br>Pra buscar um registro diferente já existente, use "Arquivo > Baixar Metadado" ou "Arquivo > Importar Metadado".' },
    sys_update_available: { title: 'Atualização disponível', type: 'warning', message: 'Existe uma versão mais nova deste metadado no Geohab.<br><br>Clique em "Atualizar agora" no aviso acima do formulário pra puxar a atualização.' },
    sys_modified: { title: 'Modificado', type: 'warning', message: 'Você tem alterações não salvas.<br><br>Use: <br>"Arquivo > Continuar Depois" pra salvar sem publicar, ou <br>"Arquivo > Publicar Metadado" para publicar no Geohab.' },
    sys_synced: { title: 'Sincronizado', type: 'success', message: 'Este metadado já está sincronizado com o Geohab.' }
};

function onGnSyncBadgeClick() {
    var badge = document.getElementById('gn-sync-badge');
    if (!badge) return;
    var state = badge.className.replace('gn-sync-badge', '').trim();
    var entry = _GN_SYNC_MODALS[state];
    if (!entry) return; // checking - nada pra mostrar enquanto verifica
    Modal.alert(entry.message, entry.title, entry.type);
}

function applyGnUpdate() {
    if (!_gnSyncUuid) return;
    pullGnRecord(_gnSyncUuid);
}

// ─── Status de publicação no GeoServer (fundido no MESMO badge #gn-sync-badge) ────
// Não é um "sync" completo como o do GN (não há formulário GS aberto aqui pra comparar
// contra "modificado") - só mostra se a camada ativa já foi publicada/salva no GeoServer,
// reaproveitando gsBridge.get_active_layer_publish_info() (mesmo bridge/método que o
// painel GeoServer usa, ver geoserver.js). _gsBadgeState guarda esse pedaço e
// _refreshGnBadgeLabel() (acima) combina com o estado GN no texto/tooltip de um único
// badge visual - não é um segundo badge, os dois status não conflitam entre si.
var _gsBadgeState = null;

// Mesmo esquema de cache por camada de _gnLastCheckedLayerKey (ver acima) - evita bater de
// novo em get_active_layer_publish_info (banco, e potencialmente rede via
// _load_layer_metadata) toda vez que o usuário só troca de painel e volta.
var _gsLastCheckedLayerKey = null;
var _gsLastCheckedAt = 0;
var _gsLastBadgeState = null;
var _gsLastBadgePublished = false; // idem _gsSyncIsPublished (geoserver.js) - só afeta o tooltip do estado _synced, ver _gsPublishTooltip

// Mesmo vocabulário tier-qualificado de _GS_SYNC_LABELS (geoserver.js) - o nível (sys_/
// db_) reflete só se há sessão ativa (_isLogged) no momento da checagem, já que
// get_active_layer_publish_info lê o banco (geoserver_publish_xml) independente de login.
// "Sincronizado" cobre publicado-de-verdade ou só salvo via "Continuar Depois" - mesmo
// rótulo pros dois (ver _gsPublishTooltip, geoserver.js), a diferença fica só no tooltip.
var _GS_STATUS_LABELS = {
    db_not_found: 'GeoServer: Não Encontrado (DB)',
    sys_not_found: 'GeoServer: Não Encontrado (Geohab)',
    sys_modified: 'GeoServer: Divergente',
    db_synced: 'GeoServer: Sincronizado (DB)',
    sys_synced: 'GeoServer: Publicado'
};

var _GS_STATUS_TOOLTIPS = {
    db_not_found: 'Essa camada ainda não foi publicada nem salva no GeoServer (verificado sem login no Geohab).',
    sys_not_found: 'Essa camada ainda não foi publicada nem salva no GeoServer. Use "Serviços > Configurar Camada" pra começar.',
    // Só aparece depois da checagem AO VIVO (_checkGsSyncOnline, geoserver.js) confirmar
    // que o que está publicado de verdade no GeoServer não bate mais com o que está salvo
    // no banco (ex.: editou o resumo e só "Continuar Depois", sem republicar).
    sys_modified: 'O que está salvo no banco não bate mais com o que está publicado no GeoServer agora. Abra "Serviços > Configurar Camada" e republique pra sincronizar.'
    // db_synced/sys_synced não têm entrada fixa aqui - ver _gsStatusTooltip logo abaixo.
};

// Tooltip do estado GS pro estado atual - _synced é calculado na hora via
// _gsPublishTooltip (geoserver.js, mesma função usada pelo badge do painel GS) porque o
// texto muda conforme foi publicado de verdade ou só salvo no banco
// (_gsLastBadgePublished); os demais estados usam a entrada fixa de _GS_STATUS_TOOLTIPS.
function _gsStatusTooltip(state) {
    if (state === 'sys_synced' || state === 'db_synced') {
        return _gsPublishTooltip(state.split('_')[0], _gsLastBadgePublished);
    }
    return _GS_STATUS_TOOLTIPS[state] || '';
}

function checkGsPublishStatus() {
    if (!document.getElementById('f-title')) return; // editor não está aberto

    // Mesma lógica de cache de checkGnSync (acima) - se já verificamos essa camada
    // recentemente, reaplica na hora em vez de bater no banco/GeoNetwork de novo.
    if (_gsLastCheckedLayerKey === _activeLayerName &&
        (Date.now() - _gsLastCheckedAt) < _GN_RECHECK_STALE_MS) {
        _gsBadgeState = _gsLastBadgeState;
        _refreshGnBadgeLabel();
        return;
    }

    _gsBadgeState = null;
    if (typeof gsBridge === 'undefined') { _refreshGnBadgeLabel(); return; }
    gsBridge.get_active_layer_publish_info('', function (info) {
        if (!document.getElementById('f-title')) return; // painel já trocou
        var tierPrefix = _isLogged ? 'sys' : 'db';
        _gsLastBadgePublished = !!(info && info.saved_published);
        if (!info || !info.publishable) { _gsBadgeState = null; } // não é camada PostGIS - GS não se aplica
        else if (!info.saved_workspace) { _gsBadgeState = tierPrefix + '_not_found'; }
        else { _gsBadgeState = tierPrefix + '_synced'; }
        _gsLastCheckedLayerKey = _activeLayerName;
        _gsLastCheckedAt = Date.now();
        _gsLastBadgeState = _gsBadgeState;
        _refreshGnBadgeLabel();

        // Nível sistema de verdade: o que foi calculado acima só diz se ALGUM destino foi
        // salvo no banco (info.saved_workspace) - não confirma se o que está publicado DE
        // FATO no GeoServer agora ainda bate com ele (usuário pode ter editado o resumo no
        // painel GS e só "Continuar Depois", sem republicar - o banco bate mas o GeoServer
        // ao vivo continua com o conteúdo antigo). Só logado dá pra confirmar isso (REST,
        // ver check_gs_sync) - atualiza o badge combinado com o resultado quando chegar
        // (_onGsSyncChecked, geoserver.js, cobre esse caso mesmo com o painel GS fechado).
        if (typeof _checkGsSyncOnline === 'function') _checkGsSyncOnline(info);
    });
}

// Chamado por updateUserUI (app.js) quando o login muda de verdade (login OU logout) - o
// NÍVEL (sys_/db_) de qualquer badge já calculado depende de _isLogged, então invalida os
// caches de "já verificado recentemente" (_gnLastCheckedLayerKey/_gsLastCheckedLayerKey,
// ver checkGnSync/checkGsPublishStatus) e força uma checagem nova na hora, se o editor
// estiver aberto - sem isso, o usuário loga mas o badge só reflete o Geohab depois de
// sair e voltar (revisitar) pro painel. Coordena os dois lados (GN aqui + GS, ver
// _onGsAuthStateChangedForSync em geoserver.js).
function _onAuthStateChangedForSync() {
    _gnLastCheckedLayerKey = null;
    _gsLastCheckedLayerKey = null;
    if (document.getElementById('f-title')) {
        var data = collectFormData();
        checkGnSync(_gnSyncUuid, (data && data.dateStamp) || '');
        checkGsPublishStatus();
    }
    if (typeof _onGsAuthStateChangedForSync === 'function') _onGsAuthStateChangedForSync();
}

function dismissGnUpdateBanner() {
    var banner = document.getElementById('gn-update-banner');
    if (banner) banner.style.display = 'none';
}

function openGnSearchModal() {
    if (!_requireEditorOpen('buscar um metadado')) return;
    if (typeof gnBridge === 'undefined') return;
    // Registros públicos aparecem mesmo sem login (o Python já busca com sessão anônima
    // nesse caso) - badge com tooltip avisa que logar dá acesso aos do setor também.
    var loginBadge = _isLogged ? '' :
        '<span class="modal-info-badge" onclick="Modal.close();navigate(\'login\')" ' +
        'data-title="Alguns metadados são públicos e aparecem mesmo sem login. Faça login pra ver também os exclusivos do seu setor.">' +
        'Não Autenticado</span>';
    var bodyHtml =
        '<div class="search-wrap">' +
        '<input type="text" id="gn-search-input" class="modal-search-input" placeholder="Buscar metadado publicado no Geohab...">' +
        '<span class="search-spinner" id="gn-search-spinner" style="display:none"></span>' +
        '</div>' +
        '<div id="gn-search-results" class="gn-search-results"></div>';
    Modal.show({ title: 'Baixar metadado do Geohab', message: bodyHtml, headerBadge: loginBadge, buttons: [{ label: 'Fechar', primary: false, onClick: null }] });

    var input = document.getElementById('gn-search-input');
    if (!input) return;
    input.focus();
    input.addEventListener('input', function () {
        clearTimeout(_gnSearchTimer);
        var q = input.value.trim();
        var spinner = document.getElementById('gn-search-spinner');
        if (spinner) spinner.style.display = q ? 'block' : 'none';
        _gnSearchTimer = setTimeout(function () { gnBridge.search_gn_metadata(q); }, 300);
    });
}

function _renderGnSearchResults(results) {
    var spinner = document.getElementById('gn-search-spinner');
    if (spinner) spinner.style.display = 'none';
    var box = document.getElementById('gn-search-results');
    if (!box) return; // modal já foi fechado
    if (!results || !results.length) {
        box.innerHTML = '<div class="suggestion-item" style="color:var(--fg-muted);cursor:default;">Nenhum resultado.</div>';
        return;
    }
    // Mesmo padrão visual da lista de sugestão de contatos (.suggestion-item). Sem badge
    // aqui - toda essa busca já é exclusivamente no catálogo online, seria redundante.
    box.innerHTML = results.map(function (r) {
        return '<div class="suggestion-item" onclick="pullGnRecord(\'' + escHtml(r.uuid) + '\')">' +
            '<span>' + escHtml(r.title) + '</span>' +
            '</div>';
    }).join('');
}

function pullGnRecord(uuid) {
    Modal.close();
    Modal.confirm('Isso vai substituir os dados atuais do formulário. Continuar?', function () {
        gnBridge.pull_from_gn(uuid, function (data) {
            if (!data) {
                Modal.alert('Não foi possível carregar esse registro do Geohab.', 'Erro', 'error');
                return;
            }
            resetEditorForm();
            populateForm(data);
            _saveDraftNow();
            checkGnSync(data.metadata_uuid, data.dateStamp || '');
            Modal.alert('Metadado baixado do Geohab com sucesso.<br>Confira os campos preenchidos no formulário.', 'Baixado', 'success');
        });
    }, 'Puxar do Geohab');
}

// Guard comum pra qualquer ação do menu Arquivo que dependa do editor estar aberto -
// mesmo toast "Ação Necessária" pra todas (exportar, importar, buscar, descartar).
function _requireEditorOpen(actionVerb) {
    if (document.getElementById("f-title")) return true;
    Modal.alert('Abra "Catálogo > Editor de Metadados" antes de ' + actionVerb + '.', 'Ação Necessária', 'warning');
    return false;
}

function collectFormData() {
    if (!_requireEditorOpen('exportar')) return null;
    var get = function (id) {
        var el = document.getElementById("f-" + id);
        return el ? el.value.trim() : "";
    };
    // Map first contact to flat fields for XML generator compatibility
    var c = contacts.length > 0 ? contacts[0].data : {};

    return {
        title: get("title"),
        dateType: get("dateType"),
        date: get("date"),
        edition: get("edition") || "1",
        date_edition: get("date_edition"),
        abstract: get("abstract"),
        purpose: get("purpose"),
        credit: get("credit"),
        status_codeListValue: get("status_codeListValue"),
        MD_Keywords: keywords.slice(),
        maintenanceFrequency: get("maintenanceFrequency"),
        dateOfNextUpdate: get("dateOfNextUpdate"),
        MD_SpatialRepresentationTypeCode: get("MD_SpatialRepresentationTypeCode"),
        topicCategory: get("topicCategory"),
        hierarchyLevel: get("hierarchyLevel"),
        LanguageCode: get("LanguageCode"),
        characterSet: get("characterSet"),
        thumbnail_url: get("thumbnail_url"),
        westBoundLongitude: get("westBoundLongitude"),
        eastBoundLongitude: get("eastBoundLongitude"),
        southBoundLatitude: get("southBoundLatitude"),
        northBoundLatitude: get("northBoundLatitude"),
        spatialResolution_denominator: get("spatialResolution_denominator"),
        epsgCode: get("epsgCode"),
        epsgTitle: get("epsgTitle"),
        zMin: get("zMin"),
        zMax: get("zMax"),
        temporalFrom: get("temporalFrom"),
        temporalTo: get("temporalTo"),
        dateStamp: get("dateStamp"),
        statement: get("statement"),
        processStep: get("processStep"),
        sourceDescription: get("sourceDescription"),
        processorContacts: procContacts,
        metadataId: get("metadataId"),
        metadata_uuid: get("metadataId"), // alias - mesma chave usada por xml_parser.py/pull do GN
        metadataLanguage: get("metadataLanguage"),
        metadataAuthorContacts: metaContacts,
        onlineResources: distResources.slice(),
        licenseType: get("licenseType"),
        useLimitation: get("useLimitation"),
        accessConstraints: get("accessConstraints"),
        useConstraints: get("useConstraints"),
        otherConstraints: get("otherConstraints"),
        // Flat contact fields (first contact) for XML generator
        contact_individualName: c.sigla || "",
        contact_organisationName: c.org || "",
        contact_positionName: c.position || "",
        contact_phone: c.phone || "",
        contact_deliveryPoint: _combineAddr(c),
        contact_city: c.city || "",
        contact_administrativeArea: c.state || "",
        contact_postalCode: c.zip || "",
        contact_country: c.country || "Brasil",
        contact_email: c.email || "",
        contact_role: c.role || "",
        contacts: contacts
    };
}

var REQUIRED_LABELS = {
    title: "Título",
    dateType: "Tipo de Data",
    date: "Data do Dado",
    maintenanceFrequency: "Frequência de Atualização",
    abstract: "Resumo",
    credit: "Crédito",
    status_codeListValue: "Status",
    MD_Keywords: "Palavras-chave",
    MD_SpatialRepresentationTypeCode: "Tipo de Representação Espacial",
    topicCategory: "Categoria Temática",
    hierarchyLevel: "Nível Hierárquico",
    LanguageCode: "Idioma",
    westBoundLongitude: "Longitude Oeste",
    eastBoundLongitude: "Longitude Leste",
    southBoundLatitude: "Latitude Sul",
    northBoundLatitude: "Latitude Norte",
    epsgCode: "Código EPSG",
    epsgTitle: "Título do SRC",
    metadataLanguage: "Idioma do Metadado"
};

function validateForm(data, silent) {
    var missing = [];
    for (var key in REQUIRED_LABELS) {
        var val = data[key];
        var empty = !val || (Array.isArray(val) && val.length === 0) || String(val).trim() === "";
        if (empty) {
            if (!silent) {
                if (key === "MD_Keywords") {
                    var chipsBox = document.getElementById("keyword-chips");
                    if (chipsBox) chipsBox.style.outline = "2px solid var(--accent)";
                } else {
                    var el = document.getElementById("f-" + key);
                    if (el) {
                        el.classList.add("error");
                        var cs = el.nextElementSibling;
                        if (cs && cs.classList.contains("custom-select")) cs.classList.add("error");
                    }
                }
            }
            missing.push(REQUIRED_LABELS[key]);
        } else {
            if (key === "MD_Keywords") {
                var chipsBox2 = document.getElementById("keyword-chips");
                if (chipsBox2) chipsBox2.style.outline = "";
            } else {
                var el2 = document.getElementById("f-" + key);
                if (el2) {
                    el2.classList.remove("error");
                    var cs2 = el2.nextElementSibling;
                    if (cs2 && cs2.classList.contains("custom-select")) cs2.classList.remove("error");
                }
            }
        }
    }

    // Contato do Recurso
    var cTable = document.getElementById("contacts-tbody");
    if (contacts.length === 0) {
        if (!silent && cTable) cTable.closest('table').style.outline = "2px solid var(--accent)";
        missing.push("Contato do Recurso");
    } else {
        if (cTable) cTable.closest('table').style.outline = "";
        if (!contacts[0].data.role) missing.push("Responsabilidade do Contato");
    }

    // Contato de Metadado
    var mTable = document.getElementById("meta-tbody");
    if (metaContacts.length === 0) {
        if (!silent && mTable) mTable.closest('table').style.outline = "2px solid var(--accent)";
        missing.push("Contato de Metadado");
    } else {
        if (mTable) mTable.closest('table').style.outline = "";
    }

    return missing;
}

// ─── Atualização de Progresso ────────────────────────────────────────────────
function updateFormProgress(e) {
    // Se o evento vier da caixa de busca, ignoramos para não causar resets visuais estranhos
    if (e && e.target && e.target.id === 'contact-search') return;

    var data = collectFormData();
    if (!data) return;

    var missing = validateForm(data, true); // true = silent, don't show red borders
    // +1 Contato do Recurso, +1 Contato de Metadado, +1 Responsabilidade (só conta se já há contato)
    var extraFields = 2 + (contacts.length > 0 ? 1 : 0);
    var totalRequired = Object.keys(REQUIRED_LABELS).length + extraFields;
    var missingCount = missing.length;
    var filledCount = totalRequired - missingCount;
    var pct = Math.round((filledCount / totalRequired) * 100);

    var spinner = document.getElementById('form-progress-spinner');
    var text = document.getElementById('form-progress-text');

    if (spinner && text) {
        spinner.style.setProperty('--progress', pct);
        text.textContent = pct + '%';
        if (pct >= 100) {
            spinner.classList.add('completed');
        } else {
            spinner.classList.remove('completed');
        }
    }
}

var FIELD_GROUPS = {
    "Identificação": ["Título", "Tipo de Data", "Data do Dado", "Frequência de Atualização", "Status", "Resumo", "Crédito", "Palavras-chave"],
    "Contato": ["Contato do Recurso", "Responsabilidade do Contato"],
    "Classificação": ["Tipo de Representação Espacial", "Categoria Temática", "Nível Hierárquico", "Idioma"],
    "Extensão": ["Longitude Oeste", "Longitude Leste", "Latitude Sul", "Latitude Norte", "Código EPSG", "Título do SRC"],
    "Metadado": ["Idioma do Metadado", "Contato de Metadado"]
};

function showValidationError(missing) {
    // Agrupar campos por seção
    var grouped = {};
    missing.forEach(function (field) {
        var found = false;
        for (var group in FIELD_GROUPS) {
            if (FIELD_GROUPS[group].indexOf(field) !== -1) {
                if (!grouped[group]) grouped[group] = [];
                grouped[group].push(field);
                found = true;
                break;
            }
        }
        if (!found) {
            if (!grouped['Outros']) grouped['Outros'] = [];
            grouped['Outros'].push(field);
        }
    });

    var html = '<p style="color:var(--fg-muted);margin-bottom:12px">Complete os campos abaixo para exportar o metadado:</p>';

    // Iterar sobre FIELD_GROUPS para garantir a ordem definida
    for (var group in FIELD_GROUPS) {
        if (grouped[group]) {
            html += '<div style="margin-bottom:10px">';
            html += '<div style="font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:0.05em;color:var(--fg-muted);margin-bottom:6px">' + group + '</div>';
            html += '<div style="display:flex;flex-wrap:wrap;gap:6px">';
            grouped[group].forEach(function (f) {
                html += '<span style="background:#fee2e2;color:#b91c1c;font-size:12px;font-weight:600;padding:3px 10px;border-radius:20px;white-space:nowrap">' + f + '</span>';
            });
            html += '</div></div>';
        }
    }

    // Se houver algum grupo extra (Outros)
    if (grouped['Outros']) {
        html += '<div style="margin-bottom:10px">';
        html += '<div style="font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:0.05em;color:var(--fg-muted);margin-bottom:6px">Outros</div>';
        html += '<div style="display:flex;flex-wrap:wrap;gap:6px">';
        grouped['Outros'].forEach(function (f) {
            html += '<span style="background:#fee2e2;color:#b91c1c;font-size:12px;font-weight:600;padding:3px 10px;border-radius:20px;white-space:nowrap">' + f + '</span>';
        });
        html += '</div></div>';
    }

    Modal.show({
        title: missing.length + ' campo' + (missing.length > 1 ? 's' : '') + ' pendente' + (missing.length > 1 ? 's' : ''),
        message: html,
        type: 'error'
    });
}

function populateForm(data) {
    if (!data) return;
    var SIMPLE_FIELDS = [
        "title", "dateType", "date", "edition", "date_edition",
        "abstract", "purpose", "credit", "status_codeListValue",
        "maintenanceFrequency", "dateOfNextUpdate",
        "MD_SpatialRepresentationTypeCode", "topicCategory", "hierarchyLevel",
        "LanguageCode", "characterSet", "thumbnail_url",
        "westBoundLongitude", "eastBoundLongitude", "southBoundLatitude", "northBoundLatitude",
        "spatialResolution_denominator", "epsgCode", "epsgTitle",
        "zMin", "zMax", "temporalFrom", "temporalTo", "dateStamp",
        "statement", "processStep", "sourceDescription",
        "metadataId", "metadataLanguage",
        "licenseType", "useLimitation", "accessConstraints", "useConstraints", "otherConstraints"
    ];
    SIMPLE_FIELDS.forEach(function (key) {
        var el = document.getElementById("f-" + key);
        if (el && data[key] !== undefined && data[key] !== null) {
            el.value = data[key];
            updateCustomSelect(el);
        }
    });
    // metadata_uuid (chave usada pelo xml_parser.py/GN) é alias de metadataId (chave do
    // campo do form) - sem isso, dado puxado do GN ou importado de arquivo local não
    // preenche o UUID real do registro, mantendo o UUID aleatório do resetEditorForm().
    if (data.metadata_uuid) {
        var uidEl = document.getElementById('f-metadataId');
        if (uidEl) uidEl.value = data.metadata_uuid;
    }
    if (Array.isArray(data.MD_Keywords) && data.MD_Keywords.length) {
        keywords = data.MD_Keywords.slice();
        renderKeywords();
    }
    var mf = document.getElementById("f-maintenanceFrequency");
    if (mf) toggleUpdateDate(mf.value);
    var ed = document.getElementById("f-edition");
    if (ed) toggleEditionDate(ed.value);
    if (Array.isArray(data.contacts) && data.contacts.length > 0) {
        contacts = data.contacts;
        renderContacts();
    }
    if (Array.isArray(data.processorContacts)) {
        procContacts = data.processorContacts;
        renderFor('proc');
    }
    if (Array.isArray(data.metadataAuthorContacts)) {
        metaContacts = data.metadataAuthorContacts;
        renderFor('meta');
    }
    if (Array.isArray(data.onlineResources)) {
        distResources = data.onlineResources.slice();
        renderDistResources();
    }
    updateFormProgress();
    _updateThumbnailPreview();
}

// ─── Edição condicional ────────────────────────────────────────────────────────

function toggleEditionDate(val) {
    var el = document.getElementById("f-date_edition");
    if (!el) return;
    var hasValue = parseInt(val, 10) > 0;
    el.disabled = !hasValue;
    if (!hasValue) el.value = "";
}

function toggleUpdateDate(val) {
    var el = document.getElementById("f-dateOfNextUpdate");
    if (!el) return;
    el.disabled = !val;
    if (!val) el.value = "";
}

// ─── Sistema de Referência ────────────────────────────────────────────────────

var EPSG_TITLES = {
    "EPSG:4326": "WGS 84",
    "EPSG:4674": "SIRGAS 2000",
    "EPSG:4618": "SAD69",
    "EPSG:31978": "SIRGAS 2000 / UTM zone 18S",
    "EPSG:31979": "SIRGAS 2000 / UTM zone 19S",
    "EPSG:31980": "SIRGAS 2000 / UTM zone 20S",
    "EPSG:31981": "SIRGAS 2000 / UTM zone 21S",
    "EPSG:31982": "SIRGAS 2000 / UTM zone 22S",
    "EPSG:31983": "SIRGAS 2000 / UTM zone 23S",
    "EPSG:31984": "SIRGAS 2000 / UTM zone 24S",
    "EPSG:31985": "SIRGAS 2000 / UTM zone 25S",
    "EPSG:29191": "SAD69 / UTM zone 21S",
    "EPSG:29192": "SAD69 / UTM zone 22S",
    "EPSG:29193": "SAD69 / UTM zone 23S",
    "EPSG:29194": "SAD69 / UTM zone 24S",
    "EPSG:32722": "WGS 84 / UTM zone 22S",
    "EPSG:32723": "WGS 84 / UTM zone 23S",
    "EPSG:32724": "WGS 84 / UTM zone 24S"
};

function setEpsgFromCode(val) {
    var titleEl = document.getElementById("f-epsgTitle");
    if (!titleEl || !val) return;
    var name = EPSG_TITLES[val];
    titleEl.value = name ? name + " (" + val + ")" : val;
}

function captureFromLayer() {
    if (typeof bridge === "undefined") { Modal.alert("Disponível apenas no QGIS.", "Aviso", "info"); return; }
    bridge.get_layer_info(function (result) {
        if (!result) { Modal.alert("Nenhuma camada ativa ou informações não disponíveis.", "Erro", "error"); return; }
        var codeEl = document.getElementById("f-epsgCode");
        var titleEl = document.getElementById("f-epsgTitle");
        if (codeEl) {
            codeEl.value = result.code || "";
            updateCustomSelect(codeEl);
        }
        if (titleEl) titleEl.value = result.title || "";
        if (result.north !== undefined) {
            var n = document.getElementById("f-northBoundLatitude");
            var s = document.getElementById("f-southBoundLatitude");
            var e = document.getElementById("f-eastBoundLongitude");
            var w = document.getElementById("f-westBoundLongitude");
            if (n) n.value = result.north;
            if (s) s.value = result.south;
            if (e) e.value = result.east;
            if (w) w.value = result.west;
        }
        updateFormProgress();
    });
}

// ─── Keywords chips ────────────────────────────────────────────────────────────

var keywords = [];

function addKeyword() {
    var inp = document.getElementById('kw-input');
    if (!inp) return;
    var val = inp.value.trim();
    if (!val) { inp.value = ''; return; }
    val = val.charAt(0).toUpperCase() + val.slice(1);
    if (keywords.indexOf(val) !== -1) { inp.value = ''; return; }
    keywords.push(val);
    inp.value = '';
    renderKeywords();
}

function removeKeyword(i) {
    keywords.splice(i, 1);
    renderKeywords();
}

function renderKeywords() {
    var box = document.getElementById('keyword-chips');
    if (!box) return;
    box.innerHTML = keywords.map(function (kw, i) {
        return '<span class="keyword-chip">' + escHtml(kw) +
            '<button onclick="removeKeyword(' + i + ')" data-title="Remover">×</button></span>';
    }).join('');
    updateFormProgress();
    _scheduleDraftSave();
}

// ─── Distribuição: recursos online ────────────────────────────────────────────

var distResources = [];
var _distSugg = [];
var _distStagedLayer = null;

function searchGeoServer(q) {
    var box = document.getElementById('dist-suggestions');
    var spinner = document.getElementById('dist-spinner');
    if (!q || q.length < 2) {
        if (box) box.style.display = 'none';
        if (spinner) spinner.style.display = 'none';
        return;
    }
    if (typeof gsBridge !== 'undefined' && gsBridge.search_geoserver) {
        if (spinner) spinner.style.display = 'inline-block';
        gsBridge.search_geoserver(q, function (results) {
            if (spinner) spinner.style.display = 'none';
            _distSugg = results || [];
            renderDistSugg();
        });
    }
}

function renderDistSugg() {
    var box = document.getElementById('dist-suggestions');
    if (!box) return;
    if (!_distSugg.length) { box.style.display = 'none'; return; }
    box.innerHTML = _distSugg.map(function (r, i) {
        return '<div class="suggestion-item" onclick="pickGeoServerLayer(' + i + ')">' +
            '<span class="sugg-name"><b>' + escHtml(r.workspace || '') + '</b> - ' + escHtml(r.title || r.name || '') + '</span>' +
            '</div>';
    }).join('');
    box.style.display = 'block';
}

function closeDistSugg() {
    var box = document.getElementById('dist-suggestions');
    if (box) box.style.display = 'none';
    _distSugg = [];
}

function pickGeoServerLayer(idx) {
    _distStagedLayer = _distSugg[idx];
    closeDistSugg();
    var inp = document.getElementById('dist-search');
    if (inp) inp.value = '';
    renderDistLayerCard();
}

function renderDistLayerCard() {
    var card = document.getElementById('dist-layer-card');
    if (!card || !_distStagedLayer) return;
    var l = _distStagedLayer;
    var nameEl = document.getElementById('dist-card-name');
    var wsEl = document.getElementById('dist-card-ws');
    if (nameEl) nameEl.textContent = l.title || l.name || '';
    if (wsEl) wsEl.textContent = l.workspace || '';

    var wmsChk = document.getElementById('dist-pick-wms');
    var wfsChk = document.getElementById('dist-pick-wfs');
    var wcsChk = document.getElementById('dist-pick-wcs');
    var wfsToggle = wfsChk ? wfsChk.closest('.dist-proto-toggle') : null;
    var wcsToggle = wcsChk ? wcsChk.closest('.dist-proto-toggle') : null;

    // WMS - sempre disponível (público)
    if (wmsChk) { wmsChk.checked = true; wmsChk.disabled = false; }

    // WFS - só se autenticado (vem como wfs_available do bridge, ou _isLogged)
    var wfsOk = !!(l.wfs_available !== undefined ? l.wfs_available : _isLogged);
    if (wfsChk) {
        wfsChk.checked = false;   // opt-in: user decide se quer WFS
        wfsChk.disabled = !wfsOk;
    }
    if (wfsToggle) {
        wfsToggle.title = wfsOk ? '' : 'Requer autenticação';
        wfsToggle.style.opacity = wfsOk ? '' : '0.45';
    }

    // WCS - nunca disponível via WMS caps (raster needs separate check)
    if (wcsChk) { wcsChk.checked = false; wcsChk.disabled = true; }
    if (wcsToggle) { wcsToggle.style.display = 'none'; }

    card.style.display = 'block';
}

function cancelDistLayer() {
    _distStagedLayer = null;
    var card = document.getElementById('dist-layer-card');
    if (card) card.style.display = 'none';
}

function _distDuplicate(url, proto) {
    return distResources.some(function (r) { return r.url === url && r.protocol === proto; });
}

function confirmDistLayer() {
    if (!_distStagedLayer) return;
    var l = _distStagedLayer;
    var pairs = [
        { id: 'dist-pick-wms', proto: 'OGC:WMS', url: l.wms_url },
        { id: 'dist-pick-wfs', proto: 'OGC:WFS', url: l.wfs_url },
        { id: 'dist-pick-wcs', proto: 'OGC:WCS', url: l.wcs_url }
    ];
    var skipped = 0;
    pairs.forEach(function (p) {
        var cb = document.getElementById(p.id);
        if (cb && cb.checked && p.url) {
            if (_distDuplicate(p.url, p.proto)) { skipped++; return; }
            distResources.push({ url: p.url, protocol: p.proto, name: l.name || '', description: l.title || '' });
        }
    });
    if (skipped) alert('Serviço(s) já adicionado(s) foram ignorados.');

    var wmsChk = document.getElementById('dist-pick-wms');
    if (wmsChk && wmsChk.checked && l.wms_url && l.name) {
        _maybeAutoFillThumbnail(l);
    }

    cancelDistLayer();
    renderDistResources();
}

// Aplica o vínculo WMS+WFS pendente de uma publicação recém-feita no GeoServer (aba GS ->
// gs_publish_done -> window._pendingGsDistLayer, ver geoserver.js). Chamada a partir de
// _loadFormForLayer() depois que o formulário do editor termina de carregar pra essa
// camada (populateForm, quando existe metadado salvo, sobrescreve distResources - por
// isso não dá pra aplicar isso ANTES do form carregar, senão o vínculo seria perdido).
// WFS entra como default aqui (diferente do fluxo manual de busca, onde é opt-in) porque
// a camada acabou de ser publicada pelo próprio usuário autenticado - WFS sempre disponível.
function _applyPendingGsDistLayerIfAny() {
    var l = window._pendingGsDistLayer;
    window._pendingGsDistLayer = null;
    if (!l || !l.wms_url || !l.name) return;
    if (!document.getElementById('f-title')) return; // editor não está mais aberto, desiste

    var distBtn = document.querySelector('.tab-link[onclick*="distribuicao"]');
    if (distBtn) showTab('distribuicao', distBtn);

    var linked = [];
    var alreadyHadWms = _distDuplicate(l.wms_url, 'OGC:WMS');
    if (!alreadyHadWms) {
        distResources.push({ url: l.wms_url, protocol: 'OGC:WMS', name: l.name, description: l.title || l.name });
        linked.push('WMS');
    }
    var alreadyHadWfs = !l.wfs_url || _distDuplicate(l.wfs_url, 'OGC:WFS');
    if (!alreadyHadWfs) {
        distResources.push({ url: l.wfs_url, protocol: 'OGC:WFS', name: l.name, description: l.title || l.name });
        linked.push('WFS');
    }
    if (linked.length) {
        renderDistResources();
        updateFormProgress();
        _scheduleDraftSave();
    }

    var thumbFilled = _maybeAutoFillThumbnail(l, true); // silencioso - o toast final é montado abaixo

    var parts = ['Camada "' + escHtml(l.title || l.name) + '" publicada com sucesso no GeoServer.'];
    if (linked.length) parts.push('Vinculada automaticamente aqui em Distribuição (' + linked.join(' + ') + ').');
    if (thumbFilled) parts.push('Miniatura gerada automaticamente na aba Classificação.');
    Modal.alert(parts.join('<br>'), 'Sucesso', 'success');
}

// Gera uma miniatura (WMS GetMap) a partir da camada do GeoServer recém-associada em
// Distribuição e preenche "Classificação > URL da Miniatura" - só se o campo estiver
// vazio, pra nunca sobrescrever uma URL externa que o usuário já tenha colocado lá.
function _buildWmsThumbnailUrl(wmsUrl, layerName) {
    var w = document.getElementById('f-westBoundLongitude');
    var e = document.getElementById('f-eastBoundLongitude');
    var s = document.getElementById('f-southBoundLatitude');
    var n = document.getElementById('f-northBoundLatitude');
    var bbox = (w && w.value && e && e.value && s && s.value && n && n.value)
        ? [w.value, s.value, e.value, n.value].join(',')
        : '-180,-90,180,90'; // sem extensão preenchida ainda (aba Extensão) - cai pro mundo todo
    return wmsUrl + '&version=1.1.0&request=GetMap&layers=' + encodeURIComponent(layerName) +
        '&bbox=' + bbox + '&width=768&height=478&srs=CRS:84&styles=&format=image%2Fpng';
}

function _maybeAutoFillThumbnail(l, silent) {
    var thumbEl = document.getElementById('f-thumbnail_url');
    if (!thumbEl || thumbEl.value.trim()) return false;

    thumbEl.value = _buildWmsThumbnailUrl(l.wms_url, l.name);
    updateFormProgress();
    _scheduleDraftSave();
    _updateThumbnailPreview();

    if (!silent) {
        Modal.alert(
            'A URL da miniatura (aba Classificação) foi preenchida automaticamente com uma imagem gerada a partir da camada do GeoServer que você acabou de associar.' +
            '<br><br>Se preferir, pode substituir por qualquer outra URL externa.',
            'Miniatura gerada automaticamente', 'info'
        );
    }
    return true;
}

// Atalho ao lado do campo "URL da Miniatura": se já existe um WMS associado em
// Distribuição, gera a miniatura a partir dele (sobrescrevendo, já que é ação explícita
// do usuário); senão, leva até a aba Distribuição pra associar um primeiro.
function fillThumbnailFromWms() {
    var wmsResource = distResources.find(function (r) { return r.protocol === 'OGC:WMS'; });
    if (!wmsResource) {
        var distBtn = document.querySelector('.tab-link[onclick*="distribuicao"]');
        showTab('distribuicao', distBtn);
        Modal.alert('Nenhum WMS associado ainda.<br><br>Associe uma camada do GeoServer aqui em Distribuição pra poder gerar a miniatura a partir dela.', 'Sem WMS associado', 'info');
        return;
    }
    var thumbEl = document.getElementById('f-thumbnail_url');
    if (!thumbEl) return;
    thumbEl.value = _buildWmsThumbnailUrl(wmsResource.url, wmsResource.name);
    updateFormProgress();
    _scheduleDraftSave();
    _updateThumbnailPreview();
}

function toggleDistManual() {
    var wrap = document.getElementById('dist-manual-wrap');
    if (!wrap) return;
    wrap.style.display = (wrap.style.display === 'none' || !wrap.style.display) ? 'block' : 'none';
}

function submitDistManual() {
    var urlEl = document.getElementById('dist-mf-url');
    var url = urlEl ? urlEl.value.trim() : '';
    if (!url) { Modal.alert('Informe a URL do recurso.', 'Aviso', 'warning'); return; }
    var proto = (document.getElementById('dist-mf-protocol') || {}).value || 'OGC:WMS';
    var name = ((document.getElementById('dist-mf-name') || {}).value || '').trim();
    var desc = ((document.getElementById('dist-mf-description') || {}).value || '').trim();
    if (_distDuplicate(url, proto)) { Modal.alert('Este recurso já foi adicionado.', 'Duplicado', 'warning'); return; }
    distResources.push({ url: url, protocol: proto, name: name, description: desc });
    ['dist-mf-url', 'dist-mf-name', 'dist-mf-description'].forEach(function (id) {
        var el = document.getElementById(id); if (el) el.value = '';
    });
    toggleDistManual();
    renderDistResources();
}

function removeDistResource(i) {
    distResources.splice(i, 1);
    renderDistResources();
}

function renderDistResources() {
    var tbody = document.getElementById('dist-tbody');
    if (!tbody) return;
    if (!distResources.length) {
        tbody.innerHTML = '<tr><td colspan="5" class="empty-state">Nenhum recurso adicionado.</td></tr>';
        _scheduleDraftSave();
        return;
    }
    var protoCls = { 'OGC:WMS': 'wms', 'OGC:WFS': 'wfs', 'OGC:WCS': 'wcs', 'OGC:WPS': 'wps', 'WWW:DOWNLOAD': 'download' };
    var protoLabel = { 'OGC:WMS': 'WMS', 'OGC:WFS': 'WFS', 'OGC:WCS': 'WCS', 'OGC:WPS': 'WPS', 'WWW:DOWNLOAD': 'DOWN', 'WWW:LINK': 'LINK' };
    tbody.innerHTML = distResources.map(function (r, i) {
        var cls = protoCls[r.protocol] || 'link';
        var lbl = protoLabel[r.protocol] || r.protocol;
        return '<tr>' +
            '<td style="text-align:center">' + (i + 1) + '</td>' +
            '<td>' + escHtml(r.name || '-') +
            (r.description ? '<br><small style="color:var(--fg-muted)">' + escHtml(r.description) + '</small>' : '') +
            '</td>' +
            '<td><span class="proto-badge ' + cls + '" data-title="' + escHtml(r.protocol) + '">' + escHtml(lbl) + '</span></td>' +
            '<td style="font-size:11px;color:var(--fg-muted);max-width:160px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" data-title="' + escHtml(r.url) + '">' + escHtml(r.url) + '</td>' +
            '<td><button class="btn-remove" onclick="removeDistResource(' + i + ')" data-title="Remover">✕</button></td>' +
            '</tr>';
    }).join('');
    _scheduleDraftSave();
}

// ─── Licença: preenchimento automático por tipo ────────────────────────────────

var _licensePresets = {
    'CC BY 4.0': { useLimitation: 'Creative Commons Atribuição 4.0 Internacional (CC BY 4.0). Permite uso, distribuição e adaptação para qualquer fim, inclusive comercial, desde que a fonte seja atribuída.', accessConstraints: 'license', useConstraints: 'license', otherConstraints: '' },
    'CC BY-SA 4.0': { useLimitation: 'Creative Commons Atribuição-CompartilhaIgual 4.0 Internacional (CC BY-SA 4.0). Derivados devem ser distribuídos sob a mesma licença.', accessConstraints: 'license', useConstraints: 'license', otherConstraints: '' },
    'CC BY-NC 4.0': { useLimitation: 'Creative Commons Atribuição-NãoComercial 4.0 Internacional (CC BY-NC 4.0). Uso não comercial apenas.', accessConstraints: 'license', useConstraints: 'license', otherConstraints: '' },
    'CC BY-NC-SA 4.0': { useLimitation: 'Creative Commons Atribuição-NãoComercial-CompartilhaIgual 4.0 Internacional (CC BY-NC-SA 4.0).', accessConstraints: 'license', useConstraints: 'license', otherConstraints: '' },
    'CC0': { useLimitation: 'CC0 1.0 Dedicação ao Domínio Público. Nenhum direito reservado.', accessConstraints: 'unrestricted', useConstraints: 'unrestricted', otherConstraints: '' },
    'proprietary': { useLimitation: 'Todos os direitos reservados. Uso autorizado exclusivamente conforme termos estabelecidos pela CDHU.', accessConstraints: 'copyright', useConstraints: 'intellectualPropertyRights', otherConstraints: '© CDHU - Companhia de Desenvolvimento Habitacional e Urbano do Estado de São Paulo. Todos os direitos reservados.' },
    'internal': { useLimitation: 'Uso interno restrito à CDHU e suas unidades. Distribuição externa não autorizada.', accessConstraints: 'restricted', useConstraints: 'restricted', otherConstraints: '© CDHU - Companhia de Desenvolvimento Habitacional e Urbano do Estado de São Paulo. Documento de uso interno.' }
};

function onLicenseChange(val) {
    var preset = _licensePresets[val];
    if (!preset) return;
    var ul = document.getElementById('f-useLimitation');
    var ac = document.getElementById('f-accessConstraints');
    var uc = document.getElementById('f-useConstraints');
    var oc = document.getElementById('f-otherConstraints');
    if (ul && !ul.value) ul.value = preset.useLimitation;
    if (ac) ac.value = preset.accessConstraints;
    if (uc) uc.value = preset.useConstraints;
    if (oc && !oc.value) oc.value = preset.otherConstraints;
}

// ─── Contatos: estado ──────────────────────────────────────────────────────────

var contacts = [];

var ROLE_LABELS = {
    "owner": "Dono",
    "author": "Autor",
    "processor": "Organizador",
    "distributor": "Distribuidor",
    "custodian": "Depositário",
    "resourceProvider": "Fornecedor de recurso",
    "principalInvestigator": "Investigador principal",
    "originator": "Originador",
    "pointOfContact": "Ponto de contato",
    "publisher": "Publicador",
    "user": "Utilizador"
};

var ROLE_TITLES = {
    "owner": "Setor proprietário ou responsável legal pelo dado",
    "author": "Quem elaborou o conteúdo técnico ou intelectual do dado",
    "processor": "Quem realizou o tratamento, organização ou limpeza dos dados",
    "distributor": "Responsável por disponibilizar e entregar o dado ao público",
    "custodian": "Responsável pela guarda, armazenamento e manutenção do dado",
    "resourceProvider": "Entidade que fornece a fonte original ou infraestrutura",
    "principalInvestigator": "Responsável técnico ou científico principal pelo projeto",
    "originator": "Fonte primária de onde a informação foi gerada",
    "pointOfContact": "Setor responsável por tirar dúvidas e dar suporte sobre o dado",
    "publisher": "Responsável pela publicação oficial do dado no catálogo",
    "user": "Usuário ou consumidor final da informação"
};

var ROLE_OPTIONS = Object.keys(ROLE_LABELS).map(function (v) {
    return { value: v, label: ROLE_LABELS[v], title: ROLE_TITLES[v] || "" };
});

function buildRoleSelect(idx, current) {
    var selected = current || "pointOfContact";
    if (contacts[idx]) contacts[idx].data.role = contacts[idx].data.role || selected;
    var opts = ROLE_OPTIONS.map(function (r) {
        var t = r.title ? ' data-title="' + r.title + '"' : '';
        return '<option value="' + r.value + '"' + (r.value === selected ? ' selected' : '') + t + '>' + r.label + '</option>';
    }).join('');
    return '<select id="role-table-' + idx + '" class="role-select" onchange="updateRole(' + idx + ', this.value)">' + opts + '</select>';
}

function updateRole(idx, val) {
    if (!contacts[idx]) return;
    contacts[idx].data.role = val;
    var tableSelect = document.getElementById("role-table-" + idx);
    var accSelect = document.getElementById("role-acc-" + idx);

    if (tableSelect && tableSelect.value !== val) {
        tableSelect.value = val;
        tableSelect.dispatchEvent(new Event('change', { bubbles: true }));
    }
    if (accSelect && accSelect.value !== val) {
        accSelect.value = val;
        accSelect.dispatchEvent(new Event('change', { bubbles: true }));
    }
}

// ─── Contatos: render ──────────────────────────────────────────────────────────

var _accEditing = {};

function _getContactArr(source) { return source === 'main' ? contacts : _sArr(source); }
function _getAccBodyId(source, idx) { return source === 'main' ? 'acc-body-' + idx : 'acc-body-' + source + '-' + idx; }
function _getIdPfx(source, idx) { return source === 'main' ? 'acc-' + idx + '-' : 'af-' + source + '-' + idx + '-'; }

function _combineAddr(d) {
    return [d.addr_street || d.address, d.addr_num, d.addr_comp, d.addr_bairro].filter(Boolean).join(', ');
}

function _buildRoleSelectHtml(source, idx, role) {
    var sel = role || 'pointOfContact';
    var opts = ROLE_OPTIONS.map(function (r) {
        var t = r.title ? ' data-title="' + r.title + '"' : '';
        return '<option value="' + r.value + '"' + (r.value === sel ? ' selected' : '') + t + '>' + r.label + '</option>';
    }).join('');
    var selectId = source === 'main' ? 'role-acc-' + idx : 'role-' + source + '-a-' + idx;
    var onchange = source === 'main'
        ? 'updateRole(' + idx + ', this.value)'
        : 'updateRoleFor(\'' + source + '\',' + idx + ',this.value)';
    return '<div class="form-group"><label>Regra <button class="help-btn" data-tip="Papel desta organização ou pessoa em relação ao dado (ex: Dono = responsável; Ponto de contato = para dúvidas).">?</button></label>' +
        '<select id="' + selectId + '" class="role-select" onchange="' + onchange + '">' + opts + '</select></div>';
}

function _buildContactFields(d, pfx, isEditing, roleSelectHtml) {
    var e = isEditing;
    var addr = _combineAddr(d);
    var addrHtml = isEditing
        ? '<div class="form-group span-2"><label>Endereço <button class="help-btn" data-tip="Logradouro completo da organização.">?</button></label>' +
        '<div class="address-split">' +
        '<div class="addr-field-wrap addr-street-wrap"><input id="' + pfx + 'addr-street" class="addr-street" type="text" placeholder="Logradouro" value="' + escHtml(d.addr_street || d.address || '') + '"></div>' +
        '<div class="addr-field-wrap addr-num-wrap"><input id="' + pfx + 'addr-num" class="addr-num" type="text" placeholder="Nº" value="' + escHtml(d.addr_num || '') + '"></div>' +
        '<div class="addr-field-wrap addr-comp-wrap"><input id="' + pfx + 'addr-comp" class="addr-comp" type="text" placeholder="Compl." value="' + escHtml(d.addr_comp || '') + '"></div>' +
        '<div class="addr-field-wrap addr-bairro-wrap"><input id="' + pfx + 'addr-bairro" class="addr-bairro" type="text" placeholder="Bairro" value="' + escHtml(d.addr_bairro || '') + '"></div>' +
        '</div></div>'
        : '<div class="form-group span-2"><label>Endereço <button class="help-btn" data-tip="Logradouro completo da organização.">?</button></label>' +
        '<div class="readonly-field">' + escHtml(addr || '-') + '</div></div>';
    return field('Sigla', d.sigla, e, pfx + 'sigla', 'Abreviação ou acrônimo da organização (ex: CDHU, IPT, IBGE).', 'data-format="uppercase"') +
        field('Organização', d.org, e, pfx + 'org', 'Nome completo da organização responsável.', 'data-format="titlecase"') +
        roleSelectHtml +
        field('E-mail', d.email, e, pfx + 'email', 'Endereço de e-mail para contato.', 'data-validate="email"') +
        field('Cargo', d.position, e, pfx + 'position', 'Cargo ou departamento do responsável na organização.', 'data-validate="letters-only"') +
        field('Telefone', d.phone, e, pfx + 'phone', 'Telefone de contato com DDD (ex: (11) 3111-0000).', 'data-format="phone"') +
        addrHtml +
        field('Cidade', d.city, e, pfx + 'city', null, 'data-validate="letters-only"') +
        field('Estado', d.state, e, pfx + 'state') +
        field('CEP', d.zip, e, pfx + 'zip', 'Código de Endereçamento Postal no formato 00000-000.', 'data-format="cep"') +
        field('País', d.country, e, pfx + 'country', null, 'data-validate="letters-only"');
}

function _sourceBadge(c) {
    if (c.isManual === 'gn') return '<span class="badge-gn">Catálogo Online</span>';
    if (c.isManual === true) return '<span class="badge-manual">Manual</span>';
    if (c.isManual === 'user') return '<span class="badge-user">Meus Contatos</span>';
    return '<span class="badge-preset">Catálogo Offline</span>';
}

// Required fields for manual contacts (all except Cargo/position)
var _MANUAL_REQ = [
    { id: 'sigla', label: 'Sigla' },
    { id: 'org', label: 'Organização' },
    { id: 'role', label: 'Regra' },
    { id: 'email', label: 'E-mail' },
    { id: 'phone', label: 'Telefone' },
    { id: '__addr', label: 'Logradouro' },   // mapped to addrFieldId
    { id: '__addr-num', label: 'Número' },        // derived from addrFieldId
    { id: '__addr-comp', label: 'Complemento' },   // derived from addrFieldId
    { id: 'addr-bairro', label: 'Bairro' },
    { id: 'city', label: 'Cidade' },
    { id: 'state', label: 'Estado' },
    { id: 'zip', label: 'CEP' },
    { id: 'country', label: 'País' },
];

// pfx: element ID prefix; addrId: the street field suffix for this form
// Returns true if any required field is empty (also marks fields inline).
function _validateManualForm(pfx, addrId) {
    // accordion uses 'addr-street'; manual forms use 'address'
    var addrBase = addrId === 'addr-street' ? 'addr' : addrId;
    var hasError = false;
    _MANUAL_REQ.forEach(function (f) {
        var fieldId = f.id === '__addr' ? addrId
            : f.id === '__addr-num' ? addrBase + '-num'
                : f.id === '__addr-comp' ? addrBase + '-comp'
                    : f.id;
        var el = document.getElementById(pfx + fieldId);
        if (!el) return;
        if (!el.value.trim()) {
            _setFieldError(el, 'Campo obrigatório.');
            hasError = true;
        } else {
            _clearFieldError(el);
        }
    });
    return hasError;
}

function _isDuplicate(arr, r) {
    return arr.some(function (c) {
        var d = c.data;
        if (r._key && d._key) return r._key === d._key;
        return (r.sigla || '') === (d.sigla || '') &&
            (r.org || '') === (d.org || '') &&
            (r.email || '') === (d.email || '');
    });
}

function _srcToIsManual(src) {
    if (src === 'gn') return 'gn';
    if (src === 'user') return 'user';
    return false;
}

function _buildAccActions(isManual, source, idx, isEditing) {
    var editable = isManual === true || isManual === 'user';
    var btns = '';
    if (editable) {
        if (isEditing) {
            btns += '<button class="btn-save" onclick="saveAccordion(\'' + source + '\',' + idx + ')">Salvar</button>' +
                '<button class="btn-cancel" onclick="cancelAccordion(\'' + source + '\',' + idx + ')">Cancelar</button>';
        } else {
            btns += '<button class="btn-edit" onclick="enterAccordionEdit(\'' + source + '\',' + idx + ')">Editar</button>';
            if (isManual === true) {
                btns += '<button class="btn-save-local" onclick="saveContactLocally(\'' + source + '\',' + idx + ')" data-title="Salvar na máquina para reutilizar em outras sessões">Salvar localmente</button>';
            }
            if (isManual === 'user') {
                btns += '<button class="btn-delete-user" onclick="deleteUserContactFromList(\'' + source + '\',' + idx + ')" data-title="Excluir dos Meus Contatos">Excluir</button>';
            }
        }
    }
    btns += '<button class="btn-export-contact" onclick="exportContactXml(\'' + source + '\',' + idx + ')">Exportar XML</button>';
    return '<div class="acc-actions">' + btns + '</div>';
}

function deleteUserContactFromList(source, idx) {
    var arr = _getContactArr(source);
    var c = arr[idx];
    if (!c) return;
    var name = c.data.sigla || c.data.org || 'este contato';
    Modal.confirm('Excluir "' + name + '" dos Meus Contatos?<br><br>Esta ação remove o contato salvo permanentemente.', function () {
        if (c.data._key) gnBridge.delete_user_contact(c.data._key);
        arr.splice(idx, 1);
        if (source === 'main') renderContacts();
        else renderFor(source);
    }, 'Excluir Contato');
}

function saveContactLocally(source, idx) {
    var arr = _getContactArr(source);
    var c = arr[idx];
    if (!c) return;
    var d = {};
    for (var k in c.data) d[k] = c.data[k];
    if (!d._key) d._key = generateUUID();
    c.data._key = d._key;
    gnBridge.save_user_contact(JSON.stringify(d));
    // Visual feedback: flash the button
    var body = document.getElementById(_getAccBodyId(source, idx));
    if (body) {
        var btn = body.querySelector('.btn-save-local');
        if (btn) {
            var orig = btn.textContent;
            btn.textContent = 'Salvo!';
            btn.disabled = true;
            setTimeout(function () { btn.textContent = orig; btn.disabled = false; }, 1800);
        }
    }
}

function deleteUserContact(key) {
    Modal.confirm('Excluir este contato dos Meus Contatos?<br><br>Esta ação não pode ser desfeita.', function () {
        gnBridge.delete_user_contact(key);
        var boxes = ['search-suggestions', 'proc-suggestions', 'meta-suggestions'];
        boxes.forEach(function (id) {
            var box = document.getElementById(id);
            if (!box) return;
            box.querySelectorAll('[data-user-key="' + key + '"]').forEach(function (el) {
                el.remove();
            });
        });
    }, 'Confirmar Exclusão');
}

function renderContacts() {
    var tbody = document.getElementById("contacts-tbody");
    var accDiv = document.getElementById("contacts-accordions");
    if (!tbody) return;

    if (contacts.length === 0) {
        tbody.innerHTML = '<tr><td colspan="6" class="empty-state">Nenhum contato. Use a busca ou clique em <b>+ Manual</b>.</td></tr>';
        if (accDiv) accDiv.innerHTML = "";
    } else {
        var last = contacts.length - 1;
        tbody.innerHTML = contacts.map(function (c, idx) {
            return '<tr>' +
                '<td style="text-align:center;color:var(--fg-muted);font-weight:700;font-size:12px">' + (idx + 1) + '</td>' +
                '<td>' + (c.data.org || '-') + '</td>' +
                '<td>' + (c.data.sigla || '-') + '</td>' +
                '<td>' + (c.data.email || '-') + '</td>' +
                '<td>' + buildRoleSelect(idx, c.data.role) + '</td>' +
                '<td style="white-space:nowrap">' +
                '<button class="btn-move" onclick="moveContact(' + idx + ',-1)" data-title="Mover para cima"' + (idx === 0 ? ' disabled' : '') + '>↑</button>' +
                '<button class="btn-move" onclick="moveContact(' + idx + ', 1)" data-title="Mover para baixo"' + (idx === last ? ' disabled' : '') + '>↓</button>' +
                '<button class="btn-remove" onclick="removeContact(' + idx + ')" data-title="Remover">✕</button>' +
                '</td>' +
                '</tr>';
        }).join('');

        if (accDiv) {
            accDiv.innerHTML = contacts.map(function (c, idx) {
                return buildAccordion(c, idx);
            }).join('');
        }
    }
    _checkCdhuWarning(contacts, 'cdhu-warning-main', 2);
    initCustomSelects();
    updateFormProgress();
    _scheduleDraftSave();
}

function buildAccordion(c, idx) {
    var d = c.data;
    var label = 'Contato ' + (idx + 1) + (d.sigla ? ' - ' + d.sigla : '');
    var isEditing = !!_accEditing['main:' + idx];
    var pfx = 'acc-' + idx + '-';
    var roleSelectHtml = _buildRoleSelectHtml('main', idx, d.role);
    var bodyHtml = '<div class="form-grid">' + _buildContactFields(d, pfx, isEditing, roleSelectHtml) + '</div>' +
        _buildAccActions(c.isManual, 'main', idx, isEditing);
    return '<div class="contact-accordion">' +
        '<button class="accordion-header" onclick="toggleAccordion(' + idx + ')">' +
        '<span class="acc-arrow" id="arr-' + idx + '"><img class="acc-chevron" src="../../img/chevron_down.svg"></span>' +
        label + _sourceBadge(c) + '</button>' +
        '<div class="accordion-body" id="acc-body-' + idx + '">' + bodyHtml + '</div>' +
        '</div>';
}

function field(label, val, editable, inputId, tip, attrs) {
    var helpBtn = tip ? ' <button class="help-btn" data-tip="' + tip + '">?</button>' : '';
    var extra = attrs ? ' ' + attrs : '';
    var input = editable
        ? '<input id="' + inputId + '" type="text" value="' + escHtml(val || '') + '"' + extra + '>'
        : '<div class="readonly-field">' + escHtml(val || '-') + '</div>';
    return '<div class="form-group"><label>' + label + helpBtn + '</label>' + input + '</div>';
}

function enterAccordionEdit(source, idx) {
    var arr = _getContactArr(source);
    var c = arr[idx];
    if (!c || (c.isManual !== true && c.isManual !== 'user')) return;
    var body = document.getElementById(_getAccBodyId(source, idx));
    if (!body) return;
    var pfx = _getIdPfx(source, idx);
    var roleSelectHtml = _buildRoleSelectHtml(source, idx, c.data.role);
    body.innerHTML = '<div class="form-grid">' + _buildContactFields(c.data, pfx, true, roleSelectHtml) + '</div>' +
        _buildAccActions(c.isManual, source, idx, true);
    if (body.style.display !== 'block') body.style.display = 'block';
    initCustomSelects();
}

function saveAccordion(source, idx) {
    var arr = _getContactArr(source);
    var c = arr[idx];
    if (!c) return;
    var pfx = _getIdPfx(source, idx);
    var g = function (suf) {
        var el = document.getElementById(pfx + suf);
        return el ? el.value.trim() : '';
    };
    if (c.isManual === true || c.isManual === 'user') {
        if (_validateManualForm(pfx, 'addr-street')) return;
    }

    var roleId = source === 'main' ? 'role-acc-' + idx : 'role-' + source + '-a-' + idx;
    var roleEl = document.getElementById(roleId);

    c.data.sigla = g('sigla') || c.data.sigla;
    c.data.org = g('org') || c.data.org;
    c.data.email = g('email');
    c.data.position = g('position');
    c.data.phone = g('phone');
    c.data.addr_street = g('addr-street');
    c.data.addr_num = g('addr-num');
    c.data.addr_comp = g('addr-comp');
    c.data.addr_bairro = g('addr-bairro');
    c.data.address = _combineAddr(c.data);
    c.data.city = g('city');
    c.data.state = g('state');
    c.data.zip = g('zip');
    c.data.country = g('country') || 'Brasil';
    if (roleEl) c.data.role = roleEl.value;

    // Auto-persist if it's a user contact
    if (c.isManual === 'user' && c.data._key) {
        var snap = {}; for (var k in c.data) snap[k] = c.data[k];
        gnBridge.save_user_contact(JSON.stringify(snap));
    }

    var body = document.getElementById(_getAccBodyId(source, idx));
    if (!body) return;
    var roleSelectHtml = _buildRoleSelectHtml(source, idx, c.data.role);
    body.innerHTML = '<div class="form-grid">' + _buildContactFields(c.data, pfx, false, roleSelectHtml) + '</div>' +
        _buildAccActions(c.isManual, source, idx, false);
    initCustomSelects();

    // Update accordion header label
    var header = body.previousElementSibling;
    if (header) {
        for (var i = header.childNodes.length - 1; i >= 0; i--) {
            var n = header.childNodes[i];
            if (n.nodeType === 3 && n.textContent.trim()) {
                n.textContent = 'Contato ' + (idx + 1) + (c.data.sigla ? ' - ' + c.data.sigla : '');
                break;
            }
        }
    }

    // Update summary table cells
    var tbodyId = source === 'main' ? 'contacts-tbody' : source + '-tbody';
    var tbody = document.getElementById(tbodyId);
    if (tbody) {
        var rows = tbody.querySelectorAll('tr');
        var row = rows[idx];
        if (row) {
            var cells = row.querySelectorAll('td');
            if (cells[1]) cells[1].textContent = c.data.org || '-';
            if (cells[2]) cells[2].textContent = c.data.sigla || '-';
            if (cells[3] && source === 'main') cells[3].textContent = c.data.email || '-';
        }
    }
}

function cancelAccordion(source, idx) {
    var arr = _getContactArr(source);
    var c = arr[idx];
    if (!c) return;
    var body = document.getElementById(_getAccBodyId(source, idx));
    if (!body) return;
    var pfx = _getIdPfx(source, idx);
    var roleSelectHtml = _buildRoleSelectHtml(source, idx, c.data.role);
    body.innerHTML = '<div class="form-grid">' + _buildContactFields(c.data, pfx, false, roleSelectHtml) + '</div>' +
        _buildAccActions(c.isManual, source, idx, false);
    initCustomSelects();
}

function exportContactXml(source, idx) {
    var arr = _getContactArr(source);
    var c = arr[idx];
    if (!c) return;
    var d = c.data;
    var addr = _combineAddr(d);
    var role = d.role || 'pointOfContact';
    var roleLabel = ROLE_LABELS[role] || role;
    var x = function (v) { return escHtml(v || ''); };
    var xml = '<?xml version="1.0" encoding="UTF-8"?>\n' +
        '<gmd:CI_ResponsibleParty\n' +
        '    xmlns:gmd="http://www.isotc211.org/2005/gmd"\n' +
        '    xmlns:gco="http://www.isotc211.org/2005/gco">\n' +
        (d.sigla ? '  <gmd:individualName><gco:CharacterString>' + x(d.sigla) + '</gco:CharacterString></gmd:individualName>\n' : '') +
        (d.org ? '  <gmd:organisationName><gco:CharacterString>' + x(d.org) + '</gco:CharacterString></gmd:organisationName>\n' : '') +
        (d.position ? '  <gmd:positionName><gco:CharacterString>' + x(d.position) + '</gco:CharacterString></gmd:positionName>\n' : '') +
        '  <gmd:contactInfo><gmd:CI_Contact>\n' +
        (d.phone ? '    <gmd:phone><gmd:CI_Telephone>\n      <gmd:voice><gco:CharacterString>' + x(d.phone) + '</gco:CharacterString></gmd:voice>\n    </gmd:CI_Telephone></gmd:phone>\n' : '') +
        '    <gmd:address><gmd:CI_Address>\n' +
        (addr ? '      <gmd:deliveryPoint><gco:CharacterString>' + x(addr) + '</gco:CharacterString></gmd:deliveryPoint>\n' : '') +
        (d.city ? '      <gmd:city><gco:CharacterString>' + x(d.city) + '</gco:CharacterString></gmd:city>\n' : '') +
        (d.state ? '      <gmd:administrativeArea><gco:CharacterString>' + x(d.state) + '</gco:CharacterString></gmd:administrativeArea>\n' : '') +
        (d.zip ? '      <gmd:postalCode><gco:CharacterString>' + x(d.zip) + '</gco:CharacterString></gmd:postalCode>\n' : '') +
        (d.country ? '      <gmd:country><gco:CharacterString>' + x(d.country) + '</gco:CharacterString></gmd:country>\n' : '') +
        (d.email ? '      <gmd:electronicMailAddress><gco:CharacterString>' + x(d.email) + '</gco:CharacterString></gmd:electronicMailAddress>\n' : '') +
        '    </gmd:CI_Address></gmd:address>\n' +
        '  </gmd:CI_Contact></gmd:contactInfo>\n' +
        '  <gmd:role>\n' +
        '    <gmd:CI_RoleCode\n' +
        '        codeList="http://standards.iso.org/ittf/PubliclyAvailableStandards/ISO_19139_Schemas/resources/codelist/gmxCodelists.xml#CI_RoleCode"\n' +
        '        codeListValue="' + x(role) + '">' + x(roleLabel) + '</gmd:CI_RoleCode>\n' +
        '  </gmd:role>\n' +
        '</gmd:CI_ResponsibleParty>';
    var filename = (d.sigla || d.org || 'contato').replace(/[^a-zA-Z0-9_\-]/g, '_') + '.xml';
    gnBridge.export_contact_xml(xml, filename);
}

function toggleAccordion(idx) {
    var body = document.getElementById("acc-body-" + idx);
    var arr = document.getElementById("arr-" + idx);
    if (!body) return;
    var open = body.style.display === "block";
    if (open) {
        body.style.display = "none";
    } else {
        body.style.display = "block";
        body.classList.add('open-anim');
        setTimeout(function () { body.classList.remove('open-anim'); }, 250);
    }
    var chevron = arr ? arr.querySelector('.acc-chevron') : null;
    if (chevron) chevron.classList.toggle('open', !open);
}

function moveContact(idx, dir) {
    var newIdx = idx + dir;
    if (newIdx < 0 || newIdx >= contacts.length) return;
    var tmp = contacts[idx];
    contacts[idx] = contacts[newIdx];
    contacts[newIdx] = tmp;
    renderContacts();
}

function moveFor(key, idx, dir) {
    var arr = _sArr(key);
    var newIdx = idx + dir;
    if (newIdx < 0 || newIdx >= arr.length) return;
    var tmp = arr[idx];
    arr[idx] = arr[newIdx];
    arr[newIdx] = tmp;
    renderFor(key);
}

function removeContact(idx) {
    contacts.splice(idx, 1);
    renderContacts();
}

// ─── Busca de contatos (via bridge) ───────────────────────────────────────────

var _suggestionResults = [];
var _localResults = [];
var _gnResults = [];
var _gnLoading = { 'main': false, 'proc': false, 'meta': false };

var _GN_LOADING_ROW = '<div class="suggestion-loading"><span class="suggestion-spinner"></span>Buscando no Catálogo Online…</div>';

// ─── Verificação de aviso CDHU ────────────────────────────────────────────────
function _isCdhu(c) {
    if (!c || !c.data) return false;
    var sig = (c.data.sigla || '').toUpperCase();
    var org = (c.data.org || '').toUpperCase();
    return sig === 'CDHU' || org.indexOf('CDHU') !== -1;
}

function _checkCdhuWarning(arr, bannerId, reqPos) {
    var banner = document.getElementById(bannerId);
    if (!banner) return;
    // Only show if any contact is from a catalog (not fully manual)
    var hasCatalogContact = arr.some(function (c) { return c.isManual !== true; });

    var ok = false;
    if (bannerId === 'cdhu-warning-main') {
        // For Recurso: allowed in Pos 1 OR Pos 2
        ok = (arr.length >= 1 && _isCdhu(arr[0])) || (arr.length >= 2 && _isCdhu(arr[1]));
    } else {
        // For Meta: strictly the reqPos (usually 1)
        ok = (arr.length >= reqPos) && _isCdhu(arr[reqPos - 1]);
    }

    if (hasCatalogContact && !ok) {
        banner.style.display = 'block';
    } else {
        banner.style.display = 'none';
    }
}

function _renderContactSuggestions(q) {
    var combined = _gnResults.concat(_localResults.filter(function (r) {
        return !_gnResults.some(function (g) { return g.email && g.email === r.email; });
    }));
    _suggestionResults = combined;
    var box = document.getElementById('search-suggestions');
    if (!box) return;
    var html = '';
    if (!combined.length) {
        if (!_gnLoading['main']) {
            html = '<div class="suggestion-item" style="color:var(--fg-muted);cursor:default;">Nenhum resultado para "' + escHtml(q) + '"</div>';
        }
    } else {
        html = combined.map(function (r, i) {
            var label = '<span>' + (r.sigla ? '<b>' + escHtml(r.sigla) + '</b> - ' : '') + escHtml(r.org || r._gn_name || '?') + '</span>';
            var right;
            if (r._source === 'gn') {
                right = '<span class="sugg-badge-gn">Catálogo Online</span>';
            } else if (r._source === 'user') {
                right = '<span class="sugg-badge-user">Meus Contatos</span>' +
                    '<button class="sugg-delete-btn" data-title="Excluir contato salvo" onclick="event.stopPropagation();deleteUserContact(\'' + escHtml(r._key) + '\')">×</button>';
            } else {
                right = '<span class="sugg-badge-local">Catálogo Offline</span>';
            }
            var dataKey = r._key ? ' data-user-key="' + escHtml(r._key) + '"' : '';
            return '<div class="suggestion-item" onclick="pickSuggestion(' + i + ')"' + dataKey + '>' + label + '<span class="sugg-right">' + right + '</span></div>';
        }).join('');
    }
    if (_gnLoading['main']) html += _GN_LOADING_ROW;
    box.innerHTML = html;
    box.style.display = 'block';
}

function suggestContacts(q) {
    q = (q || '').trim();
    if (!q) { closeSuggestions(); return; }
    gnBridge.search_contacts(q, function (results) {
        _localResults = results || [];
        _renderContactSuggestions(q);
    });
    clearTimeout(_gnSearchTimer);
    if (_isLogged) {
        _gnSearchTimer = setTimeout(function () {
            _gnLoading['main'] = true;
            _renderContactSuggestions(q);
            gnBridge.search_contacts_gn('main', q);
        }, 400);
    }
}

function pickSuggestion(idx) {
    var r = _suggestionResults[idx];
    if (!r) return;
    if (_isDuplicate(contacts, r)) {
        var inp = document.getElementById('contact-search');
        if (inp) inp.value = '';
        closeSuggestions();
        return;
    }
    contacts.push({ isManual: _srcToIsManual(r._source), data: r });
    var newIdx = contacts.length - 1;
    var inp = document.getElementById('contact-search');
    if (inp) inp.value = '';
    closeSuggestions();
    renderContacts();
    if (r._source === 'gn' && r._gn_uuid) {
        gnBridge.enrich_gn_contact('main', newIdx, r._gn_uuid);
    }
}

function closeSuggestions() {
    var box = document.getElementById('search-suggestions');
    if (box) box.style.display = 'none';
    _gnLoading['main'] = false;
    _suggestionResults = [];
    _localResults = [];
    _gnResults = [];
}

// ─── Formulário manual ─────────────────────────────────────────────────────────

function toggleManualForm() {
    var wrap = document.getElementById("manual-form-wrap");
    if (!wrap) return;
    var isHidden = wrap.style.display === "none" || wrap.style.display === "";
    wrap.style.display = isHidden ? "block" : "none";
}

// ─── Seções de contato paramétricas (Qualidade / Metadado) ───────────────────

var procContacts = [];
var metaContacts = [];
var _procSugg = [];
var _metaSugg = [];
var _procGnSugg = [];
var _metaGnSugg = [];
var _gnTimers = {};

function _sArr(key) { return key === 'proc' ? procContacts : metaContacts; }
function _sSugg(key) { return key === 'proc' ? _procSugg : _metaSugg; }
function _getGnSugg(key) { return key === 'proc' ? _procGnSugg : _metaGnSugg; }
function _setSArr(key, v) { if (key === 'proc') procContacts = v; else metaContacts = v; }
function _setSugg(key, v) { if (key === 'proc') _procSugg = v; else _metaSugg = v; }
function _setSuggGn(key, v) { if (key === 'proc') _procGnSugg = v; else _metaGnSugg = v; }

function _renderForSuggestions(key, q) {
    var gnList = _getGnSugg(key);
    var combined = gnList.concat(_sSugg(key).filter(function (r) {
        return !gnList.some(function (g) { return g.email && g.email === r.email; });
    }));
    _setSugg(key, combined);
    var box = document.getElementById(key + '-suggestions');
    if (!box) return;
    var html = '';
    if (!combined.length) {
        if (!_gnLoading[key]) {
            html = '<div class="suggestion-item" style="color:var(--fg-muted);cursor:default">Nenhum resultado para "' + escHtml(q) + '"</div>';
        }
    } else {
        html = combined.map(function (r, i) {
            var label = '<span>' + (r.sigla ? '<b>' + escHtml(r.sigla) + '</b> - ' : '') + escHtml(r.org || '?') + '</span>';
            var right;
            if (r._source === 'gn') {
                right = '<span class="sugg-badge-gn">Catálogo Online</span>';
            } else if (r._source === 'user') {
                right = '<span class="sugg-badge-user">Meus Contatos</span>' +
                    '<button class="sugg-delete-btn" data-title="Excluir contato salvo" onclick="event.stopPropagation();deleteUserContact(\'' + escHtml(r._key) + '\')">×</button>';
            } else {
                right = '<span class="sugg-badge-local">Catálogo Offline</span>';
            }
            var dataKey = r._key ? ' data-user-key="' + escHtml(r._key) + '"' : '';
            return '<div class="suggestion-item" onclick="pickFor(\'' + key + '\',' + i + ')"' + dataKey + '>' + label + '<span class="sugg-right">' + right + '</span></div>';
        }).join('');
    }
    if (_gnLoading[key]) html += _GN_LOADING_ROW;
    box.innerHTML = html;
    box.style.display = 'block';
}

function suggestFor(key, q) {
    q = (q || '').trim();
    if (!q) { closeFor(key); return; }
    gnBridge.search_contacts(q, function (results) {
        _setSugg(key, results || []);
        _renderForSuggestions(key, q);
    });
    clearTimeout(_gnTimers[key]);
    if (_isLogged) {
        _gnTimers[key] = setTimeout(function () {
            _gnLoading[key] = true;
            _renderForSuggestions(key, q);
            gnBridge.search_contacts_gn(key, q);
        }, 400);
    }
}

function pickFor(key, idx) {
    var r = _sSugg(key)[idx];
    if (!r) return;
    if (_isDuplicate(_sArr(key), r)) {
        var inp = document.getElementById(key + '-search');
        if (inp) inp.value = '';
        closeFor(key);
        return;
    }
    _sArr(key).push({ isManual: _srcToIsManual(r._source), data: r });
    var newIdx = _sArr(key).length - 1;
    var inp = document.getElementById(key + '-search');
    if (inp) inp.value = '';
    closeFor(key);
    renderFor(key);
    if (r._source === 'gn' && r._gn_uuid) {
        gnBridge.enrich_gn_contact(key, newIdx, r._gn_uuid);
    }
}

function closeFor(key) {
    var box = document.getElementById(key + '-suggestions');
    if (box) box.style.display = 'none';
    _gnLoading[key] = false;
    _setSugg(key, []);
    _setSuggGn(key, []);
}

function removeFrom(key, idx) {
    _sArr(key).splice(idx, 1);
    renderFor(key);
}

function updateRoleFor(key, idx, val) {
    var arr = _sArr(key);
    if (!arr[idx]) return;
    arr[idx].data.role = val;
    var t = document.getElementById('role-' + key + '-t-' + idx);
    var a = document.getElementById('role-' + key + '-a-' + idx);

    if (t && t.value !== val) {
        t.value = val;
        t.dispatchEvent(new Event('change', { bubbles: true }));
    }
    if (a && a.value !== val) {
        a.value = val;
        a.dispatchEvent(new Event('change', { bubbles: true }));
    }
}

function renderFor(key) {
    var arr = _sArr(key);
    var tbody = document.getElementById(key + '-tbody');
    var accDiv = document.getElementById(key + '-accordions');
    if (!tbody) return;
    if (arr.length === 0) {
        tbody.innerHTML = '<tr><td colspan="5" class="empty-state">Nenhum contato adicionado. Use a busca ou clique em <b>+ Manual</b></td></tr>';
        if (accDiv) accDiv.innerHTML = '';
    } else {
        var last = arr.length - 1;
        tbody.innerHTML = arr.map(function (c, idx) {
            var sel = c.data.role || 'pointOfContact';
            var opts = ROLE_OPTIONS.map(function (r) {
                var t = r.title ? ' data-title="' + r.title + '"' : '';
                return '<option value="' + r.value + '"' + (r.value === sel ? ' selected' : '') + t + '>' + r.label + '</option>';
            }).join('');
            return '<tr>' +
                '<td style="text-align:center;color:var(--fg-muted);font-weight:700;font-size:12px">' + (idx + 1) + '</td>' +
                '<td>' + (c.data.org || '-') + '</td>' +
                '<td>' + (c.data.sigla || '-') + '</td>' +
                '<td><select id="role-' + key + '-t-' + idx + '" class="role-select" onchange="updateRoleFor(\'' + key + '\',' + idx + ',this.value)">' + opts + '</select></td>' +
                '<td style="white-space:nowrap">' +
                '<button class="btn-move" onclick="moveFor(\'' + key + '\',' + idx + ',-1)" data-title="Mover para cima"' + (idx === 0 ? ' disabled' : '') + '>↑</button>' +
                '<button class="btn-move" onclick="moveFor(\'' + key + '\',' + idx + ', 1)" data-title="Mover para baixo"' + (idx === last ? ' disabled' : '') + '>↓</button>' +
                '<button class="btn-remove" onclick="removeFrom(\'' + key + '\',' + idx + ')" data-title="Remover">✕</button>' +
                '</td>' +
                '</tr>';
        }).join('');
        if (accDiv) {
            accDiv.innerHTML = arr.map(function (c, idx) {
                return buildAccordionFor(c, idx, key);
            }).join('');
        }
    }
    if (key === 'meta') _checkCdhuWarning(arr, 'cdhu-warning-meta', 1);
    initCustomSelects();
    updateFormProgress();
    _scheduleDraftSave();
}

function buildAccordionFor(c, idx, key) {
    var d = c.data;
    var lbl = 'Contato ' + (idx + 1) + (d.sigla ? ' - ' + d.sigla : '');
    var isEditing = !!_accEditing[key + ':' + idx];
    var pfx = 'af-' + key + '-' + idx + '-';
    var roleSelectHtml = _buildRoleSelectHtml(key, idx, d.role);
    var bodyHtml = '<div class="form-grid">' + _buildContactFields(d, pfx, isEditing, roleSelectHtml) + '</div>' +
        _buildAccActions(c.isManual, key, idx, isEditing);
    return '<div class="contact-accordion">' +
        '<button class="accordion-header" onclick="toggleAccordionFor(\'' + key + '\',' + idx + ')">' +
        '<span class="acc-arrow" id="arr-' + key + '-' + idx + '"><img class="acc-chevron" src="../../img/chevron_down.svg"></span>' +
        lbl + _sourceBadge(c) + '</button>' +
        '<div class="accordion-body" id="acc-body-' + key + '-' + idx + '">' + bodyHtml + '</div>' +
        '</div>';
}

function toggleAccordionFor(key, idx) {
    var body = document.getElementById('acc-body-' + key + '-' + idx);
    var arr = document.getElementById('arr-' + key + '-' + idx);
    if (!body) return;
    var open = body.style.display === 'block';
    if (open) {
        body.style.display = 'none';
    } else {
        body.style.display = 'block';
        body.classList.add('open-anim');
        setTimeout(function () { body.classList.remove('open-anim'); }, 250);
    }
    var ch = arr ? arr.querySelector('.acc-chevron') : null;
    if (ch) ch.classList.toggle('open', !open);
}

function toggleSectionManual(key) {
    var wrap = document.getElementById(key + '-manual-wrap');
    if (!wrap) return;
    wrap.style.display = (wrap.style.display === 'none' || !wrap.style.display) ? 'block' : 'none';
}

function submitSectionManual(key) {
    var g = function (id) { var el = document.getElementById(key + '-mf-' + id); return el ? el.value.trim() : ''; };
    if (_validateManualForm(key + '-mf-', 'address')) return;
    var sigla = g('sigla'), org = g('org');
    _sArr(key).push({
        isManual: true,
        data: {
            sigla: sigla, org: org, email: g('email'), role: g('role') || 'pointOfContact',
            position: g('position'), phone: g('phone'),
            addr_street: g('address'), addr_num: g('address-num'), addr_comp: g('address-comp'),
            addr_bairro: g('addr-bairro'),
            address: [g('address'), g('address-num'), g('address-comp'), g('addr-bairro')].filter(Boolean).join(', '),
            city: g('city'), state: g('state'), zip: g('zip'),
            country: g('country') || 'Brasil'
        }
    });
    ['sigla', 'org', 'email', 'position', 'phone', 'address', 'address-num', 'address-comp', 'addr-bairro', 'city', 'zip'].forEach(function (f) {
        var el = document.getElementById(key + '-mf-' + f); if (el) el.value = '';
    });
    var stateEl = document.getElementById(key + '-mf-state'); if (stateEl) stateEl.value = '';
    var countryEl = document.getElementById(key + '-mf-country'); if (countryEl) countryEl.value = 'Brasil';
    toggleSectionManual(key);
    renderFor(key);
    setTimeout(function () { toggleAccordionFor(key, _sArr(key).length - 1); }, 50);
}

// ─── Contato de metadado: inicialização ────────────────────────────────────────

function initMetaAuthor() {
    // Começar vazio para que o progresso reflita o trabalho do usuário do zero
    if (metaContacts.length > 0) {
        renderFor('meta');
    } else {
        renderFor('meta');
    }
}

function submitManualContact() {
    var g = function (id) {
        var el = document.getElementById("mf-" + id);
        return el ? el.value.trim() : "";
    };
    if (_validateManualForm('mf-', 'address')) return;
    var sigla = g("sigla"), org = g("org");
    contacts.push({
        isManual: true,
        data: {
            sigla: sigla, org: org, email: g("email"), role: g("role"),
            position: g("position"), phone: g("phone"),
            addr_street: g("address"), addr_num: g("address-num"), addr_comp: g("address-comp"),
            addr_bairro: g("addr-bairro"),
            address: [g("address"), g("address-num"), g("address-comp"), g("addr-bairro")].filter(Boolean).join(', '),
            city: g("city"), state: g("state"), zip: g("zip"),
            country: g("country") || "Brasil"
        }
    });
    ["sigla", "org", "email", "role", "position", "phone", "address", "address-num", "address-comp", "addr-bairro", "city", "state", "zip"].forEach(function (f) {
        var el = document.getElementById("mf-" + f);
        if (el) el.value = "";
    });
    var countryEl = document.getElementById("mf-country");
    if (countryEl) countryEl.value = "Brasil";
    toggleManualForm();
    renderContacts();
    setTimeout(function () { toggleAccordion(contacts.length - 1); }, 50);
}
