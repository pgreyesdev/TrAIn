"""Tests for the API contract (T03): schemas, mock server and exported OpenAPI."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app import mock, schemas

OPENAPI_PATH = Path(__file__).resolve().parents[2] / "docs" / "openapi.json"

EXPECTED_ROUTES = {
    ("GET", "/health"),
    ("GET", "/catalog/exercises"),
    ("GET", "/catalog/muscle-groups"),
    ("POST", "/users"),
    ("GET", "/users/{user_id}"),
    ("GET", "/users/{user_id}/program"),
    ("POST", "/sessions"),
    ("GET", "/users/{user_id}/sessions"),
    ("GET", "/users/{user_id}/recommendations"),
    ("GET", "/users/{user_id}/progress"),
    ("POST", "/chat"),
}


@pytest.fixture()
def client() -> TestClient:
    mock.store = mock.MockStore()
    return TestClient(mock.app)


def session_body(**overrides) -> dict:
    body = {
        "user_id": mock.DEMO_USER_ID,
        "program_id": 101,
        "program_day": 1,
        "date": "2026-11-16",
        "duration_min": 60,
        "questionnaire": {"sleep": 3, "body": 1, "energy": 2, "extra_activity": 0, "pain": False},
        "session_hardness": 3,
        "sets": [
            {"exercise_id": 1, "exercise_order": 1, "set_number": 1, "reps": 8, "load_kg": 80, "rpe": 8},
            {"exercise_id": 1, "exercise_order": 1, "set_number": 2, "reps": 8, "load_kg": 80, "rpe": 8.5},
        ],
    }
    body.update(overrides)
    return body


# --- OpenAPI ---------------------------------------------------------------


def test_routes_match_contract() -> None:
    paths = mock.app.openapi()["paths"]
    routes = {(m.upper(), p) for p, ops in paths.items() for m in ops}
    assert routes == EXPECTED_ROUTES


def _shape(openapi: dict) -> dict:
    """Routes, parameters and model fields: what the app relies on.

    Ignores details that change between FastAPI versions (titles, ordering...).
    """
    routes = {
        f"{m.upper()} {p}": sorted(x["name"] for x in op.get("parameters", []))
        for p, ops in openapi["paths"].items()
        for m, op in ops.items()
    }
    models = {
        name: sorted(schema.get("properties", {}))
        for name, schema in openapi["components"]["schemas"].items()
        if not name.startswith(("HTTPValidationError", "ValidationError"))
    }
    return {"version": openapi["info"]["version"], "routes": routes, "models": models}


def test_exported_openapi_is_up_to_date() -> None:
    exported = json.loads(OPENAPI_PATH.read_text(encoding="utf-8"))
    assert _shape(exported) == _shape(mock.app.openapi()), (
        "docs/openapi.json is stale: run `python -m app.mock --export ../docs/openapi.json`"
    )


# --- Schemas ---------------------------------------------------------------


@pytest.mark.parametrize("rpe", [6, 6.5, 8, 9.5, 10])
def test_rpe_valid(rpe: float) -> None:
    assert schemas.SetIn(exercise_id=1, exercise_order=1, set_number=1, rpe=rpe).rpe == rpe


@pytest.mark.parametrize("rpe", [5.5, 7.25, 10.5])
def test_rpe_invalid(rpe: float) -> None:
    with pytest.raises(ValidationError):
        schemas.SetIn(exercise_id=1, exercise_order=1, set_number=1, rpe=rpe)


def test_pain_zone_requires_pain() -> None:
    with pytest.raises(ValidationError):
        schemas.Questionnaire(pain=False, pain_zone_id=2)
    assert schemas.Questionnaire(pain=True, pain_zone_id=2).pain_zone_id == 2


def test_questionnaire_ranges() -> None:
    with pytest.raises(ValidationError):
        schemas.Questionnaire(sleep=4)
    with pytest.raises(ValidationError):
        schemas.Questionnaire(extra_activity=3)


def test_session_rejects_duplicate_sets() -> None:
    body = session_body()
    body["sets"][1]["set_number"] = 1
    with pytest.raises(ValidationError):
        schemas.SessionCreate(**body)


def test_unknown_fields_rejected() -> None:
    with pytest.raises(ValidationError):
        schemas.ChatRequest(user_id=1, message="hola", extra=1)


def test_day_status_values() -> None:
    assert [x.value for x in schemas.DayStatus] == ["entrenar", "suave", "descansar"]


# --- Mock server -----------------------------------------------------------


def test_health(client: TestClient) -> None:
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["api_version"] == schemas.API_VERSION


def test_catalog(client: TestClient) -> None:
    exercises = client.get("/catalog/exercises").json()
    assert len(exercises) == 42
    bench = next(e for e in exercises if e["id"] == 1)
    assert bench["muscle_group"] == {"id": 1, "name": "Pecho"}
    assert bench["lower_body"] is False
    groups = client.get("/catalog/muscle-groups").json()
    assert len(groups) == 7


def test_create_and_get_user(client: TestClient) -> None:
    payload = {"weight_kg": 70, "level": "principiante", "goal": "fuerza", "days_per_week": 3}
    created = client.post("/users", json=payload)
    assert created.status_code == 201
    user = created.json()
    assert client.get(f"/users/{user['id']}").json() == user
    program = client.get(f"/users/{user['id']}/program").json()
    assert len(program["days"]) == 3


def test_create_user_validation(client: TestClient) -> None:
    payload = {"weight_kg": 70, "level": "experto", "goal": "fuerza", "days_per_week": 3}
    assert client.post("/users", json=payload).status_code == 422


def test_unknown_user_is_404(client: TestClient) -> None:
    response = client.get("/users/999")
    assert response.status_code == 404
    assert response.json() == {"detail": "Usuario 999 no encontrado"}


def test_session_roundtrip(client: TestClient) -> None:
    created = client.post("/sessions", json=session_body())
    assert created.status_code == 201
    session = created.json()
    assert len(session["sets"]) == 2 and all("id" in st for st in session["sets"])
    listed = client.get(f"/users/{mock.DEMO_USER_ID}/sessions").json()
    assert listed == [session]
    assert client.get(f"/users/{mock.DEMO_USER_ID}/program").json()["next_day"] == 2


def test_session_bad_rpe_is_422(client: TestClient) -> None:
    body = session_body()
    body["sets"][0]["rpe"] = 7.3
    assert client.post("/sessions", json=body).status_code == 422


def test_recommendations(client: TestClient) -> None:
    client.post("/sessions", json=session_body())
    url = f"/users/{mock.DEMO_USER_ID}/recommendations"
    rec = client.get(url, params={"program_day": 1}).json()
    assert rec["status"] in {"entrenar", "suave", "descansar"}
    assert 0 <= rec["fatigue"] <= 100
    assert rec["questionnaire_used"] is False
    bench = next(x for x in rec["loads"] if x["exercise_id"] == 1)
    assert bench["last_load_kg"] == 80
    assert bench["suggested_load_kg"] == bench["last_load_kg"] + bench["change_kg"]

    rec = client.get(url, params={"program_day": 1, "pain": True, "pain_zone_id": 1}).json()
    assert rec["status"] == "suave" and rec["questionnaire_used"] is True


def test_progress(client: TestClient) -> None:
    client.post("/sessions", json=session_body())
    progress = client.get(f"/users/{mock.DEMO_USER_ID}/progress", params={"exercise_id": 1}).json()
    assert progress["exercise_name"] == "Press banca con barra"
    (point,) = progress["points"]
    assert point["top_load_kg"] == 80 and point["working_sets"] == 2


def test_chat(client: TestClient) -> None:
    body = {"user_id": mock.DEMO_USER_ID, "message": "¿Subo peso hoy?", "history": []}
    reply = client.post("/chat", json=body).json()
    assert reply["status"] == "ok"
    assert reply["messages_left_today"] == mock.MAX_MESSAGES_PER_DAY - 1


def test_chat_limit(client: TestClient) -> None:
    body = {"user_id": mock.DEMO_USER_ID, "message": "hola"}
    for _ in range(mock.MAX_MESSAGES_PER_DAY):
        client.post("/chat", json=body)
    reply = client.post("/chat", json=body)
    assert reply.status_code == 200
    assert reply.json()["status"] == "limit_reached"
