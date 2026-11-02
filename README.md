# EFCH EXP-019 — research artifacts

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.23873679.svg)](https://doi.org/10.5281/zenodo.23873679)

Archived at Zenodo: version `v1.0-exp019`, DOI [10.5281/zenodo.23873679](https://doi.org/10.5281/zenodo.23873679);
all versions: [10.5281/zenodo.23873678](https://doi.org/10.5281/zenodo.23873678). See `CITATION.cff`.

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
| `paper/` | manuscript draft and PDF (updated in v1.1-exp019) |

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

## Contributors

The experiment, instrument and reports were produced by AI agents under the author's direction:
Claude (Anthropic) implemented the instrument and prototypes and coordinated the work; Codex
(OpenAI, "Sol") performed the internal audit of the EXP-019 evaluation (recomputation and a complete
repeated execution, `resultados/exp019/auditoria-sol-evaluacion/` in the data archive), the review of
the P0/P1 follow-up (`docs/exploracion/semantic-store-hibrido-P0P1-dictamen-sol.md`) and the
literature verification used in the manuscript. The author is responsible for the decisions and
interpretation.

## Known limitations

- Integrity defects D10–D13 and architectural limitation L-D14 remain open
  (`docs/diseno-identidad-evidencias.md`).
- The internal audit was performed by an AI agent (Codex), not by an independent human researcher.
- Logs contain absolute paths of the original machine.

## Related artifacts

Other VentureSynaptic Labs artifact packages for EFCH (one repository and DOI per manuscript):

- [efch-artifacts-lang](https://github.com/venture-synaptic/efch-artifacts-lang): EFCH Lang experiments (EXP-004 to EXP-015) and their manuscript.

## License

- **Code** (`efch/`, `especificacion/*.py`, `experimentos/`, `scripts/`): [Apache-2.0](LICENSE).
- **Data, manuscript and documents** (`data/`, `docs/`, `paper/`, `especificacion/ESPECIFICACION.md`,
  `especificacion/resultados/`, README files): [CC-BY-4.0](LICENSE-CC-BY-4.0).

Copyright 2026 Erik Fisher Cueva Huari (VentureSynaptic Labs). See [NOTICE](NOTICE).
