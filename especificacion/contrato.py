"""Contrato de intercambio v2.5: tipos, constructores y validación de forma (ESPECIFICACION.md, §2–§4).

Normativo. Los objetos son diccionarios JSON (canon.py). Este módulo no sabe nada de EFCH: la forma canónica y la
fuente de un objeto le llegan como texto (las produce `efch_formas.py` con `efch.core`) y aquí solo se cuentan, se
comparan y se validan.

La validación es determinista: los campos y las entradas se recorren en orden de clave, y cada valor se comprueba
por tipo antes de usarlo, de modo que un objeto mal formado da siempre el mismo código.
"""

from . import canon

ESQUEMA = "efch-evidencia/2.5"
SEMANTICAS = ("efch-0.1",)

TIPOS_RANURA = ("computacion", "propiedad", "candidata", "candidata-lang")
CANDIDATAS = ("candidata", "candidata-lang")

# Papeles de cada clase y tipos de ranura admitidos en cada papel (§3.1).
PAPELES = {
    "WD": {"objeto": ("computacion",) + CANDIDATAS},
    "EQ": {"nueva": ("computacion",), "anterior": ("computacion",)},
    "PROP": {"propiedad": ("propiedad",)},
    "REAL": {"candidata": CANDIDATAS, "computacion": ("computacion",)},
    "REFUT": {"candidata": CANDIDATAS, "computacion": ("computacion",)},
    "INV": {"objeto": ("computacion",)},
    "CBMC": {"candidata": CANDIDATAS, "computacion": ("computacion",)},
    "TRADUCCION-C": {"objeto": ("computacion",) + CANDIDATAS},
    "RENDIMIENTO": {"objeto": ("computacion",) + CANDIDATAS},
}
CLASES = tuple(PAPELES)
# Papeles que entran en el cierre (§5.1). EQ relaciona dos instantáneas: su cierre es el de la revisión nueva; la
# anterior es un objeto histórico fijado por su id y no tiene que estar vigente.
PAPELES_CIERRE = {c: tuple(sorted(PAPELES[c])) for c in PAPELES}
PAPELES_CIERRE["EQ"] = ("nueva",)
TRANSFERIBLES = ("PROP", "REAL", "REFUT")          # destino de una regla de transferencia (§6)
PRINCIPAL = {"WD": "objeto", "EQ": "nueva", "PROP": "propiedad", "REAL": "candidata", "REFUT": "candidata",
             "INV": "objeto", "CBMC": "candidata", "TRADUCCION-C": "objeto", "RENDIMIENTO": "objeto"}

# Contexto fijo de cada clase (§3.2). No hay hipótesis: una afirmación con cualquier otro contexto es inválida, sea
# conclusión o premisa. El testigo de REFUT no es una hipótesis: es parte de lo que se afirma.
L_OBS = "L-OBS"
CONTEXTO_FIJO = {"WD": {}, "EQ": {"direccion": "d->a"}, "PROP": {"supuestos": [L_OBS]}, "REAL": {}, "INV": {},
                 "CBMC": {}, "TRADUCCION-C": {}, "RENDIMIENTO": {}}       # REFUT: {"testigo": {...}}

# Base de confianza de cada clase (§3.3; decisión del autor D-2, 27/10/2026): los componentes que pueden alterar el
# significado o el resultado de la comprobación. Un cambio en uno de ellos invalida solo las clases que lo incluyen.
_NUCLEO = ("efch-core", "efch-smt", "efch-interp", "z3", "ejecutor", "reglas")
BASE_POR_CLASE = {
    "WD": _NUCLEO, "EQ": _NUCLEO, "PROP": _NUCLEO, "REAL": _NUCLEO, "INV": _NUCLEO,
    "REFUT": ("efch-core", "efch-interp", "ejecutor", "reglas"),
    "CBMC": ("efch-core", "efch-c", "cbmc", "ejecutor", "reglas"),
    "TRADUCCION-C": ("efch-core", "efch-c", "gcc", "abi", "ejecutor", "reglas"),
    "RENDIMIENTO": ("efch-c", "gcc", "abi", "cpu", "workload", "ejecutor", "reglas"),
}
EXTRA_LANG = ("traductor",)                        # si algún sujeto es candidata-lang
EXTRA_REAL_LANG = ("efch-c", "cbmc")               # REAL de candidata-lang: lang.verify recurre a CBMC (D-20)
COMPONENTES = tuple(sorted({c for v in BASE_POR_CLASE.values() for c in v} | set(EXTRA_LANG) | set(EXTRA_REAL_LANG)))

