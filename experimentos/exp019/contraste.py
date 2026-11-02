"""EXP-019, O2: contraste contractual independiente (ficha, §Oráculos O2; v2.7 §2–§6).

Sin `efch` ni `especificacion`; se ejecuta con `python3 -I`. Construye un mapa propio por instantánea (ranura ->
fuente normalizada, firma, dependencias, cierre transitivo, expansión y revisión propia R̂), lo enlaza con las
revisiones JSON del almacén de C y comprueba cada certificado que respalda una obligación de O(S_d), y
recursivamente sus premisas, **cada uno en su propio contexto**: raíces reutilizables en S_d; en una R-REAL, origen y
WD(f_x) en S_x, WD(c) y EQ en S_d; la `anterior` de la EQ es histórica. Clasifica los fallos en V1a–V1d, sea cual
sea la verdad de la conclusión.

    python3 -I contraste.py --entrada DIR --almacen DIR --salida FASE1.json --descriptor D.json --out OUT.json
"""

import argparse
import hashlib
import json
import pathlib

ESQUEMA = "efch-evidencia/2.5"                                     # v2.7 §2.1
# v2.7 §3.1 (copia literal de los papeles que intervienen aquí) y §3.2 (contexto fijo)
PAPELES = {"WD": {"objeto": ("computacion", "candidata", "candidata-lang")},
           "EQ": {"nueva": ("computacion",), "anterior": ("computacion",)},
           "REAL": {"candidata": ("candidata", "candidata-lang"), "computacion": ("computacion",)},
           "REFUT": {"candidata": ("candidata", "candidata-lang"), "computacion": ("computacion",)}}
CONTEXTO = {"WD": {}, "EQ": {"direccion": "d->a"}, "REAL": {}}
PRINCIPAL = {"WD": "objeto", "EQ": "nueva", "REAL": "candidata", "REFUT": "candidata"}
CIERRE = {"WD": ("objeto",), "EQ": ("nueva",), "REAL": ("candidata", "computacion"),
          "REFUT": ("candidata", "computacion")}
# v2.7 §3.3 (copia literal): base por clase, sin efch-c ni cbmc (no hay candidatas Lang)
_N = ("efch-core", "efch-smt", "efch-interp", "z3", "ejecutor", "reglas")
BASE = {"WD": _N, "EQ": _N, "REAL": _N, "REFUT": ("efch-core", "efch-interp", "ejecutor", "reglas")}


