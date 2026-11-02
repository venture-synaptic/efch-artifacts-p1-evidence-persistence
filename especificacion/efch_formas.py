"""Correspondencia normativa entre objetos de EFCH 0.1 y revisiones del contrato (ESPECIFICACION.md, §2.2).

Único procedimiento para los bytes de `forma_canonica`, `fuente`, `firma` y `dependencias`. Lo usan los vectores y
lo tienen que reproducir la referencia y la batería (byte a byte; `vectores/canonicos.json`). El oráculo de
elaboración de §11 lo contrasta reelaborando desde las definiciones.

| Tipo | forma_canonica | fuente | firma |
|---|---|---|---|
| computación | `Computation.canonical()` | `sexpr.dumps` de su forma `(computation …)` | `Computation.signature()` |
| propiedad | `(efch V LIG canonical(body, variables))` | `sexpr.dumps` de su forma `(property …)` | `LIG` |
| candidata (y Lang) | `Candidate.canonical(comp)` | `Candidate.source_text` (dumps de su forma `(candidate …)`) | firma de la computación |

con `LIG = (property ((x T) …))` y `V = core.LANGUAGE_VERSION`. Una candidata de EFCH Lang es la candidata del
núcleo que produce el traductor; su ranura es de tipo `candidata-lang`.

Dependencias directas: las listas `(call NOMBRE …)` de la forma fuente, recorridas como árbol (nunca como texto) y
resueltas en las computaciones de la definición; `dependencias` es su cierre transitivo {ranura: revisión}.

Identidad (v2.7, §2.2): cada objeto se indexa por el **id de su ranura** (tipo, ámbito y nombre), nunca por el
nombre. El ámbito de una candidata es el id de la ranura de la computación que implementa. Una elaboración da una
sola revisión por ranura: si dos objetos ocupan la misma ranura con revisiones distintas (propiedades homónimas, o
candidatas homónimas de la misma computación), se rechaza (`RanuraRepetida`); si la revisión es la misma, es un
único objeto.
"""

from efch import core, sexpr

from . import contrato as k

VERSION = core.LANGUAGE_VERSION


def llamadas(sx):
    """Nombres llamados en un árbol de efch.sexpr: cada lista `(call SÍMBOLO …)`, a cualquier profundidad."""
    out, pila = set(), [sx]
    while pila:
        x = pila.pop()
        if isinstance(x, sexpr.SList):
            if len(x.items) >= 2 and x.head() == "call" and isinstance(x.items[1], sexpr.Sym):
                out.add(x.items[1].name)
            pila.extend(x.items)
    return out


def ligaduras(prop):
    return "(property (" + " ".join(f"({n} {core.type_str(t)})" for n, t in prop.variables) + "))"


class RanuraRepetida(ValueError):
    """Dos objetos de una misma elaboración ocupan la misma ranura con revisiones distintas (§2.2)."""


class Formas:
    """Revisiones de una definición elaborada, con dependencias {ranura: revisión} transitivas.

    `ranuras` y `revisiones` se indexan por el id de la ranura (v2.7)."""

    def __init__(self, defn, semantica="efch-0.1"):
        self.defn, self.semantica = defn, semantica
        self.ranuras, self.revisiones = {}, {}            # id de ranura -> ranura / revisión
        self._en_curso = set()

    def _ranura(self, tipo, nombre, ambito=""):
        r = k.ranura(tipo, nombre, ambito)
        return self.ranuras.setdefault(r["id"], r)

    def _fijar(self, v, que):
        """Registra la revisión de su ranura; una ranura repetida con otra revisión se rechaza."""
        previa = self.revisiones.setdefault(v["ranura"], v)
        if previa["id"] != v["id"]:
            r = self.ranuras[v["ranura"]]
            raise RanuraRepetida(f"{que}: la ranura {r['tipo']} {r['nombre']!r} ya tiene otra revisión")
        return previa

    def ranura_computacion(self, nombre):
        return self._ranura("computacion", nombre)

    def _deps(self, sx, de):
        deps = {}
        for n in sorted(llamadas(sx)):
            if n not in self.defn.computations:
                raise ValueError(f"{de} llama a {n}, que no está en la definición")
            r = self.computacion(n)
            deps[r["ranura"]] = r["id"]
            deps.update(r["dependencias"])
        return deps

    def computacion(self, nombre):
        clave = self.ranura_computacion(nombre)["id"]
        if clave in self.revisiones:
            return self.revisiones[clave]
        if nombre in self._en_curso:
            raise ValueError(f"llamadas cíclicas en {nombre}")
        self._en_curso.add(nombre)
        comp = self.defn.computations[nombre]
        v = k.revision(self.ranura_computacion(nombre), comp.canonical(), sexpr.dumps(comp.source),
                       comp.signature(), self._deps(comp.source, nombre), self.semantica)
        self._en_curso.discard(nombre)
        return self._fijar(v, f"computación {nombre}")

    def propiedad(self, prop):
        r = self._ranura("propiedad", prop.name)
        lig = ligaduras(prop)
        v = k.revision(r, f"(efch {VERSION} {lig} {core.canonical(prop.body, prop.variables)})",
                       sexpr.dumps(prop.source), lig, self._deps(prop.source, prop.name), self.semantica)
        return self._fijar(v, f"propiedad {prop.name}")

    def candidata(self, cand, tipo="candidata"):
        comp = self.defn.computations[cand.implements]
        r = self._ranura(tipo, cand.name, self.ranura_computacion(comp.name)["id"])
        [sx] = sexpr.parse(cand.source_text)
        v = k.revision(r, cand.canonical(comp), cand.source_text, comp.signature(), self._deps(sx, cand.name),
                       self.semantica)
        return self._fijar(v, f"candidata {cand.name} de {comp.name}")


    def todas(self, candidatas=(), candidatas_lang=()):
        for n in sorted(self.defn.computations):
            self.computacion(n)
        for p in self.defn.properties:
            self.propiedad(p)
        for c in candidatas:
            self.candidata(c)
        for c in candidatas_lang:
            self.candidata(c, "candidata-lang")
        return self
