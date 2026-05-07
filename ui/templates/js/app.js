// app.js — Lógica principal do GeoMetadata HTML
var bridge;

document.addEventListener("DOMContentLoaded", function () {
    if (typeof qt !== "undefined") {
        new QWebChannel(qt.webChannelTransport, function (channel) {
            window.bridge = channel.objects.bridge;
            initApp();
        });
    } else {
        console.warn("QWebChannel não detectado. Modo desenvolvimento local?");
    }
});

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

    bridge.nav_changed.connect(function (panelId) {
        loadPanel(panelId);
    });

    bridge.auth_status.connect(function (isLogged, username) {
        updateUserUI(isLogged, username);
    });

    bridge.form_data_req.connect(function (data) {
        populateForm(data);
    });
}

// ─── Navegação ────────────────────────────────────────────────────────────────

function navigate(panelId) {
    bridge.navigate(panelId);
    // nav_changed signal already triggers loadPanel — não chamar duas vezes
}

function loadPanel(panelId) {
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
            bridge.login_error.connect(function (msg)   { setLoginError(msg); });
        }
        return;
    }
    if (panelId === "editor") {
        showTab("identificacao", document.querySelector(".tab-link"));
        var now = new Date().toISOString().slice(0, 16);
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
    var missing = validateForm(data);
    if (missing.length > 0) { showValidationError(missing); return; }
    bridge.export_xml(data);
}

function tryExportGeohab() {
    var data = collectFormData();
    if (!data) return;
    var missing = validateForm(data);
    if (missing.length > 0) { showValidationError(missing); return; }
    bridge.export_geohab(data);
}

function trySaveMetadata() {
    var data = collectFormData();
    if (!data) return;
    bridge.save_metadata(data);
}

// ─── Formulário ───────────────────────────────────────────────────────────────

function collectFormData() {
    if (!document.getElementById("f-title")) {
        alert('Abra "Catálogo Geohab > Editar Metadados" antes de exportar.');
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
        hierarchyLevel: get("hierarchyLevel") || "dataset",
        LanguageCode: get("LanguageCode") || "por",
        characterSet: get("characterSet") || "utf8",
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
        contact_deliveryPoint: c.address || "",
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
    epsgTitle: "Título do SRC"
};

function validateForm(data) {
    var missing = [];
    for (var key in REQUIRED_LABELS) {
        var val = data[key];
        var empty = !val || (Array.isArray(val) && val.length === 0) || String(val).trim() === "";
        if (empty) {
            if (key === "MD_Keywords") {
                var chipsBox = document.getElementById("keyword-chips");
                if (chipsBox) chipsBox.style.outline = "2px solid var(--accent)";
            } else {
                var el = document.getElementById("f-" + key);
                if (el) el.classList.add("error");
            }
            missing.push(REQUIRED_LABELS[key]);
        } else {
            if (key === "MD_Keywords") {
                var chipsBox2 = document.getElementById("keyword-chips");
                if (chipsBox2) chipsBox2.style.outline = "";
            } else {
                var el2 = document.getElementById("f-" + key);
                if (el2) el2.classList.remove("error");
            }
        }
    }
    if (contacts.length === 0) {
        missing.push("Contato (ao menos um)");
    } else if (!contacts[0].data.role) {
        missing.push("Responsabilidade do Contato");
    }
    return missing;
}

function showValidationError(missing) {
    alert("Preencha os campos obrigatórios:\n• " + missing.join("\n• "));
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
        if (el && data[key] !== undefined && data[key] !== null) el.value = data[key];
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
    if (typeof bridge === "undefined") { alert("Disponível apenas no QGIS."); return; }
    bridge.get_layer_info(function (result) {
        if (!result) { alert("Nenhuma camada ativa ou informações não disponíveis."); return; }
        var codeEl = document.getElementById("f-epsgCode");
        var titleEl = document.getElementById("f-epsgTitle");
        if (codeEl) codeEl.value = result.code || "";
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
    });
}

// ─── Utilitário ───────────────────────────────────────────────────────────────

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
            '<button onclick="removeKeyword(' + i + ')" title="Remover">×</button></span>';
    }).join('');
}

// ─── Distribuição: recursos online ────────────────────────────────────────────

var distResources = [];
var _distSugg = [];
var _distStagedLayer = null;

