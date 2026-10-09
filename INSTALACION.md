# Manual de instalación

Guía para dejar notcd funcionando en el computador de un abogado del estudio. Está escrita para quien no programa: si algo pide conocimiento previo, es un error de esta guía y conviene avisarlo.

Toma unos **10 minutos**, casi todo esperando descargas.

En esta guía, **«la app»** es la app de escritorio del asistente de IA (la del chat).

---

## La versión corta: un comando

**Antes de empezar:** la app instalada y con la sesión iniciada, y a mano la cuenta de Google que se usará con NotebookLM (y el teléfono, por la verificación en dos pasos).

### En Mac

1. Abre la Terminal: `Command + Espacio` → escribe `Terminal` → Enter.
2. Copia esta línea, pégala en la Terminal y presiona Enter:

```bash
curl -fsSL https://raw.githubusercontent.com/djlarrix/notcd/main/instalar.sh | bash
```

### En Windows

1. Cierra la app por completo: en la barra de tareas, flechita **^** junto al reloj → clic derecho en el ícono de la app → **Salir** (cerrar la ventana no basta).
2. Abre PowerShell: menú Inicio → escribe `PowerShell` → Enter.
3. Copia esta línea, pégala en PowerShell (clic derecho pega) y presiona Enter:

```powershell
irm https://raw.githubusercontent.com/djlarrix/notcd/main/instalar.ps1 | iex
```

### Qué pasa después

El instalador avanza solo en cinco pasos y sólo pide dos cosas:

1. **Entrar con Google.** Se abre una ventana llamada **Google Chrome for Testing** (un navegador aparte, sólo para notcd; no toca tu Chrome). Entra con la cuenta de Google de NotebookLM. Al aparecer NotebookLM, la ventana se cierra sola.
2. **Cerrar la app si está abierta.** En Mac con `Command + Q`; en Windows, desde el ícono junto al reloj → *Salir*. El instalador espera y termina solo.

Al terminar se abre la carpeta con **`notcd.zip`** (la skill) seleccionado. Después abre la app y pregúntale: *«¿Qué cuadernos tengo en NotebookLM?»*. Si responde con tus cuadernos, quedó listo.

**Para actualizar** más adelante: pega el mismo comando otra vez. La sesión de Google se mantiene.

**Si tenías la versión anterior** (que tenía otro nombre), el comando la desinstala, quita sus registros y su skill, y traslada tu sesión de Google: no hay que volver a iniciar sesión.

---

## Índice

