import re
import unicodedata
from pathlib import Path
from datetime import date

import openpyxl
from sqlalchemy.orm import Session

from app.models import Learner, Team, PresentationSlot, TrackEnum


def normalize_header(val):
    if not val:
        return ""
    s = str(val).strip()
    s = s.replace("С", "С").replace("с", "с")
    s = s.replace("C", "С").replace("c", "с")
    s = s.lower().strip()
    s = re.sub(r"\s+", " ", s)
    return s


HEADER_ALIASES = {
    "суралцагчийн код": "code",
    "cуралцагчийн код": "code",
    "#": "row_num",
    "ажлын туршлага жилээр": "experience",
    "ажлын газар": "workplace",
    "албан тушаал": "position",
    "хэлний оноо": "language_score",
    "асуулт 1 (өөрийгөө танилцуулах)": "_skip",
    "асуулт 2 (зорилго)": "_skip",
    "асуулт 3 (бэрхшээл)": "_skip",
    "асуулт 4 (ai-аар шийдэх асуудал)": "_skip",
    "асуулт 5 (мотиваци)": "_skip",
    "баг": "team",
    "багийн дугаар": "team",
    "баг №": "team",
    "яагаад энэ багт орсон, ямар зорилго нь ижил байсан": "team_reason_raw",
    "багт орсон шалтгаан": "team_reason_raw",
    "овог": "surname",
    "нэр": "first_name",
    "овог нэр": "full_name",
    "утас": "phone",
    "хаанаас": "origin",
    "имэйл": "email",
    "нас": "_skip",
    "хүйс": "_skip",
    "боловсрол": "_skip",
    "магистрант эсэх": "_skip",
    "олимпиад / тэтгэлэг": "_skip",
    "голч": "_skip",
    "сурдаг сургууль": "workplace",
    "сурдаг чиглэл курс": "position",
    "багийн сэдэв": "team_topic",
    "багийн чиглэл": "team_topic",
    "гишүүдийн тоо": "_skip",
    "гишүүд (код)": "member_codes",
    "гишүүд": "member_codes",
    "ижил зорилго": "shared_goal",
    "багийн нийтлэг зорилго": "shared_goal",
    "гишүүдийн мэргэжил": "_skip",
    "date": "slot_date",
    "time": "slot_time",
    "module": "_skip",
    "session and topic": "session_name",
}


def map_headers(ws):
    header_map = {}
    for cell in ws[1]:
        if cell.value is None:
            continue
        norm = normalize_header(cell.value)
        raw_lower = str(cell.value).strip().lower()
        for alias_key, field_name in HEADER_ALIASES.items():
            alias_norm = normalize_header(alias_key)
            if norm == alias_norm or alias_key.lower() == raw_lower:
                header_map[cell.column] = field_name
                break
            if len(alias_norm) > 4 and (norm.startswith(alias_norm) or alias_norm.startswith(norm)):
                header_map[cell.column] = field_name
                break
    return header_map


def clean_phone(val):
    if not val:
        return None
    s = str(val).strip()
    s = re.sub(r"[^\d]", "", s)
    if s.startswith("976") and len(s) == 11:
        s = s[3:]
    if len(s) == 8:
        return s
    return s if s else None


def clean_email(val):
    if not val:
        return None
    return str(val).strip().lower()


def parse_team_number(val):
    if not val:
        return None
    m = re.search(r"(\d+)", str(val))
    return int(m.group(1)) if m else None


def parse_team_reason(raw_text):
    if not raw_text:
        return {"topic": "", "reason": "", "shared_goal": ""}
    text = str(raw_text)
    result = {"topic": "", "reason": "", "shared_goal": ""}

    topic_match = re.search(r"[Бб]агийн сэдэв:\s*(.+?)(?:\n|$)", text)
    if topic_match:
        result["topic"] = topic_match.group(1).strip()

    reason_match = re.search(r"[Яя]агаад энэ багт орсон:\s*(.+?)(?:\n|$)", text)
    if reason_match:
        result["reason"] = reason_match.group(1).strip()

    goal_match = re.search(r"[Ии]жил зорилго:\s*(.+?)(?:\n|$)", text)
    if goal_match:
        result["shared_goal"] = goal_match.group(1).strip()

    return result


def parse_slot_capacity(session_name):
    if not session_name:
        return 5
    m = re.search(r"(\d+)\s*[Бб]аг", str(session_name))
    return int(m.group(1)) if m else 5


