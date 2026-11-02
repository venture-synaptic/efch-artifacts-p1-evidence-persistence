"""EXP-019: arnés del instrumento (ficha docs/experimentos/EXP-019.md, §Paridad, §Método M1–M7, §Tareas).

Cada fase de cada celda se ejecuta en su propio subproceso (lo lanza ejecutar.py):

    python3 arnes.py descriptor SALIDA.json
    python3 arnes.py fase0 --cond A|B|C --entrada DIR --celda DIR --descriptor D.json [--control ID]
    python3 arnes.py fase1 --cond A|B|C --entrada DIR --celda DIR --descriptor D.json [--control ID]
    python3 arnes.py normativo --almacen DIR --salida SALIDA.json --out OUT.json     (solo `especificacion`)
    python3 arnes.py testigos --entrada DIR --salida SALIDA.json --out OUT.json       (efch.interp)

Contiene: el contador de llamadas efectivas (envoltorio común de `smt.prove`, debajo de la caché de B) con el doble
contador sobre `z3.Solver.check`; la caché de consultas normalizadas de B (§M3, normalización N); el monitor de
integridad D11 (§M7); los adaptadores A, B y C (§M2–M4); los mutadores K/KB (esperado.json) y las confirmaciones.
Código de salida: 0 bien, 1 error (celda inconclusa), 3 parada global (modificación parcial inesperada).
"""

import argparse
import hashlib
import json
import os
import pathlib
import shutil
import sys
import time
import traceback

RAIZ = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(RAIZ))

NUCLEO = ("efch-core", "efch-smt", "efch-interp", "z3", "ejecutor", "reglas")     # ficha §Modelo (v2.7 §3.3)
INDICES = ("nombres.json", "propiedades.json", "realizaciones.json", "costes.json")
TIMEOUT = 120                                                                       # ficha §Paridad
NOTA_REGISTER = "etiqueta de control"                                               # esperado.json K1/KP1
NOTA_EVOLVE = "refactor equivalente (etiqueta de control)"
PREFIJO_KB1 = "(etiqueta de control) "


# --- serialización ------------------------------------------------------------------------------------------

def jdet(x):
    """JSON determinista (ficha §M7): claves ordenadas, floats finitos, tuplas como arrays."""
    return json.dumps(x, sort_keys=True, ensure_ascii=False, indent=1, allow_nan=False,
                      default=lambda o: sorted(o) if isinstance(o, (set, frozenset)) else repr(o))


def canonico(obj):
    """Forma canónica de la v2.7 §2.1, implementada aquí (solo objetos contractuales)."""
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()


def sha(b):
    return hashlib.sha256(b if isinstance(b, bytes) else b.encode()).hexdigest()


def escribir(p, x):
    p = pathlib.Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(jdet(x) + "\n", encoding="utf-8")


def leer(p):
    return json.loads(pathlib.Path(p).read_text(encoding="utf-8"))


# --- contadores (§M5) ---------------------------------------------------------------------------------------

CONT = {"prove": 0, "check": 0, "wd_comp": 0, "wd_cand": 0, "eq_cand": 0, "eq_rev": 0, "verify": 0,
        "interp_run": 0, "aciertos_B": 0}
_DENTRO_VERIFY = [0]
CTX = {"fase": None, "obl": None, "cand": None}


def instalar_contadores():
    """Envoltorios que delegan sin cambiar argumentos ni resultados; solo cuentan."""
    from efch import interp, pipeline, smt
    from efch._z3 import z3

    prove_original = smt.prove

    def prove_contado(*a, **k):
        CONT["prove"] += 1
        return prove_original(*a, **k)

    check_original = z3.Solver.check

    def check_contado(self, *a, **k):
        CONT["check"] += 1
        return check_original(self, *a, **k)

    wd_original, eq_original, verify_original = smt.check_well_defined, smt.check_equivalence, \
        pipeline.verify_candidate

    def wd_contado(label, *a, **k):
        CONT["wd_cand" if "candidata" in str(label) else "wd_comp"] += 1
        return wd_original(label, *a, **k)

    def eq_contado(*a, **k):
        CONT["eq_cand" if _DENTRO_VERIFY[0] else "eq_rev"] += 1
        return eq_original(*a, **k)

    def verify_contado(*a, **k):
        CONT["verify"] += 1
        _DENTRO_VERIFY[0] += 1
        try:
            return verify_original(*a, **k)
        finally:
            _DENTRO_VERIFY[0] -= 1

    run_original = interp.run

    def run_contado(*a, **k):
        CONT["interp_run"] += 1
        return run_original(*a, **k)

    smt.prove = prove_contado
    z3.Solver.check = check_contado
    smt.check_well_defined, smt.check_equivalence = wd_contado, eq_contado
    pipeline.verify_candidate = verify_contado
    interp.run = run_contado
    return prove_contado


def foto_contadores():
    return dict(CONT)


def delta(a, b):
    return {k: b[k] - a[k] for k in a}


# --- caché de consultas de B (§M3) --------------------------------------------------------------------------

