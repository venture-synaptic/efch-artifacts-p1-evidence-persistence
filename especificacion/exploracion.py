"""Exploración acotada de las reglas (ESPECIFICACION.md, §8).

[Experimento] Un modelo semántico abstracto y finito, independiente de EFCH, en el que se enumeran exhaustivamente
mundos pequeños y, en cada uno, intentos de derivación honestos y alterados. Comprueba dos cosas:

1. **Corrección en el modelo:** todo certificado que `reglas.Validador` acepta afirma algo verdadero en el modelo.
2. **Potencia:** con cada comprobación relajada (`reglas.RELAJACIONES`), la exploración encuentra un contraejemplo,
   o declara que esa comprobación no es observable en el modelo (protege frente a algo que el modelo no representa:
   herramientas, objeto verificado...).

Modelo: dominio X = {0, 1}; valores {0, 1, ⊥}. Computaciones base `f` y `h` (tablas); `g` llama a `f` con un
combinador (`id`, `neg`, `k0`); la propiedad `p` habla de `g` (`g=0`, `g=x`); la candidata `c` implementa `f` y es
una tabla o una llamada a `h`. Semántica de EQ como la de SMT: un ⊥ de la revisión anterior vale 0 (codificación
total), por eso WD(f_a) es necesaria. Las hojas directas son verídicas: es la base de confianza del diseño.

Límites: no representa herramientas, presupuestos, tipos de EFCH ni más de dos instantáneas por mundo; lo que no
depende de la semántica (hashes, base, objeto verificado) lo cubren los vectores (vectores.py).

    python3 -m especificacion.exploracion [--salida ARCHIVO]
"""

import argparse
import itertools
import json

from . import contrato as k
from .reglas import RELAJACIONES, Validador
from .contrato import Rechazo

X = (0, 1)
V = (0, 1, None)
TABLAS = list(itertools.product(V, repeat=len(X)))
COMBS = ("id", "neg", "k0")
PREDS = ("g=0", "g=x")
BASE = {c: "v1" for c in k.COMPONENTES}

R = {n: k.ranura("computacion", n) for n in ("f", "g", "h")}
R["p"] = k.ranura("propiedad", "p")
R["c"] = k.ranura("candidata", "c", R["f"]["id"])


def _g(comb, tf):
    return tuple(None if comb != "k0" and tf[x] is None else (tf[x] if comb == "id" else 1 - tf[x] if comb == "neg"
                                                               else 0) for x in X)


def _p(pred, tg):
    return tuple(None if tg[x] is None else (tg[x] == 0 if pred == "g=0" else tg[x] == x) for x in X)


