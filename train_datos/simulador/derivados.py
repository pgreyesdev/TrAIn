"""Capa 3: tablas derivadas a partir del registro (capa 2).

El backend usará estas mismas funciones con los datos reales de la app, así que
el Motor de IA entrena y predice con exactamente las mismas variables.

Convención temporal de estado_diario: cada fila describe el estado al EMPEZAR
el día `fecha`, con datos hasta el día anterior (no hay fuga de información
del propio día). La columna carga_sesion es la carga de ese mismo día y solo
sirve para gráficas.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .formulas import ACTIVIDAD_EXTRA_UA, DUREZA_A_SRPE

TIPOS_EFECTIVA = ("efectiva", "fallo", "descendente")


def _con_peso(df: pd.DataFrame, medida: pd.DataFrame) -> pd.DataFrame:
    """Añade el último peso corporal registrado en o antes de cada fecha."""
    izq = df.sort_values("fecha")
    der = medida[["usuario_id", "fecha", "peso_kg"]].sort_values("fecha")
    res = pd.merge_asof(izq, der, on="fecha", by="usuario_id", direction="backward")
    # si no hay peso anterior (no debería pasar), usar el primero del usuario
    primero = medida.sort_values("fecha").groupby("usuario_id")["peso_kg"].first()
    res["peso_kg"] = res["peso_kg"].fillna(res["usuario_id"].map(primero))
    return res


def series_con_carga(serie, sesion, medida, ejercicio) -> pd.DataFrame:
    s = serie[serie["tipo"].isin(TIPOS_EFECTIVA)]
    s = s.merge(sesion[["id", "usuario_id", "fecha"]].rename(columns={"id": "sesion_id"}),
                on="sesion_id")
    s = s.merge(ejercicio[["id", "tipo_carga"]].rename(columns={"id": "ejercicio_id"}),
                on="ejercicio_id")
    s = _con_peso(s, medida)
    tipo = s["tipo_carga"]
    carga = s["carga_kg"].astype("float64")
    lastre = s["lastre_kg"].astype("float64").fillna(0)
    asist = s["asistencia_kg"].astype("float64").fillna(0)
    s["carga_efectiva"] = np.select(
        [tipo == "externa", tipo == "corporal_lastre", tipo == "asistida"],
        [carga, s["peso_kg"] + lastre, s["peso_kg"] - asist], default=np.nan)
    reps = s["reps"].astype("float64")
    rpe = s["rpe"].astype("float64").fillna(10.0)
    s["e1rm"] = np.where(reps > 0, s["carga_efectiva"] * (1 + (reps + 10 - rpe) / 30), np.nan)
    return s


def calcular_rendimiento(serie, sesion, medida, ejercicio) -> pd.DataFrame:
    s = series_con_carga(serie, sesion, medida, ejercicio)
    s["vol"] = s["reps"].astype("float64") * s["carga_efectiva"]
    s["fallidas"] = (s["reps_obj"].astype("float64") - s["reps"].astype("float64")).clip(lower=0)
    claves = ["sesion_id", "ejercicio_id"]
    agg = s.groupby(claves).agg(
        usuario_id=("usuario_id", "first"), fecha=("fecha", "first"),
        volumen_kg=("vol", lambda x: x.sum(min_count=1)),
        series_efectivas=("id", "size"), reps_fallidas=("fallidas", "sum"))
    # Desempate por orden de la serie (orden_ejercicio, num_serie y, por último, id): gana
    # la primera que logra el top. Con datos de la app el id es el orden de inserción.
    top = (s.sort_values(claves + ["e1rm", "reps", "orden_ejercicio", "num_serie", "id"],
                         ascending=[True, True, False, False, True, True, True], na_position="last")
           .drop_duplicates(claves)
           .set_index(claves)[["carga_efectiva", "reps", "rpe", "e1rm"]]
           .rename(columns={"carga_efectiva": "carga_efectiva_top", "reps": "reps_top",
                            "rpe": "rpe_top"}))
    res = agg.join(top).reset_index()
    res["reps_fallidas"] = res["reps_fallidas"].round().astype("Int16")
    res["series_efectivas"] = res["series_efectivas"].astype("int16")
    return res[["usuario_id", "sesion_id", "ejercicio_id", "fecha", "carga_efectiva_top",
                "reps_top", "rpe_top", "e1rm", "volumen_kg", "series_efectivas",
                "reps_fallidas"]]


def _ventana(df_ordenado: pd.DataFrame, col: str, dias: int, grupo) -> pd.Series:
    """Suma de `col` en los `dias` días anteriores (sin contar el propio día)."""
    acumulado = df_ordenado[col].groupby(grupo).cumsum()
    hasta_ayer = acumulado.groupby(grupo).shift(1, fill_value=0)
    hasta_hace_n = acumulado.groupby(grupo).shift(dias + 1, fill_value=0)
    return hasta_ayer - hasta_hace_n


def calcular_estado_diario(sesion, serie, ejercicio_musculo, musculo,
                           desde: pd.Series, hasta: pd.Series) -> pd.DataFrame:
    """`desde`/`hasta`: Series indexadas por usuario_id con el rango de fechas."""
    # --- carga de cada sesión (sRPE x minutos + otro deporte declarado)
    rpe_medio = (serie[serie["tipo"].isin(TIPOS_EFECTIVA)]
                 .groupby("sesion_id")["rpe"].mean().astype("float64"))
    ses = sesion[["id", "usuario_id", "fecha", "duracion_min", "dureza_sesion",
                  "actividad_extra"]].copy()
    srpe = ses["dureza_sesion"].astype("float64").map(DUREZA_A_SRPE)
    respaldo = (ses["id"].map(rpe_medio) - 1).clip(1, 10)
    ses["carga"] = (srpe.fillna(respaldo).fillna(5.0) * ses["duracion_min"].astype("float64")
                    + ses["actividad_extra"].astype("float64").fillna(0).map(ACTIVIDAD_EXTRA_UA))
    diaria = ses.groupby(["usuario_id", "fecha"])["carga"].sum()

    # --- rejilla de días por usuario
    n = ((hasta - desde).dt.days + 1).astype(int)
    usuarios = np.repeat(desde.index.to_numpy(), n.to_numpy())
    inicio = np.repeat(desde.to_numpy(dtype="datetime64[D]"), n.to_numpy())
    offset = np.concatenate([np.arange(k) for k in n.to_numpy()]) if len(n) else np.array([])
    rej = pd.DataFrame({"usuario_id": usuarios.astype("int32"),
                        "fecha": (inicio + offset.astype("timedelta64[D]")).astype("datetime64[s]")})
    rej = rej.merge(diaria.rename("carga_sesion").reset_index(),
                    on=["usuario_id", "fecha"], how="left")
    rej["carga_sesion"] = rej["carga_sesion"].fillna(0.0)
    rej = rej.sort_values(["usuario_id", "fecha"]).reset_index(drop=True)
    grupo = rej["usuario_id"]

    rej["carga_aguda_7d"] = _ventana(rej, "carga_sesion", 7, grupo)
    rej["carga_cronica_28d"] = _ventana(rej, "carga_sesion", 28, grupo) / 4
    rej["acwr"] = np.where(rej["carga_cronica_28d"] > 0,
                           rej["carga_aguda_7d"] / rej["carga_cronica_28d"].replace(0, np.nan),
                           np.nan)

    entreno = rej["carga_sesion"] > 0
    ultima = rej["fecha"].where(entreno).groupby(grupo).ffill()
    ultima_antes = ultima.groupby(grupo).shift(1)
    rej["dias_desde_ultima"] = (rej["fecha"] - ultima_antes).dt.days.astype("Int16")
    bloque = (~entreno).groupby(grupo).cumsum()
    racha = entreno.astype(int).groupby([grupo, bloque]).cumsum()
    rej["sesiones_consecutivas"] = racha.groupby(grupo).shift(1, fill_value=0).astype("int16")

    # --- series ponderadas por músculo en los 7 días anteriores
    efectivas = serie[serie["tipo"].isin(TIPOS_EFECTIVA)][["sesion_id", "ejercicio_id"]]
    efectivas = efectivas.merge(sesion[["id", "usuario_id", "fecha"]]
                                .rename(columns={"id": "sesion_id"}), on="sesion_id")
    em = ejercicio_musculo.merge(musculo[["id", "nombre"]].rename(columns={"id": "musculo_id"}),
                                 on="musculo_id")
    efectivas = efectivas.merge(em[["ejercicio_id", "nombre", "factor"]], on="ejercicio_id")
    vol = (efectivas.groupby(["usuario_id", "fecha", "nombre"])["factor"].sum()
           .unstack("nombre", fill_value=0.0))
    nombres = list(musculo["nombre"])
    vol = vol.reindex(columns=nombres, fill_value=0.0)
    vol.columns = [f"vol_{c}" for c in vol.columns]
    rej = rej.merge(vol.reset_index(), on=["usuario_id", "fecha"], how="left")
    for c in vol.columns:
        rej[c] = rej[c].fillna(0.0)
        rej[c] = _ventana(rej, c, 7, rej["usuario_id"]).astype("float32")
    return rej
