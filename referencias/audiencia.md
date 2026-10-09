# Preparar una audiencia o un alegato

## 1. Lo que hay que tener a mano

Del cuaderno de la causa (ver `expediente.md` si aún no está armado):
- Cronología breve con fojas.
- Hechos controvertidos y la prueba de cada lado sobre cada uno.
- Lo que dijo cada testigo o perito, con cita.
- Las resoluciones relevantes, transcritas.

## 2. Ensayar contra la otra parte

- «Según las fuentes, ¿cuáles son los tres argumentos más fuertes de la contraria y en qué pasajes se apoyan?»
- «¿Qué preguntas difíciles podría hacer el tribunal sobre nuestra posición, considerando lo que consta?»
- «¿Qué hechos que afirmamos no tienen respaldo documental en el expediente?»

Prepara tú las respuestas, con el pasaje que sostiene cada una.

## 3. Interrogatorios y contrainterrogatorios

- «Resume lo que declaró [testigo] sobre [hecho], con citas.»
- «¿Qué contradicciones hay entre la declaración de [testigo] y los documentos?»

Con eso propones las preguntas y el objetivo de cada bloque. Las citas de declaraciones que vayan a usarse en la audiencia, por `verificar_citas`.

## 4. Material para escuchar o mirar

- `generar(tipo="resumen_audio", formato_audio="debate", instrucciones="Enfrenta la tesis de [parte] con la de [parte] sobre [punto]. En español de Chile, sin inventar hechos que no consten.")`: para escuchar camino a tribunales. Tarda varios minutos: avisa y recógelo con `obtener_contenido`.
- `formato_audio="critica"` para una revisión crítica de nuestra propia posición.
- `generar(tipo="mapa_mental")` para ordenar hechos y prueba de un vistazo.
- `generar(tipo="tarjetas")` con fechas y datos clave para repasar.

## 5. La minuta

Tu entregable: minuta de alegato o de audiencia con (1) lo que se pide, (2) los dos o tres argumentos centrales, cada uno con su respaldo en el expediente y la norma traída de fuente oficial, (3) respuestas a las objeciones previsibles, (4) datos para tener a mano (fechas, fojas, montos). Todas las citas verificadas. Ofrece guardarla con `guardar_nota`.
