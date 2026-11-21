# TrAIn — Contexto completo del proyecto

Actualizado: 3 de noviembre de 2026.

## 1. Qué es TrAIn

Aplicación Android que actúa como entrenador personal de gimnasio. Tiene dos piezas de IA:

- **Motor de IA (Machine Learning sobre datos tabulares):** a partir del historial del usuario recomienda
  - el **cambio de carga** para cada ejercicio en la próxima sesión (regresión, objetivo `cambio_kg`);
  - el **estado del día**: `entrenar`, `suave` o `descansar` (clasificación multiclase);
  - la **fatiga** de 0 a 100 (regresión).
- **Agente conversacional:** LLM por API (Claude u OpenAI) con RAG sobre fuentes fiables y herramientas que consultan el historial del usuario y el Motor de IA, para responder dudas y explicar las recomendaciones.
- **Opcional:** módulo de reglas para hidratación y macronutrientes.

Diferencia con lo existente: Hevy solo registra entrenamientos, sin IA. Apps como Fitbod o Alpha Progression ajustan cargas pero no explican sus recomendaciones ni permiten preguntar sobre ellas.

## 2. Contexto académico

- Asignatura del grado en la Universidad de La Laguna, curso 2026/27, primer cuatrimestre. Las entregas se hacen en el campus virtual (Moodle); el acta de constitución está en el wiki de la actividad 6.
- Actividades ya hechas: propuesta de proyecto (actividad 4), acta de constitución (actividad 6) y planificación con lista de tareas, recursos y cronograma en PDF.
- **Presentación del proyecto: 13/01/2027.**
- Herramienta de gestión elegida: **GitHub Projects** (vista Roadmap y tablero). Cada tarea T01–T27 es un issue con responsable, fase, inicio, fin y estimación.

## 3. Equipo y roles

| Miembro | Rol | Responsabilidades |
| --- | --- | --- |
| Pablo García de los Reyes | Coordinación, agente conversacional y app Android | Planificación y seguimiento; app en Kotlin con Jetpack Compose; LLM por API, RAG, herramientas y endpoints del agente; comparativa Claude/OpenAI; informe y presentación |
| Sergio Rosales Calzadilla | Datos, módulo de registro y backend | Simulador y datos sintéticos (hecho); PostgreSQL; backend FastAPI (API para la app, custodia de la clave del LLM, control de gasto) y pruebas |
| Adrián Hernández Herrera | Motor de IA y módulo de reglas | Variables, modelos de carga, estado y fatiga; evaluación; endpoints de predicción; calculadora de nutrición (opcional) |

Compartido: Sergio y Adrián acuerdan el formato de datos simulador ↔ Motor de IA; Pablo y Sergio el contrato de la API app ↔ backend. Todos revisan código ajeno, escriben pruebas de su módulo, revisan el código generado con agentes y participan en la memoria.

## 4. Arquitectura

```
App Android (Kotlin + Jetpack Compose)
        │  HTTP/JSON (Retrofit)
        ▼
Backend (Python + FastAPI)
   ├── PostgreSQL 16 en Docker (capas 1-3)
   ├── Motor de IA (modelos entrenados offline con Parquet)
   └── Agente (API de Claude u OpenAI, con herramientas y RAG)
```

- La **clave de la API del LLM solo vive en el backend**. La app nunca llama al proveedor.
- Capa del LLM intercambiable entre Claude y OpenAI con `LLM_PROVIDER`.
- Límite de mensajes por usuario y día, y tope de gasto en API (propuesta: 20 €).

Tecnologías: Python 3.11+, pandas, numpy, pyarrow, scikit-learn, XGBoost, FastAPI, pytest, PostgreSQL 16, psycopg, Docker; Kotlin, Jetpack Compose, Material 3, Retrofit, kotlinx.serialization, ViewModel + StateFlow; Git, GitHub, GitHub Projects; agentes de codificación Claude Code y GitHub Copilot.

## 5. Calendario e hitos

| Hito | Fecha | Criterio |
| --- | --- | --- |
| H1 Planificación aprobada | 09/11/26 | Plan aprobado, repositorio y tablero listos (T01–T02) |
| H2 Datos y BD compartida listos | 12/11/26 | Dataset de entrenamiento y BD de demo operativa (T04–T08) |
| H3 App con registro y recomendaciones | 14/12/26 | App con registro, recomendaciones y progreso conectada al backend (T14, T17, T18) |
| H4 Agente integrado | 17/12/26 | Agente con RAG y herramientas accesible desde la app (T20–T21) |
| H5 MVP congelado | 20/12/26 | MVP integrado y evaluado; no se añaden funciones (T23–T24) |
| H6 Informe cerrado | 11/01/27 | Informe final (T25) |
| H7 Presentación | 13/01/27 | Presentación del proyecto (T26–T27) |

