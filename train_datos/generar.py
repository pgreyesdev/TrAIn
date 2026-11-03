"""Genera datos sintéticos de TrAIn.

Ejemplos:
    python generar.py --usuarios 1000                  # desarrollo (~1 min)
    python generar.py --usuarios 10000 --procesos 8    # dataset grande
    python generar.py --usuarios 50000 --meses 18 --salida /ruta/datos

Cada lote de usuarios se simula y se escribe por separado, así que la memoria
no crece con el número de usuarios y se puede generar tanto como quepa en disco.
"""
from __future__ import annotations

import argparse
import os
import random
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import date
from pathlib import Path

import pandas as pd

from simulador import catalogo
from simulador.derivados import calcular_estado_diario, calcular_rendimiento
from simulador.motor import nueva_salida, simular_usuario
from simulador.salida import Escritor, a_dataframes


def procesar_lote(n_lote: int, uid_desde: int, uid_hasta: int, n_dias: int, semilla: int,
                  base: str, formato: str, fin_datos: int) -> dict:
    rng = random.Random(semilla * 1_000_003 + n_lote)
    ejercicios = catalogo.cargar()
    cat = catalogo.tablas_capa1()
    fecha_min = date(2023, 1, 1).toordinal()
    fecha_max = fin_datos - n_dias
    out = nueva_salida()
    for uid in range(uid_desde, uid_hasta):
        simular_usuario(uid, rng, ejercicios, fecha_min, fecha_max, n_dias, out)
    dfs = a_dataframes(out)

    dfs["rendimiento_ejercicio"] = calcular_rendimiento(
        dfs["serie"], dfs["sesion"], dfs["medida_corporal"], cat["ejercicio"])
    usuarios = dfs["usuario"].set_index("id")
    desde = usuarios["fecha_alta"]
    hasta = desde + pd.to_timedelta(n_dias - 1, unit="D")
    dfs["estado_diario"] = calcular_estado_diario(
        dfs["sesion"], dfs["serie"], cat["ejercicio_musculo"], cat["musculo"], desde, hasta)

    escritor = Escritor(Path(base), formato)
    for tabla, df in dfs.items():
        escritor.lote(tabla, df, n_lote)
    return {t: len(df) for t, df in dfs.items()}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--usuarios", type=int, default=1000)
    ap.add_argument("--meses", type=float, default=12, help="historial por usuario")
    ap.add_argument("--semilla", type=int, default=42)
    ap.add_argument("--procesos", type=int, default=os.cpu_count() or 1)
    ap.add_argument("--lote", type=int, default=200, help="usuarios por fichero")
    ap.add_argument("--salida", default="datos")
    ap.add_argument("--formato", choices=["auto", "parquet", "csv"], default="auto")
    ap.add_argument("--fin", default="2026-10-01", help="última fecha posible de los datos")
    args = ap.parse_args()

    base = Path(args.salida)
    if any(base.glob("*/*/part-*")):
        raise SystemExit(f"{base} ya contiene datos: bórralo o usa otra --salida.")
    n_dias = int(round(args.meses * 30.44))
    fin = date.fromisoformat(args.fin).toordinal()

    escritor = Escritor(base, args.formato)
    for tabla, df in catalogo.tablas_capa1().items():
        escritor.catalogo(tabla, df)
    print(f"Formato: {escritor.formato} · {args.usuarios} usuarios · {n_dias} días · "
          f"{args.procesos} procesos")

    lotes = [(i, ini, min(ini + args.lote, args.usuarios + 1))
             for i, ini in enumerate(range(1, args.usuarios + 1, args.lote))]
    totales: dict[str, int] = {}
    t0 = time.time()
    with ProcessPoolExecutor(max_workers=args.procesos) as pool:
        futuros = [pool.submit(procesar_lote, i, a, b, n_dias, args.semilla, str(base),
                               escritor.formato, fin) for i, a, b in lotes]
        for k, fut in enumerate(as_completed(futuros), start=1):
            for t, n in fut.result().items():
                totales[t] = totales.get(t, 0) + n
            print(f"  lote {k}/{len(lotes)} · {time.time() - t0:.0f} s", flush=True)

    print(f"\nTerminado en {time.time() - t0:.0f} s. Filas por tabla:")
    for t, n in totales.items():
        print(f"  {t:<24} {n:>14,}".replace(",", "."))


if __name__ == "__main__":
    main()
