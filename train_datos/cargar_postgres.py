"""Carga los ficheros generados (capas 1-3) en PostgreSQL.

La capa 4 (simulación + etiquetas) NO se carga: se queda en Parquet para el
entrenamiento del Motor de IA.

    python cargar_postgres.py --dsn postgresql://usuario:clave@localhost:5432/train --crear-esquema
    python cargar_postgres.py --dsn ... --lotes 5      # solo los 5 primeros lotes (~1.000 usuarios)

Sin --crear-esquema, no carga nada si las tablas ya tienen datos (los ids chocarían):
hay que cargar todos los datos sintéticos de una vez, antes de que la app inserte.

Usa psycopg (COPY, lo más rápido). Si psycopg no está instalado, usa el
cliente `psql` con \\copy.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import subprocess
import time
from pathlib import Path

import pandas as pd

from simulador.salida import COLUMNAS_FECHA, _leer_fichero, ficheros

RAIZ = Path(__file__).resolve().parent
ORDEN = ["grupo_muscular", "musculo", "patron_movimiento", "ejercicio", "ejercicio_musculo",
         "usuario", "medida_corporal", "programa", "programa_ejercicio", "sesion", "serie",
         "rendimiento_ejercicio", "estado_diario"]
CATALOGO = ORDEN[:5]
COLUMNAS_BD = {
    "estado_diario": ["usuario_id", "fecha", "carga_sesion", "carga_aguda_7d",
                      "carga_cronica_28d", "acwr", "volumen_por_musculo", "dias_desde_ultima",
                      "sesiones_consecutivas"],
}


ENTEROS = {"smallint", "integer", "bigint"}


def preparar(tabla: str, df: pd.DataFrame, tipos_bd: dict[str, str]) -> pd.DataFrame:
    if tabla == "estado_diario":
        vol = [c for c in df.columns if c.startswith("vol_")]
        valores = df[vol].round(2).to_numpy()
        nombres = [c[4:] for c in vol]
        df = df.copy()
        df["volumen_por_musculo"] = [
            json.dumps({n: float(v) for n, v in zip(nombres, fila) if v > 0}) for fila in valores]
        df = df[COLUMNAS_BD["estado_diario"]]
    df = df[[c for c in df.columns if c in tipos_bd]].copy()
    for c in df.columns:
        if c in COLUMNAS_FECHA and pd.api.types.is_datetime64_any_dtype(df[c]):
            df[c] = df[c].dt.strftime("%Y-%m-%d")
        elif tipos_bd[c] in ENTEROS and pd.api.types.is_float_dtype(df[c]):
            df[c] = df[c].round().astype("Int64")
    return df


def a_csv(df: pd.DataFrame) -> str:
    buf = io.StringIO()
    df.to_csv(buf, index=False, header=False, na_rep="")
    return buf.getvalue()


class Destino:
    def __init__(self, dsn: str, forzar_psql: bool):
        self.dsn = dsn
        self.conn = None
        if not forzar_psql:
            try:
                import psycopg
                self.conn = psycopg.connect(dsn)
            except ImportError:
                print("psycopg no está instalado: uso psql.")

    def consultar(self, sql: str) -> list:
        if self.conn:
            return self.conn.execute(sql).fetchall()
        salida = subprocess.run(["psql", self.dsn, "-Atq", "-F", "|", "-c", sql],
                                check=True, capture_output=True, text=True).stdout
        return [linea.split("|") for linea in salida.splitlines() if linea]

    def tipos(self, tabla: str) -> dict[str, str]:
        return {c: t for c, t in self.consultar(
            "SELECT column_name, data_type FROM information_schema.columns "
            f"WHERE table_schema = 'public' AND table_name = '{tabla}'")}

    def existentes(self, tablas: list[str]) -> set[str]:
        nombres = ", ".join(f"'{t}'" for t in tablas)
        return {f[0] for f in self.consultar(
            "SELECT table_name FROM information_schema.tables "
            f"WHERE table_schema = 'public' AND table_name IN ({nombres})")}

    def con_filas(self, tablas: list[str]) -> list[str]:
        """Tablas que ya tienen alguna fila."""
        partes = [f"SELECT '{t}' WHERE EXISTS (SELECT 1 FROM {t})" for t in tablas]
        return [f[0] for f in self.consultar(" UNION ALL ".join(partes))]

    def ejecutar_fichero(self, ruta: Path):
        sql = ruta.read_text(encoding="utf-8")
        if self.conn:
            self.conn.execute(sql)
            self.conn.commit()
        else:
            subprocess.run(["psql", self.dsn, "-q", "-v", "ON_ERROR_STOP=1", "-f", str(ruta)],
                           check=True)

    def ejecutar(self, sql: str):
        if self.conn:
            self.conn.execute(sql)
            self.conn.commit()
        else:
            subprocess.run(["psql", self.dsn, "-q", "-v", "ON_ERROR_STOP=1", "-c", sql], check=True)

    def copiar(self, tabla: str, columnas: list[str], datos_csv: str):
        cols = ", ".join(columnas)
        if self.conn:
            with self.conn.cursor() as cur:
                with cur.copy(f"COPY {tabla} ({cols}) FROM STDIN WITH (FORMAT csv)") as cp:
                    cp.write(datos_csv)
            self.conn.commit()
        else:
            subprocess.run(["psql", self.dsn, "-q", "-v", "ON_ERROR_STOP=1", "-c",
                            f"\\copy {tabla} ({cols}) FROM pstdin WITH (FORMAT csv)"],
                           input=datos_csv, text=True, check=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--datos", default="datos")
    ap.add_argument("--dsn", default=os.environ.get("DATABASE_URL"),
                    help="cadena de conexión (o variable DATABASE_URL)")
    ap.add_argument("--crear-esquema", action="store_true",
                    help="borra las tablas de TrAIn si existen y crea el esquema")
    ap.add_argument("--lotes", type=int, default=None, help="cargar solo los N primeros lotes")
    ap.add_argument("--psql", action="store_true", help="usar psql aunque haya psycopg")
    args = ap.parse_args()
    if not args.dsn:
        raise SystemExit("Indica --dsn o la variable DATABASE_URL.")

    db = Destino(args.dsn, args.psql)
    if args.crear_esquema:
        db.ejecutar("SET client_min_messages TO warning; DROP TABLE IF EXISTS "
                    + ", ".join(reversed(ORDEN)) + ", recomendacion CASCADE")
        db.ejecutar_fichero(RAIZ / "sql" / "schema_postgres.sql")
        print("Esquema creado.")
    elif faltan := sorted(set(ORDEN) - db.existentes(ORDEN), key=ORDEN.index):
        raise SystemExit(f"No existe el esquema de TrAIn (faltan: {', '.join(faltan)}): "
                         "usa --crear-esquema.")
    elif llenas := db.con_filas(ORDEN):
        # Los ids sintéticos (sesión = usuario × 10.000 + n) chocarían con los ya cargados
        # o con los que haya creado la app tras reajustar las secuencias.
        raise SystemExit(
            f"La BD ya tiene datos ({', '.join(llenas)}): no se ha cargado nada.\n"
            "Cargar encima provocaría colisiones de ids con los datos ya cargados o creados "
            "por la app.\nVuelve a crear las tablas con --crear-esquema (BORRA todos los datos) "
            "y carga todos los datos sintéticos antes de que la app inserte.")

    t0 = time.time()
    for tabla in ORDEN:
        partes = ficheros(args.datos, tabla)
        if tabla not in CATALOGO and args.lotes is not None:
            partes = partes[: args.lotes]
        n = 0
        tipos_bd = db.tipos(tabla)
        for p in partes:
            df = preparar(tabla, _leer_fichero(p, tabla), tipos_bd)
            db.copiar(tabla, list(df.columns), a_csv(df))
            n += len(df)
        print(f"  {tabla:<24} {n:>12,} filas · {time.time() - t0:.0f} s".replace(",", "."))

    db.ejecutar_fichero(RAIZ / "sql" / "reajustar_secuencias.sql")
    db.ejecutar("ANALYZE " + ", ".join(ORDEN))
    print("Carga terminada.")


if __name__ == "__main__":
    main()
