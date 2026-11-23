# T07 · Ajustes del simulador y dataset de entrenamiento (10.000 usuarios)

Issue #7 · Responsable: Sergio · Fecha: 21/11/2026 · Rama: `SergioDev`

Este documento recoge qué se ha cambiado en `train_datos/` durante la T07, por qué y con qué resultados, para que el resto del equipo (en especial el Motor de IA, T09–T12) conozca el contexto.

## 1. Resumen

| Punto del issue #7 | Estado | Dónde |
| --- | --- | --- |
| 1. Límite de días seguidos frente a la rutina PPL de 6 días | Hecho | commit `fixed T04` en `main` (f82213f) |
| 2. Semilla por usuario en lugar de por lote | Hecho | commit `fixed T05` en `main` (0ab3363) |
| 3. Probar Parquet y la carga en PostgreSQL | Pruebas automáticas hechas; carga real probada con `psql`. **Falta ejecutarlas en la VM Linux** con `requirements-dev.txt` instalado, para cubrir Parquet y psycopg (se activan solas). Hasta entonces el issue #7 queda abierto | `train_datos/tests/` |
| 4. Generar el dataset de 10.000 usuarios | Hecho y comprobado | no se sube (`.gitignore`); se regenera con un comando |
| 5. Volver a pasar `validar.py` y registrar las métricas | Hecho | sección 4 |

## 2. Cambios en el simulador (commits `fixed` en `main`)

### 2.1 `MAX_DIAS_SEGUIDOS` de 5 a 6 (`simulador/motor.py`)

**Qué es.** Constante global. Si un usuario lleva N o más días seguidos entrenando, la etiqueta del día (`etiquetas_dia.clase_estado`) es `descansar`, sea cual sea su fatiga. Solo afecta a la etiqueta, no a si el usuario entrena.

**Problema.** Con 5, el sábado de la rutina PPL (lunes a sábado) se etiquetaba `descansar` siempre que el usuario hubiera entrenado de lunes a viernes, aunque la rutina lo prevé como día de entreno.

**Medición previa (400 usuarios).** Días entrenados etiquetados `descansar` en la rutina de 6 días: 3,3 % solo por la regla, 29,7 % por disposición baja (fatiga y sueño) y 0,6 % por lesión. La regla era un error real pero pequeño. El resto es el efecto buscado del modelo de fatiga: quien entrena 6 días acumula más fatiga.

**Decisión.** Límite global de 6 ("al menos un día libre por semana"), no uno por rutina:
- un límite estricto por rutina (1, 1, 2, 5, 6 días) duplicaba los `descansar` (del 13,6 % al 28,1 % de los días), porque etiquetaba como descanso el día siguiente a cualquier sesión en rutinas de 2–3 días, mezclando el horario con el estado físico;
- un límite por rutina con +1 de margen daba prácticamente lo mismo que el global de 6, con más código.

**Efecto.** El F1 de referencia del estado baja de 0,63 a 0,60 (medido con `generar.py --usuarios 2000`). Con 5 días, la regla creaba descansos triviales que el modelo acertaba mirando solo `sesiones_consecutivas`. Con la semilla nueva y el límite antiguo, sobre los mismos 2.000 usuarios, daba 0,62, así que la bajada se debe a la regla y no a la semilla.

### 2.2 Semilla por usuario (`generar.py`)

**Antes.** Un generador aleatorio por lote, `random.Random(semilla * 1_000_003 + n_lote)`, compartido por los usuarios del lote. Los datos de un usuario dependían de `--lote` y de cuántos números aleatorios hubieran gastado los usuarios anteriores (efecto dominó al ajustar el simulador).

**Ahora.** Un generador por usuario, `random.Random(f"{semilla}-{uid}")`. Los datos dependen solo de la semilla y del id: el usuario N es el mismo con cualquier `--lote`, `--procesos` o `--usuarios`. La siembra con texto es estable entre plataformas (SHA-512, no depende de `PYTHONHASHSEED`), pero la igualdad bit a bit entre Windows y Linux no está verificada: el motor usa `math.exp` y la librería matemática de cada sistema puede diferir en el último decimal. Para trabajar en equipo, generad los datos en Linux.

### 2.3 Desempate de la serie top (`simulador/derivados.py`)

Al comprobar la reproducibilidad apareció un segundo problema. Si dos series de un ejercicio empataban en e1RM y repeticiones, la "serie top" (y su `rpe_top` en `rendimiento_ejercicio`) dependía del orden de las filas. Ahora se desempata por `(orden_ejercicio, num_serie, id)`: la primera serie que logra el top. Se usa el orden de las series y no solo el id porque, con datos de la app, el id refleja el orden de inserción. Con datos simulados el resultado es idéntico (comprobado con 100 usuarios). El backend usará esta misma función.

