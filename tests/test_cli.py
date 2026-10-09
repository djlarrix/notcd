import json
import sys
import zipfile

import pytest

from notcd import cli, nombres, rutas

EXE = nombres.EJECUTABLE_WINDOWS
DESKTOP_WIN = rf"C:\Users\ana\AppData\Local\Anthropic{nombres.MARCA}\app-1.4.0\{EXE}"


def test_configurar_registra_sin_borrar_lo_demas(casa_temporal, monkeypatch):
    monkeypatch.setattr(cli, "procesos_app_escritorio", lambda: [])
    desktop = rutas.config_app_escritorio()
    desktop.parent.mkdir(parents=True)
    desktop.write_text(json.dumps({"mcpServers": {"responsa": {"command": "node"}}, "preferences": {"x": 1}}))
    code = rutas.config_app_codigo()
    code.write_text(json.dumps({"numStartups": 7, "projects": {"/a": {}}}))

    assert cli.main(["configurar"]) == 0

    d = json.loads(desktop.read_text())
    assert d["preferences"] == {"x": 1}
    assert d["mcpServers"]["responsa"] == {"command": "node"}
    assert d["mcpServers"]["notcd"] == {"command": sys.executable, "args": ["-m", "notcd", "servidor"], "env": {}}
    c = json.loads(code.read_text())
    assert c["numStartups"] == 7 and "notcd" in c["mcpServers"]
    assert desktop.with_name(desktop.name + cli.RESPALDO).exists()

    skill = rutas.skills_app_codigo() / "notcd" / "SKILL.md"
    assert skill.read_text(encoding="utf-8").startswith("---\nname: notcd\n")
    with zipfile.ZipFile(rutas.carpeta_descargas() / "notcd.zip") as z:
        nombres = z.namelist()
        # Lo que exige la app al subir: carpeta raíz con el nombre de la skill y SKILL.md adentro.
        assert "notcd/SKILL.md" in nombres
        assert all(n.startswith("notcd/") for n in nombres)


def test_configurar_no_toca_desktop_si_esta_abierto(casa_temporal, monkeypatch):
    monkeypatch.setattr(cli, "procesos_app_escritorio", lambda: [DESKTOP_WIN])
    desktop = rutas.config_app_escritorio()
    desktop.parent.mkdir(parents=True)
    desktop.write_text("{}")
    assert cli.main(["configurar"]) == 1
    assert json.loads(desktop.read_text()) == {}
    assert "notcd" in json.loads(rutas.config_app_codigo().read_text())["mcpServers"]


def test_json_invalido_no_se_toca(casa_temporal, monkeypatch):
    monkeypatch.setattr(cli, "procesos_app_escritorio", lambda: [])
    desktop = rutas.config_app_escritorio()
    desktop.parent.mkdir(parents=True)
    desktop.write_text("{ roto")
    assert cli.main(["configurar", "--sin-code"]) == 1
    assert desktop.read_text() == "{ roto"


def test_desinstalar_quita_solo_notcd(casa_temporal, monkeypatch):
    monkeypatch.setattr(cli, "procesos_app_escritorio", lambda: [])
    desktop = rutas.config_app_escritorio()
    desktop.parent.mkdir(parents=True)
    desktop.write_text(json.dumps({"mcpServers": {"responsa": {}}}))
    cli.main(["configurar"])
    cli.main(["desinstalar"])
    assert json.loads(desktop.read_text())["mcpServers"] == {"responsa": {}}
    assert not (rutas.skills_app_codigo() / "notcd").exists()


def test_configurar_no_duplica_si_esta_la_extension(casa_temporal, monkeypatch):
    monkeypatch.setattr(cli, "procesos_app_escritorio", lambda: [DESKTOP_WIN])  # ni siquiera pide cerrarlo
    desktop = rutas.config_app_escritorio()
    (desktop.parent / nombres.CARPETA_EXTENSIONES / "local.mcpb.alguien.notcd").mkdir(parents=True)
    desktop.write_text("{}")
    assert cli.main(["configurar", "--esperar"]) == 0
    assert json.loads(desktop.read_text()) == {}
    assert "notcd" in json.loads(rutas.config_app_codigo().read_text())["mcpServers"]


@pytest.mark.parametrize(
    "ruta",
    [
        rf"C:\Users\ana\.local\bin\{EXE}",
        rf"C:\Users\ana\AppData\Roaming\npm\node_modules\@anthropic-ai\{nombres.marca}-code\bin\{EXE}",
        rf"C:\Users\ana\AppData\Roaming\{nombres.MARCA}\{nombres.marca}-code\2.1.0\{EXE}",
    ],
)
def test_la_app_de_codigo_no_cuenta_como_app_de_escritorio(ruta):
    assert cli.es_app_codigo(ruta)


@pytest.mark.parametrize(
    "ruta",
    [DESKTOP_WIN, rf"C:\Program Files\WindowsApps\{nombres.MARCA}_1.4.0.0_x64__pzs8sxrjxfjjc\app\{EXE}"],
)
def test_la_app_de_escritorio_si_cuenta(ruta):
    assert not cli.es_app_codigo(ruta)


