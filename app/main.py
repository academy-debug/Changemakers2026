import shutil
from datetime import datetime
from pathlib import Path
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from app.config import SECRET_KEY, BASE_DIR, BACKUP_DIR, DATA_DIR
from app.database import init_db


def daily_backup():
    db_path = DATA_DIR / "capstone.db"
    if not db_path.exists():
        return
    BACKUP_DIR.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d")
    dest = BACKUP_DIR / f"capstone_{stamp}.db"
    if not dest.exists():
        shutil.copy2(db_path, dest)

    backups = sorted(BACKUP_DIR.glob("capstone_*.db"), reverse=True)
    for old in backups[7:]:
        old.unlink()


@asynccontextmanager
async def lifespan(app: FastAPI):
    DATA_DIR.mkdir(exist_ok=True)
    init_db()
    daily_backup()
    yield


app = FastAPI(title="AI Changemakers 100x100", lifespan=lifespan)

app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY, max_age=86400 * 30)

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
templates.env.globals["now"] = datetime.utcnow
app.state.templates = templates

from app.routes.student import router as student_router
from app.routes.admin import router as admin_router

app.include_router(student_router)
app.include_router(admin_router)


@app.exception_handler(404)
async def not_found(request: Request, exc):
    return templates.TemplateResponse("404.html", {"request": request}, status_code=404)