function searchGeoServer(q) {
    var box = document.getElementById('dist-suggestions');
    if (!q || q.length < 2) { if (box) box.style.display = 'none'; return; }
    if (typeof bridge !== 'undefined' && bridge.search_geoserver) {
        bridge.search_geoserver(q, function (results) {
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

    // WMS — sempre disponível (público)
    if (wmsChk) { wmsChk.checked = true; wmsChk.disabled = false; }

    // WFS — só se autenticado (vem como wfs_available do bridge, ou _isLogged)
    var wfsOk = !!(l.wfs_available !== undefined ? l.wfs_available : _isLogged);
    if (wfsChk) {
        wfsChk.checked = false;   // opt-in: user decide se quer WFS
        wfsChk.disabled = !wfsOk;
    }
    if (wfsToggle) {
        wfsToggle.title = wfsOk ? '' : 'Requer autenticação';
        wfsToggle.style.opacity = wfsOk ? '' : '0.45';
    }

    // WCS — nunca disponível via WMS caps (raster needs separate check)
    if (wcsChk) { wcsChk.checked = false; wcsChk.disabled = true; }
    if (wcsToggle) { wcsToggle.style.display = 'none'; }

    card.style.display = 'block';
}

function cancelDistLayer() {
    _distStagedLayer = null;
    var card = document.getElementById('dist-layer-card');
    if (card) card.style.display = 'none';
}

function confirmDistLayer() {
    if (!_distStagedLayer) return;
    var l = _distStagedLayer;
    var pairs = [
        { id: 'dist-pick-wms', proto: 'OGC:WMS', url: l.wms_url },
        { id: 'dist-pick-wfs', proto: 'OGC:WFS', url: l.wfs_url },
        { id: 'dist-pick-wcs', proto: 'OGC:WCS', url: l.wcs_url }
    ];
    pairs.forEach(function (p) {
        var cb = document.getElementById(p.id);
        if (cb && cb.checked && p.url) {
            distResources.push({ url: p.url, protocol: p.proto, name: l.name || '', description: l.title || '' });
        }
    });
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
    if (!url) { alert('Informe a URL do recurso.'); return; }
    var proto = (document.getElementById('dist-mf-protocol') || {}).value || 'OGC:WMS';
    var name = ((document.getElementById('dist-mf-name') || {}).value || '').trim();
    var desc = ((document.getElementById('dist-mf-description') || {}).value || '').trim();
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
        return;
    }
    var protoCls = { 'OGC:WMS': 'wms', 'OGC:WFS': 'wfs', 'OGC:WCS': 'wcs', 'OGC:WPS': 'wps', 'WWW:DOWNLOAD': 'download' };
    tbody.innerHTML = distResources.map(function (r, i) {
        var cls = protoCls[r.protocol] || 'link';
        return '<tr>' +
            '<td style="text-align:center">' + (i + 1) + '</td>' +
            '<td>' + escHtml(r.name || '—') +
            (r.description ? '<br><small style="color:var(--fg-muted)">' + escHtml(r.description) + '</small>' : '') +
            '</td>' +
            '<td><span class="proto-badge ' + cls + '">' + escHtml(r.protocol) + '</span></td>' +
            '<td style="font-size:11px;color:var(--fg-muted);max-width:160px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="' + escHtml(r.url) + '">' + escHtml(r.url) + '</td>' +
            '<td><button class="btn-remove" onclick="removeDistResource(' + i + ')" title="Remover">✕</button></td>' +
            '</tr>';
    }).join('');
}

// ─── Licença: preenchimento automático por tipo ────────────────────────────────

var _licensePresets = {
    'CC BY 4.0': { useLimitation: 'Creative Commons Atribuição 4.0 Internacional (CC BY 4.0). Permite uso, distribuição e adaptação para qualquer fim, inclusive comercial, desde que a fonte seja atribuída.', accessConstraints: 'license', useConstraints: 'license', otherConstraints: '' },
    'CC BY-SA 4.0': { useLimitation: 'Creative Commons Atribuição-CompartilhaIgual 4.0 Internacional (CC BY-SA 4.0). Derivados devem ser distribuídos sob a mesma licença.', accessConstraints: 'license', useConstraints: 'license', otherConstraints: '' },
    'CC BY-NC 4.0': { useLimitation: 'Creative Commons Atribuição-NãoComercial 4.0 Internacional (CC BY-NC 4.0). Uso não comercial apenas.', accessConstraints: 'license', useConstraints: 'license', otherConstraints: '' },
    'CC BY-NC-SA 4.0': { useLimitation: 'Creative Commons Atribuição-NãoComercial-CompartilhaIgual 4.0 Internacional (CC BY-NC-SA 4.0).', accessConstraints: 'license', useConstraints: 'license', otherConstraints: '' },
    'CC0': { useLimitation: 'CC0 1.0 Dedicação ao Domínio Público. Nenhum direito reservado.', accessConstraints: 'unrestricted', useConstraints: 'unrestricted', otherConstraints: '' },
    'proprietary': { useLimitation: 'Todos os direitos reservados. Uso autorizado exclusivamente conforme termos estabelecidos pela CDHU.', accessConstraints: 'copyright', useConstraints: 'intellectualPropertyRights', otherConstraints: '© CDHU — Companhia de Desenvolvimento Habitacional e Urbano do Estado de São Paulo. Todos os direitos reservados.' },
    'internal': { useLimitation: 'Uso interno restrito à CDHU e suas unidades. Distribuição externa não autorizada.', accessConstraints: 'restricted', useConstraints: 'restricted', otherConstraints: '© CDHU — Companhia de Desenvolvimento Habitacional e Urbano do Estado de São Paulo. Documento de uso interno.' }
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

var ROLE_OPTIONS = Object.keys(ROLE_LABELS).map(function (v) {
    return { value: v, label: ROLE_LABELS[v] };
});

function buildRoleSelect(idx, current) {
    var selected = current || "pointOfContact";
    if (contacts[idx]) contacts[idx].data.role = contacts[idx].data.role || selected;
    var opts = ROLE_OPTIONS.map(function (r) {
        return '<option value="' + r.value + '"' + (r.value === selected ? ' selected' : '') + '>' + r.label + '</option>';
    }).join('');
    return '<select id="role-table-' + idx + '" class="role-select" onchange="updateRole(' + idx + ', this.value)">' + opts + '</select>';
}

function updateRole(idx, val) {
    if (!contacts[idx]) return;
    contacts[idx].data.role = val;
    var tableSelect = document.getElementById("role-table-" + idx);
    var accSelect = document.getElementById("role-acc-" + idx);
    if (tableSelect && tableSelect.value !== val) tableSelect.value = val;
    if (accSelect && accSelect.value !== val) accSelect.value = val;
}

// ─── Contatos: render ──────────────────────────────────────────────────────────

function renderContacts() {
    var tbody = document.getElementById("contacts-tbody");
    var accDiv = document.getElementById("contacts-accordions");
    if (!tbody) return;

    if (contacts.length === 0) {
        tbody.innerHTML = '<tr><td colspan="6" class="empty-state">Nenhum contato. Use a busca ou clique em <b>+ Manual</b>.</td></tr>';
        if (accDiv) accDiv.innerHTML = "";
        return;
    }

    var last = contacts.length - 1;
    tbody.innerHTML = contacts.map(function (c, idx) {
        return '<tr>' +
            '<td style="text-align:center;color:var(--fg-muted);font-weight:700;font-size:12px">' + (idx + 1) + '</td>' +
            '<td>' + (c.data.org || '—') + '</td>' +
            '<td>' + (c.data.sigla || '—') + '</td>' +
            '<td>' + (c.data.email || '—') + '</td>' +
            '<td>' + buildRoleSelect(idx, c.data.role) + '</td>' +
            '<td style="white-space:nowrap">' +
            '<button class="btn-move" onclick="moveContact(' + idx + ',-1)" title="Mover para cima"' + (idx === 0 ? ' disabled' : '') + '>↑</button>' +
            '<button class="btn-move" onclick="moveContact(' + idx + ', 1)" title="Mover para baixo"' + (idx === last ? ' disabled' : '') + '>↓</button>' +
            '<button class="btn-remove" onclick="removeContact(' + idx + ')" title="Remover">✕</button>' +
            '</td>' +
            '</tr>';
    }).join('');

    if (accDiv) {
        accDiv.innerHTML = contacts.map(function (c, idx) {
            return buildAccordion(c, idx);
        }).join('');
    }
}

function buildAccordion(c, idx) {
    var d = c.data;
    var label = 'Contato ' + (idx + 1) + (d.sigla ? ' — ' + d.sigla : '');
    var badge = c.isManual
        ? '<span class="badge-manual">Manual</span>'
        : '<span class="badge-preset">Catálogo</span>';

    return '<div class="contact-accordion">' +
        '<button class="accordion-header" onclick="toggleAccordion(' + idx + ')">' +
        '<span class="acc-arrow" id="arr-' + idx + '"><img class="acc-chevron" src="../../img/chevron_down.svg"></span>' +
        label + badge +
        '</button>' +
        '<div class="accordion-body" id="acc-body-' + idx + '">' +
        '<div class="form-grid">' + buildAccordionFields(d, idx, c.isManual) + '</div>' +
        '</div>' +
        '</div>';
}

function field(label, val, editable, inputId) {
    var input = editable
        ? '<input id="' + inputId + '" type="text" value="' + (val || '') + '">'
        : '<div class="readonly-field">' + (val || '—') + '</div>';
    return '<div class="form-group"><label>' + label + '</label>' + input + '</div>';
}

function buildAccordionFields(d, idx, isManual) {
    var selectedRole = d.role || "pointOfContact";
    var roleOpts = ROLE_OPTIONS.map(function (r) {
        return '<option value="' + r.value + '"' + (r.value === selectedRole ? ' selected' : '') + '>' + r.label + '</option>';
    }).join('');
    var roleField = '<div class="form-group"><label>Regra</label>' +
        '<select id="role-acc-' + idx + '" class="role-select" onchange="updateRole(' + idx + ', this.value)">' + roleOpts + '</select></div>';

    return field('Sigla', d.sigla, isManual, 'acc-' + idx + '-sigla') +
        field('Organização', d.org, isManual, 'acc-' + idx + '-org') +
        roleField +
        field('E-mail', d.email, isManual, 'acc-' + idx + '-email') +
        field('Cargo', d.position, isManual, 'acc-' + idx + '-position') +
        field('Telefone', d.phone, isManual, 'acc-' + idx + '-phone') +
        '<div class="form-group span-2"><label>Endereço</label>' +
        (isManual
            ? '<input id="acc-' + idx + '-address" type="text" value="' + (d.address || '') + '">'
            : '<div class="readonly-field">' + (d.address || '—') + '</div>') +
        '</div>' +
        field('Cidade', d.city, isManual, 'acc-' + idx + '-city') +
        field('Estado', d.state, isManual, 'acc-' + idx + '-state') +
        field('CEP', d.zip, isManual, 'acc-' + idx + '-zip') +
        field('País', d.country, isManual, 'acc-' + idx + '-country');
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

function removeContact(idx) {
    contacts.splice(idx, 1);
    renderContacts();
}

// ─── Busca de contatos (via bridge) ───────────────────────────────────────────

var _suggestionResults = [];

function suggestContacts(q) {
    q = (q || "").trim();
    if (!q) { closeSuggestions(); return; }
    bridge.search_contacts(q, function (results) {
        _suggestionResults = results || [];
        var box = document.getElementById("search-suggestions");
        if (!box) return;
        if (!_suggestionResults.length) {
            box.innerHTML = '<div class="suggestion-item" style="color:var(--fg-muted);cursor:default;">Nenhum resultado para "' + q + '"</div>';
            box.style.display = "block";
            return;
        }
        box.innerHTML = _suggestionResults.map(function (r, i) {
            var label = (r.sigla ? "<b>" + r.sigla + "</b> — " : "") + r.org;
            return '<div class="suggestion-item" onclick="pickSuggestion(' + i + ')">' + label + '</div>';
        }).join("");
        box.style.display = "block";
    });
}

function pickSuggestion(idx) {
    var r = _suggestionResults[idx];
    if (!r) return;
    contacts.push({ isManual: false, data: r });
    var inp = document.getElementById("contact-search");
    if (inp) inp.value = "";
    closeSuggestions();
    renderContacts();
}

function closeSuggestions() {
    var box = document.getElementById("search-suggestions");
    if (box) box.style.display = "none";
    _suggestionResults = [];
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

function _sArr(key) { return key === 'proc' ? procContacts : metaContacts; }
function _sSugg(key) { return key === 'proc' ? _procSugg : _metaSugg; }
function _setSArr(key, v) { if (key === 'proc') procContacts = v; else metaContacts = v; }
function _setSugg(key, v) { if (key === 'proc') _procSugg = v; else _metaSugg = v; }

function suggestFor(key, q) {
    q = (q || '').trim();
    if (!q) { closeFor(key); return; }
    bridge.search_contacts(q, function (results) {
        _setSugg(key, results || []);
        var box = document.getElementById(key + '-suggestions');
        if (!box) return;
        if (!_sSugg(key).length) {
            box.innerHTML = '<div class="suggestion-item" style="color:var(--fg-muted);cursor:default">Nenhum resultado para "' + q + '"</div>';
            box.style.display = 'block';
            return;
        }
        box.innerHTML = _sSugg(key).map(function (r, i) {
            var label = (r.sigla ? '<b>' + r.sigla + '</b> — ' : '') + r.org;
            return '<div class="suggestion-item" onclick="pickFor(\'' + key + '\',' + i + ')">' + label + '</div>';
        }).join('');
        box.style.display = 'block';
    });
}

function pickFor(key, idx) {
    var r = _sSugg(key)[idx];
    if (!r) return;
    _sArr(key).push({ isManual: false, data: r });
    var inp = document.getElementById(key + '-search');
    if (inp) inp.value = '';
    closeFor(key);
    renderFor(key);
}

function closeFor(key) {
    var box = document.getElementById(key + '-suggestions');
    if (box) box.style.display = 'none';
    _setSugg(key, []);
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
    if (t && t.value !== val) t.value = val;
    if (a && a.value !== val) a.value = val;
}

function renderFor(key) {
    var arr = _sArr(key);
    var tbody = document.getElementById(key + '-tbody');
    var accDiv = document.getElementById(key + '-accordions');
    if (!tbody) return;
    if (arr.length === 0) {
        tbody.innerHTML = '<tr><td colspan="5" class="empty-state">Nenhum contato adicionado.</td></tr>';
        if (accDiv) accDiv.innerHTML = '';
        return;
    }
    tbody.innerHTML = arr.map(function (c, idx) {
        var sel = c.data.role || 'pointOfContact';
        var opts = ROLE_OPTIONS.map(function (r) {
            return '<option value="' + r.value + '"' + (r.value === sel ? ' selected' : '') + '>' + r.label + '</option>';
        }).join('');
        return '<tr>' +
            '<td style="text-align:center;color:var(--fg-muted);font-weight:700;font-size:12px">' + (idx + 1) + '</td>' +
            '<td>' + (c.data.org || '—') + '</td>' +
            '<td>' + (c.data.sigla || '—') + '</td>' +
            '<td><select id="role-' + key + '-t-' + idx + '" class="role-select" onchange="updateRoleFor(\'' + key + '\',' + idx + ',this.value)">' + opts + '</select></td>' +
            '<td><button class="btn-remove" onclick="removeFrom(\'' + key + '\',' + idx + ')" title="Remover">✕</button></td>' +
            '</tr>';
    }).join('');
    if (accDiv) {
        accDiv.innerHTML = arr.map(function (c, idx) {
            return buildAccordionFor(c, idx, key);
        }).join('');
    }
}

function buildAccordionFor(c, idx, key) {
    var d = c.data;
    var lbl = 'Contato ' + (idx + 1) + (d.sigla ? ' — ' + d.sigla : '');
    var badge = c.isManual ? '<span class="badge-manual">Manual</span>' : '<span class="badge-preset">Catálogo</span>';
    var sel = d.role || 'pointOfContact';
    var rOpts = ROLE_OPTIONS.map(function (r) {
        return '<option value="' + r.value + '"' + (r.value === sel ? ' selected' : '') + '>' + r.label + '</option>';
    }).join('');
    var flds =
        field('Sigla', d.sigla, c.isManual, 'af-' + key + '-' + idx + '-sigla') +
        field('Organização', d.org, c.isManual, 'af-' + key + '-' + idx + '-org') +
        '<div class="form-group"><label>Regra</label>' +
        '<select id="role-' + key + '-a-' + idx + '" class="role-select" onchange="updateRoleFor(\'' + key + '\',' + idx + ',this.value)">' + rOpts + '</select></div>' +
        field('E-mail', d.email, c.isManual, 'af-' + key + '-' + idx + '-email') +
        field('Cargo', d.position, c.isManual, 'af-' + key + '-' + idx + '-position') +
        field('Telefone', d.phone, c.isManual, 'af-' + key + '-' + idx + '-phone');
    return '<div class="contact-accordion">' +
        '<button class="accordion-header" onclick="toggleAccordionFor(\'' + key + '\',' + idx + ')">' +
        '<span class="acc-arrow" id="arr-' + key + '-' + idx + '"><img class="acc-chevron" src="../../img/chevron_down.svg"></span>' +
        lbl + badge + '</button>' +
        '<div class="accordion-body" id="acc-body-' + key + '-' + idx + '">' +
        '<div class="form-grid">' + flds + '</div></div></div>';
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
    var sigla = g('sigla'), org = g('org');
    if (!sigla && !org) { alert('Informe ao menos Sigla ou Organização.'); return; }
    _sArr(key).push({
        isManual: true,
        data: {
            sigla: sigla, org: org, email: g('email'), role: g('role') || 'pointOfContact',
            position: g('position'), phone: g('phone'),
            address: g('address'), city: g('city'), state: g('state'), zip: g('zip'),
            country: g('country') || 'Brasil'
        }
    });
    ['sigla', 'org', 'email', 'position', 'phone', 'address', 'city', 'zip'].forEach(function (f) {
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
    if (metaContacts.length > 0) { renderFor('meta'); return; }
    var fallback = {
        isManual: false,
        data: {
            sigla: 'CDHU', org: 'Companhia de Desenvolvimento Habitacional e Urbano',
            role: 'owner', email: 'geohab@cdhu.sp.gov.br',
            position: 'Gerência de Geoinformação', phone: '',
            address: '', city: 'São Paulo', state: 'SP', zip: '', country: 'Brasil'
        }
    };
    if (typeof bridge === 'undefined') { metaContacts.push(fallback); renderFor('meta'); return; }
    bridge.search_contacts('CDHU', function (results) {
        var cdhu = results && results.find(function (r) { return r.sigla === 'CDHU'; });
        if (cdhu) { cdhu.role = 'owner'; metaContacts.push({ isManual: false, data: cdhu }); }
        else { metaContacts.push(fallback); }
        renderFor('meta');
    });
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
    if (!user || !pass) { alert('Informe usuário e senha.'); return; }
    if (typeof bridge !== 'undefined' && bridge.do_admin_login) {
        setLoginState(true, 'Verificando credenciais...');
        bridge.do_admin_login(user, pass);
    }
}

function setLoginState(loading, message) {
    var btns = document.querySelectorAll('.btn-login-action');
    btns.forEach(function (btn) {
        btn.disabled = loading;
        if (loading) {
            if (!btn.dataset.label) btn.dataset.label = btn.textContent;
            btn.textContent = message || 'Aguardando...';
        } else {
            if (btn.dataset.label) { btn.textContent = btn.dataset.label; delete btn.dataset.label; }
        }
    });
    var errEl = document.getElementById('login-error-msg');
    if (errEl) errEl.style.display = 'none';
}

function setLoginError(msg) {
    setLoginState(false, '');
    // show in whichever error element is currently visible
    var errEl = document.getElementById('login-error-msg') ||
                document.getElementById('login-error-msg-adm');
    if (errEl) { errEl.textContent = msg; errEl.style.display = 'block'; }
    else { alert(msg); }
}

function submitManualContact() {
    var g = function (id) {
        var el = document.getElementById("mf-" + id);
        return el ? el.value.trim() : "";
    };
    var sigla = g("sigla"), org = g("org");
    if (!sigla && !org) { alert("Informe ao menos Sigla ou Organização."); return; }
    contacts.push({
        isManual: true,
        data: {
            sigla: sigla,
            org: org,
            email: g("email"),
            role: g("role"),
            position: g("position"),
            phone: g("phone"),
            address: g("address"),
            city: g("city"),
            state: g("state"),
            zip: g("zip"),
            country: g("country") || "Brasil"
        }
    });
    ["sigla", "org", "email", "role", "position", "phone", "address", "city", "state", "zip"].forEach(function (f) {
        var el = document.getElementById("mf-" + f);
        if (el) el.value = "";
    });
    var countryEl = document.getElementById("mf-country");
    if (countryEl) countryEl.value = "Brasil";
    toggleManualForm();
    renderContacts();
    setTimeout(function () { toggleAccordion(contacts.length - 1); }, 50);
}