def parse_slot_date(date_str):
    if not date_str:
        return None
    m = re.match(r"\w+\s+(\d+)\s+(\w+)", str(date_str).strip())
    if not m:
        return None
    day = int(m.group(1))
    month_str = m.group(2).lower()
    months = {
        "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
        "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
    }
    month = months.get(month_str[:3])
    if not month:
        return None
    return date(2026, month, day)


def import_excel(db: Session, filepath: str, track: str) -> dict:
    track_enum = TrackEnum(track)
    wb = openpyxl.load_workbook(filepath, data_only=True)
    report = {
        "learners_imported": 0,
        "teams_imported": 0,
        "slots_imported": 0,
        "no_phone": [],
        "no_email": [],
        "duplicate_phones": [],
        "duplicate_emails": [],
        "unusual_team_size": [],
        "warnings": [],
    }

    ws_members = None
    ws_teams = None
    ws_schedule = None
    ws_contact = None

    for name in wb.sheetnames:
        lower = name.lower().strip()
        if "хуваагдсан" in lower or "хуваасан" in lower:
            ws_members = wb[name]
        elif lower == "багууд":
            ws_teams = wb[name]
        elif "танилцуулах" in lower or "төсөл" in lower:
            ws_schedule = wb[name]
        elif "phone" in lower or "email" in lower:
            ws_contact = wb[name]

    teams_data = {}
    if ws_teams:
        hmap = map_headers(ws_teams)
        for row in ws_teams.iter_rows(min_row=2, values_only=False):
            vals = {hmap.get(c.column): c.value for c in row if hmap.get(c.column)}
            team_name = vals.get("team", "")
            if not team_name or "нийт" in str(team_name).lower():
                continue
            num = parse_team_number(team_name)
            if num is None:
                continue
            teams_data[num] = {
                "topic": str(vals.get("team_topic", "") or ""),
                "shared_goal": str(vals.get("shared_goal", "") or ""),
            }

    for num, tdata in teams_data.items():
        existing = db.query(Team).filter_by(number=num, track=track_enum).first()
        if existing:
            existing.topic = tdata["topic"]
            existing.shared_goal = tdata["shared_goal"]
        else:
            team = Team(number=num, track=track_enum, topic=tdata["topic"], shared_goal=tdata["shared_goal"])
            db.add(team)
        report["teams_imported"] += 1
    db.flush()

    contact_data = {}
    if ws_contact:
        hmap = map_headers(ws_contact)

        code_col = None
        for cell in ws_contact[1]:
            if cell.value is None and cell.column not in hmap:
                code_col = cell.column
                break
        if code_col is None:
            max_col = ws_contact.max_column
            if max_col not in hmap:
                code_col = max_col

        for row in ws_contact.iter_rows(min_row=2, values_only=False):
            vals = {}
            for c in row:
                field = hmap.get(c.column)
                if field and field != "_skip":
                    vals[field] = c.value
                elif c.column == code_col and c.value:
                    vals["code"] = str(c.value).strip()
                elif c.value and not field:
                    candidate = str(c.value).strip()
                    if re.match(r"[A-Za-z]+\d+", candidate):
                        vals["code"] = candidate

            code = vals.get("code")
            if not code:
                continue
            contact_data[code] = {
                "surname": str(vals.get("surname", "") or "").strip(),
                "first_name": str(vals.get("first_name", "") or "").strip(),
                "phone": clean_phone(vals.get("phone")),
                "email": clean_email(vals.get("email")),
                "origin": str(vals.get("origin", "") or "").strip(),
            }

    if ws_members:
        hmap = map_headers(ws_members)
        for row in ws_members.iter_rows(min_row=2, values_only=False):
            vals = {hmap.get(c.column): c.value for c in row if hmap.get(c.column)}
            code = vals.get("code")
            if not code:
                continue
            code = str(code).strip()
            if not code:
                continue

            team_num = parse_team_number(vals.get("team"))
            team = db.query(Team).filter_by(number=team_num, track=track_enum).first() if team_num else None

            parsed_reason = parse_team_reason(vals.get("team_reason_raw"))

            contact = contact_data.get(code, {})

            existing = db.query(Learner).filter_by(code=code, track=track_enum).first()
            if existing:
                existing.workplace = str(vals.get("workplace", "") or "").strip() or existing.workplace
                existing.position = str(vals.get("position", "") or "").strip() or existing.position
                existing.experience = str(vals.get("experience", "") or "").strip() or existing.experience
                existing.language_score = str(vals.get("language_score", "") or "").strip() or existing.language_score
                existing.team_id = team.id if team else existing.team_id
                existing.team_reason = parsed_reason.get("reason", "") or existing.team_reason
                if contact:
                    existing.surname = contact.get("surname") or existing.surname
                    existing.first_name = contact.get("first_name") or existing.first_name
                    existing.phone = contact.get("phone") or existing.phone
                    existing.email = contact.get("email") or existing.email
                    existing.origin = contact.get("origin") or existing.origin
            else:
                learner = Learner(
                    code=code,
                    track=track_enum,
                    surname=contact.get("surname", ""),
                    first_name=contact.get("first_name", ""),
                    workplace=str(vals.get("workplace", "") or "").strip(),
                    position=str(vals.get("position", "") or "").strip(),
                    experience=str(vals.get("experience", "") or "").strip(),
                    language_score=str(vals.get("language_score", "") or "").strip(),
                    phone=contact.get("phone"),
                    email=contact.get("email"),
                    origin=contact.get("origin", ""),
                    team_id=team.id if team else None,
                    team_reason=parsed_reason.get("reason", ""),
                )
                db.add(learner)
            report["learners_imported"] += 1
    db.flush()

    if ws_schedule:
        hmap = map_headers(ws_schedule)
        for row in ws_schedule.iter_rows(min_row=2, values_only=False):
            vals = {hmap.get(c.column): c.value for c in row if hmap.get(c.column)}
            date_str = vals.get("slot_date")
            if not date_str:
                continue
            slot_date = parse_slot_date(date_str)
            if not slot_date:
                report["warnings"].append(f"Огноо задлагдсангүй: {date_str}")
                continue

            time_str = str(vals.get("slot_time", "") or "")
            parts = re.split(r"\s*\|\s*", time_str)
            time_start = parts[0].strip() if parts else "19:00"
            time_end = parts[1].strip() if len(parts) > 1 else "20:30"

            session_name = str(vals.get("session_name", "") or "")
            capacity = parse_slot_capacity(session_name)

            existing = db.query(PresentationSlot).filter_by(
                track=track_enum, slot_date=slot_date
            ).first()
            if existing:
                existing.time_start = time_start
                existing.time_end = time_end
                existing.session_name = session_name
                if not existing.capacity or existing.capacity == 5:
                    existing.capacity = capacity
            else:
                slot = PresentationSlot(
                    track=track_enum,
                    slot_date=slot_date,
                    time_start=time_start,
                    time_end=time_end,
                    session_name=session_name,
                    capacity=capacity,
                )
                db.add(slot)
            report["slots_imported"] += 1
    db.flush()

    seen_phones = {}
    seen_emails = {}
    all_learners = db.query(Learner).filter_by(track=track_enum).all()
    for l in all_learners:
        if not l.phone:
            report["no_phone"].append(l.code)
        else:
            if l.phone in seen_phones:
                report["duplicate_phones"].append((l.phone, l.code, seen_phones[l.phone]))
            seen_phones[l.phone] = l.code

        if not l.email:
            report["no_email"].append(l.code)
        else:
            if l.email in seen_emails:
                report["duplicate_emails"].append((l.email, l.code, seen_emails[l.email]))
            seen_emails[l.email] = l.code

    all_teams = db.query(Team).filter_by(track=track_enum).all()
    for t in all_teams:
        member_count = len(t.members)
        if member_count < 4 or member_count > 5:
            report["unusual_team_size"].append((t.display_name, member_count))

    db.commit()
    return report


