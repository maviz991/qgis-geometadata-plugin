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

document.addEventListener("click", function (e) {
    var box = document.getElementById("search-suggestions");
    if (!box || box.style.display === "none") return;
    var input = document.getElementById("contact-search");
    if (input && input.contains(e.target)) return;
    if (box.contains(e.target)) return;
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
    loadPanel(panelId);
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
    if (panelId === "editor") {
        showTab("identificacao", document.querySelector(".tab-link"));
        var now = new Date().toISOString().slice(0, 16);
        var ds = document.getElementById("f-dateStamp");
        if (ds && !ds.value) ds.value = now;
        contacts = [];
        renderContacts();
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
    var keywords_raw = get("MD_Keywords");
    var keywords = keywords_raw
        .split(",")
        .map(function (k) { return k.trim(); })
        .filter(Boolean);

    // Map first contact to flat fields for XML generator compatibility
    var c = contacts.length > 0 ? contacts[0].data : {};

    return {
        title:                            get("title"),
        dateType:                         get("dateType"),
        date:                             get("date"),
        edition:                          get("edition") || "1",
        date_edition:                     get("date_edition"),
        abstract:                         get("abstract"),
        purpose:                          get("purpose"),
        credit:                           get("credit"),
        status_codeListValue:             get("status_codeListValue"),
        MD_Keywords:                      keywords,
        maintenanceFrequency:             get("maintenanceFrequency"),
        dateOfNextUpdate:                 get("dateOfNextUpdate"),
        MD_SpatialRepresentationTypeCode: get("MD_SpatialRepresentationTypeCode"),
        topicCategory:                    get("topicCategory"),
        hierarchyLevel:                   get("hierarchyLevel") || "dataset",
        LanguageCode:                     get("LanguageCode") || "por",
        characterSet:                     get("characterSet") || "utf8",
        thumbnail_url:                    get("thumbnail_url"),
        westBoundLongitude:               get("westBoundLongitude"),
        eastBoundLongitude:               get("eastBoundLongitude"),
        southBoundLatitude:               get("southBoundLatitude"),
        northBoundLatitude:               get("northBoundLatitude"),
        spatialResolution_denominator:    get("spatialResolution_denominator"),
        epsgCode:                         get("epsgCode"),
        epsgTitle:                        get("epsgTitle"),
        zMin:                             get("zMin"),
        zMax:                             get("zMax"),
        temporalFrom:                     get("temporalFrom"),
        temporalTo:                       get("temporalTo"),
        dateStamp:                        get("dateStamp"),
        // Flat contact fields (first contact) for XML generator
        contact_individualName:           c.sigla    || "",
        contact_organisationName:         c.org      || "",
        contact_positionName:             c.position || "",
        contact_phone:                    c.phone    || "",
        contact_deliveryPoint:            c.address  || "",
        contact_city:                     c.city     || "",
        contact_administrativeArea:       c.state    || "",
        contact_postalCode:               c.zip      || "",
        contact_country:                  c.country  || "Brasil",
        contact_email:                    c.email    || "",
        contact_role:                     c.role     || "",
        // Full contacts array for future multi-contact support
        contacts: contacts
    };
}

var REQUIRED_LABELS = {
    title:                            "Título",
    date:                             "Data do Dado",
    maintenanceFrequency:             "Frequência de Atualização",
    abstract:                         "Resumo",
    credit:                           "Crédito",
    status_codeListValue:             "Status",
    MD_Keywords:                      "Palavras-chave",
    MD_SpatialRepresentationTypeCode: "Tipo de Representação Espacial",
    topicCategory:                    "Categoria Temática",
    hierarchyLevel:                   "Nível Hierárquico",
    LanguageCode:                     "Idioma",
    westBoundLongitude:               "Longitude Oeste",
    eastBoundLongitude:               "Longitude Leste",
    southBoundLatitude:               "Latitude Sul",
    northBoundLatitude:               "Latitude Norte",
    epsgCode:                         "Código EPSG",
    epsgTitle:                        "Título do SRC"
};

function validateForm(data) {
    var missing = [];
    for (var key in REQUIRED_LABELS) {
        var val = data[key];
        var empty = !val || (Array.isArray(val) && val.length === 0) || String(val).trim() === "";
        if (empty) {
            var el = document.getElementById("f-" + key);
            if (el) el.classList.add("error");
            missing.push(REQUIRED_LABELS[key]);
        } else {
            var el2 = document.getElementById("f-" + key);
            if (el2) el2.classList.remove("error");
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
        "MD_Keywords",
        "maintenanceFrequency", "dateOfNextUpdate",
        "MD_SpatialRepresentationTypeCode", "topicCategory", "hierarchyLevel",
        "LanguageCode", "characterSet", "thumbnail_url",
        "westBoundLongitude", "eastBoundLongitude", "southBoundLatitude", "northBoundLatitude",
        "spatialResolution_denominator", "epsgCode", "epsgTitle",
        "zMin", "zMax", "temporalFrom", "temporalTo", "dateStamp"
    ];
    SIMPLE_FIELDS.forEach(function (key) {
        var el = document.getElementById("f-" + key);
        if (!el) return;
        var val = data[key];
        if (key === "MD_Keywords" && Array.isArray(val)) val = val.join(", ");
        if (val !== undefined && val !== null) el.value = val;
    });
    var mf = document.getElementById("f-maintenanceFrequency");
    if (mf) toggleUpdateDate(mf.value);
    var ed = document.getElementById("f-edition");
    if (ed) toggleEditionDate(ed.value);
    if (Array.isArray(data.contacts) && data.contacts.length > 0) {
        contacts = data.contacts;
        renderContacts();
    }
}

// ─── Badge de usuário ─────────────────────────────────────────────────────────

function updateUserUI(isLogged, username) {
    var btn   = document.getElementById("login-btn");
    var badge = document.getElementById("user-info");
    if (!btn || !badge) return;

    if (isLogged) {
        btn.style.display = "none";
        badge.style.display = "flex";
        badge.querySelector(".user-name").innerText = username;
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
    "EPSG:4326":  "WGS 84",
    "EPSG:4674":  "SIRGAS 2000",
    "EPSG:4618":  "SAD69",
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
        var codeEl  = document.getElementById("f-epsgCode");
        var titleEl = document.getElementById("f-epsgTitle");
        if (codeEl)  codeEl.value  = result.code  || "";
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

// ─── Contatos: estado ──────────────────────────────────────────────────────────

var contacts = [];

var ROLE_LABELS = {
    "owner":               "Dono",
    "author":              "Autor",
    "processor":           "Organizador",
    "distributor":         "Distribuidor",
    "custodian":           "Depositário",
    "resourceProvider":    "Fornecedor de recurso",
    "principalInvestigator": "Investigador principal",
    "originator":          "Originador",
    "pointOfContact":      "Ponto de contato",
    "publisher":           "Publicador",
    "user":                "Utilizador"
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
    var accSelect   = document.getElementById("role-acc-"   + idx);
    if (tableSelect && tableSelect.value !== val) tableSelect.value = val;
    if (accSelect   && accSelect.value   !== val) accSelect.value   = val;
}

// ─── Contatos: render ──────────────────────────────────────────────────────────

function renderContacts() {
    var tbody  = document.getElementById("contacts-tbody");
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
            '<td>' + (c.data.org   || '—') + '</td>' +
            '<td>' + (c.data.sigla || '—') + '</td>' +
            '<td>' + (c.data.email || '—') + '</td>' +
            '<td>' + buildRoleSelect(idx, c.data.role) + '</td>' +
            '<td style="white-space:nowrap">' +
            '<button class="btn-move" onclick="moveContact(' + idx + ',-1)" title="Mover para cima"' + (idx === 0    ? ' disabled' : '') + '>↑</button>' +
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
    var d     = c.data;
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

    return field('Sigla',       d.sigla,    isManual, 'acc-' + idx + '-sigla') +
        field('Organização',    d.org,      isManual, 'acc-' + idx + '-org') +
        roleField +
        field('E-mail',         d.email,    isManual, 'acc-' + idx + '-email') +
        field('Cargo',          d.position, isManual, 'acc-' + idx + '-position') +
        field('Telefone',       d.phone,    isManual, 'acc-' + idx + '-phone') +
        '<div class="form-group span-2"><label>Endereço</label>' +
        (isManual
            ? '<input id="acc-' + idx + '-address" type="text" value="' + (d.address || '') + '">'
            : '<div class="readonly-field">' + (d.address || '—') + '</div>') +
        '</div>' +
        field('Cidade', d.city,    isManual, 'acc-' + idx + '-city') +
        field('Estado', d.state,   isManual, 'acc-' + idx + '-state') +
        field('CEP',    d.zip,     isManual, 'acc-' + idx + '-zip') +
        field('País',   d.country, isManual, 'acc-' + idx + '-country');
}

function toggleAccordion(idx) {
    var body = document.getElementById("acc-body-" + idx);
    var arr  = document.getElementById("arr-" + idx);
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
            sigla:    sigla,
            org:      org,
            email:    g("email"),
            role:     g("role"),
            position: g("position"),
            phone:    g("phone"),
            address:  g("address"),
            city:     g("city"),
            state:    g("state"),
            zip:      g("zip"),
            country:  g("country") || "Brasil"
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
