# EFCH EXP-019 — research artifacts

Artifacts for the draft manuscript *Safe Reuse Is Not Enough: A Controlled Comparison of Semantic
Evidence Persistence, Full Reverification, and Strengthened Memoization* (`paper/main.tex`).

**Status:** draft, not peer reviewed, not submitted. EFCH is research software (0.1.0a1), not
production-ready. Most project documents are in Spanish; the manuscript is in English.

Author: Erik Fisher Cueva Huari, VentureSynaptic Labs — ORCID
[0000-0001-7268-5510](https://orcid.org/0000-0001-7268-5510).

## Provenance

This repository is an export from the private research repository `venture-synaptic/efch-research`.
Nothing here was modified after export; the project README was renamed to `README-efch-0.1.0a1.md`,
and this README and `SHA256SUMS` were added.

| Content | Source (commit) |
|---|---|
| `efch/`, `especificacion/`, `experimentos/exp019/`, `scripts/vendor_z3.sh`, `docs/experimentos/EXP-019.md`, `README-efch-0.1.0a1.md` | tag `exp019-instrumento` (`4aa18a7450bbf034d67048034e09cae98d970c2f`); protocol frozen at tag `exp019-protocolo` (`d94471afae4c32c8d4572f1d7086327f97d61f65`) |
| `docs/experimentos/EXP-019-resultados.md`, `docs/exploracion/*`, `docs/diseno-identidad-evidencias.md` | `main` at `26315176c3e4d04e9a29612818e8f8b0e762a8bf` |
| `data/exp019-resultados.tar.gz` (raw evaluation, logs, internal audit; `resultados/exp019/`) | branch `preparacion/exp019` at `531c847f239b15c352449428b8b39d1f675257f7` |
| `paper/` | manuscript draft, 1 November 2026 |

The tarball is deterministic (sorted names, fixed mtime, `gzip -n`). Inside it,
`resultados/exp019/ARBOL-evaluacion.sha256` and `evaluacion-huellas.sha256` are the original digests.

## Verify

```bash
sha256sum -c SHA256SUMS
sha256sum -c experimentos/exp019/MANIFIESTO.sha256     # frozen protocol
mkdir -p datos && tar -xzf data/exp019-resultados.tar.gz -C datos
```

## Reproduce (informed reproduction)

Requires Python ≥ 3.10 and `gcc`. Z3 is downloaded with a pinned hash:

```bash
scripts/vendor_z3.sh
sha256sum -c experimentos/exp019/INSTRUMENTO.sha256
python3 experimentos/exp019/ejecutar.py --preparacion
```

The evaluation set is already public here, so a rerun is an *informed reproduction*, not a new
preregistered test (see `docs/experimentos/EXP-019.md`, "Artefactos reproducibles y custodia").

## Known limitations

- Integrity defects D10–D13 and architectural limitation L-D14 remain open
  (`docs/diseno-identidad-evidencias.md`).
- The internal audit was performed by an AI agent (Codex), not by an independent human researcher.
- Logs contain absolute paths of the original machine.

## License

Pending author decision. Until a license is added, no reuse rights are granted.
