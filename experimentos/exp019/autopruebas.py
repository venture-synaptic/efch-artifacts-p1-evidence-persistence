"""EXP-019, O5: autopruebas del instrumento (solo preparación; ficha §Oráculos O5 y §M7).

    python3 experimentos/exp019/autopruebas.py --salida resultados/exp019/preparacion/autopruebas

1. O1 frente a efch.interp: 1000 expresiones (SEMILLA_AUTOPRUEBA = 20261103), gramática {literal, x, add, sub, xor,
   or, mul, neg, call h}, profundidad ≤ 4, w de 1 a 8; se descarta y regenera toda expresión cuyo texto normalizado
   coincida con un cuerpo, variante o cuerpo cambiado de la evaluación (lista tomada del texto de la ficha, §Modelo;
   no se lee ni se regenera evaluacion/).
2. Remapeo de B: dos llamadas de estructura idéntica con entradas `x` e `y`, una refutada.
3. Monitor D11: sin falsos positivos en operaciones normales; detección de modificaciones parciales en memoria,
   índices, archivos nuevos y archivos previos, con y sin excepción; parada real del lanzador (subproceso).
4. Sensibilidad de O2, del validador normativo y del confirmador de fuentes con certificados y revisiones alterados.
(El contador frente a Solver.check, las mutaciones KP/KBP, O2 frente al normativo y el determinismo se comprueban en
cada ejecución de la preparación y se resumen en el análisis.)
"""

import argparse
import json
import pathlib
import random
import shutil
import subprocess
import sys

AQUI = pathlib.Path(__file__).resolve().parent
RAIZ = AQUI.parents[1]
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(AQUI))

SEMILLA_AUTOPRUEBA = 20261103
OPS2 = ("add", "sub", "xor", "or", "mul")


def exclusion():
    """Cuerpos, variantes y cambios de la evaluación según el texto de la ficha (§Modelo)."""
    B = ["x", "0", "(add x 1)", "(call h x)"]
    out = set(B) | {"1", "(add x 1)"}
    for b in B:
        out |= {f"(add 0 {b})", f"(sub (add {b} 1) 1)", f"(add {b} 0)", f"(add {b} 1)"}
    return {" ".join(x.split()) for x in out}


def expr(rng, prof, w, con_call=True):
    if prof == 0 or rng.random() < 0.25:
        return "x" if rng.random() < 0.5 else str(rng.randrange(1 << w))
    k = rng.choice(OPS2 + ("neg",) + (("call",) if con_call else ()))
    if k == "neg":
        return f"(neg {expr(rng, prof - 1, w, con_call)})"
    if k == "call":
        return f"(call h {expr(rng, prof - 1, w, con_call)})"
    return f"({k} {expr(rng, prof - 1, w, con_call)} {expr(rng, prof - 1, w, con_call)})"


def prueba_oraculo():
    from efch import core, interp
    rng = random.Random(SEMILLA_AUTOPRUEBA)
    excl, casos, descartadas = exclusion(), [], 0
    while len(casos) < 1000:
        w = rng.randint(1, 8)
        h, e = expr(rng, 2, w, False), expr(rng, 4, w)
        if " ".join(e.split()) in excl or " ".join(h.split()) in excl:
            descartadas += 1
            continue
        casos.append({"w": w, "h": h, "e": e})
    p = subprocess.run([sys.executable, "-I", str(AQUI / "oraculo.py"), "expresiones"], input=json.dumps(casos),
                       capture_output=True, text=True, cwd=RAIZ)
    tablas = json.loads(p.stdout)
    discrepancias = []
    for c, t in zip(casos, tablas):
        w = c["w"]
        texto = (f"(efch 0.1 (computation h (input x (bv {w})) (output (bv {w})) (semantics {c['h']}))"
                 f" (computation e (input x (bv {w})) (output (bv {w})) (semantics {c['e']})))")
        comp = core.load_definition(texto).computations["e"]
        ef = [interp.run(comp, comp.inputs, [x]) for x in range(1 << w)]
        if ef != t:
            discrepancias.append({**c, "oraculo": t, "interp": ef})
    return {"casos": len(casos), "descartadas_por_exclusion": descartadas, "discrepancias": discrepancias,
            "ok": not discrepancias}


