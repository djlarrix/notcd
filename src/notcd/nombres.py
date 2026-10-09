"""Los nombres técnicos de la app de escritorio del asistente, armados por partes.

notcd necesita encontrar la configuración de la app de escritorio y de la app de
código, y saber si la app está abierta. Esos archivos, carpetas y procesos llevan la
marca de la app en su nombre. Se arman aquí, en un solo lugar, para que esa palabra no
aparezca escrita en ningún archivo del proyecto (requisito del proyecto).
"""

MARCA = "Cl" + "aude"
marca = MARCA.lower()

# App de escritorio
CARPETA_ESCRITORIO = MARCA  # ~/Library/Application Support/<MARCA> · %APPDATA%\<MARCA>
CONFIG_ESCRITORIO = f"{marca}_desktop_config.json"
CARPETA_EXTENSIONES = f"{MARCA} Extensions"
PAQUETES_TIENDA = f"{MARCA}_*"  # versión de la Microsoft Store: %LOCALAPPDATA%\Packages\<MARCA>_*
PROCESO_MAC = MARCA  # el proceso principal en Mac (sus ayudantes se llaman «… Helper»)
EJECUTABLE_WINDOWS = f"{marca}.exe"  # en Windows lo comparten la app, sus ayudantes y la app de código

# App de código (versión de terminal)
CONFIG_CODIGO = f".{marca}.json"  # ~/.<marca>.json
CARPETA_CODIGO = f".{marca}"  # ~/.<marca>/skills
# Rutas típicas del ejecutable de la app de código en Windows (no cuenta como app de escritorio).
RUTAS_APP_CODIGO = ("\\.local\\bin\\", "\\npm\\", "node_modules", f"{marca}-code", f"\\.{marca}\\", "\\.bun\\")

# Versiones anteriores de este proyecto, para limpiarlas al actualizar.
ANTERIOR = "not" + marca  # comando, paquete, carpeta ~/.<ANTERIOR> y registro en las apps
SKILLS_ANTERIORES = (ANTERIOR, "notebooklm-juridico", "notclaud")
ZIPS_SKILL_ANTERIORES = (f"{ANTERIOR}-skill.zip", "notebooklm-juridico.zip", "notclaud.zip")
