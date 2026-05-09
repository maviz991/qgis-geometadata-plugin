/* Custom Selects and Global Tooltips */

// --- Global Tooltip Logic ---
var _globalTooltip = null;

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

        _globalTooltip.textContent = tipText;
        _globalTooltip.classList.add('visible');

        var rect = target.getBoundingClientRect();
        
        // Position below by default
        var top = rect.bottom + 6;
        var left = rect.left + (rect.width / 2) - (_globalTooltip.offsetWidth / 2);

        // Adjust if out of bounds
        if (left < 10) left = 10;
        if (left + _globalTooltip.offsetWidth > window.innerWidth - 10) {
            left = window.innerWidth - _globalTooltip.offsetWidth - 10;
        }
        
        // If it goes off the bottom, position above
        if (top + _globalTooltip.offsetHeight > window.innerHeight - 10) {
            top = rect.top - _globalTooltip.offsetHeight - 6;
        }

        _globalTooltip.style.top = top + 'px';
        _globalTooltip.style.left = left + 'px';
    });

    document.addEventListener('mouseout', function(e) {
        var target = e.target.closest('[data-title]');
        if (target) {
            _globalTooltip.classList.remove('visible');
        }
    });
    
    // Hide on click to prevent sticky tooltips
    document.addEventListener('mousedown', function() {
        if (_globalTooltip) _globalTooltip.classList.remove('visible');
    });
}

// --- Custom Select Logic ---
function initCustomSelects() {
    var selects = document.querySelectorAll('select:not(.custom-select-initialized)');
    
    selects.forEach(function(select) {
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
        arrowSpan.innerHTML = '&#9662;'; // Down arrow

        trigger.appendChild(valueSpan);
        trigger.appendChild(arrowSpan);
        wrapper.appendChild(trigger);

        var dropdown = document.createElement('div');
        dropdown.className = 'search-suggestions custom-select-dropdown';
        
        // Populate options
        var optionsHtml = '';
        var selectedText = '- Selecione -';
        
        Array.from(select.options).forEach(function(opt, idx) {
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
            document.querySelectorAll('.custom-select.open').forEach(function(el) {
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

        trigger.addEventListener('click', function(e) {
            e.stopPropagation();
            if (isOpen) closeDropdown();
            else openDropdown();
        });

        // Click on items
        dropdown.addEventListener('click', function(e) {
            e.stopPropagation();
            var item = e.target.closest('.suggestion-item');
            if (!item) return;

            var idx = item.getAttribute('data-index');
            select.selectedIndex = idx;
            valueSpan.textContent = item.textContent;
            
            // Update active class
            dropdown.querySelectorAll('.suggestion-item').forEach(function(el) { el.classList.remove('active'); });
            item.classList.add('active');
            
            closeDropdown();
            
            // Trigger native change event so other scripts know
            var event = new Event('change', { bubbles: true });
            select.dispatchEvent(event);
        });

        // Click outside closes
        document.addEventListener('click', function(e) {
            if (isOpen && !wrapper.contains(e.target)) {
                closeDropdown();
            }
        });

        // Keyboard navigation
        var searchString = '';
        var searchTimeout = null;

        wrapper.addEventListener('keydown', function(e) {
            if (e.key === 'Tab') {
                closeDropdown();
                return;
            }
            
            e.preventDefault(); // Prevent page scroll for arrows

            var items = Array.from(dropdown.querySelectorAll('.suggestion-item'));
            var activeIdx = items.findIndex(function(item) { return item.classList.contains('active'); });

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
                
                searchTimeout = setTimeout(function() {
                    searchString = '';
                }, 1000);

                var matchIdx = items.findIndex(function(item) {
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
        select.addEventListener('change', function() {
            var selectedOpt = select.options[select.selectedIndex];
            if (selectedOpt) {
                valueSpan.textContent = selectedOpt.text;
                dropdown.querySelectorAll('.suggestion-item').forEach(function(el) {
                    el.classList.toggle('active', el.getAttribute('data-value') === selectedOpt.value);
                });
            }
        });
    });
}

document.addEventListener('DOMContentLoaded', function() {
    initGlobalTooltips();
    initCustomSelects();
});