Sin tareas del 21/12 al 06/01 (Navidad). Dedicación estimada: 6–10 h por persona y semana.

## 6. Lista de tareas

| Nº | Tarea | Resp. | Inicio | Fin | h |
| --- | --- | --- | --- | --- | --- |
| T01 | Planificación: tareas, recursos y cronograma | Pablo | 03/11 | 06/11 | 6 |
| T02 | Repositorio, tablero GitHub Projects y entorno | Pablo | 04/11 | 09/11 | 6 |
| T03 | Contrato de la API app ↔ backend | Pablo (+Sergio) | 09/11 | 12/11 | 4 |
| T04 | Diseño del simulador de atletas | Sergio | **hecha 25/10** | | 6 |
| T05 | Generador de datos sintéticos | Sergio | **hecha 25/10** | | 10 |
| T06 | Esquema PostgreSQL, carga y validación | Sergio | **hecha 25/10** | | 6 |
| T07 | Ajustes del simulador y dataset de 10.000 usuarios | Sergio (+Adrián) | 04/11 | 08/11 | 6 |
| T08 | PostgreSQL en Docker y BD de demo (200 usuarios) | Sergio | 09/11 | 12/11 | 4 |
| T09 | Ingeniería de variables (base: validar.py) | Adrián | 09/11 | 15/11 | 8 |
| T10 | Modelo de regresión de `cambio_kg` | Adrián | 16/11 | 24/11 | 10 |
| T11 | Clasificación del estado y regresión de fatiga | Adrián | 23/11 | 01/12 | 10 |
| T12 | Evaluación frente a líneas base y ajuste | Adrián (+Sergio) | 02/12 | 09/12 | 8 |
| T13 | Backend base: usuarios, registro, historial y derivados | Sergio | 13/11 | 25/11 | 10 |
| T14 | Endpoints de recomendaciones y progreso | Sergio (+Adrián) | 02/12 | 10/12 | 8 |
| T15 | Pruebas unitarias del backend y del Motor de IA | Sergio (+Adrián) | 11/12 | 17/12 | 8 |
| T16 | Proyecto Android: estructura, navegación, Material 3 | Pablo | 12/11 | 20/11 | 8 |
| T17 | Pantallas Registrar (con cuestionario previo) y Hoy | Pablo | 21/11 | 04/12 | 14 |
| T18 | Pantalla Progreso con gráficas | Pablo | 09/12 | 14/12 | 6 |
| T19 | Base de conocimiento (RAG) e instrucciones de seguridad | Pablo (+todos) | 30/11 | 06/12 | 8 |
| T20 | Capa LLM intercambiable, herramientas y `/chat` | Pablo (+Sergio) | 07/12 | 14/12 | 10 |
| T21 | Pantalla Chat | Pablo | 14/12 | 17/12 | 6 |
| T22 | (Opcional) Módulo de reglas: hidratación y macros | Adrián | 10/12 | 16/12 | 6 |
| T23 | Integración de extremo a extremo | Pablo (+todos) | 17/12 | 20/12 | 12 |
| T24 | Evaluación del agente (30 preguntas) y comparativa Claude/OpenAI | Pablo (+todos) | 17/12 | 20/12 | 8 |
| T25 | Informe final (memoria) | Pablo (+todos) | 07/01 | 11/01 | 18 |
| T26 | Presentación y vídeo de demostración | Pablo (+todos) | 08/01 | 12/01 | 10 |
| T27 | Ensayo y presentación | Pablo (+todos) | 12/01 | 13/01 | 4 |

Si algo se retrasa y pone en riesgo el MVP del 20/12: se recorta primero T22 y después se simplifica T18.

## 7. Estado de `train_datos/` (T04–T06, entregado por Sergio el 25/10)

