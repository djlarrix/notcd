# Investigar un tema con NotebookLM

Útil cuando hay mucho material que leer sobre un tema (un conjunto de fallos, artículos de doctrina, informes, normativa sectorial) y se necesita una síntesis con citas.

## 1. Juntar material verificable

En este orden de preferencia:

1. **Fuentes oficiales y bibliotecas propias.** Si están disponibles Responsa (legislación, jurisprudencia, dictámenes) o la biblioteca del estudio, trae de ahí los textos y súbelos al cuaderno con `agregar_fuentes(texto=..., titulo_texto=...)`, con un título que permita citarlos: «CS Rol 12.345-2024 · 15-03-2025 · nulidad del despido».
2. **Documentos del usuario** (informes en derecho, memos anteriores, papers en PDF): `agregar_fuentes(archivos=...)`.
3. **Web**: `buscar_en_web` trae candidatos. Tú eliges: prefiere sitios oficiales (bcn.cl, pjud.cl, contraloria.cl, dt.gob.cl, organismos reguladores) y revistas académicas; descarta blogs, contenido comercial y páginas sin autor ni fecha. Agrega sólo lo que el usuario apruebe, con `agregar_fuentes(urls=[...])`.

Cuidado con mezclar en un cuaderno textos de distinta vigencia: si subes una norma, que el título diga la versión o la fecha de consulta.

## 2. Preguntar

- «¿Qué criterios distintos aparecen en las fuentes sobre [problema]? Agrupa por criterio y cita cada fuente.»
- «¿Cómo evolucionó el criterio en el tiempo según las fechas de las fuentes?»
- «¿Qué argumentos se dan a favor y en contra de [tesis]?»
- «¿Qué fuentes contradicen a [fuente]?»

## 3. Entregar

La síntesis es tuya: criterio dominante, criterios minoritarios, tendencia, y qué significa para el caso del usuario. Cada afirmación con su fuente, y las citas textuales verificadas con `verificar_citas`. Recuerda que el cuaderno es una selección: «no encontré» en el cuaderno no es «no existe».

Si el tema se va a reusar, ofrece `guardar_nota` con la síntesis y deja el cuaderno nombrado por tema («Doctrina · nulidad del despido · 2026»), para que sirva al equipo.
