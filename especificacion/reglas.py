"""Validación semántica de certificados: cierre, vigencia y reglas de inferencia (ESPECIFICACION.md, §5–§6).

Normativo. `Validador(paquete).validar(id)` acepta un certificado solo si él **y toda su cadena** (premisas y
procedencia, recursivamente, hasta hojas directas) cumplen las reglas. `reutilizable(id, instantanea)` añade la
vigencia en la instantánea donde se quiere usar. Un rechazo lleva el código del primer fallo encontrado y la ruta
de premisas que llevó hasta él.

Las hojas directas son la única confianza: su veredicto no se comprueba aquí (lo contrastan los oráculos), pero sí
que afirmen lo que dicen haber verificado, con la base y el cierre de su instantánea.
"""

from . import canon
from . import contrato as k
from .contrato import Rechazo

REGLA_CLASE = {"R-PROP": "PROP", "R-REAL": "REAL", "R-REFUT": "REFUT"}

# Relajaciones: solo para que exploracion.py demuestre que cada comprobación es necesaria. Nunca en uso normal.
RELAJACIONES = ("contexto", "recursion", "vigencia", "base", "cierre", "objeto", "estado_origen", "eq", "wd_a",
                "wd_d", "wd_c", "fuente", "candidata", "evaluacion", "testigo", "cobertura")


