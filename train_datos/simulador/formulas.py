"""Fórmulas compartidas entre el simulador, el backend y el Motor de IA.

Mantenerlas en un solo sitio garantiza que el entrenamiento y la producción
calculan exactamente lo mismo.
"""
from __future__ import annotations

import math

# Escala de RPE de la app: 6 a 10 en pasos de 0,5. RIR = 10 - RPE.
RPE_MIN_APP = 6.0
RPE_MAX_APP = 10.0

# Respuesta "dureza de la sesión" (1-4) -> RPE de sesión (escala de Foster)
DUREZA_A_SRPE = {1: 3.0, 2: 5.0, 3: 7.0, 4: 9.0}

# Carga extra por la pregunta "¿otro deporte desde la última sesión?" (UA)
ACTIVIDAD_EXTRA_UA = {0: 0.0, 1: 150.0, 2: 300.0}

# Regla de seguridad: subida máxima entre sesiones (kg) por tren
TOPE_SUBIDA_KG = {"superior": 2.5, "inferior": 5.0}
TOPE_SUBIDA_PCT = 0.05


def pct_1rm(reps: float, rpe: float) -> float:
    """Fracción del 1RM que permite hacer `reps` con un RPE dado (Epley + RIR)."""
    reps_totales = reps + (10.0 - rpe)
    return 1.0 / (1.0 + reps_totales / 30.0)


def e1rm(carga: float, reps: float, rpe: float | None) -> float:
    """1RM estimado de una serie. Sin RPE se asume serie al fallo (RPE 10)."""
    if rpe is None or (isinstance(rpe, float) and math.isnan(rpe)):
        rpe = 10.0
    return carga / pct_1rm(reps, rpe)


def reps_hasta_fallo(e1rm_real: float, carga: float) -> float:
    """Repeticiones (continuas) que se pueden hacer con `carga` hasta el fallo."""
    if carga <= 0:
        return 99.0
    return 30.0 * (e1rm_real / carga - 1.0)


def carga_efectiva(tipo_carga: str, carga_kg, lastre_kg, asistencia_kg, peso_corporal):
    """Carga real que mueve el usuario, según el tipo de ejercicio."""
    if tipo_carga == "externa":
        return carga_kg
    if tipo_carga == "corporal_lastre":
        return peso_corporal + (lastre_kg or 0.0)
    if tipo_carga == "asistida":
        return peso_corporal - (asistencia_kg or 0.0)
    return None  # corporal, tiempo, transporte: fuera del modelo de cargas


def redondear(x: float, incremento: float) -> float:
    if incremento <= 0:
        return x
    return round(x / incremento) * incremento


def tope_seguridad(carga_anterior: float, carga_propuesta: float,
                   incremento: float, tren_inferior: bool) -> float:
    """Limita la subida respecto a la última carga (se permite al menos un incremento)."""
    tope_kg = TOPE_SUBIDA_KG["inferior" if tren_inferior else "superior"]
    subida_max = max(incremento, min(TOPE_SUBIDA_PCT * carga_anterior, tope_kg))
    return min(carga_propuesta, carga_anterior + subida_max)


def rpe_app(rpe: float) -> float:
    """Redondea al formato de la app (6-10, pasos de 0,5)."""
    return min(RPE_MAX_APP, max(RPE_MIN_APP, round(rpe * 2) / 2))
