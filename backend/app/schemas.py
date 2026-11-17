"""API contract between the Android app and the backend (T03).

These Pydantic models are the single source of truth for the JSON the API
accepts and returns. FastAPI turns them into the OpenAPI document served at
``/docs`` and exported to ``docs/openapi.json``; ``docs/api.md`` explains them.

Conventions:
- JSON field names are English ``snake_case``. Enumerated *values* keep the
  Spanish values stored in PostgreSQL (``entrenar``, ``hipertrofia``...), so the
  backend never translates them and the app maps them to labels.
- Dates are ISO 8601 strings (``YYYY-MM-DD``); timestamps include the offset.
- Loads are in kg. Dumbbells: weight of each one. Unilateral: per side.
- Optional fields are ``null`` when unknown, never omitted in responses.
"""

from __future__ import annotations

import datetime as dt
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

API_VERSION = "1.0.0"

# ---------------------------------------------------------------------------
# Enumerations (values match the CHECK constraints of schema_postgres.sql)
# ---------------------------------------------------------------------------


class Sex(StrEnum):
    male = "H"
    female = "M"
    other = "otro"


class Level(StrEnum):
    beginner = "principiante"
    intermediate = "intermedio"
    advanced = "avanzado"


class Goal(StrEnum):
    strength = "fuerza"
    hypertrophy = "hipertrofia"
    maintenance = "mantenimiento"
    fat_loss = "perdida_grasa"


class Split(StrEnum):
    full_body = "full_body"
    upper_lower = "torso_pierna"
    ppl = "ppl"
    weider = "weider"
    other = "otro"


class Mechanics(StrEnum):
    compound = "compuesto"
    isolation = "aislamiento"


class LoadType(StrEnum):
    external = "externa"
    bodyweight = "corporal"
    weighted_bodyweight = "corporal_lastre"
    assisted = "asistida"
    time = "tiempo"
    carry = "transporte"


class Laterality(StrEnum):
    bilateral = "bilateral"
    unilateral = "unilateral"


class SetType(StrEnum):
    warmup = "calentamiento"
    working = "efectiva"
    drop = "descendente"
    failure = "fallo"


class DayStatus(StrEnum):
    train = "entrenar"
    light = "suave"
    rest = "descansar"


class ChatRole(StrEnum):
    user = "user"
    assistant = "assistant"


class ChatStatus(StrEnum):
    ok = "ok"
    no_api_key = "no_api_key"
    limit_reached = "limit_reached"
    error = "error"


# ---------------------------------------------------------------------------
# Reusable field types
# ---------------------------------------------------------------------------

Rating3 = Annotated[int, Field(ge=1, le=3)]
Kg = Annotated[float, Field(ge=0, le=1000)]


def _check_rpe(value: float | None) -> float | None:
    """RPE from 6 to 10 in steps of 0.5 (same rule as formulas.rpe_app)."""
    if value is None:
        return value
    if not 6 <= value <= 10 or (value * 2) != int(value * 2):
        raise ValueError("RPE must be between 6 and 10 in steps of 0.5")
    return value


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=True)


# ---------------------------------------------------------------------------
# Errors and health
# ---------------------------------------------------------------------------


class ErrorResponse(ApiModel):
    """Body of every 4xx/5xx error except 422 (FastAPI validation format)."""

    detail: str = Field(examples=["Usuario 999 no encontrado"])


class Health(ApiModel):
    status: str = Field(examples=["ok"])
    api_version: str = Field(examples=[API_VERSION])
    database: bool = Field(description="PostgreSQL reachable")
    models_loaded: bool = Field(description="AI engine artifacts loaded")
    model_version: str | None = Field(examples=["2026.12.01-xgb"])
    llm_configured: bool = Field(description="An LLM API key is configured")


# ---------------------------------------------------------------------------
# Catalog (layer 1)
# ---------------------------------------------------------------------------


class MuscleGroup(ApiModel):
    id: int
    name: str = Field(examples=["Pecho"])


class Exercise(ApiModel):
    id: int = Field(examples=[1])
    name: str = Field(description="Spanish name (nombre_es)", examples=["Press banca con barra"])
    name_en: str | None = Field(examples=["Barbell Bench Press"])
    muscle_group: MuscleGroup
    pattern: str = Field(examples=["empuje_horizontal"])
    mechanics: Mechanics
    equipment: str = Field(examples=["barra"])
    load_type: LoadType
    laterality: Laterality
    increment_kg: float = Field(examples=[2.5])
    reps_min: int | None = Field(examples=[3])
    reps_max: int | None = Field(examples=[10])
    lower_body: bool = Field(description="Uses the lower-body safety cap (+5 kg)")
    in_load_model: bool = Field(description="The AI engine suggests loads for it")


