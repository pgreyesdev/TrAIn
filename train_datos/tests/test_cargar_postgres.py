"""Carga en PostgreSQL con cargar_postgres.py (prueba de integración).

Solo se ejecuta si existe la variable de entorno TRAIN_TEST_DSN, por ejemplo:

    TRAIN_TEST_DSN=postgresql://postgres@localhost:5432/train_test pytest tests

ATENCIÓN: TRAIN_TEST_DSN debe apuntar a una base de datos de PRUEBAS DESECHABLE.
La prueba ejecuta `cargar_postgres.py --crear-esquema`, que BORRA las tablas de
TrAIn (DROP TABLE ... CASCADE) y las vuelve a crear, y consume valores de las
secuencias con nextval. Como protección, la prueba se salta sin tocar nada si:

- el nombre de la BD de TRAIN_TEST_DSN no termina en "_test" (se mira en el DSN
  y, conectando, con SELECT current_database()), o
- TRAIN_TEST_DSN es igual a DATABASE_URL (la BD del backend).

La carga se prueba por las dos vías de cargar_postgres.py: la automática
(psycopg si está instalado; si no, psql) y forzando psql con --psql. Para
consultar la BD se usa psycopg si está instalado y, si no, psql.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from urllib.parse import urlparse

import pytest

# isort: split  (simulador y util se clasifican distinto según la carpeta desde la que se ejecuta ruff)
from simulador.salida import CAPA, leer

# isort: split
from util import RAIZ, TABLAS_CATALOGO, generar

DSN = os.environ.get("TRAIN_TEST_DSN")
pytestmark = pytest.mark.skipif(
    not DSN, reason="define TRAIN_TEST_DSN (BD de pruebas desechable) para probar la carga")

TABLAS_CARGADAS = TABLAS_CATALOGO + [t for t, capa in CAPA.items() if capa != "simulacion"]
TABLAS_CAPA4 = [t for t, capa in CAPA.items() if capa == "simulacion"]
CON_SECUENCIA = ["grupo_muscular", "musculo", "patron_movimiento", "ejercicio", "usuario",
                 "medida_corporal", "programa", "programa_ejercicio", "sesion", "serie"]


def _consultar(sql: str) -> list[tuple[str, ...]]:
    """Ejecuta una consulta y devuelve las filas como tuplas de texto (ninguna si no es SELECT)."""
    try:
        import psycopg
    except ImportError:
        psycopg = None
    if psycopg is not None:
        with psycopg.connect(DSN, autocommit=True) as conn:
            cur = conn.execute(sql)
            return [tuple(str(v) for v in fila) for fila in cur.fetchall()] if cur.description else []
    if shutil.which("psql") is None:
        pytest.skip("no hay psycopg ni psql para consultar la BD")
    salida = subprocess.run(["psql", DSN, "-Atq", "-F", "|", "-v", "ON_ERROR_STOP=1", "-c", sql],
                            check=True, capture_output=True, text=True).stdout
    return [tuple(linea.split("|")) for linea in salida.splitlines() if linea]


def _comprobar_bd_desechable() -> None:
    """Salta la prueba si TRAIN_TEST_DSN no parece una BD de pruebas."""
    if DSN == os.environ.get("DATABASE_URL"):
        pytest.skip("TRAIN_TEST_DSN es igual a DATABASE_URL: no se borra la BD del backend")
    nombre = urlparse(DSN).path.lstrip("/")
    if not nombre.endswith("_test"):
        pytest.skip(f"la BD de TRAIN_TEST_DSN ({nombre or 'sin nombre'}) no termina en "
                    "'_test': no se ejecuta --crear-esquema, que borra las tablas")
    (actual,), = _consultar("SELECT current_database()")
    if not actual.endswith("_test"):
        pytest.skip(f"la BD conectada ({actual}) no termina en '_test'")


@pytest.fixture(scope="module", params=[[], ["--psql"]], ids=["automatica", "psql"])
def cargado(request, tmp_path_factory):
    """Genera 12 usuarios en 3 lotes y los carga con --crear-esquema por cada vía."""
    _comprobar_bd_desechable()
    if request.param == ["--psql"] and shutil.which("psql") is None:
        pytest.skip("psql no está en el PATH: no se prueba la vía --psql")
    datos = generar(tmp_path_factory.mktemp("pg"), 12, lote=4)
    t0 = time.time()
    res = subprocess.run([sys.executable, str(RAIZ / "cargar_postgres.py"), "--datos", str(datos),
                          "--dsn", DSN, "--crear-esquema", *request.param],
                         cwd=RAIZ, capture_output=True, text=True, check=False)
    assert res.returncode == 0, f"cargar_postgres.py falló:\n{res.stdout}\n{res.stderr}"
    print(f"\n{res.stdout}carga en {time.time() - t0:.1f} s")
    return datos


@pytest.mark.parametrize("tabla", TABLAS_CARGADAS)
def test_filas_coinciden_con_los_ficheros(tabla, cargado):
    (n_bd,), = _consultar(f"SELECT count(*) FROM {tabla}")
    assert int(n_bd) == len(leer(cargado, tabla)) > 0


def test_no_se_carga_la_capa_4(cargado):
    nombres = ", ".join(f"'{t}'" for t in TABLAS_CAPA4)
    filas = _consultar("SELECT table_name FROM information_schema.tables "
                       f"WHERE table_schema = 'public' AND table_name IN ({nombres})")
    assert filas == []


def test_recomendacion_queda_vacia(cargado):
    (n,), = _consultar("SELECT count(*) FROM recomendacion")
    assert int(n) == 0


@pytest.mark.parametrize("tabla", CON_SECUENCIA)
def test_secuencias_reajustadas(tabla, cargado):
    """Tras la carga, el siguiente id de la secuencia está por encima del máximo cargado.
    (nextval consume un valor: por eso la BD debe ser desechable.)"""
    (siguiente, maximo), = _consultar(
        f"SELECT nextval(pg_get_serial_sequence('{tabla}', 'id')), max(id) FROM {tabla}")
    assert int(siguiente) > int(maximo)


def test_ids_cargados_iguales_que_en_los_ficheros(cargado):
    filas = _consultar("SELECT id FROM sesion ORDER BY id")
    assert [int(f[0]) for f in filas] == sorted(leer(cargado, "sesion")["id"].tolist())


def test_recargar_sin_crear_esquema_se_bloquea(cargado):
    """Cargar encima de una BD con datos, sin --crear-esquema, falla sin tocar nada
    (los ids sintéticos chocarían con los ya cargados o con los creados por la app)."""
    consulta = " UNION ALL ".join(f"SELECT '{t}', count(*) FROM {t}" for t in TABLAS_CARGADAS)
    antes = _consultar(consulta)
    res = subprocess.run([sys.executable, str(RAIZ / "cargar_postgres.py"), "--datos", str(cargado),
                          "--dsn", DSN], cwd=RAIZ, capture_output=True, text=True, check=False)
    assert res.returncode != 0
    assert "ya tiene datos" in res.stderr and "--crear-esquema" in res.stderr, res.stderr
    assert "Traceback" not in res.stderr
    assert _consultar(consulta) == antes


def test_cargar_sin_esquema_pide_crear_esquema(cargado):
    """Sin las tablas de TrAIn y sin --crear-esquema, la carga falla con un mensaje claro.
    Al terminar se vuelve a cargar con --crear-esquema para no dejar la BD sin esquema."""
    orden = [sys.executable, str(RAIZ / "cargar_postgres.py"), "--datos", str(cargado), "--dsn", DSN]
    try:
        _consultar("DROP TABLE IF EXISTS " + ", ".join(reversed(TABLAS_CARGADAS))
                   + ", recomendacion CASCADE")
        res = subprocess.run(orden, cwd=RAIZ, capture_output=True, text=True, check=False)
        assert res.returncode != 0
        assert "No existe el esquema de TrAIn" in res.stderr, res.stderr
        assert "--crear-esquema" in res.stderr and "Traceback" not in res.stderr, res.stderr
    finally:
        rec = subprocess.run([*orden, "--crear-esquema"], cwd=RAIZ, capture_output=True,
                             text=True, check=False)
        assert rec.returncode == 0, f"no se pudo recrear la BD:\n{rec.stdout}\n{rec.stderr}"
