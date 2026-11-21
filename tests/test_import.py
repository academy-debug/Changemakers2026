import os
from pathlib import Path

import openpyxl
import pytest


def create_test_excel(tmp_path):
    wb = openpyxl.Workbook()

    ws1 = wb.active
    ws1.title = "Багт хуваагдсан байдал"
    ws1.append(["#", "Cуралцагчийн код", "Ажлын туршлага жилээр", "Ажлын газар",
                "Албан тушаал", "Хэлний оноо",
                "Асуулт 2 (зорилго)", "Асуулт 3 (бэрхшээл)",
                "Асуулт 4 (AI-аар шийдэх асуудал)", "Асуулт 5 (мотиваци)",
                "Баг", "Яагаад энэ багт орсон, ямар зорилго нь ижил байсан"])
    ws1.append([1, "TestPro001", "3", "Тест ХХК", "Инженер", "IELTS 6.5",
                "Эссэ 2 НУУЦ", "Эссэ 3 НУУЦ", "AI ашиглах", "Эссэ 5 НУУЦ",
                "1-р баг", "Багийн сэдэв: Тест\nЯагаад энэ багт орсон: Шалтгаан\nИжил зорилго: Зорилго"])
    ws1.append([2, "TestPro002", "5", "Тест2 ХХК", "Менежер", "",
                "", "", "", "",
                "1-р баг", "Багийн сэдэв: Тест\nЯагаад энэ багт орсон: Шалтгаан2\nИжил зорилго: Зорилго"])

    ws2 = wb.create_sheet("Багууд")
    ws2.append(["Баг", "Багийн сэдэв", "Гишүүдийн тоо", "Гишүүд (код)", "Ижил зорилго"])
    ws2.append(["1-р баг", "Тест сэдэв", 2, "TestPro001, TestPro002", "Тест зорилго"])
    ws2.append(["Нийт", 2])

    ws3 = wb.create_sheet("Төсөл танилцуулах өдөр")
    ws3.append(["Date", "Time", "Module", "Session and topic"])
    ws3.append(["Thu 17 Dec", "19:00 | 20:30", "M6", "Session 19. 5 Баг rehearsal"])
    ws3.append(["Sat 26 Dec", "19:00 | 20:30", "", "Demo Day"])

    ws4 = wb.create_sheet("phone email")
    ws4.append(["Овог", "Нэр", "Нас", "Хүйс", "Боловсрол", "Утас", "Хаанаас", "Имэйл"])
    ws4.append(["Батболд", "Түвшин", 25, "Эр", "Бакалавр", "99001122", "УБ", "tuvsh@test.com", "TestPro001"])
    ws4.append(["Ганчимэг", "Солонго", 28, "Эм", "Магистр", "+976 8800 3344", "Дархан", "sol@test.com", "TestPro002"])

    path = tmp_path / "test_data.xlsx"
    wb.save(path)
    return str(path)


def test_import_creates_data(tmp_path, db):
    from app.models import Learner, Team, PresentationSlot, TrackEnum
    from app.import_data import import_excel

    path = create_test_excel(tmp_path)
    report = import_excel(db, path, "professionals")

    assert report["learners_imported"] == 2
    assert report["teams_imported"] == 1

    learners = db.query(Learner).filter_by(track=TrackEnum.professionals).all()
    assert len(learners) == 2

    l1 = db.query(Learner).filter_by(code="TestPro001").first()
    assert l1.surname == "Батболд"
    assert l1.first_name == "Түвшин"
    assert l1.phone == "99001122"
    assert l1.email == "tuvsh@test.com"
    assert l1.team is not None
    assert l1.team.topic == "Тест сэдэв"

    l2 = db.query(Learner).filter_by(code="TestPro002").first()
    assert l2.phone == "88003344"


def test_import_no_essays_stored(tmp_path, db):
    from app.models import Learner
    from app.import_data import import_excel

    path = create_test_excel(tmp_path)
    import_excel(db, path, "professionals")

    l1 = db.query(Learner).filter_by(code="TestPro001").first()
    for col in dir(l1):
        if col.startswith("_"):
            continue
        val = getattr(l1, col, None)
        if isinstance(val, str):
            assert "НУУЦ" not in val, f"Эссэний мэдээлэл '{col}' баганад олдлоо"


def test_import_idempotent(tmp_path, db):
    from app.models import Learner, Team
    from app.import_data import import_excel

    path = create_test_excel(tmp_path)
    import_excel(db, path, "professionals")
    import_excel(db, path, "professionals")

    assert db.query(Learner).count() == 2
    assert db.query(Team).count() == 1


def test_import_preserves_team_data(tmp_path, db):
    from app.models import Team, TrackEnum
    from app.import_data import import_excel

    path = create_test_excel(tmp_path)
    import_excel(db, path, "professionals")

    team = db.query(Team).filter_by(number=1, track=TrackEnum.professionals).first()
    team.leader_id = 1
    team.project_name = "My Project"
    db.commit()

    import_excel(db, path, "professionals")

    team = db.query(Team).filter_by(number=1, track=TrackEnum.professionals).first()
    assert team.leader_id == 1
    assert team.project_name == "My Project"
