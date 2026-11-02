"""EXP-019: confirmador independiente de los vínculos fuente → revisión / contenido (ficha, §O2, «Alcance del
validador y confirmación independiente de las fuentes»).

Sin `efch`, sin `especificacion` y sin código de O2 (contraste.py): tokenizador por expresión regular y reimpresor
por flujo de tokens, distintos. Recalcula la fuente normalizada de cada ranura desde antes/despues/candidatas.efch y
la compara con el campo `fuente` de la revisión que el almacén de C asigna a esa ranura en S_a y en S_d (enlazada por
los campos de la ranura JSON, no por hashes); comprueba que las igualdades de `id` entre S_a y S_d coinciden con «la
fuente propia o la de alguna dependencia transitiva cambió», y las de `contenido` con la expansión propia.

    python3 -I confirmar_fuentes.py --entrada DIR --almacen DIR --salida FASE1.json --out OUT.json
"""

import argparse
import json
import pathlib
import re

TOKEN = re.compile(r'"(?:\\.|[^"\\])*"|;[^\n]*|[()]|[^\s()";]+')


def tokens(texto):
    out = []
    for t in TOKEN.findall(texto):
        if t.startswith(";"):
            continue
        if t.startswith('"'):
            out.append(("S", re.sub(r"\\(.)", r"\1", t[1:-1])))
        else:
            out.append(("T", t))
    return out


def formas(toks):
    """Divide la secuencia de tokens en las formas de primer nivel dentro de (efch 0.1 ...)."""
    prof, actual, out = 0, [], []
    for t in toks[3:-1]:                          # sin '(' 'efch' '0.1' ... ')'
        actual.append(t)
        if t == ("T", "("):
            prof += 1
        elif t == ("T", ")"):
            prof -= 1
            if prof == 0:
                out.append(actual)
                actual = []
    return out


def reimprimir(toks):
    partes, previo = [], None
    for k, v in toks:
        s = ('"' + v.replace("\\", "\\\\").replace('"', '\\"') + '"') if k == "S" else v
        if partes and not (previo == "(" or s == ")"):
            partes.append(" ")
        partes.append(s)
        previo = s if k == "T" else None
    return "".join(partes)


def subforma(toks, cabeza):
    """Primera subforma (cabeza ...) de nivel 1 dentro de la forma `toks`."""
    prof = 0
    for i, t in enumerate(toks):
        if t == ("T", "("):
            prof += 1
            if prof == 2 and toks[i + 1] == ("T", cabeza):
                j, p = i, 0
                while True:
                    if toks[j] == ("T", "("):
                        p += 1
                    elif toks[j] == ("T", ")"):
                        p -= 1
                        if p == 0:
                            return toks[i:j + 1]
                    j += 1
        elif t == ("T", ")"):
            prof -= 1
    return None


def llamadas(toks):
    return sorted({toks[i + 2][1] for i in range(len(toks) - 2)
                   if toks[i] == ("T", "(") and toks[i + 1] == ("T", "call")})


def ranuras(texto_defs, texto_cands):
    m = {}
    for fs, tipo in ((formas(tokens(texto_defs)), "computacion"), (formas(tokens(texto_cands)), "candidata")):
        for f in fs:
            nombre = f[2][1]
            cuerpo = subforma(f, "semantics" if tipo == "computacion" else "body")[2:-1]
            entradas = [f[i + 2][1] for i in range(len(f) - 2) if f[i] == ("T", "(") and f[i + 1] == ("T", "input")]
            m[(tipo, nombre)] = {"fuente": reimprimir(f), "cuerpo": cuerpo, "entradas": entradas,
                                 "llamadas": llamadas(cuerpo)}
    for k, v in m.items():
        if k[0] == "candidata":
            v["entradas"] = m[("computacion", "f")]["entradas"]
    return m


