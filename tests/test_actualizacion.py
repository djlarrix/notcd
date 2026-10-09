from notcd import actualizacion


def test_elige_la_estable_mas_alta_bajo_1_0():
    versiones = ["0.8.3", "0.8.4", "0.8.10", "0.9.0rc1", "1.0.0", "0.8.5a1"]
    assert actualizacion.mas_nueva_compatible(versiones) == "0.8.10"


async def test_avisa_si_hay_correccion(monkeypatch):
    async def ultima():
        return "99.0.0"

    monkeypatch.setattr(actualizacion, "ultima_disponible", ultima)
    monkeypatch.setattr(actualizacion, "instalada", lambda: "0.8.4")
    assert "actualizar_conexion" in await actualizacion.aviso()


async def test_no_avisa_si_esta_al_dia(monkeypatch):
    async def ultima():
        return "0.8.4"

    monkeypatch.setattr(actualizacion, "ultima_disponible", ultima)
    monkeypatch.setattr(actualizacion, "instalada", lambda: "0.8.4")
    assert await actualizacion.aviso() is None


def test_en_el_repositorio_es_modo_desarrollo():
    assert actualizacion.modo() == "desarrollo"
    bien, mensaje = actualizacion.aplicar_sincrono()
    assert not bien and "desarrollo" in mensaje
