# Trabajar en equipo con los cuadernos

## Nombres

Que un cuaderno se entienda sin abrirlo:
- Causas: «Partes · rol · tribunal» — «Pérez con Banco Austral · C-1234-2025 · 3° Civil Stgo».
- Operaciones: «Cliente · operación · año» — «Inmobiliaria X · DD compra terreno · 2026».
- Temas: «Doctrina · tema · año».

Notas con autor y fecha en el título: «Minuta IA · 07-10-2026», «Cronología verificada · 07-10-2026».

## Compartir

`compartir_cuaderno(cuaderno_id, correos=[...], rol="lector" | "editor")`. Es una acción hacia afuera: confirma con el usuario los correos y el rol antes de hacerla, y no compartas con correos fuera del estudio sin que el usuario lo pida expresamente. Por defecto Google avisa por correo a quien recibe el acceso.

- **lector**: puede ver fuentes, preguntar y ver notas.
- **editor**: además puede agregar o quitar fuentes y notas.

## Dejar el trabajo en el cuaderno

`guardar_nota` deja minutas, cronologías verificadas y análisis junto a los documentos: el colega que abre el cuaderno en NotebookLM los ve y puede preguntar sobre ellos. Una nota no es una fuente: si quieres que NotebookLM la use al responder, agrégala también como fuente con `agregar_fuentes(texto=...)`.

## Limpiar

`quitar_fuentes` elimina fuentes del cuaderno (subidas por error, duplicadas o de otro asunto). Es irreversible en NotebookLM: confirma con el usuario cuáles. Para borrar un cuaderno completo, que lo haga el usuario en notebooklm.google.com.

## Confidencialidad

- Lo que se sube queda en la cuenta de Google del usuario. Con cuentas de Google Workspace, Google no lo revisa ni lo usa para entrenar; con cuentas personales (@gmail.com) tampoco, **salvo que se dé feedback** (👍/👎) en NotebookLM: con cuenta personal, no dar feedback.
- Sigue la política del estudio sobre qué puede ir a servicios externos. Si hay duda con un documento sensible, pregunta antes de subirlo y sugiere anonimizar (nombres, RUT, datos de salud, cuentas bancarias).
