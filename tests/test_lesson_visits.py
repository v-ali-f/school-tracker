from datetime import date

from app.core.extensions import db
from app.models import Department, DepartmentLeader, LessonVisit, TeacherLoad, User
from app.models.role_access import RoleModuleAccess
from app.modules.lesson_visits.routes import CHECKLIST_SECTIONS


def _visit_form(teacher_id, **overrides):
    data = {
        "teacher_id": str(teacher_id),
        "visit_date": date.today().isoformat(),
        "class_name": "7А",
        "subject_name": "Математика",
        "topic": "Линейные уравнения",
        "strengths": "Чёткие инструкции и активная работа класса.",
        "growth_areas": "Добавить время на итоговую рефлексию.",
        "repeat_required": "yes",
    }
    for code, _title, options, multiple in CHECKLIST_SECTIONS:
        data[f"check_{code}"] = [options[0][0]] if multiple else options[0][0]
    data.update(overrides)
    return data


def test_methodist_creates_visit_and_teacher_sees_own_result(app, client, make_user, login):
    methodist_id = make_user("METHODIST")
    teacher_id = make_user("TEACHER")

    login(methodist_id)
    response = client.post("/lesson-visits/new", data=_visit_form(teacher_id), follow_redirects=True)
    assert response.status_code == 200
    assert "Карта посещения сохранена" in response.get_data(as_text=True)
    assert "Повторное посещение требуется" in response.get_data(as_text=True)

    with app.app_context():
        visit = LessonVisit.query.one()
        assert visit.teacher_id == teacher_id
        assert visit.observer_id == methodist_id
        assert visit.parallel == 7
        visit_id = visit.id

    login(teacher_id)
    registry = client.get("/lesson-visits/")
    assert registry.status_code == 200
    assert "Линейные уравнения" in registry.get_data(as_text=True)
    detail = client.get(f"/lesson-visits/{visit_id}")
    assert detail.status_code == 200
    assert "Чёткие инструкции" in detail.get_data(as_text=True)
    assert client.get("/lesson-visits/new").status_code == 403


def test_teacher_cannot_open_another_teachers_visit(app, client, make_user, login):
    methodist_id = make_user("METHODIST")
    teacher_id = make_user("TEACHER")
    other_teacher_id = make_user("TEACHER")
    with app.app_context():
        visit = LessonVisit(
            teacher_id=teacher_id,
            observer_id=methodist_id,
            visit_date=date.today(),
            class_name="5Б",
            parallel=5,
            subject_name="Русский язык",
            topic="Главные члены предложения",
            checklist={code: ([options[0][0]] if multiple else options[0][0]) for code, _title, options, multiple in CHECKLIST_SECTIONS},
            strengths="Сильные стороны",
            growth_areas="Зоны роста",
            repeat_required=False,
        )
        db.session.add(visit)
        db.session.commit()
        visit_id = visit.id

    login(other_teacher_id)
    assert client.get(f"/lesson-visits/{visit_id}").status_code == 403
    registry = client.get("/lesson-visits/")
    assert registry.status_code == 200
    assert "Главные члены предложения" not in registry.get_data(as_text=True)


def test_department_head_is_limited_to_own_department(app, client, make_user, login):
    head_id = make_user("DEPARTMENT_HEAD")
    own_teacher_id = make_user("TEACHER")
    other_teacher_id = make_user("TEACHER")
    with app.app_context():
        db.session.get(User, own_teacher_id).last_name = "Алгебров"
        db.session.get(User, other_teacher_id).last_name = "Литературов"
        own_department = Department(name="Математика")
        other_department = Department(name="Филология")
        db.session.add_all([own_department, other_department])
        db.session.flush()
        db.session.add(DepartmentLeader(department_id=own_department.id, user_id=head_id))
        db.session.add_all([
            TeacherLoad(
                teacher_id=own_teacher_id,
                department_id=own_department.id,
                class_name="8А",
                grade=8,
                subject_name="Алгебра",
                hours=4,
            ),
            TeacherLoad(
                teacher_id=other_teacher_id,
                department_id=other_department.id,
                class_name="8Б",
                grade=8,
                subject_name="Литература",
                hours=3,
            ),
        ])
        db.session.commit()
        own_name = db.session.get(User, own_teacher_id).fio
        other_name = db.session.get(User, other_teacher_id).fio

    login(head_id)
    form = client.get("/lesson-visits/new")
    html = form.get_data(as_text=True)
    assert form.status_code == 200
    assert own_name in html
    assert other_name not in html
    assert 'role="combobox"' in html
    assert 'id="teacherResults"' in html
    assert 'type="hidden" id="teacherSelect" name="teacher_id"' in html
    assert html.count('name="teacher_id"') == 1

    workload = client.get(f"/lesson-visits/api/teachers/{own_teacher_id}/workload")
    assert workload.status_code == 200
    assert workload.get_json()["items"][0]["subject_name"] == "Алгебра"
    assert client.get(f"/lesson-visits/api/teachers/{other_teacher_id}/workload").status_code == 403


def test_future_visit_date_is_rejected(app, client, make_user, login):
    methodist_id = make_user("METHODIST")
    teacher_id = make_user("TEACHER")
    login(methodist_id)
    response = client.post(
        "/lesson-visits/new",
        data=_visit_form(teacher_id, visit_date="2099-01-01"),
    )
    assert response.status_code == 200
    assert "Нельзя сохранить посещение с будущей датой" in response.get_data(as_text=True)
    with app.app_context():
        assert LessonVisit.query.count() == 0


def test_lesson_visit_registry_and_form_use_shared_workspace(client, make_user, login):
    methodist_id = make_user("METHODIST")
    login(methodist_id)

    for path in ("/lesson-visits/", "/lesson-visits/new"):
        response = client.get(path)
        html = response.get_data(as_text=True)
        assert response.status_code == 200
        assert 'class="sp-workspace ws-workspace"' in html
        assert "workspace_ui.css" in html
        assert "lesson_visits.css" in html
        assert "Посещение уроков" in html


def test_dashboard_menu_places_lesson_visits_between_control_works_and_olympiads(
    app,
    client,
    make_user,
    login,
):
    admin_id = make_user("ADMIN")
    with app.app_context():
        # Existing installations can already have saved settings for other
        # modules. A newly added module must still use its role default.
        db.session.add(RoleModuleAccess(
            role_code="ADMIN",
            module_code="control_works",
            is_visible=True,
            is_enabled=True,
            is_active=True,
            access_level="view",
        ))
        db.session.commit()

    login(admin_id)
    response = client.get("/")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    control_position = html.index(">Контрольные работы</span>")
    lesson_position = html.index(">Посещение уроков</span>")
    olympiad_position = html.index(">Олимпиады</span>")
    assert control_position < lesson_position < olympiad_position
