"""EXP-019 (H2; G5 y G0): generador determinista de las entradas de evaluación y de preparación.

Escribe, sin red, sin solucionador y sin importar `efch`:
- `evaluacion/`: 64 transiciones (bv 1..4 × 4 cuerpos × 4 cambios) y 8 controles K1..K8;
- `preparacion/`: 32 transiciones disjuntas (bv 5..6, otras operaciones y otros cambios) y 8 controles KP1..KP8;
- `orden.json`: orden de ejecución, intercalado de condiciones y repeticiones, con sus semillas.

Cada entrada tiene `antes.efch`, `candidatas.efch`, `despues.efch` y `meta.json`; los controles, además,
`esperado.json`. El oráculo no se calcula aquí (ficha docs/experimentos/EXP-019.md, «Oráculos»).

    python3 -I experimentos/exp019/generar.py      # reescribe exactamente los mismos bytes
"""

import json
import pathlib
import random
import shutil

RAIZ = pathlib.Path(__file__).resolve().parent
SEMILLA_ORDEN = 20261101          # orden e intercalado de la evaluación
SEMILLA_PREPARACION = 20261102    # orden e intercalado de la preparación
REPETICIONES = 5                  # repeticiones de la fase medida (tiempos informativos)
TIMEOUT_SMT = 120                 # segundos por invocación del solucionador, igual en las tres condiciones
CONDICIONES = ("A", "B", "C")
CUADRADO = (("A", "B", "C"), ("B", "C", "A"), ("C", "A", "B"))

EVALUACION = {
    "anchos": (1, 2, 3, 4),
    # cuerpo inicial B de f y de la candidata c0
    "cuerpos": {"id": "x", "cero": "0", "inc": "(add x 1)", "llamada": "(call h x)"},
    # variantes equivalentes por construcción: k = 3 realizaciones de f
    "variantes": {"c0": "{B}", "c1": "(add 0 {B})", "c2": "(sub (add {B} 1) 1)"},
    "h": "x", "q": "0",
    # cambio -> (computación que evoluciona, cuerpo nuevo a partir del anterior)
    "cambios": {"q": ("q", "1"), "eq": ("f", "(add {B} 0)"), "neq": ("f", "(add {B} 1)"),
                "h": ("h", "(add x 1)")},
}
PREPARACION = {
    "anchos": (5, 6),
    "cuerpos": {"xor1": "(xor x 1)", "mul3": "(mul x 3)", "neg": "(neg x)", "llamada": "(call h (xor x 1))"},
    "variantes": {"c0": "{B}", "c1": "(or {B} 0)", "c2": "(xor (xor {B} 1) 1)"},
    "h": "x", "q": "0",
    "cambios": {"q": ("q", "2"), "eq": ("f", "(xor {B} 0)"), "neq": ("f", "(xor {B} 1)"),
                "h": ("h", "(xor x 1)")},
}
# Transiciones de evaluación que repiten sondas exploratorias de Sol (resultados/preinscripcion-h2/entrada-sol/
# informe.md, A2: bv2, c = x, x → x+0 y x → x+1, cambio en call h). Se conservan para no romper la rejilla; se
# analizan con y sin ellas.
CONTAMINADAS = ("T-w2-id-eq", "T-w2-id-neq", "T-w2-llamada-h")

PRESUPUESTO = "(budget (llm-calls 0) (llm-usd 0) (smt-seconds 120))"


def computacion(nombre, w, cuerpo, doc=None):
    d = f"\n    (doc {doc})" if doc else ""
    return (f"  (computation {nombre}{d}\n    (input x (bv {w}))\n    (output (bv {w}))\n"
            f"    (semantics {cuerpo})\n    {PRESUPUESTO})")


def definicion(eid, fase, w, cuerpos, doc_f=None):
    partes = [computacion("h", w, cuerpos["h"]), computacion("q", w, cuerpos["q"]),
              computacion("f", w, cuerpos["f"], doc_f)]
    return (f"; EXP-019 {eid}, {fase}. Generado por experimentos/exp019/generar.py; no editar.\n"
            "(efch 0.1\n" + "\n".join(partes) + ")\n")


def candidatas(eid, B, variantes):
    filas = [f"  (candidate {n} (implements f)\n    (body {v.format(B=B)}))" for n, v in variantes.items()]
    return (f"; EXP-019 {eid}, candidatas (fase 0). Generado por experimentos/exp019/generar.py; no editar.\n"
            "(efch 0.1\n" + "\n".join(filas) + ")\n")


