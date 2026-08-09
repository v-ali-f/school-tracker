ADMIN_DIRECTORY_TITLES = (
    "Классы учебного года",
    "Группы ДОУ учебного года",
    "Реестр предметов",
    "Реестр олимпиадных предметов",
    "Реестр зданий",
)


def test_admin_directories_are_moved_from_home_to_main_registries(
    app,
    client,
    make_user,
    login,
):
    login(make_user("ADMIN"))

    home_html = client.get("/").get_data(as_text=True)
    registries = client.get("/hub/registries")
    registries_html = registries.get_data(as_text=True)

    assert registries.status_code == 200
    for title in ADMIN_DIRECTORY_TITLES:
        assert title not in home_html
        assert title in registries_html


def test_non_admin_does_not_see_admin_directories_in_main_registries(
    app,
    client,
    make_user,
    login,
):
    login(make_user("METHODIST"))

    response = client.get("/hub/registries")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    for title in ADMIN_DIRECTORY_TITLES:
        assert title not in html


def test_preschool_group_registry_requires_admin_role(
    app,
    client,
    make_user,
    login,
):
    login(make_user("METHODIST"))

    assert client.get("/preschool/groups").status_code == 403


def test_olympiad_subject_settings_keep_existing_methodist_permission(
    app,
    client,
    make_user,
    login,
):
    login(make_user("METHODIST"))

    assert client.get("/olympiads/settings").status_code == 200