# ---------------------------------------------------------------------------
# Users (layer 2)
# ---------------------------------------------------------------------------


class UserCreate(ApiModel):
    sex: Sex | None = None
    birth_date: dt.date | None = Field(default=None, examples=["1999-04-12"])
    height_cm: float | None = Field(default=None, ge=100, le=250, examples=[178])
    weight_kg: float = Field(ge=30, le=300, examples=[76.5], description="Stored in medida_corporal")
    level: Level
    goal: Goal
    days_per_week: int = Field(
        ge=2, le=6, examples=[4], description="2-6: the backend builds the program with programas.py"
    )


class User(ApiModel):
    id: int = Field(examples=[1])
    sex: Sex | None
    birth_date: dt.date | None
    height_cm: float | None
    weight_kg: float | None = Field(description="Latest body measurement")
    level: Level
    goal: Goal
    days_per_week: int | None
    signup_date: dt.date
    synthetic: bool = Field(description="Created by the simulator")


# ---------------------------------------------------------------------------
# Program (layer 2)
# ---------------------------------------------------------------------------


class ProgramExercise(ApiModel):
    order: int = Field(examples=[1])
    exercise_id: int = Field(examples=[1])
    exercise_name: str = Field(examples=["Press banca con barra"])
    load_type: LoadType
    target_sets: int = Field(examples=[3])
    target_reps: int | None = Field(description="Seconds when load_type is 'tiempo'", examples=[8])
    target_rpe: float | None = Field(examples=[8.0])


class ProgramDay(ApiModel):
    day: int = Field(ge=1, le=7, examples=[1])
    exercises: list[ProgramExercise]


class Program(ApiModel):
    id: int = Field(examples=[101])
    user_id: int
    split: Split
    start_date: dt.date
    days: list[ProgramDay]
    next_day: int = Field(
        ge=1, le=7, description="Routine day due today: the one after the last session's day, cyclic"
    )


# ---------------------------------------------------------------------------
# Sessions and sets (layer 2)
# ---------------------------------------------------------------------------


class Questionnaire(ApiModel):
    """Short pre-workout questionnaire. Every answer is optional (null = not answered)."""

    sleep: Rating3 | None = Field(default=None, description="1 mal, 2 normal, 3 bien")
    body: Rating3 | None = Field(default=None, description="1 fresco, 2 algo cargado, 3 muy cargado")
    energy: Rating3 | None = Field(default=None, description="1 baja, 2 normal, 3 alta")
    extra_activity: int | None = Field(
        default=None, ge=0, le=2, description="Other sport yesterday: 0 no, 1 suave, 2 intenso"
    )
    pain: bool | None = None
    pain_zone_id: int | None = Field(default=None, description="muscle_group id; requires pain=true")

    @model_validator(mode="after")
    def _zone_requires_pain(self) -> Questionnaire:
        if self.pain_zone_id is not None and not self.pain:
            raise ValueError("pain_zone_id requires pain=true")
        return self


class SetIn(ApiModel):
    exercise_id: int = Field(examples=[1])
    exercise_order: int = Field(ge=1, examples=[1], description="Position of the exercise in the session")
    set_number: int = Field(ge=1, examples=[1])
    type: SetType = SetType.working
    target_reps: int | None = Field(default=None, ge=0)
    reps: int | None = Field(default=None, ge=0, le=100, examples=[8])
    load_kg: Kg | None = Field(default=None, examples=[80.0], description="'externa' exercises")
    added_kg: Kg | None = Field(default=None, description="Extra weight, 'corporal_lastre'")
    assistance_kg: Kg | None = Field(default=None, description="'asistida' exercises")
    duration_s: int | None = Field(default=None, ge=0, description="'tiempo' exercises")
    distance_m: float | None = Field(default=None, ge=0)
    rpe: float | None = Field(default=None, examples=[8.0], description="6-10, steps of 0.5")
    completed: bool = True

    _rpe = field_validator("rpe")(_check_rpe)


class SetOut(SetIn):
    id: int = Field(examples=[100000101])