class Mundo:
    """Dos instantáneas a y d con sus revisiones, su semántica y un almacén de certificados."""

    def __init__(self, a, d, base_d=BASE):
        self.rev, self.sem, self.objs = {}, {}, {}
        self.S = {}
        self.ranuras = list(R.values())
        self.afs, self.certs = {}, {}
        for nombre, spec, base in (("a", a, BASE), ("d", d, base_d)):
            revs = self._revisiones(nombre, spec)
            self.S[nombre] = k.instantanea(revs.values(), base)
        self.pool = []

    def _rev(self, ranura, forma, fuente, firma, deps, tabla):
        v = k.revision(ranura, forma, fuente, firma, deps)
        self.objs[v["id"]] = v
        self.sem[v["id"]] = tabla
        return v

    def _revisiones(self, nombre, spec):
        tf, th, comb, pred, cand = spec["f"], spec["h"], spec["comb"], spec["pred"], spec["c"]
        f = self._rev(R["f"], f"(comp f {tf})", f"(comp f {tf})", "(x)", {}, tf)
        h = self._rev(R["h"], f"(comp h {th})", f"(comp h {th})", "(x)", {}, th)
        gdeps = {} if comb == "k0" else {R["f"]["id"]: f["id"]}
        g = self._rev(R["g"], f"(comp g {comb} {f['forma_canonica'] if gdeps else ''})", f"(comp g {comb} f)", "(x)",
                      gdeps, _g(comb, tf))
        p = self._rev(R["p"], f"(prop {pred} {g['forma_canonica']})", f"(prop {pred} g)", "(x)",
                      {R["g"]["id"]: g["id"], **g["dependencias"]}, _p(pred, self.sem[g["id"]]))
        if cand == "h":
            c = self._rev(R["c"], f"(cand {h['forma_canonica']})", "(cand call h)", "(x)",
                          {R["h"]["id"]: h["id"]}, th)
        else:
            c = self._rev(R["c"], f"(cand {cand})", f"(cand {cand})", "(x)", {}, cand)
        revs = {"f": f, "g": g, "h": h, "p": p, "c": c}
        self.rev[nombre] = revs
        return revs

    # --- verdad en el modelo -----------------------------------------------------------------------------------

    def verdad(self, af):
        """Estado verdadero de una afirmación en el modelo: 'probado', 'refutado' o None (indefinido)."""
        s = {p: self.sem[r] for p, r in af["sujetos"].items()}
        H = af["contexto"].get("hipotesis", list(X)) if isinstance(af["contexto"], dict) else list(X)
        cl = af["clase"]
        if cl == "WD":
            return "probado" if all(v is not None for v in s["objeto"]) else "refutado"
        if cl == "EQ":
            d, a = s["nueva"], s["anterior"]
            ok = all(d[x] is None or d[x] == (0 if a[x] is None else a[x]) for x in H)
            return "probado" if ok else "refutado"
        if cl == "PROP":
            vals = [s["propiedad"][x] for x in H]
            if all(v is True for v in vals):
                return "probado"
            return "refutado" if any(v is False for v in vals) else None
        if cl == "REAL":
            c, f = s["candidata"], s["computacion"]
            ok = all(v is not None for v in c) and all(f[x] is None or c[x] == f[x] for x in X)
            return "probado" if ok else "refutado"
        if cl == "REFUT":
            w = af["contexto"]["testigo"]["x"]
            c, f = s["candidata"], s["computacion"]
            return "probado" if f[w] is not None and c[w] is not None and c[w] != f[w] else "refutado"
        raise ValueError(cl)

    # --- construcción de certificados -------------------------------------------------------------------------

    def af(self, clase, contexto=None, **suj):
        a = k.afirmacion(clase, contexto, **suj)
        self.afs[a["id"]] = a
        return a

    def _cierre(self, af):
        out = {}
        for rid in (af["sujetos"][x] for x in k.PAPELES_CIERRE[af["clase"]]):
            v = self.objs[rid]
            out[v["ranura"]] = v["id"]
            out.update(v["dependencias"])
        return out

    def _base(self, af, S):
        return {c: S["base"][c] for c in k.BASE_POR_CLASE[af["clase"]]}

    def directa(self, af, S):
        """Hoja directa verídica (o None si la afirmación es indefinida o su estado no es certificable)."""
        e = self.verdad(af)
        if e is None or e not in k.ESTADOS_POR_CLASE[af["clase"]]:
            return None
        principal = af["sujetos"][k.PRINCIPAL[af["clase"]]]
        c = k.certificado(af, e, "directa", "directa", S, self._base(af, S), self._cierre(af),
                          self.objs[principal]["contenido"])
        self.certs[c["id"]] = c
        return c

    def derivado(self, af, estado, via, regla, S, premisas=None, procedencia=None):
        c = k.certificado(af, estado, via, regla, S, self._base(af, S), self._cierre(af), None, premisas,
                          procedencia)
        self.certs[c["id"]] = c
        return c

    def paquete(self):
        return k.paquete(self.ranuras, self.objs.values(), self.S.values(), self.afs.values(), self.certs.values())


def _hipotesis(clase, h):
    base = dict(k.CONTEXTO_FIJO[clase])
    return {**base, "hipotesis": list(h)}


