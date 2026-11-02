"""Vectores de referencia del contrato v2.3 (ESPECIFICACION.md, §10).

    python3 -m especificacion.vectores --salida especificacion/vectores      # regenera (determinista)
    python3 -m especificacion.vectores --comprobar especificacion/vectores   # comprueba contra reglas.py

Cada vector es un paquete de intercambio (§2.3) —o su texto, en `entrada_b64`, para la decodificación de §2.1—, una
comprobación (`validar` un certificado o `reutilizable` en una
instantánea) y el resultado esperado: válido o el código de rechazo. `canonicos.json` da, para cada objeto del
escenario base, sus bytes canónicos y su id: otra implementación tiene que producirlos idénticos.

Escenario base (formas de `efch_formas.py`, es decir, de `efch.core`):
- S_a: `f- = 0`, `h = 0`, `g = f-(x)`, `k2 = g(f-(x))` (llamada en argumento), `p: ∀x. g(x) = 0`,
  `q: ∀x. k2(x) = f-(x)` (varias llamadas), `r: ∀x. g(x) = 1` (refutada); candidatas `c = 0`, `ch = h(x)`,
  `c1 = 1`.
- S_d: igual, con `f- = (add 0 0)` y `h = 1`.
- S_e: igual que S_d, con `f- = (add (add 0 0) 0)` (tres versiones: cadenas largas y EQ no consecutivas).
"""

import argparse
import copy
import json
import pathlib

from . import canon
from . import contrato as k
from .efch_formas import Formas
from .reglas import Validador
from .contrato import Rechazo

BASE = {c: "v1" for c in k.COMPONENTES}

DEF = """(efch 0.1
  (computation f- (input x (bv 8)) (output (bv 8)) (semantics {f}))
  (computation h (input x (bv 8)) (output (bv 8)) (semantics {h}))
  (computation g (input x (bv 8)) (output (bv 8)) (semantics {g}))
  (computation k2 (input x (bv 8)) (output (bv 8)) (semantics (call g (call f- x))))
  (property p (forall ((x (bv 8))) {p}))
  (property q (forall ((x (bv 8))) (eq (call k2 x) (call f- x))))
  (property r (forall ((x (bv 8))) (eq (call g x) 1))))"""
CANDS = """(efch 0.1 (candidate c (implements f-) (body 0)) (candidate ch (implements f-) (body (call h x)))
  (candidate c1 (implements f-) (body 1)))"""
VERSIONES = {
    "a": {"f": "0", "h": "0", "g": "(call f- x)", "p": "(eq (call g x) 0)"},
    "d": {"f": "(add 0 0)", "h": "1", "g": "(call f- x)", "p": "(eq (call g x) 0)"},
    "e": {"f": "(add (add 0 0) 0)", "h": "1", "g": "(call f- x)", "p": "(eq (call g x) 0)"},
    "fuente": {"f": "(add 0 0)", "h": "1", "g": "(call f- x)", "p": "(eq 0 (call g x))"},   # otra fuente de p
    "g_h": {"f": "(add 0 0)", "h": "1", "g": "(add (call f- x) (call h x))", "p": "(eq (call g x) 0)"},
}


def por_nombre(f):
    """{nombre: revisión} de una elaboración cuyos nombres no se repiten entre ranuras (los mundos de estos
    vectores). La identidad es la ranura (§2.2): con nombres repetidos, falla en vez de elegir una."""
    out = {}
    for rid, v in f.revisiones.items():
        n = f.ranuras[rid]["nombre"]
        if n in out:
            raise ValueError(f"nombre repetido entre ranuras: {n}")
        out[n] = v
    return out


def _definicion(v):
    from efch import core
    d = core.load_definition(DEF.format(**VERSIONES[v]))
    return d, core.load_candidates(CANDS, d)


class Escenario:
    """Las instantáneas de VERSIONES con sus revisiones, más un almacén de afirmaciones y certificados."""

    def __init__(self, versiones=("a", "d", "e")):
        self.rev, self.S, self.ranuras = {}, {}, {}
        self.extra_rev, self.extra_S = {}, {}
        self.afs, self.certs, self.regs = {}, {}, {}
        for v in versiones:
            d, cands = _definicion(v)
            f = Formas(d).todas(cands)
            self.rev[v] = por_nombre(f)
            for r in f.ranuras.values():
                self.ranuras[r["id"]] = r
            self.S[v] = k.instantanea(f.revisiones.values(), BASE)

    def R(self, nombre):
        [r] = [r for r in self.ranuras.values() if r["nombre"] == nombre]      # nombres sin repetir (§2.2)
        return r

    def _todas(self):
        out = {x["id"]: x for r in self.rev.values() for x in r.values()}
        out.update(self.extra_rev)
        return out

    def af(self, clase, contexto=None, **suj):
        a = k.afirmacion(clase, contexto, **suj)
        self.afs[a["id"]] = a
        return a

    def cierre(self, a):
        revs, out = self._todas(), {}
        for papel in k.PAPELES_CIERRE[a["clase"]]:
            v = revs[a["sujetos"][papel]]
            out[v["ranura"]] = v["id"]
            out.update(v["dependencias"])
        return out

    def base(self, a, S):
        comps = set(k.BASE_POR_CLASE[a["clase"]])
        revs = self._todas()
        if any(self.ranuras[revs[r]["ranura"]]["tipo"] == "candidata-lang" for r in a["sujetos"].values()):
            comps |= set(k.EXTRA_LANG) | (set(k.EXTRA_REAL_LANG) if a["clase"] == "REAL" else set())
        return {c: S["base"][c] for c in sorted(comps)}

    def cert(self, a, estado, via, regla, S, premisas=None, procedencia=None):
        S = self.S[S] if isinstance(S, str) else S
        ov = self._todas()[a["sujetos"][k.PRINCIPAL[a["clase"]]]]["contenido"] if regla == "directa" else None
        c = k.certificado(a, estado, via, regla, S, self.base(a, S), self.cierre(a), ov, premisas, procedencia)
        self.certs[c["id"]] = c
        return c

    def directa(self, clase, v, estado="probado", contexto=None, **suj):
        return self.cert(self.af(clase, contexto, **suj), estado, "directa", "directa", v)

    def paquete(self):
        S = list(self.S.values()) + list(self.extra_S.values())
        return k.paquete(self.ranuras.values(), self._todas().values(), S, self.afs.values(), self.certs.values(),
                         self.regs.values())


