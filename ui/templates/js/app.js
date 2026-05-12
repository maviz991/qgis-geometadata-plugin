// app.js - Lógica principal do GeoMetadata HTML
var bridge;

// ── Mapa tipo de camada (name → 'vector'|'raster') ───────────────────────────
var _layerTypeMap = {};
var _activeLayerName = '';

var _LP_INNER_VECTOR = '<polygon points="12 2 2 7 12 12 22 7 12 2"/><polyline points="2 17 12 22 22 17"/><polyline points="2 12 12 17 22 12"/>';
var _LP_INNER_RASTER = '<rect x="3" y="3" width="18" height="18" rx="1"/><line x1="3" y1="9" x2="21" y2="9"/><line x1="3" y1="15" x2="21" y2="15"/><line x1="9" y1="3" x2="9" y2="21"/><line x1="15" y1="3" x2="15" y2="21"/>';

// ── Draft: preserva estado do formulário entre navegações e fechamento ─────────
var _editorDraft = null;
var _draftTimer = null;

function _scheduleDraftSave() {
    clearTimeout(_draftTimer);
    _draftTimer = setTimeout(function () {
        var d = collectFormData();
        if (!d || typeof bridge === 'undefined') return;
        // Não sobrescreve o arquivo com formulário vazio
        var hasContent = d.title || (d.contacts && d.contacts.length > 0) ||
            (d.MD_Keywords && d.MD_Keywords.length > 0) || d.abstract;
        if (!hasContent) return;
        _editorDraft = d;
        bridge.save_draft(JSON.stringify(d));
    }, 1500);
}

