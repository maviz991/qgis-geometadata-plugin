// app.js - App-shell: bootstrap, navegação entre painéis, camada ativa, login,
// tooltips/selects genéricos. Lógica do editor GeoNetwork está em geonetwork.js
// (gnBridge); lógica de publicação GeoServer está em geoserver.js (gsBridge).
var bridge;
var gnBridge, gsBridge;

// ── Mapa tipo de camada (name → 'vector'|'raster') ───────────────────────────
var _layerTypeMap = {};
var _activeLayerName = '';

var _LP_INNER_VECTOR = '<polygon points="12 2 2 7 12 12 22 7 12 2"/><polyline points="2 17 12 22 22 17"/><polyline points="2 12 12 17 22 12"/>';
var _LP_INNER_RASTER = '<rect x="3" y="3" width="18" height="18" rx="1"/><line x1="3" y1="9" x2="21" y2="9"/><line x1="3" y1="15" x2="21" y2="15"/><line x1="9" y1="3" x2="9" y2="21"/><line x1="15" y1="3" x2="15" y2="21"/>';

// ── Draft: preserva estado do formulário entre navegações e fechamento ─────────
// (o mecanismo de agendamento/gravação em si é específico do editor GN - ver
// _scheduleDraftSave/_saveDraftNow em geonetwork.js; aqui só a variável compartilhada
// entre o app-shell - que a captura antes de trocar de painel - e o editor.)
var _editorDraft = null;

document.addEventListener("DOMContentLoaded", function () {
    _initHelpTooltip();
    _initFieldValidation();
    if (typeof qt !== "undefined") {
        new QWebChannel(qt.webChannelTransport, function (channel) {
            window.bridge = channel.objects.bridge;
            window.gnBridge = channel.objects.gnBridge;
            window.gsBridge = channel.objects.gsBridge;
            initApp();
        });
    } else {
        console.warn("QWebChannel não detectado. Modo desenvolvimento local?");
    }
});

function _initHelpTooltip() {
    var tip = document.createElement('div');
    tip.id = 'help-tooltip';
    var arrow = document.createElement('div');
    arrow.id = 'help-tooltip-arrow';
    tip.appendChild(arrow);
    document.body.appendChild(tip);

    document.addEventListener('mouseover', function (e) {
        var btn = e.target.closest ? e.target.closest('.help-btn') : null;
        if (!btn) return;
        var text = btn.getAttribute('data-tip');
        if (!text) return;
        // set text without overwriting the arrow child
        tip.childNodes[0] && tip.childNodes[0].nodeType === 3
            ? (tip.childNodes[0].nodeValue = text)
            : tip.insertBefore(document.createTextNode(text), arrow);
        tip.style.display = 'block';
        _positionHelpTip(tip, btn);
    });

    document.addEventListener('mouseout', function (e) {
        var btn = e.target.closest ? e.target.closest('.help-btn') : null;
        if (!btn) return;
        tip.style.display = 'none';
    });
}

function _positionHelpTip(tip, btn) {
    var r = btn.getBoundingClientRect();
    var vw = window.innerWidth || document.documentElement.clientWidth;
    var tw = tip.offsetWidth;
    var th = tip.offsetHeight;
    var gap = 8;

    var below = false;
    var top = r.top - th - gap;
    var left = r.left + r.width / 2 - tw / 2;

    if (left < 8) left = 8;
    if (left + tw > vw - 8) left = vw - tw - 8;

    if (top < 8) {
        top = r.bottom + gap;
        below = true;
    }

    tip.style.top = top + 'px';
    tip.style.left = left + 'px';
    tip.className = below ? 'tip-below' : 'tip-above';

    var arrow = document.getElementById('help-tooltip-arrow');
    if (arrow) {
        var btnCx = r.left + r.width / 2;
        var arrowLeft = btnCx - left - 6;
        if (arrowLeft < 6) arrowLeft = 6;
        if (arrowLeft > tw - 18) arrowLeft = tw - 18;
        arrow.style.left = arrowLeft + 'px';
    }
}

// ─── Field validation & formatting ───────────────────────────────────────────

