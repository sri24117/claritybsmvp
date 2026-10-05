"""Load the simple local .env without shell evaluation. Run from project root."""

import os, sys
from pathlib import Path

for line in Path(".env").read_text().splitlines():
    if line.strip() and not line.lstrip().startswith("#"):
        name, _, value = line.partition("=")
        os.environ[name.strip()] = value.strip()
sys.path.insert(0, str(Path.cwd()))
if os.environ.get("ENVIRONMENT") != "development":
    raise SystemExit("This launcher is for a development .env only.")
from app.db import init_db

init_db()
if len(sys.argv) > 1:
    if sys.argv[1] == "worker":
        from app.worker import main

        main()
    else:
        from app.cli import main

        main()
else:
    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, access_log=False)