Contenido:
- `simulador/motor.py`: simulación día a día de cada usuario (perfil, rasgos ocultos, fuerza por ejercicio, fatiga muscular y global, sueño, lesiones, adherencia, cinco estilos de elegir cargas, otro deporte).
- `simulador/catalogo.py` + `catalogo/ejercicios.csv`: 42 ejercicios en 7 grupos (6 por grupo), con patrón, mecánica, tipo de carga, incremento, rango de reps y músculos.
- `simulador/programas.py`: divisiones según días/semana (full body 2–3, torso/pierna 4, weider 5, PPL 6) y objetivos de series/reps/RPE.
- `simulador/formulas.py`: e1RM (Epley + RIR), %1RM, carga efectiva, regla de seguridad. Compartidas con el backend.
- `simulador/derivados.py`: capa 3 (`rendimiento_ejercicio`, `estado_diario`). La usará también el backend.
- `simulador/salida.py`: Parquet por lotes (o CSV.gz si no hay pyarrow).
- `generar.py`, `cargar_postgres.py`, `validar.py`, `sql/schema_postgres.sql` (14 tablas), `sql/reajustar_secuencias.sql`.

Verificación hecha el 3/11 (ejecutado de principio a fin):
- 400 usuarios × 12 meses en 26 s: ~168 sesiones y ~3.250 series por usuario.
- Sin ids duplicados, sin series huérfanas, valores en rango, restricciones del esquema respetadas.
- `estado_diario` sin fuga de información; la carga anterior de las etiquetas coincide en un 99,3 % con lo registrado.
- Carga en PostgreSQL 16 por `psql` sin errores (48 s); tras reajustar secuencias, la app puede insertar.
- No probado: escritura Parquet y carga con psycopg (sin acceso a PyPI en la prueba; se usó la alternativa CSV).

Resultados de `validar.py` (usuarios no vistos):

| Modelo | Línea base | Modelo sencillo |
| --- | --- | --- |
| Cambio de carga, MAE | 1,76 kg (repetir) | 0,70 kg (−60 %) |
| Estado, F1 macro | 0,25 (mayoritaria) | 0,65 · 0,73 con cuestionario |
| Fatiga 0–100, MAE | 10,4 (media) | 5,6 |

Reparto de `cambio_kg`: 32 % sube, 39 % igual, 29 % baja. Clases: entrenar 67 %, suave 20 %, descansar 14 %.

## 8. Modelo de datos (decisiones fijadas)

Capas:
1. **Catálogo:** `grupo_muscular`, `musculo`, `patron_movimiento`, `ejercicio`, `ejercicio_musculo`.
2. **Registro:** `usuario`, `medida_corporal`, `programa`, `programa_ejercicio`, `sesion` (con cuestionario), `serie`.
3. **Derivados:** `rendimiento_ejercicio`, `estado_diario`, y `recomendacion` (lo que devuelve el Motor).
4. **Simulación y etiquetas** (solo Parquet, nunca en la BD): `sim_usuario_param`, `sim_fuerza_latente`, `sim_estado_latente`, `etiquetas_carga`, `etiquetas_dia`.

Convenciones:
- Cargas en kg. Mancuernas: peso de cada una. Unilaterales: por lado. Dominadas: `lastre_kg`. Asistidas: `asistencia_kg`.
- RPE de 6 a 10 en pasos de 0,5.
- Cuestionario de sesión (opcional, NULL si no se responde). Antes de entrenar: `sueno` 1–3, `cuerpo` 1–3, `energia` 1–3, `actividad_extra` 0–2, `dolor` y `zona_dolor_id`. Después: `dureza_sesion` 1–4.
- `estado_diario` describe el estado al empezar el día, con datos hasta el día anterior.
- Ids del simulador: sesión = usuario × 10.000 + n; serie = sesión × 100 + n; programa = usuario × 100 + n.
- Regla de seguridad: subida máxima de +5 %, hasta +2,5 kg en tren superior y +5 kg en inferior (al menos un incremento).

Otras decisiones:
- PostgreSQL desde el inicio (no SQLite).
- Un modelo de cargas global para todos los ejercicios, con el patrón como variable.
- El backend calcula la capa 3 con las mismas funciones que el entrenamiento.
- La app pide el cuestionario **antes** de mostrar las cargas del día, porque es una entrada de los modelos.

## 9. Pendientes detectados en la revisión de `train_datos`

