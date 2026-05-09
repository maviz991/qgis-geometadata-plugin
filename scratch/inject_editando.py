import os
import re

filepath = 'editando.html'

with open('scratch/custom_selects.js', 'r', encoding='utf-8') as f:
    js_content = f.read()

with open('scratch/custom_selects.css', 'r', encoding='utf-8') as f:
    css_content = f.read()

with open(filepath, 'r', encoding='utf-8') as f:
    html = f.read()

# Insert CSS right before </head> or </style>
if '</head>' in html:
    html = html.replace('</head>', f'<style>\n{css_content}\n</style>\n</head>')
else:
    # Append style
    html += f'\n<style>\n{css_content}\n</style>\n'

# Insert JS right before </body>
if '</body>' in html:
    html = html.replace('</body>', f'<script>\n{js_content}\n</script>\n</body>')
else:
    html += f'\n<script>\n{js_content}\n</script>\n'

with open(filepath, 'w', encoding='utf-8') as f:
    f.write(html)
print("Injected custom selects into editando.html")
