---
name: notcd
description: Trabajar en equipo con NotebookLM (Gemini Notebook) a través de las herramientas de notcd. Úsala cuando el usuario mencione NotebookLM, Gemini Notebook o un "cuaderno"; cuando haya que leer un volumen grande de documentos (un expediente o "ebook" de la Oficina Judicial Virtual, un expediente arbitral, decenas de contratos, un data room, transcripciones) y responder con citas textuales; cuando haya que verificar que las citas de un escrito sean literales; o cuando pida un resumen en audio o podcast, un mapa mental, una tabla comparativa, una presentación o tarjetas de estudio a partir de documentos.
---

# NotebookLM lee, tú piensas

Dos IAs, dos oficios. **NotebookLM lee**: retiene corpus que no caben cómodamente en una conversación (hasta cientos de fuentes por cuaderno) y responde anclado a ellos, devolviendo el pasaje textual que respalda cada frase. **Tú piensas y escribes**: decides qué preguntar, desconfías de lo que vuelve, razonas jurídicamente y redactas. El error típico es invertir los papeles: pedirle a NotebookLM la estrategia y tratar de recordar tú el expediente.

## Reglas que no se negocian

**1. Cada hecho sacado de los documentos lleva su respaldo, pegado a la afirmación.** Fuente y pasaje textual, tal como volvieron de `preguntar` o `buscar_pasajes`:

> El arriendo se pactó en UF 85 mensuales (Contrato de arrendamiento, cláusula cuarta: "la renta mensual será la suma equivalente en pesos a 85 Unidades de Fomento").

Una respuesta de NotebookLM marcada **SIN CITAS** no está verificada: dilo así o verifícala antes de usarla.

**2. Lo que decide el asunto se comprueba en el original.** Fechas, montos, plazos, quién dijo qué, el texto exacto de una cláusula o de una resolución: contrasta con `buscar_pasajes` (texto original, sin resumir) o `leer_fuente`. NotebookLM a veces atribuye a una fuente lo que dice otra, junta dos fechas o resume de más.

**3. Toda cita entre comillas pasa por `verificar_citas` antes de entregarse.** Es una comprobación mecánica, no otra IA: dice si la cita está literal, con qué diferencias o si no está. Una cita que no sale LITERAL se corrige con el texto real o se saca de las comillas.

**4. Separa las capas.** Que se vea qué viene de los documentos (con cita) y qué es análisis tuyo. Un párrafo que mezcla las dos sin marcar se lee entero como hecho comprobado.

**5. NotebookLM no es fuente del derecho.** No le preguntes qué dice un artículo ni cómo ha fallado la Corte Suprema: contestará con lo que haya en el cuaderno o con lo que crea saber. El texto vigente de normas, fallos y dictámenes se trae de las herramientas de fuentes oficiales disponibles (por ejemplo Responsa). Si conviene cruzarlo con los documentos del caso, súbelo al cuaderno con `agregar_fuentes(texto=..., titulo_texto=...)`.

**6. Subir es enviar a Google.** `agregar_fuentes` sube documentos a la cuenta de Google del usuario. Si no lo pidió expresamente para esos documentos, pregunta antes. Nunca subas carpetas completas "por si acaso".

## Cómo preguntarle a NotebookLM

- **Específico y en serie.** "¿Qué fechas de notificación constan y en qué foja?" rinde más que "resume el caso". Varias preguntas acotadas, una por llamada.
- **Repregunta en el mismo hilo** con el `conversacion_id` de la respuesta anterior.
- **Acota las fuentes** con `fuente_ids` cuando la pregunta es sobre un documento.
- **Pide formato verificable**: "lista cada hecho con su fuente", "transcribe la cláusula", "si no consta, dilo".
- **Pídele lo contrario**: con una tesis armada, pregunta "¿qué pasajes la contradicen o debilitan?". Es la mejor defensa contra el sesgo de confirmación de las dos IAs.

Los cuadernos creados con `crear_cuaderno` ya vienen configurados para responder como lector jurídico (sólo lo que consta, cita textual, "no consta" cuando falta). En cuadernos antiguos, `configurar_lector` aplica lo mismo.

## Operaciones largas

La aplicación de escritorio corta las herramientas al minuto. Si una operación tarda más (subir muchos documentos, una pregunta difícil sobre un cuaderno enorme, un mapa mental, verificar muchas citas), vuelve un `trabajo_id` y sigue corriendo: pide el resultado con `ver_trabajo` y no repitas la operación. Audios, videos y presentaciones tardan minutos: se encargan con `generar` y se recogen con `obtener_contenido`.

## Guías por tipo de trabajo

Antes de un trabajo de varios pasos, lee la guía que corresponda (están en `referencias/`, o pídelas con `guia_de_metodo`):

| Trabajo | Guía |
|---|---|
| Leer un expediente judicial o arbitral, armar cronología, detectar plazos | [expediente.md](referencias/expediente.md) |
| Revisar o comparar contratos, due diligence | [contratos.md](referencias/contratos.md) |
| Preparar una audiencia, un alegato o un interrogatorio | [audiencia.md](referencias/audiencia.md) |
| Redactar o revisar un escrito con respaldo verificable | [escritos.md](referencias/escritos.md) |
| Investigar un tema, armar un cuaderno de doctrina o jurisprudencia | [investigacion.md](referencias/investigacion.md) |
| Trabajar en equipo: compartir cuadernos, notas, confidencialidad | [equipo.md](referencias/equipo.md) |

## Problemas frecuentes

- **"No hay sesión" / "la sesión expiró" / "sesión incompleta"**: `iniciar_sesion` y pide al usuario que entre con su cuenta de Google en la ventana que se abre. Luego `estado_conexion`.
- **Cuota o límite**: NotebookLM limita el uso por cuenta. Espera; no reintentes en bucle.
- **Errores raros en operaciones que antes funcionaban**: Google cambió algo. `estado_conexion` avisa si hay corrección disponible; aplícala con `actualizar_conexion` y pide al usuario reiniciar la aplicación.
- **Archivos .doc antiguos o escaneos sin texto**: NotebookLM no lee .doc (pide .docx o PDF); un PDF escaneado sin reconocimiento de texto puede quedar casi vacío: revísalo con `leer_fuente`.