def expandir(m, cuerpo, env):
    """Expansión por sustitución de tokens: (call g a) -> cuerpo de g con sus entradas sustituidas."""
    out, i = [], 0
    while i < len(cuerpo):
        t = cuerpo[i]
        if t == ("T", "(") and i + 1 < len(cuerpo) and cuerpo[i + 1] == ("T", "call"):
            g = m[("computacion", cuerpo[i + 2][1])]
            j, args, p, ini = i + 3, [], 0, i + 3
            while True:
                if cuerpo[j] == ("T", "("):
                    p += 1
                elif cuerpo[j] == ("T", ")"):
                    if p == 0:
                        break
                    p -= 1
                if p == 0:
                    args.append(cuerpo[ini:j + 1])
                    ini = j + 1
                j += 1
            args = [expandir(m, a, env) for a in args]
            out += expandir(m, g["cuerpo"], dict(zip(g["entradas"], args)))
            i = j + 1
        elif t[0] == "T" and t[1] in env:
            out += env[t[1]]
            i += 1
        else:
            out.append(t)
            i += 1
    return out


def principal():
    ap = argparse.ArgumentParser()
    for x in ("--entrada", "--almacen", "--salida", "--out"):
        ap.add_argument(x, required=True)
    a = ap.parse_args()
    d = pathlib.Path(a.entrada)
    tc = (d / "candidatas.efch").read_text(encoding="utf-8")
    M = {"a": ranuras((d / "antes.efch").read_text(encoding="utf-8"), tc),
         "d": ranuras((d / "despues.efch").read_text(encoding="utf-8"), tc)}
    sal = json.loads(pathlib.Path(a.salida).read_text(encoding="utf-8"))
    obj = {}
    for p in pathlib.Path(a.almacen, "objetos").glob("*/*.json"):
        obj.setdefault(p.parent.name, {})[p.stem] = json.loads(p.read_text(encoding="utf-8"))
    rans = obj.get("ranuras", {})

    def clave(rid):
        r = rans[rid]
        if r["tipo"] == "candidata":
            if rans.get(r["ambito"], {}).get("nombre") != "f":
                return None
        return (r["tipo"], r["nombre"])
    S = {"a": obj["instantaneas"][sal["S_a"]], "d": obj["instantaneas"][sal["S_d"]]}
    rev = {s: {clave(r): obj["revisiones"][v] for r, v in S[s]["revisiones"].items()} for s in S}
    discrepancias, enlaces = [], {}

    def cambio_propio(k, vistos=()):
        if M["a"][k]["fuente"] != M["d"][k]["fuente"]:
            return True
        return any(cambio_propio(("computacion", g)) for g in M["d"][k]["llamadas"] if g not in vistos)
    for k in M["a"]:
        for s in ("a", "d"):
            v = rev[s].get(k)
            if v is None:
                discrepancias.append({"tipo": "ranura_sin_revision", "ranura": k, "S": s})
                continue
            if reimprimir(tokens(v["fuente"])) != M[s][k]["fuente"]:
                discrepancias.append({"tipo": "fuente_distinta", "ranura": k, "S": s})
        if k in rev["a"] and k in rev["d"]:
            id_igual = rev["a"][k]["id"] == rev["d"][k]["id"]
            propio = not cambio_propio(k)
            ent = M["a"][k]["entradas"]
            ea = expandir(M["a"], M["a"][k]["cuerpo"], {e: [("T", f"#{i}")] for i, e in enumerate(ent)})
            ed = expandir(M["d"], M["d"][k]["cuerpo"], {e: [("T", f"#{i}")] for i, e in enumerate(ent)})
            ct_igual = rev["a"][k]["contenido"] == rev["d"][k]["contenido"]
            if id_igual != propio:
                discrepancias.append({"tipo": "identidad", "ranura": k, "efch_igual": id_igual,
                                      "propio_igual": propio})
            if ct_igual != (ea == ed):
                discrepancias.append({"tipo": "contenido", "ranura": k, "efch_igual": ct_igual,
                                      "propio_igual": ea == ed})
            enlaces["/".join(k)] = {"id_igual_efch": id_igual, "sin_cambio_propio": propio,
                                    "contenido_igual_efch": ct_igual, "expansion_igual": ea == ed}
    pathlib.Path(a.out).write_text(json.dumps({"enlaces": enlaces, "discrepancias": discrepancias}, indent=1,
                                              ensure_ascii=False, sort_keys=True, default=list), encoding="utf-8")


if __name__ == "__main__":
    principal()
