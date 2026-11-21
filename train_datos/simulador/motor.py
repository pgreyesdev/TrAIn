"""Simulación de un usuario día a día.

Para cada usuario se inventa una "verdad oculta" (fuerza real por ejercicio,
fatiga real, sueño, lesiones) y, a partir de ella, lo que el usuario *anotaría*
en la app (capa 2), con ruido y con su propia forma de elegir las cargas.
De la verdad oculta salen también las etiquetas (capa 4).

Todo se guarda como tuplas en listas para ir rápido; `salida.py` las convierte
en DataFrames con las columnas de COLUMNAS.
"""
from __future__ import annotations

import math
import random
from datetime import date

from . import formulas as F
from .catalogo import GRUPOS, MUSCULOS
from .programas import DIVISIONES, construir

COLUMNAS = {
    # capa 2
    "usuario": ["id", "sexo", "fecha_nacimiento", "altura_cm", "nivel", "objetivo",
                "dias_semana", "fecha_alta", "es_sintetico"],
    "medida_corporal": ["id", "usuario_id", "fecha", "peso_kg", "grasa_pct"],
    "programa": ["id", "usuario_id", "tipo_division", "fecha_inicio", "fecha_fin", "activo"],
    "programa_ejercicio": ["id", "programa_id", "dia", "orden", "ejercicio_id",
                           "series_obj", "reps_obj", "rpe_obj"],
    "sesion": ["id", "usuario_id", "programa_id", "dia_programa", "fecha", "hora_inicio",
               "duracion_min", "sueno", "cuerpo", "energia", "actividad_extra", "dolor",
               "zona_dolor_id", "dureza_sesion", "notas"],
    "serie": ["id", "sesion_id", "ejercicio_id", "orden_ejercicio", "num_serie", "tipo",
              "reps_obj", "reps", "carga_kg", "lastre_kg", "asistencia_kg", "duracion_s",
              "distancia_m", "rpe", "completada"],
    # capa 4 (simulación + etiquetas)
    "sim_usuario_param": ["usuario_id", "talento", "recuperacion", "adherencia", "ruido_rpe",
                          "sesgo_carga", "techo_fuerza", "estilo", "prob_cuestionario",
                          "prob_deporte"],
    "sim_fuerza_latente": ["usuario_id", "sesion_id", "ejercicio_id", "fecha", "e1rm_real",
                           "e1rm_dia"],
    "sim_estado_latente": ["usuario_id", "fecha", "forma", "fatiga_real", "readiness_real",
                           "lesion"],
    "etiquetas_carga": ["usuario_id", "sesion_id", "ejercicio_id", "fecha",
                        "carga_recomendada", "carga_efectiva_recomendada",
                        "carga_efectiva_anterior", "cambio_kg"],
    "etiquetas_dia": ["usuario_id", "fecha", "clase_estado", "fatiga"],
}

N_MUSC = len(MUSCULOS)
GRUPO_DE_MUSCULO = [GRUPOS.index(g) + 1 for g in MUSCULOS.values()]

# ---- parámetros de la simulación (ajustables) ----
FACTOR_NIVEL = {"principiante": 0.6, "intermedio": 1.0, "avanzado": 1.35}
TECHO_NIVEL = {"principiante": 1.9, "intermedio": 1.35, "avanzado": 1.12}
TASA_ADAPTACION = {"principiante": 0.02, "intermedio": 0.008, "avanzado": 0.003}
FACTOR_MUJER = {"superior": 0.55, "inferior": 0.72}
TAU_MUSCULO = 1.8      # días: recuperación local (agujetas)
TAU_GLOBAL = 4.5       # días: fatiga sistémica
G50 = 20.0             # fatiga global que equivale a fatiga_real = 50
CAIDA_POR_FATIGA_MUSCULAR = 0.003
CAIDA_POR_FATIGA_GLOBAL = 0.0008
FATIGA_MUSCULAR_POR_SERIE = 3.0
TRANSFERENCIA_PATRON = 0.6   # parte de la mejora que pasa a ejercicios del mismo patrón
DESENTRENO_DIARIO = 0.999    # a partir de 14 días sin hacer el ejercicio
DESENTRENO_MAX = 0.92        # pérdida máxima por una pausa
PESO_SUENO = 5.0             # puntos de disposición por desviación de sueño
PESO_MUSCULO = 0.8           # puntos por unidad de fatiga muscular máxima
UMBRAL_ENTRENAR = 58.0
UMBRAL_SUAVE = 47.0
MAX_DIAS_SEGUIDOS = 6        # descansar tras 6 días seguidos (≥ 1 día libre por semana; admite la PPL de 6 días)
UMBRAL_CUERPO = (4.0, 9.0)   # fatiga muscular máxima: fresco < 4 <= algo cargado < 9 <= muy cargado
ESTILOS = ["progresivo", "conservador", "agresivo", "repetidor"]
P_ESTILOS = [0.40, 0.25, 0.15, 0.20]


