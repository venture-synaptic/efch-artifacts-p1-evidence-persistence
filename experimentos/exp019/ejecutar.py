"""EXP-019: lanzador y análisis (ficha, §Método M1–M8, §Repeticiones y análisis, §Custodia).

    python3 experimentos/exp019/ejecutar.py --preparacion [--salida resultados/exp019/preparacion] [--reps 5]
    python3 experimentos/exp019/ejecutar.py --evaluacion --autorizacion REF ...      (no autorizada todavía)

Rechaza `evaluacion/` sin `--evaluacion --autorizacion REF`. Ejecuta cada fase de cada celda en un subproceso nuevo
(900 s la fase 0, 600 s la fase 1, `ulimit -v 4194304`), en el orden y con el intercalado de `orden.json`, y añade
cada ejecución a `ejecucion.jsonl`. Una parada global (código 3 del arnés) detiene todo y conserva la evidencia.
Después analiza: O1 (oráculo), O2 (contraste) y su confirmación (validador normativo, confirmador de fuentes), O3
(lector), O4 (testigos), determinismo, calibración, controles K/KB y resúmenes.
"""

import argparse
import datetime
import hashlib
import json
import os
import pathlib
import platform
import resource
import statistics
import subprocess
import sys
import time

AQUI = pathlib.Path(__file__).resolve().parent
RAIZ = AQUI.parents[1]
INSTRUMENTO = ("arnes.py", "oraculo.py", "contraste.py", "confirmar_fuentes.py", "lector.py", "ejecutar.py",
               "autopruebas.py")
LIMITE_AS = 4194304 * 1024                                      # ulimit -v 4194304 (KiB), ficha §Paridad
T_FASE = {"0": 900, "1": 600}
ADMITIDOS_REPR = None


def sha_archivo(p):
    return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()


def sha_texto(t):
    return hashlib.sha256(t.encode()).hexdigest()


def leer(p):
    return json.loads(pathlib.Path(p).read_text(encoding="utf-8"))


def escribir(p, x):
    p = pathlib.Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(x, sort_keys=True, ensure_ascii=False, indent=1, default=list) + "\n", encoding="utf-8")


def huellas():
    """Custodia (§Custodia): huellas de los manifiestos transitivos oficiales, registradas en cada línea del JSONL."""
    return {n: sha_archivo(AQUI / n) if (AQUI / n).exists() else None
            for n in ("INSTRUMENTO.sha256", "MANIFIESTO.sha256", "BASE-efch.sha256")}


def _limites():
    resource.setrlimit(resource.RLIMIT_AS, (LIMITE_AS, LIMITE_AS))


def lanzar(args, timeout, env_extra=None):
    env = {**os.environ, "PYTHONHASHSEED": "0", **(env_extra or {})}
    t0 = time.time()
    try:
        p = subprocess.run([sys.executable, str(AQUI / "arnes.py"), *args], cwd=RAIZ, env=env, timeout=timeout,
                           preexec_fn=_limites, capture_output=True, text=True)
        return {"rc": p.returncode, "segundos": time.time() - t0, "stderr": p.stderr[-3000:]}
    except subprocess.TimeoutExpired:
        return {"rc": "timeout", "segundos": time.time() - t0, "stderr": ""}


def lanzar_I(script, args, timeout=300):
    p = subprocess.run([sys.executable, "-I", str(AQUI / script), *args], cwd=RAIZ, timeout=timeout,
                       capture_output=True, text=True, env={**os.environ, "PYTHONHASHSEED": "0"})
    return p.returncode, p.stdout, p.stderr[-2000:]


class Parada(Exception):
    pass


# --- ejecución ----------------------------------------------------------------------------------------------

def entorno(salida, desc):
    cpu = next((l.split(":", 1)[1].strip() for l in open("/proc/cpuinfo") if l.startswith("model name")), "")
    mem = next((l.split()[1] for l in open("/proc/meminfo") if l.startswith("MemTotal")), "")
    base = subprocess.run(["sha256sum", "-c", "--quiet", "experimentos/exp019/BASE-efch.sha256"], cwd=RAIZ,
                          capture_output=True, text=True)
    # En la preparación la evaluación está oculta: se verifica el resto del manifiesto; en la evaluación, completo.
    filtro = "grep -v '/evaluacion/'" if os.environ.get("EXP019_AUTORIZACION_EVALUACION") is None else "cat"
    man = subprocess.run(f"{filtro} experimentos/exp019/MANIFIESTO.sha256 | sha256sum -c --quiet -",
                         shell=True, cwd=RAIZ, capture_output=True, text=True)
    inst = AQUI / "INSTRUMENTO.sha256"
    ci = subprocess.run(["sha256sum", "-c", "--quiet", str(inst.relative_to(RAIZ))], cwd=RAIZ, capture_output=True,
                        text=True) if inst.exists() else None
    escribir(salida / "entorno.json", {
        "cpu": cpu, "nproc": os.cpu_count(), "memoria_kib": mem, "so": platform.platform(),
        "python": sys.version, "z3": desc.get("z3"), "descriptor_base": desc,
        "BASE-efch.sha256": {"rc": base.returncode, "salida": base.stdout + base.stderr},
        "INSTRUMENTO.sha256": None if ci is None else {"rc": ci.returncode, "salida": ci.stdout + ci.stderr},
        "MANIFIESTO.sha256": {"filtro": filtro, "rc": man.returncode, "salida": man.stdout + man.stderr},
        "huellas_oficiales": huellas(),
        "fecha": datetime.datetime.now(datetime.timezone.utc).isoformat()})
    fallos = [n for n, ok in (("BASE-efch.sha256", base.returncode == 0),
                              ("INSTRUMENTO.sha256", ci is not None and ci.returncode == 0),
                              ("MANIFIESTO.sha256", man.returncode == 0)) if not ok]
    return fallos


def celda_dir(salida, rep, entrada, cond):
    return salida / f"rep{rep}" / entrada / cond


def registrar(salida, h, **kw):
    with open(salida / "ejecucion.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps({"fecha": datetime.datetime.now(datetime.timezone.utc).isoformat(), **kw, "huellas": h},
                           sort_keys=True, ensure_ascii=False) + "\n")


def ejecutar_celda(salida, conjunto, rep, entrada, cond, h, env_extra=None):
    E = conjunto / entrada
    celda = celda_dir(salida, rep, entrada, cond)
    celda.mkdir(parents=True, exist_ok=True)
    desc = str(salida / "base-descriptor.json")
    control = entrada if entrada.startswith("K") else None
    comun = ["--cond", cond, "--entrada", str(E), "--celda", str(celda), "--descriptor", desc] + \
        (["--control", control] if control else [])
    pasos = []
    if cond in ("B", "C"):
        r = lanzar(["fase0", *comun], T_FASE["0"], env_extra)
        pasos.append(("fase0", r))
        registrar(salida, h, entrada=entrada, condicion=cond, repeticion=rep, fase=0, rc=r["rc"])
        if r["rc"] == 3:
            raise Parada(f"{entrada}/{cond}/rep{rep} fase 0")
        if r["rc"] != 0:
            escribir(celda / "lanzador.json", pasos)
            return
        clon_C = control and control.split("-")[0] in ("KP4", "KP5", "KP6", "KP7", "KP8", "K4", "K5", "K6",
                                                       "K7", "K8")
        if cond == "C" and clon_C:
            m = lanzar(["mutarC", "--control", control, "--almacen", str(celda / "P"), "--out", str(celda / "Q"),
                        "--celda", str(celda)], 120)
            pasos.append(("mutarC", m))
        if cond == "B" and clon_C:
            t0 = leer(celda / "B" / "trazas-fase0.json")
            e0 = next((t["clave"] for t in t0 if t["obligacion"] == "WD(c0)"), "")
            m = lanzar(["mutarB", "--control", control, "--almacen", str(celda / "B"), "--out", str(celda / "BQ"),
                        "--celda", str(celda), "--clave-E0", e0], 120)
            pasos.append(("mutarB", m))
        if cond == "C" and clon_C:
            (celda / "disco-Q-antes-fase1.json").write_text(json.dumps(_foto(celda / "Q"), indent=1))
    r = lanzar(["fase1", *comun], T_FASE["1"], env_extra)
    pasos.append(("fase1", r))
    registrar(salida, h, entrada=entrada, condicion=cond, repeticion=rep, fase=1, rc=r["rc"])
    escribir(celda / "lanzador.json", pasos)
    if r["rc"] == 3:
        raise Parada(f"{entrada}/{cond}/rep{rep} fase 1")