El desempate por id entró en el commit `fixed T05`; el orden `(orden_ejercicio, num_serie, id)` se añade en la T07.

## 3. Dataset de 10.000 usuarios

Los datos no se suben al repositorio. Como la generación es reproducible, cada miembro obtiene exactamente los mismos datos con:

```bash
cd train_datos
python generar.py --usuarios 10000 --procesos 8      # semilla 42, 12 meses → train_datos/datos/
```

Medido el 21/11/2026 (2 núcleos, CSV.gz porque no había pyarrow; con `requirements.txt` instalado se escribe Parquet):

| Dato | Valor |
| --- | --- |
| Tiempo | 604 s con 2 núcleos (~0,11–0,12 s por usuario y núcleo; ~3 min con 8) |
| Disco | 675 MB (registro 231 MB, derivados 182 MB, simulación 263 MB) |
| Sesiones / series por usuario | 164,5 / 3.198,7 de media |
| Filas | usuario 10.000 · sesion 1.644.696 · serie 31.987.323 · etiquetas_carga 8.334.694 · etiquetas_dia 3.650.000 · rendimiento_ejercicio 9.398.357 · estado_diario 3.650.000 |

Usuarios por rutina: 2 días 804, 3 días 3.036, 4 días 3.198, 5 días 1.938, 6 días 1.024.

**Clases del estado (todos los días):** entrenar 68,0 %, suave 19,7 %, descansar 12,3 %.

| Días/semana | descansar | entrenar | suave |
| --- | --- | --- | --- |
| 2 | 2,1 % | 90,9 % | 7,1 % |
| 3 | 4,9 % | 81,0 % | 14,1 % |
| 4 | 18,5 % | 55,8 % | 25,6 % |
| 5 | 9,5 % | 70,6 % | 19,9 % |
| 6 | 28,0 % | 44,9 % | 27,1 % |

La rutina de 4 días (torso/pierna) descansa más que la de 5 (Weider) porque sus sesiones tienen más volumen (~21,2 frente a ~17,1 series por sesión). `dias_semana` será una variable muy informativa para el modelo de estado.

**Regla de 6 días:** solo 325 de 1.644.696 días entrenados (0,02 %) se etiquetan `descansar` únicamente por la regla. Todos son de la rutina de 6 días, en semanas con una sesión recuperada en domingo (7 días seguidos). Contando todos los días, la regla fuerza 9.462 `descansar` (0,26 %): casi todos son el domingo, que el usuario no entrena, tras 6 días seguidos. No es un error.

**`cambio_kg`:** sube 31,7 %, igual 38,3 %, baja 30,0 %.

**Comprobaciones superadas:** RPE entre 6 y 10 en pasos de 0,5 (los nulos son series de calentamiento); solo las tres clases; ids únicos y con el patrón documentado; integridad serie → sesión → usuario; 365 días por usuario. Los usuarios 1–200 generados aparte con `--lote 50` son idénticos a los del dataset de 10.000.

## 4. Métricas de `validar.py`

Prueba sobre usuarios no vistos. El modelo es la referencia sencilla de `validar.py`, no el Motor de IA. Las dos columnas son muestras del dataset de 10.000 usuarios (`validar.py --max-usuarios N`, que elige N usuarios al azar con `--semilla 0`).

| Modelo | 2.000 de los 10.000 | 5.000 de los 10.000 |
| --- | --- | --- |
| Cargas, MAE: repetir / fórmula e1RM / modelo | 1,82 / 1,16 / **0,75 kg** (−59 %) | 1,80 / 1,14 / **0,73 kg** (−60 %) |
| Estado, F1 macro: mayoritaria / modelo / con cuestionario | 0,27 / **0,61** / 0,70 | 0,27 / **0,61** / 0,70 |
| Fatiga, MAE: media / modelo | 10,0 / **5,5** | 9,7 / **5,3** |

Las cifras de `train_datos/README.md` y `CLAUDE.md` (cargas 0,75 kg, estado 0,60 · 0,70, fatiga 5,4) salen de `generar.py --usuarios 2000`, es decir, de los usuarios 1–2.000. Las diferencias de 0,01–0,02 con la primera columna se deben solo a la muestra.

