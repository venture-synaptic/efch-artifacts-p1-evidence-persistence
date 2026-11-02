"""EXP-019: comprobación solo sintáctica de las entradas (lector y elaborador del núcleo; sin solucionador,
sin `store`, sin intérprete). Falla si algún módulo de Z3 llega a cargarse.

    python3 experimentos/exp019/comprobar_sintaxis.py
"""

import pathlib
import sys

RAIZ = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(RAIZ.parent.parent))
from efch import core  # noqa: E402

n = 0
for fase in ("evaluacion", "preparacion"):
    for d in sorted(p for p in (RAIZ / fase).iterdir() if p.is_dir()):
        for nombre in ("antes.efch", "despues.efch"):
            defn = core.load_definition((d / nombre).read_text(), str(d / nombre))
            assert sorted(defn.computations) == ["f", "h", "q"], d
            cands = core.load_candidates((d / "candidatas.efch").read_text(), defn)
            assert [c.name for c in cands] == ["c0", "c1", "c2"], d
        n += 1
assert not any(m == "z3" or m.startswith("z3.") for m in sys.modules), "se cargó Z3"
print(f"sintaxis correcta: {n} entradas (antes y después, con sus candidatas); Z3 no cargado")
