"""Normalización y validación del RUT chileno.

El RUT tiene un cuerpo numérico y un dígito verificador (DV) que se calcula con
el módulo 11: se multiplica cada dígito del cuerpo, de derecha a izquierda, por
la serie 2, 3, 4, 5, 6, 7 y se repite; se suman los productos, se calcula el
resto de la división por 11 y el DV es 11 menos ese resto. Si el resultado es 11
el DV es "0" y si es 10 el DV es "K".

Este módulo no sabe nada del agente ni de la base: solo convierte lo que escribe
una persona en un RUT canónico, o explica por qué no es válido.
"""

# Largo del cuerpo numérico aceptado. Los RUT antiguos pueden tener 6 dígitos;
# los actuales tienen 8.
LARGO_MINIMO = 6
LARGO_MAXIMO = 8

DV_VALIDOS = "0123456789K"


def calcular_dv(cuerpo: str) -> str:
    """Calcula el dígito verificador de un cuerpo numérico."""
    suma = 0
    factor = 2
    for digito in reversed(cuerpo):
        suma += int(digito) * factor
        factor = 2 if factor == 7 else factor + 1

    resto = 11 - (suma % 11)
    if resto == 11:
        return "0"
    if resto == 10:
        return "K"
    return str(resto)


def validar_rut(valor: str | None) -> tuple[str | None, str | None]:
    """Devuelve (rut_normalizado, error).

    Acepta "12.345.678-5", "12345678-5", "123456785", "12345678k" y variantes
    con espacios. Devuelve siempre la forma canónica "12345678-5" (sin puntos,
    con guion y DV en mayúscula) o un mensaje de error en lenguaje natural,
    pensado para que el agente se lo repita al paciente.
    """
    if valor is None:
        return None, "Falta el RUT."

    limpio = (
        str(valor)
        .strip()
        .upper()
        .replace(".", "")
        .replace(" ", "")
        .replace("_", "")
    )

    if not limpio:
        return None, "Falta el RUT."

    # Si viene con guion, se respeta la separación; si no, el último carácter
    # es el DV.
    if "-" in limpio:
        partes = [parte for parte in limpio.split("-") if parte]
        if len(partes) != 2:
            return None, "El RUT debe tener un solo guion, por ejemplo 12345678-5."
        cuerpo, dv = partes
    else:
        cuerpo, dv = limpio[:-1], limpio[-1]

    if not cuerpo.isdigit():
        return None, "El cuerpo del RUT debe ser numérico, sin letras."
    if dv not in DV_VALIDOS or not dv:
        return None, "El dígito verificador debe ser un número o la letra K."
    if not (LARGO_MINIMO <= len(cuerpo) <= LARGO_MAXIMO):
        return None, f"El RUT debe tener entre {LARGO_MINIMO} y {LARGO_MAXIMO} dígitos."
    if set(cuerpo) == {"0"}:
        return None, "Ese RUT no existe."

    esperado = calcular_dv(cuerpo)
    if dv != esperado:
        return None, (
            "El RUT no es válido: el dígito verificador no corresponde. "
            "¿Me lo confirmas?"
        )

    return f"{cuerpo}-{dv}", None


def formatear_rut(rut: str | None) -> str | None:
    """Devuelve el RUT con puntos para mostrarlo: 12.345.678-5."""
    if not rut or "-" not in rut:
        return rut
    cuerpo, dv = rut.split("-", 1)
    con_puntos = f"{int(cuerpo):,}".replace(",", ".")
    return f"{con_puntos}-{dv}"
