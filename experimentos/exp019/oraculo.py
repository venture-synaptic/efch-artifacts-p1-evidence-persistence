"""EXP-019, O1: oráculo semántico independiente (ficha, §Oráculos O1).

Sin `efch`, `especificacion` ni `z3`; se ejecuta con `python3 -I`. Lector propio (paréntesis, símbolos, enteros,
comentarios `;` fuera de cadenas y cadenas con escapes `\\c` = c) y evaluador propio módulo 2^w de literal, `x`,
`add`, `sub`, `xor`, `or`, `mul`, `neg` y `call`. `doc` y `budget` se ignoran; cualquier otra forma es
`fuera de alcance`. Las tablas son evidencia experimental exhaustiva en este dominio, nunca `probado`.

    python3 -I oraculo.py tablas ENTRADA            # tablas de S_a y S_d (JSON en la salida estándar)
    python3 -I oraculo.py expresiones < LISTA.json  # autoprueba O5: [{"w", "h", "e"}] -> tablas de e
"""

import json
import pathlib
import sys

OPERACIONES = ("add", "sub", "xor", "or", "mul", "neg", "call")


class FueraDeAlcance(Exception):
    pass


def leer(texto):
    """Lista de expresiones: listas de Python, ('sym', s), ('num', n) o ('str', s)."""
    i, n, pila, actual = 0, len(texto), [], []
    while i < n:
        c = texto[i]
        if c == ";":
            while i < n and texto[i] != "\n":
                i += 1
        elif c.isspace():
            i += 1
        elif c == "(":
            pila.append(actual)
            actual = []
            i += 1
        elif c == ")":
            if not pila:
                raise FueraDeAlcance("paréntesis de cierre sin abrir")
            hecho, actual = actual, pila.pop()
            actual.append(hecho)
            i += 1
        elif c == '"':
            j, buf = i + 1, []
            while j < n and texto[j] != '"':
                if texto[j] == "\\" and j + 1 < n:
                    j += 1
                buf.append(texto[j])
                j += 1
            if j >= n:
                raise FueraDeAlcance("cadena sin cerrar")
            actual.append(("str", "".join(buf)))
            i = j + 1
        else:
            j = i
            while j < n and not texto[j].isspace() and texto[j] not in '();"':
                j += 1
            tok = texto[i:j]
            actual.append(("num", int(tok)) if tok.isdigit() else ("sym", tok))
            i = j
    if pila:
        raise FueraDeAlcance("paréntesis sin cerrar")
    return actual


def _sym(x):
    return x[1] if isinstance(x, tuple) and x[0] == "sym" else None


def programa(texto):
    """{'computaciones': {nombre: (entradas, ancho, cuerpo)}, 'candidatas': {nombre: (implementa, cuerpo)}}."""
    formas = leer(texto)
    if len(formas) != 1 or not isinstance(formas[0], list) or _sym(formas[0][0]) != "efch":
        raise FueraDeAlcance("se esperaba (efch 0.1 ...)")
    comps, cands = {}, {}
    for f in formas[0][2:]:
        cab = _sym(f[0])
        if cab == "computation":
            entradas, ancho, cuerpo = [], None, None
            for s in f[2:]:
                k = _sym(s[0])
                if k == "input":
                    entradas.append(_sym(s[1]))
                    ancho = _ancho(s[2])
                elif k == "output":
                    ancho = _ancho(s[1])
                elif k == "semantics":
                    cuerpo = s[1]
                elif k in ("doc", "budget"):
                    continue
                else:
                    raise FueraDeAlcance(f"sección {k}")
            comps[_sym(f[1])] = (entradas, ancho, cuerpo)
        elif cab == "candidate":
            cands[_sym(f[1])] = (_sym(f[2][1]), f[3][1])
        else:
            raise FueraDeAlcance(f"forma {cab}")
    return {"computaciones": comps, "candidatas": cands}


def _ancho(t):
    if isinstance(t, list) and _sym(t[0]) == "bv" and t[1][0] == "num":
        return t[1][1]
    raise FueraDeAlcance(f"tipo {t}")


def evaluar(e, env, w, comps, prof=0):
    m = (1 << w) - 1
    if prof > 200:
        raise FueraDeAlcance("profundidad")
    if isinstance(e, tuple):
        if e[0] == "num":
            return e[1] & m
        if e[0] == "sym" and e[1] in env:
            return env[e[1]]
        raise FueraDeAlcance(f"átomo {e}")
    op = _sym(e[0])
    if op not in OPERACIONES:
        raise FueraDeAlcance(f"operación {op}")
    if op == "call":
        nombre = _sym(e[1])
        if nombre not in comps:
            raise FueraDeAlcance(f"call a {nombre}")
        entradas, _, cuerpo = comps[nombre]
        args = [evaluar(a, env, w, comps, prof + 1) for a in e[2:]]
        return evaluar(cuerpo, dict(zip(entradas, args)), w, comps, prof + 1)
    v = [evaluar(a, env, w, comps, prof + 1) for a in e[1:]]
    if op == "neg":
        return (-v[0]) & m
    if op == "sub":
        return (v[0] - v[1]) & m
    r = v[0]
    for x in v[1:]:
        r = {"add": r + x, "xor": r ^ x, "or": r | x, "mul": r * x}[op]
    return r & m


def tabla(cuerpo, entradas, w, comps):
    return [evaluar(cuerpo, {entradas[0]: x}, w, comps) for x in range(1 << w)]


def tablas_instantanea(defs, cands):
    comps = defs["computaciones"]
    w = comps["f"][1]
    out = {n: tabla(c[2], c[0], w, comps) for n, c in comps.items()}
    for n, (impl, cuerpo) in cands["candidatas"].items():
        out[n] = tabla(cuerpo, comps[impl][0], w, comps)
    return w, out


def tablas(entrada):
    d = pathlib.Path(entrada)
    try:
        cands = programa((d / "candidatas.efch").read_text(encoding="utf-8"))
        w, sa = tablas_instantanea(programa((d / "antes.efch").read_text(encoding="utf-8")), cands)
        _, sd = tablas_instantanea(programa((d / "despues.efch").read_text(encoding="utf-8")), cands)
    except FueraDeAlcance as e:
        return {"fuera_de_alcance": str(e)}
    real = {c: sd[c] == sd["f"] for c in sd if c.startswith("c")}
    eq = {n: sd[n] == sa[n] for n in ("f", "h", "q")}
    return {"ancho": w, "S_a": sa, "S_d": sd, "WD": {n: True for n in sd}, "REAL_d": real, "EQ_d_a": eq,
            "fuera_de_alcance": None}


def expresiones(lista):
    out = []
    for x in lista:
        w = x["w"]
        try:
            comps = {"h": (["x"], w, leer(x["h"])[0])}
            out.append(tabla(leer(x["e"])[0], ["x"], w, comps))
        except FueraDeAlcance as e:
            out.append({"fuera_de_alcance": str(e)})
    return out


if __name__ == "__main__":
    if sys.argv[1] == "tablas":
        json.dump(tablas(sys.argv[2]), sys.stdout, sort_keys=True)
    elif sys.argv[1] == "expresiones":
        json.dump(expresiones(json.load(sys.stdin)), sys.stdout)
    else:
        sys.exit("uso: oraculo.py tablas ENTRADA | expresiones < LISTA.json")