`validar.py --max-usuarios 10000` no cabe en 7 GB de RAM: carga cada tabla entera antes de filtrar y el pico crece con el número de usuarios (2.000 → ~2,3 GB; 5.000 → 4,5–4,8 GB, medido leyendo CSV.gz; con Parquet los tipos ocupan menos). En equipos de 8 GB, usar `--max-usuarios 5000` como máximo. El Motor de IA (`ml/features.py`) debería leer por columnas o por lotes.

**Para el Motor de IA (Adrián):** el objetivo del CLAUDE.md para el estado (F1 ≥ 0,65, ≥ 0,70 con cuestionario) queda por encima de esta referencia sin ajustar (0,61 / 0,70).

## 5. Pruebas automáticas (`train_datos/tests/`)

```bash
cd train_datos
pip install -r requirements-dev.txt      # requirements.txt + pytest + ruff
pytest tests -q -rs
# Carga real en PostgreSQL (BD DESECHABLE: --crear-esquema borra las tablas)
createdb train_test
TRAIN_TEST_DSN=postgresql://usuario:clave@localhost:5432/train_test pytest tests -q -rs
```

Por seguridad, la prueba de carga se salta si el nombre de la BD no termina en `_test` o si coincide con `DATABASE_URL`. Prueba las dos vías de `cargar_postgres.py`: psycopg (si está instalado) y `--psql`.

| Fichero | Qué comprueba |
| --- | --- |
| `test_reproducibilidad.py` | Mismos datos con distinto `--lote`/`--procesos`; los usuarios 1–20 no cambian al generar 40; otra semilla da otros datos |
| `test_reglas.py` | `MAX_DIAS_SEGUIDOS` es 6; la etiqueta del día coincide exactamente con la regla (lesión, racha ≥ `MAX_DIAS_SEGUIDOS`, umbrales 58/47); nunca hay descanso forzado con racha 5; la racha coincide con `estado_diario.sesiones_consecutivas`; clases, RPE, ids e integridad |
| `test_salida.py` | Escritura y lectura en CSV y Parquet (las de Parquet se saltan sin pyarrow); `--formato parquet` y `csv` dan los mismos datos |
| `test_cargar_postgres.py` | Solo con `TRAIN_TEST_DSN` (BD `*_test`): filas de las capas 1–3 iguales a los ficheros, capa 4 no cargada, secuencias reajustadas; por la vía automática y por `--psql` |

Resultado el 21/11/2026: 61 pasan y 54 se saltan sin `TRAIN_TEST_DSN` (~6 s); con PostgreSQL 16 local (`train_test`) pasan 113 y se saltan 2 (pyarrow), en ~15 s.

Las pruebas fallan si se vuelve a `MAX_DIAS_SEGUIDOS = 5`, si se quita el desempate o si se vuelve a la semilla por lote (comprobado con copias modificadas).

**Carga de demo probada (vía `psql`):** 200 usuarios cargados en 23 s (~57.000 series/s), 168 MB en la BD. Las secuencias quedan por encima del máximo y el primer INSERT de usuario recibe el id 201. Su primera sesión recibe el id 2.000.176, dentro del bloque de ids del usuario simulado 200: es el pendiente ya conocido de que hay que cargar todos los datos sintéticos antes de usar la app (T08). Queda para la T08 dejarlo en Docker.

## 6. Hallazgos pendientes (no incluidos en la T07)

No cambian lo entregado. Se dejan anotados para decidir si se abordan:

1. **Cargas extremas en usuarios "repetidor"** (`motor.py`, l. 413–417). Si fallan casi todas las repeticiones solo bajan un incremento, y con probabilidad 0,5. Hay 7.598 etiquetas (0,09 %) con `cambio_kg` ≤ −20 kg, hasta −95 kg (sobre todo en prensa 45°). Es poco realista y mete outliers en el MAE. Propuesta: bajar en proporción cuando falten la mitad o más de las repeticiones, o recortar las etiquetas extremas al entrenar.
2. **RPE incoherente con 0 repeticiones** (`motor.py`, l. 347). El ruido del RPE se aplica también en las series fallidas, que pueden anotar RPE 8. Propuesta: RPE mínimo de 9,5 cuando hay fallo.
3. **`np.datetime64("NaT")` sin unidad** (`salida.py`, l. 68). Da un `DeprecationWarning` en numpy 2, que pasará a ser un error. Propuesta: `np.datetime64("NaT", "s")`.
4. **Tipos al leer CSV** (`salida.py`). `usuario_id` vuelve como int64 en las tablas de simulación, y `reps_min`/`reps_max` del catálogo como float. Solo afecta sin pyarrow y no cambia valores.

Los puntos 1 y 2 cambian los datos y obligarían a regenerar y volver a validar. Los puntos 3 y 4 no cambian los datos.
