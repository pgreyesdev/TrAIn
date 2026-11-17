# Backend

Responsable: Sergio (endpoints del agente: Pablo). Tareas T03, T13 a T15 y T20.

API en FastAPI con PostgreSQL, Motor de IA y agente. Copia `.env.example` a `.env` antes de arrancar.

## Contrato (T03)

El contrato entre la app y el backend está en [`../docs/api.md`](../docs/api.md). Los modelos de petición y respuesta son `app/schemas.py`; el backend real (T13) los importa y expone las mismas rutas que `app/mock.py`.

```bash
pip install -r requirements-dev.txt
uvicorn app.mock:app --reload --port 8000        # servidor simulado, /docs
pytest                                           # pruebas del contrato
ruff check . && ruff format --check .
python -m app.mock --export ../docs/openapi.json # tras cambiar el contrato
```