class CacheB:
    """Caché de consultas normalizadas. Clave = sha256 del texto N; solo `probado`/`refutado`; modelos por índice."""

    def __init__(self, descriptor, ruta=None):
        self.base = {c: descriptor[c] for c in NUCLEO}
        self.entradas = {}            # clave -> {clave, texto, estado, valores, origen}
        self.descartadas = []
        self.trazas = []
        if ruta is not None and pathlib.Path(ruta).exists():
            for e in leer(ruta)["entradas"]:
                if sha(e["texto"]) != e["clave"]:
                    self.descartadas.append({"clave": e["clave"], "motivo": "clave ≠ sha256(texto)"})
                    continue
                self.entradas[e["clave"]] = e

    def guardar(self, ruta):
        escribir(ruta, {"entradas": list(self.entradas.values()), "descartadas": self.descartadas})

    def normalizar(self, claim, domain, variables):
        from efch._z3 import z3
        pares, tipos = [], []
        for i, (_n, ty, sym) in enumerate(variables):
            if ty[0] == "bv":
                pares.append((sym, z3.BitVec(f"v{i}", ty[1])))
                tipos.append(f"v{i}:(bv {ty[1]})")
            elif ty[0] == "bool":
                pares.append((sym, z3.Bool(f"v{i}")))
                tipos.append(f"v{i}:bool")
            else:
                return None, None                     # otro tipo: no se guarda; siempre se delega
        aserciones = list(domain) + [z3.Not(claim)]
        subs = [z3.substitute(a, *pares) if pares else a for a in aserciones]
        texto = "QF_BV\n" + ",".join(tipos) + "\n" + "\n".join(a.sexpr() for a in subs) + "\n" + \
            canonico(self.base).decode()
        return sha(texto), texto

    def envolver(self, prove_debajo, prefijo=""):
        from efch import smt

        def prove_B(name, claim, domain, timeout_s, variables, confirm=None):
            name = prefijo + name
            clave, texto = self.normalizar(claim, domain, variables)
            obl = _obligacion(name)
            rec = {"fase": CTX["fase"], "obligacion": obl, "etiqueta": name, "clave": clave, "texto": texto}
            e = self.entradas.get(clave) if clave else None
            if e is not None:
                CONT["aciertos_B"] += 1
                nombres = [v[0] for v in variables]
                valores = {nombres[int(k[1:])]: v for k, v in (e["valores"] or {}).items()}
                if e["estado"] == "probado":
                    r = smt.Result(name, "probado", 0.0, f"caché B: {clave}")
                else:
                    crudos = {k: tuple(v) if isinstance(v, list) else v for k, v in valores.items()}
                    ok, det = confirm(crudos) if confirm is not None else (True, "")
                    r = smt.Result(name, "refutado", 0.0, det, valores) if ok else smt.Result(
                        name, "desconocido", 0.0, "inconsistencia: caché B: el intérprete no reproduce: " + det,
                        valores)
                rec.update({"acierto": True, "origen": e["origen"], "estado": r.status})
            else:
                r = prove_debajo(name, claim, domain, timeout_s, variables, confirm)
                if clave and r.status in ("probado", "refutado"):
                    vals = None
                    if r.status == "refutado" and r.counterexample is not None:
                        vals = {f"v{i}": r.counterexample[v[0]] for i, v in enumerate(variables)}
                    self.entradas[clave] = {"clave": clave, "texto": texto, "estado": r.status, "valores": vals,
                                            "origen": {"fase": CTX["fase"], "obligacion": obl, "etiqueta": name}}
                rec.update({"acierto": False, "origen": None, "estado": r.status})
            self.trazas.append(rec)
            return r
        return prove_B

    def memoria(self):
        return {"entradas": self.entradas, "trazas": self.trazas, "descartadas": self.descartadas}


def _obligacion(etiqueta):
    if CTX["cand"] is None:
        return CTX["obl"]
    return f"WD({CTX['cand']})" if "bien definida" in etiqueta else f"REAL({CTX['cand']})"


# --- monitor de integridad D11 (§M7) ------------------------------------------------------------------------

class ParadaGlobal(Exception):
    pass


def foto_disco(raiz):
    raiz = pathlib.Path(raiz)
    out = {}
    if raiz.exists():
        for p in sorted(raiz.rglob("*")):
            if p.is_file():
                b = p.read_bytes()
                out[str(p.relative_to(raiz))] = [len(b), sha(b)]
    return out


def memoria_store(s):
    """Copia determinista del estado en memoria del Store (ficha §M7)."""
    return json.loads(jdet({"alm": s.alm.t, "names": s.names, "props": s.props, "reals": s.reals,
                            "costes": s.costes, "descartados": [list(x) for x in s.descartados],
                            "en_disco": sorted(s._en_disco)}))


def _indice_ok(antes, despues, permitidos, nombre):
    """Historial solo crece; `vigente` solo cambia en las claves permitidas o nuevas; el resto, igual."""
    out = []
    for k, a in antes.items():
        d = despues.get(k)
        if d is None:
            out.append(f"{nombre}: clave {k} desaparece")
            continue
        for campo in set(a) | set(d):
            va, vd = a.get(campo), d.get(campo)
            if campo == "historial":
                if not isinstance(vd, list) or vd[:len(va or [])] != (va or []):
                    out.append(f"{nombre}[{k}].historial no solo crece")
            elif campo == "vigente":
                if va != vd and k not in permitidos:
                    out.append(f"{nombre}[{k}].vigente cambia sin estar permitido")
            elif campo == "duenos":
                if va != vd and k not in permitidos:
                    out.append(f"{nombre}[{k}].duenos cambia sin estar permitido")
            elif va != vd:
                out.append(f"{nombre}[{k}].{campo} cambia")
    return out


def comprobar_store(op, d0, d1, m0, m1, excepcion, permitidos, guarda):
    """Reglas de §M7 para el almacén de C. `permitidos`: {'names': set, 'reals': set, 'props': set}."""
    p = []
    if excepcion is not None:
        if d0 != d1:
            p.append("excepción: el disco cambió")
        if m0 is not None and sha(jdet(m0)) != sha(jdet(m1)):
            p.append("excepción: la memoria cambió")
        return p
    for ruta, h in d0.items():
        if ruta not in d1:
            p.append(f"archivo previo borrado: {ruta}")
        elif d1[ruta] != h and ruta not in INDICES:
            p.append(f"archivo previo cambiado: {ruta}")
        elif d1[ruta] != h and not guarda:
            p.append(f"índice cambiado por una operación que no guarda: {ruta}")
    for ruta in d1:
        if ruta in d0:
            continue
        partes = ruta.split("/")
        if ruta in INDICES and guarda:
            continue
        if partes[0] in ("definiciones", "pasos") and guarda:
            continue
        if partes[0] == "objetos" and guarda and len(partes) == 3:
            tabla, oid = partes[1], partes[2][:-5]
            if m1 is None or oid not in m1["alm"].get(tabla, {}):
                p.append(f"archivo nuevo sin objeto en memoria: {ruta}")
            continue
        p.append(f"archivo nuevo no previsto: {ruta}")
    if m0 is not None and m1 is not None:
        for t, objs in m0["alm"].items():
            for oid, o in objs.items():
                if m1["alm"].get(t, {}).get(oid) != o:
                    p.append(f"memoria: objeto previo cambiado o retirado: {t}/{oid[:12]}")
        p += _indice_ok(m0["names"], m1["names"], permitidos.get("names", set()), "names")
        p += _indice_ok(m0["reals"], m1["reals"], permitidos.get("reals", set()), "reals")
        p += _indice_ok(m0["props"], m1["props"], permitidos.get("props", set()), "props")
        for k, v in m0["costes"].items():
            if m1["costes"].get(k) != v:
                p.append(f"memoria: coste previo cambiado: {k[:12]}")
        if m0["descartados"] != m1["descartados"]:
            p.append("memoria: descartados cambia")
        if not set(m0["en_disco"]) <= set(m1["en_disco"]):
            p.append("memoria: _en_disco pierde ids")
    return p


