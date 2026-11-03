"""Comprobación rápida de que los datos sintéticos se pueden aprender.

No es el Motor de IA: construye un conjunto mínimo de variables, entrena dos
modelos sencillos (HistGradientBoosting) y los compara con las líneas base del
ACP. Sirve para validar el simulador y como punto de partida para el Motor.

    python validar.py --datos datos [--max-usuarios 2000]
"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier, HistGradientBoostingRegressor
from sklearn.metrics import f1_score, mean_absolute_error
from sklearn.model_selection import GroupShuffleSplit

from simulador.formulas import pct_1rm
from simulador.salida import leer


def dataset_carga(b, usuarios):
    filtro = lambda df: df[df["usuario_id"].isin(usuarios)]  # noqa: E731
    et = filtro(leer(b, "etiquetas_carga"))
    rend = filtro(leer(b, "rendimiento_ejercicio")).sort_values(["usuario_id", "ejercicio_id", "fecha"])
    ses = filtro(leer(b, "sesion"))
    est = filtro(leer(b, "estado_diario"))
    usu = leer(b, "usuario").rename(columns={"id": "usuario_id"})
    ej = leer(b, "ejercicio").rename(columns={"id": "ejercicio_id"})
    pe = leer(b, "programa_ejercicio")

    # historial: valores de la sesión anterior del mismo ejercicio (lag 1) y tendencia
    g = rend.groupby(["usuario_id", "ejercicio_id"])
    rend["n_previas"] = g.cumcount()
    for c in ["carga_efectiva_top", "reps_top", "rpe_top", "e1rm", "reps_fallidas", "fecha"]:
        rend[f"{c}_ant"] = g[c].shift(1)
    rend["e1rm_ant3"] = g["e1rm"].shift(3)
    rend["tendencia_e1rm"] = (rend["e1rm_ant"] - rend["e1rm_ant3"]) / rend["e1rm_ant3"]
    rend["dias_mismo_ej"] = (rend["fecha"] - rend["fecha_ant"]).dt.days
    hist = rend[["sesion_id", "ejercicio_id", "n_previas", "carga_efectiva_top_ant", "reps_top_ant",
                 "rpe_top_ant", "e1rm_ant", "reps_fallidas_ant", "tendencia_e1rm", "dias_mismo_ej"]]

    df = et.merge(hist, on=["sesion_id", "ejercicio_id"], how="left")
    df = df.merge(ses[["id", "programa_id", "dia_programa", "sueno", "cuerpo", "energia",
                       "actividad_extra", "dolor"]].rename(columns={"id": "sesion_id"}),
                  on="sesion_id")
    df = df.merge(pe[["programa_id", "dia", "ejercicio_id", "reps_obj", "rpe_obj", "series_obj"]]
                  .rename(columns={"dia": "dia_programa"})
                  .drop_duplicates(["programa_id", "dia_programa", "ejercicio_id"]),
                  on=["programa_id", "dia_programa", "ejercicio_id"], how="left")
    df = df.merge(est[["usuario_id", "fecha", "carga_aguda_7d", "carga_cronica_28d", "acwr",
                       "dias_desde_ultima", "sesiones_consecutivas"]], on=["usuario_id", "fecha"],
                  how="left")
    df = df.merge(usu[["usuario_id", "sexo", "nivel", "objetivo"]], on="usuario_id")
    df = df.merge(ej[["ejercicio_id", "patron_id", "mecanica", "incremento_kg", "tipo_carga"]],
                  on="ejercicio_id")
    # sugerencia "de fórmula": e1RM anterior al % que piden reps y RPE objetivo
    df["sugerencia_formula"] = (df["e1rm_ant"] * pct_1rm(df["reps_obj"].astype(float),
                                                         df["rpe_obj"].astype(float))
                                - df["carga_efectiva_anterior"])
    return df


def dataset_dia(b, usuarios):
    filtro = lambda df: df[df["usuario_id"].isin(usuarios)]  # noqa: E731
    et = filtro(leer(b, "etiquetas_dia"))
    est = filtro(leer(b, "estado_diario"))
    ses = filtro(leer(b, "sesion"))
    usu = leer(b, "usuario").rename(columns={"id": "usuario_id"})
    df = et.merge(est.drop(columns=["carga_sesion"]), on=["usuario_id", "fecha"])
    # el cuestionario solo existe los días que el usuario abre la app para entrenar
    q = ses[["usuario_id", "fecha", "sueno", "cuerpo", "energia", "actividad_extra", "dolor"]]
    df = df.merge(q.drop_duplicates(["usuario_id", "fecha"]), on=["usuario_id", "fecha"], how="left")
    df = df.merge(usu[["usuario_id", "sexo", "nivel", "objetivo", "dias_semana"]], on="usuario_id")
    return df


def preparar(df, columnas):
    X = df[columnas].copy()
    for c in X.columns:
        if pd.api.types.is_bool_dtype(X[c]) or pd.api.types.is_numeric_dtype(X[c]):
            X[c] = X[c].astype("float64")
        else:
            X[c] = X[c].astype("category")
    return X


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--datos", default="datos")
    ap.add_argument("--max-usuarios", type=int, default=2000)
    ap.add_argument("--semilla", type=int, default=0)
    args = ap.parse_args()

    usuarios = leer(args.datos, "usuario")["id"]
    usuarios = usuarios.sample(min(len(usuarios), args.max_usuarios), random_state=args.semilla)

    # ------------------------------------------------ modelo de cargas
    df = dataset_carga(args.datos, usuarios)
    df = df[df["tipo_carga"].isin(["externa", "corporal_lastre"])].dropna(subset=["e1rm_ant"])
    cols = ["carga_efectiva_anterior", "reps_top_ant", "rpe_top_ant", "e1rm_ant", "reps_fallidas_ant",
            "tendencia_e1rm", "dias_mismo_ej", "n_previas", "reps_obj", "rpe_obj", "series_obj",
            "sueno", "cuerpo", "energia", "actividad_extra", "dolor", "carga_aguda_7d",
            "carga_cronica_28d", "acwr", "dias_desde_ultima", "sesiones_consecutivas", "sexo",
            "nivel", "objetivo", "patron_id", "mecanica", "incremento_kg", "sugerencia_formula"]
    split = GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=args.semilla)
    tr, te = next(split.split(df, groups=df["usuario_id"]))
    X = preparar(df, cols)
    y = df["cambio_kg"].to_numpy()
    modelo = HistGradientBoostingRegressor(max_iter=300, learning_rate=0.08,
                                           categorical_features="from_dtype", random_state=0)
    modelo.fit(X.iloc[tr], y[tr])
    pred = modelo.predict(X.iloc[te])
    inc = df["incremento_kg"].to_numpy()[te]
    pred_red = np.round(pred / inc) * inc
    mae_base = mean_absolute_error(y[te], np.zeros(len(te)))
    mae_form = mean_absolute_error(y[te], np.round(df["sugerencia_formula"].to_numpy()[te] / inc) * inc)
    mae_mod = mean_absolute_error(y[te], pred_red)
    print(f"Modelo de cargas · {len(df):,} filas · {df['usuario_id'].nunique()} usuarios "
          f"(prueba: usuarios no vistos)")
    print(f"  MAE línea base (repetir carga)     {mae_base:5.2f} kg")
    print(f"  MAE fórmula e1RM x %1RM            {mae_form:5.2f} kg")
    print(f"  MAE modelo (redondeado)            {mae_mod:5.2f} kg   "
          f"mejora vs base {1 - mae_mod / mae_base:+.0%}")

    # ------------------------------------------------ modelo de estado
    dd = dataset_dia(args.datos, usuarios)
    vol = [c for c in dd.columns if c.startswith("vol_")]
    cols_d = ["carga_aguda_7d", "carga_cronica_28d", "acwr", "dias_desde_ultima",
              "sesiones_consecutivas", "sueno", "cuerpo", "energia", "actividad_extra", "dolor",
              "sexo", "nivel", "objetivo", "dias_semana"] + vol
    tr, te = next(split.split(dd, groups=dd["usuario_id"]))
    Xd = preparar(dd, cols_d)
    yd = dd["clase_estado"].to_numpy()
    clf = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.08, class_weight="balanced",
                                         categorical_features="from_dtype", random_state=0)
    clf.fit(Xd.iloc[tr], yd[tr])
    f1_mod = f1_score(yd[te], clf.predict(Xd.iloc[te]), average="macro")
    mayoritaria = pd.Series(yd[tr]).mode()[0]
    f1_base = f1_score(yd[te], np.full(len(te), mayoritaria), average="macro")
    con_q = dd["sueno"].notna().to_numpy()[te]
    f1_q = f1_score(yd[te][con_q], clf.predict(Xd.iloc[te][con_q]), average="macro")
    print(f"\nModelo de estado · {len(dd):,} días")
    print("  clases:", pd.Series(yd).value_counts(normalize=True).round(3).to_dict())
    print(f"  F1 macro línea base (mayoritaria)  {f1_base:.2f}")
    print(f"  F1 macro modelo (todos los días)   {f1_mod:.2f}")
    print(f"  F1 macro modelo (días con cuestionario) {f1_q:.2f}")

    # ------------------------------------------------ fatiga
    reg = HistGradientBoostingRegressor(max_iter=300, learning_rate=0.08,
                                        categorical_features="from_dtype", random_state=0)
    yf = dd["fatiga"].to_numpy()
    reg.fit(Xd.iloc[tr], yf[tr])
    mae_f = mean_absolute_error(yf[te], reg.predict(Xd.iloc[te]))
    mae_fb = mean_absolute_error(yf[te], np.full(len(te), yf[tr].mean()))
    print(f"\nModelo de fatiga (0-100) · MAE modelo {mae_f:.1f} · MAE media {mae_fb:.1f}")


if __name__ == "__main__":
    main()
