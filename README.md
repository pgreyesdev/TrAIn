# TrAIn

Entrenador personal de gimnasio con IA para Android. Proyecto de la Universidad de La Laguna, curso 2026/27.

- **Motor de IA:** recomienda el cambio de carga de cada ejercicio, el estado del día (`entrenar`, `suave` o `descansar`) y la fatiga de 0 a 100.
- **Agente conversacional:** LLM por API (Claude u OpenAI) con RAG y herramientas que consultan el historial y el Motor de IA para explicar las recomendaciones.

| Miembro | Rol |
| --- | --- |
| Pablo García de los Reyes | Coordinación, agente conversacional y app Android |
| Sergio Rosales Calzadilla | Datos, módulo de registro y backend |
| Adrián Hernández Herrera | Motor de IA y módulo de reglas |

## Arquitectura

```
App Android (Kotlin + Jetpack Compose)
        │  HTTP/JSON (Retrofit)
        ▼
Backend (Python + FastAPI)
   ├── PostgreSQL 16 en Docker (capas 1-3)
   ├── Motor de IA (modelos entrenados offline con Parquet)
   └── Agente (API de Claude u OpenAI, con herramientas y RAG)
```

La clave de la API del LLM solo vive en el backend (`backend/.env`, nunca en el repositorio ni en la app).

## Estructura

| Carpeta | Contenido | Responsable |
| --- | --- | --- |
| `train_datos/` | Simulador, datos sintéticos, esquema PostgreSQL, carga y validación | Sergio |
| `ml/` | Motor de IA: variables, entrenamiento y evaluación | Adrián |
| `backend/` | API en FastAPI, predicción y agente | Sergio (agente: Pablo) |
| `android/` | App en Kotlin con Jetpack Compose | Pablo |
| `docs/` | Planificación, acta de constitución y contexto del proyecto | Todos |
| `scripts/` | Utilidades de gestión del proyecto | Pablo |

`CLAUDE.md` recoge la especificación técnica del MVP y las decisiones fijadas.

## Puesta en marcha

Requisitos: Python 3.11 o superior, Docker y Android Studio.

```bash
git clone https://github.com/pgreyesdev/TrAIn.git
cd TrAIn
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r train_datos/requirements.txt
cp backend/.env.example backend/.env                # y rellena las claves
```

Generar datos y validar (detalles en [`train_datos/README.md`](train_datos/README.md)):

```bash
cd train_datos
python generar.py --usuarios 1000
python validar.py
```

Contrato de la API (T03, detalles en [`docs/api.md`](docs/api.md)). Servidor simulado para desarrollar la app antes del backend real, y pruebas del contrato:

```bash
cd backend
pip install -r requirements-dev.txt
uvicorn app.mock:app --reload --port 8000   # http://localhost:8000/docs
pytest
```

Cada fase añade aquí sus instrucciones (PostgreSQL en Docker en T08, backend en T13, app en T16).

## Gestión del proyecto

- Tareas T01 a T27 como issues, con etiquetas de fase y responsable y los hitos H1 a H7.
- Tablero en GitHub Projects (vistas Roadmap y tablero). Se crea con [`scripts/crear_tablero.sh`](scripts/crear_tablero.sh).
- Planificación completa en [`docs/planificacion_TrAIn.pdf`](docs/planificacion_TrAIn.pdf).

| Hito | Fecha |
| --- | --- |
| H1 Planificación aprobada | 09/11/2026 |
| H2 Datos y BD compartida listos | 12/11/2026 |
| H3 App con registro y recomendaciones | 14/12/2026 |
| H4 Agente integrado | 17/12/2026 |
| H5 MVP congelado | 20/12/2026 |
| H6 Informe cerrado | 11/01/2027 |
| H7 Presentación | 13/01/2027 |

## Normas de trabajo

- Una rama por tarea (`t13-backend-base`) y pull request revisado por otro miembro antes de integrar en `main`.
- El mensaje del commit o del PR cita la tarea (`T13: ...`) y el PR la cierra con `Closes #<issue>`.
- Código nuevo en inglés; textos de la interfaz y del agente en español. `train_datos/` mantiene sus nombres en español.
- No se suben `.env`, datos generados, Parquet ni modelos entrenados.
