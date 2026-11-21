import io
from datetime import datetime, timedelta, date

from fastapi import APIRouter, Request, Depends, Form, HTTPException, UploadFile, File
from fastapi.responses import RedirectResponse, StreamingResponse
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func

from app.database import get_db
from app.models import (
    Learner, Team, LeaderVote, Task, TaskStatus,
    PresentationSlot, Announcement, AuditLog, TrackEnum,
)
from app.config import ADMIN_PASSWORD
from app.auth import get_client_ip

router = APIRouter(prefix="/admin")


def require_admin(request: Request):
    if not request.session.get("is_admin"):
        raise HTTPException(status_code=302, headers={"Location": "/admin/login"})


@router.get("/login")
async def admin_login_page(request: Request):
    if request.session.get("is_admin"):
        return RedirectResponse(url="/admin", status_code=302)
    return request.app.state.templates.TemplateResponse("admin/login.html", {
        "request": request, "error": None,
    })


@router.post("/login")
async def admin_login_submit(request: Request, password: str = Form(...)):
    if password == ADMIN_PASSWORD:
        request.session["is_admin"] = True
        return RedirectResponse(url="/admin", status_code=302)
    return request.app.state.templates.TemplateResponse("admin/login.html", {
        "request": request, "error": "Нууц үг буруу байна.",
    })


@router.get("/logout")
async def admin_logout(request: Request):
    request.session.pop("is_admin", None)
    return RedirectResponse(url="/admin/login", status_code=302)


@router.get("")
async def admin_dashboard(request: Request, db: Session = Depends(get_db)):
    require_admin(request)

    track_filter = request.query_params.get("track", "")
    step_filter = request.query_params.get("step", "")

    query = db.query(Team).options(
        joinedload(Team.members),
        joinedload(Team.leader),
        joinedload(Team.tasks),
        joinedload(Team.slot),
        joinedload(Team.weekly_updates),
    )
    if track_filter:
        try:
            query = query.filter(Team.track == TrackEnum(track_filter))
        except ValueError:
            pass

    teams = query.order_by(Team.track, Team.number).all()

    if step_filter:
        try:
            step_num = int(step_filter)
            teams = [t for t in teams if t.current_step == step_num]
        except ValueError:
            pass

    total_learners = db.query(Learner).count()
    logged_in_count = db.query(Learner).filter(Learner.last_login_at.isnot(None)).count()

    step_counts = {}
    for t in teams:
        s = t.current_step
        step_counts[s] = step_counts.get(s, 0) + 1

    slots = db.query(PresentationSlot).order_by(PresentationSlot.track, PresentationSlot.slot_date).all()

    three_days_ago = datetime.utcnow() - timedelta(days=3)

    alerts = []
    for t in teams:
        t_alerts = []
        if t.last_activity and t.last_activity < three_days_ago:
            t_alerts.append("inactive")
        if not t.leader_id and t.current_step >= 3:
            t_alerts.append("no_leader")
        if not t.project_name and t.current_step >= 5:
            t_alerts.append("no_project")
        if not t.slot_id and t.current_step >= 8:
            t_alerts.append("no_slot")
        alerts.append((t.id, t_alerts))
    alert_map = dict(alerts)

    return request.app.state.templates.TemplateResponse("admin/dashboard.html", {
        "request": request,
        "teams": teams,
        "total_learners": total_learners,
        "logged_in_count": logged_in_count,
        "step_counts": step_counts,
        "slots": slots,
        "alert_map": alert_map,
        "track_filter": track_filter,
        "step_filter": step_filter,
    })


@router.get("/never-logged")
async def never_logged(request: Request, db: Session = Depends(get_db)):
    require_admin(request)
    learners = db.query(Learner).filter(
        Learner.last_login_at.is_(None)
    ).order_by(Learner.track, Learner.code).all()
    return request.app.state.templates.TemplateResponse("admin/never_logged.html", {
        "request": request,
        "learners": learners,
    })


@router.get("/team/{team_id}")
async def admin_team_detail(request: Request, team_id: int, db: Session = Depends(get_db)):
    require_admin(request)
    team = db.query(Team).options(
        joinedload(Team.members),
        joinedload(Team.leader),
        joinedload(Team.tasks).joinedload(Task.assignee),
        joinedload(Team.votes),
        joinedload(Team.weekly_updates),
        joinedload(Team.slot),
    ).filter_by(id=team_id).first()
    if not team:
        raise HTTPException(404)

    all_teams = db.query(Team).filter_by(track=team.track).order_by(Team.number).all()
    slots = db.query(PresentationSlot).filter_by(track=team.track).order_by(PresentationSlot.slot_date).all()

    return request.app.state.templates.TemplateResponse("admin/team_detail.html", {
        "request": request,
        "team": team,
        "all_teams": all_teams,
        "slots": slots,
    })


@router.post("/team/{team_id}/move-member")
async def move_member(
    request: Request, team_id: int,
    learner_id: int = Form(...),
    new_team_id: int = Form(...),
    db: Session = Depends(get_db),
):
    require_admin(request)
    learner = db.query(Learner).filter_by(id=learner_id).first()
    if not learner:
        raise HTTPException(404)
    learner.team_id = new_team_id
    db.commit()
    return RedirectResponse(url=f"/admin/team/{team_id}", status_code=302)


