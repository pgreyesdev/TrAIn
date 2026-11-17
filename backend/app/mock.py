"""Mock server that implements the API contract (T03) with in-memory data.

It lets the Android app (T16-T17) be built before the real backend (T13-T14)
exists. Paths, parameters and models are the contract: the real backend must
expose the same ones (``tests/test_contract.py`` checks it against
``docs/openapi.json``).

Run from ``backend/``::

    uvicorn app.mock:app --reload --port 8000

Export the OpenAPI document after changing the contract::

    python -m app.mock --export ../docs/openapi.json
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, HTTPException, Query, status

from app import schemas as s

CATALOG_CSV = Path(__file__).resolve().parents[2] / "train_datos" / "catalogo" / "ejercicios.csv"

# Same order as train_datos/simulador/catalogo.py (ids are position + 1).
MUSCLE_GROUPS = ["Pecho", "Espalda", "Cuádriceps", "Cadena posterior", "Hombro", "Brazos", "Core y gemelos"]
LOWER_BODY = {"Cuádriceps", "Cadena posterior"}

DEMO_USER_ID = 1
MOCK_MODEL_VERSION = "mock"
MAX_MESSAGES_PER_DAY = 30

NOT_FOUND = {404: {"model": s.ErrorResponse, "description": "Not found"}}

TAGS = [
    {"name": "system", "description": "Estado del servicio"},
    {"name": "catalog", "description": "Catálogo de ejercicios (capa 1)"},
    {"name": "users", "description": "Usuarios y rutina (capa 2)"},
    {"name": "sessions", "description": "Registro de sesiones y series (capa 2)"},
    {"name": "recommendations", "description": "Motor de IA: cargas, estado y fatiga"},
    {"name": "progress", "description": "Evolución por ejercicio (capa 3)"},
    {"name": "chat", "description": "Agente conversacional"},
]


def load_catalog(path: Path = CATALOG_CSV) -> list[s.Exercise]:
    exercises = []
    with path.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            group = row["grupo"]
            exercises.append(
                s.Exercise(
                    id=int(row["id"]),
                    name=row["nombre_es"],
                    name_en=row["nombre_en"] or None,
                    muscle_group=s.MuscleGroup(id=MUSCLE_GROUPS.index(group) + 1, name=group),
                    pattern=row["patron"],
                    mechanics=row["mecanica"],
                    equipment=row["equipamiento"],
                    load_type=row["tipo_carga"],
                    laterality=row["lateralidad"],
                    increment_kg=float(row["incremento_kg"]),
                    reps_min=int(row["reps_min"]) if row["reps_min"] else None,
                    reps_max=int(row["reps_max"]) if row["reps_max"] else None,
                    lower_body=group in LOWER_BODY,
                    in_load_model=row["en_modelo_carga"] == "1",
                )
            )
    return exercises


class MockStore:
    """In-memory data: one demo user with a 4-day upper/lower program."""

    def __init__(self) -> None:
        self.exercises = {e.id: e for e in load_catalog()}
        self.users: dict[int, s.User] = {}
        self.programs: dict[int, s.Program] = {}
        self.sessions: dict[int, list[s.Session]] = {}
        self.chat_count: dict[tuple[int, dt.date], int] = {}
        self._next_session_id = 10001
        self._next_set_id = 1000010001
        self.add_user(
            s.UserCreate(
                sex="H",
                birth_date=dt.date(1999, 4, 12),
                height_cm=178,
                weight_kg=76.5,
                level="intermedio",
                goal="hipertrofia",
                days_per_week=4,
            ),
            user_id=DEMO_USER_ID,
        )

    def add_user(self, data: s.UserCreate, user_id: int | None = None) -> s.User:
        user_id = user_id or max(self.users, default=0) + 1
        user = s.User(
            id=user_id,
            sex=data.sex,
            birth_date=data.birth_date,
            height_cm=data.height_cm,
            weight_kg=data.weight_kg,
            level=data.level,
            goal=data.goal,
            days_per_week=data.days_per_week,
            signup_date=dt.date.today(),
            synthetic=False,
        )
        self.users[user_id] = user
        self.programs[user_id] = self._program(user)
        self.sessions[user_id] = []
        return user

    def _program(self, user: s.User) -> s.Program:
        templates = {"A": [1, 7, 25, 9, 34], "B": [13, 20, 15, 22, 37]}
        days = []
        for day in range(1, (user.days_per_week or 2) + 1):
            ids = templates["A" if day % 2 else "B"]
            days.append(
                s.ProgramDay(
                    day=day,
                    exercises=[
                        s.ProgramExercise(
                            order=i,
                            exercise_id=eid,
                            exercise_name=self.exercises[eid].name,
                            load_type=self.exercises[eid].load_type,
                            target_sets=3,
                            target_reps=10,
                            target_rpe=8.0,
                        )
                        for i, eid in enumerate(ids, start=1)
                        if eid in self.exercises
                    ],
                )
            )
        return s.Program(
            id=user.id * 100 + 1,
            user_id=user.id,
            split="torso_pierna",
            start_date=user.signup_date,
            days=days,
            next_day=1,
        )

    def user(self, user_id: int) -> s.User:
        if user_id not in self.users:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"Usuario {user_id} no encontrado")
        return self.users[user_id]

    def exercise(self, exercise_id: int) -> s.Exercise:
        if exercise_id not in self.exercises:
            raise HTTPException(status.HTTP_404_NOT_FOUND, f"Ejercicio {exercise_id} no encontrado")
        return self.exercises[exercise_id]

    def next_day(self, user_id: int) -> int:
        program = self.programs[user_id]
        last = next((x.program_day for x in reversed(self.sessions[user_id]) if x.program_day), None)
        return 1 if last is None else last % len(program.days) + 1

    def add_session(self, data: s.SessionCreate) -> s.Session:
        self.user(data.user_id)
        for st in data.sets:
            self.exercise(st.exercise_id)
        sets = []
        for st in data.sets:
            sets.append(s.SetOut(id=self._next_set_id, **st.model_dump()))
            self._next_set_id += 1
        session = s.Session(id=self._next_session_id, sets=sets, **data.model_dump(exclude={"sets"}))
        self._next_session_id += 1
        self.sessions[data.user_id].append(session)
        self.sessions[data.user_id].sort(key=lambda x: x.date)
        return session

    def last_top_set(self, user_id: int, exercise_id: int) -> tuple[dt.date, float] | None:
        for session in reversed(self.sessions[user_id]):
            loads = [
                st.load_kg if st.load_kg is not None else st.added_kg
                for st in session.sets
                if st.exercise_id == exercise_id and st.type != "calentamiento"
            ]
            loads = [x for x in loads if x is not None]
            if loads:
                return session.date, max(loads)
        return None


store = MockStore()

app = FastAPI(
    title="TrAIn API",
    version=s.API_VERSION,
    summary="Contrato entre la app Android y el backend de TrAIn (T03).",
    description="Servidor simulado: datos en memoria y recomendaciones fijas. Ver docs/api.md.",
    openapi_tags=TAGS,
)


@app.get("/health", response_model=s.Health, tags=["system"])
def health() -> s.Health:
    return s.Health(
        status="ok",
        api_version=s.API_VERSION,
        database=True,
        models_loaded=True,
        model_version=MOCK_MODEL_VERSION,
        llm_configured=False,
    )


@app.get("/catalog/exercises", response_model=list[s.Exercise], tags=["catalog"])
def list_exercises() -> list[s.Exercise]:
    return list(store.exercises.values())


@app.get("/catalog/muscle-groups", response_model=list[s.MuscleGroup], tags=["catalog"])
def list_muscle_groups() -> list[s.MuscleGroup]:
    return [s.MuscleGroup(id=i, name=n) for i, n in enumerate(MUSCLE_GROUPS, start=1)]


@app.post("/users", response_model=s.User, status_code=status.HTTP_201_CREATED, tags=["users"])
def create_user(data: s.UserCreate) -> s.User:
    return store.add_user(data)


@app.get("/users/{user_id}", response_model=s.User, responses=NOT_FOUND, tags=["users"])
def get_user(user_id: int) -> s.User:
    return store.user(user_id)


@app.get("/users/{user_id}/program", response_model=s.Program, responses=NOT_FOUND, tags=["users"])
def get_program(user_id: int) -> s.Program:
    store.user(user_id)
    return store.programs[user_id].model_copy(update={"next_day": store.next_day(user_id)})


@app.post(
    "/sessions",
    response_model=s.Session,
    status_code=status.HTTP_201_CREATED,
    responses=NOT_FOUND,
    tags=["sessions"],
)
def create_session(data: s.SessionCreate) -> s.Session:
    return store.add_session(data)


@app.get("/users/{user_id}/sessions", response_model=list[s.Session], responses=NOT_FOUND, tags=["sessions"])
def list_sessions(
    user_id: int,
    date_from: Annotated[dt.date | None, Query(alias="from")] = None,
    date_to: Annotated[dt.date | None, Query(alias="to")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 20,
) -> list[s.Session]:
    store.user(user_id)
    found = [
        x
        for x in reversed(store.sessions[user_id])
        if (date_from is None or x.date >= date_from) and (date_to is None or x.date <= date_to)
    ]
    return found[:limit]


@app.get(
    "/users/{user_id}/recommendations",
    response_model=s.Recommendation,
    responses=NOT_FOUND,
    tags=["recommendations"],
)
def get_recommendations(
    user_id: int,
    date: Annotated[dt.date | None, Query(description="Default: today")] = None,
    program_day: Annotated[int | None, Query(ge=1, le=7, description="Default: program next_day")] = None,
    sleep: Annotated[int | None, Query(ge=1, le=3)] = None,
    body: Annotated[int | None, Query(ge=1, le=3)] = None,
    energy: Annotated[int | None, Query(ge=1, le=3)] = None,
    extra_activity: Annotated[int | None, Query(ge=0, le=2)] = None,
    pain: Annotated[bool | None, Query()] = None,
    pain_zone_id: Annotated[int | None, Query(ge=1)] = None,
) -> s.Recommendation:
    store.user(user_id)
    questionnaire = s.Questionnaire(
        sleep=sleep,
        body=body,
        energy=energy,
        extra_activity=extra_activity,
        pain=pain,
        pain_zone_id=pain_zone_id,
    )
    answered = any(v is not None for v in questionnaire.model_dump().values())
    day = program_day or store.next_day(user_id)
    program = store.programs[user_id]
    prescription = next((d for d in program.days if d.day == day), program.days[0])

    if pain or body == 3 or sleep == 1:
        status_, probs, fatigue = "suave", (0.25, 0.55, 0.20), 61.0
        text = (
            "Hoy conviene entrenar suave: bajamos un poco las cargas. "
            "Si el dolor sigue, consulta a un profesional."
        )
        change = -2.5
    else:
        status_, probs, fatigue = "entrenar", (0.72, 0.20, 0.08), 38.0
        text = "Tu fatiga es moderada y has descansado: puedes entrenar con normalidad y subir algo de carga."
        change = 2.5

    loads = []
    for pe in prescription.exercises:
        ex = store.exercises[pe.exercise_id]
        last = store.last_top_set(user_id, ex.id) if ex.in_load_model else None
        suggested = None if last is None else max(0.0, last[1] + change)
        loads.append(
            s.LoadRecommendation(
                exercise_id=ex.id,
                exercise_name=ex.name,
                load_type=ex.load_type,
                target_sets=pe.target_sets,
                target_reps=pe.target_reps,
                target_rpe=pe.target_rpe,
                last_date=last[0] if last else None,
                last_load_kg=last[1] if last else None,
                change_kg=change if last else None,
                suggested_load_kg=suggested,
                capped=False,
            )
        )
    return s.Recommendation(
        user_id=user_id,
        date=date or dt.date.today(),
        program_day=day,
        status=status_,
        status_probabilities=s.StatusProbabilities(entrenar=probs[0], suave=probs[1], descansar=probs[2]),
        fatigue=fatigue,
        loads=loads,
        explanation=text,
        questionnaire_used=answered,
        model_version=MOCK_MODEL_VERSION,
        generated_at=dt.datetime.now(dt.UTC),
    )


@app.get("/users/{user_id}/progress", response_model=s.Progress, responses=NOT_FOUND, tags=["progress"])
def get_progress(
    user_id: int,
    exercise_id: Annotated[int, Query()],
    date_from: Annotated[dt.date | None, Query(alias="from")] = None,
    date_to: Annotated[dt.date | None, Query(alias="to")] = None,
) -> s.Progress:
    store.user(user_id)
    ex = store.exercise(exercise_id)
    points = []
    for session in store.sessions[user_id]:
        if (date_from and session.date < date_from) or (date_to and session.date > date_to):
            continue
        sets = [
            x
            for x in session.sets
            if x.exercise_id == exercise_id and x.type != "calentamiento" and x.load_kg and x.reps
        ]
        if not sets:
            continue
        top = max(sets, key=lambda x: (x.load_kg, x.reps))
        rir = 10 - (top.rpe or 10)
        points.append(
            s.ProgressPoint(
                date=session.date,
                session_id=session.id,
                e1rm=round(top.load_kg * (1 + (top.reps + rir) / 30), 1),
                top_load_kg=top.load_kg,
                top_reps=top.reps,
                top_rpe=top.rpe,
                volume_kg=sum(x.load_kg * x.reps for x in sets),
                working_sets=len(sets),
            )
        )
    return s.Progress(user_id=user_id, exercise_id=ex.id, exercise_name=ex.name, points=points)


@app.post("/chat", response_model=s.ChatResponse, responses=NOT_FOUND, tags=["chat"])
def chat(data: s.ChatRequest) -> s.ChatResponse:
    store.user(data.user_id)
    key = (data.user_id, dt.date.today())
    used = store.chat_count.get(key, 0)
    if used >= MAX_MESSAGES_PER_DAY:
        return s.ChatResponse(
            status="limit_reached",
            reply="Has llegado al límite de mensajes de hoy. Vuelve mañana.",
            messages_left_today=0,
        )
    store.chat_count[key] = used + 1
    return s.ChatResponse(
        status="ok",
        reply="(Respuesta simulada) Soy el entrenador de TrAIn. Cuando el agente esté listo, "
        "te explicaré tus recomendaciones con tus datos.",
        tools_used=[],
        messages_left_today=MAX_MESSAGES_PER_DAY - used - 1,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--export", type=Path, help="Write the OpenAPI document to this path")
    args = parser.parse_args()
    if args.export:
        args.export.write_text(
            json.dumps(app.openapi(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"OpenAPI escrito en {args.export}")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