def comprobar_cache(op, d0, d1, m0, m1, excepcion):
    p = []
    if excepcion is not None:
        if d0 != d1:
            p.append("excepción: el disco de B cambió")
        if sha(jdet(m0)) != sha(jdet(m1)):
            p.append("excepción: la memoria de B cambió")
        return p
    for ruta, h in d0.items():
        if ruta not in d1:
            p.append(f"archivo previo borrado: {ruta}")
        elif d1[ruta] != h and ruta != "cache-B.json":
            p.append(f"archivo previo cambiado: {ruta}")
    for ruta in d1:
        if ruta not in d0 and ruta != "cache-B.json":
            p.append(f"archivo nuevo no previsto: {ruta}")
    for k, e in m0["entradas"].items():
        if m1["entradas"].get(k) != e:
            p.append(f"caché: entrada previa cambiada o retirada: {k[:12]}")
    if m1["trazas"][:len(m0["trazas"])] != m0["trazas"]:
        p.append("caché: las trazas no solo crecen")
    if m1["descartadas"] != m0["descartadas"]:
        p.append("caché: descartadas cambia")
    return p


INDICE_DE = {"nombres.json": "names", "propiedades.json": "props", "realizaciones.json": "reals",
             "costes.json": "costes"}


def indices_frente_a_memoria(raiz, m):
    """I1: el contenido real de cada índice en disco tiene que ser el de la memoria (no basta su nombre o hash)."""
    out = []
    if m is None:
        return out
    for nombre, campo in INDICE_DE.items():
        p = pathlib.Path(raiz) / nombre
        if p.exists():
            try:
                disco = json.loads(p.read_text(encoding="utf-8"))
            except ValueError:
                out.append(f"índice ilegible en disco: {nombre}")
                continue
            if disco != m[campo]:
                out.append(f"índice en disco distinto de la memoria: {nombre}")
        elif m[campo]:
            out.append(f"índice ausente en disco con contenido en memoria: {nombre}")
    return out


class Monitor:
    def __init__(self, raiz, celda):
        self.raiz, self.celda, self.registro = pathlib.Path(raiz), pathlib.Path(celda), []

    def verificar_carga(self, s):
        """Tras cargar un Store: los índices de disco son exactamente los de su memoria (I1)."""
        problemas = indices_frente_a_memoria(self.raiz, memoria_store(s))
        self.registro.append({"op": "índices tras la carga", "excepcion": None, "problemas": problemas})
        if problemas:
            escribir(self.celda / f"incidente-{len(self.registro):02d}.json", {"op": "carga", "problemas": problemas})
            raise ParadaGlobal(f"carga: {problemas}")

    def operar(self, nombre, fn, memoria, comprobar, **kw):
        d0, m0 = foto_disco(self.raiz), memoria()
        exc = None
        try:
            r = fn()
        except ParadaGlobal:
            raise
        except Exception as e:  # noqa: BLE001 — se registra y se vuelve a lanzar tras comprobar la integridad
            exc, r = e, None
        d1, m1 = foto_disco(self.raiz), memoria()
        problemas = comprobar(nombre, d0, d1, m0, m1, exc, **kw)
        if comprobar is comprobar_store and exc is None and m1 is not None:
            problemas = problemas + indices_frente_a_memoria(self.raiz, m1)
        self.registro.append({"op": nombre, "excepcion": repr(exc) if exc else None, "problemas": problemas})
        if problemas:
            escribir(self.celda / f"incidente-{len(self.registro):02d}.json",
                     {"op": nombre, "problemas": problemas, "excepcion": repr(exc) if exc else None,
                      "disco_antes": d0, "disco_despues": d1, "memoria_antes": m0, "memoria_despues": m1})
            raise ParadaGlobal(f"{nombre}: {problemas}")
        if exc is not None:
            raise exc
        return r


# --- utilidades de entrada ----------------------------------------------------------------------------------

def cargar_entrada(entrada):
    from efch import core
    d = pathlib.Path(entrada)
    ta, td, tc = (d / "antes.efch").read_text(), (d / "despues.efch").read_text(), (d / "candidatas.efch").read_text()
    da, dd = core.load_definition(ta), core.load_definition(td)
    return {"meta": leer(d / "meta.json"), "texto_a": ta, "texto_d": td, "defn_a": da, "defn_d": dd,
            "cands_a": core.load_candidates(tc, da), "cands_d": core.load_candidates(tc, dd)}


def esperado(entrada):
    p = pathlib.Path(entrada) / "esperado.json"
    return leer(p) if p.exists() else None


def procedimiento(defn, cands, timeout=TIMEOUT):
    """§M2 (A) y, con la caché instalada, §M3 (B): WD(f), WD(h), WD(q) y verify_candidate de c0..c2."""
    from efch import pipeline, smt
    obls = []
    for n in ("f", "h", "q"):
        CTX["obl"], CTX["cand"] = f"WD({n})", None
        comp = defn.computations[n]
        r = smt.check_well_defined("semántica bien definida", comp.semantics, comp.inputs, timeout)
        obls.append({"obligacion": f"WD({n})", "clase": "WD", "estado": r.status, "testigo": r.counterexample})
    f = defn.computations["f"]
    for c in cands:
        CTX["obl"], CTX["cand"] = None, c.name
        v = pipeline.verify_candidate(f, c.body, timeout)
        wd = next(o for o in v["obligaciones"] if o.get("clase") == "buena-definicion")
        eq = next((o for o in v["obligaciones"] if o.get("clase") == "equivalencia"), None)
        obls.append({"obligacion": f"WD({c.name})", "clase": "WD", "estado": wd["estado"],
                     "testigo": wd.get("contraejemplo")})
        obls.append({"obligacion": f"REAL({c.name})", "clase": "REAL", "estado": v["estado"],
                     "testigo": (eq or wd).get("contraejemplo") if v["estado"] == "refutado" else None})
    CTX["obl"] = CTX["cand"] = None
    return obls


