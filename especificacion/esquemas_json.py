"""Genera los JSON Schema de `esquemas/` a partir de contrato.py (ESPECIFICACION.md, §2).

    python3 -m especificacion.esquemas_json

Alcance (§2.3): los esquemas validan la forma de cada objeto **aislado**, incluidas las condiciones entre sus
propios campos que dependen del valor de un campo (ámbito según el tipo de ranura, contexto fijo según la clase,
campos de una hoja directa, origen según la vía del registro). No validan las que comparan los valores de dos
campos (§2.3), ni lo que exige calcular hashes, comprobar el dominio canónico (profundidad, rango de enteros) o
relacionar objetos: eso lo hacen contrato.py y reglas.py. Las pruebas comprueban que los vectores válidos los cumplen y que los rechazos de forma no.
"""

import json
import pathlib

from . import contrato as k

H = {"type": "string", "pattern": "^[0-9a-f]{64}$", "maxLength": 64}   # v2.6: sin LF final (§2.3)
T = {"type": "string"}
URL = "https://efch.invalid/evidencia/2.5/"


def _obj(props):
    return {"type": "object", "additionalProperties": False, "required": sorted(props), "properties": props}


def _mapa(v):
    return {"type": "object", "propertyNames": {"pattern": "^[0-9a-f]{64}$", "maxLength": 64}, "additionalProperties": v}


def esquemas():
    esq, sem = {"const": k.ESQUEMA}, {"enum": list(k.SEMANTICAS)}
    base = {"type": "object", "propertyNames": {"enum": list(k.COMPONENTES)}, "additionalProperties": T}
    S = {
        "ranura": {**_obj({"esquema": esq, "tipo": {"enum": list(k.TIPOS_RANURA)},
                           "ambito": {"anyOf": [{"const": ""}, H]}, "nombre": {"type": "string", "minLength": 1},
                           "id": H}),
                   "if": {"properties": {"tipo": {"enum": list(k.CANDIDATAS)}}},
                   "then": {"properties": {"ambito": H}}, "else": {"properties": {"ambito": {"const": ""}}}},
        "revision": _obj({"esquema": esq, "semantica": sem, "ranura": H, "contenido": H, "forma_canonica": T,
                          "fuente": T, "forma_fuente": H, "firma": T, "dependencias": _mapa(H), "id": H}),
        "instantanea": _obj({"esquema": esq, "semantica": sem, "revisiones": _mapa(H), "base": base, "id": H}),
        "afirmacion": {**_obj({"esquema": esq, "semantica": sem, "clase": {"enum": list(k.CLASES)},
                               "sujetos": {"type": "object", "additionalProperties": H},
                               "contexto": {"type": "object"}, "id": H}),
                       "allOf": [{"if": {"properties": {"clase": {"const": c}}},
                                  "then": {"properties": {
                                      "sujetos": {"required": sorted(k.PAPELES[c]),
                                                  "propertyNames": {"enum": sorted(k.PAPELES[c])}},
                                      "contexto": ({"type": "object", "required": ["testigo"],
                                                    "additionalProperties": False,
                                                    "properties": {"testigo": {"type": "object", "additionalProperties": {
                                                        "anyOf": [{"type": "boolean"}, {"type": "integer", "minimum": 0},
                                                                  {"type": "array", "items": {"type": "integer",
                                                                                              "minimum": 0,
                                                                                              "maximum": 255}}]}}}}
                                                   if c == "REFUT" else {"const": k.CONTEXTO_FIJO[c]})}}}
                                 for c in k.CLASES]},
        "certificado": {**_obj({"esquema": esq, "semantica": sem, "afirmacion": H,
                                "estado": {"enum": list(k.ESTADOS_CERTIFICADO)}, "via": {"enum": list(k.VIA_REGLA)},
                                "regla": {"enum": list(k.REGLAS)}, "instantanea": H, "base": base,
                                "cierre": _mapa(H), "objeto_verificado": {"anyOf": [H, {"type": "null"}]},
                                "premisas": {"type": "object", "additionalProperties": H},
                                "procedencia": {"anyOf": [H, {"type": "null"}]}, "id": H}),
                        "allOf": [{"if": {"properties": {"via": {"const": v}}},
                                   "then": {"properties": {"regla": {"enum": list(r)}}}}
                                  for v, r in k.VIA_REGLA.items()] + [
                            {"if": {"properties": {"regla": {"const": "directa"}}},
                             "then": {"properties": {"objeto_verificado": H, "premisas": {"maxProperties": 0},
                                                     "procedencia": {"type": "null"}}},
                             "else": {"properties": {"objeto_verificado": {"type": "null"}, "procedencia": H}}},
                            {"if": {"properties": {"regla": {"const": "conservacion"}}},
                             "then": {"properties": {"premisas": {"maxProperties": 0}}}},
                            {"if": {"properties": {"regla": {"enum": ["R-PROP", "R-REAL", "R-REFUT"]}}},
                             "then": {"properties": {"premisas": {"required": ["origen"]}}}}]},
        "registro": {**_obj({"esquema": esq, "semantica": sem, "afirmacion": H,
                             "resultado": {"enum": list(k.ESTADOS_REGISTRO)}, "via": {"enum": list(k.VIAS_REGISTRO)},
                             "instantanea": H, "origen": {"anyOf": [H, {"type": "null"}]},
                             "mediciones": {"type": "object",
                                            "additionalProperties": {"type": ["string", "integer", "boolean", "null"]}},
                             "id": H}),
                     # v2.6: la vía fija el origen (§4.1), condición local que el esquema puede expresar (§2.3)
                     "if": {"properties": {"via": {"const": "directa"}}},
                     "then": {"properties": {"origen": {"type": "null"}}}, "else": {"properties": {"origen": H}}},
    }
    S["paquete"] = _obj({"esquema": esq, **{t: _mapa({"$ref": f"{n}.schema.json"}) for t, n in k.TABLAS.items()}})
    return {n: {"$schema": "https://json-schema.org/draft/2020-12/schema", "$id": f"{URL}{n}.schema.json",
                "title": n, **s} for n, s in S.items()}


def main():
    d = pathlib.Path(__file__).parent / "esquemas"
    d.mkdir(exist_ok=True)
    for p in d.glob("*.json"):
        p.unlink()
    for n, s in esquemas().items():
        (d / f"{n}.schema.json").write_text(json.dumps(s, ensure_ascii=False, indent=1, sort_keys=True) + "\n")
    print(f"{len(esquemas())} esquemas en {d}")


if __name__ == "__main__":
    main()