def _foto(raiz):
    out = {}
    for p in sorted(pathlib.Path(raiz).rglob("*")):
        if p.is_file():
            out[str(p.relative_to(raiz))] = sha_archivo(p)
    return out


def ejecutar(conjunto, salida, reps, solo=None, env_extra=None):
    salida.mkdir(parents=True, exist_ok=True)
    r = lanzar(["descriptor", str(salida / "base-descriptor.json")], 300)
    if r["rc"] != 0:
        raise SystemExit(f"descriptor: {r}")
    desc = leer(salida / "base-descriptor.json")
    fallos = entorno(salida, desc)
    if fallos:
        raise SystemExit(f"no verifican {fallos}: no se empieza sin decisión del autor (ficha §M8, §Custodia)")
    h = huellas()
    orden = leer(conjunto / "orden.json")
    for bloque in orden["repeticiones"][:reps]:
        rep = bloque["repeticion"]
        for item in bloque["secuencia"]:
            if solo and item["entrada"] not in solo:
                continue
            for cond in item["condiciones"]:
                ejecutar_celda(salida, conjunto, rep, item["entrada"], cond, h, env_extra)


# --- análisis -----------------------------------------------------------------------------------------------

NOMBRES = ["WD(f)", "WD(h)", "WD(q)", "WD(c0)", "REAL(c0)", "WD(c1)", "REAL(c1)", "WD(c2)", "REAL(c2)"]
ESTRATO = {"q": "ajena", "eq": "eq", "neq": "neq"}


def estrato(meta):
    if meta["cambio"] == "h":
        return "dependencia" if meta["cuerpo"] == "llamada" else "ajena"
    return ESTRATO.get(meta["cambio"], meta["cambio"])


def _f1(celda):
    p = celda / "fase1.json"
    return leer(p) if p.exists() else {"ok": False, "error": "sin fase1.json"}


def _f0(celda):
    p = celda / "fase0.json"
    return leer(p) if p.exists() else None


def _verdad_interp(tab, clase, nombre, sd_o_sa="S_d"):
    t = tab[sd_o_sa]
    if clase == "WD":
        return all(v != "indefinido" for v in t[nombre])
    return t[nombre] == t["f"]


def v2_celda(f1, orac, test, cond):
    """V2 (§R1): un estado contradicho por el oráculo O1 **y** por el intérprete (tablas exhaustivas de efch.interp,
    I3), o un testigo que no reproducen ni O1 ni el intérprete. Si los árbitros discrepan, o falta el segundo, es
    calibración, nunca una V2 confirmada."""
    viol, calib = [], []
    if not f1.get("ok") or "obligaciones" not in f1:
        return viol, calib
    sd = orac["S_d"]
    tab = (test or {}).get("tablas_interp")
    for o in f1["obligaciones"]:
        n, est = o["obligacion"], o["estado"]
        if est not in ("probado", "refutado"):
            continue
        nombre = n[n.index("(") + 1:-1]
        v_o = True if o["clase"] == "WD" else orac["REAL_d"][nombre]
        if tab is None:
            if (est == "probado") != v_o:
                calib.append({"tipo": "V2_sin_segundo_arbitro", "obligacion": n, "estado": est, "oraculo": v_o})
            continue
        v_i = _verdad_interp(tab, o["clase"], nombre if o["clase"] == "REAL" else nombre)
        if v_o != v_i:
            calib.append({"tipo": "oraculo_vs_interprete", "obligacion": n, "oraculo": v_o, "interprete": v_i})
        elif (est == "probado") != v_o:
            viol.append({"tipo": "V2", "obligacion": n, "estado": est, "oraculo": v_o, "interprete": v_i,
                         "confirmada": True})
    for t in (test or {}).get("testigos", []):
        w = t.get("testigo") or t.get("eq_testigo")
        if "obligacion" in t and "cand" in t:
            c = t["obligacion"][5:-1]
            interp_distinto, orac_distinto = t["cand"] != t["f_d"], sd[c][w["x"]] != sd["f"][w["x"]]
            if interp_distinto != orac_distinto:
                calib.append({"tipo": "oraculo_vs_interprete", "testigo": t})
            elif not orac_distinto:
                viol.append({"tipo": "V2", "testigo_falso": t, "confirmada": True})
        elif "refut" in t:
            if (t["cand_v"] != t["f_d"]) != (sd[t["cand"]][w["x"]] != sd["f"][w["x"]]):
                calib.append({"tipo": "oraculo_vs_interprete", "testigo": t})
            elif sd[t["cand"]][w["x"]] == sd["f"][w["x"]]:
                viol.append({"tipo": "V2", "refut_falso": t, "confirmada": True})
        elif "eq_testigo" in t:
            n = t["computacion"]
            o_d, o_a = sd[n][w["x"]], orac["S_a"][n][w["x"]]
            if (t["n_d"] != t["n_a"]) != (o_d != o_a):
                calib.append({"tipo": "oraculo_vs_interprete", "testigo": t})
            elif o_d == o_a:
                viol.append({"tipo": "V2", "eq_testigo_falso": t, "confirmada": True})
    refut_confirmados = {t.get("refut") for t in (test or {}).get("testigos", [])}
    for x in f1.get("emitidas", []):
        if x["clase"] == "REFUT" and x.get("certificado") not in refut_confirmados:
            calib.append({"tipo": "REFUT_sin_confirmacion", "certificado": x.get("certificado")})
        if x["clase"] == "EQ" and x["estado"] in ("probado", "refutado"):
            n = x["sujetos"]["nueva"]["nombre"]
            v_o = orac["EQ_d_a"][n]
            if tab is None:
                if (x["estado"] == "probado") != v_o:
                    calib.append({"tipo": "V2_sin_segundo_arbitro", "eq": x})
                continue
            v_i = tab["S_d"][n] == tab["S_a"][n]
            if v_o != v_i:
                calib.append({"tipo": "oraculo_vs_interprete", "eq": x})
            elif (x["estado"] == "probado") != v_o:
                viol.append({"tipo": "V2", "eq": x, "confirmada": True})
    return viol, calib


