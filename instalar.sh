#!/usr/bin/env bash
# notcd — instalador para macOS (y Linux). Un solo comando en la Terminal:
#
#   curl -fsSL https://raw.githubusercontent.com/djlarrix/notcd/main/instalar.sh | bash
#
# Hace todo: instala uv (el gestor de Python) si falta, descarga notcd, lo
# instala, abre el inicio de sesión de Google, lo registra en la app de escritorio y
# en la app de código del asistente e instala la skill. Para actualizar, se pega el
# mismo comando.
#
# Opciones, desde una copia local (bash instalar.sh …) o como variables de entorno:
#   --sin-login    / NOTCD_SIN_LOGIN=1    no abrir el inicio de sesión de Google
#   --sin-desktop  / NOTCD_SIN_DESKTOP=1  no registrar en la app de escritorio (sólo en la de código)

set -euo pipefail

# Todo va dentro de una función que se llama en la última línea: así, con
# `curl | bash`, nada se ejecuta hasta que el script llegó completo.
principal() {
  local REPO="djlarrix/notcd"
  local REF="${NOTCD_REF:-main}"
  local CASA="${NOTCD_HOME:-$HOME/.notcd}"
  local SIN_LOGIN="${NOTCD_SIN_LOGIN:-0}"
  local SIN_DESKTOP="${NOTCD_SIN_DESKTOP:-0}"
  # uv usa los certificados del sistema (redes de oficina que revisan las conexiones
  # seguras) y copia en vez de enlazar archivos.
  export UV_NATIVE_TLS=1 UV_LINK_MODE=copy
  for opcion in "$@"; do
    case "$opcion" in
      --sin-login) SIN_LOGIN=1 ;;
      --sin-desktop) SIN_DESKTOP=1 ;;
      *) echo "Opción desconocida: $opcion"; return 2 ;;
    esac
  done

  local BLANCO=$'\033[1;37m' AZUL=$'\033[0;36m' TENUE=$'\033[0;90m' ROJO=$'\033[0;31m' FIN=$'\033[0m'
  paso() { printf '\n%s[%s/5] %s%s\n' "$BLANCO" "$1" "$2" "$FIN"; }
  ok()   { printf '      %s%s%s\n' "$TENUE" "$1" "$FIN"; }
  malo() { printf '      %s%s%s\n' "$ROJO" "$1" "$FIN"; }

  printf '\n  %sNOTCD%s\n' "$BLANCO" "$FIN"
  printf '  %sNotebookLM para el estudio%s\n' "$AZUL" "$FIN"

  # ─────────────────────────────────────────────────────────────── 1. uv
  paso 1 'Comprobando uv (instala y aísla Python para notcd)'
  local UV
  UV="$(command -v uv || true)"
  for candidato in "$HOME/.local/bin/uv" "$HOME/.cargo/bin/uv"; do
    [ -z "$UV" ] && [ -x "$candidato" ] && UV="$candidato"
  done
  if [ -n "$UV" ]; then
    ok "Ya está: $("$UV" --version)"
  else
    ok 'No está. Instalándolo desde astral.sh (el sitio oficial de uv)...'
    curl -LsSf https://astral.sh/uv/install.sh | sh >/dev/null
    UV="$HOME/.local/bin/uv"
    if [ ! -x "$UV" ]; then
      malo 'No se pudo instalar uv. Revisa la conexión a internet y vuelve a intentar.'
      return 1
    fi
    ok "Instalado: $("$UV" --version)"
  fi

  # ───────────────────────────────────────────────────────── 2. notcd
  paso 2 'Descargando e instalando notcd'
  mkdir -p "$CASA"
  # Cada descarga va a una carpeta nueva (igual que en Windows) y las anteriores se borran.
  local DESCARGAS="$CASA/fuente"
  local DESTINO
  DESTINO="$DESCARGAS/$(date +%Y%m%d-%H%M%S)"
  mkdir -p "$DESTINO"
  local AQUI="" FUENTE
  if [ -n "${BASH_SOURCE[0]:-}" ] && [ -f "${BASH_SOURCE[0]}" ]; then
    AQUI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  fi
  if [ -n "$AQUI" ] && [ -f "$AQUI/pyproject.toml" ] && [ -d "$AQUI/src/notcd" ]; then
    # Ejecutado desde una copia del proyecto: se instala esa copia.
    FUENTE="$DESTINO/notcd-local"
    mkdir -p "$FUENTE"
    (cd "$AQUI" && tar --exclude .git --exclude .venv --exclude __pycache__ --exclude dist --exclude build -cf - .) \
      | (cd "$FUENTE" && tar -xf -)
    ok "Usando la copia local ($AQUI)"
  else
    # Con `curl | bash`: se descarga la última versión. Sin git (en Mac, llamar a git
    # sin las herramientas de Xcode abre un diálogo de instalación).
    curl -fsSL "https://github.com/$REPO/archive/$REF.zip" -o "$DESTINO/notcd.zip"
    if command -v unzip >/dev/null 2>&1; then
      unzip -q "$DESTINO/notcd.zip" -d "$DESTINO"
    else
      python3 -m zipfile -e "$DESTINO/notcd.zip" "$DESTINO"
    fi
    rm -f "$DESTINO/notcd.zip"
    FUENTE="$(ls -d "$DESTINO"/notcd-* | head -n 1)"
    ok "Descargada la última versión de github.com/$REPO"
  fi
  for vieja in "$DESCARGAS"/* "$DESCARGAS"/.[!.]*; do
    if [ -e "$vieja" ] && [ "$vieja" != "$DESTINO" ]; then
      rm -rf "$vieja"
    fi
  done
  # La versión anterior de este proyecto tenía otro nombre: se desinstala su comando
  # (la sesión de Google y lo demás los traslada notcd al configurarse).
  local ANTERIOR="not""cl""aude"
  if "$UV" tool list 2>/dev/null | grep -q "^$ANTERIOR "; then
    "$UV" tool uninstall "$ANTERIOR" >/dev/null 2>&1 && ok 'Desinstalada la versión anterior'
  fi
  ok 'Instalando componentes (la primera vez tarda uno o dos minutos)...'
  "$UV" tool install --quiet --force --upgrade --reinstall-package notcd --python 3.12 "$FUENTE"
  local NOTCD
  NOTCD="$("$UV" tool dir --bin)/notcd"
  if [ ! -x "$NOTCD" ]; then
    malo "No quedó instalado el comando notcd (se esperaba en $NOTCD)."
    return 1
  fi
  ok "Instalado: $("$NOTCD" --version)"

  # ─────────────────────────────────────────────────────────── 3. Google
  paso 3 'Conectando con tu cuenta de Google (NotebookLM)'
  if [ "$SIN_LOGIN" = 1 ]; then
    ok 'Omitido. Para conectar después:  notcd login'
  elif "$NOTCD" estado >/dev/null 2>&1; then
    "$NOTCD" estado || true
  else
    "$NOTCD" login || {
      malo 'El inicio de sesión no terminó. Puedes reintentarlo después con:'
      malo "  $NOTCD login"
      malo 'o pidiéndole al asistente: «Conéctate a NotebookLM».'
    }
  fi

  # ──────────────────────────────────────────────────────────── 4. Apps
  paso 4 'Registrando notcd en la app de escritorio y en la app de código'
  if [ "$SIN_DESKTOP" = 1 ]; then
    "$NOTCD" configurar --sin-desktop || malo 'Hubo problemas al registrar; revisa los mensajes de arriba.'
  else
    "$NOTCD" configurar --esperar || malo 'Hubo problemas al registrar; revisa los mensajes de arriba.'
  fi

  # ─────────────────────────────────────────────────────────────── 5. Listo
  paso 5 'Listo'
  echo
  printf '      %sAbre la app de escritorio y pregúntale:%s\n' "$BLANCO" "$FIN"
  printf '      %s«¿Qué cuadernos tengo en NotebookLM?»%s\n' "$TENUE" "$FIN"
  echo
  printf '      %sPara actualizar más adelante, vuelve a pegar el mismo comando.%s\n' "$TENUE" "$FIN"
  printf '      %sSi algo falla, en una terminal nueva:  notcd diagnostico%s\n' "$TENUE" "$FIN"
  echo
}

principal "$@" </dev/null