def r_prop(e, origen, va, vd, estado="probado"):
    """R-PROP honesta de PROP(p_va) a PROP(p_vd), con EQ, WD_a y WD_d de cada computación cambiada del cierre."""
    a, d = e.rev[va], e.rev[vd]
    prem = {"origen": origen}
    for n in ("f-", "g", "h", "k2"):
        rid = e.R(n)["id"]
        if a[n]["id"] != d[n]["id"] and rid in origen["cierre"]:
            prem[f"eq:{rid}"] = e.directa("EQ", vd, nueva=d[n], anterior=a[n])
            prem[f"wd_a:{rid}"] = e.directa("WD", va, objeto=a[n])
            prem[f"wd_d:{rid}"] = e.directa("WD", vd, objeto=d[n])
    pa = e._todas()[e.afs[origen["afirmacion"]]["sujetos"]["propiedad"]]
    pd = next(r for r in d.values() if r["ranura"] == pa["ranura"])
    return e.cert(e.af("PROP", propiedad=pd), estado, "transferida", "R-PROP", vd, prem, origen)


def escenario_base():
    e = Escenario()
    a, d = e.rev["a"], e.rev["d"]
    C = {}
    C["wd_a_f"] = e.directa("WD", "a", objeto=a["f-"])
    C["eq_f"] = e.directa("EQ", "d", nueva=d["f-"], anterior=a["f-"])
    C["wd_c"] = e.directa("WD", "d", objeto=d["c"])
    C["prop_a"] = e.directa("PROP", "a", propiedad=a["p"])
    C["r_prop"] = r_prop(e, C["prop_a"], "a", "d")
    C["conservada"] = e.cert(e.afs[C["r_prop"]["afirmacion"]], "probado", "cache", "conservacion", "d",
                             procedencia=C["r_prop"])
    C["r_prop_e"] = r_prop(e, C["conservada"], "d", "e")          # cadena: R-PROP → caché → R-PROP
    C["r_prop_ae"] = r_prop(e, C["prop_a"], "a", "e")             # EQ no consecutiva (S_a → S_e)
    C["prop_r_a"] = e.directa("PROP", "a", "refutado", propiedad=a["r"])
    C["r_prop_refutada"] = r_prop(e, C["prop_r_a"], "a", "d", "refutado")
    C["prop_q_a"] = e.directa("PROP", "a", propiedad=a["q"])      # varias llamadas y llamada en argumento
    C["r_prop_q"] = r_prop(e, C["prop_q_a"], "a", "d")
    C["real_a"] = e.directa("REAL", "a", candidata=a["c"], computacion=a["f-"])
    C["r_real"] = e.cert(e.af("REAL", candidata=d["c"], computacion=d["f-"]), "probado", "transferida", "R-REAL",
                         "d", {"origen": C["real_a"], "eq": C["eq_f"], "wd_a": C["wd_a_f"], "wd_c": C["wd_c"]},
                         C["real_a"])
    t = {"testigo": {"x": 0}}
    C["refut_a"] = e.directa("REFUT", "a", contexto=t, candidata=a["c1"], computacion=a["f-"])
    C["evaluacion"] = e.directa("REFUT", "d", contexto=t, candidata=d["c1"], computacion=d["f-"])
    af_ev = e.afs[C["evaluacion"]["afirmacion"]]
    C["r_refut"] = e.cert(af_ev, "probado", "transferida", "R-REFUT", "d",
                          {"origen": C["refut_a"], "evaluacion": C["evaluacion"]}, C["refut_a"])
    C["r_refut_eq"] = e.cert(af_ev, "probado", "transferida", "R-REFUT", "d",
                             {"origen": C["refut_a"], "evaluacion": C["evaluacion"], "eq": C["eq_f"]}, C["refut_a"])
    C["inv"] = e.directa("INV", "a", objeto=a["k2"])
    C["cbmc"] = e.directa("CBMC", "a", candidata=a["c"], computacion=a["f-"])
    C["tradc"] = e.directa("TRADUCCION-C", "a", objeto=a["c"])
    C["rend"] = e.directa("RENDIMIENTO", "a", objeto=a["c"])
    # Testigos de otros tipos de valor: la conformidad con la firma la garantiza la hoja (§3.2).
    C["refut_vacio"] = e.directa("REFUT", "a", contexto={"testigo": {}}, candidata=a["c1"], computacion=a["f-"])
    C["refut_bytes"] = e.directa("REFUT", "a", contexto={"testigo": {"x": [1, 255]}}, candidata=a["c1"],
                                 computacion=a["f-"])
    af_inv = e.af("INV", objeto=a["g"])
    reg = k.registro(af_inv, "desconocido", "directa", e.S["a"], mediciones={"cpu_s": "0.25", "presupuesto_s": 30})
    reg2 = k.registro(af_inv, "desconocido", "conservada-operativa", e.S["d"], origen=reg)
    e.regs[reg["id"]], e.regs[reg2["id"]] = reg, reg2
    C["registro"] = reg
    return e, C


def escenario_z3():
    """S_a y S_z: mismas revisiones, otra Z3 (relevante para WD; irrelevante para RENDIMIENTO)."""
    e = Escenario(("a",))
    a = e.rev["a"]
    Sz = k.instantanea(a.values(), {**BASE, "z3": "v2"})
    e.extra_S["z"] = Sz
    rend = e.directa("RENDIMIENTO", "a", objeto=a["c"])
    wd = e.directa("WD", "a", objeto=a["f-"])
    cons_rend = e.cert(e.afs[rend["afirmacion"]], "probado", "conservada", "conservacion", Sz, procedencia=rend)
    cons_wd = e.cert(e.afs[wd["afirmacion"]], "probado", "conservada", "conservacion", Sz, procedencia=wd)
    return e, {"wd": wd, "cons_rend": cons_rend, "cons_wd": cons_wd, "Sz": Sz}


def escenario_lang():
    """REAL de una candidata de EFCH Lang (varint): su base añade traductor, efch-c y cbmc (D-20)."""
    from efch import core, lang
    raiz = pathlib.Path(__file__).resolve().parents[1]
    spec = core.load_definition((raiz / "ejemplos/varint.efch").read_text())
    texto = lang.candidates_text((raiz / "ejemplos/lang/varint.efl").read_text(), spec, "varint.efl")
    [cand] = core.load_candidates(texto, spec)
    f = Formas(spec)
    comp = f.computacion(cand.implements)
    cl = f.candidata(cand, "candidata-lang")
    e = Escenario(())
    for r in f.ranuras.values():
        e.ranuras[r["id"]] = r
    e.extra_rev = {x["id"]: x for x in f.revisiones.values()}
    S = k.instantanea(f.revisiones.values(), BASE)
    S_sin = k.instantanea(f.revisiones.values(), {x: v for x, v in BASE.items() if x != "cbmc"})
    e.extra_S = {"l": S, "sin": S_sin}
    real = e.cert(e.af("REAL", candidata=cl, computacion=comp), "probado", "directa", "directa", S)
    return e, {"real": real, "S_sin": S_sin}


