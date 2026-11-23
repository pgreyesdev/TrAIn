"""Escritura y lectura con simulador.salida (CSV y Parquet)."""
from __future__ import annotations

import random

import pandas as pd
import pytest

# isort: split  (simulador y util se clasifican distinto según la carpeta desde la que se ejecuta ruff)
from simulador import catalogo
from simulador.motor import nueva_salida, simular_usuario
from simulador.salida import CAPA, TIPOS, Escritor, a_dataframes, ficheros, leer

# isort: split
from util import TABLAS_CATALOGO, generar, ordenar


@pytest.fixture(scope="module")
def tablas() -> dict[str, pd.DataFrame]:
    """Capas 2 y 4 de tres usuarios, simulados en memoria (sin generar.py)."""
    ejercicios = catalogo.cargar()
    fecha_min = pd.Timestamp("2024-01-01").toordinal()
    out = nueva_salida()
    for uid in (1, 2, 3):
        simular_usuario(uid, random.Random(f"42-{uid}"), ejercicios, fecha_min,
                        fecha_min + 60, 60, out)
    return a_dataframes(out)


def _fechas_en_us(df: pd.DataFrame) -> pd.DataFrame:
    """Unifica la resolución de las fechas: al leer CSV, pandas las devuelve en
    microsegundos y el simulador las crea en segundos (mismo valor)."""
    df = df.reset_index(drop=True).copy()
    for c in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[c]):
            df[c] = df[c].astype("datetime64[us]")
    return df


def _ida_y_vuelta(base, formato: str, tablas: dict[str, pd.DataFrame]):
    esc = Escritor(base, formato)
    assert esc.formato == formato
    for tabla, df in catalogo.tablas_capa1().items():
        esc.catalogo(tabla, df)
    for tabla, df in tablas.items():
        # dos lotes por tabla, para probar también la concatenación al leer
        mitad = len(df) // 2
        esc.lote(tabla, df.iloc[:mitad], 0)
        esc.lote(tabla, df.iloc[mitad:], 1)

    for tabla, df in tablas.items():
        partes = ficheros(base, tabla)
        assert [p.name for p in partes] == [f"part-0000{i}{esc.ext}" for i in (0, 1)]
        assert partes[0].parent.parent.name == CAPA[tabla]
        leido = leer(base, tabla)
        # En Parquet los tipos se conservan todos. En CSV solo se restauran las fechas y
        # los tipos de salida.TIPOS (usuario_id vuelve como int64: ver informe T07).
        estricto = formato == "parquet"
        pd.testing.assert_frame_equal(_fechas_en_us(leido), _fechas_en_us(df),
                                      check_dtype=estricto, obj=f"{formato}:{tabla}")
        for c, tipo in TIPOS.get(tabla, {}).items():
            assert str(leido[c].dtype) == str(pd.Series(dtype=tipo).dtype), f"{tabla}.{c}"
    for tabla, df in catalogo.tablas_capa1().items():
        pd.testing.assert_frame_equal(leer(base, tabla), df.reset_index(drop=True),
                                      check_dtype=formato == "parquet", obj=f"{formato}:{tabla}")


def test_csv_ida_y_vuelta(tmp_path, tablas):
    _ida_y_vuelta(tmp_path, "csv", tablas)


def test_parquet_ida_y_vuelta(tmp_path, tablas):
    pytest.importorskip("pyarrow")
    _ida_y_vuelta(tmp_path, "parquet", tablas)


def test_leer_tabla_inexistente(tmp_path):
    with pytest.raises(FileNotFoundError):
        leer(tmp_path, "sesion")


def test_generar_en_parquet_igual_que_en_csv(tmp_path):
    """generar.py --formato parquet da las mismas tablas que --formato csv."""
    pytest.importorskip("pyarrow")
    pq = generar(tmp_path / "pq", 5, formato="parquet")
    csv = generar(tmp_path / "csv", 5, formato="csv")
    assert ficheros(pq, "serie")[0].suffix == ".parquet"
    for tabla in TABLAS_CATALOGO + list(CAPA):
        pd.testing.assert_frame_equal(_fechas_en_us(ordenar(tabla, leer(pq, tabla))),
                                      _fechas_en_us(ordenar(tabla, leer(csv, tabla))),
                                      check_dtype=False, obj=tabla)