def _directas(m):
    """Almacén de hojas directas verídicas del mundo, incluidas las de contexto con hipótesis (distractores)."""
    Sa, Sd, ra, rd = m.S["a"], m.S["d"], m.rev["a"], m.rev["d"]
    out = {}

    def put(nombre, af, S):
        c = m.directa(af, S)
        if c is not None:
            out[nombre] = c

    for n in ("f", "g", "h", "c"):
        put(f"wd_a:{n}", m.af("WD", objeto=ra[n]), Sa)
        put(f"wd_d:{n}", m.af("WD", objeto=rd[n]), Sd)
    for n in ("f", "g"):
        put(f"eq:{n}", m.af("EQ", nueva=rd[n], anterior=ra[n]), Sd)
        put(f"eq_inv:{n}", m.af("EQ", nueva=ra[n], anterior=rd[n]), Sd)
        for h in ((0,), (1,)):
            put(f"eq_h{h[0]}:{n}", m.af("EQ", _hipotesis("EQ", h), nueva=rd[n], anterior=ra[n]), Sd)
    put("prop_a", m.af("PROP", propiedad=ra["p"]), Sa)
    put("prop_d", m.af("PROP", propiedad=rd["p"]), Sd)
    for h in ((0,), (1,)):
        put(f"prop_a_h{h[0]}", m.af("PROP", _hipotesis("PROP", h), propiedad=ra["p"]), Sa)
    put("real_a", m.af("REAL", candidata=ra["c"], computacion=ra["f"]), Sa)
    for w in X:
        put(f"refut_a:{w}", m.af("REFUT", {"testigo": {"x": w}}, candidata=ra["c"], computacion=ra["f"]), Sa)
        put(f"refut_d:{w}", m.af("REFUT", {"testigo": {"x": w}}, candidata=rd["c"], computacion=rd["f"]), Sd)
    return out


def _intentos(m, D):
    """(nombre de regla, afirmación objetivo, estado, premisas) honestos y alterados."""
    ra, rd, Sa, Sd = m.rev["a"], m.rev["d"], m.S["a"], m.S["d"]
    out = []
    pool = list(D.values())

    def variantes(regla, af, estado, honestas):
        out.append((regla, af, estado, dict(honestas)))
        for prefijo in ("eq:", "wd_a:", "wd_d:"):           # quitar a la vez todas las premisas de un tipo
            sin = {p: c for p, c in honestas.items() if not p.startswith(prefijo)}
            if len(sin) < len(honestas) - 1:
                out.append((regla, af, estado, sin))
        for papel in list(honestas):
            sin = {p: c for p, c in honestas.items() if p != papel}
            out.append((regla, af, estado, sin))
            for c in pool:
                if c is not honestas[papel]:
                    out.append((regla, af, estado, {**sin, papel: c}))

    # R-PROP: origen PROP(p_a) (o con hipótesis) hacia PROP(p_d).
    af_pd = m.af("PROP", propiedad=rd["p"])
    for origen in [x for x in ("prop_a", "prop_a_h0", "prop_a_h1") if x in D]:
        cambios = [n for n in ("f", "g") if R[n]["id"] in rd["p"]["dependencias"]
                   and ra[n]["id"] != rd[n]["id"]]
        hon = {"origen": D[origen]}
        for n in cambios:
            for papel, clave in ((f"eq:{R[n]['id']}", f"eq:{n}"), (f"wd_a:{R[n]['id']}", f"wd_a:{n}"),
                                 (f"wd_d:{R[n]['id']}", f"wd_d:{n}")):
                if clave in D:
                    hon[papel] = D[clave]
        variantes("R-PROP", af_pd, D[origen]["estado"], hon)
        for h in ("0", "1"):                                  # EQ con hipótesis en lugar de la EQ fija
            alt = dict(hon)
            for n in cambios:
                if f"eq_h{h}:{n}" in D:
                    alt[f"eq:{R[n]['id']}"] = D[f"eq_h{h}:{n}"]
            out.append(("R-PROP", af_pd, D[origen]["estado"], alt))
    # R-REAL: REAL(c, f_a) hacia REAL(c_d, f_d).
    if "real_a" in D:
        af_rd = m.af("REAL", candidata=rd["c"], computacion=rd["f"])
        hon = {p: D[x] for p, x in (("origen", "real_a"), ("eq", "eq:f"), ("wd_a", "wd_a:f"), ("wd_c", "wd_d:c"))
               if x in D}
        variantes("R-REAL", af_rd, "probado", hon)
        for h in ("0", "1"):
            if f"eq_h{h}:f" in D:
                out.append(("R-REAL", af_rd, "probado", {**hon, "eq": D[f"eq_h{h}:f"]}))
    # R-REFUT: REFUT(c, f_a, w) hacia REFUT(c_d, f_d, w).
    for w in X:
        if f"refut_a:{w}" in D:
            af_fd = m.af("REFUT", {"testigo": {"x": w}}, candidata=rd["c"], computacion=rd["f"])
            hon = {"origen": D[f"refut_a:{w}"]}
            if f"refut_d:{w}" in D:
                hon["evaluacion"] = D[f"refut_d:{w}"]
            variantes("R-REFUT", af_fd, "probado", hon)
    return out


