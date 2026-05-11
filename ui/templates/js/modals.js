/**
 * Modal System for GeoMetadata Plugin
 * Replaces native alert() and confirm() with custom premium UI
 */

var Modal = (function() {
    
    function init() {
        if (document.getElementById('modal-overlay')) return;
        
        var html = 
            '<div id="modal-overlay" class="modal-overlay">' +
            '  <div class="modal-container">' +
            '    <div class="modal-header">' +
            '      <h3 id="modal-title">Aviso</h3>' +
            '      <button class="modal-close" onclick="Modal.close()">&times;</button>' +
            '    </div>' +
            '    <div class="modal-body" id="modal-body"></div>' +
            '    <div class="modal-footer" id="modal-footer"></div>' +
            '  </div>' +
            '</div>';
            
        document.body.insertAdjacentHTML('beforeend', html);
    }

    function show(options) {
        init();
        
        var overlay = document.getElementById('modal-overlay');
        var titleEl = document.getElementById('modal-title');
        var bodyEl = document.getElementById('modal-body');
        var footerEl = document.getElementById('modal-footer');
        
        titleEl.textContent = options.title || 'Aviso';
        
        // Handle icons/type
        var iconHtml = '';
        if (options.type) {
            var iconClass = 'modal-icon-' + options.type;
            var iconChar = '!';
            if (options.type === 'success') iconChar = '✓';
            if (options.type === 'info') iconChar = 'i';
            if (options.type === 'error') iconChar = '✕';
            
            iconHtml = '<div class="modal-type-icon ' + iconClass + '">' + iconChar + '</div>';
        }
        
        if (iconHtml) {
            bodyEl.innerHTML = '<div class="modal-body-with-icon">' + iconHtml + '<div>' + options.message + '</div></div>';
        } else {
            bodyEl.innerHTML = options.message;
        }
        
        // Buttons
        footerEl.innerHTML = '';
        if (options.buttons) {
            options.buttons.forEach(function(btn) {
                var b = document.createElement('button');
                b.className = 'btn-modal ' + (btn.primary ? 'btn-modal-primary' : 'btn-modal-secondary');
                b.textContent = btn.label;
                b.onclick = function() {
                    if (btn.onClick) btn.onClick();
                    if (!btn.preventClose) close();
                };
                footerEl.appendChild(b);
            });
        } else {
            // Default OK button
            var okBtn = document.createElement('button');
            okBtn.className = 'btn-modal btn-modal-primary';
            okBtn.textContent = 'OK';
            okBtn.onclick = close;
            footerEl.appendChild(okBtn);
        }
        
        overlay.classList.add('active');
        
        // Focus first primary button
        setTimeout(function() {
            var primary = footerEl.querySelector('.btn-modal-primary');
            if (primary) primary.focus();
        }, 100);
    }

    function close() {
        var overlay = document.getElementById('modal-overlay');
        if (overlay) overlay.classList.remove('active');
    }

    // Replace global alert
    function alert(message, title, type) {
        show({
            title: title || 'Aviso',
            message: message.replace(/\n/g, '<br>'),
            type: type || 'info'
        });
    }

    // Confirm dialog
    function confirm(message, onConfirm, title) {
        show({
            title: title || 'Confirmar',
            message: message,
            type: 'warning',
            buttons: [
                { label: 'Cancelar', primary: false, onClick: null },
                { label: 'Confirmar', primary: true, onClick: onConfirm }
            ]
        });
    }

    return {
        show: show,
        close: close,
        alert: alert,
        confirm: confirm
    };
})();

// Redefine window.alert if needed, but safer to use Modal.alert
// window.alert = Modal.alert; 
