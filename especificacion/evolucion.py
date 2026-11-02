"""Modelo de evolución del registro (ESPECIFICACION.md, §9; decisiones del autor sobre D8 y D9).

Normativo en lo que distingue; abstracto en lo demás. Separa cinco cosas que el registro no debe confundir:

| Concepto | Dónde vive | ¿Cambia al evolucionar `f`? |
|---|---|---|
| Definición registrada de una ranura | `fuentes` | Solo la de `f` |
| Dependencias efectivas | `revision.dependencias` en la instantánea | Las de todo lo que expande `f` |
| Identidad del objeto | `revision.contenido` en la instantánea | La de `f` y la de su cierre inverso |
| Evidencia histórica | `almacen` (inmutable, nunca se borra) | Nunca |
| Vigencia | `reglas.Validador.reutilizable(cert, S)` | Se recalcula; no se guarda |

Consecuencias: (D8) evolucionar `f` deja obsoleta toda evidencia cuyo cierre contenga `f` —WD, propiedades,
realizaciones y refutaciones de `f`, de quien la llame y de las candidatas que las llamen— sin tocar su definición
registrada ni su evidencia histórica; (D9) un cuerpo nuevo nunca hereda la identidad antigua, porque la identidad
es el hash de lo expandido y `publicar` exige que el objeto verificado sea el de la afirmación.

Las fuentes de este modelo son texto opaco con sus llamadas declaradas; `forma_canonica` es la fuente con las
formas de sus dependencias expandidas, como hace el elaborador de EFCH.
"""

from . import contrato as k
from .reglas import Validador
from .contrato import Rechazo


class Registro:
    def __init__(self, base):
        self.base = dict(base)
        self.ranuras = {}            # id -> ranura
        self.fuentes = {}            # id de ranura -> (fuente, [ids de ranura llamadas], firma)
        self.historial = {}          # id de ranura -> [fuente, ...]
        self.revisiones, self.instantaneas, self.afirmaciones = {}, {}, {}
        self.certificados, self.registros = {}, {}
        self.S = None

    # --- definiciones e instantáneas -------------------------------------------------------------------------

    def _elaborar(self):
        """Revisiones de todas las ranuras registradas, expandiendo dependencias (sin ciclos)."""
        hechas = {}

        def rev(rid, pila=()):
            if rid in hechas:
                return hechas[rid]
            if rid in pila:
                raise ValueError("dependencia cíclica")
            fuente, llamadas, firma = self.fuentes[rid]
            deps, formas = {}, []
            for l in sorted(llamadas):
                if l not in self.fuentes:
                    raise ValueError(f"llamada a una ranura no registrada: {l[:12]}")
                v = rev(l, pila + (rid,))
                deps[l] = v["id"]
                deps.update(v["dependencias"])
                formas.append(v["forma_canonica"])
            v = k.revision(self.ranuras[rid], f"({firma} {fuente} {' '.join(formas)})", fuente, firma, deps)
            hechas[rid] = v
            self.revisiones[v["id"]] = v
            return v

        revs = [rev(r) for r in sorted(self.fuentes)]
        S = k.instantanea(revs, self.base)
        self.instantaneas[S["id"]] = S
        self.S = S
        return S

    def registrar(self, ranura, fuente, llamadas=(), firma="(x)"):
        self.ranuras[ranura["id"]] = ranura
        self.fuentes[ranura["id"]] = (fuente, list(llamadas), firma)
        self.historial.setdefault(ranura["id"], []).append(fuente)
        return self._elaborar()

    def evolucionar(self, ranura, fuente, llamadas=(), firma="(x)"):
        """Cambia la definición registrada de una sola ranura. Devuelve el informe de consecuencias (§9.2)."""
        S0 = self.S
        antes = {r: self.definicion(r) for r in self.fuentes}
        S1 = self.registrar(ranura, fuente, llamadas, firma)
        obsoletas = [c for c in sorted(self.certificados)
                     if self._reutilizable(c, S0["id"]) and not self._reutilizable(c, S1["id"])]
        return {"instantanea_anterior": S0["id"], "instantanea": S1["id"],
                "definiciones_cambiadas": sorted(r for r in self.fuentes if antes.get(r) != self.definicion(r)),
                "identidades_cambiadas": sorted(r for r in self.fuentes
                                                if S0["revisiones"].get(r) != S1["revisiones"][r]),
                "obsoletas": obsoletas}

    def definicion(self, ranura_id):
        """La definición registrada completa: fuente, llamadas declaradas y firma."""
        fuente, llamadas, firma = self.fuentes[ranura_id]
        return fuente, tuple(sorted(llamadas)), firma

    def revision_actual(self, ranura_id, S=None):
        S = S or self.S
        return self.revisiones[S["revisiones"][ranura_id]]

    def dependencias_efectivas(self, ranura_id, S=None):
        return dict(self.revision_actual(ranura_id, S)["dependencias"])

    # --- evidencia ---------------------------------------------------------------------------------------------

    def paquete(self):
        return k.paquete([r for r in self.ranuras.values() if r], self.revisiones.values(),
                         self.instantaneas.values(), self.afirmaciones.values(), self.certificados.values(),
                         self.registros.values())

    def afirmacion(self, clase, contexto=None, **sujetos):
        a = k.afirmacion(clase, contexto, **sujetos)
        self.afirmaciones[a["id"]] = a
        return a

    def publicar(self, c):
        """Añade un certificado al almacén solo si es válido (§6). La evidencia publicada nunca se modifica."""
        if c["id"] in self.certificados and self.certificados[c["id"]] != c:
            raise Rechazo("hash_invalido", "publicar", "id ya publicado con otro contenido")
        self.certificados[c["id"]] = c
        try:
            Validador(self.paquete()).validar(c["id"])
        except Rechazo:
            del self.certificados[c["id"]]
            raise
        return c

    def _reutilizable(self, cid, sid):
        try:
            Validador(self.paquete()).reutilizable(cid, sid)
            return True
        except Rechazo:
            return False

    def vigencia(self, cid, S=None):
        """None si el certificado se puede reutilizar en S; si no, el código del rechazo."""
        try:
            Validador(self.paquete()).reutilizable(cid, (S or self.S)["id"])
        except Rechazo as e:
            return e.codigo
        return None