def _medir(fn):
    c0, t0, p0 = foto_contadores(), time.perf_counter(), time.process_time()
    r = fn()
    return r, {"contadores": delta(c0, foto_contadores()), "pared_s": time.perf_counter() - t0,
               "cpu_s": time.process_time() - p0}


# --- condición A ----------------------------------------------------------------------------------------------

def fase1_A(e, celda, desc, control):
    instalar_contadores()
    CTX["fase"] = 1
    estado = celda / "A-estado"                       # A no tiene estado persistente: se vigila un árbol vacío
    estado.mkdir(parents=True, exist_ok=True)
    mon = Monitor(estado, celda)
    obls, med = mon.operar("fase1-A", lambda: _medir(lambda: procedimiento(e["defn_d"], e["cands_d"])),
                           lambda: None, comprobar_store, permitidos={}, guarda=False)
    for o in obls:
        o["origen"] = "directa"
    return {"obligaciones": obls, "medida": med, "monitor": mon.registro}


# --- condición B ----------------------------------------------------------------------------------------------

def _monitor_B(celda, cache):
    mon = Monitor(celda / "B", celda)
    return mon, (lambda: json.loads(jdet(cache.memoria())))


def fase0_B(e, celda, desc, control):
    debajo = instalar_contadores()
    from efch import smt
    cache = CacheB(desc)
    smt.prove = cache.envolver(debajo, PREFIJO_KB1 if _es(control, 1) else "")
    CTX["fase"] = 0
    (celda / "B").mkdir(parents=True, exist_ok=True)
    mon, mem = _monitor_B(celda, cache)
    obls, med = mon.operar("fase0-B", lambda: _medir(lambda: procedimiento(e["defn_a"], e["cands_a"])), mem,
                           comprobar_cache)
    cache.guardar(celda / "B" / "cache-B.json")
    escribir(celda / "B" / "trazas-fase0.json", cache.trazas)
    return {"obligaciones": obls, "medida": med, "monitor": mon.registro,
            "modulos_prohibidos": sorted(m for m in sys.modules if m in ("efch.store", "efch.reglas"))}


def fase1_B(e, celda, desc, control):
    debajo = instalar_contadores()
    from efch import smt
    dirB = celda / ("BQ" if _clon_B(control) else "B")
    cache = CacheB(desc, dirB / "cache-B.json")
    trazas0 = len(cache.trazas)
    smt.prove = cache.envolver(debajo, PREFIJO_KB1 if _es(control, 1) else "")
    CTX["fase"] = 1
    mon = Monitor(dirB, celda)
    mem = lambda: json.loads(jdet(cache.memoria()))  # noqa: E731
    obls, med = mon.operar("fase1-B", lambda: _medir(lambda: procedimiento(e["defn_d"], e["cands_d"])), mem,
                           comprobar_cache)
    trazas = cache.trazas[trazas0:]
    for o in obls:
        ts = [t for t in trazas if t["obligacion"] == o["obligacion"]]
        o["origen"] = "memo" if ts and all(t["acierto"] for t in ts) else "directa"
        o["claves"] = [t["clave"] for t in ts]
    escribir(celda / "trazas-fase1.json", trazas)
    return {"obligaciones": obls, "medida": med, "monitor": mon.registro, "descartadas": cache.descartadas,
            "trazas": trazas,
            "modulos_prohibidos": sorted(m for m in sys.modules if m in ("efch.store", "efch.reglas"))}


# --- condición C ----------------------------------------------------------------------------------------------

def _es(control, n):
    return control is not None and control.split("-")[0] in (f"K{n}", f"KP{n}")


def _clon_C(control):
    return control is not None and any(_es(control, n) for n in (4, 5, 6, 7, 8))


def _clon_B(control):
    return control is not None and any(_es(control, n) for n in (4, 5, 6, 7, 8))


def _permitidos(**kw):
    return {"permitidos": {k: set(v) for k, v in kw.items()}}


def fase0_C(e, celda, desc, control):
    instalar_contadores()
    from efch import pipeline
    from efch import store as st
    raiz = celda / ("P" if _clon_C(control) else "almacen")
    mon = Monitor(raiz, celda)
    s = mon.operar("carga Store", lambda: st.Store(raiz), lambda: None, comprobar_store, permitidos={},
                   guarda=False)
    mon.verificar_carga(s)
    mem = lambda: memoria_store(s)  # noqa: E731
    traza_doble = []
    if _es(control, 3):                                 # K3/KP3: doble sobre verify_candidate visto por realize
        original = pipeline.verify_candidate

        def doble(*a, **k):
            v = original(*a, **k)
            antes = json.loads(jdet(v))
            ob = v["obligaciones"]
            if len(ob) == 2:
                ob[0]["obligacion"], ob[1]["obligacion"] = ob[1]["obligacion"], ob[0]["obligacion"]
            for o in ob:
                o["detalle"] = "(CBMC)"
            traza_doble.append({"antes": antes, "despues": json.loads(jdet(v))})
            return v
        pipeline.verify_candidate = doble
    nota = NOTA_REGISTER if _es(control, 1) else ""
    aceptadas, CTX["fase"] = [], 0
    c0, medidas = foto_contadores(), []

    def medida(fn):                                     # M5: solo la operación, sin las fotos del monitor
        r, m = _medir(fn)
        medidas.append(m)
        return r
    for n in ("h", "q", "f"):
        r = mon.operar(f"register {n}", lambda n=n: medida(lambda: st.register(
            s, e["defn_a"], e["texto_a"], n, timeout=TIMEOUT, note=nota)),
                       mem, comprobar_store, permitidos={"names": {n}}, guarda=True)
        aceptadas.append({"op": f"register {n}", "ok": r["aceptada"] is True})
    orden = list(e["cands_a"])
    if e["meta"].get("fase0_extra"):
        orden.append(e["cands_a"][0])                    # K4/KP4: segundo realize(c0) tras c2
    for c in orden:
        rid, v = mon.operar(f"realize {c.name}", lambda c=c: medida(lambda: st.realize(s, e["defn_a"], c,
                                                                                    timeout=TIMEOUT)),
                            mem, comprobar_store, permitidos={"reals": {f"f/{c.name}"}}, guarda=True)
        aceptadas.append({"op": f"realize {c.name}", "ok": v["estado"] == "probado"})
    escribir(celda / "disco-fase0.json", foto_disco(raiz))
    return {"aceptadas": aceptadas, "todas_aceptadas": all(a["ok"] for a in aceptadas),
            "contadores_fase0": delta(c0, foto_contadores()), "pared_fase0_s": sum(m["pared_s"] for m in medidas),
            "cpu_fase0_s": sum(m["cpu_s"] for m in medidas), "monitor": mon.registro, "doble_K3": traza_doble}


