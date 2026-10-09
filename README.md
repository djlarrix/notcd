# notcd

[![pruebas](https://github.com/djlarrix/notcd/actions/workflows/pruebas.yml/badge.svg)](https://github.com/djlarrix/notcd/actions/workflows/pruebas.yml)

**NotebookLM y el asistente de IA trabajando juntos.** notcd conecta la app de escritorio del asistente con NotebookLM —ahora llamado *Gemini Notebook*— de tu cuenta de Google, para que cada IA haga lo que mejor sabe hacer:

| | NotebookLM (Gemini) | El asistente |
|---|---|---|
| **Su oficio** | Leer | Pensar y escribir |
| **En qué es mejor** | Retener cientos de páginas (un expediente completo, decenas de contratos) y responder anclado a ellas, con el pasaje textual que respalda cada frase | Decidir qué preguntar, desconfiar de la respuesta, razonar jurídicamente y redactar |
| **Además** | Resúmenes en audio, mapas mentales, tablas comparativas, presentaciones | Estrategia, escritos, minutas, correos |

En la práctica: le pides *«sube la carpeta de la causa Pérez a NotebookLM y dime qué plazos están corriendo»*. El asistente crea el cuaderno, sube los documentos, le hace a NotebookLM preguntas acotadas, verifica en el texto original lo que importa y te entrega su análisis con cada hecho citado.

## Instalar (un comando)

**Mac**: abre la Terminal (`Command + Espacio` → «Terminal») y pega:

```bash
curl -fsSL https://raw.githubusercontent.com/djlarrix/notcd/main/instalar.sh | bash
```

**Windows**: abre PowerShell (menú Inicio → «PowerShell») y pega:

```powershell
irm https://raw.githubusercontent.com/djlarrix/notcd/main/instalar.ps1 | iex
```

El instalador hace todo solo. Sólo te pide **entrar con tu cuenta de Google** en la ventana que se abre y **cerrar la app de escritorio** si está abierta. Después, pregúntale al asistente: *«¿Qué cuadernos tengo en NotebookLM?»*. Para actualizar, se pega el mismo comando.

**La skill (opcional, recomendada):** descarga [notcd.zip](https://github.com/djlarrix/notcd/releases/latest/download/notcd.zip) (el instalador también la deja en *Documentos/notcd*) y súbela en la app: *Configuración → Capacidades → Skills → Subir skill*.

**→ Paso a paso, problemas frecuentes y la alternativa de doble clic: [INSTALACION.md](INSTALACION.md).**

---

## Qué puede hacer

Se le pide en lenguaje natural; el asistente elige la herramienta.

| Pídele… | Qué pasa por debajo |
|---|---|
| «¿Qué cuadernos tengo en NotebookLM?» | `listar_cuadernos` |
| «Crea un cuaderno para el arbitraje Constructora X y sube la carpeta ~/Documents/Arbitraje X» | `crear_cuaderno` (nace como lector jurídico) + `agregar_fuentes` (no duplica lo que ya está) |
| «Según el expediente, ¿cuándo se notificó la demanda y quién la contestó?» | `preguntar`: respuesta de NotebookLM con cada cita resuelta a su pasaje textual |
| «Verifica en el contrato el texto exacto de la cláusula de terminación» | `buscar_pasajes` / `leer_fuente`: texto original, sin resumir |
| «Revisa que todas las citas de este escrito sean literales» | `verificar_citas`: comparación letra por letra contra los documentos, sin IA de por medio |
| «Hazme una tabla con partes, precio, plazo y multas de estos 20 contratos» | `generar(tabla_datos)` |
| «Prepárame un audio tipo debate entre las dos tesis para escucharlo en el auto» | `generar(resumen_audio, debate)` + `obtener_contenido` |
| «Un mapa mental de los hechos del caso» | `generar(mapa_mental)` |
| «Guarda tu minuta en el cuaderno» / «Compártelo con María como lectora» | `guardar_nota` / `compartir_cuaderno` |
| «Busca en la web material sobre X» | `buscar_en_web`: el asistente elige qué vale la pena agregar |

Además: cuatro **plantillas** en el botón + de la app (analizar expediente, revisar contratos, preparar audiencia, verificar escrito), **guías de método** por tipo de trabajo (`guia_de_metodo`), operaciones largas que siguen **en segundo plano** (`ver_trabajo`) en vez de cortarse al minuto, y **aviso y aplicación de correcciones** cuando Google cambia algo (`estado_conexion`, `actualizar_conexion`).

Lo que NotebookLM genera (audios, presentaciones en PowerPoint, informes, tablas en CSV) queda en **Documentos/notcd/**, en una carpeta por cuaderno.

La **skill** le enseña al asistente el método: preguntar en serie y acotado, exigir cita textual para cada hecho, verificar en el original lo que decide el asunto, pasar toda cita entre comillas por `verificar_citas`, separar lo que dicen los documentos de su propio análisis, y no tratar a NotebookLM como fuente del derecho vigente (para eso están las herramientas de fuentes oficiales, como Responsa).

## Antes de usarlo con documentos de clientes

**Los documentos que agregas se suben a tu cuenta de Google.** Según la [ayuda oficial de Google](https://support.google.com/notebooklm/answer/17004255):

- **Cuentas de Google Workspace** (corporativas): lo que subes, preguntas y responde NotebookLM no lo revisan personas ni se usa para entrenar modelos, aunque des feedback.
- **Cuentas personales** (@gmail.com): no se usa para entrenar directamente los modelos *salvo que des feedback*. Si pulsas 👍/👎 o envías comentarios, Google puede revisar esa conversación completa, documentos incluidos. **Con una cuenta personal, no des feedback en NotebookLM.**

Sigue la política del estudio sobre qué información puede ir a servicios externos, y anonimiza cuando corresponda. El asistente está instruido para pedir confirmación antes de subir documentos que no le pediste subir expresamente.

## Limitaciones honestas

- **No es una integración oficial de Google.** Google no ofrece una API pública de NotebookLM para cuentas normales. notcd se apoya en [notebooklm-py](https://github.com/teng-lin/notebooklm-py) (código abierto, MIT, muy usado y mantenido a diario), que usa las mismas interfaces internas que la página web. Si Google cambia algo, puede dejar de funcionar hasta que salga una corrección: se trae con `notcd actualizar`.
- **NotebookLM tiene cuotas** por cuenta y plan (cuadernos, fuentes por cuaderno, generaciones por día). `estado_conexion` muestra los límites de tu plan.
- **La sesión de Google puede expirar.** notcd intenta renovarla solo; si no puede, el asistente te pedirá volver a iniciar sesión (se abre una ventana, entras y listo).
- **NotebookLM también se equivoca.** Puede atribuir a una fuente lo que dice otra o resumir de más. Por eso la regla de la skill: lo que decide el asunto se verifica en el texto original.

---

## Para quien mantiene notcd

### Estructura

```
SKILL.md, referencias/   la skill, en la raíz (el repositorio mismo sirve como skill)
src/notcd/
  server.py         las 20 herramientas MCP, 4 plantillas y las instrucciones para el asistente
  protocolo.py      el servidor MCP por stdio, en Python puro (sin nada compilado que Windows pueda bloquear)
  nombres.py        los nombres técnicos de la app (archivos, carpetas, procesos), armados por partes
  acceso.py         inicio de sesión en Mac y Linux (Playwright): abre el formulario de Google y espera
  navegador.py      inicio de sesión en Windows: el Chrome o el Edge instalados, por su puerto de depuración
  verificacion.py   verificación mecánica de citas textuales (funciones puras)
  trabajos.py       operaciones largas en segundo plano (límite de ~60 s de la app de escritorio)
  conexion.py       cliente de NotebookLM (uno por proceso) y traducción de errores
  actualizacion.py  aviso y aplicación de correcciones de notebooklm-py
  formato.py        cómo se presenta cada respuesta (funciones puras)
  cli.py            comando `notcd`: login, estado, configurar, actualizar, diagnostico, desinstalar
  registro.py       registro de actividad para soporte, sin contenido de clientes
  rutas.py          dónde vive cada cosa en Mac y Windows, y la migración desde la versión anterior
extension/          manifiesto e ícono de la extensión de doble clic (.mcpb)
servidor_mcpb.py    punto de entrada de la extensión
scripts/            empaquetar.py (arma dist/), comprobaciones de instalación, icono.py
instalar.sh / instalar.ps1 / INSTALAR-Windows.bat   el comando de instalación
tests/              pruebas con un NotebookLM falso (no usan red ni cuenta)
```

En el computador del usuario, todo vive en `~/.notcd/`: la sesión de Google (`google/`), el registro (`notcd.log`) y una copia de la fuente (`fuente/`).

**Una regla del proyecto:** la marca de la app del asistente no aparece escrita en ningún archivo. Los nombres técnicos que la necesitan (su archivo de configuración, su carpeta, su proceso) se arman por partes en `src/notcd/nombres.py`, y una prueba revisa el repositorio completo.

### El inicio de sesión

notebooklm-py 0.8.4 cree que hay sesión cuando ve la portada pública que Google muestra sin sesión desde el cambio a «Gemini Notebook», y cerraba la ventana a los segundos ([teng-lin/notebooklm-py#2467](https://github.com/teng-lin/notebooklm-py/issues/2467)). `acceso.py` abre primero el formulario de Google en el mismo perfil de navegador y espera a que la persona entre; después la librería encuentra la sesión real y la guarda bien.

### Windows y el Control inteligente de aplicaciones

Windows 11 puede bloquear todo archivo ejecutable sin firma digital (os error 4551), y eso incluye las bibliotecas compiladas de Python (`.pyd`). Por eso, en Windows, notcd no instala nada compilado:

- corre sobre el **Python oficial de python.org**, firmado, en un entorno propio (`~/.notcd/entorno`);
- el servidor MCP es **propio y en Python puro** (`protocolo.py`): la biblioteca oficial depende de pydantic-core y cryptography, compiladas. Las pruebas lo comprueban con el cliente oficial;
- el inicio de sesión usa el **Chrome o el Edge instalados** (`navegador.py`): Playwright trae greenlet (compilado) y un Chromium sin firma. notcd abre el navegador con un perfil propio y lee la sesión por el puerto de depuración local, y sólo la guarda si NotebookLM la acepta.

Una prueba revisa que importar notcd no cargue nada compilado, y la instalación de prueba en Windows falla si aparece algún `.pyd` o `.dll` en el entorno.

### Desarrollo

```bash
uv sync --extra dev && uv run pytest
```

Cada push a `main` corre las pruebas en macOS, Windows y Linux, prueba el comando de instalación en Mac y en Windows (PowerShell 5) y la extensión `.mcpb` en los tres sistemas.

### Publicar una versión

1. Cambia el código, sube `version` en `pyproject.toml` y `__version__` en `src/notcd/__init__.py`.
2. `uv lock`, `uv run pytest`, commit y push.
3. `uv run python scripts/empaquetar.py` → `dist/notcd-<versión>.mcpb` y `dist/notcd.zip`.
4. `gh release create v<versión> dist/notcd-<versión>.mcpb dist/notcd.zip`. Los enlaces `releases/latest/download/…` apuntan siempre a la última.

Quienes instalaron con el comando se actualizan pegándolo de nuevo, o con `notcd actualizar`. Si sólo hace falta la corrección de notebooklm-py por un cambio de Google, no hay que publicar nada.
