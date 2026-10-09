# Leer un expediente con NotebookLM

Para causas judiciales (el "ebook" o cuadernos descargados de la Oficina Judicial Virtual), expedientes arbitrales (CAM u otros), carpetas de investigación, sumarios administrativos o cualquier conjunto de piezas procesales.

## 1. Armar el cuaderno

1. `listar_cuadernos(filtro=...)` para no duplicar: puede que ya exista.
2. `crear_cuaderno` con un título que lo identifique sin abrirlo: **partes + rol + tribunal**, p. ej. «Pérez con Banco Austral · C-1234-2025 · 3° Civil Stgo». El cuaderno nace configurado como lector jurídico.
3. `agregar_fuentes(archivos=[carpeta o ebook])`. Si el usuario no indicó qué subir, pregúntale. Si la operación vuelve con `trabajo_id`, recógela con `ver_trabajo`.
4. `ver_cuaderno`: confirma que todo quedó «lista». Un PDF escaneado sin texto reconocible queda con muy pocas palabras: revísalo con `leer_fuente` y avisa si no se puede leer.

Un ebook de la OJV suele ser un solo PDF largo con todo el expediente. Funciona bien como una fuente; si vienen cuadernos separados (principal, apremio, incidentes), súbelos por separado para poder acotar preguntas con `fuente_ids`.

## 2. Batería de preguntas

Una pregunta por llamada, en este orden. Pide siempre fecha y foja (o página) de cada dato, y que diga «no consta» cuando falte.

**Identificación**
- Tribunal, rol, procedimiento, materia y cuantía según la demanda.
- Partes, sus abogados y apoderados; quién tiene patrocinio y poder vigente; cambios de apoderado.

**Lo que pide cada parte**
- Hechos que alega el demandante, en orden; peticiones concretas del petitorio.
- Excepciones, defensas y alegaciones del demandado; si hubo demanda reconvencional, lo mismo.
- Hechos que ambas partes reconocen (no controvertidos).

**El procedimiento**
- Cronología completa de actuaciones con fecha y foja: notificaciones, escritos principales, resoluciones, audiencias.
- Resoluciones que causan ejecutoria o que están pendientes de recurso; recursos interpuestos y su estado.
- Último trámite y qué está pendiente.

**Prueba**
- Resolución que recibe la causa a prueba y los puntos de prueba fijados, transcritos.
- Prueba ofrecida y rendida por cada parte (documental, testimonial, confesional, pericial, inspección, oficios), con su resultado.
- Prueba ofrecida que no se rindió; diligencias pendientes.

**Lo que no cuadra**
- Contradicciones entre lo que dice cada parte y los documentos.
- Contradicciones de una misma parte entre sus escritos.
- Hechos alegados sin prueba.

### Por materia (agrega a la batería general)

- **Laboral**: inicio y término de la relación, cargo, remuneración pactada y la que alega cada parte, causal invocada y transcripción de la carta de despido, fecha de la carta y de su envío, aviso a la Inspección del Trabajo, estado de cotizaciones previsionales, montos que se demandan por cada concepto.
- **Cobro / ejecutivo**: título invocado y su transcripción relevante, monto, fecha de exigibilidad, intereses pactados, gestiones preparatorias, excepciones opuestas, embargos y bienes.
- **Responsabilidad civil**: hecho dañoso con fecha, daño alegado por partida y su respaldo, relación causal que se alega, factores de atribución invocados.
- **Familia**: hijos y edades, régimen actual (cuidado personal, relación directa y regular, alimentos), ingresos acreditados de cada parte, informes técnicos y su conclusión, medidas cautelares vigentes.
- **Arbitraje**: acta de constitución y reglas procesales acordadas, plazo del arbitraje, puntos de prueba, peritajes y sus conclusiones, incidentes resueltos.
- **Penal**: hechos de la formalización o acusación transcritos, calificación jurídica invocada, medidas cautelares, diligencias de investigación y su resultado, plazos de la investigación.

## 3. Los plazos

NotebookLM puede encontrar las fechas de notificación y la resolución de la que corre un plazo, pero **no calcules ni afirmes un plazo legal con lo que diga NotebookLM**: el plazo aplicable y su cómputo se verifican en la norma vigente (Responsa u otra fuente oficial). Entrega: actuación → fecha de notificación (con foja) → plazo según la norma traída → vencimiento calculado, marcando qué parte del cálculo es tuya.

## 4. Verificar

Antes de entregar, pasa por `buscar_pasajes` o `leer_fuente` todo lo que sostiene una conclusión: fechas de notificación, montos, el texto de los puntos de prueba, la causal, lo que dijo un testigo. Las citas textuales que vayas a usar, por `verificar_citas`.

## 5. Tu trabajo

Con lo extraído: teoría del caso de cada lado, el punto que decide, debilidades de argumentación y de prueba, riesgos, qué falta y qué se puede hacer todavía. Si está disponible la skill `litis`, aplícala usando a NotebookLM como lector del expediente.

Cierra ofreciendo `guardar_nota` con la minuta (título con fecha: «Minuta IA · 07-10-2026»), para que quede en el cuaderno junto a las piezas.
