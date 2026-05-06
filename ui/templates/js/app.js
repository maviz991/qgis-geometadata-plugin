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
    // QWebChannel usa callbacks, não Promises — await não funciona aqui
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
}

function navigate(panelId) {
    bridge.navigate(panelId);
    loadPanel(panelId);
}

function loadPanel(panelId) {
    var container = document.getElementById("app-container");
    container.innerHTML = '<div class="loader">Carregando...</div>';

    // fetch() é bloqueado para file:// — Python lê o arquivo via bridge
    bridge.load_panel_html(panelId, function (html) {
        container.innerHTML = html;
        onPanelLoaded(panelId);
    });
}

function onPanelLoaded(panelId) {
    console.log("Painel " + panelId + " renderizado.");
}

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