def _etiqueta(et):
    """'computacion:f:abc' -> ('computacion', 'f'); 'candidata:c0@f:abc' -> ('candidata', 'c0')."""
    tipo, nombre = et.split(":")[0], et.split(":")[1]
    return tipo, nombre.split("@")[0]


def _nombre_obligacion(fila):
    s = fila["sujetos"]
    if fila["clase"] == "WD":
        return f"WD({_etiqueta(s['objeto'])[1]})"
    if fila["clase"] in ("REAL", "REFUT"):
        return f"{fila['clase']}({_etiqueta(s['candidata'])[1]})"
    return fila["clase"]


def fase1_C(e, celda, desc, control):
    instalar_contadores()
    from efch import identidad as I
    from efch import store as st
    raiz = celda / ("Q" if _clon_C(control) else "almacen")
    mon = Monitor(raiz, celda)
    s = mon.operar("carga Store", lambda: st.Store(raiz), lambda: None, comprobar_store, permitidos={},
                   guarda=False)
    mon.verificar_carga(s)
    mem = lambda: memoria_store(s)  # noqa: E731
    X = e["meta"]["evoluciona"]
    nota = NOTA_EVOLVE if _es(control, 1) else ""
    CTX["fase"] = 1
    excepcion = None
    def op_evolve():
        r = _medir(lambda: st.evolve(s, e["defn_d"], e["texto_d"], X, timeout=TIMEOUT, note=nota,
                                     reverify_all=False, revalidar=True))
        inyectar(s, raiz, os.environ.get("EXP019_INYECCION"))       # fuera de lo medido (solo autopruebas)
        return r
    try:
        rep, med = mon.operar(f"evolve {X}", op_evolve, mem, comprobar_store, permitidos={"names": {X}},
                              guarda=True)
    except ParadaGlobal:
        raise
    except Exception as ex:  # noqa: BLE001 — rama de excepción de K5–K8 o celda inconclusa
        excepcion = {"tipo": type(ex).__name__, "repr": repr(ex), "codigo": getattr(ex, "codigo", None),
                     "ruta": getattr(ex, "ruta", None), "detalle": getattr(ex, "detalle", None),
                     "traza": traceback.format_exc()}
        return {"excepcion": excepcion, "monitor": mon.registro, "descartados": [list(x) for x in s.descartados]}
    vig = mon.operar("vigencia", lambda: s.vigencia(), mem, comprobar_store, permitidos={}, guarda=False)
    S_d, S_a = rep["instantanea_nueva"], rep["instantanea_anterior"]
    obls = []
    for fila in vig["afirmaciones"]:
        nombre = _nombre_obligacion(fila)
        o = {"obligacion": nombre, "clase": fila["clase"], "estado": fila["estado"], "certificado":
             fila["certificado"], "registro": fila["registro"], "regla": fila["regla"]}
        if fila["certificado"]:
            c = s.alm.t["certificados"][fila["certificado"]]
            o["origen"] = ("directa" if c["instantanea"] == S_d else "conservada") if c["regla"] == "directa" \
                else c["regla"]
        else:
            o["origen"] = "registro" if fila["registro"] else "ninguno"
        if fila["clase"] == "REAL":
            fil = next((x for x in rep["realizaciones"] if x["nombre"] == nombre[5:-1]), {})
            o["testigo"] = fil.get("contraejemplo") if o["estado"] == "refutado" else None
        obls.append(o)
    # emitidas en S_d (EQ y REFUT), para V2
    emitidas = []
    for c in s.alm.t["certificados"].values():
        a = s.alm.t["afirmaciones"].get(c["afirmacion"])
        if a and c["instantanea"] == S_d and a["clase"] in ("EQ", "REFUT"):
            suj = {p: _sujeto(s, i) for p, i in a["sujetos"].items()}
            emitidas.append({"certificado": c["id"], "clase": a["clase"], "estado": c["estado"], "sujetos": suj,
                             "contexto": a["contexto"]})
    for r in s.alm.t["registros"].values():
        a = s.alm.t["afirmaciones"].get(r["afirmacion"])
        if a and r["instantanea"] == S_d and a["clase"] == "EQ":
            emitidas.append({"registro": r["id"], "clase": "EQ", "estado": r["resultado"],
                             "sujetos": {p: _sujeto(s, i) for p, i in a["sujetos"].items()}, "contexto": a["contexto"]})
    # WD redundantes: demostradas de nuevo en S_d habiendo un certificado previo reutilizable en S_d
    Sobj = s.alm.t["instantaneas"][S_d]
    redundantes = 0
    for o in obls:
        if o["clase"] != "WD" or o["origen"] != "directa":
            continue
        af = s.alm.t["certificados"][o["certificado"]]["afirmacion"]
        previos = [c for c in s.alm.t["certificados"].values() if c["afirmacion"] == af and c["instantanea"] != S_d]
        if any(s.alm.reutilizable(c["id"], Sobj) is None for c in previos):
            redundantes += 1
    med["wd_redundantes"] = redundantes
    resumen = {k: rep.get(k) for k in ("aceptada", "relacion", "testigo", "instantanea_anterior", "instantanea_nueva",
                                        "instantanea_vigente", "rechazos_transferencia", "realizaciones",
                                        "equivalente_en_historial", "motivo_rechazo")}
    return {"obligaciones": [o for o in obls if o["clase"] != "REFUT"],
            "refut_en_vigencia": [o for o in obls if o["clase"] == "REFUT"], "emitidas": emitidas,
            "medida": med, "informe": resumen, "monitor": mon.registro, "S_a": S_a, "S_d": S_d,
            "descartados": [list(x) for x in s.descartados],
            "base_Sd": Sobj["base"], "nucleo_igual_descriptor": all(Sobj["base"].get(c) == desc[c] for c in NUCLEO),
            "_I": I.ESQUEMA}


