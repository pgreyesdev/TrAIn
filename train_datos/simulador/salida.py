"""Conversión a DataFrames y escritura/lectura de los ficheros de datos.

Estructura en disco (una carpeta por tabla, un fichero por lote de usuarios):

    datos/
      catalogo/    ejercicio.parquet, musculo.parquet, ...
      registro/    usuario/part-00000.parquet, sesion/..., serie/...   (capa 2)
      derivados/   rendimiento_ejercicio/..., estado_diario/...        (capa 3)
      simulacion/  sim_*/..., etiquetas_carga/..., etiquetas_dia/...   (capa 4)

Con pyarrow instalado se escribe Parquet; si no, CSV comprimido (.csv.gz).
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from .motor import COLUMNAS

EPOCH = date(1970, 1, 1).toordinal()

CAPA = {
    "usuario": "registro", "medida_corporal": "registro", "programa": "registro",
    "programa_ejercicio": "registro", "sesion": "registro", "serie": "registro",
    "rendimiento_ejercicio": "derivados", "estado_diario": "derivados",
    "sim_usuario_param": "simulacion", "sim_fuerza_latente": "simulacion",
    "sim_estado_latente": "simulacion", "etiquetas_carga": "simulacion",
    "etiquetas_dia": "simulacion",
}

COLUMNAS_FECHA = {"fecha", "fecha_alta", "fecha_nacimiento", "fecha_inicio", "fecha_fin"}

TIPOS = {
    "usuario": {"id": "int32", "dias_semana": "int16", "es_sintetico": "bool"},
    "medida_corporal": {"id": "int64", "usuario_id": "int32", "peso_kg": "float32",
                        "grasa_pct": "float32"},
    "programa": {"id": "int64", "usuario_id": "int32", "activo": "bool"},
    "programa_ejercicio": {"id": "int64", "programa_id": "int64", "dia": "int16",
                           "orden": "int16", "ejercicio_id": "int16", "series_obj": "int16",
                           "reps_obj": "int16", "rpe_obj": "float32"},
    "sesion": {"id": "int64", "usuario_id": "int32", "programa_id": "int64",
               "dia_programa": "int16", "duracion_min": "int16", "sueno": "Int16",
               "cuerpo": "Int16", "energia": "Int16", "actividad_extra": "Int16",
               "dolor": "boolean", "zona_dolor_id": "Int16", "dureza_sesion": "Int16",
               "notas": "string"},
    "serie": {"id": "int64", "sesion_id": "int64", "ejercicio_id": "int16",
              "orden_ejercicio": "int16", "num_serie": "int16", "reps_obj": "Int16",
              "reps": "Int16", "carga_kg": "float32", "lastre_kg": "float32",
              "asistencia_kg": "float32", "duracion_s": "Int16", "distancia_m": "float32",
              "rpe": "float32", "completada": "bool"},
    "sim_fuerza_latente": {"sesion_id": "int64", "ejercicio_id": "int16",
                           "e1rm_real": "float32", "e1rm_dia": "float32"},
    "sim_estado_latente": {"forma": "float32", "fatiga_real": "float32",
                           "readiness_real": "float32", "lesion": "bool"},
    "etiquetas_carga": {"sesion_id": "int64", "ejercicio_id": "int16",
                        "carga_recomendada": "float32", "carga_efectiva_recomendada": "float32",
                        "carga_efectiva_anterior": "float32", "cambio_kg": "float32"},
    "etiquetas_dia": {"fatiga": "float32"},
}


def ordinal_a_fecha(serie: pd.Series) -> pd.Series:
    valores = pd.to_numeric(serie, errors="coerce")
    dias = (valores - EPOCH).to_numpy(dtype="float64")
    out = np.full(len(dias), np.datetime64("NaT"), dtype="datetime64[s]")
    ok = ~np.isnan(dias)
    out[ok] = dias[ok].astype("int64").astype("datetime64[D]").astype("datetime64[s]")
    return pd.Series(out, index=serie.index)


def a_dataframes(out: dict) -> dict[str, pd.DataFrame]:
    dfs = {}
    for tabla, filas in out.items():
        df = pd.DataFrame(filas, columns=COLUMNAS[tabla])
        for c in df.columns:
            if c in COLUMNAS_FECHA:
                df[c] = ordinal_a_fecha(df[c])
        for c, t in TIPOS.get(tabla, {}).items():
            df[c] = df[c].astype(t)
        if "usuario_id" in df.columns:
            df["usuario_id"] = df["usuario_id"].astype("int32")
        dfs[tabla] = df
    return dfs


def hay_pyarrow() -> bool:
    try:
        import pyarrow  # noqa: F401
        return True
    except ImportError:
        return False


class Escritor:
    def __init__(self, base: Path, formato: str = "auto"):
        self.base = Path(base)
        if formato == "auto":
            formato = "parquet" if hay_pyarrow() else "csv"
        self.formato = formato
        self.ext = ".parquet" if formato == "parquet" else ".csv.gz"

    def _guardar(self, df: pd.DataFrame, ruta: Path):
        ruta.parent.mkdir(parents=True, exist_ok=True)
        if self.formato == "parquet":
            df.to_parquet(ruta, index=False)
        else:
            df.to_csv(ruta, index=False)

    def catalogo(self, tabla: str, df: pd.DataFrame):
        self._guardar(df, self.base / "catalogo" / f"{tabla}{self.ext}")

    def lote(self, tabla: str, df: pd.DataFrame, n_lote: int):
        self._guardar(df, self.base / CAPA[tabla] / tabla / f"part-{n_lote:05d}{self.ext}")


def _leer_fichero(ruta: Path, tabla: str) -> pd.DataFrame:
    if ruta.suffix == ".parquet":
        return pd.read_parquet(ruta)
    df = pd.read_csv(ruta)
    for c in df.columns:
        if c in COLUMNAS_FECHA:
            df[c] = pd.to_datetime(df[c])
    for c, t in TIPOS.get(tabla, {}).items():
        if c in df.columns:
            df[c] = df[c].astype(t)
    return df


def ficheros(base: Path, tabla: str) -> list[Path]:
    base = Path(base)
    if tabla in CAPA:
        carpeta = base / CAPA[tabla] / tabla
        return sorted(p for p in carpeta.glob("part-*") if p.is_file())
    return sorted((base / "catalogo").glob(f"{tabla}.*"))


def leer(base: Path, tabla: str) -> pd.DataFrame:
    """Lee una tabla completa (todos sus lotes)."""
    partes = [_leer_fichero(p, tabla) for p in ficheros(base, tabla)]
    if not partes:
        raise FileNotFoundError(f"No hay ficheros para la tabla {tabla} en {base}")
    return pd.concat(partes, ignore_index=True)