class SessionCreate(ApiModel):
    user_id: int = Field(examples=[1])
    program_id: int | None = Field(default=None, examples=[101])
    program_day: int | None = Field(default=None, ge=1, le=7, examples=[1])
    date: dt.date = Field(examples=["2026-11-17"])
    start_time: dt.time | None = Field(default=None, examples=["18:30:00"])
    duration_min: int | None = Field(default=None, ge=0, le=600, examples=[65])
    questionnaire: Questionnaire | None = None
    session_hardness: int | None = Field(
        default=None, ge=1, le=4, description="1 fácil, 2 moderada, 3 dura, 4 al límite"
    )
    notes: str | None = Field(default=None, max_length=1000)
    sets: list[SetIn] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique_sets(self) -> SessionCreate:
        keys = [(s.exercise_order, s.set_number) for s in self.sets]
        if len(keys) != len(set(keys)):
            raise ValueError("(exercise_order, set_number) must be unique within a session")
        return self


class Session(ApiModel):
    id: int = Field(examples=[10001])
    user_id: int
    program_id: int | None
    program_day: int | None
    date: dt.date
    start_time: dt.time | None
    duration_min: int | None
    questionnaire: Questionnaire | None
    session_hardness: int | None
    notes: str | None
    sets: list[SetOut]


# ---------------------------------------------------------------------------
# Recommendations (AI engine; stored in `recomendacion`)
# ---------------------------------------------------------------------------


class StatusProbabilities(ApiModel):
    entrenar: float = Field(ge=0, le=1)
    suave: float = Field(ge=0, le=1)
    descansar: float = Field(ge=0, le=1)


class LoadRecommendation(ApiModel):
    exercise_id: int = Field(examples=[1])
    exercise_name: str = Field(examples=["Press banca con barra"])
    load_type: LoadType
    target_sets: int = Field(examples=[3])
    target_reps: int | None = Field(examples=[8])
    target_rpe: float | None = Field(examples=[8.0])
    last_date: dt.date | None = Field(description="Last session with this exercise")
    last_load_kg: float | None = Field(
        examples=[80.0], description="Last top working load, in the field the user logs"
    )
    change_kg: float | None = Field(
        examples=[2.5], description="Predicted change of the effective load, rounded to the increment"
    )
    suggested_load_kg: float | None = Field(
        examples=[82.5], description="Value to log next: load_kg, added_kg or assistance_kg"
    )
    capped: bool = Field(description="tope_seguridad lowered the prediction")


class Recommendation(ApiModel):
    user_id: int = Field(examples=[1])
    date: dt.date = Field(examples=["2026-11-17"])
    program_day: int | None = Field(examples=[1])
    status: DayStatus
    status_probabilities: StatusProbabilities
    fatigue: float = Field(ge=0, le=100, examples=[42.0])
    loads: list[LoadRecommendation]
    explanation: str = Field(
        max_length=500,
        examples=["Has dormido bien y tu fatiga es moderada: puedes entrenar con normalidad."],
    )
    questionnaire_used: bool
    model_version: str = Field(examples=["2026.12.01-xgb"])
    generated_at: dt.datetime


# ---------------------------------------------------------------------------
# Progress (from rendimiento_ejercicio)
# ---------------------------------------------------------------------------


class ProgressPoint(ApiModel):
    date: dt.date
    session_id: int
    e1rm: float | None = Field(description="Estimated 1RM (Epley + RIR), effective load")
    top_load_kg: float | None = Field(description="carga_efectiva_top")
    top_reps: int | None
    top_rpe: float | None
    volume_kg: float | None
    working_sets: int | None


class Progress(ApiModel):
    user_id: int
    exercise_id: int
    exercise_name: str
    points: list[ProgressPoint] = Field(description="Oldest first")


# ---------------------------------------------------------------------------
# Chat (agent)
# ---------------------------------------------------------------------------


class ChatMessage(ApiModel):
    role: ChatRole
    content: str = Field(min_length=1, max_length=4000)


class ChatRequest(ApiModel):
    user_id: int = Field(examples=[1])
    message: str = Field(min_length=1, max_length=2000, examples=["¿Por qué me bajas el press banca?"])
    history: list[ChatMessage] = Field(
        default_factory=list, max_length=20, description="Previous turns, oldest first"
    )


class ChatResponse(ApiModel):
    status: ChatStatus
    reply: str = Field(description="Always a Spanish text the app can show as is")
    tools_used: list[str] = Field(default_factory=list, examples=[["get_recommendation"]])
    messages_left_today: int = Field(ge=0, examples=[29])