def inyectar(s, raiz, tipo):
    """Solo para probar el monitor D11 (autopruebas, EXP019_INYECCION): modificaciones parciales deliberadas."""
    if not tipo:
        return
    raiz = pathlib.Path(raiz)
    if tipo in ("memoria", "excepcion_memoria"):
        cid = sorted(s.alm.t["certificados"])[0]
        s.alm.t["certificados"][cid] = {**s.alm.t["certificados"][cid], "estado": "refutado"}
    elif tipo == "indice":
        n = leer(raiz / "nombres.json")
        n["h"]["historial"][0]["nota"] = "alterada"
        escribir(raiz / "nombres.json", n)
        s.names["h"]["historial"][0]["nota"] = "alterada"
    elif tipo == "indice_disco":                     # I1: solo el archivo; la memoria no cambia
        n = leer(raiz / "nombres.json")
        n["h"]["historial"][0]["nota"] = "alterada solo en disco"
        escribir(raiz / "nombres.json", n)
    elif tipo == "archivo_nuevo":
        (raiz / "objetos" / "certificados" / ("0" * 64 + ".json")).write_text("{}")
    elif tipo == "archivo_previo":
        p = sorted((raiz / "definiciones").glob("*.json"))[0]
        p.write_text(p.read_text() + " ")
    if tipo.startswith("excepcion"):
        raise RuntimeError(f"inyección {tipo}")


def _sujeto(s, rid):
    v = s.alm.t["revisiones"][rid]
    r = s.alm.t["ranuras"][v["ranura"]]
    return {"revision": rid, "tipo": r["tipo"], "nombre": r["nombre"]}


# --- mutadores K/KB (esperado.json; sin efch) ---------------------------------------------------------------

def _objetos(raiz):
    out = {}
    for p in sorted((pathlib.Path(raiz) / "objetos").glob("*/*.json")):
        out[(p.parent.name, p.stem)] = json.loads(p.read_bytes())
    return out


def _refirmar(obj, excluidos=("id",)):
    sin = {k: v for k, v in obj.items() if k not in excluidos}
    return {**obj, "id": sha(canonico(sin))}


def _escribir_obj(raiz, tabla, obj):
    (pathlib.Path(raiz) / "objetos" / tabla / f"{obj['id']}.json").write_bytes(canonico(obj))


def localizar_A0_R0(raiz):
    """A0: única afirmación REAL con candidata = revisión de (candidata, ámbito f, c0); R0: su único certificado
    directa probado. Leyendo JSON, sin efch."""
    objs = _objetos(raiz)
    ranuras = {i: o for (t, i), o in objs.items() if t == "ranuras"}
    f_id = next(i for i, r in ranuras.items() if r["tipo"] == "computacion" and r["nombre"] == "f")
    c0_ranura = [i for i, r in ranuras.items() if r["tipo"] == "candidata" and r["nombre"] == "c0" and
                 r["ambito"] == f_id]
    revs_c0 = [i for (t, i), o in objs.items() if t == "revisiones" and o["ranura"] in c0_ranura]
    A0s = [o for (t, i), o in objs.items() if t == "afirmaciones" and o.get("clase") == "REAL" and
           o["sujetos"].get("candidata") in revs_c0]
    out = {"revisiones_c0": revs_c0, "A0": [a["id"] for a in A0s]}
    if len(A0s) != 1:
        return out
    A0 = A0s[0]
    R0s = [o for (t, i), o in objs.items() if t == "certificados" and o["afirmacion"] == A0["id"] and
           o["regla"] == "directa" and o["estado"] == "probado"]
    out["R0"] = [r["id"] for r in R0s]
    referencias = sorted(f"{t}/{i}" for (t, i), o in objs.items()
                         if (t, i) not in (("afirmaciones", A0["id"]),) and
                         (A0["id"] in json.dumps(o) or any(r["id"] in json.dumps(o) for r in R0s)) and
                         not (t == "certificados" and i in out["R0"]))
    out["referencias_ajenas"] = referencias
    return out


