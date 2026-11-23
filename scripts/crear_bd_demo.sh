#!/usr/bin/env bash
# Crea la BD de demo de TrAIn: PostgreSQL 16 (Docker) con los 200 primeros usuarios sintéticos.
#
# Uso (desde cualquier carpeta; en Windows, con Git Bash o WSL):
#   bash scripts/crear_bd_demo.sh                 # levanta Docker, genera 200 usuarios y los carga
#   bash scripts/crear_bd_demo.sh --datos DIR     # carga el primer lote de un dataset ya generado
#   bash scripts/crear_bd_demo.sh --sin-docker --dsn postgresql://usuario:clave@host:5432/bd
#
# ATENCIÓN: la carga usa --crear-esquema, que BORRA las tablas de TrAIn de la BD destino
# (pide confirmación salvo con --si). Todos los datos sintéticos se cargan aquí, antes de que
# la app inserte: después, cargar_postgres.py se niega a cargar más encima.
set -euo pipefail

RAIZ="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATOS_DIR="$RAIZ/train_datos"
PY="${PYTHON:-python3}"

ayuda() {
  cat <<'FIN'
Uso: bash scripts/crear_bd_demo.sh [opciones]

Crea la BD de demo de TrAIn: un solo lote de usuarios sintéticos (200; unos 0,17 GB).

Opciones:
  --dsn DSN      BD destino (por defecto $DATABASE_URL o, si no existe, la del
                 docker-compose.yml: postgresql://train:train@localhost:5432/train,
                 con los TRAIN_DB_* del .env de la raíz si los hay)
  --datos DIR    dataset ya generado: se carga solo su primer lote (usuarios 1-200 si se
                 generó con el --lote por defecto, 200). Sin esta opción se generan 200
                 usuarios en train_datos/datos_demo (se reutiliza si ya existe)
  --sin-docker   no levantar el contenedor (PostgreSQL ya en marcha en el DSN)
  --si           no pedir confirmación antes de BORRAR las tablas
  --ayuda        muestra esta ayuda

Variables: PYTHON (intérprete; por defecto python3).
FIN
}

error() { echo "ERROR: $*" >&2; exit 1; }

# Valor de una variable del .env de la raíz (sin ejecutarlo); vacío si no está. Como docker
# compose: entre comillas se toma tal cual; sin comillas se quita un comentario final " #...".
valor_env() {
  local valor
  [[ -f "$RAIZ/.env" ]] || return 0
  valor="$(grep -E "^[[:space:]]*$1[[:space:]]*=" "$RAIZ/.env" | tail -n 1)" || return 0
  valor="${valor%$'\r'}"
  valor="${valor#*=}"
  valor="${valor#"${valor%%[![:space:]]*}"}"
  if [[ $valor =~ ^\"([^\"]*)\" || $valor =~ ^\'([^\']*)\' ]]; then
    printf '%s' "${BASH_REMATCH[1]}"
  else
    valor="${valor%%[[:space:]]#*}"
    printf '%s' "${valor%"${valor##*[![:space:]]}"}"
  fi
}

# Codifica un texto para usarlo dentro de una URL (usuario, contraseña o BD con @ : / %).
url() { "$PY" -c 'import sys, urllib.parse; print(urllib.parse.quote(sys.argv[1], safe=""))' "$1"; }

DSN="${DATABASE_URL:-}"
DATOS=""
CON_DOCKER=1
SI=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --dsn) [[ $# -ge 2 ]] || error "--dsn necesita un valor"; DSN="$2"; shift 2 ;;
    --datos) [[ $# -ge 2 ]] || error "--datos necesita una carpeta"; DATOS="$2"; shift 2 ;;
    --sin-docker) CON_DOCKER=0; shift ;;
    --si) SI=1; shift ;;
    --ayuda|-h|--help) ayuda; exit 0 ;;
    *) error "opción desconocida: $1 (usa --ayuda)" ;;
  esac
done
# --- 1. Requisitos ------------------------------------------------------------
command -v "$PY" >/dev/null || error "no encuentro Python ('$PY'). Instálalo o indica PYTHON=/ruta/python."
"$PY" -c "import pandas" 2>/dev/null \
  || error "a '$PY' le falta pandas: pip install -r train_datos/requirements.txt"
if command -v psql >/dev/null; then
  CLIENTE=psql
elif "$PY" -c "import psycopg" 2>/dev/null; then
  CLIENTE=psycopg
else
  error "hace falta el cliente psql o psycopg: pip install 'psycopg[binary]'"
fi
if [[ -z "$DSN" ]]; then
  u="$(valor_env TRAIN_DB_USER)"; c="$(valor_env TRAIN_DB_PASSWORD)"
  b="$(valor_env TRAIN_DB_NAME)"; p="$(valor_env TRAIN_DB_PORT)"
  DSN="postgresql://$(url "${u:-train}"):$(url "${c:-train}")@localhost:${p:-5432}/$(url "${b:-train}")"
fi
if [[ $CON_DOCKER -eq 1 ]]; then
  command -v docker >/dev/null && docker compose version >/dev/null 2>&1 \
    || error "no encuentro 'docker compose' (Docker con el plugin compose). Arranca Docker o usa --sin-docker."
  [[ -f "$RAIZ/docker-compose.yml" ]] || error "no existe $RAIZ/docker-compose.yml"
fi
if [[ -n "$DATOS" ]]; then
  [[ -d "$DATOS" ]] || error "no existe la carpeta de datos $DATOS"
  DATOS="$(cd "$DATOS" && pwd)"
  compgen -G "$DATOS/registro/usuario/part-*" >/dev/null \
    || error "$DATOS no parece un dataset de generar.py (falta registro/usuario/part-*)"
fi

# Ejecuta una consulta y escribe una fila por línea (columnas separadas por '|').
consultar() {
  if [[ $CLIENTE == psql ]]; then
    psql "$DSN" -Atq -F '|' -v ON_ERROR_STOP=1 -c "$1"
  else
    "$PY" -c 'import sys, psycopg
with psycopg.connect(sys.argv[1]) as c:
    for f in c.execute(sys.argv[2]).fetchall():
        print("|".join(str(v) for v in f))' "$DSN" "$1"
  fi
}

echo "BD destino: $DSN"
if [[ $SI -eq 0 ]]; then
  [[ -t 0 ]] || error "no hay terminal para confirmar: repite con --si si quieres borrar las tablas."
  read -r -p "Se BORRARÁN las tablas de TrAIn de esa BD y se cargará la demo. ¿Seguir? [s/N] " resp
  case "$resp" in
    s|S|si|Si|SI|sI|sí|Sí|SÍ|sÍ) ;;
    *) echo "Cancelado: no se ha tocado nada."; exit 1 ;;
  esac