def _mundos():
    """Mundos exhaustivos para cada familia (≈ 1,1·10⁴)."""
    for fa, fd in itertools.product(TABLAS, repeat=2):                 # 81 pares de f
        for comb, pred in itertools.product(COMBS, PREDS):
            yield ({"f": fa, "h": (0, 0), "comb": comb, "pred": pred, "c": (0, 0)},
                   {"f": fd, "h": (0, 0), "comb": comb, "pred": pred, "c": (0, 0)})
        for cand in TABLAS + ["h"]:
            for hd in ((0, 0), (1, 1)) if cand == "h" else ((0, 0),):
                yield ({"f": fa, "h": (0, 0), "comb": "id", "pred": "g=0", "c": cand},
                       {"f": fd, "h": hd, "comb": "id", "pred": "g=0", "c": cand})
    # cambio de fuente de la propiedad (otra plantilla) con f y g fijas
    for f in TABLAS:
        for pa, pd in itertools.permutations(PREDS, 2):
            yield ({"f": f, "h": (0, 0), "comb": "id", "pred": pa, "c": (0, 0)},
                   {"f": f, "h": (0, 0), "comb": "id", "pred": pd, "c": (0, 0)})
    # cambio de fuente de g (cambio fuente, no derivado) con f fija
    for f in TABLAS:
        for ca, cd in itertools.product(COMBS, repeat=2):
            yield ({"f": f, "h": (0, 0), "comb": ca, "pred": "g=0", "c": (0, 0)},
                   {"f": f, "h": (0, 0), "comb": cd, "pred": "g=0", "c": (0, 0)})


def _falsificado(m, D):
    """Una R-PROP persistida sin EQ ni WD (cadena inválida con hashes íntegros) y una conservación encima."""
    if "prop_a" not in D:
        return None
    af_pd = m.af("PROP", propiedad=m.rev["d"]["p"])
    falso = m.derivado(af_pd, D["prop_a"]["estado"], "transferida", "R-PROP", m.S["d"], {"origen": D["prop_a"]},
                       D["prop_a"])
    return m.derivado(af_pd, falso["estado"], "conservada", "conservacion", m.S["d"], None, falso)


