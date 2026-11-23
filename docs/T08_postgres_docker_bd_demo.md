# T08 · PostgreSQL en Docker y BD de demo (200 usuarios)

Issue #8 · Responsable: Sergio · Fecha: 23/11/2026 · Rama: `SergioDev`

Este documento recoge cómo se levanta la base de datos del proyecto, qué contiene la BD de demo y qué decisiones se han tomado, para que todo el equipo trabaje con la misma BD.

## 1. Resumen

| Punto del issue #8 | Estado | Dónde |
| --- | --- | --- |
| 1. `docker-compose.yml` con PostgreSQL 16 | Hecho | `docker-compose.yml`, `docker/postgres/init/` |
| 2. BD de demo con un lote (200 usuarios) | Hecho: un comando la crea | `scripts/crear_bd_demo.sh` |
| 3. Cargar los datos sintéticos antes de que la app inserte y reajustar secuencias | Hecho: `cargar_postgres.py` se niega a cargar sobre una BD con datos | `train_datos/cargar_postgres.py` |
| 4. Documentar en el README | Hecho | `README.md` (sección «Base de datos») y este documento |

Probado aquí contra PostgreSQL 16 instalado directamente (sin Docker). **El arranque con Docker y la vía psycopg quedan por probar en la VM Linux**: ver sección 6.

## 2. Decisión: una BD local por miembro

Cada miembro del equipo levanta su propia BD con Docker en su equipo. No se comparte una BD por red.

- No depende de que el equipo de nadie esté encendido ni de configurar la red de VirtualBox o del router.
- No se expone ninguna BD a internet: el puerto se publica solo en `127.0.0.1`.
- Como la generación de datos es reproducible, todos obtienen exactamente la misma BD de demo.
- Para la demo final o el despliegue del backend se podrá usar una BD alojada en la nube; se decidirá más adelante.

## 3. Cómo se usa

Requisitos: Docker con `docker compose` v2, Python 3.11+ con `train_datos/requirements.txt` instalado. En Linux (en Windows, Git Bash o WSL).

```bash
docker compose up -d --wait db       # PostgreSQL 16 en localhost:5432 (espera a que esté listo)
bash scripts/crear_bd_demo.sh        # genera 200 usuarios y los carga (pide confirmación: borra las tablas)
```

DSN para el backend y las herramientas: `postgresql://train:train@localhost:5432/train` (igual que `DATABASE_URL` en `backend/.env.example`).

Opciones del script: `--dsn`, `--datos DIR` (usar un dataset existente, por ejemplo el de 10.000 usuarios: carga su primer lote, que son los usuarios 1–200 si se generó con el `--lote` por defecto; si no, el script avisa), `--sin-docker` (BD ya en marcha), `--si` (no preguntar), `--ayuda`. Si el Python se llama `python`: `PYTHON=python bash scripts/crear_bd_demo.sh`. Se invoca con `bash` para que funcione aunque el fichero haya perdido el permiso de ejecución (Windows no lo guarda).

**Cuidado:** si tienes `DATABASE_URL` exportada en la terminal, el script la usa como destino. Antes de borrar muestra el DSN y pide confirmación; léelo.

Otras órdenes útiles:

```bash
docker compose ps                    # estado (debe salir "healthy")
docker compose exec db psql -U train -d train
docker compose down                  # para el contenedor; los datos se conservan (volumen train_pgdata)
docker compose down -v               # borra también los datos; el próximo up empieza de cero
```

Configuración opcional en un `.env` en la raíz del repositorio (ignorado por git; el script lo lee igual que Docker, sin ejecutarlo): `TRAIN_DB_USER`, `TRAIN_DB_PASSWORD`, `TRAIN_DB_NAME`, `TRAIN_DB_PORT`. Por ejemplo, `TRAIN_DB_PORT=5433` si el 5432 ya está ocupado (y ajusta el DSN). Usuario, contraseña y nombre solo se aplican con el volumen vacío: tras cambiarlos, `docker compose down -v`.

## 4. Qué hay en cada fichero

