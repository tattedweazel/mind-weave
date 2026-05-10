from unittest.mock import AsyncMock, MagicMock, patch
import uuid

from fastapi.testclient import TestClient

from app.core.config import settings
from app.domain.palette_defaults import BUILTIN_WORKFLOW_PALETTES
from app.domain.system_palette_defaults import BUILTIN_SYSTEM_PALETTES


def test_health(client: TestClient):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_head(client: TestClient):
    """HEAD /health for `curl -I` and standard probes (no JSON body)."""
    response = client.head("/api/v1/health")
    assert response.status_code == 200
    assert response.content == b""


def test_health_ready_with_authenticated_client(client: TestClient):
    """Readiness passes when JWT/cookie auth succeeds (fixture injects current user)."""
    response = client.get("/api/v1/health/ready")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["database"] == "connected"


def test_health_ready_without_auth_returns_401(client_anonymous: TestClient):
    response = client_anonymous.get("/api/v1/health/ready")
    assert response.status_code == 401


def test_models_without_auth_returns_401(client_anonymous: TestClient):
    response = client_anonymous.get("/api/v1/models/")
    assert response.status_code == 401


@patch("app.api.v1.models.httpx.AsyncClient")
def test_models_authed_mocks_lmstudio(mock_client_cls, client: TestClient):
    """LM Studio probe is mocked — no outbound HTTP in CI."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"data": [{"id": "mock-model"}]}
    http_instance = MagicMock()
    http_instance.get = AsyncMock(return_value=mock_response)
    http_instance.__aenter__ = AsyncMock(return_value=http_instance)
    http_instance.__aexit__ = AsyncMock(return_value=None)
    mock_client_cls.return_value = http_instance

    response = client.get("/api/v1/models/")
    assert response.status_code == 200
    body = response.json()
    assert body["local"] == ["mock-model"]
    assert body["external"] == []
    assert not body.get("lm_studio_list_error")


@patch("app.api.v1.models.httpx.AsyncClient")
def test_models_list_uses_server_lm_key_not_user_key(mock_client_cls, client: TestClient):
    """GET /models/ uses LMSTUDIO_API_KEY; per-user My Settings lmstudio_api_key must not be used."""
    put = client.put(
        "/api/v1/auth/me",
        json={"api_keys": {"lmstudio_api_key": "user-key-must-not-be-used-for-model-list"}},
    )
    assert put.status_code == 200
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"data": [{"id": "from-server-key"}]}
    http_instance = MagicMock()
    http_instance.get = AsyncMock(return_value=mock_response)
    http_instance.__aenter__ = AsyncMock(return_value=http_instance)
    http_instance.__aexit__ = AsyncMock(return_value=None)
    mock_client_cls.return_value = http_instance

    response = client.get("/api/v1/models/")
    assert response.status_code == 200
    assert response.json()["local"] == ["from-server-key"]
    http_instance.get.assert_awaited_once()
    _args, kwargs = http_instance.get.await_args
    assert kwargs["headers"]["Authorization"] == f"Bearer {settings.LMSTUDIO_API_KEY}"


def test_models_list_no_server_key_returns_error_field(monkeypatch, client: TestClient):
    """Without LMSTUDIO_API_KEY, listing fails with a client-visible message (not silent empty only)."""
    monkeypatch.setattr(settings, "LMSTUDIO_API_KEY", "")
    response = client.get("/api/v1/models/")
    assert response.status_code == 200
    body = response.json()
    assert body["local"] == []
    assert body["external"] == []
    assert body.get("lm_studio_list_error")


def test_get_me_masks_api_keys(client: TestClient):
    """GET /auth/me never echoes raw api_keys (SE-011)."""
    put = client.put(
        "/api/v1/auth/me",
        json={"api_keys": {"openai": "sk-super-secret-key"}},
    )
    assert put.status_code == 200
    data = put.json()
    assert data["api_keys"]["openai"] == "[stored]"

    me = client.get("/api/v1/auth/me")
    assert me.status_code == 200
    body = me.json()
    assert body["api_keys"]["openai"] == "[stored]"
    assert "sk-super-secret" not in str(body)


def test_list_personas(client: TestClient):
    # Conftest already seeds the default system persona.
    response = client.get("/api/v1/personas/")
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= 1
    assert any(p["name"] == "default" for p in data)
    for p in data:
        assert p.get("suppress_lm_thinking") is False


def test_persona_suppress_lm_thinking_roundtrip(client: TestClient):
    create = client.post(
        "/api/v1/personas/",
        json={
            "name": "SuppressThink Roundtrip",
            "description": "Test",
            "system_prompt": "You are a test assistant.",
            "suppress_lm_thinking": True,
        },
    )
    assert create.status_code == 201
    pid = create.json()["id"]
    assert create.json()["suppress_lm_thinking"] is True

    got = client.get(f"/api/v1/personas/{pid}")
    assert got.status_code == 200
    assert got.json()["suppress_lm_thinking"] is True

    upd = client.put(f"/api/v1/personas/{pid}", json={"suppress_lm_thinking": False})
    assert upd.status_code == 200
    assert upd.json()["suppress_lm_thinking"] is False


def test_list_palettes(client: TestClient):
    response = client.get("/api/v1/palettes/")
    assert response.status_code == 200
    data = response.json()
    assert len(data) >= len(BUILTIN_WORKFLOW_PALETTES)
    names = {p["name"] for p in data}
    for builtin in BUILTIN_WORKFLOW_PALETTES:
        assert builtin.name in names
    default = next((p for p in data if p.get("slug") == "default"), None)
    assert default is not None
    assert default.get("slug") == "default"
    assert "workflow" in default["colors"]
    assert "simple_llm_call" in default["colors"]
    assert "multimodal_llm" in default["colors"]
    assert default["colors"]["multimodal_llm"] == "#6366f1"
    assert "fetch_url" in default["colors"]
    assert default["colors"]["fetch_url"] == "#0ea5e9"
    assert "capture_url_snapshot" in default["colors"]
    assert default["colors"]["capture_url_snapshot"] == "#7c3aed"
    assert "image" in default["colors"]
    assert default["colors"]["image"] == "#f43f5e"
    assert "html_parse_basic" in default["colors"]
    assert default["colors"]["html_parse_basic"] == "#65a30d"
    assert "list_to_string" in default["colors"]
    assert "string_to_list" in default["colors"]
    assert "dictionary_value_by_key" in default["colors"]
    assert "dictionary_set_value_by_key" in default["colors"]
    assert "add_to_list" in default["colors"]
    assert "prepend_text" in default["colors"]
    assert "string_trunc" in default["colors"]
    assert "message" in default["colors"]
    assert "decision_action" in default["colors"]
    assert "basic_conditional" in default["colors"]
    assert "is_control" in default["colors"]
    assert "boolean" in default["colors"]
    assert "int" in default["colors"]
    assert "len_from_list" in default["colors"]
    assert "random_item_from_list" in default["colors"]
    assert "sandbox_pet_cell" in default["colors"]
    assert "int_to_string" in default["colors"]
    assert "add_ints" in default["colors"]
    assert "add_days" in default["colors"]
    assert "between_control" in default["colors"]
    assert isinstance(default["entries"], list)
    assert len(default["entries"]) >= 85
    assert isinstance(default["effective_colors"], dict)
    assert "string" in default["effective_colors"]
    assert isinstance(default["warnings"], list)

    slate = next((p for p in data if p.get("slug") == "slate"), None)
    assert slate is not None
    assert "primitive" in slate["colors"]


def test_get_palette_by_slug(client: TestClient):
    r = client.get("/api/v1/palettes/by-slug/default")
    assert r.status_code == 200
    body = r.json()
    assert body["slug"] == "default"
    assert body["name"] == "Default"

    assert client.get("/api/v1/palettes/by-slug/definitely-missing").status_code == 404


def test_resolve_workflow_palette_no_workflow_id_returns_default(client: TestClient):
    r = client.get("/api/v1/palettes/resolve")
    assert r.status_code == 200
    body = r.json()
    assert body.get("slug") == "default" or body.get("name") == "Default"


def test_resolve_workflow_palette_unknown_workflow_404(client: TestClient):
    r = client.get(f"/api/v1/palettes/resolve?workflow_id={uuid.uuid4()}")
    assert r.status_code == 404


def test_resolve_workflow_palette_workflow_palette_id_wins(client: TestClient):
    cp = client.post(
        "/api/v1/palettes/",
        json={
            "name": "Resolve Test Pal",
            "colors": {
                "string": "#38bdf8",
                "list": "#f472b6",
                "dictionary": "#e879f9",
                "any": "#ffffff",
                "workflow": "#14b8a6",
                "simple_llm_call": "#8b5cf6",
                "list_to_string": "#22d3ee",
                "string_to_list": "#67e8f9",
                "dictionary_value_by_key": "#9333ea",
                "prepend_text": "#f59e0b",
            },
        },
    )
    assert cp.status_code == 201
    pid = cp.json()["id"]
    wf = client.post(
        "/api/v1/workflow-definitions/",
        json={"name": "Resolve WF", "palette_id": pid, "graph": {"nodes": [], "edges": []}},
    )
    assert wf.status_code == 201
    rid = wf.json()["id"]
    r = client.get(f"/api/v1/palettes/resolve?workflow_id={rid}")
    assert r.status_code == 200
    assert r.json()["id"] == pid


def test_resolve_workflow_palette_preferred_when_workflow_has_no_palette(client: TestClient):
    cp = client.post(
        "/api/v1/palettes/",
        json={
            "name": "Preferred Pal",
            "colors": {
                "string": "#38bdf8",
                "list": "#f472b6",
                "dictionary": "#e879f9",
                "any": "#ffffff",
                "workflow": "#14b8a6",
                "simple_llm_call": "#8b5cf6",
                "list_to_string": "#22d3ee",
                "string_to_list": "#67e8f9",
                "dictionary_value_by_key": "#9333ea",
                "prepend_text": "#f59e0b",
            },
        },
    )
    assert cp.status_code == 201
    pref_id = cp.json()["id"]
    assert (
        client.put(
            "/api/v1/auth/me",
            json={"settings": {"preferred_editor_palette_id": pref_id}},
        ).status_code
        == 200
    )
    wf = client.post(
        "/api/v1/workflow-definitions/",
        json={"name": "No palette WF", "graph": {"nodes": [], "edges": []}},
    )
    assert wf.status_code == 201
    r = client.get(f"/api/v1/palettes/resolve?workflow_id={wf.json()['id']}")
    assert r.status_code == 200
    assert r.json()["id"] == pref_id


def test_create_palette(client: TestClient):
    response = client.post(
        "/api/v1/palettes/",
        json={
            "name": "My Palette",
            "colors": {
                "string": "#38bdf8",
                "list": "#f472b6",
                "dictionary": "#e879f9",
                "any": "#ffffff",
                "workflow": "#14b8a6",
                "simple_llm_call": "#8b5cf6",
                "list_to_string": "#22d3ee",
                "string_to_list": "#67e8f9",
                "dictionary_value_by_key": "#9333ea",
                "prepend_text": "#f59e0b",
            },
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "My Palette"
    assert data.get("slug") in (None, "")
    assert data["colors"]["string"] == "#38bdf8"
    assert data["colors"]["workflow"] == "#14b8a6"
    assert data["colors"]["simple_llm_call"] == "#8b5cf6"
    assert data["colors"]["list_to_string"] == "#22d3ee"
    assert data["colors"]["string_to_list"] == "#67e8f9"
    assert data["colors"]["dictionary_value_by_key"] == "#9333ea"
    assert data["colors"]["prepend_text"] == "#f59e0b"
    assert any(e["key"] == "simple_llm_call" for e in data["entries"])
    assert data["effective_colors"]["simple_llm_call"]


def test_post_palette_validate_strips_unknown_keys(client: TestClient):
    payload = {"colors": {"string": "#aabbcc", "zzz_unknown": "#001122"}}
    r = client.post("/api/v1/palettes/validate", json=payload)
    assert r.status_code == 200
    body = r.json()
    assert "string" in body["colors"]
    assert "zzz_unknown" not in body["colors"]
    assert any("stripped_unknown_palette_color_key:zzz_unknown" in w for w in body["warnings"])


def test_create_palette_rejects_unknown_colors_key(client: TestClient):
    r = client.post(
        "/api/v1/palettes/",
        json={"name": "Bad Palette", "colors": {"string": "#ffffff", "not_known": "#000"}},
    )
    assert r.status_code == 422


def test_update_palette(client: TestClient):
    create_resp = client.post(
        "/api/v1/palettes/",
        json={
            "name": "Edit Me",
            "colors": {
                "string": "#000000",
                "list": "#f472b6",
                "dictionary": "#e879f9",
                "any": "#ffffff",
                "workflow": "#14b8a6",
                "simple_llm_call": "#8b5cf6",
                "list_to_string": "#22d3ee",
                "string_to_list": "#67e8f9",
                "dictionary_value_by_key": "#9333ea",
                "prepend_text": "#f59e0b",
            },
        },
    )
    assert create_resp.status_code == 201
    pid = create_resp.json()["id"]
    response = client.put(
        f"/api/v1/palettes/{pid}",
        json={
            "name": "Updated",
            "colors": {
                "string": "#111111",
                "list": "#f472b6",
                "dictionary": "#e879f9",
                "any": "#ffffff",
                "workflow": "#14b8a6",
                "simple_llm_call": "#8b5cf6",
                "list_to_string": "#22d3ee",
                "string_to_list": "#67e8f9",
                "dictionary_value_by_key": "#9333ea",
                "prepend_text": "#f59e0b",
            },
        },
    )
    assert response.status_code == 200
    assert response.json()["name"] == "Updated"
    assert response.json()["colors"]["string"] == "#111111"


def test_delete_palette(client: TestClient):
    create_resp = client.post(
        "/api/v1/palettes/",
        json={
            "name": "To Delete",
            "colors": {
                "string": "#38bdf8",
                "list": "#f472b6",
                "dictionary": "#e879f9",
                "any": "#ffffff",
                "workflow": "#14b8a6",
                "simple_llm_call": "#8b5cf6",
                "list_to_string": "#22d3ee",
                "string_to_list": "#67e8f9",
                "dictionary_value_by_key": "#9333ea",
                "prepend_text": "#f59e0b",
            },
        },
    )
    assert create_resp.status_code == 201
    pid = create_resp.json()["id"]
    response = client.delete(f"/api/v1/palettes/{pid}")
    assert response.status_code == 204
    get_resp = client.get(f"/api/v1/palettes/{pid}")
    assert get_resp.status_code == 404


def test_list_system_palettes(client: TestClient):
    r = client.get("/api/v1/system-palettes/")
    assert r.status_code == 200
    data = r.json()
    assert len(data) >= len(BUILTIN_SYSTEM_PALETTES)
    slugs = {p.get("slug") for p in data if p.get("user_id") is None}
    for builtin in BUILTIN_SYSTEM_PALETTES:
        assert builtin.slug in slugs


def test_get_system_palette_by_slug(client: TestClient):
    r = client.get("/api/v1/system-palettes/by-slug/default")
    assert r.status_code == 200
    body = r.json()
    assert body["slug"] == "default"
    assert "light" in body["colors"]
    assert "dark" in body["colors"]

    assert client.get("/api/v1/system-palettes/by-slug/missing-slug-xyz").status_code == 404


def test_system_palette_crud_smoke(client: TestClient):
    create = client.post(
        "/api/v1/system-palettes/",
        json={
            "name": "My Theme",
            "colors": {
                "light": {"page_bg": "#ffffff"},
                "dark": {"page_bg": "#000000"},
            },
        },
    )
    assert create.status_code == 201
    tid = create.json()["id"]
    got = client.get(f"/api/v1/system-palettes/{tid}")
    assert got.status_code == 200
    assert got.json()["name"] == "My Theme"
    upd = client.put(f"/api/v1/system-palettes/{tid}", json={"name": "Renamed"})
    assert upd.status_code == 200
    assert upd.json()["name"] == "Renamed"
    assert client.delete(f"/api/v1/system-palettes/{tid}").status_code == 204
    assert client.get(f"/api/v1/system-palettes/{tid}").status_code == 404


def test_cannot_update_builtin_system_palette(client: TestClient):
    listed = client.get("/api/v1/system-palettes/").json()
    default = next(p for p in listed if p.get("slug") == "default")
    pid = default["id"]
    assert client.put(f"/api/v1/system-palettes/{pid}", json={"name": "Hax"}).status_code == 404


def test_list_structures(client: TestClient):
    response = client.get("/api/v1/structures/")
    assert response.status_code == 200
    assert response.json() == []


def test_create_structure(client: TestClient):
    schema = '{"type":"object","properties":{"joke":{"type":"string"}},"required":["joke"]}'
    response = client.post(
        "/api/v1/structures/", json={"name": "Joke", "description": "Joke response", "json_schema": schema}
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Joke"
    assert data["description"] == "Joke response"
    assert data["json_schema"] == schema


def test_update_me_settings_system_colors(client: TestClient):
    """PUT /auth/me can update user settings including system_colors."""
    system_colors = {
        "light": {"primary": "#ff0000", "page_bg": "#f0f0f0"},
        "dark": {"primary": "#00ff00"},
    }
    response = client.put(
        "/api/v1/auth/me",
        json={"settings": {"system_colors": system_colors}},
    )
    assert response.status_code == 200
    data = response.json()
    assert "settings" in data
    assert data["settings"]["system_colors"] == system_colors


def test_update_me_settings_system_palette_id(client: TestClient):
    listed = client.get("/api/v1/system-palettes/").json()
    default = next(p for p in listed if p.get("slug") == "default")
    pid = default["id"]
    r = client.put("/api/v1/auth/me", json={"settings": {"system_palette_id": pid}})
    assert r.status_code == 200
    assert r.json()["settings"]["system_palette_id"] == pid
    r_clear = client.put("/api/v1/auth/me", json={"settings": {"system_palette_id": None}})
    assert r_clear.status_code == 200
    assert r_clear.json()["settings"].get("system_palette_id") is None


def test_update_me_rejects_bad_system_palette_id(client: TestClient):
    r = client.put("/api/v1/auth/me", json={"settings": {"system_palette_id": "not-a-uuid"}})
    assert r.status_code == 422


def test_update_me_settings_theme_mode(client: TestClient):
    r = client.put("/api/v1/auth/me", json={"settings": {"theme_mode": "dark"}})
    assert r.status_code == 200
    assert r.json()["settings"]["theme_mode"] == "dark"
    r2 = client.put("/api/v1/auth/me", json={"settings": {"theme_mode": "system"}})
    assert r2.status_code == 200
    assert r2.json()["settings"]["theme_mode"] == "system"


def test_update_me_rejects_invalid_theme_mode(client: TestClient):
    r = client.put("/api/v1/auth/me", json={"settings": {"theme_mode": "purple"}})
    assert r.status_code == 422


def test_update_me_settings_workflow_editor_remember_panel_widths(client: TestClient):
    r = client.put(
        "/api/v1/auth/me",
        json={"settings": {"workflow_editor_remember_panel_widths": False}},
    )
    assert r.status_code == 200
    assert r.json()["settings"]["workflow_editor_remember_panel_widths"] is False
    r2 = client.put(
        "/api/v1/auth/me",
        json={"settings": {"workflow_editor_remember_panel_widths": True}},
    )
    assert r2.status_code == 200
    assert r2.json()["settings"]["workflow_editor_remember_panel_widths"] is True


def test_update_me_settings_auto_play_tts_on_node_end(client: TestClient):
    r = client.put(
        "/api/v1/auth/me",
        json={"settings": {"auto_play_tts_on_node_end": False}},
    )
    assert r.status_code == 200
    assert r.json()["settings"]["auto_play_tts_on_node_end"] is False
    r2 = client.put(
        "/api/v1/auth/me",
        json={"settings": {"auto_play_tts_on_node_end": True}},
    )
    assert r2.status_code == 200
    assert r2.json()["settings"]["auto_play_tts_on_node_end"] is True


def test_update_me_rejects_non_bool_auto_play_tts_on_node_end(client: TestClient):
    r = client.put(
        "/api/v1/auth/me",
        json={"settings": {"auto_play_tts_on_node_end": "yes"}},
    )
    assert r.status_code == 422


def test_update_me_settings_tts_playback_when(client: TestClient):
    r = client.put(
        "/api/v1/auth/me",
        json={"settings": {"tts_playback_when": "after_workflow"}},
    )
    assert r.status_code == 200
    assert r.json()["settings"]["tts_playback_when"] == "after_workflow"


def test_update_me_rejects_invalid_tts_playback_when(client: TestClient):
    r = client.put(
        "/api/v1/auth/me",
        json={"settings": {"tts_playback_when": "nope"}},
    )
    assert r.status_code == 422


def test_update_me_settings_gmail_workflow_filters(client: TestClient):
    r = client.put(
        "/api/v1/auth/me",
        json={
            "settings": {
                "gmail_workflow_inbox_focus": "primary",
                "gmail_workflow_exclude_categories": ["promotions", "social"],
            },
        },
    )
    assert r.status_code == 200
    s = r.json()["settings"]
    assert s["gmail_workflow_inbox_focus"] == "primary"
    assert s["gmail_workflow_exclude_categories"] == ["promotions", "social"]


def test_update_me_rejects_invalid_gmail_exclude_category(client: TestClient):
    r = client.put(
        "/api/v1/auth/me",
        json={"settings": {"gmail_workflow_exclude_categories": ["primary", "nope"]}},
    )
    assert r.status_code == 422


def test_update_me_rejects_invalid_gmail_inbox_focus(client: TestClient):
    r = client.put(
        "/api/v1/auth/me",
        json={"settings": {"gmail_workflow_inbox_focus": "spam"}},
    )
    assert r.status_code == 422


def test_update_me_settings_workflow_time_zone_system(client: TestClient):
    r = client.put("/api/v1/auth/me", json={"settings": {"workflow_time_zone": "system"}})
    assert r.status_code == 200
    assert r.json()["settings"]["workflow_time_zone"] == "system"


def test_update_me_settings_workflow_time_zone_iana(client: TestClient):
    r = client.put("/api/v1/auth/me", json={"settings": {"workflow_time_zone": "Europe/Paris"}})
    assert r.status_code == 200
    assert r.json()["settings"]["workflow_time_zone"] == "Europe/Paris"


def test_update_me_rejects_invalid_workflow_time_zone(client: TestClient):
    r = client.put("/api/v1/auth/me", json={"settings": {"workflow_time_zone": "Not/AZone"}})
    assert r.status_code == 422


def test_update_me_settings_max_concurrent_lm_studio_calls(client: TestClient):
    r = client.put("/api/v1/auth/me", json={"settings": {"max_concurrent_lm_studio_calls": 3}})
    assert r.status_code == 200
    assert r.json()["settings"]["max_concurrent_lm_studio_calls"] == 3


def test_update_me_rejects_max_concurrent_lm_studio_calls_out_of_range(client: TestClient):
    r = client.put("/api/v1/auth/me", json={"settings": {"max_concurrent_lm_studio_calls": 0}})
    assert r.status_code == 422
    r2 = client.put("/api/v1/auth/me", json={"settings": {"max_concurrent_lm_studio_calls": 33}})
    assert r2.status_code == 422


def test_update_me_rejects_max_concurrent_lm_studio_calls_non_int(client: TestClient):
    r = client.put("/api/v1/auth/me", json={"settings": {"max_concurrent_lm_studio_calls": "3"}})
    assert r.status_code == 422


def test_update_me_settings_workflow_execution_limits_prefs_sparse(client: TestClient):
    r = client.put(
        "/api/v1/auth/me",
        json={"settings": {"workflow_execution_limits_prefs": {"max_loop_iterations": 77}}},
    )
    assert r.status_code == 200
    assert r.json()["settings"]["workflow_execution_limits_prefs"] == {"max_loop_iterations": 77}


def test_update_me_workflow_execution_limits_prefs_empty_removed(client: TestClient):
    r1 = client.put(
        "/api/v1/auth/me",
        json={"settings": {"workflow_execution_limits_prefs": {"max_loop_iterations": 10}}},
    )
    assert r1.status_code == 200
    r2 = client.put("/api/v1/auth/me", json={"settings": {"workflow_execution_limits_prefs": {}}})
    assert r2.status_code == 200
    assert "workflow_execution_limits_prefs" not in r2.json()["settings"]


def test_update_me_workflow_execution_limits_prefs_null_removed(client: TestClient):
    r = client.put("/api/v1/auth/me", json={"settings": {"workflow_execution_limits_prefs": None}})
    assert r.status_code == 200
    assert "workflow_execution_limits_prefs" not in r.json()["settings"]


def test_update_me_rejects_workflow_execution_limits_prefs_above_ceiling(client: TestClient):
    ceiling = settings.WORKFLOW_EXECUTION_CEILING_MAX_LOOP_ITERATIONS + 1
    r = client.put(
        "/api/v1/auth/me",
        json={"settings": {"workflow_execution_limits_prefs": {"max_loop_iterations": ceiling}}},
    )
    assert r.status_code == 422


def test_update_me_rejects_workflow_execution_limits_prefs_not_object(client: TestClient):
    r = client.put("/api/v1/auth/me", json={"settings": {"workflow_execution_limits_prefs": "nope"}})
    assert r.status_code == 422


def test_update_me_rejects_non_bool_workflow_editor_remember_panel_widths(client: TestClient):
    r = client.put(
        "/api/v1/auth/me",
        json={"settings": {"workflow_editor_remember_panel_widths": "yes"}},
    )
    assert r.status_code == 422


def test_update_me_settings_preferred_editor_palette_id(client: TestClient):
    listed = client.get("/api/v1/palettes/").json()
    pal = next(p for p in listed if p.get("slug") == "default")
    pid = pal["id"]
    r = client.put("/api/v1/auth/me", json={"settings": {"preferred_editor_palette_id": pid}})
    assert r.status_code == 200
    assert r.json()["settings"]["preferred_editor_palette_id"] == pid
    r_clear = client.put("/api/v1/auth/me", json={"settings": {"preferred_editor_palette_id": None}})
    assert r_clear.status_code == 200
    assert r_clear.json()["settings"].get("preferred_editor_palette_id") is None


def test_update_me_rejects_bad_preferred_editor_palette_id(client: TestClient):
    r = client.put("/api/v1/auth/me", json={"settings": {"preferred_editor_palette_id": "not-uuid"}})
    assert r.status_code == 422


def test_update_me_rejects_unknown_settings_key(client: TestClient):
    response = client.put("/api/v1/auth/me", json={"settings": {"unknown_key": True}})
    assert response.status_code == 422


def test_put_me_api_keys_strips_bearer_prefix(client: TestClient):
    assert client.put("/api/v1/auth/me", json={"api_keys": {"openai": "Bearer sk-bearer-strip"}}).status_code == 200
    from sqlmodel import Session, select

    from app.core.user_api_keys_crypto import decrypt_api_keys_store
    from app.persistence.tables import User
    from tests.conftest import engine

    with Session(engine) as s:
        u = s.exec(select(User).where(User.username == "testuser")).first()
        assert u is not None
        assert decrypt_api_keys_store(u.api_keys).get("openai") == "sk-bearer-strip"


def test_put_me_api_keys_strips_surrounding_whitespace(client: TestClient):
    assert client.put("/api/v1/auth/me", json={"api_keys": {"openai": "  sk-ws-test  "}}).status_code == 200
    from sqlmodel import Session, select

    from app.core.user_api_keys_crypto import decrypt_api_keys_store
    from app.persistence.tables import User
    from tests.conftest import engine

    with Session(engine) as s:
        u = s.exec(select(User).where(User.username == "testuser")).first()
        assert u is not None
        assert decrypt_api_keys_store(u.api_keys).get("openai") == "sk-ws-test"


def test_put_me_preserves_api_key_when_client_sends_stored_placeholder(client: TestClient):
    """Masked GET uses [stored]; PUT must not overwrite the real secret with that literal."""
    assert client.put("/api/v1/auth/me", json={"api_keys": {"openai": "sk-keep-me"}}).status_code == 200
    r2 = client.put("/api/v1/auth/me", json={"api_keys": {"openai": "[stored]"}})
    assert r2.status_code == 200
    assert r2.json()["api_keys"]["openai"] == "[stored]"
    from sqlmodel import Session, select

    from app.core.user_api_keys_crypto import decrypt_api_keys_store
    from app.persistence.tables import User
    from tests.conftest import engine

    with Session(engine) as s:
        u = s.exec(select(User).where(User.username == "testuser")).first()
        assert u is not None
        assert decrypt_api_keys_store(u.api_keys).get("openai") == "sk-keep-me"


def test_put_me_api_keys_encrypted_at_rest(client: TestClient):
    """api_keys string values stored encrypted (SE-023)."""
    assert (
        client.put(
            "/api/v1/auth/me",
            json={"api_keys": {"openai": "sk-test-secret-value"}},
        ).status_code
        == 200
    )
    from sqlmodel import Session, select

    from app.persistence.tables import User
    from tests.conftest import engine

    with Session(engine) as s:
        u = s.exec(select(User).where(User.username == "testuser")).first()
        assert u is not None
        assert str(u.api_keys.get("openai", "")).startswith("v1.")
        assert "sk-test-secret" not in str(u.api_keys)