def _real_ch():
    e = Escenario(("a", "d"))
    a, d = e.rev["a"], e.rev["d"]
    o = e.directa("REAL", "a", candidata=a["ch"], computacion=a["f-"])
    prem = {"origen": o, "eq": e.directa("EQ", "d", nueva=d["f-"], anterior=a["f-"]),
            "wd_a": e.directa("WD", "a", objeto=a["f-"]), "wd_c": e.directa("WD", "d", objeto=d["ch"])}
    r = e.cert(e.af("REAL", candidata=d["ch"], computacion=d["f-"]), "probado", "transferida", "R-REAL", "d", prem, o)
    return e.paquete(), r["id"]


def _vector(nombre, descripcion, paquete, cert, esperado, instantanea=None):
    comp = {"tipo": "reutilizable" if instantanea else "validar", "certificado": cert}
    if instantanea:
        comp["instantanea"] = instantanea
    return {"nombre": nombre, "descripcion": descripcion, "paquete": paquete, "comprobacion": comp,
            "esperado": esperado}


def vectores():
    e, C = escenario_base()
    P = e.paquete()
    a, d = e.rev["a"], e.rev["d"]
    rf = e.R("f-")["id"]
    V = []
    ok = {"valido": True}
    for n in ("wd_a_f", "eq_f", "prop_a", "r_prop", "conservada", "r_prop_e", "r_prop_ae", "r_prop_refutada",
              "r_prop_q", "real_a", "r_real", "r_refut", "r_refut_eq", "inv", "cbmc", "tradc", "rend",
              "refut_vacio", "refut_bytes"):
        V.append(_vector(f"valido-{n}", f"certificado {n} del escenario base", P, C[n]["id"], ok))
    V.append(_vector("valido-reutilizable-r_prop", "la propiedad transferida es reutilizable en S_d", P,
                     C["r_prop"]["id"], ok, e.S["d"]["id"]))
    V.append(_vector("rechazo-d8-vigencia", "PROP(p_a) no es reutilizable en S_d: f- cambió (D8)", P,
                     C["prop_a"]["id"], {"rechazo": "no_vigente"}, e.S["d"]["id"]))
    V.append(_vector("rechazo-d8-transitiva", "PROP(q_a) no es reutilizable en S_d: q llama a k2, que llama a g, "
                     "que llama a f- (D8)", P, C["prop_q_a"]["id"], {"rechazo": "no_vigente"}, e.S["d"]["id"]))

    ez, Z = escenario_z3()
    PZ = ez.paquete()
    V.append(_vector("valido-base-irrelevante", "RENDIMIENTO se conserva aunque cambie Z3 (no está en su base)", PZ,
                     Z["cons_rend"]["id"], ok))
    V.append(_vector("rechazo-base-relevante", "WD no se conserva si cambia Z3 (D-2)", PZ, Z["cons_wd"]["id"],
                     {"rechazo": "base_distinta"}))
    V.append(_vector("rechazo-no-vigente-base", "WD de S_a no es reutilizable en S_z (otra Z3)", PZ, Z["wd"]["id"],
                     {"rechazo": "no_vigente"}, Z["Sz"]["id"]))
    el, L = escenario_lang()
    PL = el.paquete()
    V.append(_vector("valido-lang-real", "REAL de una candidata de EFCH Lang con traductor, efch-c y cbmc", PL,
                     L["real"]["id"], ok))
    pch, cch = _real_ch()
    V.append(_vector("rechazo-candidata", "R-REAL con la candidata ch, que cambió al cambiar h (D9)", pch, cch,
                     {"rechazo": "candidata_distinta"}))
    for vd, codigo, desc in (("fuente", "fuente_distinta", "R-PROP hacia una p con otra fuente"),
                             ("g_h", "ranura_nueva", "R-PROP cuando g pasa a llamar a h: el cierre gana una ranura")):
        ex = Escenario(("a", vd))
        c = r_prop(ex, ex.directa("PROP", "a", propiedad=ex.rev["a"]["p"]), "a", vd)
        V.append(_vector(f"rechazo-{codigo.replace('_', '-')}", desc, ex.paquete(), c["id"], {"rechazo": codigo}))

    def mal(nombre, descripcion, codigo, mutar, objetivo="r_prop", base=None):
        p = copy.deepcopy(base or P)
        cid = mutar(p) or C[objetivo]["id"]
        V.append(_vector(f"rechazo-{nombre}", descripcion, p, cid, {"rechazo": codigo}))

    def nuevo(p, tabla, base_obj, **cambios):
        x = canon.con_id({**base_obj, **cambios})
        p[tabla][x["id"]] = x
        return x

    def cert(p, base_cert, **cambios):
        return nuevo(p, "certificados", base_cert, **cambios)

    def af_de(c):
        return e.afs[c["afirmacion"]]

    def con_af(p, c, **cambios_af):
        return cert(p, c, afirmacion=nuevo(p, "afirmaciones", af_de(c), **cambios_af)["id"])["id"]

    def sin_firmar(p, c):               # objeto añadido tal cual (sin recalcular el id)
        p["certificados"][c["id"]] = c
        return c["id"]

    def lang_sin_cbmc(p):
        return cert(p, L["real"], instantanea=L["S_sin"]["id"],
                    base={x: v for x, v in L["real"]["base"].items() if x != "cbmc"})["id"]
    mal("base-incompleta", "la instantánea no identifica cbmc, que la REAL de Lang necesita", "base_incompleta",
        lang_sin_cbmc, base=PL)
    # --- forma, hashes y serialización (§2, §4) ---
    mal("hash", "campo alterado sin recalcular el id", "hash_invalido",
        lambda p: p["certificados"][C["wd_a_f"]["id"]].update(estado="refutado"), "wd_a_f")
    mal("esquema", "esquema del borrador anterior", "esquema_desconocido",
        lambda p: cert(p, C["wd_a_f"], esquema="efch-evidencia/2.1")["id"])
    mal("campo-desconocido", "campo no previsto en el certificado", "campo_desconocido",
        lambda p: cert(p, C["wd_a_f"], coste=1)["id"])
    mal("paquete-campo", "clave no prevista en el paquete", "campo_desconocido", lambda p: p.__setitem__("extra", {}))
    mal("campo-ausente", "falta un campo", "campo_ausente",
        lambda p: sin_firmar(p, canon.con_id({x: v for x, v in C["wd_a_f"].items() if x != "cierre"})))
    mal("semantica", "semántica desconocida", "semantica_desconocida",
        lambda p: cert(p, C["wd_a_f"], semantica="efch-0.2")["id"])
    mal("tipo", "premisas que no son un objeto", "tipo_invalido",
        lambda p: sin_firmar(p, canon.con_id({**C["r_prop"], "premisas": ["origen"]})))

    def entero_grande(p):              # un testigo fuera de [-2^63, 2^128): no se puede ni calcular el hash
        a_ = {**af_de(C["refut_a"]), "contexto": {"testigo": {"x": 2 ** 128}}, "id": "0" * 64}
        p["afirmaciones"][a_["id"]] = a_
        return cert(p, C["refut_a"], afirmacion=a_["id"])["id"]
    mal("no-canonico", "entero fuera de rango en un testigo", "no_canonico", entero_grande)
    mal("estado-desconocido", "un desconocido no es un certificado reutilizable (D-3)", "estado_no_reutilizable",
        lambda p: cert(p, C["wd_a_f"], estado="desconocido")["id"])
    mal("estado-clase", "REAL refutado: se expresa con REFUT", "estado_invalido",
        lambda p: cert(p, C["real_a"], estado="refutado")["id"])
    mal("via-regla", "vía y regla incompatibles", "via_regla_incompatible",
        lambda p: cert(p, C["wd_a_f"], via="cache")["id"])
    mal("directa-premisas", "una hoja directa con premisas", "premisa_sobrante",
        lambda p: cert(p, C["wd_a_f"], premisas={"x": C["eq_f"]["id"]})["id"])
    mal("objeto-en-derivada", "objeto verificado en una conservación", "objeto_verificado_distinto",
        lambda p: cert(p, C["conservada"], objeto_verificado=d["p"]["contenido"])["id"])
    mal("contenido", "contenido ≠ sha256(forma_canonica)", "contenido_invalido",
        lambda p: con_af(p, C["wd_a_f"], sujetos={"objeto": nuevo(p, "revisiones", a["f-"], contenido="0" * 64)["id"]}))
    mal("fuente-invalida", "forma_fuente ≠ sha256(fuente)", "fuente_invalida",
        lambda p: con_af(p, C["wd_a_f"], sujetos={"objeto": nuevo(p, "revisiones", a["f-"], forma_fuente="0" * 64)["id"]}))
    mal("referencia", "premisa que no está en el paquete", "referencia_desconocida",
        lambda p: p["certificados"].pop(C["eq_f"]["id"]) and None)
    mal("componente", "componente de base desconocido", "componente_desconocido",
        lambda p: cert(p, C["wd_a_f"], base={**C["wd_a_f"]["base"], "otro": "v1"})["id"])
    mal("procedencia", "procedencia distinta de la premisa origen", "procedencia_invalida",
        lambda p: cert(p, C["r_prop"], procedencia=C["eq_f"]["id"])["id"])
    # --- afirmaciones (§3) ---
    mal("contexto-conclusion", "hipótesis adicional en la conclusión", "contexto_no_fijo",
        lambda p: con_af(p, C["prop_a"], contexto={"supuestos": ["L-OBS"], "hipotesis": "x = 1"}))

    def eq_con_hipotesis(p):            # crítico 1 del control: EQ válida solo bajo x = 1 usada como premisa
        eq = cert(p, C["eq_f"], afirmacion=nuevo(p, "afirmaciones", af_de(C["eq_f"]),
                                                 contexto={"direccion": "d->a", "hipotesis": "x = 1"})["id"])
        return cert(p, C["r_prop"], premisas={**C["r_prop"]["premisas"], f"eq:{rf}": eq["id"]})["id"]
    mal("contexto-premisa", "EQ con hipótesis como premisa de R-PROP (crítico 1 del control)", "contexto_no_fijo",
        eq_con_hipotesis)
    mal("papel", "papeles de sujeto incorrectos", "papel_invalido",
        lambda p: con_af(p, C["wd_a_f"], sujetos={"nueva": a["f-"]["id"]}))
    mal("clase", "clase desconocida", "clase_desconocida", lambda p: con_af(p, C["wd_a_f"], clase="WD2"))
    mal("tipo-sujeto", "WD de una propiedad", "tipo_sujeto_invalido",
        lambda p: con_af(p, C["wd_a_f"], sujetos={"objeto": a["p"]["id"]}))
    mal("eq-ranuras", "EQ entre ranuras distintas", "ranura_distinta",
        lambda p: con_af(p, C["eq_f"], sujetos={"nueva": d["g"]["id"], "anterior": a["f-"]["id"]}))
    mal("firma", "EQ entre firmas distintas", "firma_distinta",
        lambda p: con_af(p, C["eq_f"], sujetos={"nueva": d["f-"]["id"], "anterior": nuevo(
            p, "revisiones", a["f-"], firma="(computation f- ((x (bv 16))) (bv 8))")["id"]}))
    # --- cierre, base y vigencia (§5) ---
    mal("cierre", "cierre sin la dependencia f- (D7)", "cierre_distinto",
        lambda p: cert(p, C["prop_a"], cierre={x: v for x, v in C["prop_a"]["cierre"].items() if x != rf})["id"])
    mal("cierre-incoherente", "k2 llama a g, que llama a f-, pero sus dependencias no incluyen f-",
        "cierre_incoherente",
        lambda p: con_af(p, C["inv"], sujetos={"objeto": nuevo(p, "revisiones", a["k2"], dependencias={
            e.R("g")["id"]: a["g"]["id"]})["id"]}))
    mal("base", "base sin el ejecutor actual (D-2)", "base_distinta",
        lambda p: cert(p, C["wd_a_f"], base={**C["wd_a_f"]["base"], "ejecutor": "v0"})["id"])
    mal("objeto-verificado", "hoja que verificó otro cuerpo (D9)", "objeto_verificado_distinto",
        lambda p: cert(p, C["real_a"], objeto_verificado=d["f-"]["contenido"])["id"])
    mal("no-vigente-propia", "certificado de S_a que dice estar en S_d", "no_vigente",
        lambda p: cert(p, C["prop_a"], instantanea=e.S["d"]["id"])["id"])
    # --- reglas (§6) ---
    mal("premisa-ausente", "R-PROP sin WD(f-_d)", "premisa_ausente",
        lambda p: cert(p, C["r_prop"], premisas={x: v for x, v in C["r_prop"]["premisas"].items()
                                                  if x != f"wd_d:{rf}"})["id"])
    mal("premisa-sobrante", "premisa no exigida por la regla", "premisa_sobrante",
        lambda p: cert(p, C["r_prop"], premisas={**C["r_prop"]["premisas"], "extra": C["wd_c"]["id"]})["id"])
    mal("homonimo", "WD(c) usada como WD(f-_a) (D3/D5)", "premisa_clase",
        lambda p: cert(p, C["r_real"], premisas={**C["r_real"]["premisas"], "wd_a": C["wd_c"]["id"]})["id"])
    mal("premisa-estado", "EQ refutada como premisa", "premisa_estado",
        lambda p: cert(p, C["r_real"], premisas={**C["r_real"]["premisas"], "eq": cert(
            p, C["eq_f"], estado="refutado")["id"]})["id"])

    def premisa_otra_base(p):           # WD(f-_a) válida con otro ejecutor: no vigente en S_a (D-2)
        Sx = nuevo(p, "instantaneas", e.S["a"], base={**BASE, "ejecutor": "v0"})
        w = cert(p, C["wd_a_f"], instantanea=Sx["id"], base={**C["wd_a_f"]["base"], "ejecutor": "v0"})
        return cert(p, C["r_real"], premisas={**C["r_real"]["premisas"], "wd_a": w["id"]})["id"]
    mal("premisa-no-vigente", "WD(f-_a) de otra base de confianza (D-2)", "no_vigente", premisa_otra_base)

    def falsificada(p):                 # crítico 2 del control: conservación sobre una R-PROP sin EQ ni WD
        r = cert(p, C["r_prop"], premisas={"origen": C["prop_a"]["id"]})
        return cert(p, C["conservada"], procedencia=r["id"])["id"]
    mal("cadena", "conservación sobre una derivación intermedia inválida (crítico 2)", "premisa_ausente", falsificada)

    def falsificada_larga(p):           # la invalidez está dos niveles por debajo
        r = cert(p, C["r_prop"], premisas={"origen": C["prop_a"]["id"]})
        cons = cert(p, C["conservada"], procedencia=r["id"])
        return cert(p, C["r_prop_e"], premisas={**C["r_prop_e"]["premisas"], "origen": cons["id"]},
                    procedencia=cons["id"])["id"]
    mal("cadena-larga", "R-PROP sobre una conservación de una R-PROP sin premisas", "premisa_ausente",
        falsificada_larga)
    mal("registro-premisa", "un registro histórico usado como procedencia (D-3)", "registro_como_premisa",
        lambda p: cert(p, C["conservada"], procedencia=C["registro"]["id"])["id"])
    mal("conservacion-estado", "conservación que cambia el estado", "conservacion_estado_distinto",
        lambda p: cert(p, C["conservada"], estado="refutado")["id"])
    mal("conservacion-afirmacion", "conservación de otra afirmación", "conservacion_afirmacion_distinta",
        lambda p: cert(p, C["conservada"], procedencia=C["prop_a"]["id"])["id"])
    mal("regla-clase", "R-REAL sobre una PROP", "regla_clase_incompatible",
        lambda p: cert(p, C["r_prop"], regla="R-REAL")["id"])
    # --- v2.3: precedencia, profundidad, igualdad tipada y prevalidación global (segunda auditoría de Sol) ---
    mal("precedencia-esquema", "esquema desconocido y campo de más: gana el esquema", "esquema_desconocido",
        lambda p: cert(p, C["wd_a_f"], esquema="otro", extra=1)["id"])
    mal("precedencia-ausente", "campo ausente y tipo incorrecto: gana el ausente", "campo_ausente",
        lambda p: sin_firmar(p, canon.con_id({**{x: v for x, v in C["wd_a_f"].items() if x != "cierre"},
                                              "via": []})))
    mal("precedencia-tipo", "vía no textual y base no objeto (sin excepciones de Python)", "tipo_invalido",
        lambda p: sin_firmar(p, canon.con_id({**C["wd_a_f"], "via": [], "base": []})))
    mal("precedencia-cierre-base", "cierre y base incorrectos: gana el cierre", "cierre_distinto",
        lambda p: cert(p, C["prop_a"], cierre={}, base={**C["prop_a"]["base"], "z3": "v0"})["id"])

    def medicion_lista(p):              # un registro no alcanzado con mediciones inválidas: prevalidación global
        r = canon.con_id({**C["registro"], "mediciones": {"cpu_s": [1, 2]}}, k.EXCLUIDOS["registro"])
        p["registros"][r["id"]] = r
    mal("prevalidacion", "registro no alcanzado con mediciones inválidas: se rechaza el paquete", "tipo_invalido",
        medicion_lista)

    # --- v2.6: coherencia entre vía y origen del registro (§4.1), que el esquema también expresa (§2.3) ---
    def registro_con(p, **cambios):
        r = canon.con_id({**C["registro"], **cambios}, k.EXCLUIDOS["registro"])
        p["registros"][r["id"]] = r
    mal("registro-directo-origen", "registro directo que declara origen", "procedencia_invalida",
        lambda p: registro_con(p, origen=C["registro"]["id"]))
    mal("registro-conservado-sin-origen", "registro conservado sin origen", "procedencia_invalida",
        lambda p: registro_con(p, via="conservada-operativa"))

    def autodependencia(p):             # condición local que el esquema no expresa: compara dos campos (§2.3)
        v = canon.con_id({**a["k2"], "dependencias": {**a["k2"]["dependencias"], a["k2"]["ranura"]: a["k2"]["id"]}})
        p["revisiones"][v["id"]] = v
    mal("revision-autodependencia", "revisión que depende de su propia ranura", "tipo_invalido", autodependencia)

    # --- v2.6: un hash seguido de LF no es un hash (el patrón de JSON Schema lo admitía sin `maxLength`) ---
    mal("hash-lf-campo", "origen de un registro con LF final", "tipo_invalido",
        lambda p: registro_con(p, via="conservada-operativa", origen=C["registro"]["id"] + "\n"))
    mal("hash-lf-clave", "clave del cierre con LF final", "tipo_invalido",
        lambda p: cert(p, C["prop_a"], cierre={k + "\n": v for k, v in C["prop_a"]["cierre"].items()})["id"])

    def testigo_tipado(p):              # False y 0 son valores distintos (igualdad de bytes canónicos)
        o = cert(p, C["refut_a"], afirmacion=nuevo(p, "afirmaciones", af_de(C["refut_a"]),
                                                   contexto={"testigo": {"x": False}})["id"])
        return cert(p, C["r_refut"], premisas={**C["r_refut"]["premisas"], "origen": o["id"]},
                    procedencia=o["id"])["id"]
    mal("testigo-tipado", "testigo false en el origen y 0 en el destino", "testigo_distinto", testigo_tipado)
    # --- v2.4: fronteras de totalidad y precedencia (tercera auditoría de Sol) ---
    def anidado(p):                    # 40 niveles en unas mediciones: fuera del dominio (máximo 32)
        prof = "x"
        for _ in range(40):
            prof = [prof]
        r = {**C["registro"], "mediciones": {"traza": prof}}
        p["registros"][r["id"]] = r
    mal("anidamiento", "mediciones con 40 niveles de anidamiento", "no_canonico", anidado)
    mal("fila-null", "una fila null en la tabla de certificados", "tipo_invalido",
        lambda p: p["certificados"].__setitem__("0" * 64, None))
    mal("contenedor-precedencia", "paquete sin `registros` y con una clave de más: gana el ausente", "campo_ausente",
        lambda p: (p.pop("registros"), p.__setitem__("extra", {})) and None)
    mal("postorden-procedencia", "procedencia ausente y cierre incorrecto: gana la cadena", "referencia_desconocida",
        lambda p: cert(p, C["conservada"], procedencia="1" * 64, cierre={})["id"])
    mal("postorden-premisa", "premisa eq ausente y cierre incorrecto: gana la cadena", "referencia_desconocida",
        lambda p: cert(p, C["r_real"], premisas={**C["r_real"]["premisas"], "eq": "2" * 64}, cierre={})["id"])

    def unicode_no_normalizado(p):     # el texto no se normaliza: «a\u1add\u0300» es un nombre válido tal cual
        r = nuevo(p, "ranuras", e.R("f-"), nombre="a\u1add\u0300")
        v = nuevo(p, "revisiones", a["f-"], ranura=r["id"])
        S = nuevo(p, "instantaneas", e.S["a"], revisiones={r["id"]: v["id"]})
        af_ = nuevo(p, "afirmaciones", af_de(C["wd_a_f"]), sujetos={"objeto": v["id"]})
        return cert(p, C["wd_a_f"], afirmacion=af_["id"], instantanea=S["id"], cierre={r["id"]: v["id"]})["id"]
    p_u = copy.deepcopy(P)
    V.append(_vector("valido-unicode-sin-normalizar", "nombre con combinantes, sin normalizar (§2.1)", p_u,
                     unicode_no_normalizado(p_u), ok))
    # --- v2.5: unicidad texto/código (cuarta auditoría de Sol) ---
    mal("tipo-y-canonico", "id con formato inválido y base con un flotante: gana el tipo (paso 5) sobre el dominio "
        "(paso 7)", "tipo_invalido",
        lambda p: sin_firmar(p, {**C["wd_a_f"], "id": "no-es-un-hash", "base": {**C["wd_a_f"]["base"], "z3": 1.5}}))
    mal("procedencia-ausente", "conservación cuya procedencia no está en el paquete", "referencia_desconocida",
        lambda p: cert(p, C["conservada"], procedencia="0" * 64)["id"])
    mal("testigo", "R-REFUT con otro testigo que el origen", "testigo_distinto",
        lambda p: con_af(p, C["r_refut"], contexto={"testigo": {"x": 1}}))
    mal("evaluacion", "R-REFUT cuya evaluación no es una hoja directa", "evaluacion_no_directa",
        lambda p: cert(p, C["r_refut"], premisas={**C["r_refut"]["premisas"], "evaluacion": cert(
            p, C["evaluacion"], via="cache", regla="conservacion", objeto_verificado=None,
            procedencia=C["evaluacion"]["id"])["id"]})["id"])
    V.append(_vector_profundo(e, C))
    V.append(_vector_real_gana_ranura())
    V.extend(_vectores_texto(P, C))
    V.extend(_vectores_homonimas())
    return V