def mutar_C(control, P, Q):
    """Copia P→Q y aplica la mutación de K4–K8 (esperado.json). Devuelve el registro de la intervención."""
    shutil.copytree(P, Q)
    rec = {"control": control}
    Q = pathlib.Path(Q)
    if _es(control, 4):
        costes = leer(Q / "costes.json")
        ordenes = [v["orden"] for v in costes.values() if isinstance(v.get("orden"), (int, float))]
        mx, mn = max(ordenes), min(ordenes)
        for v in costes.values():
            if isinstance(v.get("segundos"), (int, float)) and not isinstance(v.get("segundos"), bool):
                v["segundos"] = v["segundos"] * 1000
            if isinstance(v.get("orden"), (int, float)):
                v["orden"] = mx + mn - v["orden"]
        escribir(Q / "costes.json", costes)
        rec["previsto"] = {"cambiados": ["costes.json"], "nuevos": [], "borrados": []}
        return rec
    loc = localizar_A0_R0(Q)
    rec["localizacion"] = loc
    if len(loc.get("A0", [])) != 1 or len(loc.get("R0", [])) != 1:
        rec["error"] = "A0 o R0 no únicos"
        return rec
    objs = _objetos(Q)
    A0 = objs[("afirmaciones", loc["A0"][0])]
    R0 = objs[("certificados", loc["R0"][0])]
    nuevos, borrados = [], []
    if _es(control, 5) or _es(control, 6):
        A1 = {k: v for k, v in A0.items() if k != "clase"} if _es(control, 5) else {**A0, "clase": "WD"}
        A1 = _refirmar(A1)
        R1 = _refirmar({**R0, "afirmacion": A1["id"]})
        _escribir_obj(Q, "afirmaciones", A1)
        (Q / "objetos" / "afirmaciones" / f"{A0['id']}.json").unlink()
        nuevos.append(f"objetos/afirmaciones/{A1['id']}.json")
        borrados.append(f"objetos/afirmaciones/{A0['id']}.json")
        rec["A0'"] = A1["id"]
    else:
        base = dict(R0["base"])
        if _es(control, 7):
            base.pop("z3", None)
        else:
            base["z3"] = "4.8.0:otra"
        R1 = _refirmar({**R0, "base": base})
    _escribir_obj(Q, "certificados", R1)
    (Q / "objetos" / "certificados" / f"{R0['id']}.json").unlink()
    nuevos.append(f"objetos/certificados/{R1['id']}.json")
    borrados.append(f"objetos/certificados/{R0['id']}.json")
    rec.update({"A0": A0["id"], "R0": R0["id"], "R0'": R1["id"]})
    costes = leer(Q / "costes.json")
    if R0["id"] in costes:
        costes[R1["id"]] = costes.pop(R0["id"])
    escribir(Q / "costes.json", costes)
    rec["previsto"] = {"cambiados": ["costes.json"], "nuevos": nuevos, "borrados": borrados}
    return rec


def comprobar_intervencion(P, Q, previsto):
    dp, dq = foto_disco(P), foto_disco(Q)
    cambiados = sorted(k for k in dp if k in dq and dp[k] != dq[k])
    nuevos = sorted(k for k in dq if k not in dp)
    borrados = sorted(k for k in dp if k not in dq)
    real = {"cambiados": cambiados, "nuevos": nuevos, "borrados": borrados}
    return {"real": real, "exacto": real == {k: sorted(v) for k, v in previsto.items()}}


def mutar_B(control, P, Q, clave_E0):
    shutil.copytree(P, Q)
    ruta = pathlib.Path(Q) / "cache-B.json"
    c = leer(ruta)
    rec = {"control": control, "E0": clave_E0}
    if _es(control, 4):
        c["entradas"] = list(reversed(c["entradas"]))
        escribir(ruta, c)
        rec["previsto"] = "orden invertido"
        return rec
    idx = next((i for i, x in enumerate(c["entradas"]) if x["clave"] == clave_E0), None)
    if idx is None:
        rec["error"] = "E0 no está en la caché"
        return rec
    e = dict(c["entradas"][idx])
    lineas = e["texto"].split("\n")
    if _es(control, 5):
        e["texto"] = "\n".join([lineas[0]] + lineas[2:])               # sin la línea de tipos; clave intacta
    else:
        if _es(control, 6):
            lineas[1] = ",".join(_mas_uno(t) for t in lineas[1].split(","))
        elif _es(control, 7):
            lineas = lineas[:-1]
        else:
            b = json.loads(lineas[-1])
            b["z3"] = "4.8.0:otra"
            lineas[-1] = canonico(b).decode()
        e["texto"] = "\n".join(lineas)
        e["clave"] = sha(e["texto"])
    c["entradas"][idx] = e
    escribir(ruta, c)
    rec.update({"E0'": e["clave"], "texto_E0'": e["texto"]})
    return rec


def _mas_uno(t):
    nombre, tipo = t.split(":")
    if tipo.startswith("(bv "):
        return f"{nombre}:(bv {int(tipo[4:-1]) + 1})"
    return t


# --- normativo y testigos -------------------------------------------------------------------------------------

def normativo(almacen, salida, out):
    """Segunda opinión con el validador normativo congelado (especificacion/), sin efch: para cada raíz usada en S_d
    (también las conservadas ajenas al cambio), un paquete con su cadena completa (premisas, procedencia,
    afirmaciones, revisiones con sus dependencias, ranuras e instantáneas S_a, S_x y S_d) y `reutilizable(raíz, S_d)`;
    las premisas se validan en su propio contexto dentro de la cadena (reglas.Validador)."""
    from especificacion import reglas as R
    from especificacion.contrato import Rechazo
    sal = leer(salida)
    objs = _objetos(almacen)
    tabla = lambda t: {i: o for (tt, i), o in objs.items() if tt == t}  # noqa: E731
    certs, afs, revs, rans, insts = tabla("certificados"), tabla("afirmaciones"), tabla("revisiones"), \
        tabla("ranuras"), tabla("instantaneas")
    raices = sorted({o["certificado"] for o in sal.get("obligaciones", []) if o.get("certificado")})
    res = {"raices": {}, "error_paquete": None, "paquetes": {}}
    for raiz in raices:
        usados_c, pila = set(), [raiz]
        while pila:
            c = pila.pop()
            if c in usados_c or c not in certs:
                continue
            usados_c.add(c)
            pila += list(certs[c]["premisas"].values()) + ([certs[c]["procedencia"]] if certs[c]["procedencia"]
                                                           else [])
        p = {"esquema": "efch-evidencia/2.5", "ranuras": {}, "revisiones": {}, "instantaneas": {},
             "afirmaciones": {}, "certificados": {}, "registros": {}}
        pila_r = []
        for c in usados_c:
            p["certificados"][c] = certs[c]
            a = afs.get(certs[c]["afirmacion"])
            if a:
                p["afirmaciones"][a["id"]] = a
                pila_r += list(a["sujetos"].values())
            if certs[c]["instantanea"] in insts:
                p["instantaneas"][certs[c]["instantanea"]] = insts[certs[c]["instantanea"]]
            pila_r += list(certs[c]["cierre"].values())
        for sid in (sal.get("S_a"), sal.get("S_d")):
            if sid in insts:
                p["instantaneas"][sid] = insts[sid]
        while pila_r:
            r = pila_r.pop()
            if r in p["revisiones"] or r not in revs:
                continue
            p["revisiones"][r] = revs[r]
            pila_r += list(revs[r]["dependencias"].values())
        for v in list(p["revisiones"].values()):
            rr = rans.get(v["ranura"])
            if rr:
                p["ranuras"][rr["id"]] = rr
                if rr.get("ambito") and rr["ambito"] in rans:
                    p["ranuras"][rr["ambito"]] = rans[rr["ambito"]]
        res["paquetes"][raiz] = {t: sorted(p[t]) for t in p if t != "esquema"}
        try:
            R.Validador(p).reutilizable(raiz, sal["S_d"])
            res["raices"][raiz] = {"ok": True}
        except Rechazo as e:
            res["raices"][raiz] = {"ok": False, "codigo": e.codigo, "ruta": e.ruta, "detalle": e.detalle}
    res["modulos_efch"] = sorted(m for m in sys.modules if m.startswith("efch"))
    escribir(out, res)


