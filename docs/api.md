# Contrato de la API app ↔ backend (T03)

Versión **1.0.0** · 17/11/2026 · Pablo (+ Sergio para revisar)

Este documento fija cómo se hablan la app Android y el backend para que ambos se desarrollen en paralelo (T13–T14 en el backend, T16–T18 y T21 en la app).

La fuente de verdad es el código:

| Archivo | Qué es |
| --- | --- |
| [`backend/app/schemas.py`](../backend/app/schemas.py) | Modelos Pydantic de todas las peticiones y respuestas |
| [`backend/app/mock.py`](../backend/app/mock.py) | Servidor simulado que cumple el contrato con datos en memoria |
| [`docs/openapi.json`](openapi.json) | OpenAPI exportado (se puede importar en Postman o generar clientes) |
| [`backend/tests/test_contract.py`](../backend/tests/test_contract.py) | Pruebas del contrato |

Si este documento y `schemas.py` no coinciden, manda `schemas.py`, y hay que corregir este documento.

## 1. Convenciones

- **Base URL:** `http://10.0.2.2:8000` desde el emulador; `http://localhost:8000` desde el PC. Sin prefijo de versión en el MVP.
- **Formato:** JSON en UTF-8. Nombres de campo en inglés y `snake_case`, igual que en Kotlin con `@SerialName` o con `JsonNamingStrategy.SnakeCase`.
- **Valores enumerados en español**, los mismos que en PostgreSQL, para que el backend no traduzca nada: `entrenar`, `suave`, `descansar`, `principiante`, `hipertrofia`, `efectiva`... La app los convierte en etiquetas de la interfaz.
- **Fechas:** ISO 8601, `YYYY-MM-DD`. Horas `HH:MM:SS`. Marcas de tiempo con zona (`2026-11-17T08:00:00Z`).
- **Cargas en kg.** Mancuernas: peso de cada una. Unilaterales: por lado. Dominadas con lastre: `added_kg`. Asistidas: `assistance_kg`.
- **RPE** de 6 a 10 en pasos de 0,5. El backend rechaza otros valores con 422.
- **Nulos:** en las respuestas todos los campos aparecen siempre; `null` significa "sin dato". En las peticiones, los campos opcionales se pueden omitir.
- **Campos desconocidos:** el backend rechaza con 422 los campos que no están en el contrato (evita erratas silenciosas). La app debe configurar `ignoreUnknownKeys = true` al leer, para tolerar campos nuevos.
- **Usuario de demo:** sin login en el MVP. La app usa un `user_id` fijo (`DEMO_USER_ID = 1`, configurable en `BuildConfig`).
- **Documentación interactiva:** `/docs` (Swagger) y `/openapi.json`.

## 2. Errores

| Código | Cuándo | Cuerpo |
| --- | --- | --- |
| 404 | Usuario, ejercicio o recurso inexistente | `{"detail": "Usuario 999 no encontrado"}` |
| 409 | Conflicto al guardar (p. ej. sesión duplicada), si el backend lo detecta | `{"detail": "..."}` |
| 422 | Petición que no cumple el contrato | Formato estándar de FastAPI: `{"detail": [{"loc": [...], "msg": "...", "type": "..."}]}` |
| 500 | Error interno | `{"detail": "Error interno"}` |
| 503 | Base de datos o modelos no disponibles | `{"detail": "..."}` |

`detail` es un texto en español que la app puede enseñar tal cual (salvo en 422, que es para depurar). El chat no usa errores para la falta de clave ni para el límite diario: ver §3.9.

## 3. Endpoints