def errores_tecnicos_AB(celda, cond, f0, f1):
    """G1 (§Repeticiones, precedencia 2): una excepción de A o de B, en la fase 0 o en la 1, es un fallo de
    calibración. No lo son un `desconocido` normal del solucionador (fase con `ok` y obligaciones), un límite externo
    agotado (`timeout` del lanzador) ni una parada global (precedencia 1): quedan como celda inconclusa o parada."""
    if cond not in ("A", "B"):
        return []
    pasos = {n: r for n, r in leer(celda / "lanzador.json")} if (celda / "lanzador.json").exists() else {}
    out = []
    fases = [("fase0", f0)] if cond == "B" else []
    fases.append(("fase1", f1))
    for fase, f in fases:
        rc = (pasos.get(fase) or {}).get("rc")
        if rc == "timeout":
            continue
        if fase == "fase1" and cond == "B" and (f0 is None or not f0.get("ok")):
            break                                     # la fase 1 no se lanzó: ya cuenta la fase 0
        if f is None or not f.get("ok"):
            if f is not None and f.get("parada_global"):
                continue
            out.append({"fase": fase, "rc": rc, "error": (f or {}).get("error") or "fase sin salida"})
    return out


def analizar_celda(salida, conjunto, rep, entrada, cond, orac):
    celda = celda_dir(salida, rep, entrada, cond)
    f1 = _f1(celda)
    f0 = _f0(celda) if cond != "A" else None
    meta = leer(conjunto / entrada / "meta.json")
    res = {"entrada": entrada, "condicion": cond, "repeticion": rep, "ok": bool(f1.get("ok"))}
    inconcl = []
    if f0 is not None and (not f0.get("ok") or (cond == "C" and not f0.get("todas_aceptadas"))):
        inconcl.append("fase 0 sin establecer")
    if not f1.get("ok"):
        inconcl.append(f1.get("error") or f1.get("parada_global") or "fase 1 sin salida")
    elif "obligaciones" not in f1:
        inconcl.append("excepción en la fase 1: " + str((f1.get("excepcion") or {}).get("repr")))
    else:
        nombres = sorted(o["obligacion"] for o in f1["obligaciones"])
        if nombres != sorted(NOMBRES):
            inconcl.append(f"O(S_d) incompleto: {nombres}")
        for o in f1["obligaciones"]:
            if o["estado"] not in ("probado", "refutado"):
                inconcl.append(f"{o['obligacion']}: {o['estado']}")
        if cond == "C":
            inf = f1["informe"]
            if not inf.get("aceptada") or inf.get("instantanea_vigente") != inf.get("instantanea_nueva"):
                inconcl.append("evolve no aceptada o instantánea vigente distinta")
    res["inconclusa"] = inconcl
    tecnicos = errores_tecnicos_AB(celda, cond, f0, f1)
    if f1.get("ok") and "obligaciones" in f1:
        m = f1["medida"]
        res.update({"n": m["contadores"]["prove"], "check": m["contadores"]["check"], "contadores": m["contadores"],
                    "pared_s": m["pared_s"], "cpu_s": m["cpu_s"],
                    "estados": {o["obligacion"]: o["estado"] for o in f1["obligaciones"]},
                    "origenes": {o["obligacion"]: o["origen"] for o in f1["obligaciones"]},
                    "reglas": {o["obligacion"]: o.get("regla") for o in f1["obligaciones"]}})
        if cond == "C":
            res["wd_redundantes"] = m.get("wd_redundantes")
            res["eq_rev"] = m["contadores"]["eq_rev"]
            res["reverif_REAL"] = m["contadores"]["verify"]
            res["nucleo_igual_descriptor"] = f1.get("nucleo_igual_descriptor")
            res["emitidas"] = {c: sum(1 for x in f1.get("emitidas", []) if x["clase"] == c) for c in ("EQ", "REFUT")}
        if cond == "B":
            res["aciertos_B"] = m["contadores"]["aciertos_B"]
            res["modulos_prohibidos"] = f1.get("modulos_prohibidos")
    if f0 is not None and f0.get("ok"):
        res["fase0"] = f0.get("contadores_fase0") or (f0.get("medida") or {}).get("contadores")
    calib = [{"tipo": f"excepcion_en_{cond}", **t} for t in tecnicos]     # G1: precedencia 2, no solo inconclusa
    # O3
    alm = celda / ("Q" if (celda / "Q").exists() else "almacen")
    args = ["--cond", cond, "--celda", str(celda), "--out", str(celda / "lector.json")] + \
        (["--almacen", str(alm)] if cond == "C" else [])
    rc, _, err = lanzar_I("lector.py", args)
    lec = leer(celda / "lector.json") if rc == 0 else {"discrepancias": [{"tipo": "lector_fallo", "err": err}]}
    calib += [{"tipo": "lector", **d} for d in lec["discrepancias"]]
    viol = []
    if f1.get("ok") and "obligaciones" in f1:
        test = None
        (celda / "testigos.json").unlink(missing_ok=True)         # nunca se reutiliza una confirmación previa
        rt = lanzar(["testigos", "--entrada", str(conjunto / entrada), "--salida", str(celda / "fase1.json"),
                     "--out", str(celda / "testigos.json")], 300)
        if rt["rc"] == 0 and (celda / "testigos.json").exists():
            test = leer(celda / "testigos.json")
        else:                                                      # I2: fallo técnico de la confirmación
            calib.append({"tipo": "confirmacion_testigos_fallida", "rc": rt["rc"], "stderr": rt["stderr"][-500:]})
            inconcl.append("confirmación de testigos (O4) fallida")
        v2, cal2 = v2_celda(f1, orac, test, cond)
        viol += v2
        calib += cal2
    if cond == "C" and f1.get("ok") and "obligaciones" in f1:
        desc = str(salida / "base-descriptor.json")
        rc, _, err = lanzar_I("contraste.py", ["--entrada", str(conjunto / entrada), "--almacen", str(alm),
                                               "--salida", str(celda / "fase1.json"), "--descriptor", desc,
                                               "--out", str(celda / "contraste.json")])
        o2 = leer(celda / "contraste.json") if rc == 0 else None
        rc2, _, err2 = lanzar_I("confirmar_fuentes.py", ["--entrada", str(conjunto / entrada), "--almacen", str(alm),
                                                         "--salida", str(celda / "fase1.json"),
                                                         "--out", str(celda / "fuentes.json")])
        cf = leer(celda / "fuentes.json") if rc2 == 0 else None
        lanzar(["normativo", "--almacen", str(alm), "--salida", str(celda / "fase1.json"),
                "--out", str(celda / "normativo.json")], 300)
        nor = leer(celda / "normativo.json") if (celda / "normativo.json").exists() else None
        if o2 is None or cf is None or nor is None:
            calib.append({"tipo": "instrumento_O2", "err": [err, err2]})
        else:
            res["identicos"] = o2["identicos"]
            res["reverif_identicas"] = sorted(c for c, ident in o2["identicos"].items()
                                              if ident and res["origenes"].get(f"REAL({c})") == "directa")
            if nor.get("error_paquete"):
                calib.append({"tipo": "normativo_paquete", **nor["error_paquete"]})
            for ob, r in o2["raices"].items():
                cid = r.get("certificado")
                if not cid:
                    continue
                o2_contractual = [t for t in r.get("violaciones", []) if t in ("V1a", "V1b", "V1d")]
                n_ok = nor["raices"].get(cid, {}).get("ok")
                if o2_contractual and n_ok is False:
                    viol += [{"tipo": t, "obligacion": ob, "certificado": cid, "confirmada": True,
                              "normativo": nor["raices"][cid]} for t in o2_contractual]
                elif bool(o2_contractual) != (n_ok is False):
                    calib.append({"tipo": "O2_vs_normativo", "obligacion": ob, "o2": r.get("fallos"),
                                  "normativo": nor["raices"].get(cid)})
                if "V1c" in r.get("violaciones", []):
                    ranuras = {f["detalle"] for f in r["fallos"] if f["codigo"] == "identidad_contradicha"}
                    conf = {"/".join(d["ranura"]) for d in cf["discrepancias"] if d["tipo"] == "identidad"}
                    if ranuras & conf:
                        viol.append({"tipo": "V1c", "obligacion": ob, "certificado": cid, "confirmada": True})
                    else:
                        calib.append({"tipo": "V1c_no_confirmada", "obligacion": ob})
            k2 = lambda ds: sorted((d["tipo"], "/".join(d["ranura"])) for d in ds  # noqa: E731
                                   if d["tipo"] in ("identidad", "contenido"))
            if k2(o2["discrepancias"]) != k2(cf["discrepancias"]):
                calib.append({"tipo": "O2_vs_confirmador_enlaces", "o2": o2["discrepancias"],
                              "confirmador": cf["discrepancias"]})
            res["enlace_discrepancias"] = {"o2": o2["discrepancias"], "confirmador": cf["discrepancias"]}
        if f1.get("nucleo_igual_descriptor") is False:
            calib.append({"tipo": "base_C_vs_descriptor"})
    if cond == "B" and res.get("modulos_prohibidos"):
        calib.append({"tipo": "B_importa_store_o_reglas", "modulos": res["modulos_prohibidos"]})
    if res.get("n") is not None and res["n"] != res["check"]:
        calib.append({"tipo": "contador_vs_Solver.check", "prove": res["n"], "check": res["check"]})
    if cond in ("A", "B"):
        for v in viol:
            calib.append({"tipo": f"violacion_en_{cond}", **v})
    res["violaciones"] = viol if cond == "C" else []
    res["calibracion"] = calib
    res["estrato"] = estrato(meta) if not entrada.startswith("K") else "control"
    return res


