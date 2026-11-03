#!/usr/bin/env bash
# Crea el tablero de GitHub Projects de TrAIn y añade los issues T01–T27 con sus campos.
#
# Requisitos: GitHub CLI (gh) 2.40 o superior, sesión iniciada con permiso de proyectos:
#   gh auth login
#   gh auth refresh -s project
# Uso (desde la raíz del repositorio; en Windows, con Git Bash):
#   bash scripts/crear_tablero.sh
#
# Lee los datos de scripts/tareas.tsv. Si el proyecto ya existe, pasa su número:
#   PROJECT_NUMBER=3 bash scripts/crear_tablero.sh
set -euo pipefail

OWNER="${OWNER:-pgreyesdev}"
REPO="${REPO:-pgreyesdev/TrAIn}"
TITLE="${TITLE:-TrAIn}"
TSV="$(dirname "$0")/tareas.tsv"

if [[ -z "${PROJECT_NUMBER:-}" ]]; then
  echo "Creando el proyecto \"$TITLE\"..."
  PROJECT_NUMBER=$(gh project create --owner "$OWNER" --title "$TITLE" --format json --jq '.number')
fi
PROJECT_ID=$(gh project view "$PROJECT_NUMBER" --owner "$OWNER" --format json --jq '.id')
echo "Proyecto número $PROJECT_NUMBER ($PROJECT_ID)"

gh project link "$PROJECT_NUMBER" --owner "$OWNER" --repo "$REPO" >/dev/null 2>&1 || true

field_exists() {
  gh project field-list "$PROJECT_NUMBER" --owner "$OWNER" --limit 100 --format json \
    --jq ".fields[] | select(.name == \"$1\") | .id" | grep -q .
}

create_field() { # nombre tipo [opciones]
  if field_exists "$1"; then echo "El campo $1 ya existe"; return; fi
  if [[ -n "${3:-}" ]]; then
    gh project field-create "$PROJECT_NUMBER" --owner "$OWNER" --name "$1" --data-type "$2" \
      --single-select-options "$3" >/dev/null
  else
    gh project field-create "$PROJECT_NUMBER" --owner "$OWNER" --name "$1" --data-type "$2" >/dev/null
  fi
  echo "Campo $1 creado"
}

create_field "Responsable" SINGLE_SELECT "Pablo,Sergio,Adrián"
create_field "Fase" SINGLE_SELECT "Gestión,Datos,Motor de IA,Backend,App Android,Agente,Opcional,Integración,Cierre"
create_field "Hito" SINGLE_SELECT "H1,H2,H3,H4,H5,H6,H7"
create_field "Inicio" DATE
create_field "Fin" DATE
create_field "Estimación (h)" NUMBER

# Tabla "campo<TAB>opción<TAB>id" (opción vacía para el propio campo), leída una sola vez.
LOOKUP=$(gh project field-list "$PROJECT_NUMBER" --owner "$OWNER" --limit 100 --format json \
  --jq '.fields[] | (.name + "\t\t" + .id), (.name as $f | (.options // [])[] | $f + "\t" + .name + "\t" + .id)')
field_id() { printf '%s\n' "$LOOKUP" | awk -F'\t' -v f="$1" '$1 == f && $2 == "" { print $3 }'; }
option_id() { printf '%s\n' "$LOOKUP" | awk -F'\t' -v f="$1" -v o="$2" '$1 == f && $2 == o { print $3 }'; }

F_RESP=$(field_id "Responsable"); F_FASE=$(field_id "Fase"); F_HITO=$(field_id "Hito")
F_INI=$(field_id "Inicio"); F_FIN=$(field_id "Fin"); F_H=$(field_id "Estimación (h)")
F_STATUS=$(field_id "Status")
DONE_OPT=$(option_id "Status" "Done")

ISSUES=$(gh issue list -R "$REPO" --state all --limit 200 --json number,url,title \
  --jq '.[] | select(.title | test("^T[0-9]{2}:")) | (.title[0:3]) + "\t" + .url')

tail -n +2 "$TSV" | while IFS=$'\t' read -r id fase titulo resp personal medios inicio fin horas depende hito estado; do
  url=$(printf '%s\n' "$ISSUES" | awk -F'\t' -v id="$id" '$1 == id { print $2 }')
  if [[ -z "$url" ]]; then echo "Sin issue para $id, se omite"; continue; fi
  item=$(gh project item-add "$PROJECT_NUMBER" --owner "$OWNER" --url "$url" --format json --jq '.id')
  edit() { gh project item-edit --id "$item" --project-id "$PROJECT_ID" "$@" >/dev/null; }
  edit --field-id "$F_RESP" --single-select-option-id "$(option_id Responsable "$resp")"
  edit --field-id "$F_FASE" --single-select-option-id "$(option_id Fase "$fase")"
  edit --field-id "$F_HITO" --single-select-option-id "$(option_id Hito "$hito")"
  edit --field-id "$F_INI" --date "$inicio"
  edit --field-id "$F_FIN" --date "$fin"
  edit --field-id "$F_H" --number "$horas"
  if [[ "$estado" == "hecha" && -n "$DONE_OPT" ]]; then
    edit --field-id "$F_STATUS" --single-select-option-id "$DONE_OPT"
  fi
  echo "$id añadida"
done

cat <<MSG

Hecho. Termina en la web (https://github.com/users/$OWNER/projects/$PROJECT_NUMBER):
  1. Status: renombra las opciones a Pendiente, En curso, En revisión y Hecho (añade En revisión).
  2. Nueva vista Roadmap: fechas Inicio y Fin, agrupada por Fase, con los hitos marcados.
  3. Vista tablero agrupada por Status, para la reunión semanal.
  4. Workflows: activa "Item closed → Done" y "Auto-add to project" para el repositorio.
MSG