1. [Qué instala el comando](#1-qué-instala-el-comando)
2. [La ventana de Google, paso a paso](#2-la-ventana-de-google-paso-a-paso)
3. [Cerrar la app cuando lo pide](#3-cerrar-la-app-cuando-lo-pide)
4. [Subir la skill a la app](#4-subir-la-skill-a-la-app)
5. [Comprobar que funciona](#5-comprobar-que-funciona)
6. [Uso diario](#6-uso-diario)
7. [Problemas frecuentes](#7-problemas-frecuentes)
8. [Actualizar y desinstalar](#8-actualizar-y-desinstalar)
9. [Otra forma: la extensión de doble clic](#9-otra-forma-la-extensión-de-doble-clic)
10. [Lista para quien instala a otros](#10-lista-para-quien-instala-a-otros)

---

## 1. Qué instala el comando

| | |
|---|---|
| **uv** | Un instalador de programas en Python, estándar y gratuito ([astral.sh](https://astral.sh)). Instala una copia de Python sólo para notcd, sin tocar nada más del computador. |
| **notcd** | Un programa pequeño que corre en el computador y habla con NotebookLM usando tu sesión de Google. Se descarga desde este repositorio. Sólo se activa cuando la app le pide algo. |
| **Registro en la app** | Una entrada en la configuración de la app de escritorio (y de la app de código, si la usas) para que sepan que notcd existe, con respaldo de la configuración anterior. |
| **La skill** (*notcd*) | El método de trabajo, como `notcd.zip` en la carpeta *notcd* de tus Documentos, para subirla a la app ([punto 4](#4-subir-la-skill-a-la-app)). |
| **Tu sesión de Google** | Queda guardada en la carpeta `.notcd` de tu usuario. Como quedar con la sesión iniciada en un navegador: no se guarda tu contraseña. |

Requisitos: macOS 12 o superior, o Windows 10 u 11; internet; unos 500 MB libres.

> **¿Qué cuenta de Google usar?** Con una cuenta de Google Workspace (corporativa), Google no revisa ni usa para entrenar lo que se sube a NotebookLM. Con una cuenta personal (@gmail.com) tampoco, **salvo que se dé feedback** (👍/👎) en NotebookLM: con cuenta personal, nunca dar feedback. Detalle en el [README](README.md#antes-de-usarlo-con-documentos-de-clientes).

## 2. La ventana de Google, paso a paso

En el paso 3 del instalador:

1. Se abre la ventana **Google Chrome for Testing**. **La primera vez tarda uno o dos minutos** (descarga ese navegador) y a veces aparece **detrás** de otras ventanas: búscala en el Dock (Mac) o en la barra de tareas (Windows).
2. Entra con **la cuenta de Google que usas en NotebookLM** y completa la verificación en dos pasos si la pide. Tienes 10 minutos.
3. Cuando aparece NotebookLM, la ventana se cierra sola y el instalador muestra algo como:

   ```
   ✓ Sesión de Google guardada
   ✓ Conectado a NotebookLM como tunombre@estudio.cl.
       12 cuaderno(s) en la cuenta.
   ```

Si la ventana no aparece o Google dice *«Este navegador o app puede no ser seguro»*, el instalador reintenta solo con tu Google Chrome. Si aun así no resulta, termina igual: después le pides al asistente *«Conéctate a NotebookLM»* y se abre la ventana de nuevo.

## 3. Cerrar la app cuando lo pide

La app reescribe su configuración al cerrarse, así que el registro sólo se puede hacer con la app cerrada. En el paso 4, si está abierta, el instalador muestra:

```
! La app de escritorio está abierta: al cerrarse reescribe su configuración y borraría el registro.
    Ciérrala por completo ahora. Esperando…
```

Ciérrala **por completo** (cerrar la ventana no basta):
- **Mac:** `Command + Q`.
- **Windows:** al cerrar la ventana, la app **sigue corriendo** junto al reloj. En la barra de tareas, abre la flechita **^** (íconos ocultos), haz clic derecho en el ícono de la app y elige **Salir**.

El instalador lo detecta, termina el registro y queda listo para volver a abrir la app. Sólo cuenta la app misma: los procesos ayudantes que quedan vivos al cerrarla no la hacen parecer abierta. Si en 10 minutos la app sigue abierta, el instalador termina sin registrar en ella y explica cómo hacerlo después (ver [Problemas frecuentes](#7-problemas-frecuentes)).

## 4. Subir la skill a la app

notcd funciona sin esto: el servidor ya le da al asistente las reglas y las guías. La skill agrega el método completo para que lo aplique solo.

1. En la app: **Configuración → Capacidades**.
2. En **Skills**, pulsa **Subir skill** y elige **`notcd.zip`**. Está en la carpeta *notcd* dentro de tus Documentos; al terminar, el instalador abre esa carpeta y deja el archivo seleccionado. En Windows con OneDrive, Documentos suele estar en *OneDrive → Documentos*.

   **O descárgalo directo:** [notcd.zip](https://github.com/djlarrix/notcd/releases/latest/download/notcd.zip) (siempre la versión vigente).
3. Verifica que la skill **notcd** quede activada.

> **Sube `notcd.zip`.** Si quedó en la app alguna skill de la versión anterior a medio cargar, bórrala antes.

Si no aparece la sección Skills, activa primero **«Ejecución de código y creación de archivos»** en esa misma pantalla.

## 5. Comprobar que funciona

En una conversación nueva:

> ¿Qué cuadernos tengo en NotebookLM?

La app pedirá permiso la primera vez que use cada herramienta de notcd (puedes permitirlo una vez o siempre) y el asistente responderá con la lista de tus cuadernos.

## 6. Uso diario

Se le habla al asistente normalmente. Algunos ejemplos:

> Crea un cuaderno «Pérez con Banco Austral · C-1234-2025 · 3° Civil Stgo» y sube la carpeta /Users/tunombre/Documents/Causas/Perez

> Usando el cuaderno de Pérez: arma la cronología del juicio con fecha y foja de cada actuación, y dime qué plazos están corriendo.

> En el cuaderno de due diligence, haz una tabla con partes, precio, plazo, renovación, terminación anticipada y multas de cada contrato. Después dime cuáles se apartan de nuestro estándar.

> Revisa este borrador contra el expediente y verifica que todas las citas entre comillas sean literales.

> Prepárame un resumen en audio tipo debate entre la tesis del demandante y la del demandado, para escucharlo antes de la audiencia.

### Plantillas listas

En el botón **+** de la conversación aparecen cuatro plantillas de notcd: **Analizar un expediente**, **Revisar o comparar contratos**, **Preparar una audiencia** y **Verificar las citas y hechos de un escrito**.

### Cómo darle la ruta de un archivo o carpeta

notcd sube documentos desde el computador, así que el asistente necesita su **ruta** (los archivos adjuntados en el chat no le sirven a notcd):

- **Mac:** en Finder, clic derecho sobre el archivo o carpeta, **mantén presionada la tecla Opción** y elige **Copiar «…» como nombre de ruta**. Pégala en el chat.
- **Windows:** clic derecho sobre el archivo o carpeta → **Copiar como ruta** (en Windows 10, mantén `Shift` al hacer clic derecho). Pégala en el chat.

### Lo que conviene saber

- **El asistente verifica las citas.** Antes de entregar un texto con citas entre comillas, las compara letra por letra con los documentos. Si una no es literal, muestra el texto real.
- **Los cuadernos que crea notcd responden como «lector jurídico»**: sólo lo que consta, «no consta» cuando falta, citas textuales.
- **Algunas operaciones siguen en segundo plano.** Subir muchos documentos o una pregunta difícil pueden tardar más de un minuto; el asistente lo avisa y recoge el resultado después.
- **Lo generado** (audios, presentaciones en PowerPoint, informes, tablas en CSV que se abren en Excel, mapas mentales) queda en **Documentos/notcd/**, en una carpeta por cuaderno.
- **Audios y videos tardan** de 5 a 15 minutos: el asistente los encarga y los recoge cuando se lo pidas.

## 7. Problemas frecuentes

**El comando no hace nada o dice que no reconoce `curl` / `irm`.**
Revisa que estés en la Terminal (Mac) o en PowerShell (Windows, no en «Símbolo del sistema») y que la línea se haya copiado completa.

**Windows: «la ejecución de scripts está deshabilitada».**
Usa este comando en su lugar:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://raw.githubusercontent.com/djlarrix/notcd/main/instalar.ps1 | iex"
```

**El instalador dice que la app está abierta, pero la cerré.**
En Windows, cerrar la ventana deja a la app corriendo junto al reloj: flechita **^** de la barra de tareas → clic derecho en el ícono de la app → **Salir**. El instalador muestra qué detectó (`detectado: …`). Si ya la cerraste y aun así insiste, pega esto en PowerShell:

```powershell
$env:NOTCD_IGNORAR_APP_ABIERTA='1'; irm https://raw.githubusercontent.com/djlarrix/notcd/main/instalar.ps1 | iex
```

(Sólo con la app realmente cerrada: si estuviera abierta, al cerrarse borraría el registro.) Para ayudarme a corregirlo, abre una ventana nueva de PowerShell, ejecuta `notcd diagnostico` y envíame lo que aparece bajo *«Procesos de la app en esta sesión»*.

**La app no ve las herramientas de notcd.**
La app estaba abierta cuando se registró. Ciérrala por completo y pega el comando otra vez (es seguro repetirlo).

**Herramientas repetidas en la app.**
Quedó instalada la extensión de la versión anterior: desinstálala en *Configuración → Extensiones* (la que no se llama notcd). `notcd diagnostico` avisa si la encuentra.

**«No hay sesión», «la sesión expiró» o «la sesión está incompleta».**
Pídele al asistente *«Conéctate a NotebookLM»* y vuelve a entrar en la ventana. O en la terminal: `notcd login`.

**«NotebookLM está limitando las solicitudes».**
Se alcanzó la cuota de uso de la cuenta (por ejemplo, de audios por día). Se libera sola.

**Errores raros en cosas que antes funcionaban.**
Probablemente Google cambió NotebookLM. Pídele al asistente *«Revisa el estado de notcd»*: si hay una corrección, la aplica. O pega el comando de instalación otra vez. Después, reinicia la app.

**Un archivo .doc no se sube**: NotebookLM no acepta el formato antiguo de Word; guárdalo como .docx o PDF.
**Un PDF escaneado no se lee**: hay que pasarlo antes por reconocimiento de texto (OCR).

**Para soporte**, en una terminal nueva:

```bash
notcd diagnostico
```

Muestra versiones, sesión, registro en las apps y las últimas operaciones, sin datos de clientes.

## 8. Actualizar y desinstalar

**Actualizar**: pega el mismo comando de instalación. O pídele al asistente *«Actualiza notcd»*, o en la terminal `notcd actualizar`. Después, reinicia la app.

**Desinstalar**, en la terminal:

```bash
notcd desinstalar
```

Quita notcd de las apps. Para borrar también el programa: `uv tool uninstall notcd`. Para borrar la sesión de Google guardada: elimina la carpeta `.notcd` de tu usuario. La skill subida a la app se borra desde *Configuración → Capacidades*.

## 9. Otra forma: la extensión de doble clic

Sirve sólo para la app de escritorio y no usa la Terminal. Útil si alguien no puede o no quiere pegar el comando.

1. Descarga **`notcd-0.2.1.mcpb`** y **`notcd.zip`** desde la [página de versiones](https://github.com/djlarrix/notcd/releases/latest) (*Assets*).
2. **Doble clic en el `.mcpb`** → la app muestra la extensión → **Instalar**. La primera vez tarda uno o dos minutos en estar disponible. Para confirmar: *Configuración → Extensiones* muestra **notcd** activada.
3. Sube la skill ([punto 4](#4-subir-la-skill-a-la-app)).
4. En una conversación nueva: *«Conéctate a NotebookLM»* y entra con Google en la ventana que se abre.

**Usa una forma o la otra, no ambas.** Si ya tienes la extensión, el comando de instalación lo detecta y no registra notcd otra vez en la app de escritorio. Para actualizar la extensión, instala el `.mcpb` de la versión nueva.

## 10. Lista para quien instala a otros

Antes:
- [ ] La persona tiene la app de escritorio instalada y con sesión iniciada.
- [ ] Sabe con qué cuenta de Google usará NotebookLM y tiene su teléfono a mano.

En su computador (unos 10 minutos):
- [ ] En Windows, cerrar la app desde el ícono junto al reloj → *Salir*.
- [ ] Abrir la Terminal (Mac) o PowerShell (Windows) y pegar el comando de la [versión corta](#la-versión-corta-un-comando).
- [ ] Entrar con Google en la ventana *Google Chrome for Testing*.
- [ ] Si lo pide, cerrar la app.
- [ ] Subir `notcd.zip` (se abre la carpeta donde quedó) en *Configuración → Capacidades → Skills*.
- [ ] Abrir la app y preguntar *«¿Qué cuadernos tengo en NotebookLM?»*.

Antes de irse, explicarle:
- [ ] Que lo que sube va a su cuenta de Google, y la regla de **no dar feedback (👍/👎) con cuenta personal**.
- [ ] Cómo copiar la ruta de una carpeta ([punto 6](#cómo-darle-la-ruta-de-un-archivo-o-carpeta)) y las cuatro plantillas del botón +.
- [ ] Que si algo falla, lo primero es pedirle al asistente *«Revisa el estado de notcd»*.
