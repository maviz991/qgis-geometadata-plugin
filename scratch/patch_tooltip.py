import re
import os

# 1. Update app.js
js_file = 'ui/templates/js/app.js'
with open(js_file, 'r', encoding='utf-8') as f:
    js_content = f.read()

# Replace initGlobalTooltips function
new_tooltip_js = """
// --- Global Tooltip Logic ---
var _globalTooltip = null;
var _tooltipTimeout = null;

function initGlobalTooltips() {
    if (!_globalTooltip) {
        _globalTooltip = document.createElement('div');
        _globalTooltip.className = 'global-tooltip';
        document.body.appendChild(_globalTooltip);
    }

    document.addEventListener('mouseover', function(e) {
        var target = e.target.closest('[data-title]');
        if (!target) return;

        var tipText = target.getAttribute('data-title');
        if (!tipText) return;

        clearTimeout(_tooltipTimeout);
        
        _tooltipTimeout = setTimeout(function() {
            _globalTooltip.textContent = tipText;
            _globalTooltip.classList.add('visible');

            // Force reflow to get correct dimensions
            void _globalTooltip.offsetWidth;

            var rect = target.getBoundingClientRect();
            var tooltipRect = _globalTooltip.getBoundingClientRect();
            
            var top = rect.bottom + 8;
            var left = rect.left + (rect.width / 2) - (tooltipRect.width / 2);
            var arrowClass = 'arrow-up';

            if (left < 10) left = 10;
            if (left + tooltipRect.width > window.innerWidth - 10) {
                left = window.innerWidth - tooltipRect.width - 10;
            }
            
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

        }, 600); // 600ms delay before showing
    });

    document.addEventListener('mouseout', function(e) {
        var target = e.target.closest('[data-title]');
        if (target) {
            clearTimeout(_tooltipTimeout);
            _globalTooltip.classList.remove('visible');
        }
    });
    
    document.addEventListener('mousedown', function() {
        clearTimeout(_tooltipTimeout);
        if (_globalTooltip) _globalTooltip.classList.remove('visible');
    });
}
"""

# Extract everything before and after initGlobalTooltips
pattern = re.compile(r'// --- Global Tooltip Logic ---.*?(?=// --- Custom Select Logic ---)', re.DOTALL)
js_content = pattern.sub(new_tooltip_js, js_content)

with open(js_file, 'w', encoding='utf-8') as f:
    f.write(js_content)


# 2. Update styles.css
css_file = 'ui/templates/css/styles.css'
with open(css_file, 'r', encoding='utf-8') as f:
    css_content = f.read()

# Replace custom-select-dropdown gap
old_dropdown_css = """.custom-select-dropdown {
    /* Uses .search-suggestions styling but we force some defaults */
    position: absolute;
    top: calc(100% + 4px);"""
new_dropdown_css = """.custom-select-dropdown {
    /* Uses .search-suggestions styling but we force some defaults */
    position: absolute;
    top: calc(100% - 1px); /* Overlap border */
    margin-top: 0;"""
css_content = css_content.replace(old_dropdown_css, new_dropdown_css)

# Update global-tooltip and add arrow CSS
old_tooltip_css = """.global-tooltip {
    position: fixed;
    z-index: 9999;
    pointer-events: none;
    background: #1e293b;
    color: #f8fafc;
    padding: 8px 12px;
    border-radius: 6px;
    font-size: 12px;
    line-height: 1.4;
    max-width: 250px;
    box-shadow: 0 4px 12px rgba(0,0,0,0.25);
    opacity: 0;
    transition: opacity 0.2s ease;
    text-transform: none;
    font-weight: 500;
}

.global-tooltip.visible {
    opacity: 1;
}"""

new_tooltip_css = """.global-tooltip {
    position: fixed;
    z-index: 9999;
    pointer-events: none;
    background: #1e293b;
    color: #f8fafc;
    padding: 8px 12px;
    border-radius: 6px;
    font-size: 12px;
    line-height: 1.4;
    max-width: 250px;
    box-shadow: 0 4px 12px rgba(0,0,0,0.25);
    opacity: 0;
    transition: opacity 0.2s ease, transform 0.2s ease;
    transform: translateY(4px);
    text-transform: none;
    font-weight: 500;
}

.global-tooltip.visible {
    opacity: 1;
    transform: translateY(0);
}

.global-tooltip::after {
    content: '';
    position: absolute;
    width: 0;
    height: 0;
    border-style: solid;
}

.global-tooltip[data-arrow="arrow-up"]::after {
    top: -6px;
    left: var(--arrow-pos, 50%);
    margin-left: -6px;
    border-width: 0 6px 6px 6px;
    border-color: transparent transparent #1e293b transparent;
}

.global-tooltip[data-arrow="arrow-down"]::after {
    bottom: -6px;
    left: var(--arrow-pos, 50%);
    margin-left: -6px;
    border-width: 6px 6px 0 6px;
    border-color: #1e293b transparent transparent transparent;
}"""

css_content = css_content.replace(old_tooltip_css, new_tooltip_css)

with open(css_file, 'w', encoding='utf-8') as f:
    f.write(css_content)

print("Patch applied to app.js and styles.css")
