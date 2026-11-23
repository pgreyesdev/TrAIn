"""Utilidades compartidas por las pruebas de train_datos.

tests/pytest.ini pone tests/ y train_datos/ en el sys.path, así que las pruebas
importan `util` y `simulador` sin depender del modo de importación de pytest.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pandas as pd

# isort: split  (simulador se clasifica distinto según la carpeta desde la que se ejecuta ruff)
from simulador.salida import CAPA

RAIZ = Path(__file__).resolve().parent.parent          # train_datos/
MESES = 3                     # historial corto: las pruebas deben ser rápidas
SEMILLA = 42

TABLAS_CATALOGO = ["grupo_muscular", "musculo", "patron_movimiento", "ejercicio",
                   "ejercicio_musculo"]
TABLAS_LOTE = list(CAPA)      # capas 2, 3 y 4

# Claves con las que se ordena cada tabla antes de comparar.
CLAVES = {
    "ejercicio_musculo": ["ejercicio_id", "musculo_id"],
    "sim_usuario_param": ["usuario_id"],
    "sim_fuerza_latente": ["sesion_id", "ejercicio_id"],
    "etiquetas_carga": ["sesion_id", "ejercicio_id"],
    "rendimiento_ejercicio": ["sesion_id", "ejercicio_id"],
    "sim_estado_latente": ["usuario_id", "fecha"],
    "etiquetas_dia": ["usuario_id", "fecha"],
    "estado_diario": ["usuario_id", "fecha"],
}


def claves(tabla: str, df: pd.DataFrame) -> list[str]:
    if tabla in CLAVES:
        return CLAVES[tabla]
    if "id" in df.columns:
        return ["id"]
    raise KeyError(f"No sé con qué claves ordenar {tabla}")


def ordenar(tabla: str, df: pd.DataFrame) -> pd.DataFrame:
    return df.sort_values(claves(tabla, df), kind="stable").reset_index(drop=True)


def generar(salida: Path, usuarios: int, semilla: int = SEMILLA, lote: int = 200,
            procesos: int = 1, meses: float = MESES, formato: str = "auto") -> Path:
    """Ejecuta generar.py como subproceso y devuelve la carpeta de salida."""
    orden = [sys.executable, str(RAIZ / "generar.py"), "--usuarios", str(usuarios),
             "--semilla", str(semilla), "--lote", str(lote), "--procesos", str(procesos),
             "--meses", str(meses), "--salida", str(salida), "--formato", formato]
    res = subprocess.run(orden, cwd=RAIZ, capture_output=True, text=True, check=False)
    if res.returncode != 0:
        raise AssertionError(f"generar.py falló:\n{res.stdout}\n{res.stderr}")
    return salida