def escribir(d, nombre, texto):
    (d / nombre).write_text(texto, encoding="utf-8")


def json_txt(x):
    return json.dumps(x, ensure_ascii=False, indent=1, sort_keys=True) + "\n"


DOC_K2 = '"suma \\"cero\\"; f \\\\ sin cambio (K2)"'   # literal fuente: comillas, \\, ; y paréntesis


def transicion(dest, conj, pref, w, cn, cambio, eid=None, extra=None):
    B = conj["cuerpos"][cn]
    eid = eid or f"{pref}-w{w}-{cn}-{cambio}"
    d = dest / eid
    d.mkdir(parents=True)
    antes = {"h": conj["h"], "q": conj["q"], "f": B}
    despues = dict(antes)
    if cambio == "doc":                     # solo el (doc ...) de f: cambia la fuente, no el cuerpo
        evol, doc_f = "f", DOC_K2
    else:
        evol, nuevo = conj["cambios"][cambio]
        despues[evol] = nuevo.format(B=antes[evol])
        doc_f = None
    escribir(d, "antes.efch", definicion(eid, "antes (S_a)", w, antes))
    escribir(d, "candidatas.efch", candidatas(eid, B, conj["variantes"]))
    escribir(d, "despues.efch", definicion(eid, "después (S_d)", w, despues, doc_f))
    meta = {"id": eid, "ancho": w, "cuerpo": cn, "cambio": cambio, "evoluciona": evol,
            "cuerpos_antes": antes, "cuerpos_despues": despues, "doc_f_despues": doc_f,
            "candidatas": {n: v.format(B=B) for n, v in conj["variantes"].items()},
            "contaminada": eid in CONTAMINADAS, **(extra or {})}
    escribir(d, "meta.json", json_txt(meta))
    return d


# --- controles K (ficha, «Tareas»: procedimiento exacto, activación y ramas de resultado) -----------------------

CLON = ["fase 0 en un almacén nuevo P (subproceso 1); P se conserva intacto como evidencia",
        "shutil.copytree(P, Q)",
        "mutación sobre los archivos de Q (campo `mutacion`), escrita por el mutador sin usar efch: los objetos "
        "contractuales en la forma canónica de la v2.7 §2.1; costes.json (y la caché de B) en JSON determinista con "
        "claves ordenadas, floats finitos y tuplas como arrays",
        "comprobación de la intervención: releer Q; el diff de sha256 de todo Q frente a P es exactamente el previsto",
        "foto de integridad (disco) de Q después de la mutación y antes de la fase 1",
        "fase 1 en un subproceso nuevo con Store(Q) nuevo"]
REFIRMAR = ("refirmado: id = sha256 de la forma canónica sin `id`; el archivo se escribe con el id nuevo y el "
            "original se borra de Q (no de P); toda referencia en objetos/ al id antiguo se actualiza y su objeto se "
            "refirma igual; la clave de costes.json se traslada; pasos/ no se toca (exportaciones históricas)")
A0 = ("A0 = la única afirmación de Q/objetos/afirmaciones con clase REAL y sujetos.candidata = revisión de la ranura "
      "(candidata, ámbito f, c0) de S_a; R0 = el único certificado directa probado con afirmacion = A0")
ACT_REAL = ["en el gemelo (misma repetición), la procedencia de REAL(c0, f_d) por R-REAL es el certificado que "
            "corresponde a R0 (el objeto se habría usado)",
            "ningún objeto de Q/objetos, salvo R0, referencia A0 o R0 antes de mutar",
            "la mutación se aplicó (diff exacto) y Store(Q) se creó después"]
RAMAS_RECHAZO = {
    "superado: rechazo estructurado diagnosticado (operación completa)": [
        "rechazo estructurado con código admitido y enlazado al objeto mutado: (a) una entrada de "
        "Store(Q).descartados cuyo id es el de A0' o R0'; o (b) una entrada de informe.rechazos_transferencia['c0'] "
        "con código admitido, siendo R0' el único certificado REAL(c0, ·) de Q (precondición comprobada)",
        "ni A0' ni R0' son origen, premisa ni procedencia de ningún certificado de S_d (contraste)",
        "REAL(c0, f_d) probado por vía directa; REAL(c1, f_d) y REAL(c2, f_d) por R-REAL, como en el gemelo",
        "cero V1/V2; monitor sin modificación parcial"],
    "superado: rechazo estructurado diagnosticado (excepción)": [
        "evolve lanza un Rechazo (efch.identidad.Rechazo) con `codigo` admitido y cuya ruta o detalle contiene el id "
        "de A0' o R0'",
        "memoria y disco idénticos antes y después de la operación; aquí no se exige nada de c1 ni de c2"],
    "fallo (refuta R1)": [
        "A0' o R0' aparecen como origen, premisa o procedencia de un certificado de S_d",
        "REAL(c0, f_d) probado por R-REAL o conservada desde R0'", "cualquier V1/V2"],
    "inconcluso (no superado)": [
        "falla una precondición de activación o la comprobación de la intervención",
        "rechazo sin diagnóstico estructurado enlazado (el objeto no se usa, pero no hay código admitido enlazado)",
        "cualquier otra excepción (p. ej., KeyError(ID), IdentidadDistinta, o un Rechazo sin código admitido o sin "
        "enlace): inconcluso, nunca superado", "obligación desconocida; error del arnés"],
    "parada global": ["modificación parcial inesperada (monitor D11)"]}
