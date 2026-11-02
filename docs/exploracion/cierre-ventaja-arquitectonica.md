# Cierre de la línea de ventaja arquitectónica del Semantic Store

**[Decisión del autor, 01/11/2026]** Se cierra la línea de **superioridad arquitectónica** del Semantic Store dentro del
alcance investigado. No se cierra EFCH, ni el paradigma ni el Semantic Store.

## Conclusión registrada (texto del autor)

> No se ha identificado una ventaja arquitectónica diferencial de los mecanismos de persistencia y reutilización de
> evidencia EFCH evaluados frente a comparadores incrementales con garantías y optimizaciones equivalentes. La
> investigación queda cerrada en este alcance, sin afirmar imposibilidad general.

## Base de la decisión

| Evidencia | Resultado | Dónde |
|---|---|---|
| EXP-019 (preinscrito, auditado) | R1 y R2 sostenidas; R3 refutada (C = 252 llamadas frente a B = 96) | `docs/experimentos/EXP-019-resultados.md` |
| P0/P1 (exploratorio) | P1 descartado: +0,514 s por entrada, IC95 [0,510; 0,519], y defectos Y1–Y3; sin ventaja diferencial | `docs/exploracion/semantic-store-hibrido-P0P1.md` y su dictamen |
| Investigación conceptual (Sol y Opus) | Las cinco líneas tienen antecedentes directos; el contrato v2.7 es neutral respecto a la arquitectura | Rama `investigacion/persistencia-evidencia`, `aee012c` y `03a992f` |
| Filtro Q1/Q2 (Sol) | Q1: ninguna candidata acredita garantías equivalentes completas. Q2: ninguna conserva una ventaja diferencial frente a un comparador con las mismas técnicas | Misma rama, `8f0d340` |

## Qué queda vigente

- **EXP-019 y P0/P1** se conservan sin cambios y se incorporan al historial como resultados negativos válidos, sin
  reinterpretarlos.
- **Semantic Store:** se mantiene como infraestructura experimental (0.1.0a1). Sus resultados son evidencia de
  investigación, no una tecnología de superioridad demostrada.
- **Defectos:** D11, D12 y D13 siguen abiertos y L-D14 queda como limitación arquitectónica
  (`docs/diseno-identidad-evidencias.md`). Las correcciones irán fuera de la v2.7 congelada, con pruebas y en una
  versión separada.
- **No autorizado:** nuevos experimentos o prototipos de Semantic Store con los mismos mecanismos para intentar
  superar a B.
- **Reapertura:** solo con una pregunta científica distinta, un mecanismo nuevo y una predicción nueva, frente a un
  comparador con las mismas garantías y técnicas.
- **Sin cambios por este cierre:** no se integra en `main` la rama experimental de Sol ni la de prototipos, y no se
  modifica ninguna etiqueta congelada.