1. ~~**Regla de 5 días seguidos vs. rutina de 6 días (PPL)**~~ Resuelto (`fixed T04`): `MAX_DIAS_SEGUIDOS = 6`, global (al menos un día libre por semana). El F1 de referencia del estado baja de 0,63 a 0,60 al desaparecer los descansos triviales.
2. ~~**Semilla por lote:** los datos cambian si cambia `--lote`.~~ Resuelto (`fixed T05`): cada usuario tiene su generador, sembrado con `(semilla, id)`.
3. **Ids app vs. simulador:** tras reajustar secuencias, la app crea ids dentro del patrón simulado (p. ej. sesión 4.000.097). Cargar todos los datos sintéticos antes de usar la app. (T08)
4. **Tamaño de la BD:** ~0,85 GB por cada 1.000 usuarios en PostgreSQL (Parquet: ~70 MB). BD de demo con `--lotes 1` (200 usuarios). (T08)
5. **La recomendación no tiene consecuencias en la simulación:** los usuarios entrenan igual los días etiquetados "descansar" (44 %). No se puede afirmar que seguir las recomendaciones mejore el progreso. Limitación para la memoria.
6. **Circularidad:** las relaciones fuerza–fatiga–sueño son reglas inventadas; las métricas miden cuánto aprende el modelo esas reglas. Explicarlo en la memoria.
7. Probar la escritura Parquet y la carga con psycopg en un equipo con acceso a PyPI.
8. Tras cambiar parámetros del simulador, volver a pasar `validar.py`.

## 10. Criterios de éxito (revisados el 3/11)

| Objetivo | Métrica | Criterio |
| --- | --- | --- |
| Predecir el cambio de carga | MAE sobre usuarios no vistos | ≤ 1 kg y ≥ 40 % mejor que repetir la carga |
| Recomendar el estado del día | F1 macro | ≥ 0,65 (≥ 0,70 con cuestionario) |
| Estimar la fatiga | MAE (0–100) | ≤ 6 |
| Respuestas correctas del agente | ~30 preguntas de referencia revisadas por el equipo | ≥ 80 % |
| Agente seguro | Preguntas sobre dolor o lesión que deriva a un profesional | 100 % |
| Rapidez | Predicción / primera respuesta del agente | < 1 s / < 3 s |
| Coste | Gasto total en API del LLM | dentro del tope (propuesta 20 €) |
| Código mantenible | Cobertura de pruebas en backend y Motor | ≥ 70 % |
| Funcionalidad | Registro, Motor, Backend y App integrados | 4 de 4 |

Los criterios antiguos del acta (MAE < 2,5 kg; F1 ≥ 0,80) quedan sustituidos: el primero ya lo cumplía la línea base y el segundo no es alcanzable con estos datos.

## 11. Riesgos principales

- Alcance amplio para tres personas → priorizar núcleo; agente como ampliación; nutrición opcional.
- Curva de Kotlin/Compose → empezar pronto con pantallas sencillas y apoyarse en agentes de codificación.
- Agente con información incorrecta o peligrosa → RAG con fuentes fiables, instrucciones de seguridad y derivación.
- Recomendaciones de carga peligrosas → regla de seguridad y aviso de uso orientativo.
- Datos sintéticos poco realistas / sobreajuste a las reglas → validación por usuarios, líneas base, limitaciones documentadas.
- Gasto o exposición de la clave de API → clave solo en backend, límites y revisión semanal.
- Código de agentes con errores → revisión por pares y pruebas antes de integrar.

## 12. Próximos pasos inmediatos

1. Crear el repositorio y el tablero con T01–T27 (T02, Pablo).
2. Subir `train_datos/` al repositorio y añadir `CLAUDE.md` en la raíz.
3. Aplicar los ajustes del simulador y generar el dataset de 10.000 usuarios (T07, Sergio).
4. `docker-compose.yml` con PostgreSQL 16 y BD de demo de 200 usuarios (T08, Sergio).
5. Definir el contrato de la API (T03, Pablo y Sergio).
6. Ingeniería de variables partiendo de `validar.py` (T09, Adrián).
7. Corregir el acta del wiki: roles actuales, PostgreSQL y criterios revisados.

## 13. Cómo trabajar con Claude Code

- `CLAUDE.md` en la raíz del repositorio; Claude Code lo lee al arrancar.
- Pedir el trabajo por fases y con una tarea concreta del plan, por ejemplo: "Haz T08: crea `docker-compose.yml` con PostgreSQL 16, carga 200 usuarios con `cargar_postgres.py --lotes 1` y añade las instrucciones al README".
- Revisar y hacer commit al final de cada fase; no subir `.env`, datos generados, Parquet ni modelos entrenados.
- Si falla la compilación de Android, pegar el error completo a Claude Code.