def testigos(entrada, salida, out):
    """O4 e I3: cada testigo emitido se evalúa en efch.interp.run (sobre S_d), y se guardan además las tablas
    exhaustivas del intérprete (S_a y S_d), segundo árbitro de toda contradicción de estados con O1."""
    from efch import interp
    e = cargar_entrada(entrada)
    sal = leer(salida)
    comps = e["defn_d"].computations
    cands = {c.name: c for c in e["cands_d"]}
    comps_a = e["defn_a"].computations
    res = []

    def val(cuerpo, inputs, w):
        args = [w[n] for n, _ in inputs]
        try:
            return interp.run(cuerpo, inputs, args)
        except interp.Undefined:
            return "indefinido"
    for o in sal.get("obligaciones", []):
        if o.get("estado") == "refutado" and o.get("testigo"):
            w = o["testigo"]
            nombre = o["obligacion"][o["obligacion"].index("(") + 1:-1]
            if o["clase"] == "REAL":
                res.append({"obligacion": o["obligacion"], "testigo": w,
                            "cand": val(cands[nombre].body, comps["f"].inputs, w), "f_d": val(comps["f"], comps["f"].inputs, w)})
            else:
                res.append({"obligacion": o["obligacion"], "testigo": w, "nota": "WD refutada con testigo"})
    for x in sal.get("emitidas", []):
        if x["clase"] == "REFUT":
            w = x["contexto"]["testigo"]
            c = x["sujetos"]["candidata"]["nombre"]
            res.append({"refut": x["certificado"], "cand": c, "testigo": w,
                        "cand_v": val(cands[c].body, comps["f"].inputs, w), "f_d": val(comps["f"], comps["f"].inputs, w)})
    t = (sal.get("informe") or {}).get("testigo")
    if t:
        n = leer(pathlib.Path(entrada) / "meta.json")["evoluciona"]
        res.append({"eq_testigo": t, "computacion": n, "n_d": val(comps[n], comps[n].inputs, t),
                    "n_a": val(comps_a[n], comps_a[n].inputs, t)})
    w = int(comps["f"].output[1])
    tablas = {"S_d": {n: [val(c, c.inputs, {c.inputs[0][0]: x}) for x in range(1 << w)] for n, c in comps.items()},
              "S_a": {n: [val(c, c.inputs, {c.inputs[0][0]: x}) for x in range(1 << w)] for n, c in comps_a.items()}}
    for c in e["cands_d"]:
        tablas["S_d"][c.name] = [val(c.body, comps["f"].inputs, {comps["f"].inputs[0][0]: x}) for x in range(1 << w)]
    escribir(out, {"testigos": res, "tablas_interp": tablas})


# --- punto de entrada de los subprocesos --------------------------------------------------------------------

FASES = {("0", "B"): fase0_B, ("0", "C"): fase0_C, ("1", "A"): fase1_A, ("1", "B"): fase1_B, ("1", "C"): fase1_C}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("modo")
    ap.add_argument("pos", nargs="?")
    ap.add_argument("--cond")
    ap.add_argument("--entrada")
    ap.add_argument("--celda")
    ap.add_argument("--descriptor")
    ap.add_argument("--control")
    ap.add_argument("--almacen")
    ap.add_argument("--salida")
    ap.add_argument("--out")
    ap.add_argument("--clave-E0")
    a = ap.parse_args()
    if "evaluacion" in str(a.entrada or "") and os.environ.get("EXP019_AUTORIZACION_EVALUACION") is None:
        sys.exit("arnes: evaluacion/ no está autorizada")
    if a.modo == "descriptor":
        from efch import store as st
        escribir(a.pos, st.base_registro())
        return 0
    if a.modo == "normativo":
        normativo(a.almacen, a.salida, a.out)
        return 0
    if a.modo == "testigos":
        testigos(a.entrada, a.salida, a.out)
        return 0
    if a.modo == "mutarC":
        rec = mutar_C(a.control, a.almacen, a.out)
        rec["intervencion"] = comprobar_intervencion(a.almacen, a.out, rec.get("previsto", {})) \
            if isinstance(rec.get("previsto"), dict) else None
        escribir(pathlib.Path(a.celda) / "mutacion.json", rec)
        return 0
    if a.modo == "mutarB":
        rec = mutar_B(a.control, a.almacen, a.out, a.clave_E0)
        d0, d1 = foto_disco(a.almacen), foto_disco(a.out)
        rec["diff"] = sorted(k for k in set(d0) | set(d1) if d0.get(k) != d1.get(k))
        escribir(pathlib.Path(a.celda) / "mutacion-B.json", rec)
        return 0
    fase = a.modo[-1]
    celda = pathlib.Path(a.celda)
    celda.mkdir(parents=True, exist_ok=True)
    nombre = celda / f"fase{fase}.json"
    try:
        e = cargar_entrada(a.entrada)
        r = FASES[fase, a.cond](e, celda, leer(a.descriptor), a.control)
        r.pop("_I", None)
        escribir(nombre, {"ok": True, **r})
        return 0
    except ParadaGlobal as ex:
        escribir(nombre, {"ok": False, "parada_global": str(ex), "traza": traceback.format_exc()})
        return 3
    except Exception as ex:  # noqa: BLE001
        escribir(nombre, {"ok": False, "error": repr(ex), "traza": traceback.format_exc()})
        return 1


if __name__ == "__main__":
    sys.exit(main())