def analizar(conjunto, salida, reps):
    orden = leer(conjunto / "orden.json")
    orac = {}
    for e in orden["transiciones"] + orden["controles"]:
        rc, out, err = lanzar_I("oraculo.py", ["tablas", str(conjunto / e)])
        orac[e] = json.loads(out) if rc == 0 else {"fuera_de_alcance": err}
    escribir(salida / "oraculo.json", orac)
    celdas = {}
    for bloque in orden["repeticiones"][:reps]:
        rep = bloque["repeticion"]
        for item in bloque["secuencia"]:
            for cond in item["condiciones"]:
                if celda_dir(salida, rep, item["entrada"], cond).exists():
                    celdas[(item["entrada"], cond, rep)] = analizar_celda(salida, conjunto, rep, item["entrada"],
                                                                          cond, orac[item["entrada"]])
    # determinismo entre repeticiones (§M6)
    por_celda = {}
    for (e, c, r), x in celdas.items():
        por_celda.setdefault((e, c), []).append(x)
    agregado = {}
    for (e, c), xs in sorted(por_celda.items()):
        firmas = {json.dumps([x.get("estados"), x.get("n"), x.get("origenes")], sort_keys=True) for x in xs}
        inc = sorted({i for x in xs for i in x["inconclusa"]})
        if len(firmas) > 1:
            inc.append("repeticiones que no coinciden")
        calib = [y for x in xs for y in x["calibracion"]]
        if len(firmas) > 1 and c in ("A", "B"):
            calib.append({"tipo": "no_determinista", "condicion": c})
        tiempos = [x["pared_s"] for x in xs if "pared_s" in x]
        cpus = [x["cpu_s"] for x in xs if "cpu_s" in x]
        agregado[f"{e}|{c}"] = {
            "entrada": e, "condicion": c, "repeticiones": len(xs), "inconclusa": inc, "n": xs[0].get("n"),
            "estados": xs[0].get("estados"), "origenes": xs[0].get("origenes"), "estrato": xs[0]["estrato"],
            "violaciones": [y for x in xs for y in x["violaciones"]], "calibracion": calib,
            "pared_mediana_s": statistics.median(tiempos) if tiempos else None,
            "pared_riq_s": _riq(tiempos), "cpu_mediana_s": statistics.median(cpus) if cpus else None,
            "cpu_riq_s": _riq(cpus), "fase0": xs[0].get("fase0"),
            **{k: xs[0].get(k) for k in ("wd_redundantes", "eq_rev", "reverif_REAL", "aciertos_B",
                                          "reverif_identicas", "identicos", "emitidas")}}
    controles = evaluar_controles(conjunto, salida, celdas, reps, orac)
    return celdas, agregado, controles, decisiones(conjunto, salida, agregado, controles)


def _riq(xs):
    if len(xs) < 2:
        return None
    q = statistics.quantiles(xs, n=4)
    return q[2] - q[0]


# --- controles ------------------------------------------------------------------------------------------------

def _num(entrada):
    return int(entrada.split("-")[0].lstrip("KP"))


def _certs(raiz):
    out = {}
    for p in (pathlib.Path(raiz) / "objetos" / "certificados").glob("*.json"):
        out[p.stem] = leer(p)
    return out


def _afs(raiz):
    return {p.stem: leer(p) for p in (pathlib.Path(raiz) / "objetos" / "afirmaciones").glob("*.json")}


def invariantes(cel, gem, raiz_c, raiz_g):
    """Ficha/esperado: estado, origen y regla por obligación; clase y componentes de base de los certificados de
    S_d; n_C; cero V1/V2."""
    dif = []
    for k in ("estados", "origenes", "reglas", "n"):
        if cel.get(k) != gem.get(k):
            dif.append({"invariante": k, "control": cel.get(k), "gemelo": gem.get(k)})
    clases = []
    for x, raiz in ((cel, raiz_c), (gem, raiz_g)):
        f1 = leer(celda_de(x) / "fase1.json")
        cs, afs = _certs(raiz), _afs(raiz)
        m = {}
        for o in f1["obligaciones"]:
            c = cs.get(o.get("certificado") or "")
            if c:
                m[o["obligacion"]] = [afs.get(c["afirmacion"], {}).get("clase"), sorted(c["base"])]
        clases.append(m)
    if clases[0] != clases[1]:
        dif.append({"invariante": "clase_y_base", "control": clases[0], "gemelo": clases[1]})
    if cel.get("violaciones"):
        dif.append({"invariante": "V1/V2", "control": cel["violaciones"]})
    return dif


SALIDA_GLOBAL = {}


def celda_de(x):
    return celda_dir(SALIDA_GLOBAL["salida"], x["repeticion"], x["entrada"], x["condicion"])


def evaluar_controles(conjunto, salida, celdas, reps, orac):
    SALIDA_GLOBAL["salida"] = salida
    orden = leer(conjunto / "orden.json")
    out = {}
    for k in orden["controles"]:
        esp = leer(conjunto / k / "esperado.json")
        for rep in range(1, reps + 1):
            cel = celdas.get((k, "C", rep))
            out[f"{k}|C|{rep}"] = evaluar_C(k, esp, cel, celdas, rep, conjunto, salida) if cel else \
                {"resultado": "inconcluso", "motivo": "sin celda"}
            if esp.get("calibracion_B"):
                celB = celdas.get((k, "B", rep))
                out[f"{k}|B|{rep}"] = evaluar_B(k, esp, celB, celdas, rep, salida) if celB else \
                    {"resultado": "inconcluso", "motivo": "sin celda"}
    return out


