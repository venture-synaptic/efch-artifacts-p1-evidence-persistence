# EXP-019 — Resultados de la evaluación (H2)

- **Estado:** evaluación ejecutada el 01/11/2026 con la autorización INF-2026-11-01-12 (Notion 06) y el instrumento
  congelado `exp019-instrumento` = `4aa18a7`. Resultados íntegros en `resultados/exp019/evaluacion/` (JSONL
  `59c354f3…`, análisis `82e684e7…`, árbol `ARBOL-evaluacion.sha256`).
- **Auditoría independiente de Codex Sol:** «resultados válidos en el dominio preinscrito», en
  `resultados/exp019/auditoria-sol-evaluacion/`. Sol recalculó todo desde las celdas sin usar el análisis del
  instrumento y reprodujo una repetición completa.
- La ficha congelada (`docs/experimentos/EXP-019.md`) y la aclaración G2 no cambian. Este documento solo registra los
  resultados.

## Resultados ([Resultado], evidencia experimental, no «probado»)

| | Reverificación completa A | Memoización fortalecida B | EFCH C |
|---|---:|---:|---:|
| Llamadas efectivas, 64 transiciones | 576 | 96 | 252 |
| Llamadas efectivas, 61 limpias | 549 | 86 | 233 |

- **R1, solidez: sostenida** en este dominio.
  - 576 de 576 obligaciones decididas, 64 EQ, 48 REFUT y 8 de 8 controles en C;
  - cero violaciones, cero inconclusas y cero fallos de calibración (precedencia 5);
  - no se conservó ninguna REAL obsoleta: en el cambio no equivalente, las 48 se refutaron;
  - no es una demostración de solidez general.
- **R2, eficiencia frente a A: sostenida.** 252 frente a 576 (ρ_A = 0,4375; un 56,25 % menos), y ninguna REAL idéntica
  se reverifica.
- **R3, valor diferencial frente a B: superioridad refutada, inferioridad.** 252 frente a 96 (ρ = 2,625; +156), fuera
  de la zona de indiferencia práctica.
  - Por estrato:
    - ajena: 0 frente a 56;
    - **equivalente: 32 frente a 40 (ρ = 0,8), única superioridad, localizada**;
    - no equivalente: 128 frente a 40;
    - dependencia: 36 frente a 16.
  - La conclusión es robusta: es la misma con las 61 limpias (ρ = 2,709).
- **Predicción preinscrita** (576/116/252): A y C coinciden; **B no** (96, 20 aciertos más de lo previsto). La causa,
  según Sol, es que el impresor `sexpr()` de Z3 da el mismo texto para AST asociativamente distintos. La derivación
  suponía que igual estructura implicaba igual `sexpr`, pero la inversa no es cierta. No es un defecto del
  instrumento ni un debilitamiento de B, y no cambia ninguna decisión. Se conserva como desviación de la predicción.

## Alcance (lo que no se concluye)

- **Dominio:**
  - núcleo total bv1–4, con tres candidatas relacionadas por construcción;
  - cambios muy pequeños y base constante;
  - efecto techo: WD siempre verdadera.
- **Fuera:**
  - la superioridad general;
  - la persistencia ante cambios reales de base;
  - PROP/D8 y R-REFUT;
  - Lang y C compilado;
  - las herramientas externas.
- **Defectos abiertos:** D10 posicional sigue `no comprobado`. D11 se evitó por construcción y no queda cerrado.
- **H2, conclusión acotada:** en este ensayo, EFCH conserva la evidencia correctamente y cuesta menos que reverificarlo
  todo, pero **no** aporta un valor diferencial global frente a una caché convencional fuerte. Solo gana en los
  cambios equivalentes.

## Dictamen y cierre (decisión del autor, 01/11/2026)

| Hipótesis | Resultado | Decisión |
|---|---|---|
| R1, reutilización segura | Sostenida | Conservar |
| R2, mejor que la reverificación completa | Sostenida | Conservar |
| R3, mejor que la memoización B | Refutada | Investigar otra arquitectura |

- [Decisión] EXP-019 queda **cerrado como experimento auditado**. R3 se mantiene refutada y todos los resultados
  quedan intactos. Lo refutado es la superioridad de la **implementación C evaluada**, no la posibilidad de un
  mecanismo semántico más eficiente.
- [Decisión] Siguiente línea, el **Semantic Store híbrido y adaptativo**:
  - una fase exploratoria de análisis de costes y prototipos mínimos, comparados con B sobre los datos ya conocidos;
    puede descartar propuestas, pero no demuestra nada;
  - después, un experimento **nuevo y preinscrito**, con entradas de evaluación nuevas y ocultas, que mida además el
    tiempo total, la memoria, el tamaño de la evidencia y las garantías;
  - un selector que use etiquetas conocidas del experimento no es aceptable.
- D10 posicional y D11 siguen abiertos.
- **Evidencia** (fuera de `main`):
  - protocolo: etiqueta `exp019-protocolo` (`d94471a`);
  - instrumento: etiqueta `exp019-instrumento` (`4aa18a7`);
  - preinscripción y revisiones: rama `preinscripcion/h2`;
  - instrumento, preparación, evaluación y auditorías: rama `preparacion/exp019` (`resultados/exp019/` y
    `resultados/preparacion-exp019/`).
