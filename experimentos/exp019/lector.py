"""EXP-019, O3: lector independiente de las salidas de A, B y C (ficha, §Oráculos O3).

Sin `efch`; `python3 -I`. Recalcula desde los JSON brutos (almacén de C, trazas de B) el origen, la regla y el estado
que declara cada adaptador, y los conteos (llamadas efectivas = fallos de caché de B; contador = doble contador).
Una discrepancia es un fallo de calibración.

    python3 -I lector.py --cond A|B|C --celda DIR --out OUT.json [--almacen DIR]
"""

import argparse
import json
import pathlib


def leer(p):
    return json.loads(pathlib.Path(p).read_text(encoding="utf-8"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cond", required=True)
    ap.add_argument("--celda", required=True)
    ap.add_argument("--almacen")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    celda = pathlib.Path(a.celda)
    f1 = leer(celda / "fase1.json")
    disc, sin_evidencia = [], []
    if not f1.get("ok") or "obligaciones" not in f1:
        pathlib.Path(a.out).write_text(json.dumps({"aplicable": False, "discrepancias": []}), encoding="utf-8")
        return
    cont = f1["medida"]["contadores"]
    if cont["prove"] != cont["check"]:
        disc.append({"tipo": "contador", "prove": cont["prove"], "check": cont["check"]})
    if a.cond == "A":
        for o in f1["obligaciones"]:
            if o.get("origen") != "directa":
                disc.append({"tipo": "origen", "obligacion": o["obligacion"]})
    elif a.cond == "B":
        trazas = leer(celda / "trazas-fase1.json")
        fallos = sum(1 for t in trazas if not t["acierto"])
        if fallos != cont["prove"]:
            disc.append({"tipo": "fallos_de_cache_vs_contador", "fallos": fallos, "prove": cont["prove"]})
        if sum(1 for t in trazas if t["acierto"]) != cont["aciertos_B"]:
            disc.append({"tipo": "aciertos"})
        for o in f1["obligaciones"]:
            ts = [t for t in trazas if t["obligacion"] == o["obligacion"]]
            origen = "memo" if ts and all(t["acierto"] for t in ts) else "directa"
            if origen != o["origen"]:
                disc.append({"tipo": "origen", "obligacion": o["obligacion"], "declarado": o["origen"],
                             "recalculado": origen})
            if ts and ts[-1]["estado"] != o["estado"] and o["clase"] == "WD":
                disc.append({"tipo": "estado", "obligacion": o["obligacion"]})
    else:
        alm = pathlib.Path(a.almacen)
        S_d = f1["S_d"]
        for o in f1["obligaciones"]:
            if o.get("certificado"):
                p = alm / "objetos" / "certificados" / f"{o['certificado']}.json"
                if not p.exists():
                    disc.append({"tipo": "certificado_ausente", "obligacion": o["obligacion"]})
                    continue
                c = leer(p)
                origen = ("directa" if c["instantanea"] == S_d else "conservada") if c["regla"] == "directa" \
                    else c["regla"]
                if origen != o["origen"] or c["regla"] != o["regla"] or c["estado"] != o["estado"]:
                    disc.append({"tipo": "origen_regla_estado", "obligacion": o["obligacion"],
                                 "declarado": [o["origen"], o["regla"], o["estado"]],
                                 "recalculado": [origen, c["regla"], c["estado"]]})
            elif o.get("registro"):
                r = leer(alm / "objetos" / "registros" / f"{o['registro']}.json")
                if r["resultado"] != o["estado"]:
                    disc.append({"tipo": "registro_estado", "obligacion": o["obligacion"]})
            else:
                sin_evidencia.append({"obligacion": o["obligacion"], "estado": o["estado"]})
    pathlib.Path(a.out).write_text(json.dumps({"aplicable": True, "discrepancias": disc, "sin_evidencia": sin_evidencia}, indent=1,
                                              ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