def evaluar_C(k, esp, cel, celdas, rep, conjunto, salida):
    n = _num(k)
    celda = celda_de(cel)
    f0, f1 = _f0(celda), _f1(celda)
    if f1.get("parada_global"):
        return {"resultado": "parada global"}
    gem = celdas.get((esp["gemelo"], "C", rep)) if esp.get("gemelo") else None
    if esp.get("gemelo") and (gem is None or gem["inconclusa"]):
        return {"resultado": "inconcluso", "motivo": "gemelo ausente o inconcluso"}
    raiz = celda / ("Q" if (celda / "Q").exists() else "almacen")
    raiz_g = celda_de(gem) / "almacen" if gem else None
    if n == 1:
        nombres = leer(raiz / "nombres.json")
        act = all(any(x.get("nota") == "etiqueta de control" for x in nombres[m]["historial"]) for m in "hqf") and \
            nombres["f"]["historial"][-1].get("nota") == "refactor equivalente (etiqueta de control)"
        if not act:
            return {"resultado": "inconcluso", "motivo": "notas no registradas"}
        if cel["inconclusa"]:
            return {"resultado": "inconcluso", "motivo": cel["inconclusa"]}
        dif = invariantes(cel, gem, raiz, raiz_g)
        return {"resultado": "fallo" if dif else "superado", "diferencias": dif}
    if n == 2:
        if cel["inconclusa"]:
            return {"resultado": "inconcluso", "motivo": cel["inconclusa"]}
        cf = leer(celda / "fuentes.json")["enlaces"].get("computacion/f", {})
        o2 = leer(celda / "contraste.json")["enlace"].get("computacion/f", {})
        if cf.get("sin_cambio_propio") is not False or cf.get("expansion_igual") is not True:
            return {"resultado": "inconcluso", "motivo": "precondición: el lector propio no ve doc distinto e "
                                                          "expansión igual", "cf": cf}
        fallos = []
        if o2.get("id_igual_efch") is not False:
            fallos.append("la revisión de f no cambia (doc ignorado en la identidad)")
        if o2.get("contenido_igual_efch") is not True:
            fallos.append("el contenido de f cambia")
        for c in ("c0", "c1", "c2"):
            if cel["origenes"][f"REAL({c})"] not in ("R-REAL", "directa"):
                fallos.append(f"REAL({c}) con origen {cel['origenes'][f'REAL({c})']}")
            if cel["estados"][f"REAL({c})"] != "probado":
                fallos.append(f"REAL({c}) no probado")
        if cel["estados"]["WD(f)"] != "probado":
            fallos.append("WD(f) no probado")
        if cel["violaciones"]:
            fallos.append(cel["violaciones"])
        return {"resultado": "fallo" if fallos else "superado", "fallos": fallos}
    if n == 3:
        traza = (f0 or {}).get("doble_K3", [])
        if len(traza) != 3:
            return {"resultado": "inconcluso", "motivo": f"doble llamado {len(traza)} veces"}
        defectos = [i for i, t in enumerate(traza) if not intervencion_K3_aplicada(t)]
        if defectos:                                   # I4: el doble no intervino como define esperado.json
            return {"resultado": "inconcluso", "motivo": "intervención K3 no aplicada en las llamadas "
                                                         f"{defectos}", "calibracion": True}
        if cel["inconclusa"]:
            return {"resultado": "inconcluso", "motivo": cel["inconclusa"]}
        ids_gem = []
        for r in range(1, 6):
            g = celdas.get((esp["gemelo"], "C", r))
            if g:
                ids_gem.append(sorted(x for x in leer(celda_de(g) / "disco-fase0.json") if x.startswith("objetos/")))
        if len({json.dumps(x) for x in ids_gem}) != 1:
            return {"resultado": "inconcluso", "motivo": "el gemelo no reproduce sus ids de la fase 0",
                    "calibracion": True}
        ids_c = sorted(x for x in leer(celda / "disco-fase0.json") if x.startswith("objetos/"))
        dif = invariantes(cel, gem, raiz, raiz_g)
        if ids_c != ids_gem[0]:
            dif.append({"invariante": "ids_fase0", "solo_control": sorted(set(ids_c) - set(ids_gem[0])),
                        "solo_gemelo": sorted(set(ids_gem[0]) - set(ids_c))})
        return {"resultado": "fallo" if dif else "superado", "diferencias": dif}
    mut = leer(celda / "mutacion.json") if (celda / "mutacion.json").exists() else {}
    interv = (mut.get("intervencion") or {})
    if not interv.get("exacto"):
        return {"resultado": "inconcluso", "motivo": "intervención no aplicada o diff no exacto", "mutacion": mut}
    if n == 4:
        P = celda / "P"
        cs, afs = _certs(P), _afs(P)
        loc_af = [i for i, a in afs.items() if a.get("clase") == "REAL"]
        from_c0 = [c for c in cs.values() if c["afirmacion"] in loc_af and c["regla"] == "directa" and
                   c["estado"] == "probado" and _es_c0(P, afs[c["afirmacion"]])]
        insts = {c["instantanea"] for c in from_c0}
        if cel["inconclusa"]:
            return {"resultado": "inconcluso", "motivo": cel["inconclusa"]}
        S_d = leer(raiz / "objetos" / "instantaneas" / f"{_f1(celda)['S_d']}.json")
        vig = [c["id"] for c in from_c0 if all(S_d["revisiones"].get(r) == v for r, v in c["cierre"].items())]
        cP, cQ = leer(P / "costes.json"), leer(raiz / "costes.json") if False else leer(celda / "Q" / "costes.json")
        orden_inv = len(from_c0) == 2 and (cP[from_c0[0]["id"]]["orden"] < cP[from_c0[1]["id"]]["orden"]) != \
            (cQ[from_c0[0]["id"]]["orden"] < cQ[from_c0[1]["id"]]["orden"])
        if len(from_c0) != 2 or len(insts) != 2 or len(vig) != 2 or not orden_inv:
            return {"resultado": "inconcluso", "motivo": "precondición de K4", "certs": [c["id"] for c in from_c0],
                    "vigentes": vig, "orden_invertido": orden_inv}
        dif = invariantes(cel, gem, raiz, raiz_g)
        f1c = _f1(celda)
        elegido = next(o["certificado"] for o in f1c["obligaciones"] if o["obligacion"] == "REAL(c0)")
        if elegido not in vig:
            dif.append({"invariante": "REAL(c0) desde uno de los dos válidos", "elegido": elegido})
        return {"resultado": "fallo" if dif else "superado", "diferencias": dif, "elegido": elegido,
                "elegido_mayor_orden_en_Q": elegido == max(vig, key=lambda c: cQ[c]["orden"])}
    # K5–K8
    admitidos = set(esp["codigos_admitidos"])
    A1, R1 = mut.get("A0'"), mut.get("R0'")
    mutados = {x for x in (A1, R1) if x}
    loc = mut.get("localizacion", {})
    if loc.get("referencias_ajenas"):
        return {"resultado": "inconcluso", "motivo": "otros objetos referencian A0 o R0"}
    gem_cel = celda_de(gem)
    gf1 = _f1(gem_cel)
    gcs = _certs(gem_cel / "almacen")
    gc = gcs.get(next((o["certificado"] for o in gf1["obligaciones"] if o["obligacion"] == "REAL(c0)"), ""), {})
    if gc.get("regla") != "R-REAL" or gc.get("procedencia") != mut.get("R0"):
        return {"resultado": "inconcluso", "motivo": "activación: en el gemelo REAL(c0) no procede de R0",
                "gemelo": {"regla": gc.get("regla"), "procedencia": gc.get("procedencia"), "R0": mut.get("R0")}}
    if f1.get("ok") and "excepcion" in f1:
        ex = f1["excepcion"]
        texto = f"{ex.get('ruta')} {ex.get('detalle')}"
        if ex["tipo"] == "Rechazo" and ex.get("codigo") in admitidos and any(m in texto for m in mutados):
            return {"resultado": "superado (rechazo estructurado, excepción)", "excepcion": ex}
        return {"resultado": "inconcluso", "motivo": "excepción no estructurada o sin enlace", "excepcion": ex}
    if cel["inconclusa"]:
        return {"resultado": "inconcluso", "motivo": cel["inconclusa"]}
    # uso del objeto alterado
    cs = _certs(raiz)
    usado = [c["id"] for c in cs.values() if c["id"] not in mutados and
             (set(c["premisas"].values()) & mutados or c["procedencia"] in mutados or c["afirmacion"] in mutados)]
    fallos = []
    if usado:
        fallos.append({"objeto_alterado_usado_por": usado})
    if cel["violaciones"]:
        fallos.append({"violaciones": cel["violaciones"]})
    real_c0 = next(o for o in f1["obligaciones"] if o["obligacion"] == "REAL(c0)")
    if real_c0["origen"] in ("R-REAL", "conservada") and real_c0["estado"] == "probado":
        c = cs.get(real_c0["certificado"], {})
        if c.get("procedencia") in mutados or real_c0["certificado"] in mutados:
            fallos.append("REAL(c0) desde R0'")
    if fallos:
        return {"resultado": "fallo", "fallos": fallos}
    desc = [d for d in f1.get("descartados", []) if d[1] in mutados and d[2] in admitidos]
    rech = (f1["informe"].get("rechazos_transferencia") or {}).get("c0") or []
    rech_ok = [r for r in rech if r.get("codigo") in admitidos]
    q_real_c0 = [c for c in _certs(celda / "P").values()]  # noqa: F841 (documental)
    unico = _unico_R0(celda / "Q" if False else celda, R1)
    diag = bool(desc) or (bool(rech_ok) and unico)
    completo = real_c0["origen"] == "directa" and real_c0["estado"] == "probado" and \
        all(cel["origenes"][f"REAL({c})"] == "R-REAL" == gem["origenes"][f"REAL({c})"] for c in ("c1", "c2"))
    if diag and completo:
        return {"resultado": "superado (rechazo estructurado, operación completa)", "descartados": desc,
                "rechazos": rech_ok}
    return {"resultado": "inconcluso", "motivo": "rechazo sin diagnóstico estructurado enlazado" if not diag
            else "operación incompleta", "descartados": f1.get("descartados"), "rechazos": rech}