def prueba_remapeo():
    import arnes
    from efch import smt
    from efch._z3 import z3
    debajo = arnes.instalar_contadores()
    cache = arnes.CacheB({c: "d" for c in arnes.NUCLEO})
    smt.prove = cache.envolver(debajo)
    vistos = []

    def confirm(nombre):
        def f(valores):
            vistos.append(sorted(valores))
            return (set(valores) == {nombre} and valores[nombre] != 3), f"{nombre}={valores.get(nombre)}"
        return f
    out = []
    for n in ("x", "y"):
        v = z3.BitVec(n, 4)
        c0 = arnes.CONT["prove"]
        r = smt.prove(f"sintética {n}", v == 3, [], 30, [(n, ("bv", 4), v)], confirm(n))
        out.append({"nombre": n, "estado": r.status, "contraejemplo": r.counterexample, "delegada":
                    arnes.CONT["prove"] - c0 == 1, "acierto": cache.trazas[-1]["acierto"],
                    "result_nombre": r.obligation})
    ok = out[0]["estado"] == out[1]["estado"] == "refutado" and out[0]["delegada"] and not out[1]["delegada"] and \
        out[1]["acierto"] and set(out[1]["contraejemplo"]) == {"y"} and vistos[-1] == ["y"] and \
        out[1]["result_nombre"] == "sintética y"
    return {"llamadas": out, "claves_confirm": vistos, "ok": ok}


def prueba_monitor(dirp):
    import arnes
    from efch import store as st
    E = AQUI / "preparacion" / "P-w5-xor1-eq"
    e = arnes.cargar_entrada(E)
    raiz = dirp / "almacen-normal"
    mon = arnes.Monitor(raiz, dirp / "normal")
    res = {"falsos_positivos": None, "detecciones": {}}
    try:
        s = mon.operar("carga", lambda: st.Store(raiz), lambda: None, arnes.comprobar_store, permitidos={},
                       guarda=False)
        mem = lambda: arnes.memoria_store(s)  # noqa: E731
        for n in ("h", "q", "f"):
            mon.operar(f"register {n}", lambda n=n: st.register(s, e["defn_a"], e["texto_a"], n, timeout=120),
                       mem, arnes.comprobar_store, permitidos={"names": {n}}, guarda=True)
        for c in e["cands_a"]:
            mon.operar(f"realize {c.name}", lambda c=c: st.realize(s, e["defn_a"], c, timeout=120), mem,
                       arnes.comprobar_store, permitidos={"reals": {f"f/{c.name}"}}, guarda=True)
        mon.operar("evolve f", lambda: st.evolve(s, e["defn_d"], e["texto_d"], "f", timeout=120, revalidar=True),
                   mem, arnes.comprobar_store, permitidos={"names": {"f"}}, guarda=True)
        mon.operar("vigencia", lambda: s.vigencia(), mem, arnes.comprobar_store, permitidos={}, guarda=False)
        try:
            mon.operar("excepción limpia", lambda: (_ for _ in ()).throw(ValueError("limpia")), mem,
                       arnes.comprobar_store, permitidos={}, guarda=True)
        except ValueError:
            pass
        res["falsos_positivos"] = [r for r in mon.registro if r["problemas"]]
    except arnes.ParadaGlobal as ex:
        res["falsos_positivos"] = [str(ex)]

    def caso(nombre, op, guarda=True, permitidos=None):
        r2 = dirp / f"almacen-{nombre}"
        shutil.copytree(raiz, r2)
        s2 = st.Store(r2)
        m2 = arnes.Monitor(r2, dirp / nombre)
        try:
            m2.operar(nombre, lambda: op(s2, r2), lambda: arnes.memoria_store(s2), arnes.comprobar_store,
                      permitidos=permitidos or {}, guarda=guarda)
            res["detecciones"][nombre] = {"detectada": False}
        except arnes.ParadaGlobal as ex:
            res["detecciones"][nombre] = {"detectada": True, "problemas": str(ex)[:400]}
        except Exception as ex:  # noqa: BLE001
            res["detecciones"][nombre] = {"detectada": False, "excepcion": repr(ex)}

    def mem_obj(s2, r2):
        cid = sorted(s2.alm.t["certificados"])[0]
        s2.alm.t["certificados"][cid] = {**s2.alm.t["certificados"][cid], "estado": "refutado"}

    def indice(s2, r2):
        s2.names["h"]["historial"][0]["nota"] = "alterada"
        s2.guardar()

    def nuevo_fuera(s2, r2):
        (r2 / "basura.json").write_text("{}")

    def nuevo_objeto(s2, r2):
        (r2 / "objetos" / "certificados" / ("0" * 64 + ".json")).write_text("{}")

    def previo(s2, r2):
        p = sorted((r2 / "objetos" / "revisiones").glob("*.json"))[0]
        p.write_bytes(p.read_bytes() + b" ")

    def exc_memoria(s2, r2):                       # patrón D11: memoria modificada y excepción, disco intacto
        a = next(iter(s2.alm.t["afirmaciones"].values()))
        s2.alm.t["afirmaciones"]["f" * 64] = {**a, "id": "f" * 64}
        raise RuntimeError("D11 simulado")

    def exc_indice(s2, r2):
        (r2 / "costes.json").write_text((r2 / "costes.json").read_text().replace("{", "{ ", 1))
        raise RuntimeError("índice escrito y excepción")

    def exc_nuevo(s2, r2):
        (r2 / "pasos" / "9999-parcial.json").write_text("{}")
        raise RuntimeError("archivo nuevo y excepción")
    def indice_solo_disco(s2, r2):                 # I1: solo el archivo, sin tocar s.names
        n = json.loads((r2 / "nombres.json").read_text())
        n["h"]["historial"][0]["nota"] = "alterada solo en disco"
        (r2 / "nombres.json").write_text(json.dumps(n))     # s2.names no cambia
    caso("memoria-objeto-previo", mem_obj)
    caso("indice-solo-disco", indice_solo_disco)
    caso("indice-historial", indice)
    caso("archivo-nuevo-no-previsto", nuevo_fuera)
    caso("archivo-nuevo-sin-objeto", nuevo_objeto)
    caso("archivo-previo-cambiado", previo)
    caso("excepcion-memoria", exc_memoria)
    caso("excepcion-indice", exc_indice)
    caso("excepcion-archivo-nuevo", exc_nuevo)
    res["ok"] = res["falsos_positivos"] == [] and all(d["detectada"] for d in res["detecciones"].values())
    return res


