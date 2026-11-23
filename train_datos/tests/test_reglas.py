"""Regla de la etiqueta del día y coherencia general de los datos generados."""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

# isort: split  (simulador y util se clasifican distinto según la carpeta desde la que se ejecuta ruff)
from simulador.motor import MAX_DIAS_SEGUIDOS, UMBRAL_ENTRENAR, UMBRAL_SUAVE
from simulador.salida import leer

# isort: split
from util import TABLAS_LOTE, claves

CLASES = {"entrenar", "suave", "descansar"}
TOLERANCIA = 1e-3   # readiness_real se guarda en float32: no se juzgan valores pegados al umbral


def _dias_con_racha(base) -> pd.DataFrame:
    """Une estado latente y etiqueta del día, y añade la racha de días entrenados
    seguidos hasta ayer, reconstruida solo a partir de la tabla sesion."""
    lat = leer(base, "sim_estado_latente")
    etq = leer(base, "etiquetas_dia")
    ses = leer(base, "sesion")
    dias = lat.merge(etq, on=["usuario_id", "fecha"], validate="one_to_one")
    assert len(dias) == len(lat) == len(etq)
    entreno = set(zip(ses["usuario_id"], ses["fecha"], strict=True))
    dias = dias.sort_values(["usuario_id", "fecha"]).reset_index(drop=True)

    rachas = np.zeros(len(dias), dtype=int)
    usuario_previo, fecha_previa, racha = None, None, 0
    for i, (u, f) in enumerate(zip(dias["usuario_id"], dias["fecha"], strict=True)):
        if u != usuario_previo:
            racha = 0
        else:
            assert (f - fecha_previa).days == 1, "faltan días en sim_estado_latente"
        rachas[i] = racha
        racha = racha + 1 if (u, f) in entreno else 0
        usuario_previo, fecha_previa = u, f
    dias["racha"] = rachas
    return dias


def _clase_esperada(lesion: bool, racha: int, readiness: float) -> str:
    if lesion or racha >= MAX_DIAS_SEGUIDOS:
        return "descansar"
    if readiness >= UMBRAL_ENTRENAR:
        return "entrenar"
    if readiness >= UMBRAL_SUAVE:
        return "suave"
    return "descansar"


@pytest.fixture(scope="module")
def dias(datos_base) -> pd.DataFrame:
    return _dias_con_racha(datos_base)


def test_etiqueta_del_dia_sigue_la_regla(dias):
    r = dias["readiness_real"].astype("float64")
    pegado = ((r - UMBRAL_ENTRENAR).abs() < TOLERANCIA) | ((r - UMBRAL_SUAVE).abs() < TOLERANCIA)
    juzgables = dias[~pegado]
    assert len(juzgables) >= 0.99 * len(dias)
    esperada = [_clase_esperada(bool(le), int(ra), float(re)) for le, ra, re in
                zip(juzgables["lesion"], juzgables["racha"], juzgables["readiness_real"],
                    strict=True)]
    malas = juzgables[juzgables["clase_estado"].to_numpy() != np.array(esperada)]
    assert malas.empty, f"{len(malas)} días no siguen la regla:\n{malas.head(10)}"


def test_max_dias_seguidos_es_6():
    """Decisión de "fixed T04": la rutina PPL tiene 6 días seguidos, así que con 5 la
    regla forzaba descansos triviales. Cambiarlo exige acordarlo y volver a validar."""
    assert MAX_DIAS_SEGUIDOS == 6


def test_la_regla_de_racha_se_ejercita(dias):
    """Sin días con racha >= MAX_DIAS_SEGUIDOS la prueba anterior no comprobaría nada."""
    forzados = dias[(dias["racha"] >= MAX_DIAS_SEGUIDOS) & ~dias["lesion"]]
    assert len(forzados) > 0
    assert (forzados["clase_estado"] == "descansar").all()


def test_no_hay_descanso_forzado_con_racha_5(dias):
    """Con 5 días seguidos (antes de "fixed T04" ya forzaba descansar) solo se descansa
    por lesión o por disposición baja. El 5 va escrito a propósito, no como
    MAX_DIAS_SEGUIDOS - 1, para que la prueba falle si se vuelve a poner 5."""
    previa = dias[(dias["racha"] == 5) & ~dias["lesion"]
                  & (dias["readiness_real"] >= UMBRAL_SUAVE + TOLERANCIA)]
    assert len(previa) > 0
    assert (previa["clase_estado"] != "descansar").all()


def test_racha_coincide_con_sesiones_consecutivas(datos_base, dias):
    est = leer(datos_base, "estado_diario")[["usuario_id", "fecha", "sesiones_consecutivas"]]
    unido = dias.merge(est, on=["usuario_id", "fecha"], validate="one_to_one")
    assert len(unido) == len(dias)
    assert (unido["racha"] == unido["sesiones_consecutivas"]).all()


# ---------------------------------------------------------------- coherencia

def test_clases_validas(datos_base):
    assert set(leer(datos_base, "etiquetas_dia")["clase_estado"].unique()) <= CLASES


def test_rpe_en_escala_de_la_app(datos_base):
    rpe = leer(datos_base, "serie")["rpe"].dropna().astype("float64")
    assert len(rpe) > 0
    assert rpe.between(6, 10).all()
    assert ((rpe * 2) == (rpe * 2).round()).all(), "hay RPE fuera de los pasos de 0,5"


@pytest.mark.parametrize("tabla", TABLAS_LOTE)
def test_claves_unicas(tabla, datos_base):
    df = leer(datos_base, tabla)
    assert not df.duplicated(claves(tabla, df)).any(), f"claves repetidas en {tabla}"


def test_ids_del_simulador_siguen_el_patron(datos_base):
    ses = leer(datos_base, "sesion")
    ser = leer(datos_base, "serie")
    prog = leer(datos_base, "programa")
    assert (ses["id"] // 10000 == ses["usuario_id"]).all()
    assert (ser["id"] // 100 == ser["sesion_id"]).all()
    assert (prog["id"] // 100 == prog["usuario_id"]).all()
    assert ser["sesion_id"].isin(ses["id"]).all()
    assert leer(datos_base, "usuario")["id"].tolist() == list(range(1, 41))