CONSERVADOS_K3 = ("clase", "herramienta", "estado", "contraejemplo", "segundos")


def intervencion_K3_aplicada(t):
    """esperado.json K3: `obligacion` intercambiada entre las dos obligaciones, `detalle` = '(CBMC)', y orden, clase,
    herramienta, estado, contraejemplo y segundos conservados."""
    a, d = t.get("antes", {}).get("obligaciones", []), t.get("despues", {}).get("obligaciones", [])
    if len(a) != 2 or len(d) != 2 or a[0]["obligacion"] == a[1]["obligacion"]:
        return False
    if d[0]["obligacion"] != a[1]["obligacion"] or d[1]["obligacion"] != a[0]["obligacion"]:
        return False
    if any(x.get("detalle") != "(CBMC)" for x in d):
        return False
    if any(a[i].get(c) != d[i].get(c) for i in range(2) for c in CONSERVADOS_K3):
        return False
    return t["antes"].get("estado") == t["despues"].get("estado")


def _es_c0(raiz, af):
    rv = leer(pathlib.Path(raiz) / "objetos" / "revisiones" / f"{af['sujetos']['candidata']}.json")
    r = leer(pathlib.Path(raiz) / "objetos" / "ranuras" / f"{rv['ranura']}.json")
    return r["nombre"] == "c0"


def _unico_R0(celda, R1):
    """¿R0' es el único certificado REAL(c0, ·) de Q antes de la fase 1? (precondición de la rama (b))."""
    disco = leer(celda / "disco-Q-antes-fase1.json") if (celda / "disco-Q-antes-fase1.json").exists() else {}
    Q = celda / "Q"
    afs = _afs(Q)
    n = 0
    for ruta in disco:
        if ruta.startswith("objetos/certificados/"):
            cid = ruta.split("/")[-1][:-5]
            p = Q / ruta
            if not p.exists():
                continue
            c = leer(p)
            a = afs.get(c["afirmacion"])
            if a and a.get("clase") == "REAL" and _es_c0(Q, a):
                n += 1 if cid != R1 else 0
    return n == 0


def evaluar_B(k, esp, cel, celdas, rep, salida):
    """Controles de calibración de B (esperado.json, `calibracion_B`). El gemelo se toma de esperado.json (I6)."""
    n = _num(k)
    celda = celda_de(cel)
    f1 = _f1(celda)
    if cel["inconclusa"]:
        return {"resultado": "inconcluso", "motivo": cel["inconclusa"]}
    tr = leer(celda / "trazas-fase1.json")
    firma = lambda ts: [(t["obligacion"], t["clave"], t["acierto"], t["estado"]) for t in ts]  # noqa: E731
    if n == 2:
        ok = all(t["acierto"] for t in tr) and cel["n"] == 0
        return {"resultado": "superado" if ok else "fallo (calibración de B)", "n_B": cel["n"],
                "fallos_de_cache": [t["obligacion"] for t in tr if not t["acierto"]]}
    gemelo = esp.get("gemelo")
    gem = celdas.get((gemelo, "B", rep)) if gemelo else None
    if gem is None or gem["inconclusa"]:
        return {"resultado": "inconcluso", "motivo": f"gemelo {gemelo} ausente o inconcluso"}
    tg = leer(celda_de(gem) / "trazas-fase1.json")
    if n == 1:
        if not tr or not all(t["etiqueta"].startswith("(etiqueta de control) ") for t in tr):
            return {"resultado": "inconcluso", "motivo": "intervención no aplicada"}
        ok = firma(tr) == firma(tg) and cel["n"] == gem["n"] and cel["estados"] == gem["estados"]
        return {"resultado": "superado" if ok else "fallo (calibración de B)", "gemelo": gemelo}
    mut = leer(celda / "mutacion-B.json") if (celda / "mutacion-B.json").exists() else {}
    if mut.get("error") or mut.get("diff") != ["cache-B.json"]:
        return {"resultado": "inconcluso", "motivo": "intervención no aplicada", "mutacion": mut}
    if n == 4:
        ok = firma(tr) == firma(tg) and cel["n"] == gem["n"] and cel["estados"] == gem["estados"]
        return {"resultado": "superado" if ok else "fallo (calibración de B)", "gemelo": gemelo}
    E0, E1 = mut["E0"], mut.get("E0'")
    usan = [t["obligacion"] for t in tg if t["acierto"] and t["clave"] == E0]
    if not usan:
        return {"resultado": "inconcluso", "motivo": "en el gemelo ninguna obligación acierta en E0"}
    fallos = []
    if any(t["acierto"] and t["clave"] in (E1, E0) for t in tr):
        fallos.append("acierto en E0' (o en E0, retirada del clon)")
    if [t["obligacion"] for t in tr] != [t["obligacion"] for t in tg]:
        fallos.append("secuencia de llamadas distinta del gemelo")
    for t, g in zip(tr, tg):
        if g["acierto"] and g["clave"] == E0:          # afectada: misma consulta, ahora delegada
            if t["clave"] != g["clave"] or t["acierto"] or t["estado"] != g["estado"]:
                fallos.append(f"{t['obligacion']}: la llamada afectada no es la misma consulta delegada")
        elif (t["obligacion"], t["clave"], t["acierto"], t["estado"]) != \
                (g["obligacion"], g["clave"], g["acierto"], g["estado"]):    # I5: resto igual al gemelo
            fallos.append(f"{t['obligacion']}: traza no afectada distinta del gemelo")
    if cel["n"] != gem["n"] + len(usan):
        fallos.append(f"n_B = {cel['n']} ≠ {gem['n']} + {len(usan)}")
    no_afectadas = lambda ts, ref: sum(1 for t, g in zip(ts, ref) if not t["acierto"] and not (  # noqa: E731
        g["acierto"] and g["clave"] == E0))
    if no_afectadas(tr, tg) != no_afectadas(tg, tg):
        fallos.append("N de las llamadas no afectadas distinto del gemelo")
    if cel["estados"] != gem["estados"]:
        fallos.append("estados distintos del gemelo")
    if n == 5 and not any(d["clave"] == E0 and d["motivo"] == "clave ≠ sha256(texto)"
                          for d in f1.get("descartadas", [])):
        fallos.append("sin diagnóstico del cargador")
    return {"resultado": "fallo (calibración de B)" if fallos else "superado", "fallos": fallos,
            "obligaciones_en_E0": usan, "gemelo": gemelo}


