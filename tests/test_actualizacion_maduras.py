from notcd import actualizacion


def test_opciones_maduras_limita_cada_compilada_a_una_fecha():
    opciones = actualizacion.opciones_maduras(21)
    pares = list(zip(opciones[::2], opciones[1::2]))
    assert len(pares) == len(actualizacion.COMPILADAS)
    for (opcion, valor), paquete in zip(pares, actualizacion.COMPILADAS):
        assert opcion == "--exclude-newer-package"
        nombre, fecha = valor.split("=")
        assert nombre == paquete and len(fecha) == 10
    assert "notebooklm-py" not in " ".join(opciones)
