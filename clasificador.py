"""
Regla de clasificación automática para materiales nuevos (no YC4, ya no se usa).

1. Forma:
     "BUCKET" en la descripción            -> BUCKET
     "COCKTAIL SHAKER" en la descripción   -> SHAKER
     si no                                 -> REGULAR

2. Línea (DC/SS):
     "SS" en la descripción, siempre y cuando NO esté seguida
     inmediatamente de otra letra (para no confundir con palabras como
     "Seafoam", "Blossom", etc., pero sí capturar casos como "MUG2.0SS:"
     o "STK SS:")                          -> SS
     si no                                 -> DC

3. Logo (-1 / -2): se decide fuera de este módulo, según si la cantidad
   viene en la columna Single Side o Double Side del reporte de SAP.
   Bucket no tiene esta distinción (siempre una sola categoría).
"""

import re

_SS_PATTERN = re.compile(r"SS(?![A-Za-z])")


def clasificar_forma_linea(descripcion: str) -> tuple[str, str]:
    """Devuelve (forma, linea) para una descripción de material de SAP."""
    desc = str(descripcion).upper()

    if "BUCKET" in desc:
        forma = "BUCKET"
    elif "COCKTAIL SHAKER" in desc:
        forma = "SHAKER"
    else:
        forma = "REGULAR"

    linea = "SS" if _SS_PATTERN.search(desc) else "DC"

    return forma, linea


def pt_final(forma: str, linea: str, es_doble: bool) -> str:
    """Construye el código de PT final a partir de forma + línea + logo."""
    if forma == "BUCKET":
        return f"PT-BUCKET-{linea}"
    if forma == "SHAKER":
        base = "2LOGOSHAKER" if es_doble else "1LOGOSHAKER"
        return f"PT-{base}-{linea}"
    base = "2LOGOS" if es_doble else "1LOGO"
    return f"PT-{base}-{linea}"