# --- decisiones globales (ficha §Hipótesis, §Repeticiones y análisis) ---------------------------------------

def clase_R3(NC, NB):
    if NB == 0:
        return "igualdad" if NC == 0 else "inferioridad"
    rho = NC / NB
    return "superioridad estricta" if rho < 1 else ("igualdad" if NC == NB else "inferioridad")


ORDEN_R3 = {"inferioridad": 0, "igualdad": 1, "superioridad estricta": 2}


def _r2_r3(trans, agregado, estratos):
    N = {c: sum(agregado[f"{e}|{c}"]["n"] for e in trans) for c in "ABC"}
    reverif = sorted(e for e in trans if agregado[f"{e}|C"].get("reverif_identicas"))
    negativos = sorted(e for e in trans if agregado[f"{e}|C"]["n"] > agregado[f"{e}|A"]["n"])
    r2 = "sostenida" if N["C"] < N["A"] and not reverif else "refutada"
    rho = N["C"] / N["B"] if N["B"] else None
    r3 = {"N": N, "N_C_menos_N_B": N["C"] - N["B"], "rho": rho, "clase": clase_R3(N["C"], N["B"]),
          "indiferencia_practica": rho is not None and 0.90 <= rho <= 1.10,
          "superioridad_refutada": N["C"] >= N["B"]}
    por_estrato = {}
    for est in sorted(set(estratos.values())):
        ts = [e for e in trans if estratos[e] == est]
        n = {c: sum(agregado[f"{e}|{c}"]["n"] for e in ts) for c in "ABC"}
        por_estrato[est] = {"transiciones": len(ts), "N": n, "clase_R3": clase_R3(n["C"], n["B"]),
                            "rho": n["C"] / n["B"] if n["B"] else None, "N_C_menos_N_B": n["C"] - n["B"]}
    return {"R2": {"clase": r2, "N_A": N["A"], "N_C": N["C"], "rho_A": N["C"] / N["A"] if N["A"] else None,
                   "reverificaciones_identicas": reverif, "transiciones_nC_mayor_nA": negativos},
            "R3": r3, "estratos": por_estrato}


def _publicar(x):
    r3 = x["R3"]
    return {"R2": x["R2"]["clase"], "R3": r3["clase"], "N_A": r3["N"]["A"], "N_B": r3["N"]["B"], "N_C": r3["N"]["C"],
            "rho": r3["rho"], "N_C_menos_N_B": r3["N_C_menos_N_B"], "rho_A": x["R2"]["rho_A"]}


def _resumen_control(resultados):
    rs = [r["resultado"] for r in resultados]
    if any(r == "parada global" for r in rs):
        return "parada global"
    if any(r.startswith("fallo") for r in rs):
        return "fallo"
    if rs and all(r.startswith("superado") for r in rs):
        return "superado"
    return "inconcluso"


