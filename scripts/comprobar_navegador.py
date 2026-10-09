"""Comprueba el inicio de sesión con los navegadores instalados (sin cuenta: sólo la mecánica).

Abre cada navegador oculto con el perfil de notcd, se conecta por su puerto de
depuración, lee cookies y pestañas, y lo cierra. Se corre con el Python donde está
instalado notcd:

    python scripts/comprobar_navegador.py [chrome|edge ...]
"""

import sys
import time

from notcd import navegador

pedidos = sys.argv[1:] or ["chrome", "edge"]
for nombre in pedidos:
    encontrados = navegador.disponibles(nombre)
    assert encontrados, f"no encontré {nombre}"
    _, ejecutable = encontrados[0]
    print(f"{nombre}: {ejecutable}")
    proceso, puerto, ruta = navegador.abrir(ejecutable, oculto=True)
    canal = navegador.Canal(puerto, ruta)
    try:
        for _ in range(20):
            paginas = [p["url"] for p in canal.llamar("Target.getTargets")["targetInfos"] if p["type"] == "page"]
            if any("accounts.google" in u for u in paginas):
                break
            time.sleep(0.5)
        cookies = canal.llamar("Storage.getCookies")["cookies"]
        print(f"  páginas: {[u[:60] for u in paginas]}")
        print(f"  {len(cookies)} cookies · sesión: {navegador.hay_sesion(cookies)} · en NotebookLM: {navegador.en_notebooklm(canal)}")
        assert any("accounts.google" in u for u in paginas), "no abrió el formulario de Google"
        assert not navegador.hay_sesion(cookies)
    finally:
        canal.llamar("Browser.close")
        canal.cerrar()
        navegador.cerrar_proceso(proceso)
    inicio = time.monotonic()
    assert navegador.iniciar_sesion(ejecutable, espera=4, oculto=True) is False
    print(f"  sin cuenta, iniciar_sesion termina sin guardar nada ({time.monotonic() - inicio:.0f} s)")
print("OK")