def canon(x):
    return json.dumps(x, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()


def h(b):
    return hashlib.sha256(b if isinstance(b, bytes) else b.encode()).hexdigest()


def hash_objeto(o, tabla):
    excl = ("id", "mediciones") if tabla == "registros" else ("id",)
    return h(canon({k: v for k, v in o.items() if k not in excl}))


# --- lector e impresor propios ----------------------------------------------------------------------------

class Atomo:
    __slots__ = ("tipo", "valor")

    def __init__(self, tipo, valor):
        self.tipo, self.valor = tipo, valor


def _tokens(t):
    i, n = 0, len(t)
    while i < n:
        c = t[i]
        if c == ";":
            while i < n and t[i] != "\n":
                i += 1
            continue
        if c.isspace():
            i += 1
            continue
        if c in "()":
            yield c
            i += 1
            continue
        if c == '"':
            j, buf = i + 1, []
            while j < n and t[j] != '"':
                if t[j] == "\\" and j + 1 < n:
                    j += 1
                buf.append(t[j])
                j += 1
            yield Atomo("str", "".join(buf))
            i = j + 1
            continue
        j = i
        while j < n and not t[j].isspace() and t[j] not in '();"':
            j += 1
        yield Atomo("sym", t[i:j])
        i = j


def parsear(t):
    pila, cur = [], []
    for tok in _tokens(t):
        if tok == "(":
            pila.append(cur)
            cur = []
        elif tok == ")":
            hecho, cur = cur, pila.pop()
            cur.append(hecho)
        else:
            cur.append(tok)
    return cur


def imprimir(x):
    if isinstance(x, list):
        return "(" + " ".join(imprimir(y) for y in x) + ")"
    if x.tipo == "str":
        return '"' + x.valor.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return x.valor


def _s(x):
    return x.valor if isinstance(x, Atomo) and x.tipo == "sym" else None


# --- modelo propio por instantánea --------------------------------------------------------------------------

def _seccion(forma, nombre):
    return next((s for s in forma[2:] if isinstance(s, list) and _s(s[0]) == nombre), None)


def _llamadas(e, out):
    if isinstance(e, list):
        if e and _s(e[0]) == "call":
            out.add(_s(e[1]))
        for y in e:
            _llamadas(y, out)
    return out


def modelo(texto_defs, texto_cands):
    defs = parsear(texto_defs)[0][2:]
    cands = parsear(texto_cands)[0][2:]
    comps = {_s(f[1]): f for f in defs if _s(f[0]) == "computation"}
    m = {}
    for n, f in comps.items():
        entradas = [(_s(s[1]), imprimir(s[2])) for s in f[2:] if isinstance(s, list) and _s(s[0]) == "input"]
        salida = imprimir(_seccion(f, "output")[1])
        cuerpo = _seccion(f, "semantics")[1]
        m[("computacion", n)] = {"forma": f, "fuente": imprimir(f), "firma": [entradas, salida], "cuerpo": cuerpo,
                                 "entradas": [e[0] for e in entradas], "directas": sorted(_llamadas(cuerpo, set()))}
    for f in cands:
        n, cuerpo = _s(f[1]), _seccion(f, "body")[1]
        impl = _s(_seccion(f, "implements")[1])
        m[("candidata", n)] = {"forma": f, "fuente": imprimir(f), "firma": m[("computacion", impl)]["firma"],
                               "cuerpo": cuerpo, "entradas": m[("computacion", impl)]["entradas"], "implementa": impl,
                               "directas": sorted(_llamadas(cuerpo, set()))}
    for k in m:
        m[k]["cierre"] = sorted(_transitivo(m, k))
    for k in m:
        m[k]["expansion"] = _expandir(m, m[k]["cuerpo"], {e: f"${i}" for i, e in enumerate(m[k]["entradas"])})
    memo = {}

    def rh(k):
        if k not in memo:
            memo[k] = h(canon({"fuente": m[k]["fuente"], "firma": m[k]["firma"],
                               "deps": {d: rh(("computacion", d)) for d in m[k]["directas"]}}))
        return memo[k]
    for k in m:
        m[k]["R"] = rh(k)
    return m


def _transitivo(m, k):
    vistos, pila = set(), list(m[k]["directas"])
    while pila:
        d = pila.pop()
        if d not in vistos:
            vistos.add(d)
            pila += m[("computacion", d)]["directas"]
    return vistos


def _expandir(m, e, env):
    if isinstance(e, list):
        if e and _s(e[0]) == "call":
            g = m[("computacion", _s(e[1]))]
            args = [_expandir(m, a, env) for a in e[2:]]
            return _expandir(m, g["cuerpo"], dict(zip(g["entradas"], args)))
        return "(" + " ".join(_expandir(m, y, env) for y in e) + ")"
    if isinstance(e, str):
        return e
    if e.tipo == "sym" and e.valor in env:
        return env[e.valor]
    return imprimir(e)


def ranura_id(tipo, nombre, ambito=""):
    return h(canon({"esquema": ESQUEMA, "tipo": tipo, "ambito": ambito, "nombre": nombre}))


# --- contraste ----------------------------------------------------------------------------------------------

class Contraste:
    def __init__(self, entrada, almacen, salida, descriptor):
        d = pathlib.Path(entrada)
        tc = (d / "candidatas.efch").read_text(encoding="utf-8")
        self.M = {"a": modelo((d / "antes.efch").read_text(encoding="utf-8"), tc),
                  "d": modelo((d / "despues.efch").read_text(encoding="utf-8"), tc)}
        self.sal = json.loads(pathlib.Path(salida).read_text(encoding="utf-8"))
        self.desc = json.loads(pathlib.Path(descriptor).read_text(encoding="utf-8"))
        self.o = {}
        for p in sorted(pathlib.Path(almacen, "objetos").glob("*/*.json")):
            self.o.setdefault(p.parent.name, {})[p.stem] = json.loads(p.read_bytes())
        f_id = ranura_id("computacion", "f")
        self.rid = {}
        for k in self.M["a"]:
            self.rid[k] = ranura_id(k[0], k[1], f_id if k[0] == "candidata" else "")
        self.clave_de_ranura = {v: k for k, v in self.rid.items()}
        self.S = {"a": self.o["instantaneas"][self.sal["S_a"]], "d": self.o["instantaneas"][self.sal["S_d"]]}
        self.discrepancias, self.violaciones = [], []

    # enlace fuente -> revisión y relaciones de igualdad entre S_a y S_d
    def enlace(self):
        out = {}
        for k, rid in self.rid.items():
            fila = {}
            for s in ("a", "d"):
                rv = self.S[s]["revisiones"].get(rid)
                if rv is None:
                    self.discrepancias.append({"tipo": "ranura_ausente", "ranura": k, "S": s})
                    continue
                v = self.o["revisiones"][rv]
                if imprimir(parsear(v["fuente"])[0]) != self.M[s][k]["fuente"]:
                    self.discrepancias.append({"tipo": "enlace_fuente", "ranura": k, "S": s})
                deps = {self.rid[("computacion", n)] for n in self.M[s][k]["cierre"]}
                if set(v["dependencias"]) != deps:
                    self.discrepancias.append({"tipo": "dependencias_distintas", "ranura": k, "S": s})
                fila[s] = v
            if len(fila) == 2:
                id_e, id_p = fila["a"]["id"] == fila["d"]["id"], self.M["a"][k]["R"] == self.M["d"][k]["R"]
                ct_e = fila["a"]["contenido"] == fila["d"]["contenido"]
                ct_p = self.M["a"][k]["expansion"] == self.M["d"][k]["expansion"]
                if id_e != id_p:
                    self.discrepancias.append({"tipo": "identidad", "ranura": k, "efch_igual": id_e,
                                               "propio_igual": id_p})
                if ct_e != ct_p:
                    self.discrepancias.append({"tipo": "contenido", "ranura": k, "efch_igual": ct_e,
                                               "propio_igual": ct_p})
                out["/".join(k)] = {"id_igual_efch": id_e, "R_igual": id_p, "contenido_igual_efch": ct_e,
                                    "expansion_igual": ct_p}
        return out

    def _modelo_de(self, S_id):
        return "d" if S_id == self.sal["S_d"] else "a"

    def comprobar(self, cid, S_id, rol, fallos, visitados):
        """Comprueba el certificado `cid` en el contexto de la instantánea `S_id`; añade fallos (código, rol)."""
        def fallo(cod, det=""):
            fallos.append({"certificado": cid, "rol": rol, "codigo": cod, "detalle": det})
        c = self.o.get("certificados", {}).get(cid)
        if c is None:
            return fallo("certificado_ausente")
        if (cid, S_id) in visitados:
            return c
        visitados.add((cid, S_id))
        if hash_objeto(c, "certificados") != cid:
            fallo("hash_certificado")
        a = self.o.get("afirmaciones", {}).get(c["afirmacion"])
        if a is None:
            return fallo("afirmacion_ausente")
        if hash_objeto(a, "afirmaciones") != a["id"]:
            fallo("hash_afirmacion")
        clase = a.get("clase")
        if clase not in PAPELES or set(a.get("sujetos", {})) != set(PAPELES[clase]):
            return fallo("clase_o_papeles", str(clase))
        if clase in CONTEXTO and a.get("contexto") != CONTEXTO[clase]:
            fallo("contexto")
        S = self.o["instantaneas"].get(S_id)
        if S is None:
            return fallo("instantanea_ausente", S_id)
        suj = {}
        for papel, rv in a["sujetos"].items():
            v = self.o["revisiones"].get(rv)
            if v is None:
                fallo("revision_ausente", papel)
                continue
            r = self.o["ranuras"].get(v["ranura"])
            if r is None or r["tipo"] not in PAPELES[clase][papel]:
                fallo("tipo_sujeto", papel)
            suj[papel] = v
        if len(suj) != len(a["sujetos"]):
            return c
        # sujetos de la instantánea de contexto (raíces y premisas en S_d; origen y WD(f_x) en S_x)
        for papel in CIERRE[clase]:
            v = suj[papel]
            if S["revisiones"].get(v["ranura"]) != v["id"]:
                fallo("sujeto_no_vigente", papel)
        # cierre propio traducido a ids de la instantánea
        md = self.M[self._modelo_de(S_id)]
        propio = {}
        for papel in CIERRE[clase]:
            k = self.clave_de_ranura.get(suj[papel]["ranura"])
            if k is None:
                fallo("ranura_desconocida", papel)
                continue
            for nk in [k] + [("computacion", n) for n in md[k]["cierre"]]:
                rr = self.rid[nk]
                propio[rr] = S["revisiones"].get(rr)
        if propio != c["cierre"]:
            fallo("cierre_distinto")
        base = BASE[clase]
        if set(c["base"]) != set(base) or any(c["base"][x] != self.desc.get(x) for x in base):
            fallo("base_normativa")
        if any(S["base"].get(x) != c["base"].get(x) for x in base):
            fallo("base_de_instantanea")
        if c["regla"] == "directa":
            if c["premisas"] or c["procedencia"] is not None:
                fallo("directa_con_premisas")
            if c["objeto_verificado"] != suj[PRINCIPAL[clase]]["contenido"]:
                fallo("objeto_verificado")
            Sc = self.o["instantaneas"].get(c["instantanea"])
            if Sc is None:
                fallo("instantanea_propia_ausente")
            else:
                if any(Sc["revisiones"].get(r) != v for r, v in c["cierre"].items()):
                    fallo("hoja_no_valida_en_su_instantanea")
                if any(Sc["base"].get(x) != c["base"].get(x) for x in base):
                    fallo("hoja_base_distinta_en_su_instantanea")
        elif c["regla"] == "R-REAL":
            self._r_real(c, a, suj, S_id, fallos, visitados)
        else:
            fallo("regla_no_contemplada", c["regla"])
        return c

    def _r_real(self, c, a, suj, S_id, fallos, visitados):
        def fallo(cod, det=""):
            fallos.append({"certificado": c["id"], "rol": "R-REAL", "codigo": cod, "detalle": det})
        if c["instantanea"] != S_id:
            fallo("transferencia_fuera_de_contexto")
        p = c["premisas"]
        if set(p) != {"origen", "eq", "wd_a", "wd_c"}:
            return fallo("premisas_incompletas", str(sorted(p)))
        if c["procedencia"] != p["origen"]:
            fallo("procedencia_distinta")
        o = self.o["certificados"].get(p["origen"])
        if o is None:
            return fallo("origen_ausente")
        oa = self.o["afirmaciones"].get(o["afirmacion"])
        if oa is None or oa.get("clase") != "REAL" or o["estado"] != "probado":
            return fallo("origen_no_real_probado")
        if oa["sujetos"].get("candidata") != a["sujetos"]["candidata"]:
            fallo("candidata_distinta")
        S_x = o["instantanea"]
        self.comprobar(o["id"], S_x, "origen (S_x)", fallos, visitados)
        if o["base"] != c["base"]:
            fallo("base_origen_distinta")
        prem = {"wd_a": ("WD", {"objeto": oa["sujetos"]["computacion"]}, S_x),
                "wd_c": ("WD", {"objeto": a["sujetos"]["candidata"]}, S_id),
                "eq": ("EQ", {"nueva": a["sujetos"]["computacion"], "anterior": oa["sujetos"]["computacion"]}, S_id)}
        for nombre, (clase, sujetos, ctx) in prem.items():
            x = self.o["certificados"].get(p[nombre])
            xa = self.o["afirmaciones"].get(x["afirmacion"]) if x else None
            if x is None or xa is None or xa.get("clase") != clase or xa["sujetos"] != sujetos or \
                    x["estado"] != "probado":
                fallo(f"premisa_{nombre}")
                continue
            if nombre == "eq" and x["regla"] != "directa":
                fallo("eq_no_directa")
            self.comprobar(x["id"], ctx, f"premisa {nombre}", fallos, visitados)

    def raices(self):
        res, s_d = {}, self.sal["S_d"]
        cambiadas_propias = {k for k in self.rid if self.M["a"][k]["R"] != self.M["d"][k]["R"]}
        id_iguales_efch = {k for k in self.rid if self.S["a"]["revisiones"].get(self.rid[k]) ==
                           self.S["d"]["revisiones"].get(self.rid[k])}
        for ob in self.sal.get("obligaciones", []):
            cid = ob.get("certificado")
            if not cid:
                res[ob["obligacion"]] = {"certificado": None, "origen": ob.get("origen"), "fallos": []}
                continue
            fallos = []
            self.comprobar(cid, s_d, "raiz", fallos, set())
            tipos = set()
            for f in fallos:
                if f["codigo"].startswith("hash"):
                    tipos.add("V1d")
                elif f["rol"] == "raiz" and f["certificado"] == cid:
                    tipos.add("V1a")
                else:
                    tipos.add("V1b")
            # V1c: reutilización apoyada en una igualdad de identidad de efch que el contraste contradice
            if ob.get("origen") in ("conservada", "R-REAL"):
                c = self.o["certificados"].get(cid, {})
                for rr in c.get("cierre", {}):
                    k = self.clave_de_ranura.get(rr)
                    if k in cambiadas_propias and k in id_iguales_efch:
                        tipos.add("V1c")
                        fallos.append({"certificado": cid, "rol": "raiz", "codigo": "identidad_contradicha",
                                       "detalle": "/".join(k)})
            res[ob["obligacion"]] = {"certificado": cid, "origen": ob.get("origen"), "fallos": fallos,
                                     "violaciones": sorted(tipos)}
            for t in sorted(tipos):
                self.violaciones.append({"tipo": t, "obligacion": ob["obligacion"], "certificado": cid})
        return res

    def identicos(self):
        """Para R2: ¿sujetos, cierre y base de REAL(ci, f) idénticos en S_a y S_d (según el modelo propio)?"""
        out = {}
        for k in self.rid:
            if k[0] != "candidata":
                continue
            ks = [k, ("computacion", "f")] + [("computacion", n) for n in self.M["d"][k]["cierre"]] + \
                [("computacion", n) for n in self.M["d"][("computacion", "f")]["cierre"]]
            out[k[1]] = all(self.M["a"][x]["R"] == self.M["d"][x]["R"] for x in ks) and \
                self.M["a"][k]["cierre"] == self.M["d"][k]["cierre"]
        return out


def main():
    ap = argparse.ArgumentParser()
    for x in ("--entrada", "--almacen", "--salida", "--descriptor", "--out"):
        ap.add_argument(x, required=True)
    a = ap.parse_args()
    c = Contraste(a.entrada, a.almacen, a.salida, a.descriptor)
    out = {"enlace": c.enlace(), "raices": c.raices(), "identicos": c.identicos()}
    out.update({"discrepancias": c.discrepancias, "violaciones": c.violaciones})
    pathlib.Path(a.out).write_text(json.dumps(out, sort_keys=True, ensure_ascii=False, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