def decisiones(conjunto, salida, agregado, controles):
    """Decisiones de R1, R2 y R3 con la precedencia de la ficha: 1 parada global; 2 fallo de calibración (para la
    comparación; R1 refutado solo si hay violación confirmada); 3 violación confirmada; 4 umbral de inconclusos
    (> 5 % de las transiciones en alguna condición); 5 exclusión de la unión pareada. Robustez con y sin las
    transiciones `meta.contaminada` (sin leer nada más que los metadatos del conjunto)."""
    orden = leer(conjunto / "orden.json")
    T = orden["transiciones"]
    meta = {e: leer(conjunto / e / "meta.json") for e in T}
    estratos = {e: estrato(meta[e]) for e in T}
    contaminadas = sorted(e for e in T if meta[e].get("contaminada"))
    umbral = 0.05 * len(T)
    falta = {"inconclusa": ["sin celda"], "n": 0, "calibracion": [], "violaciones": []}
    cel = lambda e, c: agregado.get(f"{e}|{c}", falta)  # noqa: E731
    inc = {c: sorted(e for e in T if cel(e, c)["inconclusa"]) for c in "ABC"}
    union = sorted(set().union(*inc.values()))
    parada = (salida / "PARADA.json").exists()
    calib = [{"celda": k, **x} for k, v in agregado.items() for x in v["calibracion"]]
    ctrl = {}
    for k, r in controles.items():
        e, c, _ = k.split("|")
        ctrl.setdefault((e, c), []).append(r)
    ctrl_C = {e: _resumen_control(rs) for (e, c), rs in ctrl.items() if c == "C"}
    ctrl_B = {e: _resumen_control(rs) for (e, c), rs in ctrl.items() if c == "B"}
    calib += [{"celda": f"{e}|B", "tipo": "control_B_fallido"} for e, r in ctrl_B.items() if r == "fallo"]
    calib += [{"celda": f"{e}|C", "tipo": "control_C_calibracion"} for (e, c), rs in ctrl.items()
              if c == "C" for r in rs if r.get("calibracion")]
    viol = [{"celda": k, **v} for k, v in agregado.items() if k.endswith("|C") for v in v["violaciones"]
            if v.get("confirmada")]
    ctrl_fallo = sorted(e for e, r in ctrl_C.items() if r == "fallo")
    # R1
    if parada:
        r1 = "refutada" if viol or ctrl_fallo else "parada global"
    elif viol or ctrl_fallo:
        r1 = "refutada"
    elif calib:
        r1 = "inconclusa por calibración"
    elif any(len(v) > umbral for v in inc.values()):     # G2: precedencia 4, en cualquier condición
        r1 = "no refutada, cobertura insuficiente"
    elif any(r != "superado" for r in ctrl_C.values()):
        r1 = "no refutada, controles incompletos"
    else:
        r1 = "sostenida"
    obls_C = [o for e in T for o in (cel(e, "C").get("estados") or {}).values()]
    denominadores = {"O_decididas": sum(1 for o in obls_C if o in ("probado", "refutado")), "O_total": 9 * len(T),
                     "EQ_emitidas": sum((cel(e, "C").get("emitidas") or {}).get("EQ", 0) for e in T),
                     "REFUT_emitidas": sum((cel(e, "C").get("emitidas") or {}).get("REFUT", 0) for e in T),
                     "controles_C": {r: sum(1 for x in ctrl_C.values() if x == r) for r in set(ctrl_C.values())}}
    out = {"precedencia": None, "R1": {"clase": r1, "violaciones_confirmadas": viol, "controles_fallidos": ctrl_fallo,
                                         "denominadores": denominadores},
           "inconclusas": inc, "umbral_inconclusas": f"> {umbral:g} (5 % de {len(T)})", "union_pareada": union,
           "calibracion": calib, "controles_C": ctrl_C, "controles_B": ctrl_B, "contaminadas": contaminadas,
           "parada_global": parada}
    if parada:
        out["precedencia"], out["R2"], out["R3"] = 1, "no informado (parada global)", "no informado (parada global)"
    elif calib:
        out["precedencia"], out["R2"], out["R3"] = 2, "no informado (fallo de calibración)", \
            "no informado (fallo de calibración)"
    elif any(len(v) > umbral for v in inc.values()):
        # G3: con violación confirmada manda la precedencia 3 (R1 refutada); el umbral se registra además
        out["precedencia"] = 3 if viol or ctrl_fallo else 4
        out["R2"], out["R3"] = "inconcluso (umbral)", "inconcluso (umbral)"
        out["motivos"] = (["3: violación confirmada en C (R1 refutada)"] if viol or ctrl_fallo else []) + \
            ["4: umbral de inconclusos superado (R2 y R3 inconclusos)"]
    else:
        out["precedencia"] = 3 if viol or ctrl_fallo else 5
        decididas = [e for e in T if e not in union]
        todas = _r2_r3(decididas, agregado, estratos)
        sin = _r2_r3([e for e in decididas if e not in contaminadas], agregado, estratos)
        robusto = {"R2": todas["R2"]["clase"] == sin["R2"]["clase"], "R3": todas["R3"]["clase"] == sin["R3"]["clase"]}
        r2 = todas["R2"] if robusto["R2"] else {**todas["R2"], "clase": "refutada (no robusto)"}
        r3 = dict(todas["R3"])
        if not robusto["R3"]:
            peor = min(todas["R3"]["clase"], sin["R3"]["clase"], key=ORDEN_R3.get)
            r3["clase"] = f"{peor} (no robusto)"
        if any(r != "superado" for r in ctrl_B.values()):
            r3["interpretacion"] = "no interpretable (calibración de B incompleta)"
        out.update({"R2": r2, "R3": r3, "estratos": todas["estratos"], "excluidas_R2_R3": union,
                    "robustez": {"con_todas": {"R2": todas["R2"]["clase"], "R3": todas["R3"]["clase"]},
                                 "sin_contaminadas": {"R2": sin["R2"]["clase"], "R3": sin["R3"]["clase"]},
                                 "misma_clase": robusto, "contaminadas": contaminadas,
                                 # G4: los dos agregados completos, cada cifra con su agregado
                                 "agregados": {
                                     "con_todas": {"transiciones": len(decididas), **_publicar(todas)},
                                     "sin_contaminadas": {"transiciones": len(decididas) - len(
                                         [e for e in decididas if e in contaminadas]), **_publicar(sin)}},
                                 "cifras_de_R2_R3_publicados": "con_todas; la clase, la peor de ambos si no es "
                                                               "robusto"}})
    if r1 == "refutada" and out["precedencia"] == 2:
        out["R1"]["nota"] = "refutada por violación confirmada; la calibración no la borra"
    return out


def escribir_instrumento():
    """Borrador de INSTRUMENTO.sha256 (§Artefactos): instrumento, versiones y semillas, artefactos congelados,
    efch/*.py, scripts/vendor_z3.sh, especificacion/ y el árbol extraído de Z3. Lo congela el coordinador."""
    rutas = [AQUI / n for n in sorted(INSTRUMENTO + ("INSTRUMENTO-versiones.txt",))]
    rutas += [AQUI / n for n in ("MANIFIESTO.sha256", "BASE-efch.sha256", "generar.py", "comprobar_sintaxis.py")]
    rutas += [AQUI / "preparacion" / "orden.json"] + sorted((RAIZ / "efch").glob("*.py")) + \
        [RAIZ / "scripts" / "vendor_z3.sh"]
    for d in (RAIZ / "especificacion", RAIZ / ".vendor" / "z3-5.1.0.0"):
        rutas += sorted((p for p in d.rglob("*") if p.is_file() and "__pycache__" not in p.parts),
                        key=lambda p: str(p.relative_to(RAIZ)).encode())
    (AQUI / "INSTRUMENTO.sha256").write_text("".join(f"{sha_archivo(p)}  {p.relative_to(RAIZ)}\n" for p in rutas))
    return len(rutas)


# --- principal ----------------------------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--preparacion", action="store_true")
    g.add_argument("--evaluacion", action="store_true")
    ap.add_argument("--autorizacion")
    ap.add_argument("--salida")
    ap.add_argument("--reps", type=int, default=5)
    ap.add_argument("--solo", nargs="*")
    ap.add_argument("--solo-analisis", action="store_true")
    if "--escribir-instrumento" in sys.argv:
        print(f"INSTRUMENTO.sha256: {escribir_instrumento()} huellas (borrador)")
        return 0
    a = ap.parse_args()
    if a.evaluacion:
        if not a.autorizacion:
            sys.exit("ejecutar: --evaluacion exige --autorizacion REF (decisión del autor)")
        conjunto = AQUI / "evaluacion"
        os.environ["EXP019_AUTORIZACION_EVALUACION"] = a.autorizacion
    else:
        conjunto = AQUI / "preparacion"
    salida = pathlib.Path(a.salida).resolve() if a.salida else RAIZ / "resultados" / "exp019" / \
        ("preparacion" if a.preparacion else "evaluacion")
    if a.preparacion and "evaluacion" in str(salida):
        sys.exit("ejecutar: la preparación no escribe en una salida de evaluación")
    env = {"EXP019_INYECCION": os.environ["EXP019_INYECCION"]} if os.environ.get("EXP019_INYECCION") else None
    parada = None
    if not a.solo_analisis:
        try:
            ejecutar(conjunto, salida, a.reps, a.solo, env)
        except Parada as e:
            parada = str(e)
            escribir(salida / "PARADA.json", {"parada_global": parada})
            print(f"PARADA GLOBAL: {parada}")
            return 3
    celdas, agregado, controles, decision = analizar(conjunto, salida, a.reps)
    escribir(salida / "analisis.json", {"celdas": {"|".join(map(str, k)): v for k, v in celdas.items()},
                                        "agregado": agregado, "controles": controles, "decision": decision})
    print(f"analizadas {len(celdas)} ejecuciones de celda; {len(agregado)} celdas; {len(controles)} controles; "
          f"R1: {decision['R1']['clase']}; precedencia {decision['precedencia']}")
    if decision["parada_global"]:
        return 3
    return 2 if decision["calibracion"] else 0


if __name__ == "__main__":
    sys.exit(main())
