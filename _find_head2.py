import re, os
base = "backend/alembic/versions"
files = sorted(f for f in os.listdir(base) if f.endswith(".py") and not f.startswith("__"))
for f in files:
    with open(os.path.join(base, f), encoding="utf-8") as fh:
        content = fh.read()
    rev = re.search(r"revision[ =]+['\"]([^'\"]+)['\"]", content)
    down = re.search(r"down_revision[ =]+['\"]([^'\"]+)['\"]", content)
    rv = rev.group(1) if rev else "???"
    dr = down.group(1) if down else "None"
    print(f"{f:55s}  rev: {rv:25s}  down: {dr}")
