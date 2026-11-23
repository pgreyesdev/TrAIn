"""Fixtures comunes de las pruebas de train_datos.

Las pruebas generan datos pequeños con `generar.py` (como subproceso, igual que
lo usa una persona) en carpetas temporales de pytest. Los conjuntos que se
reutilizan entre pruebas se generan una sola vez por sesión.

Ejecutar desde train_datos/:

    pytest tests
"""
from __future__ import annotations

from pathlib import Path

import pytest

# isort: split  (util se clasifica distinto según la carpeta desde la que se ejecuta ruff)
from util import generar


@pytest.fixture(scope="session")
def datos_base(tmp_path_factory) -> Path:
    """40 usuarios en lotes de 7 con 2 procesos (semilla 42)."""
    return generar(tmp_path_factory.mktemp("base"), 40, lote=7, procesos=2)


@pytest.fixture(scope="session")
def datos_otro_reparto(tmp_path_factory) -> Path:
    """Los mismos 40 usuarios en un único lote con 1 proceso."""
    return generar(tmp_path_factory.mktemp("otro_reparto"), 40, lote=40, procesos=1)


@pytest.fixture(scope="session")
def datos_20(tmp_path_factory) -> Path:
    """Solo 20 usuarios con la misma semilla."""
    return generar(tmp_path_factory.mktemp("veinte"), 20, lote=200, procesos=1)


@pytest.fixture(scope="session")
def datos_otra_semilla(tmp_path_factory) -> Path:
    """20 usuarios con otra semilla."""
    return generar(tmp_path_factory.mktemp("semilla7"), 20, semilla=7, lote=200, procesos=1)