def _vector_real_gana_ranura():
    """R-REAL válida cuando f pasa de x a h(x), con h(x) = x: el cierre gana la ranura h dentro de f (§6)."""
    from efch import core
    texto = """(efch 0.1 (computation h (input x (bv 8)) (output (bv 8)) (semantics x))
      (computation f (input x (bv 8)) (output (bv 8)) (semantics {f})))"""
    e = Escenario(())
    revs = {}
    for v, cuerpo in (("a", "x"), ("d", "(call h x)")):
        d = core.load_definition(texto.format(f=cuerpo))
        [c] = core.load_candidates("(efch 0.1 (candidate c (implements f) (body x)))", d)
        f = Formas(d).todas([c])
        for r in f.ranuras.values():
            e.ranuras[r["id"]] = r
        e.extra_rev.update({x["id"]: x for x in f.revisiones.values()})
        e.extra_S[v] = k.instantanea(f.revisiones.values(), BASE)
        revs[v] = por_nombre(f)
    a, d = revs["a"], revs["d"]
    assert a["c"]["id"] == d["c"]["id"]
    o = e.cert(e.af("REAL", candidata=a["c"], computacion=a["f"]), "probado", "directa", "directa", e.extra_S["a"])
    prem = {"origen": o, "eq": e.cert(e.af("EQ", nueva=d["f"], anterior=a["f"]), "probado", "directa", "directa",
                                       e.extra_S["d"]),
            "wd_a": e.cert(e.af("WD", objeto=a["f"]), "probado", "directa", "directa", e.extra_S["a"]),
            "wd_c": e.cert(e.af("WD", objeto=d["c"]), "probado", "directa", "directa", e.extra_S["d"])}
    r = e.cert(e.af("REAL", candidata=d["c"], computacion=d["f"]), "probado", "transferida", "R-REAL",
               e.extra_S["d"], prem, o)
    return _vector("valido-r_real-gana-ranura", "R-REAL cuando f pasa a llamar a h (el cierre gana h dentro de f)",
                   e.paquete(), r["id"], {"valido": True})


