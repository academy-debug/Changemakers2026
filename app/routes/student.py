from datetime import datetime

from fastapi import APIRouter, Request, Depends, Form, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func

from app.database import get_db
from app.models import (
    Learner, Team, LeaderVote, Task, TaskStatus,
    PresentationSlot, WeeklyUpdate, Announcement, AuditLog,
)
from app.auth import (
    find_learner, get_current_learner, check_rate_limit,
    record_login_attempt, get_client_ip,
)
from app.config import SHOW_CONTACT_INFO

router = APIRouter()


def audit(db: Session, learner_id: int | None, action: str, detail: str, ip: str):
    log = AuditLog(learner_id=learner_id, action=action, detail=detail, ip=ip)
    db.add(log)
    db.commit()


@router.get("/", name="home")
async def home(request: Request):
    learner = get_current_learner(request, next(get_db()))
    if learner:
        return RedirectResponse(url="/my-team", status_code=302)
    return RedirectResponse(url="/login", status_code=302)


@router.get("/login", name="login")
async def login_page(request: Request):
    learner = get_current_learner(request, next(get_db()))
    if learner:
        return RedirectResponse(url="/my-team", status_code=302)
    return request.app.state.templates.TemplateResponse("login.html", {
        "request": request,
        "error": None,
        "selected_track": "",
    })


@router.post("/login")
async def login_submit(
    request: Request,
    credential: str = Form(...),
    track: str = Form(""),
    db: Session = Depends(get_db),
):
    ip = get_client_ip(request)

    if not check_rate_limit(db, ip):
        return request.app.state.templates.TemplateResponse("login.html", {
            "request": request,
            "error": "Хэт олон оролдлого. 1 минут хүлээнэ үү.",
            "selected_track": track,
        }, status_code=429)

    learner = find_learner(db, credential, track=track or None)

    if not learner:
        record_login_attempt(db, ip, False)
        return request.app.state.templates.TemplateResponse("login.html", {
            "request": request,
            "error": "Утас эсвэл имэйл олдсонгүй. Та бүртгэлтэй мэдээллээ оруулна уу. Асуудал гарвал зохион байгуулагчтай холбогдоно уу.",
            "selected_track": track,
        }, status_code=404)

    record_login_attempt(db, ip, True)
    learner.last_login_at = datetime.utcnow()
    db.commit()

    request.session["learner_id"] = learner.id
    audit(db, learner.id, "login", f"Нэвтэрлээ: {learner.code}", ip)
    return RedirectResponse(url="/my-team", status_code=302)