def explorar(relajar=(), limite=None, exportar=None, cada=50):
    """Devuelve el resumen de la exploración con esas relajaciones. Con `exportar` (lista), añade un mundo de cada
    `cada`: su paquete y el veredicto de cada intento, para contrastar validadores independientes (§11)."""
    res = {"relajar": sorted(relajar), "mundos": 0, "intentos": 0, "aceptados": {}, "rechazados": {},
           "contraejemplos": [], "n_contraejemplos": 0}
    for i, (a, d) in enumerate(_mundos()):
        if limite is not None and i >= limite:
            break
        m = Mundo(a, d)
        D = _directas(m)
        intentos = _intentos(m, D)
        cons = _falsificado(m, D)
        objetivos = []
        forma = {}
        for regla, af, estado, prem in intentos:
            c = m.derivado(af, estado, "transferida", regla, m.S["d"], prem, prem.get("origen"))
            try:                                  # los fallos de forma los cubren los vectores; no entran al paquete
                k.validar_certificado(c)
                objetivos.append((regla, c))
            except Rechazo as e:
                del m.certs[c["id"]]
                forma[f"{regla}:{e.codigo}"] = forma.get(f"{regla}:{e.codigo}", 0) + 1
        if cons is not None:
            objetivos.append(("conservacion", cons))
        # Prevalidación global (§4): un paquete con un objeto mal formado se rechaza entero. Cada intento se juzga
        # como si su paquete solo tuviera su cierre de certificados: los que alcanzan una afirmación mal formada
        # (p. ej. con hipótesis) se rechazan con ese código y esos objetos no entran en el paquete compartido.
        malas = {}
        for aid, af in list(m.afs.items()):
            try:
                k.validar_afirmacion(af, exigir_contexto="contexto" not in relajar)
            except Rechazo as e:
                malas[aid] = e.codigo
        malos = {cid: malas[c["afirmacion"]] for cid, c in m.certs.items() if c["afirmacion"] in malas}

        def alcanza_malo(cid, visto=None):
            visto = set() if visto is None else visto
            if cid in malos:
                return malos[cid]
            if cid in visto or cid not in m.certs:
                return None
            visto.add(cid)
            c = m.certs[cid]
            for h in [c["procedencia"], *c["premisas"].values()]:
                if h and (r := alcanza_malo(h, visto)):
                    return r
            return None

        limpios = []
        for regla, c in objetivos:
            codigo = alcanza_malo(c["id"])
            if codigo:
                forma[f"{regla}:{codigo}"] = forma.get(f"{regla}:{codigo}", 0) + 1
            else:
                limpios.append((regla, c))
        objetivos = limpios
        for cid in malos:
            del m.certs[cid]
        for aid in malas:
            del m.afs[aid]
        val = Validador(m.paquete(), relajar)
        res["mundos"] += 1
        res["intentos"] += sum(forma.values())
        for x, n in forma.items():
            res["rechazados"][x] = res["rechazados"].get(x, 0) + n
        veredictos = [] if exportar is not None and i % cada == 0 else None
        for regla, c in objetivos:
            res["intentos"] += 1
            try:
                val.validar(c["id"])
            except Rechazo as e:
                clave = f"{regla}:{e.codigo}"
                res["rechazados"][clave] = res["rechazados"].get(clave, 0) + 1
                if veredictos is not None:
                    veredictos.append({"certificado": c["id"], "esperado": {"rechazo": e.codigo}})
                continue
            if veredictos is not None:
                veredictos.append({"certificado": c["id"], "esperado": {"valido": True}})
            res["aceptados"][regla] = res["aceptados"].get(regla, 0) + 1
            af = m.afs[val.p["certificados"][c["id"]]["afirmacion"]]
            if m.verdad(af) != c["estado"]:
                res["n_contraejemplos"] += 1
                if len(res["contraejemplos"]) < 3:
                    res["contraejemplos"].append({"regla": regla, "antes": _legible(a), "despues": _legible(d),
                                                  "afirmacion": af["clase"], "estado_certificado": c["estado"],
                                                  "verdad": m.verdad(af), "premisas": sorted(c["premisas"])})
        if veredictos is not None:
            exportar.append({"mundo": i, "paquete": m.paquete(), "veredictos": veredictos})
    return res


def _legible(spec):
    return {x: (list(v) if isinstance(v, tuple) else v) for x, v in spec.items()}


# Relajaciones que se ensayan: cada una sola y los pares que se enmascaran entre sí (§8).
GRUPOS = [(r,) for r in RELAJACIONES] + [("candidata", "cobertura"), ("wd_c", "estado_origen"),
                                         ("testigo", "evaluacion")]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--salida")
    ap.add_argument("--limite", type=int)
    ap.add_argument("--procesos", type=int, default=4)
    ap.add_argument("--exportar", help="JSON comprimido con una muestra de mundos y sus veredictos (§11)")
    args = ap.parse_args()
    import multiprocessing
    with multiprocessing.Pool(args.procesos) as pool:
        resultados = pool.starmap(explorar, [((), args.limite)] + [(r, args.limite) for r in GRUPOS])
    informe = {"base": resultados[0], "relajaciones": {}}
    for r, x in zip(GRUPOS, resultados[1:]):
        informe["relajaciones"]["+".join(r)] = {"n_contraejemplos": x["n_contraejemplos"], "aceptados": x["aceptados"],
                                      "ejemplo": x["contraejemplos"][:1]}
    if args.exportar:
        import gzip
        muestra = []
        explorar((), args.limite, muestra)
        with gzip.open(args.exportar, "wt") as f:
            json.dump(muestra, f, ensure_ascii=False, sort_keys=True)
    texto = json.dumps(informe, ensure_ascii=False, indent=1, sort_keys=True)
    if args.salida:
        open(args.salida, "w").write(texto + "\n")
    b = informe["base"]
    print(f"mundos {b['mundos']}, intentos {b['intentos']}, aceptados {b['aceptados']}, "
          f"contraejemplos {b['n_contraejemplos']}")
    for r, x in informe["relajaciones"].items():
        print(f"  relajar {r:24s}: contraejemplos {x['n_contraejemplos']}")


if __name__ == "__main__":
    main()