function _initFieldValidation() {
    document.addEventListener('input', function (e) {
        var el = e.target;
        var tag = el.tagName;
        var f = el.getAttribute('data-format');
        var v = el.getAttribute('data-validate');

        // Clear error as soon as the field has a value
        if (el.classList.contains('error') && el.value.trim()) _clearFieldError(el);

        // Phone: + only at position 0; digits only after; max 15 with DDI, 13 without
        if (f === 'phone') {
            var hasPlus = el.value.charAt(0) === '+';
            var phoneDigits = el.value.replace(/\D/g, '');
            var maxD = hasPlus ? 15 : 13;
            if (phoneDigits.length > maxD) phoneDigits = phoneDigits.slice(0, maxD);
            var phoneClean = hasPlus ? '+' + phoneDigits : phoneDigits;
            if (phoneClean !== el.value) el.value = phoneClean;
            return;
        }
        // CEP: only digits allowed while typing; max 8 digits
        if (f === 'cep') {
            var cepClean = el.value.replace(/\D/g, '').slice(0, 8);
            if (cepClean !== el.value) el.value = cepClean;
            return;
        }
        // Sigla: uppercase + no spaces in real time
        if (f === 'uppercase') {
            var up = el.value.replace(/\s/g, '').toUpperCase();
            if (up !== el.value) el.value = up;
            return;
        }

        // Strip < > from all other text inputs and textareas (breaks XML)
        if (tag === 'TEXTAREA' || (tag === 'INPUT' && el.type !== 'date' && el.type !== 'datetime-local' && el.type !== 'number')) {
            var stripped = el.value.replace(/[<>]/g, '');
            if (stripped !== el.value) el.value = stripped;
        }

        if (v === 'no-digits') _warnNoDigits(el);
        if (v === 'digits-only') _enforceDigitsOnly(el);
        if (v === 'letters-only') _enforceLettersOnly(el);
        if (v === 'email') _clearFieldError(el);
    });

    document.addEventListener('focusout', function (e) {
        var el = e.target;
        var f = el.getAttribute('data-format');
        var v = el.getAttribute('data-validate');
        if (f === 'phone') _validatePhone(el);
        if (f === 'cep') _validateCep(el);
        if (f === 'titlecase') { el.value = _toTitleCase(el.value); }
        if (v === 'email') _checkEmail(el);
        if (v === 'url') _checkUrl(el);
        if (v === 'no-digits') _warnNoDigits(el);
    });

    document.addEventListener('change', function (e) {
        var el = e.target;
        if (el.tagName === 'SELECT' && el.classList.contains('error') && el.value.trim()) _clearFieldError(el);
    });
}

var _PT_PREP = /^(de|da|do|das|dos|e|em|a|o|as|os|para|por|com|sem|sob|sobre|até|desde|entre|ante|após|perante|segundo|conforme|mediante|via|ao|à|às|aos|no|na|nos|nas|num|nuns|numa|numas)$/i;

function _toTitleCase(str) {
    if (!str) return str;
    return str.trim().replace(/\S+/g, function (word, offset) {
        if (offset > 0 && _PT_PREP.test(word)) return word.toLowerCase();
        return word.charAt(0).toUpperCase() + word.slice(1).toLowerCase();
    });
}

function _setFieldError(el, msg) {
    el.classList.add('error');
    var sib = el.nextElementSibling;
    if (sib && sib.classList.contains('field-err')) { sib.textContent = msg; return; }
    var span = document.createElement('span');
    span.className = 'field-err';
    span.textContent = msg;
    el.parentNode.insertBefore(span, el.nextSibling);
}

function _clearFieldError(el) {
    el.classList.remove('error');
    var sib = el.nextElementSibling;
    if (sib && sib.classList.contains('field-err')) sib.remove();
}

function _warnNoDigits(el) {
    if (!el.value) { _clearFieldError(el); return; }
    if (/\d/.test(el.value)) _setFieldError(el, 'Nome não deve conter números.');
    else _clearFieldError(el);
}

function _enforceDigitsOnly(el) {
    var clean = el.value.replace(/\D/g, '');
    if (clean !== el.value) el.value = clean;
}

function _enforceLettersOnly(el) {
    // Allow letters (incl. accented), spaces, hyphens, dots, apostrophes, commas
    var clean = el.value.replace(/[^a-zA-ZÀ-ÿ\s\-\.',]/g, '');
    if (clean !== el.value) el.value = clean;
}

function _checkEmail(el) {
    var v = (el.value || '').trim();
    if (!v) { _clearFieldError(el); return; }
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v))
        _setFieldError(el, 'E-mail inválido (ex: nome@dominio.com.br).');
    else _clearFieldError(el);
}

function _checkUrl(el) {
    var v = (el.value || '').trim();
    if (!v) { _clearFieldError(el); return; }
    if (!/^https?:\/\/.+/.test(v))
        _setFieldError(el, 'URL deve começar com http:// ou https://');
    else _clearFieldError(el);
}

function _validatePhone(el) {
    var raw = (el.value || '').trim();
    if (!raw) { el.value = ''; _clearFieldError(el); return; }

    // Explicit DDI: user typed + at start - accept any international format
    if (raw.charAt(0) === '+') {
        var intlDigits = raw.slice(1).replace(/\D/g, '');
        if (intlDigits.length < 7) {
            _setFieldError(el, 'Número internacional incompleto (mín. 7 dígitos após o +).');
            return;
        }
        el.value = '+' + intlDigits;
        _clearFieldError(el);
        return;
    }

    // No DDI typed: default to Brazil (+55)
    var digits = raw.replace(/\D/g, '');
    if (!digits) { el.value = ''; _clearFieldError(el); return; }
    if (digits.length < 8) {
        _setFieldError(el, 'Telefone incompleto (mínimo 8 dígitos).');
        return;
    }
    if (digits.length === 8) {
        _setFieldError(el, 'DDD não informado. Ex: +55 11 ' + digits.slice(0, 4) + '-' + digits.slice(4));
        return;
    }
    if (digits.length === 9) {
        _setFieldError(el, 'DDD não informado. Ex: +55 11 ' + digits.slice(0, 5) + '-' + digits.slice(5));
        return;
    }
    var formatted = _fmtPhone(digits);
    if (!formatted) {
        _setFieldError(el, 'Telefone inválido. Use: +55 11 XXXX-XXXX');
        return;
    }
    el.value = formatted;
    _clearFieldError(el);
}

