from notcd.verificacion import Fuente, diferencias, normalizar, tramos, verificar

CONTRATO = """CLÁUSULA CUARTA: Renta.
La renta mensual será la suma equivalente en pesos a 85 Unidades de Fomento,
que el arrendatario pagará por mesada anticipada dentro de los cinco primeros días de cada mes.
CLÁUSULA DÉCIMA: Término anticipado. El arrendador podrá poner término al contrato
si el arrendatario no pagare la renta dentro del plazo señalado, sin necesidad de declaración judicial."""

FUENTES = [Fuente("f1", "Contrato.pdf", CONTRATO), Fuente("f2", "Otro.pdf", "texto sin relación " * 40)]


def test_normalizar_unifica_comillas_espacios_y_conserva_posiciones():
    texto = "Dijo:\n  “no  pagaré”—nunca"
    norm, mapa = normalizar(texto)
    assert norm == 'Dijo: "no pagaré"-nunca'
    assert texto[mapa[norm.index("p")]] == "p"


def test_tramos_quita_comillas_y_parte_en_omisiones():
    assert tramos("«uno […] dos (...) tres…»") == ["uno", "dos", "tres"]


def test_literal_aunque_cambien_saltos_de_linea_y_comillas():
    r = verificar("“la suma equivalente en pesos a 85 Unidades de Fomento, que el arrendatario”", FUENTES)
    assert r.tipo == "exacta" and r.fuente.id == "f1"
    assert "Unidades de Fomento,\nque" in r.texto_fuente


def test_mayuscula_inicial_no_cuenta_como_diferencia():
    assert verificar('"la renta mensual será la suma"', FUENTES).tipo == "exacta"


def test_mayusculas_en_el_medio_se_informan():
    assert verificar('"La RENTA mensual será la suma"', FUENTES).tipo == "exacta_mayusculas"


def test_omisiones_marcadas_se_aceptan_en_orden():
    r = verificar('"El arrendador podrá poner término al contrato […] sin necesidad de declaración judicial"', FUENTES)
    assert r.tipo == "exacta" and r.omisiones == 1


def test_omisiones_en_desorden_no_son_literales():
    r = verificar('"sin necesidad de declaración judicial […] El arrendador podrá poner término"', FUENTES)
    assert r.tipo != "exacta"


def test_una_negacion_agregada_se_detecta():
    r = verificar('"El arrendador no podrá poner término al contrato si el arrendatario no pagare la renta"', FUENTES)
    assert r.tipo == "aproximada"
    assert r.diferencias == ["sobra «no» (no está en la fuente)"]


def test_cambio_de_palabra_muestra_el_texto_real():
    r = verificar(
        '"si el arrendatario no pagara la renta dentro del plazo convenido, sin necesidad de declaración judicial"',
        FUENTES,
    )
    assert r.tipo == "aproximada"
    assert "plazo señalado" in r.texto_fuente
    assert "tu cita dice «convenido», la fuente dice «señalado»" in r.diferencias


def test_tilde_distinta_es_diferencia():
    assert "«termino» en vez de «término»" in diferencias("poner termino al contrato", "poner término al contrato")


def test_inventada_no_se_encuentra():
    assert verificar('"el arrendatario podrá subarrendar libremente el inmueble a terceros"', FUENTES).tipo == "no_encontrada"


def test_cita_corta_no_se_aproxima():
    assert verificar('"renta anual"', FUENTES).tipo == "no_encontrada"


def test_texto_grande_se_verifica_rapido():
    import time

    relleno = " ".join(f"palabra{i}" for i in range(200_000))
    grande = Fuente("g", "Expediente.pdf", relleno + " " + CONTRATO + " " + relleno)
    inicio = time.monotonic()
    r = verificar('"El arrendador podrá poner término al contrato si el arrendatario no pagara la renta"', [grande])
    assert r.tipo == "aproximada"
    assert time.monotonic() - inicio < 10