def print_report(report: dict, track: str):
    print(f"\n{'='*50}")
    print(f"Импортын тайлан: {track}")
    print(f"{'='*50}")
    print(f"Суралцагч: {report['learners_imported']}")
    print(f"Баг: {report['teams_imported']}")
    print(f"Танилцуулгын слот: {report['slots_imported']}")

    if report["no_phone"]:
        print(f"\nУтасгүй ({len(report['no_phone'])}): {', '.join(report['no_phone'][:10])}")
    if report["no_email"]:
        print(f"Имэйлгүй ({len(report['no_email'])}): {', '.join(report['no_email'][:10])}")
    if report["duplicate_phones"]:
        print(f"\nДавхардсан утас:")
        for phone, code1, code2 in report["duplicate_phones"]:
            print(f"  {phone}: {code1}, {code2}")
    if report["duplicate_emails"]:
        print(f"\nДавхардсан имэйл:")
        for email, code1, code2 in report["duplicate_emails"]:
            print(f"  {email}: {code1}, {code2}")
    if report["unusual_team_size"]:
        print(f"\n4-5 хүнээс өөр хэмжээтэй баг:")
        for name, count in report["unusual_team_size"]:
            print(f"  {name}: {count} гишүүн")
    if report["warnings"]:
        print(f"\nАнхааруулга:")
        for w in report["warnings"]:
            print(f"  {w}")
    print()
