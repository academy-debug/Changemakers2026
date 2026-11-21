import argparse
import shutil
from datetime import datetime
from pathlib import Path

from app.config import BACKUP_DIR, DATA_DIR
from app.database import SessionLocal, init_db
from app.import_data import import_excel, print_report


def cmd_import(args):
    init_db()
    db = SessionLocal()
    try:
        report = import_excel(db, args.file, args.track)
        print_report(report, args.track)
    finally:
        db.close()


def cmd_backup(args):
    db_path = DATA_DIR / "capstone.db"
    if not db_path.exists():
        print("Өгөгдлийн сан олдсонгүй.")
        return
    BACKUP_DIR.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = BACKUP_DIR / f"capstone_{stamp}.db"
    shutil.copy2(db_path, dest)
    print(f"Нөөцлөлт хийгдлээ: {dest}")


def main():
    parser = argparse.ArgumentParser(description="AI Changemakers 100x100 удирдлагын хэрэгсэл")
    sub = parser.add_subparsers(dest="command")

    p_import = sub.add_parser("import", help="Excel файл импортлох")
    p_import.add_argument("file", help="Excel файлын зам")
    p_import.add_argument("--track", required=True, choices=["professionals", "students"],
                          help="Урсгал: professionals эсвэл students")
    p_import.set_defaults(func=cmd_import)

    p_backup = sub.add_parser("backup", help="Өгөгдлийн сангийн нөөц хуулбар хийх")
    p_backup.set_defaults(func=cmd_backup)

    args = parser.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
