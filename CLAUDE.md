# TrAIn — Entrenador personal con IA (MVP)

Proyecto académico de Pablo García de los Reyes (coordinación, agente y app), Sergio Rosales Calzadilla (datos, registro y backend) y Adrián Hernández Herrera (Motor de IA y módulo de reglas). Universidad de La Laguna, 2026/27. Presentación: **13/01/2027**; MVP congelado el **20/12/2026**.

App Android que actúa como entrenador personal de gimnasio:
- Un **Motor de IA** con tres modelos: cambio de carga para la próxima sesión, estado del día (entrenar / suave / descansar) y fatiga 0–100.
- Un **agente conversacional** (LLM por API, Claude u OpenAI) que responde dudas y explica las recomendaciones consultando los datos del usuario.

## Arquitectura

```
App Android (Kotlin + Jetpack Compose)
        │  HTTP/JSON
        ▼
Backend (Python + FastAPI)
   ├── PostgreSQL 16 (capas 1-3; en Docker)
   ├── Motor de IA (modelos entrenados offline con los Parquet)
   └── Agente (API de Claude u OpenAI, con herramientas)
```

Regla de seguridad obligatoria: **la clave de la API del LLM solo vive en el backend** (`.env`, nunca en el repositorio ni en la app). La app nunca llama directamente al proveedor del LLM.

## Estado actual

`train_datos/` está **hecho y validado** (T04–T06, 25/10/2026). No reescribirlo ni sustituirlo: se amplía y se reutiliza.

- `simulador/`: simulación día a día de usuarios sintéticos (`motor.py`), catálogo de 42 ejercicios (`catalogo.py` + `catalogo/ejercicios.csv`), rutinas (`programas.py`), fórmulas (`formulas.py`), tablas derivadas (`derivados.py`) y E/S (`salida.py`).
- `generar.py`: genera los datos en Parquet por lotes.
- `cargar_postgres.py` + `sql/schema_postgres.sql`: esquema de 14 tablas y carga en PostgreSQL.
- `validar.py`: modelos sencillos de referencia y líneas base. Es el punto de partida del Motor de IA, no el Motor.

## Modelo de datos (no cambiar sin acordarlo)

Capas:
1. **Catálogo:** `grupo_muscular`, `musculo`, `patron_movimiento`, `ejercicio`, `ejercicio_musculo`.
2. **Registro:** `usuario`, `medida_corporal`, `programa`, `programa_ejercicio`, `sesion` (con cuestionario), `serie`.
3. **Derivados:** `rendimiento_ejercicio`, `estado_diario`; más `recomendacion` para guardar lo que devuelve el Motor.
4. **Simulación y etiquetas** (solo Parquet, nunca en la BD): `sim_*`, `etiquetas_carga`, `etiquetas_dia`.

Convenciones:
- Cargas en kg; mancuernas = peso de cada una; unilaterales = por lado. Dominadas con `lastre_kg`; asistidas con `asistencia_kg`.
- RPE de 6 a 10 en pasos de 0,5.
- `estado_diario` describe el estado al **empezar** el día con datos hasta el día anterior (sin fuga de información).
- Clases de estado: exactamente `entrenar`, `suave`, `descansar`.
- El backend calcula la capa 3 con **las mismas funciones** de `simulador/derivados.py` y `simulador/formulas.py` que el entrenamiento. No duplicar fórmulas.
- Regla de seguridad de cargas: `formulas.tope_seguridad` (+5 % como máximo; hasta +2,5 kg tren superior y +5 kg tren inferior).

## Estructura del repositorio

```
train/
├── CLAUDE.md
├── README.md
├── docker-compose.yml        # PostgreSQL 16 (+ backend)
├── .gitignore                # .env, datos/, *.parquet, modelos entrenados, build/ de Android
├── train_datos/              # simulador, esquema SQL, carga y validación (existente)
├── ml/                       # Motor de IA (Adrián)
│   ├── features.py           # variables a partir de capas 2-3 (partiendo de validar.py)
│   ├── train.py              # entrena los tres modelos y guarda los artefactos
│   └── evaluate.py           # métricas frente a líneas base, sobre usuarios no vistos
├── backend/                  # FastAPI (Sergio; endpoints del agente: Pablo)
│   ├── .env.example          # DATABASE_URL, LLM_PROVIDER, ANTHROPIC_API_KEY, OPENAI_API_KEY, LLM_MODEL, MAX_MESSAGES_PER_DAY
│   └── app/
│       ├── main.py, db.py, schemas.py   # schemas.py = contrato de la API (T03)
│       ├── mock.py           # servidor simulado del contrato
│       ├── routers/          # usuarios, sesiones/series, recomendaciones, progreso, chat
│       ├── ml/predictor.py   # carga modelos; usa ml/features.py y train_datos/simulador
│       ├── agent/            # llm.py (Claude/OpenAI intercambiable), tools.py, prompts.py, knowledge/
│       └── rules/nutrition.py  # opcional
└── android/                  # Kotlin + Jetpack Compose (Pablo)
```

## Pendiente en datos (T07–T08, Sergio)