DEF_HOMONIMAS = """(efch 0.1 (computation f (input x (bv 8)) (output (bv 8)) (semantics x))
  (computation g (input x (bv 8)) (output (bv 8)) (semantics 0))
  (property p (forall ((x (bv 8))) (eq (call g x) 0))))"""
CANDS_HOMONIMAS = """(efch 0.1 (candidate c (implements f) (body x)) (candidate c (implements g) (body 0)))"""


def escenario_homonimas():
    """v2.7 (Astra, EFCH-CTRL-G6): dos candidatas `c`, de f y de g. Son ranuras distintas (el ámbito es el id de la
    ranura de la computación): la elaboración conserva las dos y su evidencia no se mezcla (§2.2)."""
    from efch import core
    d = core.load_definition(DEF_HOMONIMAS)
    f = Formas(d).todas(core.load_candidates(CANDS_HOMONIMAS, d))
    e = Escenario(())
    for r in f.ranuras.values():
        e.ranuras[r["id"]] = r
    e.extra_rev = {x["id"]: x for x in f.revisiones.values()}
    e.extra_S["h"] = S = k.instantanea(f.revisiones.values(), BASE)
    rc = {f.ranuras[v["ranura"]]["ambito"]: v for v in f.revisiones.values()
          if f.ranuras[v["ranura"]]["tipo"] == "candidata"}
    rf, rg = f.computacion("f"), f.computacion("g")
    cf, cg = rc[rf["ranura"]], rc[rg["ranura"]]
    C = {"cf": cf, "cg": cg, "rf": rf, "rg": rg, "S": S, "p": f.propiedad(d.properties[0])}
    C["real_f"] = e.cert(e.af("REAL", candidata=cf, computacion=rf), "probado", "directa", "directa", S)
    C["real_g"] = e.cert(e.af("REAL", candidata=cg, computacion=rg), "probado", "directa", "directa", S)
    C["wd_cf"] = e.cert(e.af("WD", objeto=cf), "probado", "directa", "directa", S)
    return e, C