def prueba_parada(dirp):
    """Parada real: ejecutar.py con una inyección en evolve; tiene que devolver 3 y dejar PARADA.json."""
    out = {}
    for tipo in ("memoria", "indice", "indice_disco", "archivo_nuevo", "archivo_previo", "excepcion_memoria"):
        sal = dirp / f"parada-{tipo}"
        p = subprocess.run([sys.executable, str(AQUI / "ejecutar.py"), "--preparacion", "--reps", "1", "--solo",
                            "P-w5-xor1-q", "--salida", str(sal)], cwd=RAIZ, capture_output=True, text=True,
                           env={**__import__("os").environ, "EXP019_INYECCION": tipo}, timeout=1800)
        jsonl = (sal / "ejecucion.jsonl").read_text().splitlines() if (sal / "ejecucion.jsonl").exists() else []
        out[tipo] = {"rc": p.returncode, "parada": (sal / "PARADA.json").exists(),
                     "ejecuciones_registradas": len(jsonl), "salida": p.stdout[-300:]}
    out["ok"] = all(v["rc"] == 3 and v["parada"] for v in out.values() if isinstance(v, dict))
    return out


def prueba_sensibilidad_O2(dirp):
    """Controles negativos del contraste: certificados y revisiones alterados en una copia de un almacén de C."""
    import arnes
    E = AQUI / "preparacion" / "P-w5-xor1-eq"
    cel = dirp / "base-C"
    desc = dirp / "desc.json"
    subprocess.run([sys.executable, str(AQUI / "arnes.py"), "descriptor", str(desc)], cwd=RAIZ, check=True)
    for f in ("fase0", "fase1"):
        subprocess.run([sys.executable, str(AQUI / "arnes.py"), f, "--cond", "C", "--entrada", str(E), "--celda",
                        str(cel), "--descriptor", str(desc)], cwd=RAIZ, check=True,
                       env={**__import__("os").environ, "PYTHONHASHSEED": "0"})
    f1 = json.loads((cel / "fase1.json").read_text())
    raiz = cel / "almacen"
    res = {}

    def correr(nombre, mutar):
        r2 = dirp / f"sens-{nombre}"
        shutil.copytree(raiz, r2)
        sal = json.loads(json.dumps(f1))
        mutar(r2, sal)
        (r2 / "fase1.json").write_text(json.dumps(sal))
        subprocess.run([sys.executable, "-I", str(AQUI / "contraste.py"), "--entrada", str(E), "--almacen", str(r2),
                        "--salida", str(r2 / "fase1.json"), "--descriptor", str(desc), "--out",
                        str(r2 / "o2.json")], cwd=RAIZ, check=True)
        subprocess.run([sys.executable, str(AQUI / "arnes.py"), "normativo", "--almacen", str(r2), "--salida",
                        str(r2 / "fase1.json"), "--out", str(r2 / "norm.json")], cwd=RAIZ, check=True)
        subprocess.run([sys.executable, "-I", str(AQUI / "confirmar_fuentes.py"), "--entrada", str(E), "--almacen",
                        str(r2), "--salida", str(r2 / "fase1.json"), "--out", str(r2 / "cf.json")], cwd=RAIZ,
                       check=True)
        o2, nor, cf = (json.loads((r2 / x).read_text()) for x in ("o2.json", "norm.json", "cf.json"))
        res[nombre] = {"o2_violaciones": o2["violaciones"], "o2_discrepancias": o2["discrepancias"],
                       "normativo_rechaza": [k[:12] for k, v in nor["raices"].items() if not v["ok"]],
                       "confirmador": cf["discrepancias"]}

    def obl(sal, nombre):
        return next(o for o in sal["obligaciones"] if o["obligacion"] == nombre)

    def reemplazar_cert(r2, sal, nombre, cambio):
        o = obl(sal, nombre)
        p = r2 / "objetos" / "certificados" / f"{o['certificado']}.json"
        c = cambio(json.loads(p.read_bytes()))
        c = arnes._refirmar(c)
        arnes._escribir_obj(r2, "certificados", c)
        o["certificado"] = c["id"]

    correr("sin-cambio", lambda r2, sal: None)
    correr("raiz-base-alterada", lambda r2, sal: reemplazar_cert(
        r2, sal, "WD(q)", lambda c: {**c, "base": {**c["base"], "efch-smt": "otra"}}))
    correr("raiz-cierre-alterado", lambda r2, sal: reemplazar_cert(
        r2, sal, "WD(c1)", lambda c: {**c, "cierre": {}}))
    correr("rreal-sin-premisa-eq", lambda r2, sal: reemplazar_cert(
        r2, sal, "REAL(c0)", lambda c: {**c, "premisas": {k: v for k, v in c["premisas"].items() if k != "eq"}}))

    def raiz_obsoleta(r2, sal):                    # REAL(c0) declarado con el certificado directo de S_a
        o = obl(sal, "REAL(c0)")
        orig = json.loads((r2 / "objetos" / "certificados" / f"{o['certificado']}.json").read_bytes())
        o["certificado"], o["origen"] = orig["procedencia"], "conservada"
    correr("raiz-obsoleta-conclusion-verdadera", raiz_obsoleta)

    def hash_roto(r2, sal):
        o = obl(sal, "WD(h)")
        p = r2 / "objetos" / "certificados" / f"{o['certificado']}.json"
        c = json.loads(p.read_bytes())
        c["via"] = "directa "
        p.write_bytes(arnes.canonico(c))
    correr("hash-roto", hash_roto)

    def fuente_revision(r2, sal):
        S = json.loads((r2 / "objetos" / "instantaneas" / f"{sal['S_d']}.json").read_bytes())
        for rid in S["revisiones"].values():
            p = r2 / "objetos" / "revisiones" / f"{rid}.json"
            v = json.loads(p.read_bytes())
            if "(computation q" in v["fuente"]:
                v["fuente"] = v["fuente"].replace("(semantics 0)", "(semantics 7)")
                p.write_bytes(arnes.canonico(v))
    correr("fuente-de-revision-alterada", fuente_revision)
    esperado = {"sin-cambio": False, "raiz-base-alterada": True, "raiz-cierre-alterado": True,
                "rreal-sin-premisa-eq": True, "raiz-obsoleta-conclusion-verdadera": True, "hash-roto": True}
    res["resumen"] = {k: {"o2_detecta": bool(res[k]["o2_violaciones"]), "normativo_rechaza": bool(
        res[k]["normativo_rechaza"]), "esperado": v} for k, v in esperado.items()}
    res["resumen"]["fuente-de-revision-alterada"] = {
        "o2_detecta": any(d["tipo"] == "enlace_fuente" for d in res["fuente-de-revision-alterada"]["o2_discrepancias"]),
        "confirmador_detecta": any(d["tipo"] == "fuente_distinta" for d in res["fuente-de-revision-alterada"][
            "confirmador"]), "normativo_rechaza": bool(res["fuente-de-revision-alterada"]["normativo_rechaza"]),
        "esperado": "O2 y el confirmador detectan; el normativo no decide este vínculo"}
    res["ok"] = all(v["o2_detecta"] == v["esperado"] and v["normativo_rechaza"] == v["esperado"]
                    for k, v in res["resumen"].items() if k != "fuente-de-revision-alterada") and \
        res["resumen"]["fuente-de-revision-alterada"]["o2_detecta"] and \
        res["resumen"]["fuente-de-revision-alterada"]["confirmador_detecta"]
    return res