| Método | Ruta | Pantalla | Responsable |
| --- | --- | --- | --- |
| GET | `/health` | arranque | Sergio |
| GET | `/catalog/exercises` | Registrar, Progreso | Sergio |
| GET | `/catalog/muscle-groups` | cuestionario (zona de dolor) | Sergio |
| POST | `/users` | alta (fuera del flujo de demo) | Sergio |
| GET | `/users/{user_id}` | Hoy | Sergio |
| GET | `/users/{user_id}/program` | Registrar | Sergio |
| POST | `/sessions` | Registrar | Sergio |
| GET | `/users/{user_id}/sessions` | historial, agente | Sergio |
| GET | `/users/{user_id}/recommendations` | Hoy | Sergio + Adrián |
| GET | `/users/{user_id}/progress` | Progreso | Sergio |
| POST | `/chat` | Chat | Pablo |

Añadidos respecto a la lista mínima de `CLAUDE.md`: `/health`, `/catalog/muscle-groups` y `/users/{user_id}/program` (la pantalla Registrar necesita los ejercicios del día de rutina antes de que haya recomendación).

### 3.1 `GET /health`

```json
{
  "status": "ok",
  "api_version": "1.0.0",
  "database": true,
  "models_loaded": true,
  "model_version": "2026.12.01-xgb",
  "llm_configured": false
}
```

### 3.2 Catálogo

`GET /catalog/exercises` devuelve los 42 ejercicios (capa 1). `name` es `nombre_es`.

```json
[
  {
    "id": 1,
    "name": "Press banca con barra",
    "name_en": "Barbell Bench Press",
    "muscle_group": {"id": 1, "name": "Pecho"},
    "pattern": "empuje_horizontal",
    "mechanics": "compuesto",
    "equipment": "barra",
    "load_type": "externa",
    "laterality": "bilateral",
    "increment_kg": 2.5,
    "reps_min": 3,
    "reps_max": 10,
    "lower_body": false,
    "in_load_model": true
  }
]
```

- `load_type` dice qué campo de la serie rellena la app: `externa` → `load_kg`; `corporal_lastre` → `added_kg`; `asistida` → `assistance_kg`; `tiempo` → `duration_s`; `corporal` → solo `reps`.
- `in_load_model = false` (corporales y plancha): el Motor no sugiere carga.

`GET /catalog/muscle-groups` → `[{"id": 1, "name": "Pecho"}, ...]` (7 grupos). Sirve para elegir la zona de dolor.

### 3.3 Usuarios

`POST /users` → **201**

```json
{
  "sex": "H",
  "birth_date": "1999-04-12",
  "height_cm": 178,
  "weight_kg": 76.5,
  "level": "intermedio",
  "goal": "hipertrofia",
  "days_per_week": 4
}
```

- Obligatorios: `weight_kg`, `level`, `goal`, `days_per_week`.
- `sex`: `H`, `M` u `otro`. `level`: `principiante`, `intermedio`, `avanzado`. `goal`: `fuerza`, `hipertrofia`, `mantenimiento`, `perdida_grasa`.
- `days_per_week` de 2 a 6: el backend crea el programa con `simulador/programas.py` y guarda el peso en `medida_corporal`.

`GET /users/{user_id}` →

```json
{
  "id": 1,
  "sex": "H",
  "birth_date": "1999-04-12",
  "height_cm": 178,
  "weight_kg": 76.5,
  "level": "intermedio",
  "goal": "hipertrofia",
  "days_per_week": 4,
  "signup_date": "2026-11-17",
  "synthetic": false
}
```

`weight_kg` es la última medida corporal.

### 3.4 `GET /users/{user_id}/program`

Programa activo, con todos sus días y el día que toca hoy.

```json
{
  "id": 101,
  "user_id": 1,
  "split": "torso_pierna",
  "start_date": "2026-11-17",
  "next_day": 2,
  "days": [
    {
      "day": 1,
      "exercises": [
        {
          "order": 1,
          "exercise_id": 1,
          "exercise_name": "Press banca con barra",
          "load_type": "externa",
          "target_sets": 3,
          "target_reps": 10,
          "target_rpe": 8.0
        }
      ]
    }
  ]
}
```

- `next_day`: el siguiente al `program_day` de la última sesión, de forma cíclica; 1 si no hay sesiones.
- `target_reps` son segundos cuando `load_type = "tiempo"`.
- 404 si el usuario no existe o no tiene programa activo.