# Estados (§3.4; decisión del autor D-3). Un certificado es reutilizable: solo probado o refutado. El resto de
# resultados (y las mediciones) son registros históricos, que nunca son premisa ni procedencia de un certificado.
ESTADOS_CERTIFICADO = ("probado", "refutado")
ESTADOS_REGISTRO = ("probado", "refutado", "desconocido", "no comprobado", "fuera de alcance", "evidencia experimental")
ESTADOS_POR_CLASE = {"WD": ESTADOS_CERTIFICADO, "EQ": ESTADOS_CERTIFICADO, "PROP": ESTADOS_CERTIFICADO,
                     "REAL": ("probado",), "REFUT": ("probado",), "INV": ESTADOS_CERTIFICADO,
                     "CBMC": ESTADOS_CERTIFICADO, "TRADUCCION-C": ESTADOS_CERTIFICADO,
                     "RENDIMIENTO": ("probado",)}
VIA_REGLA = {"directa": ("directa",), "conservada": ("conservacion",), "cache": ("conservacion",),
             "transferida": ("R-PROP", "R-REAL", "R-REFUT")}
REGLAS = ("directa", "conservacion", "R-PROP", "R-REAL", "R-REFUT")
VIAS_REGISTRO = ("directa", "conservada-operativa")

CAMPOS = {
    "ranura": ("esquema", "tipo", "ambito", "nombre", "id"),
    "revision": ("esquema", "semantica", "ranura", "contenido", "forma_canonica", "fuente", "forma_fuente", "firma",
                 "dependencias", "id"),
    "instantanea": ("esquema", "semantica", "revisiones", "base", "id"),
    "afirmacion": ("esquema", "semantica", "clase", "sujetos", "contexto", "id"),
    "certificado": ("esquema", "semantica", "afirmacion", "estado", "via", "regla", "instantanea", "base", "cierre",
                    "objeto_verificado", "premisas", "procedencia", "id"),
    "registro": ("esquema", "semantica", "afirmacion", "resultado", "via", "instantanea", "origen", "mediciones",
                 "id"),
}
# Tipo JSON de cada campo (§4, paso 5): "texto", "hash", "objeto", "hash?" (hash o null), "ambito" (hash o "").
_COMUNES = {"esquema": "texto", "semantica": "texto", "id": "hash"}
TIPOS_CAMPO = {
    "ranura": {"esquema": "texto", "id": "hash", "tipo": "texto", "ambito": "ambito", "nombre": "texto"},
    "revision": {**_COMUNES, "ranura": "hash", "contenido": "hash", "forma_canonica": "texto", "fuente": "texto",
                 "forma_fuente": "hash", "firma": "texto", "dependencias": "objeto"},
    "instantanea": {**_COMUNES, "revisiones": "objeto", "base": "objeto"},
    "afirmacion": {**_COMUNES, "clase": "texto", "sujetos": "objeto", "contexto": "objeto"},
    "certificado": {**_COMUNES, "afirmacion": "hash", "estado": "texto", "via": "texto", "regla": "texto",
                    "instantanea": "hash", "base": "objeto", "cierre": "objeto", "objeto_verificado": "hash?",
                    "premisas": "objeto", "procedencia": "hash?"},
    "registro": {**_COMUNES, "afirmacion": "hash", "resultado": "texto", "via": "texto", "instantanea": "hash",
                 "origen": "hash?", "mediciones": "objeto"},
}
EXCLUIDOS = {"registro": ("id", "mediciones")}      # las mediciones no entran en el hash, pero se validan (§2.1)
TABLAS = {"ranuras": "ranura", "revisiones": "revision", "instantaneas": "instantanea",
          "afirmaciones": "afirmacion", "certificados": "certificado", "registros": "registro"}


class Rechazo(Exception):
    """Rechazo con código normativo (ESPECIFICACION.md, §7) y ruta del objeto que lo causa."""

    def __init__(self, codigo, ruta="", detalle=""):
        super().__init__(f"{codigo} en {ruta}: {detalle}" if detalle else f"{codigo} en {ruta}")
        self.codigo, self.ruta, self.detalle = codigo, ruta, detalle


# --- constructores ---------------------------------------------------------------------------------------------

def ranura(tipo, nombre, ambito=""):
    return canon.con_id({"esquema": ESQUEMA, "tipo": tipo, "ambito": ambito, "nombre": nombre})