def _copiar_celda(base, out, entrada, cond):
    dst = out / "rep1" / entrada / cond
    shutil.copytree(base / "rep1" / entrada / cond, dst)
    shutil.copy2(base / "base-descriptor.json", out / "base-descriptor.json")
    return dst


def _orac(e, conj, entrada):
    rc, out, err = e.lanzar_I("oraculo.py", ["tablas", str(conj / entrada)])
    assert rc == 0, err
    return json.loads(out)


def prueba_metapruebas(dirp):
    """Metapruebas: cada defecto plantado (negativos de Sol (a)–(e), V1c puro, I1–I6, precedencia y código de
    salida) tiene que **detectarse**; ninguno puede dar un «superado» falso ni una celda limpia."""
    import copy
    import os
    import ejecutar as e
    P = AQUI / "preparacion"
    base = dirp / "base"
    entradas = ["P-w5-xor1-neq", "P-w5-xor1-eq", "P-w5-xor1-q", "KP1-nota", "KP3-nombres-de-obligacion",
                "KP5-ausencia-de-clase", "KP6-contradiccion-de-clase"]
    rc = subprocess.run([sys.executable, str(AQUI / "ejecutar.py"), "--preparacion", "--reps", "1", "--salida",
                         str(base), "--solo", *entradas], cwd=RAIZ, capture_output=True, text=True).returncode
    an = json.loads((base / "analisis.json").read_text())
    cells = {(k.split("|")[0], k.split("|")[1], int(k.split("|")[2])): v for k, v in an["celdas"].items()}
    res = {"_base": {"rc": rc, "decision_R1": an["decision"]["R1"]["clase"]}}

    def leer(p):
        return json.loads(pathlib.Path(p).read_text())

    def esc(p, x):
        pathlib.Path(p).write_text(json.dumps(x, ensure_ascii=False, indent=1))

    def obl(f, n):
        return next(o for o in f["obligaciones"] if o["obligacion"] == n)

    def celda_alterada(nombre, entrada, alterar, conj=P):
        out = dirp / nombre
        dst = _copiar_celda(base, out, entrada, "C")
        f = leer(dst / "fase1.json")
        alterar(dst, f)
        esc(dst / "fase1.json", f)
        return e.analizar_celda(out, conj, 1, entrada, "C", _orac(e, conj, entrada))

    # (a) REAL(c0) obsoleta conservada tras neq: V1a confirmada
    def obsoleta(d, f):
        cs, afs = e._certs(d / "almacen"), e._afs(d / "almacen")
        c = next(c for c in cs.values() if c["regla"] == "directa" and c["estado"] == "probado" and
                 afs[c["afirmacion"]].get("clase") == "REAL" and e._es_c0(d / "almacen", afs[c["afirmacion"]]))
        obl(f, "REAL(c0)").update(certificado=c["id"], registro=None, regla="directa", origen="conservada",
                                   estado="probado", testigo=None)
    r = celda_alterada("a-obsoleta", "P-w5-xor1-neq", obsoleta)
    res["a-REAL-obsoleta"] = {"detectado": any(v["tipo"].startswith("V1") and v.get("confirmada")
                                               for v in r["violaciones"]), "violaciones": r["violaciones"]}

    # (b) REFUT con testigo falso sobre una igualdad real: V2 confirmada
    def refut_falsa(d, f):
        f["emitidas"].append({"clase": "REFUT", "certificado": "f" * 64, "estado": "probado",
                              "sujetos": {"candidata": {"nombre": "c0"}, "computacion": {"nombre": "f"}},
                              "contexto": {"testigo": {"x": 0}}})
    r = celda_alterada("b-testigo-falso", "P-w5-xor1-eq", refut_falsa)
    res["b-REFUT-testigo-falso"] = {"detectado": any(v["tipo"] == "V2" and "refut_falso" in v
                                                     for v in r["violaciones"]), "violaciones": r["violaciones"]}

    # V1c puro: la propuesta cambia solo el doc de f; el registro sigue normativamente válido
    conj = dirp / "v1c-entradas"
    shutil.copytree(P / "P-w5-xor1-q", conj / "P-w5-xor1-q")
    t = (conj / "P-w5-xor1-q" / "despues.efch").read_text()
    (conj / "P-w5-xor1-q" / "despues.efch").write_text(t.replace("(computation f", '(computation f (doc "sonda")', 1))
    r = celda_alterada("v1c-puro", "P-w5-xor1-q", lambda d, f: None, conj)
    res["V1c-puro"] = {"detectado": bool(r["violaciones"]) and all(v["tipo"] == "V1c" and v.get("confirmada")
                                                                   for v in r["violaciones"]),
                       "violaciones": r["violaciones"]}

    # I2: fallo técnico del subproceso de testigos: nunca una celda limpia
    original = e.lanzar

    def lanzar_fallido(args, *a, **k):
        if args[0] == "testigos":
            return {"rc": 1, "segundos": 0, "stderr": "fallo plantado del confirmador"}
        return original(args, *a, **k)
    e.lanzar = lanzar_fallido
    try:
        r = celda_alterada("I2-testigos-fallidos", "P-w5-xor1-eq", refut_falsa)
    finally:
        e.lanzar = original
    res["I2-confirmacion-fallida"] = {"detectado": bool(r["inconclusa"]) and any(
        c["tipo"] == "confirmacion_testigos_fallida" for c in r["calibracion"]), "inconclusa": r["inconclusa"]}

    # I3: V2 con un solo árbitro: no se confirma; con dos que coinciden, sí; si discrepan, calibración
    f = {"ok": True, "obligaciones": [{"obligacion": "REAL(c0)", "clase": "REAL", "estado": "probado"}]}
    o = {"S_d": {}, "REAL_d": {"c0": False}}
    v1, c1 = e.v2_celda(f, o, None, "C")
    v2, c2 = e.v2_celda(f, o, {"testigos": [], "tablas_interp": {"S_d": {"c0": [0], "f": [1]}, "S_a": {}}}, "C")
    v3, c3 = e.v2_celda(f, o, {"testigos": [], "tablas_interp": {"S_d": {"c0": [0], "f": [0]}, "S_a": {}}}, "C")
    res["I3-un-solo-arbitro"] = {"detectado": not v1 and bool(c1) and bool(v2) and not v3 and bool(c3),
                                 "sin_interprete": [v1, c1], "coinciden": v2, "discrepan": [v3, c3]}

    # (c) B mutante que acierta ignorando la clave (copia del instrumento; el original no se toca)
    copia = dirp / "copia-raiz"
    (copia / "experimentos").mkdir(parents=True)
    shutil.copytree(AQUI, copia / "experimentos" / "exp019", ignore=shutil.ignore_patterns("evaluacion",
                                                                                         "__pycache__"))
    for d in ("efch", "especificacion", ".vendor"):
        (copia / d).symlink_to(RAIZ / d)
    ar = copia / "experimentos" / "exp019" / "arnes.py"
    marca = "e = self.entradas.get(clave) if clave else None"
    txt = ar.read_text()
    assert txt.count(marca) == 1
    ar.write_text(txt.replace(marca, "e = next(iter(self.entradas.values()), None)"))
    out = dirp / "c-B-mutante"
    cel = out / "rep1" / "P-w5-xor1-neq" / "B"
    out.mkdir(parents=True)
    shutil.copy2(base / "base-descriptor.json", out / "base-descriptor.json")
    for fz in ("fase0", "fase1"):
        subprocess.run([sys.executable, str(ar), fz, "--cond", "B", "--entrada", str(P / "P-w5-xor1-neq"),
                        "--celda", str(cel), "--descriptor", str(out / "base-descriptor.json")], cwd=RAIZ,
                       env={**os.environ, "PYTHONHASHSEED": "0"}, capture_output=True)
    r = e.analizar_celda(out, P, 1, "P-w5-xor1-neq", "B", _orac(e, P, "P-w5-xor1-neq"))
    res["c-B-aciertos-indebidos"] = {"detectado": bool(r["calibracion"]), "calibracion": r["calibracion"][:3]}

    # evaluadores de controles con resultados falsificados (sobre una copia de la base)
    falsa = dirp / "base-falsificada"
    shutil.copytree(base, falsa)
    e.SALIDA_GLOBAL["salida"] = falsa
    k = "KP5-ausencia-de-clase"
    m = leer(falsa / "rep1" / k / "C" / "mutacion.json")
    m["intervencion"]["exacto"] = False
    esc(falsa / "rep1" / k / "C" / "mutacion.json", m)
    r = e.evaluar_C(k, leer(P / k / "esperado.json"), cells[k, "C", 1], cells, 1, P, falsa)
    res["d-KP5-veto-no-ejercitado"] = {"detectado": r["resultado"] == "inconcluso", "observado": r["resultado"]}
    k = "KP6-contradiccion-de-clase"
    c = copy.deepcopy(cells[k, "B", 1])
    c["n"] += 1
    r = e.evaluar_B(k, leer(P / k / "esperado.json"), c, cells, 1, falsa)
    res["d-KB6-coste-falso"] = {"detectado": r["resultado"].startswith("fallo"), "observado": r["resultado"]}
    # I4: K3 sin intervención real (despues = antes, tres llamadas)
    k = "KP3-nombres-de-obligacion"
    f0 = leer(falsa / "rep1" / k / "C" / "fase0.json")
    for tr in f0["doble_K3"]:
        tr["despues"] = copy.deepcopy(tr["antes"])
    esc(falsa / "rep1" / k / "C" / "fase0.json", f0)
    r = e.evaluar_C(k, leer(P / k / "esperado.json"), cells[k, "C", 1], cells, 1, P, falsa)
    res["I4-K3-sin-intervencion"] = {"detectado": r["resultado"] == "inconcluso", "observado": r["resultado"]}
    # I5: clave falsificada en una traza ajena a E0 (KB6)
    k = "KP6-contradiccion-de-clase"
    pt = falsa / "rep1" / k / "B" / "trazas-fase1.json"
    trz = leer(pt)
    mb = leer(falsa / "rep1" / k / "B" / "mutacion-B.json")
    i = next(i for i, t in enumerate(trz) if t["clave"] != mb["E0"] and t["obligacion"] != "WD(c0)")
    trz[i]["clave"] = "0" * 64
    esc(pt, trz)
    r = e.evaluar_B(k, leer(P / k / "esperado.json"), cells[k, "B", 1], cells, 1, falsa)
    res["I5-B-resto-distinto"] = {"detectado": r["resultado"].startswith("fallo"), "observado": r["resultado"]}
    # I6: el gemelo se toma de esperado.json (nombre ficticio del mismo gemelo de preparación)
    e.SALIDA_GLOBAL["salida"] = base
    k = "KP1-nota"
    esp = leer(P / k / "esperado.json")
    esp["gemelo"] = "GEMELO-FICTICIO-DE-PREPARACION"
    cs = {**cells, (esp["gemelo"], "B", 1): cells["P-w5-xor1-eq", "B", 1]}
    r = e.evaluar_B(k, esp, cells[k, "B", 1], cs, 1, base)
    res["I6-gemelo-parametrico"] = {"detectado": r["resultado"] == "superado" and r.get("gemelo") == esp["gemelo"],
                                    "observado": r}

    # precedencia y código de salida: calibración plantada ⇒ comparación parada y rc ≠ 0
    plantada = dirp / "base-calibracion"
    shutil.copytree(base, plantada)
    f1p = plantada / "rep1" / "P-w5-xor1-q" / "A" / "fase1.json"
    f1 = leer(f1p)
    f1["medida"]["contadores"]["check"] += 1
    esc(f1p, f1)
    p2 = subprocess.run([sys.executable, str(AQUI / "ejecutar.py"), "--preparacion", "--reps", "1",
                         "--solo-analisis", "--salida", str(plantada)], cwd=RAIZ, capture_output=True, text=True)
    dec = leer(plantada / "analisis.json")["decision"]
    res["precedencia-calibracion-rc"] = {"detectado": p2.returncode == 2 and dec["precedencia"] == 2 and
                                         str(dec["R2"]).startswith("no informado"),
                                         "rc": p2.returncode, "precedencia": dec["precedencia"]}
    ag = copy.deepcopy(an["agregado"])
    ag["P-w5-xor1-eq|C"]["violaciones"] = [{"tipo": "V2", "confirmada": True}]
    d = e.decisiones(P, base, ag, an["controles"])
    res["precedencia-violacion"] = {"detectado": d["R1"]["clase"] == "refutada", "R1": d["R1"]["clase"]}
    ag = copy.deepcopy(an["agregado"])
    for x in ("P-w5-xor1-eq|C", "P-w5-xor1-q|C"):
        ag[x]["inconclusa"] = ["plantada"]
    orden_parcial = {"transiciones": ["P-w5-xor1-eq", "P-w5-xor1-q", "P-w5-xor1-neq"],
                     "controles": [], "repeticiones": []}
    tmp_conj = dirp / "conj-umbral"
    tmp_conj.mkdir()
    for x in orden_parcial["transiciones"]:
        (tmp_conj / x).symlink_to(P / x)
    (tmp_conj / "orden.json").write_text(json.dumps(orden_parcial))
    d = e.decisiones(tmp_conj, base, ag, {})
    res["precedencia-umbral"] = {"detectado": d["precedencia"] == 4 and d["R1"]["clase"] ==
                                 "no refutada, cobertura insuficiente", "precedencia": d["precedencia"],
                                 "R1": d["R1"]["clase"]}
    # G1: una excepción técnica de A (fase 1) o de B (fase 0) es calibración: precedencia 2, R2/R3 sin informar, rc 2
    for nombre, cond, fase in (("G1-excepcion-A", "A", "fase1"), ("G1-excepcion-B-fase0", "B", "fase0")):
        dd = dirp / nombre
        shutil.copytree(base, dd)
        esc(dd / "rep1" / "P-w5-xor1-q" / cond / f"{fase}.json",
            {"ok": False, "error": f"RuntimeError('excepción plantada en {cond}')", "traza": "plantada"})
        pr = subprocess.run([sys.executable, str(AQUI / "ejecutar.py"), "--preparacion", "--reps", "1",
                             "--solo-analisis", "--salida", str(dd)], cwd=RAIZ, capture_output=True, text=True)
        dec = leer(dd / "analisis.json")["decision"]
        res[nombre] = {"detectado": pr.returncode == 2 and dec["precedencia"] == 2 and
                       str(dec["R2"]).startswith("no informado") and str(dec["R3"]).startswith("no informado") and
                       any(c["tipo"] == f"excepcion_en_{cond}" for c in dec["calibracion"]),
                       "rc": pr.returncode, "precedencia": dec["precedencia"]}
    # G1 (regresión): un `desconocido` normal sigue siendo solo inconcluso, sin calibración
    dd = dirp / "G1-desconocido-normal"
    dst = _copiar_celda(base, dd, "P-w5-xor1-q", "A")
    f = leer(dst / "fase1.json")
    obl(f, "WD(f)")["estado"] = "desconocido"
    esc(dst / "fase1.json", f)
    r = e.analizar_celda(dd, P, 1, "P-w5-xor1-q", "A", _orac(e, P, "P-w5-xor1-q"))
    res["G1-desconocido-sigue-inconcluso"] = {"detectado": bool(r["inconclusa"]) and not any(
        c["tipo"].startswith("excepcion_en_") for c in r["calibracion"]), "inconclusa": r["inconclusa"],
        "calibracion": r["calibracion"]}

    # G2–G4 sobre un conjunto de tres transiciones de preparación (umbral > 0,15)
    def conjunto(nombre, contaminada=None):
        cj = dirp / nombre
        cj.mkdir()
        ts = ["P-w5-xor1-eq", "P-w5-xor1-q", "P-w5-xor1-neq"]
        for x in ts:
            shutil.copytree(P / x, cj / x)
            if x == contaminada:
                m = leer(cj / x / "meta.json")
                m["contaminada"] = True
                esc(cj / x / "meta.json", m)
        (cj / "orden.json").write_text(json.dumps({"transiciones": ts, "controles": [], "repeticiones": []}))
        return cj
    cj = conjunto("conj-G2-G3")
    ag = copy.deepcopy(an["agregado"])
    ag["P-w5-xor1-q|A"]["inconclusa"] = ["plantada solo en A"]
    d = e.decisiones(cj, base, ag, {})
    res["G2-inconclusas-solo-en-A"] = {"detectado": d["precedencia"] == 4 and d["R1"]["clase"] ==
                                       "no refutada, cobertura insuficiente", "R1": d["R1"]["clase"],
                                       "precedencia": d["precedencia"]}
    ag["P-w5-xor1-eq|C"]["violaciones"] = [{"tipo": "V2", "confirmada": True}]
    d = e.decisiones(cj, base, ag, {})
    res["G3-violacion-y-umbral"] = {"detectado": d["precedencia"] == 3 and d["R1"]["clase"] == "refutada" and
                                    d["R2"] == "inconcluso (umbral)" and len(d.get("motivos", [])) == 2,
                                    "precedencia": d["precedencia"], "motivos": d.get("motivos")}
    cj = conjunto("conj-G4", contaminada="P-w5-xor1-eq")
    ag = copy.deepcopy(an["agregado"])
    d = e.decisiones(cj, base, ag, {})
    agr = d["robustez"]["agregados"]
    suma = lambda ts, c: sum(ag[f"{t}|{c}"]["n"] for t in ts)  # noqa: E731
    todas, sin = ["P-w5-xor1-eq", "P-w5-xor1-q", "P-w5-xor1-neq"], ["P-w5-xor1-q", "P-w5-xor1-neq"]
    esperado = {"con_todas": {c: suma(todas, c) for c in "ABC"}, "sin_contaminadas": {c: suma(sin, c) for c in "ABC"}}
    ok = all(agr[k][f"N_{c}"] == esperado[k][c] for k in esperado for c in "ABC") and \
        all(k in agr[a] for a in agr for k in ("R2", "R3", "rho", "N_C_menos_N_B")) and \
        agr["con_todas"]["transiciones"] == 3 and agr["sin_contaminadas"]["transiciones"] == 2 and \
        all(agr[k]["N_C_menos_N_B"] == esperado[k]["C"] - esperado[k]["B"] for k in esperado)
    res["G4-agregados-64-61-publicados"] = {"detectado": ok, "agregados": agr, "esperado": esperado}
    res["ok"] = all(v["detectado"] for k, v in res.items() if not k.startswith("_"))
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--salida", required=True)
    ap.add_argument("--solo", nargs="*")
    a = ap.parse_args()
    sal = pathlib.Path(a.salida)
    sal.mkdir(parents=True, exist_ok=True)
    pruebas = {"oraculo": lambda: prueba_oraculo(), "remapeo_B": lambda: prueba_remapeo(),
               "monitor_D11": lambda: prueba_monitor(sal / "monitor"), "parada": lambda: prueba_parada(sal),
               "sensibilidad_O2": lambda: prueba_sensibilidad_O2(sal / "sensibilidad"),
               "metapruebas": lambda: prueba_metapruebas(sal / "metapruebas")}
    out = {}
    for k, f in pruebas.items():
        if a.solo and k not in a.solo:
            continue
        (sal / k).mkdir(exist_ok=True)
        try:
            out[k] = f()
        except Exception as ex:  # noqa: BLE001
            import traceback
            out[k] = {"ok": False, "error": repr(ex), "traza": traceback.format_exc()}
        (sal / f"{k}.json").write_text(json.dumps(out[k], indent=1, ensure_ascii=False, default=str))
        print(k, "ok" if out[k].get("ok") else "FALLO")
    return 0 if all(v.get("ok") for v in out.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