class Validador:
    def __init__(self, paquete, relajar=()):
        k.validar_paquete(paquete)
        desconocidas = set(relajar) - set(RELAJACIONES)
        if desconocidas:
            raise ValueError(f"relajaciones desconocidas: {sorted(desconocidas)}")
        self.p = paquete
        self.relajar = frozenset(relajar)
        self._validos = {}
        self._en_curso = set()
        self._objetos = {}           # (tabla, id) -> objeto ya validado en su forma
        self._afirmaciones = {}
        # Prevalidación global (§4): la forma de todos los objetos, en orden de tabla y de id, antes de nada más.
        formas = {"ranuras": k.validar_ranura, "revisiones": k.validar_revision,
                  "instantaneas": k.validar_instantanea, "certificados": k.validar_certificado,
                  "registros": k.validar_registro,
                  "afirmaciones": lambda x, r: k.validar_afirmacion(x, r, exigir_contexto="contexto" not in relajar)}
        for tabla in sorted(k.TABLAS):
            for oid in sorted(paquete[tabla]):
                self._obj(tabla, oid, "paquete", formas[tabla])

    # --- objetos ---------------------------------------------------------------------------------------------

    def _obj(self, tabla, oid, ruta, validar):
        if (tabla, oid) in self._objetos:
            return self._objetos[tabla, oid]
        if oid not in self.p[tabla]:
            raise Rechazo("referencia_desconocida", ruta, f"{tabla}/{oid}")
        x = self.p[tabla][oid]                            # un null presente lo rechaza la validación de forma
        validar(x, f"{ruta}<{tabla}/{oid[:12]}>")
        if x["id"] != oid:
            raise Rechazo("hash_invalido", ruta, f"{tabla}: índice {oid[:12]} ≠ id {x['id'][:12]}")
        self._objetos[tabla, oid] = x
        return x

    def ranura(self, oid, ruta):
        """La ranura; la de una candidata, con su ámbito resuelto en una ranura de computación (v2.7, §2.2)."""
        r = self._obj("ranuras", oid, ruta, k.validar_ranura)
        if r["tipo"] in k.CANDIDATAS and ("ambito-ok", oid) not in self._objetos:
            if self._obj("ranuras", r["ambito"], f"{ruta}.ambito", k.validar_ranura)["tipo"] != "computacion":
                raise Rechazo("ambito_invalido", ruta, f"el ámbito de {r['nombre']!r} no es una ranura de computación")
            self._objetos["ambito-ok", oid] = r
        return r

    def revision(self, oid, ruta):
        """La revisión, con sus dependencias comprobadas sin recursión: cada una es una revisión de computación de
        esa ranura y sus propias dependencias están en este mismo mapa (el mapa es transitivo y coherente)."""
        if ("rev-ok", oid) in self._objetos:
            return self._objetos["rev-ok", oid]
        v = self._obj("revisiones", oid, ruta, k.validar_revision)
        self.ranura(v["ranura"], ruta)
        for rk in sorted(v["dependencias"]):
            if self.ranura(rk, ruta)["tipo"] != "computacion":
                raise Rechazo("tipo_invalido", ruta, "solo se depende de computaciones")
            d = self._obj("revisiones", v["dependencias"][rk], ruta, k.validar_revision)
            if d["ranura"] != rk:
                raise Rechazo("cierre_incoherente", ruta, "la dependencia es de otra ranura")
            for dk in sorted(d["dependencias"]):
                if dk == v["ranura"] or v["dependencias"].get(dk) != d["dependencias"][dk]:
                    raise Rechazo("cierre_incoherente", ruta, "dependencias no transitivas o incoherentes")
        self._objetos["rev-ok", oid] = v
        return v

    def instantanea(self, oid, ruta):
        return self._obj("instantaneas", oid, ruta, k.validar_instantanea)

    def afirmacion(self, oid, ruta):
        """La afirmación con sus sujetos resueltos y comprobados (§3.1)."""
        if oid in self._afirmaciones:
            return self._afirmaciones[oid]
        a = self._obj("afirmaciones", oid, ruta,
                      lambda x, r: k.validar_afirmacion(x, r, exigir_contexto="contexto" not in self.relajar))
        suj = {}
        for papel in sorted(a["sujetos"]):
            v = self.revision(a["sujetos"][papel], f"{ruta}.{papel}")
            if v["semantica"] != a["semantica"]:
                raise Rechazo("semantica_distinta", ruta, papel)
            tipo = self.ranura(v["ranura"], ruta)["tipo"]
            if tipo not in k.PAPELES[a["clase"]][papel]:
                raise Rechazo("tipo_sujeto_invalido", ruta, f"{papel}: {tipo}")
            suj[papel] = v
        if "candidata" in suj and self.ranura(suj["candidata"]["ranura"], ruta)["ambito"] != suj["computacion"]["ranura"]:
            raise Rechazo("tipo_sujeto_invalido", ruta, "la candidata no implementa esa computación")
        if a["clase"] == "EQ":
            if suj["nueva"]["ranura"] != suj["anterior"]["ranura"]:
                raise Rechazo("ranura_distinta", ruta, "EQ entre ranuras distintas")
            if suj["nueva"]["firma"] != suj["anterior"]["firma"]:
                raise Rechazo("firma_distinta", ruta, "EQ entre firmas distintas")
        self._afirmaciones[oid] = (a, suj)
        return a, suj

    # --- cierre, base y vigencia (§5) ------------------------------------------------------------------------

    def cierre(self, a, suj, ruta):
        """Cierre intrínseco de una afirmación: cada sujeto de `PAPELES_CIERRE` y sus dependencias de expansión."""
        out = {}
        for v in (suj[x] for x in k.PAPELES_CIERRE[a["clase"]]):
            for rk, c in [(v["ranura"], v["id"]), *sorted(v["dependencias"].items())]:
                if out.setdefault(rk, c) != c:
                    raise Rechazo("cierre_incoherente", ruta, f"ranura {rk[:12]} con dos contenidos")
        return out

    def base_de_clase(self, a, suj, S, ruta):
        comps = list(k.BASE_POR_CLASE[a["clase"]])
        tipos = {self.ranura(v["ranura"], ruta)["tipo"] for v in suj.values()}
        if "candidata-lang" in tipos:
            comps += k.EXTRA_LANG
            if a["clase"] == "REAL":
                comps += k.EXTRA_REAL_LANG
        falta = [c for c in comps if c not in S["base"]]
        if falta:
            raise Rechazo("base_incompleta", ruta, ", ".join(falta))
        return {c: S["base"][c] for c in sorted(set(comps))}

    def vigente(self, c, S, ruta):
        """¿El certificado (ya válido) habla de los objetos y la base de la instantánea S? (§5.3)"""
        if "vigencia" in self.relajar:
            return
        a, suj = self.afirmacion(c["afirmacion"], ruta)
        for rk, rev in sorted(c["cierre"].items()):
            if S["revisiones"].get(rk) != rev:
                raise Rechazo("no_vigente", ruta, f"ranura {rk[:12]}")
        if "base" not in self.relajar and c["base"] != self.base_de_clase(a, suj, S, ruta):
            raise Rechazo("no_vigente", ruta, "base de la clase distinta")

    # --- validación (§6) -------------------------------------------------------------------------------------

    def validar(self, cid, ruta="certificado"):
        """Valida la cadena en orden inverso de profundidad (sin recursión de Python: §6, profundidad sin cota)."""
        if cid not in self._validos and cid not in self._en_curso and "recursion" not in self.relajar:
            for x in self._orden(cid, ruta):
                self._validar_uno(x, ruta)
        return self._validar_uno(cid, ruta)

    def _orden(self, cid, ruta):
        """Certificados alcanzables desde `cid` por premisas y procedencia, en postorden (hojas primero)."""
        orden, visto, pila = [], set(), [(cid, False)]
        while pila:
            x, hecho = pila.pop()
            if hecho:
                orden.append(x)
                continue
            if x in visto or x in self._validos:
                continue
            visto.add(x)
            c = self.p["certificados"].get(x)
            pila.append((x, True))
            if not isinstance(c, dict):
                continue                                  # ausente o registro: _validar_uno da su código en su turno
            hijos = [c.get("procedencia")] + [c["premisas"][p] for p in sorted(c.get("premisas") or {})
                                              if isinstance(c.get("premisas"), dict)]
            for h in reversed([h for h in hijos if isinstance(h, str)]):
                pila.append((h, False))
        return orden[:-1] if orden and orden[-1] == cid else orden

    def _validar_uno(self, cid, ruta):
        if cid in self._validos:
            return self._validos[cid]
        if cid in self.p["registros"]:
            raise Rechazo("registro_como_premisa", ruta, "un registro histórico no es un certificado")
        if cid in self._en_curso:
            raise Rechazo("ciclo", ruta, cid[:12])
        self._en_curso.add(cid)
        try:
            c = self._obj("certificados", cid, ruta, k.validar_certificado)
            self._validar(c, ruta)
        finally:
            self._en_curso.discard(cid)
        self._validos[cid] = c
        return c

    def _validar(self, c, ruta):
        a, suj = self.afirmacion(c["afirmacion"], ruta)
        S = self.instantanea(c["instantanea"], ruta)
        if c["semantica"] != a["semantica"] or S["semantica"] != a["semantica"]:
            raise Rechazo("semantica_distinta", ruta)
        if c["estado"] not in k.ESTADOS_POR_CLASE[a["clase"]]:
            raise Rechazo("estado_invalido", ruta, f"{a['clase']}: {c['estado']}")
        if "cierre" not in self.relajar and c["cierre"] != self.cierre(a, suj, ruta):
            raise Rechazo("cierre_distinto", ruta)
        if "base" not in self.relajar and c["base"] != self.base_de_clase(a, suj, S, ruta):
            raise Rechazo("base_distinta", ruta)
        self.vigente(c, S, ruta)                                    # en su propia instantánea
        regla = c["regla"]
        if regla == "directa":
            if "objeto" not in self.relajar and c["objeto_verificado"] != suj[k.PRINCIPAL[a["clase"]]]["contenido"]:
                raise Rechazo("objeto_verificado_distinto", ruta)
            return
        if regla == "conservacion":
            o = self._premisa_cert(c["procedencia"], f"{ruta}/procedencia")
            if o["afirmacion"] != c["afirmacion"]:
                raise Rechazo("conservacion_afirmacion_distinta", ruta)
            if o["estado"] != c["estado"]:
                raise Rechazo("conservacion_estado_distinto", ruta)
            if "base" not in self.relajar and o["base"] != c["base"]:
                raise Rechazo("base_distinta", ruta, "la conservación exige la misma base")
            return
        if a["clase"] != REGLA_CLASE[regla]:
            raise Rechazo("regla_clase_incompatible", ruta, f"{regla} sobre {a['clase']}")
        if a["clase"] not in k.TRANSFERIBLES:
            raise Rechazo("clase_no_transferible", ruta, a["clase"])
        {"R-PROP": self._r_prop, "R-REAL": self._r_real, "R-REFUT": self._r_refut}[regla](c, a, suj, S, ruta)

    def _premisa_cert(self, cid, ruta):
        if "recursion" in self.relajar:
            if cid in self.p["registros"]:
                raise Rechazo("registro_como_premisa", ruta)
            return self._obj("certificados", cid, ruta, k.validar_certificado)
        return self.validar(cid, ruta)

    def _premisa(self, c, papel, clase, sujetos, estados, S, ruta, usados, relajacion=None):
        """Premisa `papel`: certificado válido de `clase`, con esos sujetos (ranura, contenido), con un estado de
        `estados` y vigente en S. `sujetos` = {papel del sujeto: revisión}; se comparan por id de revisión.
        `relajacion`: nombre de la relajación que la suprime (solo exploración)."""
        usados.add(papel)
        if relajacion in self.relajar:
            return None                                   # relajada: presente o no, no se exige ni sobra
        cid = c["premisas"].get(papel)
        if cid is None:
            raise Rechazo("premisa_ausente", ruta, papel)
        rp = f"{ruta}/{papel}"
        p = self._premisa_cert(cid, rp)
        pa, psuj = self.afirmacion(p["afirmacion"], rp)
        if pa["clase"] != clase or set(psuj) != set(sujetos) or any(psuj[x]["id"] != v["id"] for x, v in sujetos.items()):
            raise Rechazo("premisa_clase", rp, f"se esperaba {clase} sobre {sorted(sujetos)}")
        if p["estado"] not in estados:
            raise Rechazo("premisa_estado", rp, p["estado"])
        self.vigente(p, S, rp)
        return p, pa

    def _fin_premisas(self, c, usados, ruta):
        sobra = set(c["premisas"]) - usados
        if sobra:
            raise Rechazo("premisa_sobrante", ruta, ", ".join(sorted(sobra)))

    def _origen(self, c, clase, ruta, usados):
        usados.add("origen")
        cid = c["premisas"].get("origen")
        if cid is None:
            raise Rechazo("premisa_ausente", ruta, "origen")
        o = self._premisa_cert(cid, f"{ruta}/origen")
        oa, osuj = self.afirmacion(o["afirmacion"], f"{ruta}/origen")
        if oa["clase"] != clase:
            raise Rechazo("premisa_clase", f"{ruta}/origen", oa["clase"])
        if "estado_origen" not in self.relajar and o["estado"] != c["estado"]:
            raise Rechazo("premisa_estado", f"{ruta}/origen", "el origen tiene otro estado")
        if "base" not in self.relajar and o["base"] != c["base"]:
            raise Rechazo("base_distinta", ruta, "la base de la clase cambió entre S_a y S_d")
        return o, oa, osuj, self.instantanea(o["instantanea"], f"{ruta}/origen")

    def _cambios(self, ca, cd, ruta):
        if set(ca) != set(cd):
            raise Rechazo("ranura_nueva", ruta, "el cierre gana o pierde ranuras")
        return sorted(r for r in ca if ca[r] != cd[r])

    def _misma_ranura(self, va, vd, ruta):
        if va["ranura"] != vd["ranura"]:
            raise Rechazo("ranura_distinta", ruta)
        if va["firma"] != vd["firma"]:
            raise Rechazo("firma_distinta", ruta)

    def _r_prop(self, c, a, suj, Sd, ruta):
        usados = set()
        o, oa, osuj, Sa = self._origen(c, "PROP", ruta, usados)
        pa, pd = osuj["propiedad"], suj["propiedad"]
        self._misma_ranura(pa, pd, ruta)
        if "fuente" not in self.relajar and pa["forma_fuente"] != pd["forma_fuente"]:
            raise Rechazo("fuente_distinta", ruta, "la propiedad cambió de fuente")
        for r in self._cambios(o["cierre"], c["cierre"], ruta):
            if r == pd["ranura"]:
                continue                                  # la propia propiedad: cambio derivado, fuente comprobada
            if self.ranura(r, ruta)["tipo"] != "computacion":
                raise Rechazo("cambio_no_cubierto", ruta, r[:12])
            va = self.revision(o["cierre"][r], ruta)
            vd = self.revision(c["cierre"][r], ruta)
            self._premisa(c, f"eq:{r}", "EQ", {"nueva": vd, "anterior": va}, ("probado",), Sd, ruta, usados, "eq")
            self._premisa(c, f"wd_a:{r}", "WD", {"objeto": va}, ("probado",), Sa, ruta, usados, "wd_a")
            self._premisa(c, f"wd_d:{r}", "WD", {"objeto": vd}, ("probado",), Sd, ruta, usados, "wd_d")
        self._fin_premisas(c, usados, ruta)

    def _r_real(self, c, a, suj, Sd, ruta):
        usados = set()
        o, oa, osuj, Sa = self._origen(c, "REAL", ruta, usados)
        ca, cd = osuj["candidata"], suj["candidata"]
        if "candidata" not in self.relajar and ca["id"] != cd["id"]:
            raise Rechazo("candidata_distinta", ruta)
        fa, fd = osuj["computacion"], suj["computacion"]
        self._misma_ranura(fa, fd, ruta)
        # El cierre puede ganar o perder ranuras dentro de f (f_d pasa a llamar a h): EQ(f) lo cubre (§6).
        cubiertas = {fd["ranura"], *fa["dependencias"], *fd["dependencias"]}
        ca_, cd_ = o["cierre"], c["cierre"]
        for r in sorted(r for r in set(ca_) | set(cd_) if ca_.get(r) != cd_.get(r)):
            if "cobertura" not in self.relajar and r not in cubiertas:
                raise Rechazo("cambio_no_cubierto", ruta, r[:12])
        self._premisa(c, "eq", "EQ", {"nueva": fd, "anterior": fa}, ("probado",), Sd, ruta, usados, "eq")
        self._premisa(c, "wd_a", "WD", {"objeto": fa}, ("probado",), Sa, ruta, usados, "wd_a")
        self._premisa(c, "wd_c", "WD", {"objeto": cd}, ("probado",), Sd, ruta, usados, "wd_c")
        self._fin_premisas(c, usados, ruta)

    def _r_refut(self, c, a, suj, Sd, ruta):
        usados = set()
        o, oa, osuj, Sa = self._origen(c, "REFUT", ruta, usados)
        ca, cd = osuj["candidata"], suj["candidata"]
        if "candidata" not in self.relajar and ca["id"] != cd["id"]:
            raise Rechazo("candidata_distinta", ruta)
        fa, fd = osuj["computacion"], suj["computacion"]
        self._misma_ranura(fa, fd, ruta)
        if "testigo" not in self.relajar and canon.canonico(oa["contexto"]) != canon.canonico(a["contexto"]):
            raise Rechazo("testigo_distinto", ruta)
        ev = self._premisa(c, "evaluacion", "REFUT", suj, ("probado",), Sd, ruta, usados, "evaluacion")
        if ev is not None:
            e, ea = ev
            if ea["id"] != a["id"] or e["regla"] != "directa":
                raise Rechazo("evaluacion_no_directa", f"{ruta}/evaluacion",
                              "hace falta la reevaluación directa del mismo testigo sobre S_d")
        if "eq" in c["premisas"]:                     # opcional: política del contador de EXP-018 (§6)
            self._premisa(c, "eq", "EQ", {"nueva": fd, "anterior": fa}, ("probado",), Sd, ruta, usados)
        self._fin_premisas(c, usados, ruta)

    # --- uso -------------------------------------------------------------------------------------------------

    def reutilizable(self, cid, instantanea_id, ruta="uso"):
        """Lo que B1, E y el registro deben comprobar antes de reutilizar un certificado en una instantánea."""
        c = self.validar(cid, ruta)
        self.vigente(c, self.instantanea(instantanea_id, ruta), ruta)
        return c


def validar(paquete, cid, relajar=()):
    """Atajo: None si el certificado es válido; si no, el Rechazo."""
    try:
        Validador(paquete, relajar).validar(cid)
    except Rechazo as e:
        return e
    return None