@router.get("/logout", name="logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=302)


def require_learner(request: Request, db: Session) -> Learner:
    learner = get_current_learner(request, db)
    if not learner:
        raise HTTPException(status_code=302, headers={"Location": "/login"})
    return learner


@router.get("/my-team", name="my_team")
async def my_team(request: Request, db: Session = Depends(get_db)):
    learner = require_learner(request, db)
    team = db.query(Team).options(
        joinedload(Team.members),
        joinedload(Team.leader),
        joinedload(Team.tasks).joinedload(Task.assignee),
        joinedload(Team.votes),
        joinedload(Team.weekly_updates),
        joinedload(Team.slot),
    ).filter(Team.id == learner.team_id).first()

    if not team:
        return request.app.state.templates.TemplateResponse("no_team.html", {
            "request": request,
            "learner": learner,
        })

    announcements = db.query(Announcement).filter_by(active=True).order_by(Announcement.created_at.desc()).all()

    my_vote = db.query(LeaderVote).filter_by(team_id=team.id, voter_id=learner.id).first()

    vote_counts = {}
    for v in team.votes:
        vote_counts[v.candidate_id] = vote_counts.get(v.candidate_id, 0) + 1

    slots = db.query(PresentationSlot).filter_by(track=learner.track).order_by(PresentationSlot.slot_date).all()
    available_slots = [s for s in slots if not s.is_demo_day]

    is_leader = team.leader_id == learner.id

    steps = get_steps(team)

    return request.app.state.templates.TemplateResponse("my_team.html", {
        "request": request,
        "learner": learner,
        "team": team,
        "announcements": announcements,
        "my_vote": my_vote,
        "vote_counts": vote_counts,
        "steps": steps,
        "is_leader": is_leader,
        "show_contact": SHOW_CONTACT_INFO,
        "available_slots": available_slots,
        "TaskStatus": TaskStatus,
    })


def get_steps(team):
    members_logged = any(m.last_login_at for m in team.members)
    steps = [
        {"num": 1, "name": "Багаа мэдэх", "done": members_logged,
         "desc": "Багийн гишүүд, мэргэжил, холбоо барих мэдээллийг хар"},
        {"num": 2, "name": "Багаараа уулзах", "done": team.meeting_done,
         "desc": "Эхний уулзалтын цаг, линк тохир — танилцаж, зорилгоо ярилц"},
        {"num": 3, "name": "Ахлагч сонгох", "done": team.leader_id is not None,
         "desc": "Санал өгч, олонхын саналаар ахлагчаа баталгаажуул"},
        {"num": 4, "name": "Асуудал тодорхойлох", "done": bool(team.problem_statement),
         "desc": "Шийдэх асуудал, хэнд тулгардаг, яагаад чухал — тодорхой бич"},
        {"num": 5, "name": "Төсөл бүртгүүлэх", "done": bool(team.project_name),
         "desc": "Төслийн нэр, нэг мөр тайлбар, AI-аар хэрхэн шийдэх санаа"},
        {"num": 6, "name": "Ажил хуваарилах", "done": len([t for t in team.tasks if t.assignee_id]) >= 3,
         "desc": "Хэн юу хийх, хэзээ дуусгах — ажлуудаа бүртгэж хариуцагч тогтоо"},
        {"num": 7, "name": "Хэрэгжүүлэх", "done": False,
         "desc": "AI шийдлээ бүтээж, долоо хоног бүр явцаа бичиж тэмдэглэ",
         "progress": team.task_progress},
        {"num": 8, "name": "Rehearsal өдөр сонгох", "done": team.slot_confirmed_at is not None,
         "desc": "Demo Day-ээс өмнө зөвлөгөө авах өдрөө сонго — 5-6 баг, нэг баг ~10 мин"},
        {"num": 9, "name": "Demo Day", "done": False,
         "desc": "2026.12.26 — Шилдэг 10 багийн танилцуулга, хаалтын арга хэмжээ", "info_only": True},
    ]
    return steps


@router.post("/meeting", name="update_meeting")
async def update_meeting(
    request: Request,
    meeting_link: str = Form(""),
    meeting_datetime: str = Form(""),
    db: Session = Depends(get_db),
):
    learner = require_learner(request, db)
    team = db.query(Team).filter_by(id=learner.team_id).first()
    if not team:
        raise HTTPException(404)
    team.meeting_link = meeting_link.strip()
    team.meeting_datetime = meeting_datetime.strip()
    db.commit()
    audit(db, learner.id, "meeting_update", f"Уулзалтын мэдээлэл: {meeting_link}", get_client_ip(request))
    return RedirectResponse(url="/my-team#step-2", status_code=302)


@router.post("/meeting-done", name="meeting_done")
async def meeting_done(request: Request, db: Session = Depends(get_db)):
    learner = require_learner(request, db)
    team = db.query(Team).filter_by(id=learner.team_id).first()
    if not team:
        raise HTTPException(404)
    team.meeting_done = True
    db.commit()
    audit(db, learner.id, "meeting_done", "Уулзалт болсон", get_client_ip(request))
    return RedirectResponse(url="/my-team#step-2", status_code=302)


@router.post("/vote-leader", name="vote_leader")
async def vote_leader(
    request: Request,
    candidate_id: int = Form(...),
    db: Session = Depends(get_db),
):
    learner = require_learner(request, db)
    team = db.query(Team).options(joinedload(Team.members)).filter_by(id=learner.team_id).first()
    if not team:
        raise HTTPException(404)

    if team.leader_id:
        return RedirectResponse(url="/my-team#step-3", status_code=302)

    candidate = db.query(Learner).filter_by(id=candidate_id, team_id=team.id).first()
    if not candidate:
        raise HTTPException(400)

    existing_vote = db.query(LeaderVote).filter_by(team_id=team.id, voter_id=learner.id).first()
    if existing_vote:
        existing_vote.candidate_id = candidate_id
        existing_vote.voted_at = datetime.utcnow()
    else:
        vote = LeaderVote(team_id=team.id, voter_id=learner.id, candidate_id=candidate_id)
        db.add(vote)
    db.flush()

    votes = db.query(LeaderVote).filter_by(team_id=team.id).all()
    vote_counts = {}
    for v in votes:
        vote_counts[v.candidate_id] = vote_counts.get(v.candidate_id, 0) + 1

    member_count = len(team.members)
    majority = member_count // 2 + 1
    for cid, count in vote_counts.items():
        if count >= majority:
            team.leader_id = cid
            db.commit()
            leader = db.query(Learner).get(cid)
            audit(db, learner.id, "leader_elected",
                  f"Ахлагч сонгогдлоо: {leader.full_name} ({count}/{member_count})",
                  get_client_ip(request))
            return RedirectResponse(url="/my-team#step-3", status_code=302)

    db.commit()
    audit(db, learner.id, "vote_cast", f"Санал өгсөн: candidate_id={candidate_id}", get_client_ip(request))
    return RedirectResponse(url="/my-team#step-3", status_code=302)


@router.post("/problem", name="update_problem")
async def update_problem(
    request: Request,
    problem_statement: str = Form(""),
    problem_who: str = Form(""),
    problem_why: str = Form(""),
    db: Session = Depends(get_db),
):
    learner = require_learner(request, db)
    team = db.query(Team).filter_by(id=learner.team_id).first()
    if not team:
        raise HTTPException(404)
    team.problem_statement = problem_statement.strip()
    team.problem_who = problem_who.strip()
    team.problem_why = problem_why.strip()
    db.commit()
    audit(db, learner.id, "problem_update", "Асуудлын тодорхойлолт шинэчлэгдлээ", get_client_ip(request))
    return RedirectResponse(url="/my-team#step-4", status_code=302)


@router.post("/project", name="register_project")
async def register_project(
    request: Request,
    project_name: str = Form(""),
    project_description: str = Form(""),
    project_ai_solution: str = Form(""),
    project_before_state: str = Form(""),
    project_ai_tools: str = Form(""),
    project_ai_level: int = Form(0),
    project_measurement_plan: str = Form(""),
    project_target_audience: str = Form(""),
    db: Session = Depends(get_db),
):
    learner = require_learner(request, db)
    team = db.query(Team).filter_by(id=learner.team_id).first()
    if not team:
        raise HTTPException(404)
    if team.leader_id and team.leader_id != learner.id:
        raise HTTPException(403, "Зөвхөн ахлагч бүртгүүлэх боломжтой")
    team.project_name = project_name.strip()
    team.project_description = project_description.strip()
    team.project_ai_solution = project_ai_solution.strip()
    team.project_before_state = project_before_state.strip()
    team.project_ai_tools = project_ai_tools.strip()
    team.project_ai_level = project_ai_level if project_ai_level else None
    team.project_measurement_plan = project_measurement_plan.strip()
    team.project_target_audience = project_target_audience.strip()
    db.commit()
    audit(db, learner.id, "project_register", f"Төсөл бүртгүүлсэн: {project_name}", get_client_ip(request))
    return RedirectResponse(url="/my-team#step-5", status_code=302)


@router.post("/tasks/add", name="add_task")
async def add_task(
    request: Request,
    title: str = Form(...),
    assignee_id: int = Form(0),
    due_date: str = Form(""),
    db: Session = Depends(get_db),
):
    learner = require_learner(request, db)
    team = db.query(Team).filter_by(id=learner.team_id).first()
    if not team:
        raise HTTPException(404)

    from datetime import date as date_type
    dd = None
    if due_date:
        try:
            dd = date_type.fromisoformat(due_date)
        except ValueError:
            pass

    task = Task(
        team_id=team.id,
        title=title.strip(),
        assignee_id=assignee_id if assignee_id else None,
        due_date=dd,
    )
    db.add(task)
    db.commit()
    audit(db, learner.id, "task_add", f"Ажил нэмсэн: {title}", get_client_ip(request))
    return RedirectResponse(url="/my-team#step-6", status_code=302)


@router.post("/tasks/{task_id}/status", name="update_task_status")
async def update_task_status(
    request: Request,
    task_id: int,
    status: str = Form(...),
    db: Session = Depends(get_db),
):
    learner = require_learner(request, db)
    task = db.query(Task).filter_by(id=task_id).first()
    if not task or task.team_id != learner.team_id:
        raise HTTPException(404)
    try:
        task.status = TaskStatus(status)
    except ValueError:
        raise HTTPException(400)
    db.commit()
    audit(db, learner.id, "task_status", f"Ажлын төлөв: {task.title} -> {status}", get_client_ip(request))
    return RedirectResponse(url="/my-team#step-7", status_code=302)


@router.post("/tasks/{task_id}/delete", name="delete_task")
async def delete_task(request: Request, task_id: int, db: Session = Depends(get_db)):
    learner = require_learner(request, db)
    task = db.query(Task).filter_by(id=task_id).first()
    if not task or task.team_id != learner.team_id:
        raise HTTPException(404)
    db.delete(task)
    db.commit()
    audit(db, learner.id, "task_delete", f"Ажил устгасан: {task.title}", get_client_ip(request))
    return RedirectResponse(url="/my-team#step-6", status_code=302)


@router.post("/weekly-update", name="add_weekly_update")
async def add_weekly_update(
    request: Request,
    content: str = Form(""),
    repo_link: str = Form(""),
    demo_link: str = Form(""),
    slide_link: str = Form(""),
    db: Session = Depends(get_db),
):
    learner = require_learner(request, db)
    team = db.query(Team).filter_by(id=learner.team_id).first()
    if not team:
        raise HTTPException(404)
    update = WeeklyUpdate(
        team_id=team.id,
        content=content.strip(),
        repo_link=repo_link.strip() or None,
        demo_link=demo_link.strip() or None,
        slide_link=slide_link.strip() or None,
        created_by_id=learner.id,
    )
    db.add(update)
    db.commit()
    audit(db, learner.id, "weekly_update", "Явцын мэдээлэл нэмсэн", get_client_ip(request))
    return RedirectResponse(url="/my-team#step-7", status_code=302)


@router.post("/results", name="submit_results")
async def submit_results(
    request: Request,
    result_summary: str = Form(""),
    result_time_saved: str = Form(""),
    result_output_change: str = Form(""),
    result_quality_change: str = Form(""),
    result_cost_change: str = Form(""),
    result_outcome_change: str = Form(""),
    result_key_insight: str = Form(""),
    db: Session = Depends(get_db),
):
    learner = require_learner(request, db)
    team = db.query(Team).filter_by(id=learner.team_id).first()
    if not team:
        raise HTTPException(404)
    team.result_summary = result_summary.strip()
    team.result_time_saved = result_time_saved.strip()
    team.result_output_change = result_output_change.strip()
    team.result_quality_change = result_quality_change.strip()
    team.result_cost_change = result_cost_change.strip()
    team.result_outcome_change = result_outcome_change.strip()
    team.result_key_insight = result_key_insight.strip()
    db.commit()
    audit(db, learner.id, "results_submit", "Үр дүн бүртгэсэн", get_client_ip(request))
    return RedirectResponse(url="/my-team#step-7", status_code=302)


@router.post("/presentation", name="submit_presentation")
async def submit_presentation(
    request: Request,
    presentation_slide_link: str = Form(""),
    presentation_demo_video_link: str = Form(""),
    db: Session = Depends(get_db),
):
    learner = require_learner(request, db)
    team = db.query(Team).filter_by(id=learner.team_id).first()
    if not team:
        raise HTTPException(404)
    team.presentation_slide_link = presentation_slide_link.strip()
    team.presentation_demo_video_link = presentation_demo_video_link.strip()
    db.commit()
    audit(db, learner.id, "presentation_submit", "Танилцуулгын материал бүртгэсэн", get_client_ip(request))
    return RedirectResponse(url="/my-team#step-8", status_code=302)


@router.post("/select-slot", name="select_slot")
async def select_slot(
    request: Request,
    slot_id: int = Form(...),
    db: Session = Depends(get_db),
):
    learner = require_learner(request, db)
    team = db.query(Team).filter_by(id=learner.team_id).first()
    if not team:
        raise HTTPException(404)
    if team.leader_id and team.leader_id != learner.id:
        raise HTTPException(403, "Зөвхөн ахлагч баталгаажуулна")

    slot = db.query(PresentationSlot).with_for_update().filter_by(id=slot_id).first()
    if not slot:
        raise HTTPException(404, "Слот олдсонгүй")
    if slot.is_demo_day:
        raise HTTPException(400, "Demo Day слот сонгох боломжгүй")

    booked = db.query(Team).filter_by(slot_id=slot.id).count()
    if booked >= slot.capacity:
        db.rollback()
        raise HTTPException(409, "Уучлаарай, энэ өдрийн бүх суудал дүүрсэн байна. Өөр өдөр сонгоно уу.")

    if team.slot_id and team.slot_id != slot.id:
        pass
    team.slot_id = slot.id
    team.slot_confirmed_at = datetime.utcnow()
    db.commit()

    audit(db, learner.id, "slot_select",
          f"Танилцуулгын өдөр сонгосон: {slot.slot_date}", get_client_ip(request))
    return RedirectResponse(url="/my-team#step-8", status_code=302)


@router.post("/cancel-slot", name="cancel_slot")
async def cancel_slot(request: Request, db: Session = Depends(get_db)):
    learner = require_learner(request, db)
    team = db.query(Team).filter_by(id=learner.team_id).first()
    if not team:
        raise HTTPException(404)
    if team.leader_id and team.leader_id != learner.id:
        raise HTTPException(403)
    team.slot_id = None
    team.slot_confirmed_at = None
    db.commit()
    audit(db, learner.id, "slot_cancel", "Танилцуулгын өдөр цуцалсан", get_client_ip(request))
    return RedirectResponse(url="/my-team#step-8", status_code=302)


@router.get("/schedule", name="schedule")
async def schedule_page(request: Request, db: Session = Depends(get_db)):
    learner = require_learner(request, db)
    slots = db.query(PresentationSlot).filter_by(
        track=learner.track
    ).order_by(PresentationSlot.slot_date).all()

    from datetime import date
    today = date.today()

    return request.app.state.templates.TemplateResponse("schedule.html", {
        "request": request,
        "learner": learner,
        "slots": slots,
        "today": today,
    })


@router.get("/cpd", name="cpd_requirements")
async def cpd_requirements(request: Request, db: Session = Depends(get_db)):
    learner = require_learner(request, db)
    return request.app.state.templates.TemplateResponse("cpd.html", {
        "request": request,
        "learner": learner,
    })


@router.get("/guide", name="capstone_guide")
async def capstone_guide(request: Request, db: Session = Depends(get_db)):
    learner = require_learner(request, db)
    from app.config import CONTENT_DIR
    import markdown
    guide_path = CONTENT_DIR / "capstone_guide.md"
    content_html = ""
    if guide_path.exists():
        raw = guide_path.read_text(encoding="utf-8")
        content_html = markdown.markdown(raw, extensions=["tables", "fenced_code"])
    return request.app.state.templates.TemplateResponse("capstone_guide.html", {
        "request": request,
        "learner": learner,
        "content_html": content_html,
    })