| Fichero | Qué hace |
| --- | --- |
| `docker-compose.yml` | Proyecto `train`, servicio `db` con `postgres:16`. Usuario, contraseña y BD `train` por defecto. Puerto solo en `127.0.0.1`. Volumen `train_pgdata`. Comprobación de salud con `pg_isready` por TCP, para que `--wait` no dé la BD por lista mientras aún se está inicializando. El servicio del backend se añadirá en la T13. |
| `docker/postgres/init/10-crear_bd_test.sql` | En el primer arranque crea la BD desechable `train_test`, que usan las pruebas de `train_datos` (`TRAIN_TEST_DSN=postgresql://train:train@localhost:5432/train_test`). |
| `.gitattributes` | Fuerza finales de línea LF en `*.sh` y `docker/**`, para que funcionen en Linux aunque se haga el commit desde Windows. |
| `scripts/crear_bd_demo.sh` | Comprueba requisitos, levanta Docker, genera los datos en `train_datos/datos_demo` (ignorado por git; se reutiliza) o usa `--datos`, carga con `--crear-esquema --lotes 1` y muestra un resumen. |
| `train_datos/cargar_postgres.py` | Sin `--crear-esquema`, no carga nada si alguna tabla ya tiene filas (sección 5) o si no existe el esquema. El `ANALYZE` final se limita a las tablas de TrAIn. |
| `train_datos/tests/test_cargar_postgres.py` | Pruebas nuevas: recargar sin `--crear-esquema` se bloquea y la BD no cambia; cargar sin esquema da un mensaje claro. |

## 5. Ids: por qué hay que cargar todo antes de usar la app

Los ids sintéticos siguen un patrón: sesión = usuario × 10.000 + n, serie = sesión × 100 + n. Tras la carga, `reajustar_secuencias.sql` deja las secuencias por encima del máximo, así que la app puede insertar sin problemas. Comprobado: el primer usuario nuevo recibe el id 201.

Pero su primera sesión recibe el id 2.000.176, que cae dentro del bloque de ids del usuario simulado 200. Si después se cargaran más usuarios sintéticos encima, sus ids chocarían con los de la app.

Por eso `cargar_postgres.py` sin `--crear-esquema` aborta, sin escribir nada, si alguna tabla de las capas 1–3 ya tiene filas. Para cambiar los datos sintéticos hay que recrear la BD entera (`--crear-esquema`, que borra todo) y cargar todo de una vez antes de que la app inserte. El script de demo ya lo hace así.

El riesgo queda **mitigado**, no eliminado: los ids de la app siguen dentro del patrón sintético. Regla para el backend y el Motor de IA: **no deducir nunca el usuario a partir de un id** (`sesion_id // 10000`); usar siempre la columna `usuario_id`.

## 6. Resultados y pendientes de probar

Medido el 23/11/2026 con PostgreSQL 16.15 instalado directamente, 2 núcleos, carga vía `psql` y datos en CSV:

| Prueba | Resultado |
| --- | --- |
| BD de demo, primera vez (genera los datos) | 35 s: 200 usuarios, 32.367 sesiones, 631.776 series; 169 MB |
| BD de demo, segunda vez (reutiliza los datos) | 18 s, mismas filas: el script es repetible |
| Recargar sin `--crear-esquema` | Bloqueado (código 1); la BD no cambia |
| `--datos` con un dataset de 400 usuarios (lote 200) | Carga solo los usuarios 1–200; contenido idéntico al de 200 |
| `pytest` en `train_datos` | Sin BD: 61 pasan, 58 se saltan. Con `train_test`: 117 pasan, 2 se saltan (pyarrow; en la VM deberían pasar las 119) |
| `docker compose config` | Correcto con valores por defecto y con un `.env` propio |
| Script de init | Crea `train_test`, propiedad de `train` |

**Pendiente de probar en la VM Linux** (aquí no hay demonio de Docker ni psycopg):

```bash
docker compose up -d --wait db && docker compose ps
docker compose exec db psql -U train -d train -c '\l'        # deben salir train y train_test
pip install -r train_datos/requirements-dev.txt
bash scripts/crear_bd_demo.sh
cd train_datos && TRAIN_TEST_DSN=postgresql://train:train@localhost:5432/train_test pytest -q -rs
```

Esto prueba por primera vez el arranque con Docker, la vía psycopg de `cargar_postgres.py` (cierra el punto 3 de la T07) y que el rol `train` puede recrear las tablas en `train_test`.

## 7. Limitaciones

- El script de demo es de bash: en Windows, Git Bash o WSL.
- La BD de demo ocupa ~170 MB; cargar los 10.000 usuarios ocuparía ~8,5 GB y no hace falta para la app.
- `shellcheck` no estaba disponible aquí; el script solo se ha comprobado con `bash -n` y ejecutándolo.