INVARIANTES = ["estado, origen y regla de cada obligación de O(S_d), iguales a los del gemelo",
               "clase y conjunto de componentes de base de cada certificado de S_d, iguales",
               "n_C de la fase 1, igual", "cero V1/V2; monitor sin modificación parcial"]


def ramas_invariancia(extra_fallo=()):
    return {"superado": INVARIANTES,
            "fallo (refuta R1)": ["cualquier diferencia en un invariante", *extra_fallo],
            "inconcluso (no superado)": ["falla una precondición de activación", "alguna obligación inconclusa",
                                         "error del arnés"],
            "parada global": ["modificación parcial inesperada (monitor D11)"]}


def CONTROLES(gq, ge):
    return [
        ("nota", "cambio de etiqueta", ge, "eq", None,
         {"fase": "0 y 1", "procedimiento": ["note='etiqueta de control' en register(h, q, f)",
                                              "note='refactor equivalente (etiqueta de control)' en evolve"]},
         ["nombres.json registra las dos notas"], ramas_invariancia(), None,
         "solo que `note` no es causal; nada más"),
        ("doc", "cambio de etiqueta", None, "doc", None,
         {"fase": "1", "procedimiento": ["S_d = S_a salvo (doc ...) en f, con comillas, \\, ; y paréntesis "
                                          "escapados; evolve(f)"]},
         ["el lector propio y el de efch leen la cadena; el contraste ve fuente de f distinta y expansión igual"],
         {"superado": ["revisión de f en S_d distinta de la de S_a y mismo `contenido` (v2.7 §2.2)",
                       "WD(f_d) y REAL(ci, f_d) probado; ninguna REAL `conservada` desde S_a; origen R-REAL o "
                       "directa", "cero V1/V2; monitor sin modificación parcial"],
          "fallo (refuta R1)": ["la revisión de f no cambia (doc ignorado en la identidad) o `misma identidad`",
                                "alguna REAL(ci, f_d) conservada desde S_a", "cualquier V1/V2"],
          "inconcluso (no superado)": ["alguna obligación inconclusa", "error del arnés"],
          "parada global": ["modificación parcial inesperada (monitor D11)"]}, None,
         "identidad por fuente con doc e inocuidad semántica de doc en f; no doc en candidatas ni otras anotaciones"),
        ("nombres-de-obligacion", "cambio de etiqueta", ge, "eq", None,
         {"fase": "0", "procedimiento": ["doble sobre pipeline.verify_candidate visto por store.realize: intercambia "
                                          "`obligacion` entre las dos obligaciones y pone `detalle` = '(CBMC)'; "
                                          "conserva orden, clase, herramienta, estado, contraejemplo y segundos"]},
         ["el doble se llamó 3 veces y su traza guarda la salida antes y después"],
         {**ramas_invariancia(["ids de los objetos contractuales de la fase 0 distintos de los del gemelo"]),
          "inconcluso (no superado)": ["falla una precondición de activación", "alguna obligación inconclusa",
                                       "error del arnés", "el gemelo no reproduce sus propios ids de la fase 0 en "
                                       "sus 5 repeticiones: inconcluso del control y fallo de calibración, nunca "
                                       "superado omitiendo el invariante"]}, None,
         "frases y detalle fuera de decisiones y de objetos con hash; NO la clasificación por posición "
         "(store.py usa obls[0]): no comprobado en EXP-019"),
        ("costes", "cambio de etiqueta", gq, "q", ["realize(c0) otra vez tras c2 (segundo certificado elegible)"],
         {"fase": "clon tras la fase 0", "procedimiento": CLON, "mutacion": [
             "Q/costes.json: cada `segundos` numérico × 1000; `orden` reflejado (o' = max + min - o) en todo el "
             "archivo, de modo que se invierte el orden relativo de los dos certificados de REAL(c0, f_a)"]},
         ["Q contiene exactamente dos certificados distintos de la afirmación REAL(c0, f_a), directa, probado, de "
          "instantáneas distintas, ambos vigentes en S_d según el contraste, con `orden` distinto",
          "la mutación invirtió su orden relativo (diff exacto)", "Store(Q) creado después"],
         ramas_invariancia(["REAL(c0, f_d) no `conservada` o desde un certificado que no sea uno de los dos"]), None,
         "la selección por `orden` entre dos certificados válidos (se registra cuál elige); no puede detectar la "
         "elección de uno inválido"),
        ("ausencia-de-clase", "ausencia o contradicción", ge, "eq", None,
         {"fase": "clon tras la fase 0", "procedimiento": CLON, "objetos": A0, "mutacion": [
             "A0' = A0 sin la clave `clase`", REFIRMAR]},
         ACT_REAL, RAMAS_RECHAZO, ["campo_ausente"], "una afirmación sin clase; no otras ausencias"),
        ("contradiccion-de-clase", "ausencia o contradicción", ge, "eq", None,
         {"fase": "clon tras la fase 0", "procedimiento": CLON, "objetos": A0, "mutacion": [
             "A0' = A0 con `clase` = 'WD' y los mismos sujetos (candidata, computacion)", REFIRMAR]},
         ACT_REAL, RAMAS_RECHAZO, ["papel_invalido", "tipo_sujeto_invalido"], "una contradicción clase/papeles"),
        ("ausencia-de-herramienta", "ausencia o contradicción", ge, "eq", None,
         {"fase": "clon tras la fase 0", "procedimiento": CLON, "objetos": A0, "mutacion": [
             "R0' = R0 sin el componente `z3` en `base`", REFIRMAR]},
         ACT_REAL, RAMAS_RECHAZO, ["base_incompleta", "base_distinta", "no_vigente"],
         "un componente de herramienta ausente en la base de un certificado"),
        ("contradiccion-de-herramienta", "ausencia o contradicción", ge, "eq", None,
         {"fase": "clon tras la fase 0", "procedimiento": CLON, "objetos": A0, "mutacion": [
             "R0' = R0 con `base.z3` = '4.8.0:otra'", REFIRMAR]},
         ACT_REAL, RAMAS_RECHAZO, ["base_distinta", "no_vigente"],
         "una huella de herramienta contradictoria; no un cambio real de base (fuera de alcance)"),
    ]


