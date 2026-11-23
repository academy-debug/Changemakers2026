import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

load_dotenv(BASE_DIR / ".env")

ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "changeme123")
SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key-change-in-production")
_raw_db_url = os.getenv("DATABASE_URL", f"sqlite:///{BASE_DIR / 'data' / 'capstone.db'}")
if _raw_db_url.startswith("postgresql://"):
    DATABASE_URL = _raw_db_url.replace("postgresql://", "postgresql+psycopg://", 1)
else:
    DATABASE_URL = _raw_db_url
SHOW_CONTACT_INFO = os.getenv("SHOW_CONTACT_INFO", "true").lower() == "true"
RATE_LIMIT_PER_MINUTE = int(os.getenv("RATE_LIMIT_PER_MINUTE", "10"))
BACKUP_DIR = BASE_DIR / "backups"
DATA_DIR = BASE_DIR / "data"
CONTENT_DIR = BASE_DIR / "content"
