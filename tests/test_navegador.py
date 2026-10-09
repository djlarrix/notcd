"""Inicio de sesión con el navegador instalado (notcd/navegador.py), sin abrir navegadores."""

import json

from notcd import navegador, rutas


class CanalFalso:
    def __init__(self, urls):
        self.urls = urls

    def llamar(self, metodo, params=None):
        assert metodo == "Target.getTargets"
        return {"targetInfos": [{"type": "page", "url": u} for u in self.urls]}


def test_portada_publica_no_cuenta_como_notebooklm():
    assert navegador.en_notebooklm(CanalFalso(["https://notebook.google.com/"]))
    assert navegador.en_notebooklm(CanalFalso(["https://notebooklm.google.com/notebook/abc"]))
    assert not navegador.en_notebooklm(CanalFalso(["https://notebook.google.com/trynow"]))
    assert not navegador.en_notebooklm(CanalFalso(["https://accounts.google.com/v3/signin/identifier"]))


def test_hay_sesion_exige_las_dos_cookies_de_google():
    sid = {"name": "SID", "domain": ".google.com"}
    sidts = {"name": "__Secure-1PSIDTS", "domain": ".google.com"}
    assert navegador.hay_sesion([sid, sidts])
    assert not navegador.hay_sesion([sid])
    assert not navegador.hay_sesion([{**sid, "domain": ".youtube.com"}, sidts])


def test_formato_de_playwright():
    cookies = [
        {"name": "SID", "value": "v", "domain": ".google.com", "path": "/", "expires": 1900000000.5,
         "httpOnly": False, "secure": True, "session": False, "sameSite": "None", "size": 3, "priority": "High"},
        {"name": "OSID", "value": "w", "domain": "notebooklm.google.com", "path": "/", "expires": -1,
         "httpOnly": True, "secure": True, "session": True},
    ]
    filas = navegador.formato_sesion(cookies)["cookies"]
    assert filas[0] == {"name": "SID", "value": "v", "domain": ".google.com", "path": "/", "expires": 1900000000.5,
                        "httpOnly": False, "secure": True, "sameSite": "None"}
    assert filas[1]["expires"] == -1 and filas[1]["sameSite"] == "Lax"


def test_una_sesion_que_no_sirve_no_reemplaza_la_anterior(monkeypatch):
    destino = rutas.sesion_google()
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text('{"cookies": [{"name": "anterior"}]}', encoding="utf-8")
    try:
        monkeypatch.setattr(navegador, "sesion_aceptada", lambda archivo: False)
        assert navegador.guardar([{"name": "SID", "value": "x", "domain": ".google.com"}]) is False
        assert json.loads(destino.read_text(encoding="utf-8"))["cookies"][0]["name"] == "anterior"
        assert not destino.with_name(destino.name + ".nuevo").exists()

        monkeypatch.setattr(navegador, "sesion_aceptada", lambda archivo: True)
        assert navegador.guardar([{"name": "SID", "value": "x", "domain": ".google.com"}]) is True
        assert json.loads(destino.read_text(encoding="utf-8"))["cookies"][0]["name"] == "SID"
    finally:
        destino.unlink(missing_ok=True)


def test_el_perfil_es_propio_de_notcd():
    from notcd import INICIO

    assert navegador.perfil() == INICIO / "navegador"
