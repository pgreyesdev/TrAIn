"""Rutinas: divisiones, plantillas de días y objetivos de series/reps/RPE."""
from __future__ import annotations

import random

# Hueco de una plantilla: (grupo, mecánica o None, músculo primario o None)
C, A = "compuesto", "aislamiento"
PECHO, ESPALDA, CUAD, POST, HOMBRO, BRAZOS, CORE = (
    "Pecho", "Espalda", "Cuádriceps", "Cadena posterior", "Hombro", "Brazos", "Core y gemelos")

H_CORE = (CORE, None, "abdomen")
H_GEMELO = (CORE, None, "gemelo")
H_BICEPS = (BRAZOS, None, "biceps")
H_TRICEPS = (BRAZOS, None, "triceps")

DIAS = {
    "fb_a": [(CUAD, C, None), (PECHO, C, None), (ESPALDA, C, None), (HOMBRO, A, None), H_BICEPS, H_CORE],
    "fb_b": [(POST, C, None), (HOMBRO, C, None), (ESPALDA, C, None), (CUAD, None, None), H_TRICEPS, H_GEMELO],
    "fb_c": [(CUAD, C, None), (PECHO, C, None), (ESPALDA, C, None), (POST, A, None), (HOMBRO, A, None), H_CORE],
    "torso": [(PECHO, C, None), (ESPALDA, C, None), (HOMBRO, C, None), (ESPALDA, C, None),
              (PECHO, None, None), H_BICEPS, H_TRICEPS],
    "pierna": [(CUAD, C, None), (POST, C, None), (CUAD, None, None), (POST, A, None), H_GEMELO, H_CORE],
    "empuje": [(PECHO, C, None), (HOMBRO, C, None), (PECHO, None, None),
               (HOMBRO, A, "deltoides_lateral"), H_TRICEPS, H_TRICEPS],
    "tiron": [(ESPALDA, C, None), (ESPALDA, C, None), (HOMBRO, A, "deltoides_posterior"),
              H_BICEPS, H_BICEPS, H_CORE],
    "w_pecho": [(PECHO, C, None), (PECHO, C, None), (PECHO, A, None), H_TRICEPS, H_CORE],
    "w_espalda": [(ESPALDA, C, None), (ESPALDA, C, None), (ESPALDA, C, None),
                  (HOMBRO, A, "deltoides_posterior"), H_BICEPS],
    "w_hombro": [(HOMBRO, C, None), (HOMBRO, A, "deltoides_lateral"), (HOMBRO, A, None),
                 (HOMBRO, A, "deltoides_posterior"), H_GEMELO, H_CORE],
    "w_brazos": [H_BICEPS, H_TRICEPS, H_BICEPS, H_TRICEPS, H_CORE],
}

# días/semana -> (división, secuencia de días de la plantilla, días de la semana 0=lunes)
DIVISIONES = {
    2: ("full_body", ["fb_a", "fb_b"], [0, 3]),
    3: ("full_body", ["fb_a", "fb_b", "fb_c"], [0, 2, 4]),
    4: ("torso_pierna", ["torso", "pierna", "torso", "pierna"], [0, 1, 3, 4]),
    5: ("weider", ["w_pecho", "w_espalda", "pierna", "w_hombro", "w_brazos"], [0, 1, 2, 3, 4]),
    6: ("ppl", ["empuje", "tiron", "pierna", "empuje", "tiron", "pierna"], [0, 1, 2, 3, 4, 5]),
}

# objetivo -> mecánica -> (series, [reps posibles], rpe)
OBJETIVOS = {
    "fuerza":        {C: (4, [3, 5, 6], 8.0),  A: (3, [10, 12], 8.0)},
    "hipertrofia":   {C: (3, [6, 8, 10], 8.0), A: (3, [10, 12, 15], 8.5)},
    "mantenimiento": {C: (3, [8, 10], 7.0),    A: (3, [12], 7.5)},
    "perdida_grasa": {C: (3, [10, 12], 7.5),   A: (3, [12, 15], 8.0)},
}


def candidatos(hueco, ejercicios, excluir):
    grupo, mecanica, primario = hueco
    return [e for e in ejercicios
            if e.grupo == grupo
            and (mecanica is None or e.mecanica == mecanica)
            and (primario is None or e.primario == primario)
            and e.id not in excluir]


def construir(rng: random.Random, dias_semana: int, objetivo: str, nivel: str,
              ejercicios, puede_hacer) -> tuple[str, list]:
    """Devuelve (división, días) donde cada día es una lista de prescripciones
    (ejercicio, series, reps_obj, rpe_obj). `puede_hacer(e)` descarta, por ejemplo,
    dominadas si el usuario no puede con su peso."""
    division, plantilla, _ = DIVISIONES[dias_semana]
    elegidos_por_tipo: dict[str, list] = {}
    dias = []
    for nombre_dia in plantilla:
        # Los días repetidos (torso/pierna, PPL) reutilizan la misma selección
        if nombre_dia in elegidos_por_tipo:
            dias.append(elegidos_por_tipo[nombre_dia])
            continue
        usados: set[int] = set()
        dia = []
        for hueco in DIAS[nombre_dia]:
            opciones = [e for e in candidatos(hueco, ejercicios, usados) if puede_hacer(e)]
            if not opciones:
                continue
            e = rng.choice(opciones)
            usados.add(e.id)
            series, reps_posibles, rpe = OBJETIVOS[objetivo][e.mecanica]
            if nivel == "avanzado" and e.mecanica == C:
                series += 1
            if e.tipo_carga == "tiempo":
                reps = rng.choice([30, 45, 60])        # segundos objetivo
            elif e.tipo_carga == "corporal":
                reps = {"principiante": e.reps_min, "intermedio": 10,
                        "avanzado": e.reps_max}[nivel]
            else:
                reps = min(max(rng.choice(reps_posibles), e.reps_min), e.reps_max)
            dia.append((e, series, reps, rpe))
        elegidos_por_tipo[nombre_dia] = dia
        dias.append(dia)
    return division, dias