def _elegir(rng, opciones, pesos):
    return rng.choices(opciones, weights=pesos, k=1)[0]


def _clip(x, lo, hi):
    return lo if x < lo else hi if x > hi else x


def nueva_salida():
    return {t: [] for t in COLUMNAS}


def simular_usuario(uid: int, rng: random.Random, ejercicios, fecha_min: int,
                    fecha_max: int, n_dias: int, out: dict) -> None:
    # ------------------------------------------------------------- perfil
    sexo = "H" if rng.random() < 0.6 else "M"
    edad = int(_clip(rng.gauss(30, 8), 17, 65))
    nivel = _elegir(rng, ["principiante", "intermedio", "avanzado"], [0.40, 0.45, 0.15])
    objetivo = _elegir(rng, ["fuerza", "hipertrofia", "mantenimiento", "perdida_grasa"],
                       [0.20, 0.40, 0.15, 0.25])
    dias_semana = _elegir(rng, [2, 3, 4, 5, 6], [0.08, 0.30, 0.32, 0.20, 0.10])
    altura = rng.gauss(177 if sexo == "H" else 164, 7)
    imc = rng.gauss(24.5 if sexo == "H" else 23.0, 3.0)
    if objetivo == "perdida_grasa":
        imc += 2.5
    peso0 = _clip(imc * (altura / 100) ** 2, 45, 160)
    alta = rng.randint(fecha_min, fecha_max)
    nacimiento = alta - int(edad * 365.25) - rng.randint(0, 364)
    out["usuario"].append((uid, sexo, nacimiento, round(altura, 1), nivel, objetivo,
                           dias_semana, alta, True))

    # ---------------------------------------------- rasgos ocultos (capa 4)
    talento = math.exp(rng.gauss(0, 0.3))
    recuperacion = math.exp(rng.gauss(0, 0.25))
    adherencia = rng.betavariate(8, 2)
    ruido_rpe = rng.uniform(0.25, 1.0)
    sesgo = rng.gauss(0, 0.04)
    techo = math.exp(rng.gauss(0, 0.12))
    estilo = _elegir(rng, ESTILOS, P_ESTILOS)
    p_cuest = rng.betavariate(4, 2)
    p_deporte = 0.0 if rng.random() < 0.6 else rng.uniform(0.08, 0.3)
    sueno_medio = rng.gauss(0, 0.3)
    hora_pref = _clip(rng.gauss(18, 3), 7, 22)
    out["sim_usuario_param"].append((uid, talento, recuperacion, adherencia, ruido_rpe,
                                     sesgo, techo, estilo, p_cuest, p_deporte))

    # ------------------------------------------- fuerza inicial por ejercicio
    indiv = math.exp(rng.gauss(0, 0.12))
    e1rm, techo_ej = {}, {}
    for e in ejercicios:
        if e.tipo_carga == "tiempo":
            base = 60.0 * FACTOR_NIVEL[nivel] * indiv * math.exp(rng.gauss(0, 0.15))
            e1rm[e.id], techo_ej[e.id] = base, base * TECHO_NIVEL[nivel]
            continue
        f_sexo = 1.0 if sexo == "H" else FACTOR_MUJER["inferior" if e.inferior else "superior"]
        base = peso0 * e.ratio * f_sexo * FACTOR_NIVEL[nivel] * indiv * math.exp(rng.gauss(0, 0.08))
        e1rm[e.id] = base
        techo_ej[e.id] = base * TECHO_NIVEL[nivel] * techo
    e1rm_inicial = dict(e1rm)
    mismo_patron = {e.id: [o.id for o in ejercicios if o.patron == e.patron and o.id != e.id
                           and o.tipo_carga != "tiempo"]
                    for e in ejercicios}

    # ------------------------------------------------------ estado oculto
    fm = [0.0] * N_MUSC          # fatiga por músculo
    g = 0.0                      # fatiga global
    z_sueno = 0.0
    lesion_hasta, lesion_zona = -1, None
    dias_seguidos = 0
    deporte_desde_ultima = 0
    recuperar_pendiente = False
    decay_m = math.exp(-recuperacion / TAU_MUSCULO)
    decay_g = math.exp(-recuperacion / TAU_GLOBAL)
    deriva = {"perdida_grasa": -0.0006, "hipertrofia": 0.0002}.get(objetivo, 0.0)

    vacaciones = set()
    for _ in range(max(1, round(n_dias / 365 * rng.choice([1, 1, 2])))):
        ini = rng.randint(30, max(31, n_dias - 20))
        vacaciones.update(range(ini, ini + rng.randint(7, 16)))

    # memoria del usuario por ejercicio (lo que "recuerda" y apunta)
    carga_trabajo = {}           # carga registrada habitual (kg o lastre)
    racha = {}
    ultima_vez = {}
    ultima_top = {}              # carga efectiva top de la sesión anterior

    # ------------------------------------------------------------ programa
    n_prog = 0
    prog_id = None
    prog_fin = 0
    dias_prog = []
    puntero = 0
    _, _, dias_plan = DIVISIONES[dias_semana]
    n_ses = 0
    n_medida = 0

    def puede_hacer(e):
        if e.tipo_carga == "corporal_lastre":
            return e1rm[e.id] > 1.15 * peso_actual
        return True

    peso_actual = peso0
    for d in range(n_dias):
        fecha = alta + d
        # ------------------------------------------- recuperación nocturna
        for m in range(N_MUSC):
            fm[m] *= decay_m
        g *= decay_g
        z_sueno = 0.5 * z_sueno + rng.gauss(0, 0.87)
        sueno = _clip(z_sueno + sueno_medio, -2.0, 2.0)
        peso_actual = peso0 * (1 + deriva * min(d, 140)) + rng.gauss(0, 0.3)

        if d == 0 or (d % 7 == 0 and rng.random() < 0.6):
            out["medida_corporal"].append((uid * 1000 + n_medida, uid, fecha,
                                           round(peso_actual, 1), None))
            n_medida += 1

        # ------------------------------------------- programa nuevo
        if d >= prog_fin:
            if prog_id is not None:
                fila = out["programa"][-1]
                out["programa"][-1] = (fila[0], fila[1], fila[2], fila[3], fecha - 1, False)
            prog_id = uid * 100 + n_prog
            n_prog += 1
            division, dias_prog = construir(rng, dias_semana, objetivo, nivel, ejercicios,
                                            puede_hacer)
            out["programa"].append((prog_id, uid, division, fecha, None, True))
            k = 0
            for i, dia in enumerate(dias_prog, start=1):
                for orden, (e, series, reps, rpe) in enumerate(dia, start=1):
                    out["programa_ejercicio"].append(
                        (prog_id * 100 + k, prog_id, i, orden, e.id, series, reps, rpe))
                    k += 1
            prog_fin = d + 7 * rng.randint(8, 16)
            puntero = 0

        # ------------------------------------------- estado de la mañana
        fatiga = 100.0 * g / (g + G50)
        lesion = d <= lesion_hasta
        fm_max_dia = max(fm)
        readiness = (100.0 - 0.9 * fatiga + PESO_SUENO * sueno - PESO_MUSCULO * fm_max_dia
                     - (25.0 if lesion else 0.0))
        if lesion or dias_seguidos >= MAX_DIAS_SEGUIDOS:
            clase = "descansar"
        elif readiness >= UMBRAL_ENTRENAR:
            clase = "entrenar"
        elif readiness >= UMBRAL_SUAVE:
            clase = "suave"
        else:
            clase = "descansar"
        forma = sum(e1rm[k] / e1rm_inicial[k] for k in e1rm) / len(e1rm)
        out["sim_estado_latente"].append((uid, fecha, forma, fatiga, readiness, lesion))
        out["etiquetas_dia"].append((uid, fecha, clase, fatiga))

        if not lesion:
            riesgo = 0.0005 * (1 + fatiga / 25) * (2.0 if estilo == "agresivo" else 1.0)
            if rng.random() < riesgo:
                lesion_hasta = d + rng.randint(3, 14)
                m_max = max(range(N_MUSC), key=lambda m: fm[m])
                lesion_zona = GRUPO_DE_MUSCULO[m_max] if fm[m_max] > 1 else rng.randint(1, 7)

        # ------------------------------------------- ¿entrena hoy?
        planificado = date.fromordinal(fecha).weekday() in dias_plan
        entrena = False
        if d not in vacaciones:
            if planificado:
                p = adherencia * (0.5 if lesion else 1.0) * (0.8 if fatiga > 75 else 1.0)
                entrena = rng.random() < p
                recuperar_pendiente = not entrena
            elif recuperar_pendiente and rng.random() < 0.3:
                entrena, recuperar_pendiente = True, False

        if entrena:
            ses_id = uid * 10000 + n_ses
            n_ses += 1
            dia_idx = puntero % len(dias_prog)
            puntero += 1
            responde = rng.random() < p_cuest
            fm_max_manana = max(fm)           # el cuestionario se responde antes de entrenar
            g_sesion, n_series, rpes_sesion, n_calent = 0.0, 0, [], 0
            orden_ej = 0
            for (e, series, reps_obj, rpe_obj) in dias_prog[dia_idx]:
                zona_afectada = lesion and e.grupo_id == lesion_zona
                if zona_afectada and rng.random() < 0.7:
                    continue
                if rng.random() < 0.05:          # se salta un ejercicio (prisa, máquina ocupada)
                    continue
                orden_ej += 1
                # desentrenamiento perezoso
                if e.id in ultima_vez and d - ultima_vez[e.id] > 14:
                    e1rm[e.id] *= max(DESENTRENO_MAX,
                                      DESENTRENO_DIARIO ** (d - ultima_vez[e.id] - 14))
                rend_dia = ((1 - CAIDA_POR_FATIGA_GLOBAL * fatiga) * (1 + 0.015 * sueno)
                            * rng.gauss(1, 0.015) * (0.85 if zona_afectada else 1.0))

                def fuerza_ahora():
                    fw = sum(f * fm[m] for m, f in e.musculos) / sum(f for _, f in e.musculos)
                    return e1rm[e.id] * rend_dia * (1 - CAIDA_POR_FATIGA_MUSCULAR * fw)

                e_inicio = fuerza_ahora()
                inc = e.incremento
                out["sim_fuerza_latente"].append((uid, ses_id, e.id, fecha, e1rm[e.id], e_inicio))

                # ---- carga que usará el usuario (registrada)
                lastre = e.tipo_carga == "corporal_lastre"
                if e.en_modelo:
                    if e.id not in carga_trabajo:
                        error = math.exp(rng.gauss(sesgo - 0.05,
                                                   0.15 if nivel == "principiante" else 0.10))
                        objetivo_ef = e_inicio * F.pct_1rm(reps_obj, rpe_obj) * error
                        w = objetivo_ef - peso_actual if lastre else objetivo_ef
                        carga_trabajo[e.id] = max(0.0 if lastre else inc, F.redondear(w, inc))
                        racha[e.id] = 0
                    else:
                        w = carga_trabajo[e.id]
                        if d - ultima_vez[e.id] > 14 and rng.random() < 0.6:
                            w *= 0.9
                        if zona_afectada:
                            w *= 0.8
                        carga_trabajo[e.id] = max(0.0 if lastre else inc, F.redondear(w, inc))

                    # ---- etiqueta: carga correcta para hoy
                    if e.id in ultima_top:
                        anterior = ultima_top[e.id]
                        opt = e_inicio * F.pct_1rm(reps_obj, rpe_obj)
                        tope = F.tope_seguridad(anterior, opt, inc, e.inferior)
                        limitado = tope < opt   # la regla de seguridad recorta la subida
                        base = peso_actual if lastre else 0.0
                        if limitado:
                            reg = math.floor((tope - base) / inc + 1e-9) * inc
                        else:
                            reg = F.redondear(tope - base, inc)
                        reg = max(0.0 if lastre else inc, reg)
                        ef = base + reg
                        out["etiquetas_carga"].append((uid, ses_id, e.id, fecha, reg, ef,
                                                       anterior, ef - anterior))

                # ---- calentamiento
                if orden_ej == 1 and e.mecanica == "compuesto" and e.tipo_carga == "externa" \
                        and rng.random() < 0.7:
                    for j, (pct, r) in enumerate(((0.5, 8), (0.7, 4)), start=1):
                        c = max(inc, F.redondear(carga_trabajo[e.id] * pct, inc))
                        out["serie"].append((ses_id * 100 + n_series, ses_id, e.id, orden_ej, j,
                                             "calentamiento", r, r, c, None, None, None, None,
                                             None, True))
                        n_series += 1
                        n_calent += 1
                num0 = n_calent if orden_ej == 1 else 0

                # ---- series efectivas
                if e.tipo_carga == "externa":
                    carga_ef = carga_trabajo[e.id]
                elif lastre:
                    carga_ef = peso_actual + carga_trabajo[e.id]
                elif e.tipo_carga == "corporal":
                    carga_ef = e.fraccion_corporal * peso_actual
                else:
                    carga_ef = None
                reps_hechas, rpes, estimulo = [], [], 0.0
                for j in range(1, series + 1):
                    ahora = fuerza_ahora()
                    if e.tipo_carga == "tiempo":
                        dur = int(min(reps_obj, ahora))
                        rpe_real = _clip(10 - 6 * (ahora - dur) / ahora, 5, 10)
                        reps, fallo = None, ahora < reps_obj
                    else:
                        cap = F.reps_hasta_fallo(ahora, carga_ef)
                        fallo = cap < reps_obj
                        reps = reps_obj if not fallo else max(0, int(cap))
                        rpe_real = _clip(10 - max(0.0, cap - reps), 5, 10)
                        dur = None
                    rpe_reg = F.rpe_app(rpe_real + rng.gauss(0, ruido_rpe))
                    esfuerzo = 0.4 + 0.6 * _clip((rpe_real - 5) / 5, 0, 1)
                    for m, f in e.musculos:
                        fm[m] += f * esfuerzo * FATIGA_MUSCULAR_POR_SERIE
                    g_sesion += e.factor_fatiga * esfuerzo
                    if reps is None or reps > 0:
                        estimulo += max(0.0, (rpe_real - 5) / 5)
                    out["serie"].append((
                        ses_id * 100 + n_series, ses_id, e.id, orden_ej, num0 + j,
                        "efectiva", reps_obj if reps is not None else None,
                        reps,
                        carga_trabajo[e.id] if e.tipo_carga == "externa" else None,
                        carga_trabajo[e.id] if lastre else None,
                        None, dur, None, rpe_reg, reps is None or reps > 0))
                    n_series += 1
                    rpes.append(rpe_reg)
                    rpes_sesion.append(rpe_reg)
                    if reps is not None:
                        reps_hechas.append(reps)

                # ---- adaptación (la verdad oculta mejora)
                estim = min(estimulo, 4.0) / 3.0 * (1 - fatiga / 150)
                tasa = TASA_ADAPTACION[nivel] * talento * (1 - e1rm[e.id] / techo_ej[e.id]) * estim
                if tasa > 0:
                    e1rm[e.id] *= 1 + tasa
                for o in mismo_patron[e.id]:
                    t_o = (TASA_ADAPTACION[nivel] * talento * TRANSFERENCIA_PATRON
                           * (1 - e1rm[o] / techo_ej[o]) * estim)
                    if t_o > 0:
                        e1rm[o] *= 1 + t_o
                    if o in ultima_vez:
                        ultima_vez[o] = max(ultima_vez[o], d - 7)  # el patrón se mantiene entrenado
                ultima_vez[e.id] = d

                # ---- el usuario decide su próxima carga, a su manera
                if e.en_modelo and reps_hechas:
                    ultima_top[e.id] = carga_ef
                    rpe_medio = sum(rpes) / len(rpes)
                    faltan = reps_obj - min(reps_hechas)
                    exito = faltan <= 0 and rpe_medio <= rpe_obj
                    facil = exito and rpe_medio <= rpe_obj - 1.5
                    falla = faltan >= 2 or (faltan == 1 and rng.random() < 0.5)
                    demasiado = falla or rpe_medio >= rpe_obj + 0.75
                    w = carga_trabajo[e.id]
                    if estilo == "progresivo":       # el usuario "de manual"
                        if facil:
                            w += 2 * inc
                        elif exito and rpe_medio <= rpe_obj - 0.75:
                            w += inc
                        elif demasiado:
                            w -= inc
                    elif estilo == "conservador":
                        if exito:
                            racha[e.id] += 1
                            if racha[e.id] >= 2:
                                w += inc
                                racha[e.id] = 0
                        else:
                            racha[e.id] = 0
                            if demasiado:
                                w -= inc
                    elif estilo == "agresivo":
                        if faltan >= 2:
                            w -= inc if rng.random() < 0.5 else 0
                        elif faltan <= 0:
                            w += 2 * inc if facil else inc
                    else:  # repetidor
                        if exito and rng.random() < 0.15:
                            w += inc
                        elif falla and rng.random() < 0.5:
                            w -= inc
                    if rng.random() < 0.05:
                        w += inc * rng.choice((-1, 1))
                    carga_trabajo[e.id] = max(0.0 if lastre else inc, w)

            g += g_sesion

            # ---- cuestionario y datos de la sesión
            efectivas = n_series - n_calent
            duracion = int(max(10, efectivas * 2.6 + n_calent * 1.5 + rng.gauss(5, 3)))
            hora = int(_clip(hora_pref + rng.gauss(0, 1), 6, 22))
            hora_inicio = f"{hora:02d}:{rng.choice((0, 15, 30, 45)):02d}:00"
            sueno_r = cuerpo_r = energia_r = extra_r = dolor_r = zona_r = dureza_r = None
            if responde:
                sueno_r = 1 if sueno < -0.7 else 3 if sueno > 0.7 else 2
                if rng.random() < 0.15:
                    sueno_r = int(_clip(sueno_r + rng.choice((-1, 1)), 1, 3))
                cuerpo_r = 1 if fm_max_manana < UMBRAL_CUERPO[0] else \
                    2 if fm_max_manana < UMBRAL_CUERPO[1] else 3
                if rng.random() < 0.15:
                    cuerpo_r = int(_clip(cuerpo_r + rng.choice((-1, 1)), 1, 3))
                en = readiness + rng.gauss(0, 10)
                energia_r = 3 if en > 65 else 1 if en < 40 else 2
                extra_r = deporte_desde_ultima if rng.random() < 0.9 else 0
                if lesion:
                    dolor_r = rng.random() < 0.9
                    zona_r = (lesion_zona if rng.random() < 0.85 else rng.randint(1, 7)) \
                        if dolor_r else None
                else:
                    dolor_r = rng.random() < 0.02
                    zona_r = rng.randint(1, 7) if dolor_r else None
                if rpes_sesion and rng.random() < 0.9:
                    media = sum(rpes_sesion) / len(rpes_sesion)
                    dureza_r = 1 if media < 7 else 2 if media < 8 else 3 if media < 9 else 4
                    if rng.random() < 0.15:
                        dureza_r = int(_clip(dureza_r + rng.choice((-1, 1)), 1, 4))
            out["sesion"].append((ses_id, uid, prog_id, dia_idx + 1, fecha, hora_inicio, duracion,
                                  sueno_r, cuerpo_r, energia_r, extra_r, dolor_r, zona_r,
                                  dureza_r, None))
            deporte_desde_ultima = 0
            dias_seguidos += 1
        else:
            dias_seguidos = 0

        # ------------------------------------------- otro deporte por la tarde
        if p_deporte and d not in vacaciones and rng.random() < p_deporte:
            intensidad = 1 if rng.random() < 0.6 else 2
            g += 3.0 if intensidad == 1 else 7.0
            deporte_desde_ultima = max(deporte_desde_ultima, intensidad)