### 3.5 Sesiones

`POST /sessions` → **201**. Se envía al terminar el entrenamiento, con el cuestionario previo, la dureza y todas las series.

```json
{
  "user_id": 1,
  "program_id": 101,
  "program_day": 1,
  "date": "2026-11-17",
  "start_time": "18:30:00",
  "duration_min": 65,
  "questionnaire": {
    "sleep": 3,
    "body": 1,
    "energy": 2,
    "extra_activity": 0,
    "pain": false,
    "pain_zone_id": null
  },
  "session_hardness": 3,
  "notes": null,
  "sets": [
    {
      "exercise_id": 1,
      "exercise_order": 1,
      "set_number": 1,
      "type": "efectiva",
      "target_reps": 10,
      "reps": 10,
      "load_kg": 80.0,
      "added_kg": null,
      "assistance_kg": null,
      "duration_s": null,
      "distance_m": null,
      "rpe": 8.0,
      "completed": true
    }
  ]
}
```

Cuestionario (todo opcional; `questionnaire: null` si no se responde):

| Campo JSON | Columna `sesion` | Valores |
| --- | --- | --- |
| `sleep` | `sueno` | 1 mal · 2 normal · 3 bien |
| `body` | `cuerpo` | 1 fresco · 2 algo cargado · 3 muy cargado |
| `energy` | `energia` | 1 baja · 2 normal · 3 alta |
| `extra_activity` | `actividad_extra` | 0 no · 1 suave · 2 intenso |
| `pain` | `dolor` | `true` / `false` |
| `pain_zone_id` | `zona_dolor_id` | id de grupo muscular; exige `pain = true` |

`session_hardness` (`dureza_sesion`): 1 fácil · 2 moderada · 3 dura · 4 al límite.

Series:
- `type`: `calentamiento`, `efectiva` (por defecto), `descendente`, `fallo`.
- `(exercise_order, set_number)` es único en la sesión.
- Campos de carga según `load_type` del ejercicio (§3.2).

La respuesta es la misma sesión con `id` y un `id` en cada serie. Tras guardar, el backend recalcula `rendimiento_ejercicio` y `estado_diario` con `simulador/derivados.py` (no hace falta otra llamada).

`GET /users/{user_id}/sessions?from=2026-11-01&to=2026-11-30&limit=20` → lista de sesiones como la respuesta anterior, de la más reciente a la más antigua. `from`, `to` opcionales; `limit` de 1 a 200 (20 por defecto).

### 3.6 `GET /users/{user_id}/recommendations`

Pantalla **Hoy**. Primero se responde el cuestionario y después se piden las cargas, porque el cuestionario es una entrada de los modelos. Las respuestas van como parámetros de consulta (mismos nombres que en §3.5):

```
GET /users/1/recommendations?sleep=3&body=1&energy=2&extra_activity=0&pain=false
```

| Parámetro | Por defecto |
| --- | --- |
| `date` | hoy |
| `program_day` | `next_day` del programa |
| `sleep`, `body`, `energy`, `extra_activity`, `pain`, `pain_zone_id` | sin responder |

```json
{
  "user_id": 1,
  "date": "2026-11-17",
  "program_day": 1,
  "status": "entrenar",
  "status_probabilities": {"entrenar": 0.72, "suave": 0.2, "descansar": 0.08},
  "fatigue": 38.0,
  "loads": [
    {
      "exercise_id": 1,
      "exercise_name": "Press banca con barra",
      "load_type": "externa",
      "target_sets": 3,
      "target_reps": 10,
      "target_rpe": 8.0,
      "last_date": "2026-11-13",
      "last_load_kg": 80.0,
      "change_kg": 2.5,
      "suggested_load_kg": 82.5,
      "capped": false
    }
  ],
  "explanation": "Tu fatiga es moderada y has descansado: puedes entrenar con normalidad y subir algo de carga.",
  "questionnaire_used": true,
  "model_version": "2026.12.01-xgb",
  "generated_at": "2026-11-17T08:00:00Z"
}
```

