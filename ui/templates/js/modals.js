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
            var svg = '';
            
            if (options.type === 'success') {
                svg = '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg>';
            } else if (options.type === 'error') {
                svg = '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>';
            } else if (options.type === 'warning') {
                svg = '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path><line x1="12" y1="9" x2="12" y2="13"></line><line x1="12" y1="17" x2="12.01" y2="17"></line></svg>';
            } else if (options.type === 'info') {
                svg = '<svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="16" x2="12" y2="12"></line><line x1="12" y1="8" x2="12.01" y2="8"></line></svg>';
            }
            
            iconHtml = '<div class="modal-type-icon ' + iconClass + '">' + svg + '</div>';
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