def revision(ranura_, forma_canonica, fuente, firma, dependencias, semantica="efch-0.1"):
    """`dependencias`: {id de ranura: id de revisión} del cierre transitivo de la expansión (sin la propia)."""
    return canon.con_id({"esquema": ESQUEMA, "semantica": semantica, "ranura": ranura_["id"],
                         "contenido": canon.sha(forma_canonica), "forma_canonica": forma_canonica,
                         "fuente": fuente, "forma_fuente": canon.sha(fuente), "firma": firma,
                         "dependencias": dict(dependencias)})


def instantanea(revisiones, base, semantica="efch-0.1"):
    """`revisiones`: lista de revisiones; se guarda {id de ranura: id de revisión}. Una ranura con dos revisiones
    distintas no cabe en una instantánea (v2.7, §2.2): se rechaza en vez de quedarse con una."""
    m = {}
    for r in revisiones:
        if m.setdefault(r["ranura"], r["id"]) != r["id"]:
            raise ValueError(f"instantánea con dos revisiones de la ranura {r['ranura'][:12]}")
    return canon.con_id({"esquema": ESQUEMA, "semantica": semantica, "revisiones": m, "base": dict(base)})


def afirmacion(clase, contexto=None, semantica="efch-0.1", **sujetos):
    ctx = CONTEXTO_FIJO.get(clase, {}) if contexto is None else contexto
    return canon.con_id({"esquema": ESQUEMA, "semantica": semantica, "clase": clase,
                         "sujetos": {p: r["id"] for p, r in sujetos.items()}, "contexto": ctx})


def certificado(af, estado, via, regla, inst, base, cierre, objeto_verificado=None, premisas=None,
                procedencia=None):
    return canon.con_id({"esquema": ESQUEMA, "semantica": af["semantica"], "afirmacion": af["id"],
                         "estado": estado, "via": via, "regla": regla, "instantanea": inst["id"],
                         "base": dict(base), "cierre": dict(cierre), "objeto_verificado": objeto_verificado,
                         "premisas": {p: c["id"] for p, c in (premisas or {}).items()},
                         "procedencia": procedencia["id"] if procedencia else None})


def registro(af, resultado, via, inst, origen=None, mediciones=None):
    return canon.con_id({"esquema": ESQUEMA, "semantica": af["semantica"], "afirmacion": af["id"],
                         "resultado": resultado, "via": via, "instantanea": inst["id"],
                         "origen": origen["id"] if origen else None, "mediciones": dict(mediciones or {})},
                        EXCLUIDOS["registro"])


def paquete(ranuras=(), revisiones=(), instantaneas=(), afirmaciones=(), certificados=(), registros=()):
    """Paquete de intercambio: todos los objetos de un paso, indexados por id (§2.3)."""
    return {"esquema": ESQUEMA,
            "ranuras": {x["id"]: x for x in ranuras}, "revisiones": {x["id"]: x for x in revisiones},
            "instantaneas": {x["id"]: x for x in instantaneas}, "afirmaciones": {x["id"]: x for x in afirmaciones},
            "certificados": {x["id"]: x for x in certificados}, "registros": {x["id"]: x for x in registros}}


# --- validación de forma (§4) ----------------------------------------------------------------------------------

def _es(x, tipo, ruta, campo):
    if tipo is dict and not isinstance(x, dict):
        raise Rechazo("tipo_invalido", ruta, f"{campo} no es un objeto")
    if tipo is str and not isinstance(x, str):
        raise Rechazo("tipo_invalido", ruta, f"{campo} no es texto")
    return x


def _hash(x, ruta, campo):
    if not canon.es_hash(x):
        raise Rechazo("tipo_invalido", ruta, f"{campo} no es un hash")


def _mapa_hashes(x, ruta, campo):
    _es(x, dict, ruta, campo)
    for k in sorted(x):
        _hash(k, ruta, f"{campo} (clave)")
        _hash(x[k], ruta, f"{campo}.{k[:12]}")


def _tipo_ok(x, t):
    if t == "texto":
        return isinstance(x, str)
    if t == "hash":
        return canon.es_hash(x)
    if t == "hash?":
        return x is None or canon.es_hash(x)
    if t == "ambito":
        return x == "" or canon.es_hash(x)
    return isinstance(x, dict)


