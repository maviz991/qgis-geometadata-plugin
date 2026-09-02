import re

with open("ui/geoserver_bridge.py", "r", encoding="utf-8") as f:
    lines = f.readlines()

new_lines = []
for line in lines:
    if line.strip().startswith("print("):
        new_lines.append(line.replace("print(", "pass # print("))
    elif "traceback.print_exc()" in line:
        new_lines.append(line.replace("traceback.print_exc()", "pass # traceback.print_exc()"))
    else:
        new_lines.append(line)

with open("ui/geoserver_bridge.py", "w", encoding="utf-8") as f:
    f.writelines(new_lines)