- ~~La regla `MAX_DIAS_SEGUIDOS = 5` choca con la rutina de 6 días (PPL)~~: hecho (`fixed T04`), ahora es 6 para todos.
- ~~Fijar la semilla por usuario~~: hecho (`fixed T05`). Cada usuario se siembra con `(semilla, id)`.
- Generar el dataset de entrenamiento: `python generar.py --usuarios 10000`.
- PostgreSQL en Docker y BD de demo con `--lotes 1` (200 usuarios; unos 0,85 GB por cada 1.000 usuarios).
- Cargar todos los datos sintéticos **antes** de que la app inserte datos: los ids nuevos siguen el mismo patrón que los simulados.
- Tras cambiar parámetros del simulador, volver a ejecutar `validar.py`.

## Motor de IA (Adrián)

- Entrena con los Parquet (todas las capas); división train/test **por usuarios** (`GroupShuffleSplit`).
- Cargas: objetivo `cambio_kg` respecto a la última carga; un modelo global con el patrón como variable; predicción redondeada al incremento del ejercicio y limitada con `tope_seguridad`.
- Estado: clasificación `entrenar` / `suave` / `descansar` con `class_weight="balanced"`.
- Fatiga: regresión 0–100.
- XGBoost o Random Forest, comparados con `HistGradientBoosting` de `validar.py`.
- Criterios de éxito (revisados con la validación):

| Modelo | Línea base | Referencia (validar.py) | Objetivo |
| --- | --- | --- | --- |
| Cambio de carga, MAE | 1,83 kg (repetir) | 0,75 kg | ≤ 1 kg y ≥ 40 % mejor que la línea base |
| Estado, F1 macro | 0,27 (mayoritaria) | 0,60 · 0,70 con cuestionario | ≥ 0,65 · ≥ 0,70 con cuestionario |
| Fatiga, MAE | 10,0 (media) | 5,4 | ≤ 6 |

- Predicción en menos de 1 s por consulta.
- En la memoria hay que explicar que las métricas miden cuánto aprende el modelo las reglas del simulador, no la realidad.

## Backend (FastAPI)

Contrato de la API (T03): [`docs/api.md`](docs/api.md), modelos en `backend/app/schemas.py` y servidor simulado en `backend/app/mock.py`. JSON con campos en inglés `snake_case` y valores enumerados en español (los de la BD).

Endpoints mínimos:
- `POST /users`, `GET /users/{id}`
- `POST /sessions` (sesión con cuestionario y series), `GET /users/{id}/sessions`
- `GET /users/{id}/recommendations` → cambio de carga por ejercicio del día de rutina, estado del día, fatiga y una explicación corta; se guarda en `recomendacion`
- `GET /users/{id}/progress?exercise_id=...` (desde `rendimiento_ejercicio`)
- `POST /chat` → `{user_id, message, history}` → respuesta del agente
- `GET /catalog/exercises`, `GET /catalog/muscle-groups`
- `GET /users/{id}/program` (rutina activa y día que toca), `GET /health`
- Documentación automática en `/docs`. Usuario de demo fijo (sin login) en el MVP.

## Agente conversacional (Pablo)

- `llm.py`: interfaz común y dos implementaciones (Anthropic y OpenAI), elegidas con `LLM_PROVIDER`.
- Herramientas: `get_history`, `get_recommendation`, `get_progress`.
- RAG sencillo sobre documentos propios en `knowledge/` (progresión, descanso, técnica, hidratación).
- System prompt en español: solo entrenamiento y hábitos saludables; sin diagnósticos ni consejo médico; ante dolor o lesión, derivar a un profesional; recomendaciones orientativas.
- Límite `MAX_MESSAGES_PER_DAY`; si no hay clave de API, mensaje claro en lugar de error.

## App Android (Pablo)

- Material 3, barra inferior: **Hoy**, **Registrar**, **Progreso**, **Chat**.
- **Flujo del día:** primero el cuestionario corto (sueño, cuerpo, energía, otro deporte, dolor; respuestas de 1–3), después la recomendación de cargas. El cuestionario es una entrada de los modelos.
- **Registrar:** ejercicios del día de rutina; por serie carga, reps y RPE (6–10, pasos de 0,5); al final, dureza de la sesión (1–4).
- **Hoy:** estado del día, fatiga y carga sugerida por ejercicio.
- **Progreso:** e1RM o carga top por ejercicio en el tiempo.
- Retrofit + kotlinx.serialization, ViewModel + StateFlow. Backend en `http://10.0.2.2:8000` desde el emulador.

## Opcional: Módulo de Reglas (Adrián)
`rules/nutrition.py`: hidratación y macros según peso, objetivo y actividad. Solo si se cumplen los hitos H1–H4.

## Fuera del MVP
Login y multiusuario real, iOS, Google Play, datos reales o wearables, ajuste fino de LLMs.

## Convenciones
- Python 3.11+, tipado, `ruff`, `pytest`. Kotlin con version catalog (`libs.versions.toml`).
- Código en inglés en los módulos nuevos; textos de la interfaz y del agente en español. `train_datos/` mantiene sus nombres en español.
- No subir `.env`, datos generados, Parquet ni modelos entrenados.
- Cada fase termina con pruebas pasando y una instrucción en el README.
