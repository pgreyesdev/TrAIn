"""Reproducibilidad: los datos de cada usuario dependen solo de (semilla, id)."""
from __future__ import annotations

import pandas as pd
import pytest

# isort: split  (simulador y util se clasifican distinto según la carpeta desde la que se ejecuta ruff)
from simulador.salida import leer

# isort: split
from util import TABLAS_CATALOGO, TABLAS_LOTE, ordenar

TODAS = TABLAS_CATALOGO + TABLAS_LOTE


def _solo_usuarios(df: pd.DataFrame, tabla: str, hasta: int) -> pd.DataFrame:
    """Filas de los usuarios 1..hasta (por usuario_id, o por id en la tabla usuario)."""
    if "usuario_id" in df.columns:
        return df[df["usuario_id"] <= hasta]
    if tabla == "usuario":
        return df[df["id"] <= hasta]
    if tabla == "programa_ejercicio":           # programa = usuario × 100 + n
        return df[df["programa_id"] // 100 <= hasta]
    if tabla == "serie":                        # serie = sesión × 100 + n; sesión = usuario × 10.000 + n
        return df[df["sesion_id"] // 10000 <= hasta]
    raise KeyError(tabla)


@pytest.mark.parametrize("tabla", TODAS)
def test_mismo_resultado_con_otro_lote_y_procesos(tabla, datos_base, datos_otro_reparto):
    a = ordenar(tabla, leer(datos_base, tabla))
    b = ordenar(tabla, leer(datos_otro_reparto, tabla))
    assert len(a) > 0
    pd.testing.assert_frame_equal(a, b)


@pytest.mark.parametrize("tabla", TABLAS_LOTE)
def test_prefijo_estable_al_cambiar_usuarios(tabla, datos_base, datos_20):
    """Generar 20 o 40 usuarios con la misma semilla: los usuarios 1-20 son idénticos."""
    a = ordenar(tabla, _solo_usuarios(leer(datos_base, tabla), tabla, 20))
    b = ordenar(tabla, leer(datos_20, tabla))
    assert len(b) > 0
    pd.testing.assert_frame_equal(a, b)


@pytest.mark.parametrize("tabla", ["usuario", "sesion", "serie", "sim_estado_latente",
                                   "etiquetas_dia", "etiquetas_carga"])
def test_semilla_distinta_da_datos_distintos(tabla, datos_20, datos_otra_semilla):
    a = ordenar(tabla, leer(datos_20, tabla))
    b = ordenar(tabla, leer(datos_otra_semilla, tabla))
    assert not a.equals(b), f"{tabla}: con otra semilla salen los mismos datos"


def test_catalogo_no_depende_de_la_semilla(datos_20, datos_otra_semilla):
    for tabla in TABLAS_CATALOGO:
        pd.testing.assert_frame_equal(ordenar(tabla, leer(datos_20, tabla)),
                                      ordenar(tabla, leer(datos_otra_semilla, tabla)))