// Receives only digit string; returns formatted string or null if unrecognised.
function _fmtPhone(digits) {
    var ddd, num;
    if (digits.length === 10) {
        ddd = digits.slice(0, 2); num = digits.slice(2);
        return '+55 ' + ddd + ' ' + num.slice(0, 4) + '-' + num.slice(4);
    }
    if (digits.length === 11) {
        ddd = digits.slice(0, 2); num = digits.slice(2);
        return '+55 ' + ddd + ' ' + num.slice(0, 5) + '-' + num.slice(5);
    }
    if (digits.length === 12 && digits.startsWith('55')) {
        ddd = digits.slice(2, 4); num = digits.slice(4);
        return '+55 ' + ddd + ' ' + num.slice(0, 4) + '-' + num.slice(4);
    }
    if (digits.length === 13 && digits.startsWith('55')) {
        ddd = digits.slice(2, 4); num = digits.slice(4);
        return '+55 ' + ddd + ' ' + num.slice(0, 5) + '-' + num.slice(5);
    }
    return null;
}

function _validateCep(el) {
    var val = (el.value || '').trim();
    if (!val) { _clearFieldError(el); return; }
    var digits = val.replace(/\D/g, '');
    if (digits.length !== 8) {
        _setFieldError(el, 'CEP inválido. Informe 8 dígitos (ex: 01310-100).');
        return;
    }
    el.value = digits.slice(0, 5) + '-' + digits.slice(5);
    _clearFieldError(el);
}

var CDA_URL = "https://cda.cdhu.sp.gov.br"; // fallback só até bridge.get_initial_data() responder

function initApp() {
    bridge.get_initial_data(function (data) {
        if (data) updateUserUI(data.is_logged, data.user);
        if (data && data.cda_url) {
            CDA_URL = data.cda_url;
            var cdaLink = document.getElementById('cda-link');
            if (cdaLink) cdaLink.href = CDA_URL;
        }
        navigate("home");
    });

    bridge.get_active_layer_name(function (name) {
        updateLayerBadge(name);
    });

    bridge.nav_changed.connect(function (panelId) {
        loadPanel(panelId);
    });

    bridge.toast.connect(function (message, title, type) {
        Modal.alert(message, title, type);
    });

    bridge.auth_status.connect(function (isLogged, username) {
        updateUserUI(isLogged, username);
    });

    bridge.form_data_req.connect(function (data) {
        populateForm(data);
    });

    bridge.layer_changed.connect(function (name) {
        updateLayerBadge(name, _layerTypeMap[name]);
        _editorDraft = null;
        if (typeof _onActiveLayerChanged === 'function') _onActiveLayerChanged(name);
        if (typeof _onGsActiveLayerChanged === 'function') _onGsActiveLayerChanged(name);
    });

    if (typeof _initGnBridge === 'function') _initGnBridge();
    if (typeof _initGsBridge === 'function') _initGsBridge();
}

function updateLayerBadge(name, type) {
    var badge = document.getElementById('layer-badge');
    var nameEl = document.getElementById('layer-badge-name');
    var iconEl = document.getElementById('layer-badge-icon');
    if (!badge || !nameEl) return;
    if (name) {
        _activeLayerName = name;
        nameEl.textContent = name.length > 16 ? name.slice(0, 16) + '…' : name;
        badge.style.display = 'flex';
        if (iconEl) {
            var t = type || _layerTypeMap[name] || 'vector';
            iconEl.innerHTML = (t === 'raster') ? _LP_INNER_RASTER : _LP_INNER_VECTOR;
        }
    } else {
        badge.style.display = 'none';
        closeLayerPicker();
    }
}

// ── Layer picker dropdown ─────────────────────────────────────────────────────

function toggleLayerPicker(e) {
    e.stopPropagation();
    var dropdown = document.getElementById('layer-picker-dropdown');
    if (!dropdown) return;
    if (dropdown.style.display === 'none') {
        openLayerPicker();
    } else {
        closeLayerPicker();
    }
}

function openLayerPicker() {
    var dropdown = document.getElementById('layer-picker-dropdown');
    var badge = document.getElementById('layer-badge');
    if (!dropdown || typeof bridge === 'undefined') return;

    dropdown.innerHTML = '<div class="lp-empty">Carregando...</div>';
    dropdown.style.display = 'block';
    badge.classList.add('open');

    bridge.list_layers(function (layers) {
        if (!layers || !layers.length) {
            dropdown.innerHTML = '<div class="lp-empty">Nenhuma camada no projeto.</div>';
            return;
        }
        // Popula mapa de tipos para uso no badge e no signal layer_changed
        (layers || []).forEach(function (l) { _layerTypeMap[l.name] = l.type; });

        var activeName = _activeLayerName;
        var mkIcon = function (type) {
            return '<svg class="lp-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
                (type === 'raster' ? _LP_INNER_RASTER : _LP_INNER_VECTOR) + '</svg>';
        };
        dropdown.innerHTML = layers.map(function (l) {
            var isActive = l.name === activeName;
            return '<div class="lp-item' + (isActive ? ' active' : '') + '" ' +
                'data-lid="' + escHtml(l.id) + '" data-lname="' + escHtml(l.name) + '" data-ltype="' + l.type + '" ' +
                'onclick="selectLayer(this.dataset.lid, this.dataset.lname, this.dataset.ltype)">' +
                mkIcon(l.type) + escHtml(l.name) + '</div>';
        }).join('');
    });
}

