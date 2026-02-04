# passenger_wsgi.py (tiler)
import os, sys, glob

BASE = "/usr/local/usrapps/drones/drone-data-viewer/drone-tiling-server"
VENV = os.path.join(BASE, ".venv")

# Add venv site-packages to sys.path (works even if Passenger runs /bin/python)
candidates = glob.glob(os.path.join(VENV, "lib", "python*", "site-packages"))
if candidates and candidates[0] not in sys.path:
    sys.path.insert(0, candidates[0])

# Add repo root to sys.path so "import main" works
if BASE not in sys.path:
    sys.path.insert(0, BASE)

# Mimic venv activation env vars (helps some libs that inspect VIRTUAL_ENV/PATH)
os.environ["VIRTUAL_ENV"] = VENV
os.environ["PATH"] = os.path.join(VENV, "bin") + ":" + os.environ.get("PATH", "")

# App env
os.environ.setdefault("ENVIRONMENT", "prod")
os.environ.setdefault("COG_STORAGE_PATH", "/rs1/shares/cals-research-station")
os.environ.setdefault("ALLOWED_ORIGINS", "https://servood.hpc.ncsu.edu")
os.environ.setdefault("DEFAULT_CACHE_CONTROL", "public, max-age=3600")

# If you ever need writable dirs (optional)
HOME = os.path.expanduser("~")
os.environ.setdefault("TILER_LOG_DIR", os.path.join(HOME, "ondemand", "data", "tiler", "logs"))
os.makedirs(os.environ["TILER_LOG_DIR"], exist_ok=True)

# --- ASGI -> WSGI adapter ---
from a2wsgi import ASGIMiddleware
from main import app as asgi_app

application = ASGIMiddleware(asgi_app)