document.addEventListener("DOMContentLoaded", function () {
    _initHelpTooltip();
    _initFieldValidation();
    if (typeof qt !== "undefined") {
        new QWebChannel(qt.webChannelTransport, function (channel) {
            window.bridge = channel.objects.bridge;
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

function initApp() {
    bridge.get_initial_data(function (data) {
        if (data) updateUserUI(data.is_logged, data.user);
        navigate("home");
    });

    bridge.get_active_layer_name(function (name) {
        updateLayerBadge(name);
    });

    bridge.nav_changed.connect(function (panelId) {
        loadPanel(panelId);
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
        if (document.getElementById('f-title')) {
            resetEditorForm();
            _loadFormForLayer(null);
        }
    });

    bridge.gn_contacts_ready.connect(function (key, q, results) {
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

    bridge.gn_contact_enriched.connect(function (key, idx, data) {
        var arr = (key === 'main') ? contacts : _sArr(key);
        if (!arr || !arr[idx]) return;
        var d = arr[idx].data;
        Object.keys(data).forEach(function (k) { if (data[k]) d[k] = data[k]; });
        if (key === 'main') renderContacts();
        else renderFor(key);
    });
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
    bridge.navigate(panelId);
    // nav_changed signal already triggers loadPanel - não chamar duas vezes
}

function loadPanel(panelId) {
    // Salva estado do editor antes de substituir o HTML
    if (document.getElementById("f-title")) {
        _editorDraft = collectFormData();
    }
    var container = document.getElementById("app-container");
    container.innerHTML = '<div class="loader">Carregando...</div>';

    bridge.load_panel_html(panelId, function (html) {
        container.innerHTML = html;
        onPanelLoaded(panelId);
    });
}

function onPanelLoaded(panelId) {
    if (panelId === "login") {
        if (typeof bridge !== 'undefined') {
            bridge.login_loading.connect(function (msg) { setLoginState(true, msg); });
            bridge.login_error.connect(function (msg) { setLoginError(msg); });
        }
        return;
    }
    if (panelId === "editor") {
        showTab("identificacao", document.querySelector(".tab-link"));
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
    bridge.export_xml(data);
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
    bridge.export_geohab(data);
}

function trySaveMetadata() {
    var data = collectFormData();
    if (!data) return;
    Modal.confirm('Deseja realmente salvar as alterações no banco de dados?', function () {
        bridge.save_metadata(data);
    }, 'Confirmar Salvamento');
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
}

// Prioridade: draft (edições não salvas) > metadado salvo (DB/sidecar) > vazio
function _loadFormForLayer(sessionDraft) {
    if (sessionDraft) {
        populateForm(sessionDraft);
        return;
    }
    if (typeof bridge === 'undefined') return;
    bridge.load_draft(function (draft) {
        if (draft) {
            populateForm(draft);
        } else {
            bridge.load_layer_metadata(function (saved) {
                if (saved) populateForm(saved);
            });
        }
    });
}

function collectFormData() {
    if (!document.getElementById("f-title")) {
        Modal.alert('Abra "Catálogo > Editor de Metadados" antes de exportar.', 'Ação Necessária', 'warning');
        return null;
    }
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
}

// ─── Badge de usuário ─────────────────────────────────────────────────────────

var _isLogged = false;

function updateUserUI(isLogged, username) {
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
    if (typeof bridge !== 'undefined' && bridge.search_geoserver) {
        if (spinner) spinner.style.display = 'inline-block';
        bridge.search_geoserver(q, function (results) {
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
            '<span class="sugg-sigla">' + escHtml(r.workspace || '') + '</span>' +
            '<span class="sugg-name">' + escHtml(r.title || r.name || '') + '</span>' +
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
    cancelDistLayer();
    renderDistResources();
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
        if (c.data._key) bridge.delete_user_contact(c.data._key);
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
    bridge.save_user_contact(JSON.stringify(d));
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
        bridge.delete_user_contact(key);
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
        bridge.save_user_contact(JSON.stringify(snap));
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
    bridge.export_contact_xml(xml, filename);
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
var _gnSearchTimer = null;
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
    bridge.search_contacts(q, function (results) {
        _localResults = results || [];
        _renderContactSuggestions(q);
    });
    clearTimeout(_gnSearchTimer);
    if (_isLogged) {
        _gnSearchTimer = setTimeout(function () {
            _gnLoading['main'] = true;
            _renderContactSuggestions(q);
            bridge.search_contacts_gn('main', q);
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
        bridge.enrich_gn_contact('main', newIdx, r._gn_uuid);
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
    bridge.search_contacts(q, function (results) {
        _setSugg(key, results || []);
        _renderForSuggestions(key, q);
    });
    clearTimeout(_gnTimers[key]);
    if (_isLogged) {
        _gnTimers[key] = setTimeout(function () {
            _gnLoading[key] = true;
            _renderForSuggestions(key, q);
            bridge.search_contacts_gn(key, q);
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
        bridge.enrich_gn_contact(key, newIdx, r._gn_uuid);
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

// ─── UUID e inicialização do metadado ─────────────────────────────────────────

function generateUUID() {
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function (c) {
        var r = Math.random() * 16 | 0;
        return (c === 'x' ? r : (r & 0x3 | 0x8)).toString(16);
    });
}

function initMetaAuthor() {
    // Começar vazio para que o progresso reflita o trabalho do usuário do zero
    if (metaContacts.length > 0) {
        renderFor('meta');
    } else {
        renderFor('meta');
    }
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

function showLoginLoading() {
    var area = document.getElementById('login-loading-area');
    if (area) area.style.display = 'flex';
}

function hideLoginLoading() {
    var area = document.getElementById('login-loading-area');
    if (area) area.style.display = 'none';
}

function setLoginState(loading) {
    if (loading) { showLoginLoading(); } else { hideLoginLoading(); }
    var errEl = document.getElementById('login-error-msg') ||
        document.getElementById('login-error-msg-adm');
    if (!loading && errEl) errEl.style.display = 'none';
}

function setLoginError(msg) {
    hideLoginLoading();
    var errEl = document.getElementById('login-error-msg') ||
        document.getElementById('login-error-msg-adm');
    if (errEl) { errEl.textContent = msg; errEl.style.display = 'block'; }
    else { Modal.alert(msg, 'Erro de Login', 'error'); }
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

        // Skip if the form-group already has a ? help button,
        // but never skip items inside a dropdown (they have no ? button)
        var inDropdown = target.closest('.custom-select-dropdown');
        if (!inDropdown) {
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
        dropdown.innerHTML = optionsHtml;
        wrapper.appendChild(dropdown);

        select.parentNode.insertBefore(wrapper, select.nextSibling);

        // --- Interaction Logic ---
        var isOpen = false;

        function closeDropdown() {
            dropdown.style.display = 'none';
            wrapper.classList.remove('open');
            isOpen = false;
        }

        function openDropdown() {
            // Close others
            document.querySelectorAll('.custom-select.open').forEach(function (el) {
                if (el !== wrapper) {
                    el.querySelector('.custom-select-dropdown').style.display = 'none';
                    el.classList.remove('open');
                }
            });
            dropdown.style.display = 'block';
            wrapper.classList.add('open');
            isOpen = true;

            // Scroll to active item
            var activeItem = dropdown.querySelector('.suggestion-item.active');
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
            if (!item) return;

            var idx = item.getAttribute('data-index');
            select.selectedIndex = idx;
            valueSpan.textContent = item.textContent;

            // Update active class
            dropdown.querySelectorAll('.suggestion-item').forEach(function (el) { el.classList.remove('active'); });
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

        // Keyboard navigation
        var searchString = '';
        var searchTimeout = null;

        wrapper.addEventListener('keydown', function (e) {
            if (e.key === 'Tab') {
                closeDropdown();
                return;
            }

            e.preventDefault(); // Prevent page scroll for arrows

            var items = Array.from(dropdown.querySelectorAll('.suggestion-item'));
            var activeIdx = items.findIndex(function (item) { return item.classList.contains('active'); });

            if (e.key === 'ArrowDown') {
                if (!isOpen) openDropdown();
                else {
                    var nextIdx = activeIdx + 1 < items.length ? activeIdx + 1 : items.length - 1;
                    items[activeIdx]?.classList.remove('active');
                    items[nextIdx].classList.add('active');
                    items[nextIdx].scrollIntoView({ block: 'nearest' });
                }
            } else if (e.key === 'ArrowUp') {
                if (!isOpen) openDropdown();
                else {
                    var prevIdx = activeIdx - 1 >= 0 ? activeIdx - 1 : 0;
                    items[activeIdx]?.classList.remove('active');
                    items[prevIdx].classList.add('active');
                    items[prevIdx].scrollIntoView({ block: 'nearest' });
                }
            } else if (e.key === 'Enter' || e.key === ' ') {
                if (!isOpen) {
                    openDropdown();
                } else {
                    if (activeIdx >= 0) {
                        items[activeIdx].click();
                    }
                }
            } else if (e.key === 'Escape') {
                closeDropdown();
            } else if (e.key.length === 1) {
                // Type to search
                if (!isOpen) openDropdown();
                searchString += e.key.toLowerCase();
                clearTimeout(searchTimeout);

                searchTimeout = setTimeout(function () {
                    searchString = '';
                }, 1000);

                var matchIdx = items.findIndex(function (item) {
                    return item.textContent.trim().toLowerCase().startsWith(searchString);
                });

                if (matchIdx >= 0) {
                    if (activeIdx >= 0) items[activeIdx].classList.remove('active');
                    items[matchIdx].classList.add('active');
                    items[matchIdx].scrollIntoView({ block: 'nearest' });
                }
            }
        });

        // Listen for programmatic value changes on the original select
        select.addEventListener('change', function () {
            var selectedOpt = select.options[select.selectedIndex];
            if (selectedOpt) {
                valueSpan.textContent = selectedOpt.text;
                dropdown.querySelectorAll('.suggestion-item').forEach(function (el) {
                    el.classList.toggle('active', el.getAttribute('data-value') === selectedOpt.value);
                });
            }
        });
    });
}

document.addEventListener('DOMContentLoaded', function () {
    initGlobalTooltips();
});
