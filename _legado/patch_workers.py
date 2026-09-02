with open("ui/geoserver_workers.py", "r", encoding="utf-8") as f:
    content = f.read()

# Insert dummy print function after imports
if "def print(*args, **kwargs):" not in content:
    import_block_end = content.find("except ImportError:")
    import_block_end = content.find("\n", import_block_end)
    import_block_end = content.find("\n", import_block_end + 1)
    
    dummy_print = """
# Overrides built-in print for this module to prevent QGIS segfaults from background threads
def print(*args, **kwargs):
    pass
"""
    content = content[:import_block_end] + dummy_print + content[import_block_end:]
    
    with open("ui/geoserver_workers.py", "w", encoding="utf-8") as f:
        f.write(content)