# Controles pertinentes sobre la caché de B (calibración de claves, base, tipos, remapeo y reconfirmación; no
# certificados). Mismas entradas, condición B; un fallo es fallo de calibración de B, no de R1.
E0 = ("E0 = la entrada de cache-B.json cuya clave es la de la consulta WD(c0) de la fase 0 (por la traza); en el "
      "gemelo, las obligaciones de la fase 1 que aciertan en E0 quedan fijadas por su traza")
B_RECHAZO = {"superado": ["ninguna llamada de la fase 1 acierta en E0'", "las obligaciones que en el gemelo "
                          "acertaban en E0 se delegan; n_B = n_B(gemelo) + su número; resto igual al gemelo",
                          "en KB5, además, diagnóstico del cargador «clave ≠ sha256(texto)» con la clave de E0"],
             "fallo (calibración de B)": ["algún acierto en E0'", "estado distinto del gemelo",
                                          "Con activación e intervención válidas y sin error del arnés, cualquier "
                                          "incumplimiento de los requisitos de superado, incluidas delegación, `n_B` y "
                                          "diagnóstico de KB5, es fallo de calibración de B"],
             "inconcluso (no superado)": ["en el gemelo ninguna obligación de la fase 1 acierta en E0",
                                          "intervención no aplicada", "error del arnés"]}
B_INV = {"superado": ["mismas claves, aciertos, estados y n_B que el gemelo en B"],
         "fallo (calibración de B)": ["cualquier diferencia"],
         "inconcluso (no superado)": ["intervención no aplicada", "error del arnés"]}
CLON_B = ["fase 0 de B en P; copia a Q; mutación de Q/cache-B.json (JSON determinista); comprobación del diff; "
          "fase 1 de B en un subproceso nuevo que carga Q", "refirmado de entrada: clave = sha256 del texto nuevo; "
          "la entrada original se retira de Q (no de P)"]