function closeLayerPicker() {
    var dropdown = document.getElementById('layer-picker-dropdown');
    var badge = document.getElementById('layer-badge');
    if (dropdown) dropdown.style.display = 'none';
    if (badge) badge.classList.remove('open');
}

function selectLayer(layerId, layerName, layerType) {
    closeLayerPicker();
    if (typeof bridge === 'undefined') return;
    bridge.set_active_layer(layerId);
    if (layerType) _layerTypeMap[layerName] = layerType;
    updateLayerBadge(layerName, layerType);
}

// Fecha o picker ao clicar fora
document.addEventListener('click', function (e) {
    var wrap = document.querySelector('.layer-picker-wrap');
    if (wrap && !wrap.contains(e.target)) closeLayerPicker();
});

// ─── Navegação ────────────────────────────────────────────────────────────────

function navigate(panelId) {
    // 1. Executa os hooks de saída ANTES de trocar o DOM - collectFormData() e
    //    _saveGsDraftNow() ainda encontram os campos do painel atual aqui.
    if (typeof _onBeforePanelUnload === 'function') _onBeforePanelUnload();
    if (typeof _onGsBeforePanelUnload === 'function') _onGsBeforePanelUnload();
    // 2. Mostra o spinner IMEDIATAMENTE (antes do round-trip Python) para
    //    eliminar o freeze entre o clique no menu e o nav_changed chegar.
    var container = document.getElementById('app-container');
    if (container) _showPanelLoading(container);
    // 3. Chama o Python; nav_changed dispara loadPanel quando estiver pronto.
    bridge.navigate(panelId);
}

function loadPanel(panelId) {
    // Os hooks de saída já foram chamados em navigate() se a navegação veio de
    // lá (DOM já substituído pelo spinner, então getElementById retorna null e
    // eles viram no-op). Ficam aqui como proteção para chamadas diretas via
    // nav_changed sem passar por navigate() (ex.: Python navega programaticamente).
    if (typeof _onBeforePanelUnload === 'function') _onBeforePanelUnload();
    if (typeof _onGsBeforePanelUnload === 'function') _onGsBeforePanelUnload();
    var container = document.getElementById('app-container');
    // Garante o spinner mesmo quando loadPanel é chamado sem navigate() antes.
    _showPanelLoading(container);

    bridge.load_panel_html(panelId, function (html) {
        container.innerHTML = html;
        onPanelLoaded(panelId);
    });
}

// Insere o overlay de carregamento com spinner circular (mesmo visual do
// _SpinnerWidget Qt em gateway_login_dialog.py) no container do painel.
function _showPanelLoading(container) {
    container.innerHTML =
        '<div class="panel-loading-overlay">' +
        '<div class="panel-loading-spinner"></div>' +
        '<span class="panel-loading-msg">Carregando...</span>' +
        '</div>';
}

function onPanelLoaded(panelId) {
    if (panelId === "login") {
        if (typeof bridge !== 'undefined') {
            bridge.login_loading.connect(function (msg) { setLoginState(true, msg); });
            bridge.login_error.connect(function (msg) { setLoginError(msg); });
        }
        return;
    }
    if (panelId === "editor" && typeof _onEditorPanelLoaded === 'function') {
        _onEditorPanelLoaded();
    }
    if (panelId === "geoserver" && typeof _onGeoServerPanelLoaded === 'function') {
        _onGeoServerPanelLoaded();
    }
}

function showTab(tabId, btn) {
    document.querySelectorAll(".tab-content").forEach(function (el) {
        el.classList.remove("active");
    });
    document.querySelectorAll(".tab-link").forEach(function (el) {
        el.classList.remove("active");
    });
    var panel = document.getElementById("tab-" + tabId);
    if (panel) panel.classList.add("active");
    if (btn) btn.classList.add("active");
}

// ─── Badge de usuário ─────────────────────────────────────────────────────────

var _isLogged = false;

function updateUserUI(isLogged, username) {
    var wasLogged = _isLogged;
    _isLogged = !!isLogged;
    var btn = document.getElementById("login-btn");
    var badge = document.getElementById("user-info");
    if (!btn || !badge) return;

    if (isLogged) {
        btn.style.display = "none";
        badge.style.display = "flex";
        badge.querySelector(".user-name").innerText = username;
        // Se o painel de login estiver aberto, voltar para home
        var container = document.getElementById("app-container");
        if (container && container.querySelector('.login-page')) {
            navigate('home');
        }
    } else {
        btn.style.display = "block";
        badge.style.display = "none";
    }

    // Login/logout muda o NÍVEL (sys_/db_) de qualquer badge de sincronização já
    // calculado (GN e GS) - sem esse gancho, o usuário loga e continua vendo "Sincronizado
    // (DB)" até sair e voltar (revisitar) pro painel, porque nada mais recalcula o badge
    // nesse meio tempo. Só dispara se o estado mudou de verdade (evita rechecagem à toa
    // em eventuais auth_status redundantes).
    if (wasLogged !== _isLogged && typeof _onAuthStateChangedForSync === 'function') {
        _onAuthStateChangedForSync();
    }
}

// ─── Utilitário ───────────────────────────────────────────────────────────────