def _campos(tipo, obj, ruta):
    """Pasos 1–8 de la precedencia normativa (§4): objeto, esquema, ausentes, sobrantes, tipo de cada campo en
    orden alfabético, semántica, canonicidad y hash. Lo específico de cada objeto viene después."""
    if not isinstance(obj, dict):
        raise Rechazo("tipo_invalido", ruta, "no es un objeto")
    esperados = set(CAMPOS[tipo])
    if obj.get("esquema") != ESQUEMA:
        raise Rechazo("esquema_desconocido", ruta, repr(obj.get("esquema")) if isinstance(obj.get("esquema"), str)
                      else "esquema no textual")
    falta = esperados - set(obj)
    if falta:
        raise Rechazo("campo_ausente", ruta, ", ".join(sorted(falta)))
    sobra = set(obj) - esperados
    if sobra:
        raise Rechazo("campo_desconocido", ruta, ", ".join(sorted(sobra)))
    for campo in sorted(TIPOS_CAMPO[tipo]):
        if not _tipo_ok(obj[campo], TIPOS_CAMPO[tipo][campo]):
            raise Rechazo("tipo_invalido", ruta, f"{campo}: se esperaba {TIPOS_CAMPO[tipo][campo]}")
    if "semantica" in esperados and obj["semantica"] not in SEMANTICAS:
        raise Rechazo("semantica_desconocida", ruta, repr(obj["semantica"]))
    try:
        canon.canonico(obj)                          # todo el objeto, también lo excluido del hash
        h = canon.hash_objeto(obj, EXCLUIDOS.get(tipo, ("id",)))
    except canon.NoCanonico as e:
        raise Rechazo("no_canonico", ruta, str(e))
    if obj["id"] != h:
        raise Rechazo("hash_invalido", ruta, f"id {obj['id']!r}, calculado {h}")


def validar_ranura(r, ruta="ranura"):
    _campos("ranura", r, ruta)
    if r["tipo"] not in TIPOS_RANURA:
        raise Rechazo("tipo_invalido", ruta, f"tipo de ranura {r['tipo']!r}")
    if not _es(r["nombre"], str, ruta, "nombre"):
        raise Rechazo("tipo_invalido", ruta, "nombre vacío")
    if r["tipo"] in CANDIDATAS:
        _hash(r["ambito"], ruta, "ambito")          # la ranura de la computación que implementa
    elif r["ambito"] != "":
        raise Rechazo("tipo_invalido", ruta, "solo una candidata tiene ámbito")


def validar_revision(v, ruta="revision"):
    _campos("revision", v, ruta)
    _hash(v["ranura"], ruta, "ranura")
    _es(v["forma_canonica"], str, ruta, "forma_canonica")
    _es(v["fuente"], str, ruta, "fuente")
    _es(v["firma"], str, ruta, "firma")
    if v["contenido"] != canon.sha(v["forma_canonica"]):
        raise Rechazo("contenido_invalido", ruta, "contenido ≠ sha256(forma_canonica)")
    if v["forma_fuente"] != canon.sha(v["fuente"]):
        raise Rechazo("fuente_invalida", ruta, "forma_fuente ≠ sha256(fuente)")
    _mapa_hashes(v["dependencias"], ruta, "dependencias")
    if v["ranura"] in v["dependencias"]:
        raise Rechazo("tipo_invalido", ruta, "una revisión no depende de su propia ranura")


def validar_instantanea(s, ruta="instantanea"):
    _campos("instantanea", s, ruta)
    _mapa_hashes(s["revisiones"], ruta, "revisiones")
    _es(s["base"], dict, ruta, "base")
    for k in sorted(s["base"]):
        if k not in COMPONENTES:
            raise Rechazo("componente_desconocido", ruta, k)
        _es(s["base"][k], str, ruta, f"base.{k}")


def validar_afirmacion(a, ruta="afirmacion", exigir_contexto=True):
    """Forma de la afirmación, sin resolver sus sujetos (eso lo hace reglas.Validador).

    `exigir_contexto=False` solo lo usa la exploración (exploracion.py) para demostrar que la regla es necesaria."""
    _campos("afirmacion", a, ruta)
    if a["clase"] not in CLASES:
        raise Rechazo("clase_desconocida", ruta, repr(a["clase"]))
    _es(a["sujetos"], dict, ruta, "sujetos")
    if set(a["sujetos"]) != set(PAPELES[a["clase"]]):
        raise Rechazo("papel_invalido", ruta, f"papeles {sorted(a['sujetos'])}")
    for p in sorted(a["sujetos"]):
        _hash(a["sujetos"][p], ruta, f"sujetos.{p}")
    _es(a["contexto"], dict, ruta, "contexto")
    if not exigir_contexto:
        return
    if a["clase"] == "REFUT":
        ctx = a["contexto"]
        if set(ctx) != {"testigo"} or not isinstance(ctx["testigo"], dict):
            raise Rechazo("contexto_no_fijo", ruta, "REFUT exige exactamente {testigo: {...}}")
        for k in sorted(ctx["testigo"]):
            if not valor_entrada(ctx["testigo"][k]):
                raise Rechazo("tipo_invalido", ruta, f"testigo.{k}")
    elif a["contexto"] != CONTEXTO_FIJO[a["clase"]]:
        raise Rechazo("contexto_no_fijo", ruta, f"{a['clase']}: {a['contexto']!r}")


