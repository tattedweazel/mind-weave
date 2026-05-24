"""Board project folder API (Shared seed, CRUD, board project_id)."""

from fastapi.testclient import TestClient

from app.domain.sandbox.builtins import EMPTY_SANDBOX_BOARD_ID


def test_board_projects_list_includes_shared(client: TestClient):
    r = client.get("/api/v1/board-projects/")
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, list)
    names = {p["name"] for p in body}
    assert "Shared" in names
    shared = next(p for p in body if p["name"] == "Shared")
    assert "board_count" in shared


def test_board_projects_create_rejects_shared_name(client: TestClient):
    r = client.post("/api/v1/board-projects/", json={"name": "shared"})
    assert r.status_code == 400


def test_board_projects_crud_and_delete_empty(client: TestClient):
    create = client.post(
        "/api/v1/board-projects/",
        json={"name": "Alpha Board Project"},
    )
    assert create.status_code == 201
    pid = create.json()["id"]

    dup = client.post("/api/v1/board-projects/", json={"name": "Alpha Board Project"})
    assert dup.status_code == 400

    deleted = client.delete(f"/api/v1/board-projects/{pid}")
    assert deleted.status_code == 204

    listed = client.get("/api/v1/board-projects/")
    assert listed.status_code == 200
    assert not any(p["id"] == pid for p in listed.json())


def test_board_projects_delete_nonempty_requires_cascade(client: TestClient):
    create = client.post(
        "/api/v1/board-projects/",
        json={"name": "Beta Board Project"},
    )
    assert create.status_code == 201
    pid = create.json()["id"]

    board = client.post(
        "/api/v1/sandbox/boards",
        json={"name": "In Beta", "project_id": pid},
    )
    assert board.status_code == 200
    board_id = board.json()["id"]

    blocked = client.delete(f"/api/v1/board-projects/{pid}")
    assert blocked.status_code == 409

    still_there = client.get("/api/v1/sandbox/boards")
    assert still_there.status_code == 200
    assert any(b["id"] == board_id for b in still_there.json()["boards"])

    deleted = client.delete(f"/api/v1/board-projects/{pid}?delete_boards=true")
    assert deleted.status_code == 204

    boards = client.get("/api/v1/sandbox/boards")
    assert boards.status_code == 200
    assert not any(b["id"] == board_id for b in boards.json()["boards"])

    projects = client.get("/api/v1/board-projects/")
    assert not any(p["id"] == pid for p in projects.json())


def test_board_create_defaults_to_shared_project(client: TestClient):
    shared = next(p for p in client.get("/api/v1/board-projects/").json() if p["name"] == "Shared")
    created = client.post("/api/v1/sandbox/boards", json={"name": "Default Project Board"})
    assert created.status_code == 200
    assert created.json()["project_id"] == shared["id"]


def test_board_create_with_project_id(client: TestClient):
    proj = client.post("/api/v1/board-projects/", json={"name": "My Boards"})
    assert proj.status_code == 201
    pid = proj.json()["id"]

    created = client.post(
        "/api/v1/sandbox/boards",
        json={"name": "Placed Board", "project_id": pid},
    )
    assert created.status_code == 200
    assert created.json()["project_id"] == pid


def test_board_update_project_id(client: TestClient):
    proj_a = client.post("/api/v1/board-projects/", json={"name": "Move From"})
    proj_b = client.post("/api/v1/board-projects/", json={"name": "Move To"})
    assert proj_a.status_code == 201
    assert proj_b.status_code == 201
    pid_a = proj_a.json()["id"]
    pid_b = proj_b.json()["id"]

    board = client.post(
        "/api/v1/sandbox/boards",
        json={"name": "Movable Board", "project_id": pid_a},
    )
    assert board.status_code == 200
    board_id = board.json()["id"]

    moved = client.patch(
        f"/api/v1/sandbox/boards/{board_id}",
        json={"project_id": pid_b},
    )
    assert moved.status_code == 200
    assert moved.json()["project_id"] == pid_b


def test_cannot_delete_shared_board_project(client: TestClient):
    shared = next(p for p in client.get("/api/v1/board-projects/").json() if p["name"] == "Shared")
    r = client.delete(f"/api/v1/board-projects/{shared['id']}")
    assert r.status_code == 400


def test_system_board_has_null_project_id(client: TestClient):
    boards = client.get("/api/v1/sandbox/boards").json()["boards"]
    empty = next(b for b in boards if b["id"] == str(EMPTY_SANDBOX_BOARD_ID))
    assert empty["is_system"] is True
    assert empty["project_id"] is None


def test_delete_user_board_succeeds_system_board_404(client: TestClient):
    created = client.post("/api/v1/sandbox/boards", json={"name": "To Delete"})
    assert created.status_code == 200
    board_id = created.json()["id"]

    deleted = client.delete(f"/api/v1/sandbox/boards/{board_id}")
    assert deleted.status_code == 200
    assert deleted.json()["ok"] is True

    boards = client.get("/api/v1/sandbox/boards").json()["boards"]
    assert not any(b["id"] == board_id for b in boards)

    system_delete = client.delete(f"/api/v1/sandbox/boards/{EMPTY_SANDBOX_BOARD_ID}")
    assert system_delete.status_code == 404
