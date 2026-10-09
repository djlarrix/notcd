# Revisar y comparar contratos

Para revisar un contrato largo, comparar un conjunto (arriendos de una cartera, contratos de trabajo de una empresa, contratos con proveedores) o hacer una due diligence sobre un data room.

## 1. El cuaderno

- Un cuaderno por operación o por cartera, no uno por contrato: la gracia es poder comparar.
- Si el cliente tiene un contrato tipo o una política de negociación, súbelo también y dale un título claro («ESTÁNDAR DEL CLIENTE — contrato tipo de arriendo»): servirá de vara.
- Anexos y modificaciones como fuentes separadas, con títulos que digan a qué contrato pertenecen.

## 2. La tabla comparativa

`generar(tipo="tabla_datos", instrucciones=...)` con columnas explícitas. Ejemplos:

**Arriendos**: «Una fila por contrato. Columnas: arrendador, arrendatario, inmueble, fecha, plazo, renovación, renta y reajuste, garantía, destino, prohibiciones de subarriendo, término anticipado y su causal, multas, quién paga gastos comunes y contribuciones, domicilio y jurisdicción.»

**Proveedores / servicios**: «Partes, objeto, precio y forma de pago, plazo y renovación automática, niveles de servicio, multas y límites de responsabilidad, confidencialidad, propiedad intelectual, término anticipado, cesión, ley aplicable y solución de controversias.»

**Contratos de trabajo**: «Trabajador, cargo, fecha de inicio, tipo de contrato y plazo, jornada, remuneración y sus componentes, beneficios, cláusulas de confidencialidad o no competencia, lugar de trabajo.»

**Due diligence societaria**: «Por documento: tipo, fecha, partes, obligaciones relevantes, cambios de control, prohibiciones de gravar o enajenar, garantías otorgadas, vencimientos, litigios mencionados.»

Pide que cada celda diga «no consta» cuando no aparezca. Las tablas son donde más se cuelan errores de atribución (el dato de un contrato en la fila de otro): **verifica con `buscar_pasajes` acotado a la fuente cada celda que importe**.

## 3. Preguntas que rinden

- «Transcribe la cláusula de término anticipado de cada contrato.» (luego `verificar_citas` sobre lo que vayas a citar)
- «¿Qué contratos tienen renovación automática y con qué aviso?»
- «¿Qué cláusulas se apartan del contrato tipo del cliente? Cita ambas versiones.»
- «¿Qué obligaciones vencen o requieren aviso en los próximos 12 meses?»
- «¿Hay cláusulas de cambio de control, exclusividad o no competencia?»
- «¿Hay contradicciones entre el contrato y sus anexos o modificaciones?»

## 4. Tu trabajo

Con la tabla y los pasajes verificados: desviaciones respecto del estándar, riesgos priorizados (alto / medio / bajo, con el porqué), cláusulas a renegociar con redacción alternativa propuesta, y lo que falta en el data room. El análisis de validez o efectos de una cláusula se apoya en la norma vigente traída de una fuente oficial, no en NotebookLM.

Ofrece `guardar_nota` con el informe y `obtener_contenido` para entregar la tabla en CSV (se abre en Excel).