function updateCustomSelect(select) {
    if (!select || !select.classList.contains('custom-select-initialized')) return;
    var wrapper = select.nextElementSibling;
    if (wrapper && wrapper.classList.contains('custom-select')) {
        var opt = select.options[select.selectedIndex];
        if (opt) {
            var valueSpan = wrapper.querySelector('.custom-select-value');
            if (valueSpan) valueSpan.textContent = opt.text;
            var items = wrapper.querySelectorAll('.suggestion-item');
            items.forEach(function (i) { i.classList.remove('active'); });
            var activeItem = wrapper.querySelector('.suggestion-item[data-value="' + opt.value.replace(/"/g, '\\"') + '"]');
            if (activeItem) activeItem.classList.add('active');
        }
    }
}

function escHtml(s) {
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

// Indicador de carregamento central genérico (usado por qualquer operação de rede
// demorada - publicação/salvamento no GN, publicação no GS etc.). Timeout de segurança
// de 20s evita que fique preso na tela caso o sinal de conclusão nunca chegue.
var _actionLoadingTimer = null;

function _showActionLoading(message) {
    var el = document.getElementById('action-loading');
    if (!el) {
        el = document.createElement('div');
        el.id = 'action-loading';
        el.className = 'action-loading';
        el.innerHTML = '<span class="suggestion-spinner"></span><span id="action-loading-text"></span>';
        document.body.appendChild(el);
    }
    document.getElementById('action-loading-text').textContent = message;
    el.style.display = 'flex';
    clearTimeout(_actionLoadingTimer);
    _actionLoadingTimer = setTimeout(_hideActionLoading, 20000);
}

function _hideActionLoading() {
    clearTimeout(_actionLoadingTimer);
    var el = document.getElementById('action-loading');
    if (el) el.style.display = 'none';
}

// "Arquivo > Continuar Depois" (main.html) - um item de menu só, mas o que ele faz
// depende de qual painel está aberto: editor de metadados (GN) ou publicação de camadas
// (GS). Dispatcher genérico aqui em app.js pra não acoplar o menu a um domínio só -
// delega pras implementações reais (_tryGnSaveMetadata em geonetwork.js,
// saveGsDraftNow em geoserver.js), detectando o painel pelos mesmos marcadores de DOM
// já usados em outros lugares (_requireEditorOpen usa #f-title; geoserver.js usa
// #gs-layer-card).
function trySaveMetadata() {
    if (document.getElementById('f-title') && typeof _tryGnSaveMetadata === 'function') {
        _tryGnSaveMetadata();
        return;
    }
    if (document.getElementById('gs-layer-card') && typeof saveGsDraftNow === 'function') {
        saveGsDraftNow();
        return;
    }
    Modal.alert('Abra "Catálogo > Editor de Metadados" ou "Serviços > Publicar Camada" antes de "Continuar Depois".', 'Ação Necessária', 'warning');
}

// "Arquivo > Descartar Alterações" (main.html) - mesmo dispatcher genérico de
// trySaveMetadata() acima: sem isso, o item chamava direto uma função só do GN
// (tryResetForm em geonetwork.js), então no painel GeoServer ele só mostrava "abra o
// editor de metadados" em vez de descartar as alterações da aba Destino/Identificação.
function tryResetForm() {
    if (document.getElementById('f-title') && typeof _tryGnResetForm === 'function') {
        _tryGnResetForm();
        return;
    }
    if (document.getElementById('gs-layer-card') && typeof tryGsResetForm === 'function') {
        tryGsResetForm();
        return;
    }
    Modal.alert('Abra "Catálogo > Editor de Metadados" ou "Serviços > Configurar Camada" antes de descartar alterações.', 'Ação Necessária', 'warning');
}

function generateUUID() {
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function (c) {
        var r = Math.random() * 16 | 0;
        return (c === 'x' ? r : (r & 0x3 | 0x8)).toString(16);
    });
}

// ─── Logout ────────────────────────────────────────────────────────────────────

function doLogout() {
    Modal.confirm('Deseja realmente sair da conta?', function () {
        if (typeof bridge !== 'undefined' && bridge.logout) {
            bridge.logout();
        }
    }, 'Sair');
}

// ─── Login ─────────────────────────────────────────────────────────────────────

function toggleLoginMode() {
    var corpWrap = document.getElementById('login-corp-wrap');
    var adminWrap = document.getElementById('login-admin-wrap');
    var btn = document.getElementById('login-toggle-btn');
    if (!corpWrap || !adminWrap) return;
    var showingCorp = corpWrap.style.display !== 'none';
    corpWrap.style.display = showingCorp ? 'none' : '';
    adminWrap.style.display = showingCorp ? '' : 'none';
    if (btn) btn.textContent = showingCorp ? 'ACESSO GERAL' : 'ACESSO CORPORATIVO';
}

function doAdminLogin() {
    var userEl = document.getElementById('admin-user');
    var passEl = document.getElementById('admin-pass');
    var user = userEl ? userEl.value.trim() : '';
    var pass = passEl ? passEl.value : '';
    if (!user || !pass) { Modal.alert('Informe usuário e senha.', 'Login', 'warning'); return; }
    if (typeof bridge !== 'undefined' && bridge.do_admin_login) {
        setLoginState(true, 'Verificando credenciais...');
        bridge.do_admin_login(user, pass);
    }
}

function _activeLoginSuffix() {
    var adminWrap = document.getElementById('login-admin-wrap');
    return (adminWrap && adminWrap.style.display !== 'none') ? '-adm' : '';
}

function showLoginLoading() {
    var area = document.getElementById('login-loading-area' + _activeLoginSuffix());
    if (area) area.style.display = 'flex';
}

function hideLoginLoading() {
    ['', '-adm'].forEach(function (suf) {
        var area = document.getElementById('login-loading-area' + suf);
        if (area) area.style.display = 'none';
    });
}

function setLoginState(loading) {
    if (loading) { showLoginLoading(); } else { hideLoginLoading(); }
    if (!loading) {
        ['login-error-msg', 'login-error-msg-adm'].forEach(function (id) {
            var el = document.getElementById(id);
            if (el) el.style.display = 'none';
        });
    }
}

function setLoginError(msg) {
    hideLoginLoading();
    var errEl = document.getElementById('login-error-msg' + _activeLoginSuffix());
    if (errEl) { errEl.textContent = msg; errEl.style.display = 'block'; }
    else { Modal.alert(msg, 'Erro de Login', 'error'); }
}

/* Custom Selects and Global Tooltips */


// --- Global Tooltip Logic ---
var _globalTooltip = null;
var _tooltipTimeout = null;

function initGlobalTooltips() {
    if (!_globalTooltip) {
        _globalTooltip = document.createElement('div');
        _globalTooltip.className = 'global-tooltip';
        document.body.appendChild(_globalTooltip);
    }

    document.addEventListener('mouseover', function (e) {
        var target = e.target.closest('[data-title]');
        if (!target) return;

        var tipText = target.getAttribute('data-title');
        if (!tipText) return;

        // Skip só o próprio campo (input/select/textarea) quando o form-group já tem um
        // botão "?" de ajuda - evita tooltip duplicado nele. Nunca pula itens dentro de
        // um dropdown (não têm "?") nem outros elementos com data-title próprio no mesmo
        // form-group, como um botão de ação ao lado do campo.
        var inDropdown = target.closest('.custom-select-dropdown');
        var isFieldEl = target.tagName === 'INPUT' || target.tagName === 'SELECT' || target.tagName === 'TEXTAREA';
        if (!inDropdown && isFieldEl) {
            var formGroup = target.closest('.form-group');
            if (formGroup && formGroup.querySelector('.help-btn')) return;
        }

        clearTimeout(_tooltipTimeout);

        _tooltipTimeout = setTimeout(function () {
            _globalTooltip.textContent = tipText;
            _globalTooltip.classList.add('visible');

            void _globalTooltip.offsetWidth;

            var rect = target.getBoundingClientRect();
            var tooltipRect = _globalTooltip.getBoundingClientRect();
            var top, left;

            // Dropdown items: show tooltip above the item (flip below if no space)
            if (inDropdown) {
                left = rect.left + rect.width / 2 - tooltipRect.width / 2;
                if (left < 10) left = 10;
                if (left + tooltipRect.width > window.innerWidth - 10)
                    left = window.innerWidth - tooltipRect.width - 10;
                top = rect.top - tooltipRect.height - 8;
                var arrowPos = (rect.left + rect.width / 2) - left;
                if (arrowPos < 10) arrowPos = 10;
                if (arrowPos > tooltipRect.width - 10) arrowPos = tooltipRect.width - 10;
                var arrowCls = 'arrow-down';
                if (top < 10) {
                    top = rect.bottom + 8;
                    arrowCls = 'arrow-up';
                }
                _globalTooltip.style.top = top + 'px';
                _globalTooltip.style.left = left + 'px';
                _globalTooltip.setAttribute('data-arrow', arrowCls);
                _globalTooltip.style.setProperty('--arrow-pos', arrowPos + 'px');
                return;
            }

            // Default: below the element (auto-flip to above if needed)
            top = rect.bottom + 8;
            left = rect.left + rect.width / 2 - tooltipRect.width / 2;
            var arrowClass = 'arrow-up';

            if (left < 10) left = 10;
            if (left + tooltipRect.width > window.innerWidth - 10)
                left = window.innerWidth - tooltipRect.width - 10;

            if (top + tooltipRect.height > window.innerHeight - 10) {
                top = rect.top - tooltipRect.height - 8;
                arrowClass = 'arrow-down';
            }

            _globalTooltip.style.top = top + 'px';
            _globalTooltip.style.left = left + 'px';
            _globalTooltip.setAttribute('data-arrow', arrowClass);

            var arrowLeft = (rect.left + rect.width / 2) - left;
            if (arrowLeft < 10) arrowLeft = 10;
            if (arrowLeft > tooltipRect.width - 10) arrowLeft = tooltipRect.width - 10;
            _globalTooltip.style.setProperty('--arrow-pos', arrowLeft + 'px');

        }, 600);
    });

    document.addEventListener('mouseout', function (e) {
        var target = e.target.closest('[data-title]');
        if (target) {
            clearTimeout(_tooltipTimeout);
            _globalTooltip.classList.remove('visible');
        }
    });

    document.addEventListener('mousedown', function () {
        clearTimeout(_tooltipTimeout);
        if (_globalTooltip) _globalTooltip.classList.remove('visible');
    });
}
// --- Custom Select Logic ---
function initCustomSelects() {
    var selects = document.querySelectorAll('select:not(.custom-select-initialized)');

    selects.forEach(function (select) {
        // Only convert selects that are inside the main form panels (skip any hidden system ones if they exist)
        if (select.style.display === 'none') return;

        select.classList.add('custom-select-initialized');
        select.style.display = 'none'; // Hide native select

        var wrapper = document.createElement('div');
        wrapper.className = 'custom-select search-wrap';
        wrapper.tabIndex = 0; // Make focusable for keyboard

        var trigger = document.createElement('div');
        trigger.className = 'custom-select-trigger';

        var valueSpan = document.createElement('span');
        valueSpan.className = 'custom-select-value';

        var arrowSpan = document.createElement('span');
        arrowSpan.className = 'custom-select-arrow';

        trigger.appendChild(valueSpan);
        trigger.appendChild(arrowSpan);
        wrapper.appendChild(trigger);

        var dropdown = document.createElement('div');
        dropdown.className = 'search-suggestions custom-select-dropdown';

        // Campo de busca (filtro ao vivo) - só faz sentido em listas compridas
        // (workspaces, estilos existentes, que podem ter dezenas de itens); num select de
        // poucas opções fixas (ex.: "Estilo principal", 4 itens) só ocupa espaço à toa.
        // SEARCH_THRESHOLD decide isso pelo Nº de opções, não por select específico - se
        // um select curto crescer (ou um comprido encolher) o comportamento se ajusta
        // sozinho, sem precisar marcar cada `<select>` manualmente.
        var SEARCH_THRESHOLD = 6;
        var needsSearch = select.options.length > SEARCH_THRESHOLD;

        // Mesmo espírito da busca de contatos do editor GN, só embutido no dropdown em
        // vez de um modal separado. Substitui, pras listas compridas, o antigo "digitar
        // pra pular pro item" (só saltava pro primeiro que COMEÇAVA com o texto, sem
        // filtrar a lista) - esse "type to jump" simples continua valendo pros selects
        // curtos (ver o keydown do wrapper mais abaixo).
        var searchInput = null;
        if (needsSearch) {
            searchInput = document.createElement('input');
            searchInput.type = 'text';
            searchInput.className = 'custom-select-search';
            searchInput.placeholder = 'Buscar...';
            searchInput.autocomplete = 'off';
            dropdown.appendChild(searchInput);
        }

        var itemsWrap = document.createElement('div');
        itemsWrap.className = 'custom-select-items';
        dropdown.appendChild(itemsWrap);

        // Populate options
        var optionsHtml = '';
        var selectedText = '- Selecione -';

        Array.from(select.options).forEach(function (opt, idx) {
            var title = opt.getAttribute('data-title') || '';
            var titleAttr = title ? ' data-title="' + title.replace(/"/g, '&quot;') + '"' : '';
            var activeClass = opt.selected ? ' active' : '';
            if (opt.selected) selectedText = opt.text;

            optionsHtml += '<div class="suggestion-item' + activeClass + '" data-index="' + idx + '" data-value="' + opt.value + '"' + titleAttr + '>' + opt.text + '</div>';
        });

        valueSpan.textContent = selectedText;
        itemsWrap.innerHTML = optionsHtml;
        wrapper.appendChild(dropdown);

        select.parentNode.insertBefore(wrapper, select.nextSibling);

        // --- Interaction Logic ---
        var isOpen = false;

        function closeDropdown() {
            dropdown.style.display = 'none';
            wrapper.classList.remove('open');
            isOpen = false;
        }

        // Itens realmente navegáveis (visíveis pelo filtro atual, sem contar a linha de
        // "Nenhum resultado").
        function _visibleItems() {
            return Array.from(itemsWrap.querySelectorAll('.suggestion-item:not(.custom-select-empty)'))
                .filter(function (el) { return el.style.display !== 'none'; });
        }

        // Filtra os itens por substring (case-insensitive, em qualquer posição do texto -
        // não só prefixo) e mostra/esconde a mensagem de "Nenhum resultado" conforme sobra
        // ou não algum item visível.
        function _filterItems(query) {
            var q = (query || '').trim().toLowerCase();
            var anyVisible = false;
            itemsWrap.querySelectorAll('.suggestion-item:not(.custom-select-empty)').forEach(function (el) {
                var match = !q || el.textContent.trim().toLowerCase().indexOf(q) !== -1;
                el.style.display = match ? '' : 'none';
                if (match) anyVisible = true;
            });
            var emptyMsg = itemsWrap.querySelector('.custom-select-empty');
            if (!anyVisible) {
                if (!emptyMsg) {
                    emptyMsg = document.createElement('div');
                    emptyMsg.className = 'suggestion-item custom-select-empty';
                    emptyMsg.style.cursor = 'default';
                    emptyMsg.style.color = 'var(--fg-muted)';
                    emptyMsg.textContent = 'Nenhum resultado.';
                    itemsWrap.appendChild(emptyMsg);
                }
            } else if (emptyMsg) {
                emptyMsg.remove();
            }
        }

        function openDropdown() {
            // Close others
            document.querySelectorAll('.custom-select.open').forEach(function (el) {
                if (el !== wrapper) {
                    el.querySelector('.custom-select-dropdown').style.display = 'none';
                    el.classList.remove('open');
                }
            });
            dropdown.style.display = 'flex'; // não 'block' - .custom-select-dropdown é column flex (ver CSS)
            wrapper.classList.add('open');
            isOpen = true;
            if (searchInput) {
                searchInput.value = '';
                _filterItems('');
                // setTimeout - o dropdown acabou de virar display:flex nesta mesma chamada;
                // sem adiar um tick, o foco não "pega" de forma confiável em todo navegador.
                setTimeout(function () { searchInput.focus(); }, 0);
            }

            // Scroll to active item
            var activeItem = itemsWrap.querySelector('.suggestion-item.active');
            if (activeItem) {
                activeItem.scrollIntoView({ block: 'nearest' });
            }
        }

        trigger.addEventListener('click', function (e) {
            e.stopPropagation();
            if (isOpen) closeDropdown();
            else openDropdown();
        });

        // Click on items
        dropdown.addEventListener('click', function (e) {
            e.stopPropagation();
            var item = e.target.closest('.suggestion-item');
            if (!item || item.classList.contains('custom-select-empty')) return;

            var idx = item.getAttribute('data-index');
            select.selectedIndex = idx;
            valueSpan.textContent = item.textContent;

            // Update active class
            itemsWrap.querySelectorAll('.suggestion-item').forEach(function (el) { el.classList.remove('active'); });
            item.classList.add('active');

            closeDropdown();

            // Trigger native change event so other scripts know
            var event = new Event('change', { bubbles: true });
            select.dispatchEvent(event);
        });

        // Click outside closes
        document.addEventListener('click', function (e) {
            if (isOpen && !wrapper.contains(e.target)) {
                closeDropdown();
            }
        });

        if (searchInput) {
            searchInput.addEventListener('input', function () {
                _filterItems(searchInput.value);
            });

            // Navegação por teclado DENTRO do campo de busca (dropdown já aberto, foco
            // nele). stopPropagation só nas teclas tratadas AQUI (Escape/setas/Enter) -
            // Tab passa direto (sem stopPropagation nem preventDefault) pro handler do
            // wrapper (abaixo), que fecha o dropdown e deixa o navegador avançar o foco
            // normalmente. Engolir Tab aqui também deixava o dropdown aberto e o foco
            // pulava pro próximo elemento focável da PÁGINA inteira (não do formulário),
            // em vez do próximo campo lógico.
            searchInput.addEventListener('keydown', function (e) {
                if (e.key === 'Escape') {
                    e.stopPropagation();
                    closeDropdown();
                    wrapper.focus();
                    return;
                }
                if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
                    e.stopPropagation();
                    e.preventDefault();
                    var items = _visibleItems();
                    if (!items.length) return;
                    var activeIdx = items.findIndex(function (item) { return item.classList.contains('active'); });
                    var nextIdx;
                    if (e.key === 'ArrowDown') nextIdx = activeIdx + 1 < items.length ? activeIdx + 1 : items.length - 1;
                    else nextIdx = activeIdx - 1 >= 0 ? activeIdx - 1 : 0;
                    if (activeIdx >= 0) items[activeIdx].classList.remove('active');
                    items[nextIdx].classList.add('active');
                    items[nextIdx].scrollIntoView({ block: 'nearest' });
                    return;
                }
                if (e.key === 'Enter') {
                    e.stopPropagation();
                    e.preventDefault();
                    var active = itemsWrap.querySelector('.suggestion-item.active');
                    if (active && active.style.display !== 'none' && !active.classList.contains('custom-select-empty')) {
                        active.click();
                    }
                }
            });
        }

        // Teclado no wrapper (trigger fechado) - abre o dropdown. Com campo de busca
        // (lista comprida), a digitação em si (uma vez aberto) é tratada pelo listener do
        // campo acima, que já tem o foco. Sem campo de busca (lista curta, ~4 itens fixos
        // tipo "Estilo principal"), mantém o comportamento antigo de "digitar pra pular
        // pro item que começa com o texto" (searchString com reset por timeout).
        var jumpSearchString = '';
        var jumpSearchTimeout = null;
        wrapper.addEventListener('keydown', function (e) {
            if (e.key === 'Tab') {
                closeDropdown();
                return;
            }
            if (isOpen) return;
            if (e.key === 'ArrowDown' || e.key === 'ArrowUp' || e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                openDropdown();
            } else if (e.key.length === 1) {
                e.preventDefault();
                openDropdown();
                if (searchInput) {
                    searchInput.value = e.key;
                    _filterItems(e.key);
                } else {
                    jumpSearchString += e.key.toLowerCase();
                    clearTimeout(jumpSearchTimeout);
                    jumpSearchTimeout = setTimeout(function () { jumpSearchString = ''; }, 1000);
                    var items = _visibleItems();
                    var matchIdx = items.findIndex(function (item) {
                        return item.textContent.trim().toLowerCase().startsWith(jumpSearchString);
                    });
                    if (matchIdx >= 0) {
                        items.forEach(function (el) { el.classList.remove('active'); });
                        items[matchIdx].classList.add('active');
                        items[matchIdx].scrollIntoView({ block: 'nearest' });
                    }
                }
            }
        });

        // Listen for programmatic value changes on the original select
        select.addEventListener('change', function () {
            var selectedOpt = select.options[select.selectedIndex];
            if (selectedOpt) {
                valueSpan.textContent = selectedOpt.text;
                itemsWrap.querySelectorAll('.suggestion-item').forEach(function (el) {
                    el.classList.toggle('active', el.getAttribute('data-value') === selectedOpt.value);
                });
            }
        });
    });
}

document.addEventListener('DOMContentLoaded', function () {
    initGlobalTooltips();
});