@router.post("/team/{team_id}/set-leader")
async def set_leader(
    request: Request, team_id: int,
    leader_id: int = Form(...),
    db: Session = Depends(get_db),
):
    require_admin(request)
    team = db.query(Team).filter_by(id=team_id).first()
    if not team:
        raise HTTPException(404)
    team.leader_id = leader_id
    db.commit()
    return RedirectResponse(url=f"/admin/team/{team_id}", status_code=302)


@router.post("/team/{team_id}/set-slot")
async def admin_set_slot(
    request: Request, team_id: int,
    slot_id: int = Form(...),
    db: Session = Depends(get_db),
):
    require_admin(request)
    team = db.query(Team).filter_by(id=team_id).first()
    if not team:
        raise HTTPException(404)
    team.slot_id = slot_id if slot_id else None
    team.slot_confirmed_at = datetime.utcnow() if slot_id else None
    db.commit()
    return RedirectResponse(url=f"/admin/team/{team_id}", status_code=302)


@router.post("/slot/{slot_id}/capacity")
async def update_slot_capacity(
    request: Request, slot_id: int,
    capacity: int = Form(...),
    db: Session = Depends(get_db),
):
    require_admin(request)
    slot = db.query(PresentationSlot).filter_by(id=slot_id).first()
    if not slot:
        raise HTTPException(404)
    slot.capacity = max(1, capacity)
    db.commit()
    return RedirectResponse(url="/admin", status_code=302)


@router.post("/announcement")
async def set_announcement(
    request: Request,
    text: str = Form(""),
    db: Session = Depends(get_db),
):
    require_admin(request)
    db.query(Announcement).update({"active": False})
    if text.strip():
        ann = Announcement(text=text.strip(), active=True)
        db.add(ann)
    db.commit()
    return RedirectResponse(url="/admin", status_code=302)


@router.post("/import")
async def admin_import(
    request: Request,
    file: UploadFile = File(...),
    track: str = Form(...),
    db: Session = Depends(get_db),
):
    require_admin(request)
    import tempfile, os
    from app.import_data import import_excel

    with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        report = import_excel(db, tmp_path, track)
    finally:
        os.unlink(tmp_path)

    return request.app.state.templates.TemplateResponse("admin/import_report.html", {
        "request": request,
        "report": report,
        "track": track,
    })


@router.get("/export/learners")
async def export_learners(request: Request, db: Session = Depends(get_db)):
    require_admin(request)
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Суралцагчид"
    ws.append(["Код", "Овог", "Нэр", "Урсгал", "Баг", "Ажлын газар", "Албан тушаал", "Утас", "Имэйл", "Нэвтэрсэн эсэх", "Сүүлд нэвтэрсэн"])

    learners = db.query(Learner).options(joinedload(Learner.team)).order_by(Learner.track, Learner.code).all()
    for l in learners:
        ws.append([
            l.code, l.surname, l.first_name,
            l.track.value if l.track else "",
            l.team.display_name if l.team else "",
            l.workplace or "", l.position or "",
            l.phone or "", l.email or "",
            "Тийм" if l.last_login_at else "Үгүй",
            l.last_login_at.strftime("%Y-%m-%d %H:%M") if l.last_login_at else "",
        ])

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=learners_export.xlsx"},
    )


@router.get("/export/teams")
async def export_teams(request: Request, db: Session = Depends(get_db)):
    require_admin(request)
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Багууд"
    ws.append(["Урсгал", "Баг", "Сэдэв", "Ахлагч", "Төсөл", "Асуудал", "Алхам", "Явц %", "Сонгосон өдөр", "Сүүлд идэвхтэй"])

    teams = db.query(Team).options(
        joinedload(Team.members), joinedload(Team.leader),
        joinedload(Team.tasks), joinedload(Team.slot),
        joinedload(Team.weekly_updates),
    ).order_by(Team.track, Team.number).all()

    for t in teams:
        ws.append([
            t.track.value if t.track else "",
            t.display_name,
            t.topic or "",
            t.leader.full_name if t.leader else "",
            t.project_name or "",
            t.problem_statement or "",
            t.current_step,
            t.task_progress,
            str(t.slot.slot_date) if t.slot else "",
            t.last_activity.strftime("%Y-%m-%d") if t.last_activity else "",
        ])

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=teams_export.xlsx"},
    )


@router.get("/export/schedule")
async def export_schedule(request: Request, db: Session = Depends(get_db)):
    require_admin(request)
    import openpyxl

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Танилцуулгын хуваарь"
    ws.append(["Урсгал", "Огноо", "Цаг", "Хичээл", "Багтаамж", "Бүртгэгдсэн", "Багууд"])

    slots = db.query(PresentationSlot).order_by(
        PresentationSlot.track, PresentationSlot.slot_date
    ).all()

    for s in slots:
        booked_teams = [t.display_name for t in s.bookings]
        ws.append([
            s.track.value if s.track else "",
            str(s.slot_date),
            f"{s.time_start} - {s.time_end}",
            s.session_name or "",
            s.capacity,
            s.booked_count,
            ", ".join(booked_teams),
        ])

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=schedule_export.xlsx"},
    )