def _vectores_homonimas():
    e, C = escenario_homonimas()
    P = e.paquete()
    out = [_vector("valido-homonimas-real-f", "REAL de la candidata c de f, con otra c de g en la misma instantánea",
                   P, C["real_f"]["id"], {"valido": True}),
           _vector("valido-homonimas-real-g", "REAL de la candidata c de g, con otra c de f en la misma instantánea",
                   P, C["real_g"]["id"], {"valido": True})]

    def mal(nombre, descripcion, codigo, mutar):
        p = copy.deepcopy(P)
        out.append(_vector(f"rechazo-{nombre}", descripcion, p, mutar(p), {"rechazo": codigo}))

    def nuevo(p, tabla, base_obj, **cambios):
        x = canon.con_id({**base_obj, **cambios})
        p[tabla][x["id"]] = x
        return x

    def real_cruzada(p):              # REAL(c de f, g): la evidencia de una c no vale para la otra
        a = nuevo(p, "afirmaciones", e.afs[C["real_f"]["afirmacion"]],
                  sujetos={"candidata": C["cf"]["id"], "computacion": C["rg"]["id"]})
        return nuevo(p, "certificados", C["real_f"], afirmacion=a["id"])["id"]

    def conservar_en_otra(p):         # conservar REAL(c de f) como REAL(c de g)
        return nuevo(p, "certificados", C["real_g"], via="cache", regla="conservacion", objeto_verificado=None,
                     procedencia=C["real_f"]["id"])["id"]

    def transferir_a_otra(p):         # R-REAL hacia la c de g con origen en la REAL de la c de f
        return nuevo(p, "certificados", C["real_g"], via="transferida", regla="R-REAL", objeto_verificado=None,
                     procedencia=C["real_f"]["id"], premisas={"origen": C["real_f"]["id"]})["id"]

    def ambito(valor):
        def mutar(p):                 # la misma candidata c de f con otro ámbito (y su revisión y su WD)
            r = nuevo(p, "ranuras", e.ranuras[C["cf"]["ranura"]], ambito=valor)
            v = nuevo(p, "revisiones", C["cf"], ranura=r["id"])
            S = nuevo(p, "instantaneas", C["S"], revisiones={**C["S"]["revisiones"], r["id"]: v["id"]})
            a = nuevo(p, "afirmaciones", e.afs[C["wd_cf"]["afirmacion"]], sujetos={"objeto": v["id"]})
            return nuevo(p, "certificados", C["wd_cf"], afirmacion=a["id"], instantanea=S["id"],
                         cierre={r["id"]: v["id"]}, objeto_verificado=v["contenido"])["id"]
        return mutar

    mal("homonimas-cruzada", "REAL que une la candidata c de f con la computación g", "tipo_sujeto_invalido",
        real_cruzada)
    mal("homonimas-conservacion", "REAL de la c de g conservada desde la REAL de la c de f",
        "conservacion_afirmacion_distinta", conservar_en_otra)
    mal("homonimas-transferencia", "R-REAL de la c de g con origen en la REAL de la c de f", "candidata_distinta",
        transferir_a_otra)
    mal("ambito-propiedad", "candidata cuyo ámbito es la ranura de una propiedad", "ambito_invalido",
        ambito(C["p"]["ranura"]))
    mal("ambito-ausente", "candidata cuyo ámbito no es una ranura del paquete", "referencia_desconocida",
        ambito("3" * 64))
    mal("ambito-nombre", "candidata cuyo ámbito es el nombre de la computación, no el id de su ranura",
        "tipo_invalido", ambito("f"))
    return out


