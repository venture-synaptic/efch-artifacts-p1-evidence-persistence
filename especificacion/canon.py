"""Serialización canónica, decodificación y hashes del contrato de intercambio (ESPECIFICACION.md, §2.1).

Normativo. **Dominio canónico** de un valor JSON:
- profundidad de anidamiento ≤ PROFUNDIDAD_MAX (32); se comprueba antes que nada, sin recursión;
- enteros en [-2^63, 2^128); booleanos; null; texto UTF-8 válido (sin sustitutos aislados), **sin normalizar**:
  el texto se compara por sus bytes UTF-8 y no depende de ninguna versión de Unicode;
- listas y objetos con claves de texto; ningún número de coma flotante.
El primer fallo se busca en orden determinista: primero la profundidad; después, en preorden con las claves de cada
objeto ordenadas.

**Forma canónica**: `json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)`
en UTF-8. El identificador de un objeto es el sha256 (hexadecimal, en minúscula) de la forma canónica del objeto
**sin** su campo `id` (y sin los campos excluidos de su tipo). Nada en esta especificación analiza un
identificador: solo se compara.
"""

import hashlib
import json

ENTERO_MIN, ENTERO_MAX = -(2 ** 63), 2 ** 128
PROFUNDIDAD_MAX = 32
DIGITOS_MAX = 39                     # 2^128 tiene 39 cifras: más cifras están fuera de rango sin convertir nada


class NoCanonico(ValueError):
    """El valor no está en el dominio canónico (profundidad, coma flotante, entero fuera de rango, texto...)."""


def _profundidad(x):
    """Comprueba la profundidad sin recursión."""
    pila = [(x, 1)]
    while pila:
        v, d = pila.pop()
        if isinstance(v, (list, dict)):
            if d > PROFUNDIDAD_MAX:
                raise NoCanonico(f"anidamiento de más de {PROFUNDIDAD_MAX} niveles")
            pila.extend((h, d + 1) for h in (v.values() if isinstance(v, dict) else v))


def _comprobar(x):
    _profundidad(x)
    pila = [(x, "$")]
    while pila:
        v, ruta = pila.pop()
        if isinstance(v, bool) or v is None:
            continue
        if isinstance(v, int):
            if not ENTERO_MIN <= v < ENTERO_MAX:
                raise NoCanonico(f"{ruta}: entero fuera de [-2^63, 2^128)")
            continue
        if isinstance(v, float):
            raise NoCanonico(f"{ruta}: número de coma flotante")
        if isinstance(v, str):
            _texto(v, ruta)
            continue
        if isinstance(v, list):
            pila.extend((h, f"{ruta}[{i}]") for i, h in reversed(list(enumerate(v))))
            continue
        if isinstance(v, dict):
            if not all(isinstance(c, str) for c in v):
                raise NoCanonico(f"{ruta}: clave no textual")
            for c in sorted(v, reverse=True):
                pila.append((v[c], f"{ruta}.{c}"))
                pila.append((c, f"{ruta}.<clave>"))
            continue
        raise NoCanonico(f"{ruta}: tipo {type(v).__name__} no admitido")


def _texto(v, ruta):
    try:
        v.encode("utf-8")
    except UnicodeEncodeError:
        raise NoCanonico(f"{ruta}: sustituto Unicode aislado")


def canonico(obj):
    """Bytes de la forma canónica."""
    _comprobar(obj)
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()


def sha(data):
    if isinstance(data, str):
        data = data.encode()
    return hashlib.sha256(data).hexdigest()


def hash_objeto(obj, excluidos=("id",)):
    """sha256 de la forma canónica de `obj` sin las claves `excluidos`."""
    return sha(canonico({k: v for k, v in obj.items() if k not in excluidos}))


def con_id(obj, excluidos=("id",)):
    """Copia de `obj` con su campo `id` calculado."""
    sin = {k: v for k, v in obj.items() if k != "id"}
    return {**sin, "id": hash_objeto(sin, excluidos)}


def _explorar_texto(texto):
    """Antes de decodificar, y sin recursión: profundidad de anidamiento y longitud de cada número (§2.1)."""
    prof, i, n, en_cadena = 0, 0, len(texto), False
    while i < n:
        c = texto[i]
        if en_cadena:
            if c == "\\":
                i += 2
                continue
            if c == '"':
                en_cadena = False
        elif c == '"':
            en_cadena = True
        elif c in "[{":
            prof += 1
            if prof > PROFUNDIDAD_MAX:
                raise NoCanonico(f"anidamiento de más de {PROFUNDIDAD_MAX} niveles")
        elif c in "]}":
            prof -= 1
        elif c in "-0123456789":
            j = i + 1 if c == "-" else i
            while j < n and texto[j] in "0123456789":
                j += 1
            if j - i - (c == "-") > DIGITOS_MAX:
                raise NoCanonico("entero fuera de rango")
            i = j
            continue
        i += 1


def decodificar(datos):
    """Decodificador normativo de la entrada textual (§2.1): bytes UTF-8 estrictos con un único valor JSON.

    En este orden: UTF-8 inválido; profundidad y longitud de los números (antes de convertir nada); claves
    duplicadas, números no enteros (`1.0`, `1e3`), `NaN`/`Infinity` o JSON inválido; y el dominio canónico del valor.
    Todo se rechaza con NoCanonico. Los espacios entre símbolos están permitidos y los escapes `\\uXXXX` equivalen
    al carácter escapado."""
    if not isinstance(datos, (bytes, bytearray)):
        raise TypeError("decodificar recibe bytes (la entrada normativa es binaria)")
    try:
        texto = bytes(datos).decode("utf-8", errors="strict")
    except UnicodeDecodeError as e:
        raise NoCanonico(f"UTF-8 inválido: {e}")
    _explorar_texto(texto)

    def sin_duplicados(pares):
        out = {}
        for k, v in pares:
            if k in out:
                raise NoCanonico(f"clave duplicada {k!r}")
            out[k] = v
        return out

    def no_admitido(x):
        raise NoCanonico(f"número no entero o no finito: {x}")

    try:
        obj = json.loads(texto, object_pairs_hook=sin_duplicados, parse_float=no_admitido,
                         parse_constant=no_admitido)
    except json.JSONDecodeError as e:
        raise NoCanonico(f"JSON inválido: {e}")
    _comprobar(obj)
    return obj


def es_hash(x):
    return isinstance(x, str) and len(x) == 64 and all(c in "0123456789abcdef" for c in x)
