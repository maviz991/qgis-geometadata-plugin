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
        var dc = document.getElementById("f-date_creation");
        if (ds && !ds.value) ds.value = now;
        if (dc && !dc.value) dc.value = now;
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

var FORM_FIELDS = [
    "title", "edition", "abstract", "MD_Keywords", "spatialResolution_denominator",
    "thumbnail_url", "status_codeListValue", "MD_SpatialRepresentationTypeCode",
    "LanguageCode", "characterSet", "topicCategory", "hierarchyLevel",
    "contact_individualName", "contact_organisationName", "contact_positionName",
    "contact_phone", "contact_deliveryPoint", "contact_city", "contact_administrativeArea",
    "contact_postalCode", "contact_country", "contact_email", "contact_role",
    "westBoundLongitude", "eastBoundLongitude", "southBoundLatitude", "northBoundLatitude",
    "dateStamp", "date_creation"
];

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

    return {
        title:                           get("title"),
        edition:                         get("edition") || "1",
        abstract:                        get("abstract"),
        MD_Keywords:                     keywords,
        spatialResolution_denominator:   get("spatialResolution_denominator"),
        thumbnail_url:                   get("thumbnail_url"),
        status_codeListValue:            get("status_codeListValue"),
        MD_SpatialRepresentationTypeCode: get("MD_SpatialRepresentationTypeCode"),
        LanguageCode:                    get("LanguageCode") || "por",
        characterSet:                    get("characterSet") || "utf8",
        topicCategory:                   get("topicCategory"),
        hierarchyLevel:                  get("hierarchyLevel") || "dataset",
        contact_individualName:          get("contact_individualName"),
        contact_organisationName:        get("contact_organisationName"),
        contact_positionName:            get("contact_positionName"),
        contact_phone:                   get("contact_phone"),
        contact_deliveryPoint:           get("contact_deliveryPoint"),
        contact_city:                    get("contact_city"),
        contact_administrativeArea:      get("contact_administrativeArea"),
        contact_postalCode:              get("contact_postalCode"),
        contact_country:                 get("contact_country") || "Brasil",
        contact_email:                   get("contact_email"),
        contact_role:                    get("contact_role"),
        westBoundLongitude:              get("westBoundLongitude"),
        eastBoundLongitude:              get("eastBoundLongitude"),
        southBoundLatitude:              get("southBoundLatitude"),
        northBoundLatitude:              get("northBoundLatitude"),
        dateStamp:                       get("dateStamp"),
        date_creation:                   get("date_creation")
    };
}

var REQUIRED_LABELS = {
    title:                            "Título",
    abstract:                         "Resumo",
    MD_Keywords:                      "Palavras-chave",
    status_codeListValue:             "Status",
    MD_SpatialRepresentationTypeCode: "Tipo de Representação Espacial",
    LanguageCode:                     "Idioma",
    topicCategory:                    "Categoria Temática",
    hierarchyLevel:                   "Nível Hierárquico",
    contact_individualName:           "Sigla (Contato)",
    contact_organisationName:         "Organização (Contato)",
    contact_deliveryPoint:            "Endereço (Contato)",
    contact_city:                     "Cidade (Contato)",
    contact_administrativeArea:       "Estado (Contato)",
    contact_postalCode:               "CEP (Contato)",
    contact_email:                    "E-mail (Contato)",
    contact_country:                  "País (Contato)",
    contact_role:                     "Responsabilidade (Contato)",
    westBoundLongitude:               "Longitude Oeste",
    eastBoundLongitude:               "Longitude Leste",
    southBoundLatitude:               "Latitude Sul",
    northBoundLatitude:               "Latitude Norte"
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
    return missing;
}

function showValidationError(missing) {
    alert("Preencha os campos obrigatórios:\n• " + missing.join("\n• "));
}

function populateForm(data) {
    if (!data) return;
    FORM_FIELDS.forEach(function (key) {
        var el = document.getElementById("f-" + key);
        if (!el) return;
        var val = data[key];
        if (key === "MD_Keywords" && Array.isArray(val)) val = val.join(", ");
        if (val !== undefined && val !== null) el.value = val;
    });
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