def _vector_profundo(e, C):
    """1100 conservaciones encadenadas sobre una WD: válido, y no depende del límite de recursión (§6)."""
    p = copy.deepcopy(e.paquete())
    prev = C["wd_a_f"]
    for i in range(1100):
        nxt = canon.con_id({**C["wd_a_f"], "via": "conservada" if i % 2 else "cache", "regla": "conservacion",
                            "objeto_verificado": None, "procedencia": prev["id"]})
        p["certificados"][nxt["id"]] = nxt
        prev = nxt
    return _vector("valido-cadena-profunda", "1100 conservaciones encadenadas", p, prev["id"], {"valido": True})


def _vectores_texto(P, C):
    """Entrada textual (§2.1): el validador recibe bytes y los decodifica con canon.decodificar."""
    import base64
    bonito = json.dumps(P, ensure_ascii=False, indent=2, sort_keys=False).encode()
    r = C["registro"]
    texto_r = json.dumps(r, ensure_ascii=False, sort_keys=True)
    flotante = bonito.replace(texto_r.encode(), texto_r.replace('"presupuesto_s": 30', '"presupuesto_s": 30.0').encode())
    if flotante == bonito:                   # el registro va indentado: se sustituye el valor
        flotante = bonito.replace(b'"presupuesto_s": 30', b'"presupuesto_s": 30.0', 1)
    esq = f'"esquema": "{k.ESQUEMA}",'.encode()
    duplicada = bonito.replace(esq, esq + b" " + esq, 1)
    assert duplicada != bonito
    out = []
    escapado = bonito.replace("L-OBS".encode(), b"L-\\u004fBS", 1)          # escape \uXXXX ≡ el carácter
    largo = bonito.replace(b'"presupuesto_s": 30', b'"presupuesto_s": ' + b"9" * 5000, 1)
    profundo = bonito.replace(b'"presupuesto_s": 30', b'"presupuesto_s": ' + b"[" * 2000 + b"]" * 2000, 1)
    sustituto = bonito.replace("L-OBS".encode(), b"L-\\ud800", 1)
    assert len({bonito, escapado, largo, profundo, sustituto}) == 5
    for nombre, datos, esperado in (("valido-texto", bonito, {"valido": True}),
                                    ("valido-texto-escapes", escapado, {"valido": True}),
                                    ("rechazo-texto-entero-largo", largo, {"rechazo": "no_canonico"}),
                                    ("rechazo-texto-profundo", profundo, {"rechazo": "no_canonico"}),
                                    ("rechazo-texto-sustituto", sustituto, {"rechazo": "no_canonico"}),
                                    ("rechazo-texto-flotante", flotante, {"rechazo": "no_canonico"}),
                                    ("rechazo-texto-duplicada", duplicada, {"rechazo": "no_canonico"}),
                                    ("rechazo-texto-utf8", bonito.replace(b"L-OBS", b"L-\xff".decode("unicode_escape").encode("latin-1"), 1),
                                     {"rechazo": "no_canonico"})):
        v = _vector(nombre, "entrada textual (§2.1)", None, C["r_prop"]["id"], esperado)
        del v["paquete"]
        v["entrada_b64"] = base64.b64encode(datos).decode()
        out.append(v)
    return out


