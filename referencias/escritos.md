# Redactar o revisar un escrito con respaldo verificable

## Redactar

1. **Extraer antes de escribir.** Con `preguntar` y `buscar_pasajes`, junta los hechos que el escrito va a afirmar, cada uno con su fuente y pasaje. No redactes hechos "de memoria" de la conversación.
2. **Traer el derecho de fuente oficial.** Normas, fallos y dictámenes desde Responsa u otra fuente verificable. NotebookLM no.
3. **Redactar** (esto es tuyo): estructura, argumentación, petitorio.
4. **Verificar citas.** Junta todas las frases que van entre comillas y pásalas por `verificar_citas` en una sola llamada (acotando `fuente_ids` si sabes de qué documento vienen). Resultado:
   - **LITERAL**: queda.
   - **CON DIFERENCIAS**: reemplázala por el texto real que muestra el informe, o quítale las comillas y parafrasea. Ojo especial con diferencias que cambian el sentido (un «no», un monto, una fecha, un plazo).
   - **NO ENCONTRADA**: búscala con `buscar_pasajes`; si no aparece, sale de las comillas o sale del escrito.
5. **Verificar hechos sin comillas.** Fechas, montos y fojas que el escrito afirma: contrástalos con `buscar_pasajes`.
6. Entrega el escrito y, aparte, una tabla breve de respaldo: afirmación → fuente → pasaje.

## Revisar un borrador (propio o de la contraria)

El usuario pega o adjunta el borrador.

1. Extrae del borrador: (a) las citas textuales, (b) las afirmaciones de hecho, (c) las citas de normas y fallos.
2. (a) → `verificar_citas`.
3. (b) → para cada afirmación relevante, `buscar_pasajes`: ¿consta? ¿consta distinto?
4. (c) → no con NotebookLM: con la fuente oficial.
5. Pide a NotebookLM lo contrario: «¿qué pasajes del expediente contradicen o debilitan lo que sostiene este escrito sobre [punto]?».
6. Informe: lo que está bien respaldado, lo que no consta, lo que consta distinto, citas a corregir (con el texto real), y los flancos que deja abiertos.

## Por qué así

Un escrito con una cita inexacta o un hecho que no consta le entrega a la contraria un argumento fácil y le cuesta credibilidad al abogado frente al tribunal. `verificar_citas` no es una IA opinando: compara letra por letra contra el texto del documento.
