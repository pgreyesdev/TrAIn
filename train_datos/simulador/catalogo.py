"""Catálogo (capa 1): grupos, músculos, patrones y ejercicios.

La fuente de verdad de los ejercicios es catalogo/ejercicios.csv.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

RUTA_CSV = Path(__file__).resolve().parent.parent / "catalogo" / "ejercicios.csv"

GRUPOS = ["Pecho", "Espalda", "Cuádriceps", "Cadena posterior", "Hombro", "Brazos", "Core y gemelos"]

# músculo -> grupo de la app
MUSCULOS = {
    "pectoral": "Pecho",
    "dorsal": "Espalda",
    "trapecio": "Espalda",
    "lumbar": "Espalda",
    "deltoides_anterior": "Hombro",
    "deltoides_lateral": "Hombro",
    "deltoides_posterior": "Hombro",
    "biceps": "Brazos",
    "triceps": "Brazos",
    "antebrazo": "Brazos",
    "cuadriceps": "Cuádriceps",
    "aductores": "Cuádriceps",
    "isquiosurales": "Cadena posterior",
    "gluteo": "Cadena posterior",
    "abdomen": "Core y gemelos",
    "gemelo": "Core y gemelos",
}

PATRONES = [
    "empuje_horizontal", "empuje_vertical", "tiron_horizontal", "tiron_vertical",
    "sentadilla", "bisagra_cadera", "unilateral_pierna", "aislamiento_superior",
    "aislamiento_inferior", "core", "gemelo", "transporte",
]

GRUPOS_TREN_INFERIOR = {"Cuádriceps", "Cadena posterior"}

# Fracción del peso corporal que mueve cada ejercicio de tipo "corporal"
# (solo simulador; estos ejercicios no entran en el modelo de cargas).
FRACCION_CORPORAL = {"Elevaciones de piernas colgado": 0.35, "Rueda abdominal": 0.40}


@dataclass(frozen=True)
class Ejercicio:
    id: int
    grupo: str
    grupo_id: int
    nombre: str
    patron: str
    mecanica: str
    equipamiento: str
    tipo_carga: str
    lateralidad: str
    incremento: float
    reps_min: int
    reps_max: int
    factor_fatiga: float
    ratio: float
    en_modelo: bool
    musculos: tuple  # ((indice_musculo, factor), ...)
    primario: str
    inferior: bool
    fraccion_corporal: float


def leer_csv(ruta: Path = RUTA_CSV) -> pd.DataFrame:
    return pd.read_csv(ruta)


def cargar(ruta: Path = RUTA_CSV) -> list[Ejercicio]:
    df = leer_csv(ruta)
    nombres_musculo = list(MUSCULOS)
    ejercicios = []
    for r in df.itertuples(index=False):
        musc = []
        for parte in r.musculos.split(";"):
            nombre, factor = parte.split(":")
            musc.append((nombres_musculo.index(nombre), float(factor)))
        ejercicios.append(Ejercicio(
            id=int(r.id), grupo=r.grupo, grupo_id=GRUPOS.index(r.grupo) + 1,
            nombre=r.nombre_es, patron=r.patron, mecanica=r.mecanica,
            equipamiento=r.equipamiento, tipo_carga=r.tipo_carga, lateralidad=r.lateralidad,
            incremento=float(r.incremento_kg),
            reps_min=int(r.reps_min) if pd.notna(r.reps_min) else 0,
            reps_max=int(r.reps_max) if pd.notna(r.reps_max) else 0,
            factor_fatiga=float(r.factor_fatiga),
            ratio=float(r.ratio_fuerza_ref) if pd.notna(r.ratio_fuerza_ref) else 0.0,
            en_modelo=bool(r.en_modelo_carga), musculos=tuple(musc),
            primario=r.musculos.split(";")[0].split(":")[0],
            inferior=(r.grupo in GRUPOS_TREN_INFERIOR) or r.patron == "gemelo",
            fraccion_corporal=FRACCION_CORPORAL.get(r.nombre_es, 0.0),
        ))
    return ejercicios


def tablas_capa1(ruta: Path = RUTA_CSV) -> dict[str, pd.DataFrame]:
    """Las cinco tablas del catálogo, con los mismos nombres y columnas que la BD."""
    df = leer_csv(ruta)
    grupo = pd.DataFrame({"id": range(1, len(GRUPOS) + 1), "nombre": GRUPOS})
    musculo = pd.DataFrame({
        "id": range(1, len(MUSCULOS) + 1),
        "nombre": list(MUSCULOS),
        "grupo_id": [GRUPOS.index(g) + 1 for g in MUSCULOS.values()],
    })
    patron = pd.DataFrame({"id": range(1, len(PATRONES) + 1), "nombre": PATRONES})
    ejercicio = pd.DataFrame({
        "id": df["id"],
        "nombre_es": df["nombre_es"],
        "nombre_en": df["nombre_en"],
        "grupo_id": df["grupo"].map(lambda g: GRUPOS.index(g) + 1),
        "patron_id": df["patron"].map(lambda p: PATRONES.index(p) + 1),
        "mecanica": df["mecanica"],
        "equipamiento": df["equipamiento"],
        "tipo_carga": df["tipo_carga"],
        "lateralidad": df["lateralidad"],
        "incremento_kg": df["incremento_kg"],
        "reps_min": df["reps_min"].astype("Int16"),
        "reps_max": df["reps_max"].astype("Int16"),
        "factor_fatiga": df["factor_fatiga"],
        "ratio_fuerza_ref": df["ratio_fuerza_ref"],
        "es_nucleo": True,
        "en_modelo_carga": df["en_modelo_carga"].astype(bool),
    })
    filas = []
    nombres = list(MUSCULOS)
    for r in df.itertuples(index=False):
        for i, parte in enumerate(r.musculos.split(";")):
            nombre, factor = parte.split(":")
            filas.append((int(r.id), nombres.index(nombre) + 1,
                          "primario" if i == 0 else "secundario", float(factor)))
    ej_musc = pd.DataFrame(filas, columns=["ejercicio_id", "musculo_id", "rol", "factor"])
    return {
        "grupo_muscular": grupo,
        "musculo": musculo,
        "patron_movimiento": patron,
        "ejercicio": ejercicio,
        "ejercicio_musculo": ej_musc,
    }