# Códigos de §7 que ningún paquete puede producir con las comprobaciones actuales (defensivos; §7).
INALCANZABLES = {
    "ciclo": "los ids son hashes del contenido: un ciclo exigiría encontrar un ciclo de preimágenes de SHA-256, "
             "computacionalmente inviable bajo el supuesto criptográfico habitual (no es imposible lógicamente)",
    "semantica_distinta": "solo hay una semántica admitida; otra se rechaza antes con semantica_desconocida",
    "clase_no_transferible": "regla_clase_incompatible se comprueba antes y las tres reglas van a clases transferibles",
    "cambio_no_cubierto": "con la candidata invariable y el cierre coherente, todo cambio está en f o en sus "
                          "dependencias (R-REAL); el cierre de una PROP solo contiene computaciones y la propia p",
}


def canonicos():
    e, C = escenario_base()
    P = e.paquete()
    out = []
    for tabla in sorted(k.TABLAS):
        for oid, x in sorted(P[tabla].items()):
            excl = k.EXCLUIDOS["registro"] if tabla == "registros" else ("id",)
            out.append({"tabla": tabla, "id": oid,
                        "bytes": canon.canonico({kk: v for kk, v in x.items() if kk not in excl}).decode(),
                        "objeto": x})
    # v2.7: el mundo de las candidatas homónimas (§2.2) fija los bytes de ranuras y revisiones con ámbitos distintos.
    eh, _ = escenario_homonimas()
    PH = eh.paquete()
    vistos = {x["id"] for x in out}
    for tabla in ("ranuras", "revisiones", "instantaneas"):
        for oid, x in sorted(PH[tabla].items()):
            if oid not in vistos:
                out.append({"tabla": tabla, "id": oid, "bytes": canon.canonico(
                    {kk: v for kk, v in x.items() if kk != "id"}).decode(), "objeto": x})
    # Un registro con otras mediciones conserva su id: las mediciones no entran en el hash.
    otro = {**C["registro"], "mediciones": {"cpu_s": "0.31", "presupuesto_s": 30}}
    out.append({"tabla": "registros", "id": otro["id"], "objeto": otro,
                "bytes": canon.canonico({x: v for x, v in otro.items() if x not in k.EXCLUIDOS["registro"]}).decode()})
    return out


def comprobar(vs):
    fallos = []
    import base64
    for v in vs:
        c = v["comprobacion"]
        try:
            if "entrada_b64" in v:
                try:
                    paquete = canon.decodificar(base64.b64decode(v["entrada_b64"]))
                except canon.NoCanonico as e:
                    raise Rechazo("no_canonico", "entrada", str(e))
            else:
                paquete = v["paquete"]
            val = Validador(paquete)
            if c["tipo"] == "reutilizable":
                val.reutilizable(c["certificado"], c["instantanea"])
            else:
                val.validar(c["certificado"])
            obtenido = {"valido": True}
        except Rechazo as e:
            obtenido = {"rechazo": e.codigo}
        if obtenido != v["esperado"]:
            fallos.append((v["nombre"], v["esperado"], obtenido))
    return fallos


def cobertura(vs):
    """(códigos de §7 cubiertos por algún vector, códigos sin cubrir que no están declarados inalcanzables)."""
    import re
    texto = (pathlib.Path(__file__).parent / "ESPECIFICACION.md").read_text()
    seccion = texto[texto.index("## 7."):texto.index("## 8.")]
    codigos = set(re.findall(r"`([a-z_]+)`", seccion))
    cubiertos = {v["esperado"]["rechazo"] for v in vs if "rechazo" in v["esperado"]}
    return sorted(codigos & cubiertos), sorted(codigos - cubiertos - set(INALCANZABLES))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--salida")
    ap.add_argument("--comprobar")
    args = ap.parse_args()
    if args.salida:
        d = pathlib.Path(args.salida)
        d.mkdir(parents=True, exist_ok=True)
        for p in d.glob("*.json"):
            p.unlink()
        vs = vectores()
        for v in vs:
            (d / f"{v['nombre']}.json").write_text(json.dumps(v, ensure_ascii=False, sort_keys=True, indent=1) + "\n")
        (d / "canonicos.json").write_text(json.dumps(canonicos(), ensure_ascii=False, sort_keys=True, indent=1) + "\n")
        print(f"{len(vs)} vectores en {d}")
    if args.comprobar:
        d = pathlib.Path(args.comprobar)
        vs = [json.loads(p.read_text()) for p in sorted(d.glob("*.json")) if p.name != "canonicos.json"]
        fallos = comprobar(vs)
        for c in json.loads((d / "canonicos.json").read_text()):
            excl = k.EXCLUIDOS["registro"] if c["tabla"] == "registros" else ("id",)
            b = canon.canonico({x: v for x, v in c["objeto"].items() if x not in excl}).decode()
            if b != c["bytes"] or canon.sha(b) != c["id"]:
                fallos.append((c["id"], "bytes canónicos", "distintos"))
        cub, faltan = cobertura(vs)
        for f in fallos:
            print("FALLO", *f)
        print(f"{len(vs)} vectores, {len(fallos)} fallos; códigos cubiertos {len(cub)}; sin cubrir {faltan}")
        raise SystemExit(1 if fallos or faltan else 0)


if __name__ == "__main__":
    main()
