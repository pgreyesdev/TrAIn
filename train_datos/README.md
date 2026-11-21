# TrAIn · Base de datos y datos sintéticos

Base de datos PostgreSQL de TrAIn y simulador que genera usuarios sintéticos con
historiales de entrenamiento creíbles, para entrenar el Motor de IA.

```
train_datos/
├── sql/schema_postgres.sql        esquema de la BD (capas 1-3, 14 tablas)
├── sql/reajustar_secuencias.sql   tras cargar ids del simulador
├── catalogo/ejercicios.csv        los 42 ejercicios (6 por grupo) con sus atributos
├── simulador/                     código del simulador
│   ├── catalogo.py                grupos, músculos, patrones; carga el CSV
│   ├── formulas.py                e1RM, %1RM, carga efectiva, regla de seguridad (compartidas con el backend)
│   ├── programas.py               divisiones y plantillas de rutina
│   ├── motor.py                   simulación día a día de cada usuario
│   ├── derivados.py               capa 3 (la usará también el backend)
│   └── salida.py                  escritura/lectura de Parquet
├── generar.py                     genera los datos
├── cargar_postgres.py             vuelca capas 1-3 en PostgreSQL
└── validar.py                     comprueba que los datos se pueden aprender
```

## 1. Instalación

```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

PostgreSQL 15 o superior. Crea una base vacía:

```bash
createdb train
```

## 2. Generar datos

```bash
python generar.py --usuarios 1000                 # desarrollo, ~1-2 min
python generar.py --usuarios 10000 --procesos 8   # dataset de entrenamiento
python generar.py --usuarios 50000 --meses 18 --salida datos_grande
```

| Opción | Por defecto | Qué hace |
| --- | --- | --- |
| `--usuarios` | 1000 | número de usuarios simulados |
| `--meses` | 12 | historial por usuario |
| `--procesos` | núcleos del PC | simulación en paralelo |
| `--lote` | 200 | usuarios por fichero |
| `--semilla` | 42 | misma semilla = mismos datos para cada usuario, sea cual sea `--lote`, `--procesos` o `--usuarios` |
| `--salida` | `datos` | carpeta de salida |

**Magnitud de referencia** (medida con 2.000 usuarios × 12 meses): ~166 sesiones y
~3.200 series por usuario; 0,15 s por usuario y núcleo; ~70 MB por cada 1.000 usuarios
en disco.

| Usuarios | Series | Tiempo con 8 núcleos | Disco (aprox.) |
| --- | --- | --- | --- |
| 1.000 | 3,2 M | ~20 s | 70 MB |
| 10.000 | 32 M | ~3 min | 700 MB |
| 100.000 | 320 M | ~30 min | 7 GB |

La memoria no crece con el número de usuarios: cada lote se simula y se escribe por separado.

## 3. Qué son los ficheros Parquet y cómo encajan con la BD

Parquet es un formato de fichero para tablas, como un CSV pero **por columnas,
comprimido y con tipos**. pandas lee una columna de 30 millones de filas en
segundos, cuando de PostgreSQL tardaría minutos. Por eso es el formato estándar
para entrenar modelos.

En TrAIn conviven así:

| Dónde | Qué contiene | Quién lo usa |
| --- | --- | --- |
| **PostgreSQL** | capas 1-3: catálogo, registro y derivados | la app (vía backend) y el backend |
| **Parquet** `datos/catalogo`, `registro`, `derivados` | las mismas tablas que la BD, generadas por el simulador | carga inicial de la BD y entrenamiento |
| **Parquet** `datos/simulacion` | capa 4: verdad oculta y etiquetas | solo entrenamiento y evaluación del Motor de IA |

Los ids (`usuario_id`, `sesion_id`, `ejercicio_id`) son los mismos en la BD y en
Parquet, así que se unen con un `merge`:

```python
from simulador.salida import leer
rend = leer("datos", "rendimiento_ejercicio")      # capa 3
etiq = leer("datos", "etiquetas_carga")            # capa 4
df = etiq.merge(rend, on=["usuario_id", "sesion_id", "ejercicio_id"])
```

Flujo previsto:

1. `generar.py` escribe todo en Parquet.
2. `cargar_postgres.py` vuelca las capas 1-3 a PostgreSQL. Para la app basta
   con una parte, por ejemplo `--lotes 5` (1.000 usuarios).
3. Adrián entrena con los Parquet (todas las capas).
4. En producción, el backend lee de PostgreSQL y calcula la capa 3 con las
   mismas funciones de `simulador/derivados.py` y `simulador/formulas.py`.
   Con datos reales no existe capa 4.

## 4. Cargar en PostgreSQL

```bash
python cargar_postgres.py --dsn postgresql://usuario:clave@localhost:5432/train --crear-esquema
python cargar_postgres.py --dsn ... --crear-esquema --lotes 5   # solo 1.000 usuarios
```

`--crear-esquema` borra las tablas de TrAIn si existen y las vuelve a crear.
Al final se reajustan las secuencias, de modo que la app puede seguir
insertando usuarios, sesiones y series con ids nuevos.

Probado con PostgreSQL 16 usando `psql`: unas 50.000 series por segundo. Con
psycopg debería ir igual o más rápido, pero esa vía no la he podido probar aquí.

## 5. Validar

```bash
python validar.py --datos datos --max-usuarios 2000
```

Resultado con 2.000 usuarios (prueba sobre usuarios **no vistos**):

| Modelo | Línea base | Fórmula e1RM | Modelo sencillo |
| --- | --- | --- | --- |
| Cargas, MAE del cambio | 1,81 kg (repetir) | 1,13 kg | **0,73 kg** (−60 %) |
| Estado, F1 macro | 0,27 (mayoritaria) | — | **0,63** · 0,72 con cuestionario |
| Fatiga 0-100, MAE | 9,9 (media) | — | **5,5** |

`validar.py` usa pocas variables y modelos sin ajustar: es un punto de partida, no
el Motor de IA.

## 6. Cómo funciona el simulador

Cada usuario tiene un perfil (sexo, edad, peso, nivel, objetivo, días por semana)
y unos rasgos ocultos:

- talento (velocidad de mejora);
- recuperación;
- adherencia;
- precisión al estimar el RPE;
- estilo al elegir cargas: progresivo, conservador, agresivo o repetidor.

Cada día:

1. Se recupera la fatiga muscular (τ ≈ 1,8 días) y la global (τ ≈ 4,5 días).
2. Se genera el sueño de la noche anterior.
3. Se calcula la disposición real y la etiqueta del día:
   - descansar si hay lesión, si lleva 5 o más días seguidos entrenando, o si la disposición está por debajo de 47;
   - entrenar suave si está entre 47 y 58;
   - entrenar si está en 58 o más.
4. Si le toca y acude (según su adherencia), entrena su rutina:
   - Cada serie sale de su fuerza real del día (menos fatiga, más o menos sueño) con la fórmula de Epley.
   - El RPE que anota lleva ruido.
5. La fuerza mejora con el estímulo, cada vez menos cerca de su techo. Parte de la mejora pasa a los ejercicios del mismo patrón.
6. El usuario decide su próxima carga **según su estilo**, con errores. Por eso el modelo tiene algo que corregir.
7. Por la tarde puede hacer otro deporte, que suma fatiga.

**Etiqueta de carga:** la carga que con su fuerza real de ese día daría las reps
objetivo al RPE objetivo. Se redondea al incremento del ejercicio y se limita con
la regla de seguridad (+5 % como máximo, hasta +2,5 kg en tren superior y +5 kg
en inferior). El objetivo del modelo es `cambio_kg` respecto a la carga anterior.

Distribución de `cambio_kg`: 32 % sube, 39 % igual y 29 % baja.

Los parámetros están al principio de `simulador/motor.py` (tasas de mejora,
umbrales, pesos de la fatiga…). Si los cambiáis, volved a pasar `validar.py`.

## 7. Convenciones de registro

- **Cargas en kg.**
  - Mancuernas: el peso de **cada** mancuerna.
  - Ejercicios unilaterales: la carga por lado.
- **Dominadas:** `lastre_kg` (0 si es sin lastre). La carga efectiva es peso corporal + lastre.
- **Máquinas asistidas:** `asistencia_kg`. La carga efectiva es peso corporal − asistencia.
- **RPE:** escala de 6 a 10 en pasos de 0,5.
- **Fuera del modelo de cargas:** plancha (se registra en segundos), elevaciones de piernas y rueda abdominal (peso corporal).
- **`estado_diario`:** describe el estado al **empezar** el día, con datos hasta el día anterior. Así no hay fuga de información.
- **Ids del simulador:**
  - sesión = usuario × 10.000 + n;
  - serie = sesión × 100 + n;
  - programa = usuario × 100 + n.

## 8. Decisiones tomadas

- RPE como medida principal.
- El modelo de cargas predice el cambio respecto a la última carga.
- Un modelo global para todos los ejercicios, con el patrón como variable.
- Cuestionario opcional con respuestas cortas.
- PostgreSQL desde el inicio.

## 9. Limitaciones conocidas

- Las relaciones fuerza–fatiga–sueño son reglas inventadas y razonables, no medidas. El modelo aprenderá esas reglas.
- La etiqueta "estado" depende del sueño real, que el usuario solo describe en tres niveles y solo los días que entrena. Por eso el F1 tiene un techo.
- No se simulan semanas de descarga planificadas, cambios de gimnasio ni series descendentes.