def valor_entrada(x):
    """Valor de una entrada de EFCH 0.1 en JSON (§3.2): booleano, entero no negativo (bv) o lista de bytes."""
    if isinstance(x, bool):
        return True
    if isinstance(x, int):
        return x >= 0
    return isinstance(x, list) and all(isinstance(b, int) and not isinstance(b, bool) and 0 <= b < 256 for b in x)


def validar_certificado(c, ruta="certificado"):
    """Forma del certificado, sin resolver referencias."""
    _campos("certificado", c, ruta)
    _hash(c["afirmacion"], ruta, "afirmacion")
    _hash(c["instantanea"], ruta, "instantanea")
    if c["estado"] not in ESTADOS_CERTIFICADO:
        raise Rechazo("estado_no_reutilizable", ruta, repr(c["estado"]))
    if c["via"] not in VIA_REGLA or c["regla"] not in VIA_REGLA[c["via"]]:
        raise Rechazo("via_regla_incompatible", ruta, f"{c['via']!r}/{c['regla']!r}")
    _es(c["base"], dict, ruta, "base")
    for k in sorted(c["base"]):
        if k not in COMPONENTES:
            raise Rechazo("componente_desconocido", ruta, k)
        _es(c["base"][k], str, ruta, f"base.{k}")
    _mapa_hashes(c["cierre"], ruta, "cierre")
    _es(c["premisas"], dict, ruta, "premisas")
    for p in sorted(c["premisas"]):
        _hash(c["premisas"][p], ruta, f"premisas.{p}")
    if c["regla"] == "directa":
        _hash(c["objeto_verificado"], ruta, "objeto_verificado")
        if c["premisas"] or c["procedencia"] is not None:
            raise Rechazo("premisa_sobrante", ruta, "una evidencia directa no tiene premisas ni procedencia")
    else:
        if c["objeto_verificado"] is not None:
            raise Rechazo("objeto_verificado_distinto", ruta, "solo una evidencia directa declara objeto verificado")
        _hash(c["procedencia"], ruta, "procedencia")
        if c["regla"] == "conservacion" and c["premisas"]:
            raise Rechazo("premisa_sobrante", ruta, "la conservación no tiene premisas, solo procedencia")
        if c["regla"] != "conservacion" and c["procedencia"] != c["premisas"].get("origen"):
            raise Rechazo("procedencia_invalida", ruta, "la procedencia de una transferencia es su premisa origen")


def validar_registro(r, ruta="registro"):
    _campos("registro", r, ruta)
    _hash(r["afirmacion"], ruta, "afirmacion")
    _hash(r["instantanea"], ruta, "instantanea")
    if r["resultado"] not in ESTADOS_REGISTRO:
        raise Rechazo("tipo_invalido", ruta, f"resultado {r['resultado']!r}")
    if r["via"] not in VIAS_REGISTRO:
        raise Rechazo("tipo_invalido", ruta, f"vía {r['via']!r}")
    if (r["via"] == "directa") != (r["origen"] is None):
        raise Rechazo("procedencia_invalida", ruta, "un registro conservado declara su origen; uno directo no")
    if r["origen"] is not None:
        _hash(r["origen"], ruta, "origen")
    _es(r["mediciones"], dict, ruta, "mediciones")
    for k in sorted(r["mediciones"]):
        x = r["mediciones"][k]
        if not (x is None or isinstance(x, (str, bool, int))):
            raise Rechazo("tipo_invalido", ruta, f"mediciones.{k}: solo texto, entero, booleano o null")


def validar_paquete(p, ruta="paquete"):
    """Forma del paquete (§2.3). Los objetos se validan al usarlos (reglas.Validador)."""
    if not isinstance(p, dict):
        raise Rechazo("tipo_invalido", ruta, "no es un objeto")
    if p.get("esquema") != ESQUEMA:
        raise Rechazo("esquema_desconocido", ruta, repr(p.get("esquema")))
    esperados = {"esquema", *TABLAS}
    if esperados - set(p):
        raise Rechazo("campo_ausente", ruta, ", ".join(sorted(esperados - set(p))))
    if set(p) - esperados:
        raise Rechazo("campo_desconocido", ruta, ", ".join(sorted(set(p) - esperados)))
    for t in sorted(TABLAS):
        _es(p[t], dict, ruta, t)
        for k in sorted(p[t]):
            _hash(k, ruta, f"{t} (índice)")
