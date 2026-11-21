#!/usr/bin/env bash
# Huella de contenido de un conjunto de archivos/carpetas del repo: 12 caracteres hexadecimales.
# Es la ÚNICA implementación: la usan el workflow de GitHub (job `imagen`, etiqueta app-<huella>)
# y deploy/desplegar.sh, así que ambos siempre calculan lo mismo.
#
# Uso:  bash deploy/huella.sh <entrada...>      p. ej.  Dockerfile requirements.txt src
#
# Se basa en `git ls-tree -r HEAD`: da el hash de contenido de cada archivo versionado y su ruta,
# en orden estable. No necesita Docker; solo cambia si cambia el contenido de HEAD.
set -euo pipefail

[ $# -ge 1 ] || { echo "Uso: $0 <entrada...>  (archivos o carpetas del repo)" >&2; exit 2; }

# Siempre desde la raíz del repo, se llame desde donde se llame.
cd "$(dirname "${BASH_SOURCE[0]}")/.."

for entrada in "$@"; do
  [ -e "$entrada" ] || { echo "huella.sh: la entrada '$entrada' no existe en $(pwd)" >&2; exit 1; }
done

lista=$(git ls-tree -r HEAD -- "$@")
[ -n "$lista" ] || { echo "huella.sh: ninguna de las entradas está versionada en HEAD: $*" >&2; exit 1; }

printf '%s\n' "$lista" | sha256sum | cut -c1-12
