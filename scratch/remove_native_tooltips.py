import os
import re

files = [
    'ui/templates/panels/editor.html',
    'editando.html'
]

for filepath in files:
    if not os.path.exists(filepath):
        continue
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # Replace title="..." with data-title="..."
    # This disables the native yellow OS tooltips that overlap with custom UI
    content = re.sub(r'\btitle="([^"]*)"', r'data-title="\1"', content)

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"Removed native tooltips from {filepath}")
