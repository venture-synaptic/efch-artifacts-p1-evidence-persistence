# Semantic Store híbrido: prototipos P0/P1 (informe y cierre)

[Decisión] H2, línea exploratoria posterior a EXP-019; puertas G0 y G5. **No es un experimento numerado ni
confirmatorio**: P0 y P1 se desarrollaron y midieron sobre las 112 entradas **conocidas** de EXP-019 (72 de
evaluación y 40 de preparación), usadas solo como conjunto de desarrollo. Nada de lo que sigue confirma ni refuta H2.

**Procedencia.** Todo el código, las mediciones y la auditoría están en la rama `prototipos/hibrido-p0p1`, que no se
integra en `main`:

| Pieza | Commit | Contenido |
|---|---|---|
| Exploración de Sol | `7bc6068` | `resultados/exploracion-hibrido/sol/`: descomposición, candidatas, comparador justo |
| Prototipos de Opus | `dc39ff95` | `prototipos/hibrido/` y `resultados/prototipos-hibrido/` (`INFORME.md`, `desviaciones.md`, `mediciones.json`, `solidez.json`, `SHA256SUMS`) |
| Auditoría de Sol | `fcd15aae` | `resultados/prototipos-hibrido/auditoria-sol/`, reproducida en [el dictamen](semantic-store-hibrido-P0P1-dictamen-sol.md) |

Implementó Claude Opus, aislado y sin red salvo su API. Auditó Codex Sol, también aislado y con solo lectura sobre
la entrega. Coordinó Claude Opus (coordinador), y decidió el autor.

## 1. Pregunta y diseño

- **[Hipótesis]** Tras EXP-019 (R3 refutada: C = 252 llamadas frente a B = 96), Sol descompuso el sobrecoste de C y
  propuso H: hacer EQ solo cuando su VC esté cubierta por una REAL residual. Con un comparador justo (B con la misma
  normalización afín), B + AF y H + AF empataban en 16 llamadas de la fase 1 sobre los datos conocidos.
- **[Decisión del autor]** Se autorizaron dos prototipos:
  - **P0**, caché reforzada: B con normalización afín (AF) y decidor tipado;
  - **P1**, P0 más **solo** el mecanismo H, con las mismas optimizaciones y recursos.
  Criterios de descarte de P1: compromete R1, la atomicidad o la cobertura; añade verificaciones en un estado
  totalmente en caché; o no muestra una mejora de tiempo reproducible frente a P0.

## 2. Resultados

- **[Resultado] P0.**
  - Normalización: 0 discrepancias y 0 colisiones en unas 6 300 consultas, y Z3 confirma 345/345 en bv16/32/64.
  - Los contraejemplos de Sol (H-dom, anchura, N-div) se reproducen con variantes inseguras y P0 los rechaza.
  - Línea base reproducible en 3 repeticiones: 120 llamadas en la fase 0 y 72 en la fase 1, todas en preparación.
- **[Resultado] P1.**
  - H se activó en 22 entradas, todas de preparación, y bajó la fase 1 de 72 a 44 llamadas.
  - Sin violaciones de reutilización detectadas: 936/936 raíces normativas y, en la auditoría, un evaluador
    independiente sobre 2 016 obligaciones.
  - Cobertura igual a P0 en 112/112, y 0 verificaciones en estado totalmente en caché.
- **[Resultado] Coste** (10 repeticiones emparejadas e intercaladas, 4 480 procesos, *bootstrap* por entrada,
  recalculado por Sol):
  - ΔT(P1 − P0) = **+0,514 s por entrada**, IC95 [0,510; 0,519], positivo en cada una de las 112 entradas;
  - unas 11,6 veces más lento, con más memoria pico (54,6 → 60,6 MiB) y más estado persistido (5 kB → 87 kB);
  - no amortiza: ΔT0 y ΔT1 son ambos positivos.

## 3. Dictamen: P1 descartado, por dos motivos distintos

**Motivo 1, ineficiencia (criterio del autor).** P1 tarda 0,514 s más por entrada, de forma reproducible. Aunque se le
descuente toda la carga y la persistencia, sigue perdiendo 0,485 s. El ahorro máximo optimista, de 3,6 ms por entrada,
no cubre ni el coste del selector, de 9,4 ms. Esto basta para el descarte.

**Motivo 2, defectos de implementación (hallados por Sol, no por Opus).** P1 **no cumplió todas las garantías
declaradas**:

- **Y1, versionado de certificados.** La base de los certificados no incluye el normalizador ni el adaptador. Tras
  cambiar el normalizador, un proceso nuevo reutiliza la WD anterior. Es una falta de versionado causal (G5), no un
  contraejemplo de comportamiento observado.
- **Y2, atomicidad.** Si el guardado de la caché falla **después** de publicar el índice, la fase queda publicada a
  medias: la generación avanza y el estado nuevo es recargable, pero la caché es la antigua. Los controles de Opus
  (X9) solo inyectaban fallos antes del índice. Por tanto, aunque ninguna prueba de reutilización detectó evidencia
  inválida, **la afirmación del informe de Opus de que P1 «cumple la atomicidad» no se sostiene**.
- **Y3, reintentos innecesarios.** Con un presupuesto agotado (`rlimit=1`), P1 vuelve a intentar una VC desconocida:
  4 checks frente a 3 de P0. No transfiere nada falso, pero rompe el presupuesto compartido por VC.

**Otros límites:**
- La equidad no fue estricta. P1 añade instantáneas, validación normativa y publicación, así que no es una ablación pura
  de H. Las asimetrías medidas favorecían a P1.
- No queda acreditado que P0 se construyera antes que P1: P1 se escribió antes de los entregables de la línea base de
  P0, aunque esa línea base se validó después.
- El oráculo O1 no admite `udiv`, de modo que X8 solo tiene el respaldo del intérprete.
- No se ensayaron propiedades (PROP), cambios de interfaz, historiales largos ni otros fallos e intercalaciones: quedan
  `no comprobado`.

**Ventaja diferencial real: ninguna en coste total.** Las 28 llamadas ahorradas no requieren información exclusiva de
EFCH. `Z3.simplify` reduce a `true` las 18 afirmaciones por entrada de las 14 entradas transferidas, así que un
preprocesador convencional compartido absorbería el ahorro.

**[Decisión del autor]** No se corrige P1 solo para conservar un prototipo descartado. Sus defectos y límites quedan
documentados aquí y en la rama. P0 se acepta como **línea base de caché convencional acotada**, no como comparador con
las garantías de v2.7.

## 4. Cierre y consecuencia

- **[Decisión del autor]** Se cierra la arquitectura híbrida P1. No se declara imposible toda reutilización semántica.
- **[Resultado]** Los ahorros observados se pueden obtener con técnicas convencionales. Las garantías de v2.7 (certificados,
  procedencia, publicación atómica) introducen costes que no se amortizaron en este dominio.
- **[Hipótesis]** La línea se replantea: ya no se trata de conseguir menos llamadas a Z3, sino de saber si EFCH puede
  conservar y transformar evidencia formal entre versiones (demostraciones, refutaciones, dependencias, verificación
  incremental) con garantías verificables y un coste total acumulado competitivo. Siempre frente a un comparador con
  **las mismas garantías**, que P0 no ofrece.
- Antes de un nuevo experimento confirmatorio, que no está autorizado, debe haber una hipótesis que prediga una ventaja
  verificable, un comparador, métricas y criterios de refutación.

Siguen abiertos D10 (posicional) y D11. No se alteran v2.7, EXP-019, EXP-018, E-v4, la enmienda 4 ni la reserva.