- `status`: exactamente `entrenar`, `suave` o `descansar`. `fatigue`: 0–100.
- `loads`: un elemento por ejercicio del día de rutina, en el orden del programa.
- `change_kg`: cambio de la **carga efectiva** respecto a la última sesión (objetivo `cambio_kg` del Motor), redondeado al `increment_kg` del ejercicio y limitado con `formulas.tope_seguridad`. `capped = true` si la regla ha recortado la predicción.
- `last_load_kg` y `suggested_load_kg` están en el campo que registra el usuario (`load_kg` o `added_kg`; en asistidas, `assistance_kg`, que baja cuando la carga efectiva sube).
- Sin historial del ejercicio, o con `in_load_model = false`: `last_date`, `last_load_kg`, `change_kg` y `suggested_load_kg` son `null`.
- `explanation`: frase corta en español (máx. 500 caracteres), generada con plantillas a partir de los resultados del Motor; no llama al LLM.
- El backend guarda el resultado en `recomendacion` (una fila de `estado`, una de `fatiga` y una de `carga` por ejercicio). Pedirla dos veces el mismo día vuelve a calcularla y la sobrescribe.
- Debe responder en menos de 1 s.

### 3.7 `GET /users/{user_id}/progress?exercise_id=1&from=&to=`

Pantalla **Progreso**, desde `rendimiento_ejercicio`. `exercise_id` es obligatorio.

```json
{
  "user_id": 1,
  "exercise_id": 1,
  "exercise_name": "Press banca con barra",
  "points": [
    {
      "date": "2026-11-13",
      "session_id": 10001,
      "e1rm": 104.0,
      "top_load_kg": 80.0,
      "top_reps": 10,
      "top_rpe": 8.0,
      "volume_kg": 2400.0,
      "working_sets": 3
    }
  ]
}
```

Puntos de más antiguo a más reciente. `top_load_kg` es `carga_efectiva_top` (en dominadas incluye el peso corporal).

| Campo JSON | Columna `rendimiento_ejercicio` |
| --- | --- |
| `e1rm` | `e1rm` |
| `top_load_kg` | `carga_efectiva_top` |
| `top_reps` | `reps_top` |
| `top_rpe` | `rpe_top` |
| `volume_kg` | `volumen_kg` |
| `working_sets` | `series_efectivas` |

### 3.8 Correspondencia de nombres con la BD

| JSON | BD |
| --- | --- |
| `name` (ejercicio) | `ejercicio.nombre_es` |
| `mechanics`, `equipment`, `load_type`, `laterality`, `increment_kg` | `mecanica`, `equipamiento`, `tipo_carga`, `lateralidad`, `incremento_kg` |
| `in_load_model` | `ejercicio.en_modelo_carga` |
| `level`, `goal`, `days_per_week`, `signup_date`, `synthetic` | `nivel`, `objetivo`, `dias_semana`, `fecha_alta`, `es_sintetico` |
| `split` | `programa.tipo_division` |
| `day`, `order`, `target_sets`, `target_reps`, `target_rpe` | `programa_ejercicio.dia`, `orden`, `series_obj`, `reps_obj`, `rpe_obj` |
| `program_day`, `duration_min`, `start_time` | `sesion.dia_programa`, `duracion_min`, `hora_inicio` |
| `exercise_order`, `set_number`, `type`, `load_kg`, `added_kg`, `assistance_kg`, `completed` | `serie.orden_ejercicio`, `num_serie`, `tipo`, `carga_kg`, `lastre_kg`, `asistencia_kg`, `completada` |

### 3.9 `POST /chat`

```json
{
  "user_id": 1,
  "message": "¿Por qué me bajas el press banca?",
  "history": [
    {"role": "user", "content": "Hola"},
    {"role": "assistant", "content": "¡Hola! ¿En qué te ayudo?"}
  ]
}
```