fi
inicio=$SECONDS

# --- 2. PostgreSQL ------------------------------------------------------------
if [[ $CON_DOCKER -eq 1 ]]; then
  echo "Levantando PostgreSQL (docker compose up -d --wait db)..."
  (cd "$RAIZ" && docker compose up -d --wait db) \
    || error "no se pudo levantar el contenedor db (¿está Docker en marcha? ¿puerto ocupado?: TRAIN_DB_PORT en .env)"
fi
consultar "SELECT 1" >/dev/null \
  || error "no puedo conectar con $DSN (¿está PostgreSQL en marcha? ¿usuario, clave y BD correctos?)"

# --- 3. Datos -----------------------------------------------------------------
if [[ -z "$DATOS" ]]; then
  DATOS="$DATOS_DIR/datos_demo"
  if compgen -G "$DATOS/registro/usuario/part-*" >/dev/null; then
    echo "Reutilizo los datos de $DATOS (bórralo para regenerarlos)."
  else
    echo "Generando 200 usuarios en $DATOS..."
    rm -rf "$DATOS" "${DATOS}_tmp"
    "$PY" "$DATOS_DIR/generar.py" --usuarios 200 --lote 200 --salida "${DATOS}_tmp"
    mv "${DATOS}_tmp" "$DATOS"
  fi
fi

# --- 4. Carga (un solo lote) ----------------------------------------------------
echo "Cargando el primer lote de $DATOS..."
"$PY" "$DATOS_DIR/cargar_postgres.py" --datos "$DATOS" --dsn "$DSN" --crear-esquema --lotes 1

# --- 5. Resumen -----------------------------------------------------------------
resumen="$(consultar "SELECT (SELECT count(*) FROM usuario), (SELECT count(*) FROM sesion),
  (SELECT count(*) FROM serie), pg_size_pretty(pg_database_size(current_database()))")"
IFS='|' read -r n_usuarios n_sesiones n_series tamano <<<"$resumen"
echo
echo "BD de demo lista en $((SECONDS - inicio)) s."
echo "  usuarios: $n_usuarios · sesiones: $n_sesiones · series: $n_series · tamaño de la BD: $tamano"
echo "  DATABASE_URL=$DSN"
if [[ "$n_usuarios" != 200 ]]; then
  echo "AVISO: se han cargado $n_usuarios usuarios, no 200. --datos carga solo el PRIMER lote del"
  echo "  dataset: son los usuarios 1-200 únicamente si se generó con el --lote por defecto (200)."
fi
echo "No cargues más datos sintéticos encima: si hace falta, vuelve a ejecutar este script."
