// docs.js - manual do Geohab Plugin
// ===================================
// Redimensiona cada iframe de .doc-mockup pra altura real do conteúdo dele, em vez de
// um valor fixo chutado por página (isso já saiu errado mais de uma vez).
//
// Usa postMessage (não contentDocument.scrollHeight direto) de propósito: sob file://
// (preview local, antes de subir pro MinIO), navegadores baseados em Chromium bloqueiam
// acesso de script a contentDocument entre documentos file:// por padrão, mesmo vindo da
// mesma pasta - a tentativa falha silenciosamente e o iframe fica preso na altura de
// fallback do CSS. postMessage não tem essa restrição (funciona em file:// e em
// http(s) igual), então cada mockup (ver o <script> no fim de
// vendor_mockups/ui/templates/mockup-*.html) mede a própria altura e AVISA o pai via
// postMessage, em vez do pai tentar ler direto.
window.addEventListener('message', function (event) {
    var data = event.data;
    if (!data || typeof data.docMockupHeight !== 'number') return;
    var iframes = document.querySelectorAll('.doc-mockup iframe');
    for (var i = 0; i < iframes.length; i++) {
        if (iframes[i].contentWindow === event.source) {
            iframes[i].style.height = data.docMockupHeight + 'px';
            break;
        }
    }
});
