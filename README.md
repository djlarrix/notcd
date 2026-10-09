# notcd

Skill para trabajar con **NotebookLM** (Gemini Notebook) en el estudio: NotebookLM lee los documentos y responde con el pasaje textual que respalda cada frase; la IA del chat decide qué preguntar, verifica en el original y redacta.

## Instalar la skill

1. Descarga **[notcd.zip](https://github.com/djlarrix/notcd/releases/latest/download/notcd.zip)**.
2. En la app de escritorio: **Configuración → Capacidades → Skills → Subir skill** → elige `notcd.zip`.
3. Verifica que **notcd** quede activada.

Sube ese archivo (`notcd.zip`), no el ZIP que genera el botón *Code → Download ZIP* de esta página.

## Qué contiene

- `SKILL.md`: las reglas de trabajo (cita textual para cada hecho, verificación en el original, verificación mecánica de citas, separar fuentes de análisis).
- `referencias/`: guías por tipo de trabajo (expediente, contratos, audiencia, escritos, investigación, equipo).

La skill usa las herramientas del conector de NotebookLM del estudio (`preguntar`, `buscar_pasajes`, `verificar_citas`, `generar`, etc.), que se instala aparte con el comando del instructivo.