CALIBRACION_B = {
    1: {"intervencion": ["doble sobre smt.prove en B: antepone '(etiqueta de control) ' al nombre de cada llamada"],
        "ramas": B_INV},
    2: {"intervencion": ["B sobre la entrada K2 (solo doc): la fuente no entra en N"],
        "ramas": {"superado": ["cada consulta de S_d acierta en una clave de S_a: n_B = 0"],
                  "fallo (calibración de B)": ["alguna consulta de S_d falla en la caché"],
                  "inconcluso (no superado)": ["error del arnés"]}},
    4: {"intervencion": CLON_B[:1] + ["KB4 invierte exclusivamente el orden de entradas de `cache-B.json`, sin añadir "
                                      "ni mutar campos `segundos`; exige las mismas claves, aciertos, estados y `n_B` "
                                      "que el gemelo"],
        "ramas": B_INV},
    5: {"intervencion": CLON_B[:1] + [E0, "E0' sustituye a E0 en Q: E0 sin la línea de tipos, conservando la clave "
                                          "original y sin refirmar"],
        "ramas": B_RECHAZO},
    6: {"intervencion": CLON_B + [E0, "E0' = E0 con la línea de tipos (bv w) → (bv w+1), refirmada"],
        "ramas": B_RECHAZO},
    7: {"intervencion": CLON_B + [E0, "E0' = E0 sin la base, refirmada"], "ramas": B_RECHAZO},
    8: {"intervencion": CLON_B + [E0, "E0' = E0 con base.z3 = '4.8.0:otra', refirmada"], "ramas": B_RECHAZO},
}


def controles(dest, conj, pref, w, cn, tpref):
    out = []
    gq, ge = f"{tpref}-w{w}-{cn}-q", f"{tpref}-w{w}-{cn}-eq"
    for i, (nombre, familia, gemelo, cambio, extra0, interv, activ, ramas, codigos, alcance) in \
            enumerate(CONTROLES(gq, ge), 1):
        eid = f"{pref}{i}-{nombre}"
        d = transicion(dest, conj, pref, w, cn, cambio, eid=eid,
                       extra={"control": True, "familia": familia, "gemelo": gemelo, "fase0_extra": extra0})
        esperado = {"id": eid, "familia": familia, "gemelo": gemelo, "condicion": "C", "cambio": cambio,
                    "fase0_extra": extra0, "intervencion": interv, "precondiciones_de_activacion": activ,
                    "codigos_admitidos": codigos, "ramas": ramas, "alcance": alcance,
                    "calibracion_B": CALIBRACION_B.get(i)}
        if i in CALIBRACION_B:
            esperado["condicion"] = "C (y B como calibración)"
        escribir(d, "esperado.json", json_txt(esperado))
        out.append(eid)
    return out


def orden(ids, semilla, condiciones):
    rng = random.Random(semilla)
    reps = []
    for r in range(1, REPETICIONES + 1):
        perm = list(ids)
        rng.shuffle(perm)
        reps.append({"repeticion": r, "secuencia": [
            {"entrada": e, "condiciones": list(CUADRADO[k % 3]) if condiciones(e) == CONDICIONES
             else list(condiciones(e))} for k, e in enumerate(perm)]})
    return {"semilla": semilla, "generador": "random.Random(semilla).shuffle, una vez por repetición, en orden",
            "intercalado": "cuadrado latino ABC/BCA/CAB según la posición mod 3; controles: B (calibración) y C, "
                           "salvo K3/KP3, solo C",
            "repeticiones": reps}


def generar(conj, carpeta, pref, gemelo, semilla):
    dest = RAIZ / carpeta
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir()
    ids = [transicion(dest, conj, pref, w, cn, ch).name
           for w in conj["anchos"] for cn in conj["cuerpos"] for ch in conj["cambios"]]
    gw, gc = gemelo
    kp = "K" if pref == "T" else "KP"
    ks = controles(dest, conj, kp, gw, gc, pref)
    o = orden(ids + ks, semilla, lambda e: (("C",) if "-nombres-" in e else ("B", "C")) if e.startswith("K")
              else CONDICIONES)
    o.update({"timeout_smt_s": TIMEOUT_SMT, "transiciones": ids, "controles": ks})
    (dest / "orden.json").write_text(json_txt(o), encoding="utf-8")
    return len(ids), len(ks)


if __name__ == "__main__":
    print("evaluacion", *generar(EVALUACION, "evaluacion", "T", (3, "inc"), SEMILLA_ORDEN))
    print("preparacion", *generar(PREPARACION, "preparacion", "P", (5, "xor1"), SEMILLA_PREPARACION))