def test_si_no_lo_cierran_no_espera_para_siempre(casa_temporal, monkeypatch, capsys):
    monkeypatch.setattr(cli, "procesos_app_escritorio", lambda: [DESKTOP_WIN])
    monkeypatch.setattr(cli, "ESPERA_CIERRE", 0)
    desktop = rutas.config_app_escritorio()
    desktop.parent.mkdir(parents=True)
    desktop.write_text("{}")
    assert cli.main(["configurar", "--esperar"]) == 1
    salida = capsys.readouterr().out
    assert "detectado: " + DESKTOP_WIN in salida
    assert "sigue abierta" in salida
    assert json.loads(desktop.read_text()) == {}


def test_se_puede_saltar_el_chequeo(casa_temporal, monkeypatch):
    monkeypatch.setattr(cli, "procesos_app_escritorio", lambda: [DESKTOP_WIN])
    monkeypatch.setenv("NOTCD_IGNORAR_APP_ABIERTA", "1")
    desktop = rutas.config_app_escritorio()
    desktop.parent.mkdir(parents=True)
    desktop.write_text("{}")
    assert cli.main(["configurar", "--esperar"]) == 0
    assert "notcd" in json.loads(desktop.read_text())["mcpServers"]


@pytest.mark.skipif(sys.platform != "win32", reason="sólo Windows")
def test_documentos_de_windows_se_encuentran():
    ruta = rutas.documentos_windows()
    assert ruta is not None and ruta.is_dir()


@pytest.mark.skipif(sys.platform != "win32", reason="sólo Windows")
def test_detector_real_de_windows_funciona_sin_la_app_abierta():
    # En la máquina de la CI no hay app de escritorio: debe responder lista vacía, sin fallar.
    assert cli.procesos_app_escritorio() == []


def test_quita_el_zip_antiguo_rechazado(casa_temporal, monkeypatch):
    monkeypatch.setattr(cli, "procesos_app_escritorio", lambda: [])
    viejo = rutas.carpeta_descargas() / nombres.ZIPS_SKILL_ANTERIORES[0]
    viejo.parent.mkdir(parents=True, exist_ok=True)
    viejo.write_text("zip antiguo")
    cli.main(["configurar", "--sin-desktop"])
    assert not viejo.exists()
    assert (rutas.carpeta_descargas() / "notcd.zip").is_file()


CHROME_HOST = "chrome-extension://fcoeoabgfenejglbffodgkkbkcdhcgfn/ --parent-window=0"


@pytest.mark.parametrize(
    "ruta, comando, esperado",
    [
        (DESKTOP_WIN, f'"{DESKTOP_WIN}"', "principal"),
        (DESKTOP_WIN, f'"{DESKTOP_WIN}" --type=crashpad-handler --database=x', "ayudante de la app de escritorio (crashpad-handler)"),
        (DESKTOP_WIN, f'"{DESKTOP_WIN}" --type=renderer --lang=es-419', "ayudante de la app de escritorio (renderer)"),
        (DESKTOP_WIN, f'"{DESKTOP_WIN}" {CHROME_HOST}', "puente de la extensión de Chrome"),
        (DESKTOP_WIN, f'"{DESKTOP_WIN}" --squirrel-firstrun', "instalador o actualizador de la app"),
        (rf"C:\Users\ana\.local\bin\{EXE}", nombres.marca, "app de código"),
        ("", "", "sin información (de otro usuario o con permisos de administrador)"),
    ],
)
def test_clasifica_cada_proceso_de_la_app(ruta, comando, esperado):
    assert cli.que_es(ruta, comando) == esperado


def _esperar(condicion, segundos=15):
    import time

    limite = time.monotonic() + segundos
    while time.monotonic() < limite:
        if condicion():
            return True
        time.sleep(0.5)
    return False


@pytest.mark.skipif(sys.platform != "win32", reason="sólo Windows")
def test_windows_ignora_el_ayudante_que_queda_vivo_al_cerrar_la_app(tmp_path):
    """El caso real: la app cerrada, pero su ayudante de fallas (--type=crashpad-handler) sigue vivo."""
    import os
    import shutil
    import subprocess
    from pathlib import Path

    base = Path(sys._base_executable).parent
    carpeta = tmp_path / f"Anthropic{nombres.MARCA}" / "app-1.0.0"
    carpeta.mkdir(parents=True)
    falso = carpeta / EXE  # un Python con el nombre y la ruta de la app de escritorio
    shutil.copy(sys._base_executable, falso)
    for dll in base.glob("*.dll"):
        shutil.copy(dll, carpeta)
    entorno = {**os.environ, "PYTHONHOME": str(base)}
    dormir = "import time; time.sleep(120)"
    ayudante = subprocess.Popen([str(falso), "-c", dormir, "--type=crashpad-handler"], env=entorno)
    try:
        assert _esperar(lambda: any("crashpad" in c for _, c in cli.procesos_app_windows()))
        assert cli.procesos_app_escritorio() == []
        principal = subprocess.Popen([str(falso), "-c", dormir], env=entorno)
        try:
            assert _esperar(lambda: cli.procesos_app_escritorio() == [str(falso)])
        finally:
            principal.kill()
    finally:
        ayudante.kill()