- `message`: 1–2.000 caracteres. `history`: turnos anteriores, del más antiguo al más reciente, 20 como máximo. La app guarda la conversación; el backend no.

```json
{
  "status": "ok",
  "reply": "Tu última sesión de press banca fue muy exigente (RPE 9,5)...",
  "tools_used": ["get_recommendation", "get_history"],
  "messages_left_today": 29
}
```

`status`:

| Valor | Cuándo | HTTP |
| --- | --- | --- |
| `ok` | Respuesta del agente | 200 |
| `no_api_key` | No hay clave del LLM en `backend/.env` | 200 |
| `limit_reached` | Se alcanzó `MAX_MESSAGES_PER_DAY` | 200 |
| `error` | El proveedor del LLM falló o tardó demasiado | 200 |

En todos los casos `reply` es un texto en español que la app enseña tal cual (por ejemplo, "El chat no está disponible: falta configurar la clave del asistente."). Así la falta de clave da un mensaje claro en lugar de un error. La app nunca llama al proveedor del LLM: la clave solo vive en el backend.

## 4. Flujos de la app

**Hoy**
1. `GET /users/{id}` y `GET /users/{id}/program` (día que toca).
2. Cuestionario en la app.
3. `GET /users/{id}/recommendations?...` con las respuestas → estado, fatiga y carga sugerida por ejercicio.

**Registrar**
1. Ejercicios del día desde `program.days[next_day]` (o desde la recomendación, que ya trae las cargas sugeridas para rellenar las series).
2. La app guarda las series en local mientras se entrena.
3. Al terminar, dureza de la sesión y `POST /sessions` con el cuestionario de ese día.

**Progreso**: `GET /catalog/exercises` para el selector y `GET /users/{id}/progress?exercise_id=...`.

**Chat**: `POST /chat` con el historial local.

## 5. Servidor simulado

Para desarrollar la app antes de que exista el backend real:

```bash
cd backend
pip install -r requirements-dev.txt
uvicorn app.mock:app --reload --port 8000
```

Abre `http://localhost:8000/docs`. Hay un usuario de demo (`id = 1`) con una rutina torso/pierna de 4 días; las sesiones se guardan en memoria y se pierden al reiniciar. Las recomendaciones son fijas: con dolor, cuerpo muy cargado o mal sueño devuelve `suave` y baja 2,5 kg; si no, `entrenar` y sube 2,5 kg. El chat responde un texto fijo y aplica el límite diario.

## 6. Cambios en el contrato

- Cualquier cambio se hace en `schemas.py` (y en `mock.py` si cambia una ruta) dentro de un PR revisado por Pablo y Sergio.
- Después hay que regenerar el OpenAPI (`python -m app.mock --export ../docs/openapi.json`, desde `backend/`) y actualizar este documento. `test_contract.py` falla si `docs/openapi.json` se queda desfasado.
- Añadir campos opcionales en las respuestas no rompe la app (`ignoreUnknownKeys`). Quitar o renombrar campos sí: sube la versión mayor (`API_VERSION`).
- El backend real (T13) debe importar los modelos de `app/schemas.py` y exponer las mismas rutas que `mock.py`.

## 7. Puntos para revisar con Sergio

1. **Cuestionario en `GET /recommendations`:** va como parámetros de consulta y no se guarda hasta el `POST /sessions`. Alternativa: crear la sesión al empezar (`POST /sessions` con el cuestionario) y completarla al final con `PATCH`. Se ha elegido lo primero porque es más simple y no deja sesiones a medias.
2. **`GET` que escribe en `recomendacion`:** lo pide `CLAUDE.md`. Si molesta, se puede pasar a `POST /users/{id}/recommendations` sin cambiar el cuerpo de la respuesta.
3. **Ids de la app dentro del patrón del simulador:** cargar todos los datos sintéticos antes de que la app inserte (pendiente de T08).
