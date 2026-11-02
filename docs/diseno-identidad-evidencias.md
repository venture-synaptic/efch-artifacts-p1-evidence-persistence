# Diseño: identidad, dependencias y transferencia de evidencias (E-v4 / B1-v2)

Estado: **borrador v2.1** (26/10/2026). Incorpora la revisión del diseño v1 de Codex Sol
(`resultados/codex/sol-revision-diseno/`; la v1 está en `diseno-revisado-v1.md`), que no aprobó la v1, y la de la
v2 (`resultados/codex/sol-revision-diseno-v2/`): cierra la mayoría de los hallazgos; quedan los supuestos, la
cobertura y la paridad, resueltos en la v2.1 (§2.3, §5.6, §7 y §9).
Hipótesis H2; puertas G0 y G5 (§25). No acredita G3.

Decisión del autor del 26/10/2026: E-v4 es una revisión arquitectónica, no otro parche. Siguiendo la revisión, **las
reglas de inferencia (§5) se escriben ahora, antes de implementar**, en lugar de esperar a la regla de parada.

## 1. Diagnóstico

Todos los defectos encontrados comparten una causa: una evidencia, un objeto o una dependencia se identifica por
**texto** (nombre, prefijo o expresión regular), o por una forma **incompleta** de su contenido, en vez de por un
valor tipado y completo.

| # | Defecto | Dónde | Origen |
|---|---|---|---|
| D1 | EQ demostrada sobre una definición distinta de la transferida | E | Sol v1 |
| D2 | WD(f_a) aceptada con huellas incompletas | E | Sol v1 |
| D3 | WD de una candidata tomada como la de una computación homónima | E | Sol v2 |
| D4 | Cadena de justificaciones perdida al pasar por la caché | E | Sol v2 |
| D5 | Confusión homónima inversa: WD(c) usada como WD(f_a) | E | Sol v3 |
| D6 | Se admite una afirmación anterior obsoleta y ninguna prueba lo detecta | E (pruebas) | Sol v3 |
| D7 | Cierre de `call` buscado con `\b`: omite `f-` | `comun.py` (B1, E, E⁻), `reevaluar.py`; `pipeline.py:60` (solo presupuesto) | Sol v3 |
| D8 | `store.evolve f` no reverifica las propiedades que dependen de `f` a través de otra computación | `efch/store.py:117` | Auditoría del 26/10; confirmado por Sol |
| D9 | `store` recarga una candidata con la definición **nueva** (`call h` se expande distinto), verifica ese cuerpo y anota `probado` para la realización registrada, cuyo cuerpo se refuta | `efch/store.py:85`, `:160` | Sol, diseño |
| D10 | Clasificaciones por texto en la evidencia; WD(c) reconocida por una frase | `evidencia.py:67`, `:110`; `reevaluar.py:374` | Sol, diseño |
| D11 | **Abierto (riesgo conocido, 01/11/2026).** `store.realize` con una dependencia sin revisión vigente (f sin vigencia, g → f vigente) termina con `IdentidadDistinta` engañosa y deja la memoria modificada (no el disco) | `efch/store.py`, `realize` | Opus y Sol, ronda `register` |
| D12 | **Abierto (escalabilidad, 01/11/2026).** `Store.vigente` recorre todos los certificados retenidos y, para los que coinciden en afirmación, crea un `Validador` nuevo sin memoria entre llamadas: el coste de una consulta crece con el historial | `efch/store.py:504–512`, `efch/reglas.py:445–453` | Opus (viabilidad), modelo de Sol (filtro Q1/Q2) |
| D13 | **Abierto (integridad y persistencia, 01/11/2026).** `Store.guardar` escribe los objetos y después los cuatro índices uno a uno con `write_text`, sin archivo temporal, renombrado atómico, `fsync` ni transacción: un fallo a mitad deja índices incoherentes entre sí o truncados | `efch/store.py:341–352` | Opus (viabilidad); confirmado por el coordinador y por Sol |

D8 y D9 son defectos del registro semántico, no solo de EXP-018 (`resultados/auditoria-identidad/`,
`resultados/codex/sol-revision-diseno/reproducir.sh`).

**D11 (abierto).** Decisión del autor (01/11/2026): se documenta como riesgo conocido y no se abre todavía otra ronda de
corrección.
- **Reproductor:** `resultados/correccion-store-register/auditoria-sol/casos.py` (resultados en `*/casos-resumen.json`)
  y `resultados/correccion-store-register/dudas.md`, §5. Se reproduce con `efch` en `579644d` y en `5d5047f`.
- **Alcance:** solo un almacén en el que una dependencia ha perdido su revisión vigente (no se ha producido por la
  API normal). El disco y la recarga quedan intactos; la memoria del objeto `Store` queda modificada.
- **Impacto:** el diagnóstico atribuye mal la causa, y un `Store` reutilizado tras el error no equivale al almacén en
  disco.
- **Hasta corregirlo:**
  - no se usa ese escenario para producir evidencia de éxito de H2;
  - no se supone que un error deja intacto el `Store` en memoria;
  - los ensayos se hacen en almacenes aislados y descartables;
  - se detiene la ejecución si aparece una modificación parcial inesperada.
- No es una garantía de integridad ni autoriza a presentar el almacén como componente estable.

**D12 y D13 (abiertos) y limitación L-D14.** Decisión del autor (01/11/2026): se registran **sin alterar el código
congelado**. Sus correcciones necesitarán pruebas y una versión separada, fuera de la v2.7.
- **D12, modelo de coste** (Sol, `resultados/investigacion-persistencia/sol-filtro-q1q2/d12-modelo.md` en la rama
  `investigacion/persistencia-evidencia`):
  - Una consulta cuesta `Θ(N) + Σ_{c∈M} V(c,S)`, donde N son los certificados retenidos, M los que coinciden en
    afirmación y V el coste de construir el paquete y validar su derivación y vigencia. V depende del DAG, de los bytes
    y de los cierres, no solo de la profundidad.
  - El coste **acumulado** depende del crecimiento del historial:
    - Θ(h²) con N = Θ(i) y las consultas, las coincidencias y V acotadas;
    - Θ(h³) si crecen las coincidencias o las consultas por revisión;
    - Θ(h) o Θ(h log h) si N no crece o crece de forma espaciada.
    La afirmación «coste cuadrático» no es incondicional.
  - Un índice por afirmación elimina el escaneo, pero no garantiza O(h) sin supuestos adicionales.
- **D13, afecta a una propiedad esencial del almacén, con independencia del rendimiento.**
  - Es análogo a Y2 de P1, pero en el `store` de EFCH.
  - Hasta corregirlo, la publicación del almacén no es atómica ni duradera, y ningún resultado se apoya en la
    atomicidad del `store`.
  - EXP-019 vigilaba la publicación parcial con su monitor (§M7) y no registró incidentes, pero eso no acredita la
    garantía.
- **L-D14, limitación arquitectónica, no defecto.** Las hojas directas de los certificados son atestaciones del
  productor, no pruebas lógicas portables que un tercero pueda comprobar sin confiar en él ni rehacer la verificación.
  - Sol comprobó que el contrato v2.7 **no exige** esa garantía: §6 y §12 declaran las hojas y la elaboración como base
    de confianza, y §3.3 y §11.4 asignan la completitud causal al productor (`d14-caracterizacion.md`).
  - Sí se pueden comprobar la estructura, la derivación y la vigencia, y algunos testigos REFUT pueden reevaluarse.
  - Una garantía más fuerte, con un consumidor independiente, sería una ampliación futura del contrato, no una
    corrección de la v2.7.

## 2. Modelo

### 2.1 Instantánea

`Instantánea S = (definiciones elaboradas, base B)`. Es inmutable y tiene un hash. `B` versiona **todas** las piezas
de las que depende un veredicto: z3, efch (por módulo), traductor, backend, cbmc, gcc, cpu y, además, el
canonizador, el elaborador y el cálculo de cierres, el ejecutor (trabajador y recetas) y las reglas de
transferencia. Si cambia una regla, cambia `B`.

### 2.2 Objeto

- **Ranura** `(tipo, ámbito, nombre)`. Es el *dónde* y persiste entre versiones. `tipo` ∈ {`computacion`,
  `propiedad`, `candidata`, `candidata-lang`}.
- **Revisión** `(ranura, contenido)`. `contenido` es el sha256 de la forma canónica **cerrada y completa**:
  versión del lenguaje, firma o ligaduras **con sus tipos**, y cuerpo elaborado con las llamadas expandidas.
  - computación: `Computation.canonical()` (ya incluye la firma);
  - candidata: `Candidate.canonical(comp)`, sobre **el cuerpo realmente verificado**;
  - propiedad: **nuevo** `(efch V (property ((x T)…)) canonical(body, variables))`. Corrige el caso `modelo_dominio`
    de Sol (`∀b:bytes[0]` frente a `∀b:bytes[1]`).
- **Forma fuente** de una revisión: la misma forma canónica, pero con las llamadas sin expandir y cada llamada
  sustituida por su ranura. Sirve para distinguir los cambios **fuente** de los **derivados** (§5.2).

Dos revisiones de una ranura nunca se identifican entre sí; solo las relaciona una evidencia EQ.

### 2.3 Afirmación

`Afirmación = (clase, sujetos por papel, contexto)`. Su identificador es el hash de la tupla canónica. **Nunca se
analiza**: los campos se leen.

**[Decisión] v2.1: contexto fijo.** El contexto de cada clase es exactamente el de la tabla: no hay hipótesis
adicionales. Los únicos supuestos declarados son **L-OBS**, que es fijo y forma parte de la base. Una afirmación con
otro supuesto queda fuera de E-v4 y **no se transfiere**. Así se descarta el contraejemplo `context_drop` de Sol
(una PROP probada bajo `x = 0` transferida sin esa hipótesis). Si más adelante se admiten hipótesis, la regla tendrá
que exigir que el contexto de destino implique el de origen y conservar las hipótesis que no se descarguen.

| Clase | Sujetos | Contexto |
|---|---|---|
| `WD` | `objeto`: revisión | versión del lenguaje |
| `EQ` | `nueva`, `anterior`: revisiones de la misma ranura y misma firma | dirección `d→a`; dominio `definida(nueva)` |
| `PROP` | `propiedad`: revisión | supuestos declarados (L-OBS) |
| `REAL` | `candidata`, `computacion`: revisiones | — |
| `REFUT` | `candidata`, `computacion`: revisiones; `testigo` | — |

### 2.4 Evidencia (certificado)

`Evidencia = (afirmación, estado, vía, instantánea, base de la clase, cierre, objeto verificado, premisas,
procedencia, regla)`

- **Identificador = hash del certificado completo**, con estado, vía y procedencia (corrige `modelo_evidencia`). El
  coste y los tiempos se registran **aparte**, fuera del hash. Al cargar una evidencia se recalcula su hash; si no
  coincide, se descarta.
- `objeto verificado`: la forma canónica que recibió el verificador. Tiene que coincidir con la revisión de la
  afirmación (corrige D9).
- `premisas`: identificadores de evidencias. Forman un **DAG** cuyas hojas son evidencias `directa`.
- `regla`: la regla de §5 que la justifica (`directa`, `conservacion`, `R-PROP`, `R-REAL`, `R-REFUT`).
- La caché se indexa por (afirmación, cierre, base de la clase) y devuelve el certificado entero, procedencia
  incluida (D4).

## 3. Dependencias

- **[Decisión]** El elaborador (`core.Elaborator`, al resolver un `call`, `core.py:510`) registra las dependencias
  directas resueltas de **todo** objeto elaborado: computaciones, propiedades, candidatas del núcleo y núcleo
  traducido desde EFCH Lang, incluidas las llamadas que aparecen en los argumentos. Cada objeto tiene su propio
  colector y conserva su contexto de resolución.
- **[Decisión]** Una sola función, `cierre(S, ranura)`, calcula el cierre transitivo. La usan B1, E, `store` y
  `pipeline`. Ningún módulo analiza texto.
- **Oráculo independiente de dependencias** (para las pruebas): lo implementa otra persona y tiene su propia
  representación y su propio comparador; no reutiliza ni el colector ni el canonizador de producción. Por ejemplo,
  sustituye una ranura por un símbolo opaco y comprueba por enumeración con el intérprete que el resultado cambia
  solo si la ranura está en el cierre.
- **Identidades históricas.** El colector no altera `canonical()`, así que las identidades de computaciones y
  candidatas no cambian (se comprueba recalculándolas para todo el corpus). Las de las propiedades **sí cambian**:
  dejan de ser el hash de su fuente. Por eso el esquema de evidencias y de la caché pasa a la **versión 2**. Las
  evidencias v1 no se traducen: se conservan intactas y, si hacen falta, se reverifican.

## 4. Responsabilidades de los módulos

| Módulo | Hace | No hace |
|---|---|---|
| `efch/core.py` | Elaborar y registrar dependencias resueltas | Nada de evidencias |
| `efch/identidad.py` (nuevo) | Tipos de §2, forma canónica, `cierre`, hash y validación de certificados. Puro: sin E/S y sin solucionador | Decidir transferencias |
| `efch/reglas.py` (nuevo) | Las reglas de §5 como funciones puras de (afirmación objetivo, certificados premisa) a certificado o rechazo con motivo | Verificar nada |
| `experimentos/exp018/comun.py` (B1) | Grafo de afirmaciones; conservación según §5.1 | Claves de texto |
| `efch/reevaluar.py` (E) | Elegir qué transferir y obtener las premisas; producir certificados **solo** a través de `reglas` | Inventar premisas, buscar por nombre |
| `efch/store.py` | Dependencias inversas desde `cierre`; no recargar con otra definición sin comprobar la identidad (D8, D9) | Buscar `(call n` en texto |
| `efch/evidencia.py`, `contador.py`, `arnes.py` | Clasificar por los campos `clase`, `vía` y `regla` | Clasificar por prefijos o frases (D10) |
| Comprobador independiente (pruebas) | Revalidar cada DAG de certificados contra §5 con su propia implementación | Compartir código con `reglas` |

**[Decisión]** `identidad.py` y `reglas.py` son de la referencia: los implementa el implementador de B1, y para el
de E son de solo lectura. **Limitación declarada (Sol, punto 6):** E y B1 comparten el canonizador y el cierre, así
que un error en ellos lo cometerían los dos. Por eso la corrección no se juzga comparando E con B1, sino con
oráculos que no comparten esa base (§6).

## 5. Reglas de inferencia

Notación: `S_a` es la instantánea anterior y `S_d` la nueva. `x_a` y `x_d` son las revisiones de la ranura `x` en
cada una. `C` es el conjunto de ranuras cuya revisión cambia entre `cierre_a(A)` y `cierre_d(A)`. «Vigente en `S`»
significa que el estado es el exigido, la base de la clase coincide con la de `S`, el cierre coincide con el que
`cierre(S, ·)` recalcula y el hash del certificado es válido.

**Premisas comunes a toda transferencia:**
- **P0.** Están **todas** las premisas que exige la regla, cada una con su clase, papel y revisión exactos (I1, I2).
  Si falta alguna, la transferencia se rechaza; no basta con que las presentes sean válidas.
- **P1.** La evidencia de partida es `directa` o cumple recursivamente §5 (DAG con hojas directas), y es vigente en
  `S_a` (I5).
- **P2.** Se cumplen las condiciones de la regla y la base de la clase de la conclusión es igual en `S_a` y en
  `S_d` (I7).

### 5.1 Conservación (B1, E y E⁻)

Una evidencia de `A` en `S_a` se conserva en `S_d` si y solo si la revisión de cada sujeto, el cierre y la base de
la clase son idénticos. **Correcta solo si la identidad es completa** (§2.2), y eso es justo lo que comprueban los
oráculos de §6.

### 5.2 Cambios fuente y derivados

`s ∈ C` es un **cambio fuente** si su forma fuente cambia, y un **cambio derivado** si su forma fuente es igual y
solo cambia lo que expande. **[Decisión] v4:** cada ranura de `C`, sea fuente o derivada, necesita su propia EQ
directa. No hay regla de congruencia. Así se evita rechazar casos como `modelo_i4` sin introducir una regla nueva.
La congruencia queda como mejora futura, con su propia demostración.

### 5.3 R-PROP

Para pasar de `PROP(p_a)` a `PROP(p_d)` hace falta:
1. `PROP(p_a)` `probado`, vigente en `S_a`;
2. la forma fuente de `p` sin cambios (mismas ligaduras, tipos y plantilla);
3. para cada `s ∈ C`: `EQ(s_d → s_a)` `probado`, directa en `S_d`; `WD(s_a)` vigente en `S_a`; `WD(s_d)` directa
   en `S_d`;
4. L-OBS declarado como supuesto en la conclusión.

Justificación: con `WD(s_d)` y la EQ, `s_d(x) = s_a(x)` para todo `x`. Por L-OBS, `p_d` y `p_a` son
equivalentes punto a punto.

### 5.4 R-REAL

Para pasar de `REAL(c, f_a)` a `REAL(c, f_d)` hace falta:
1. `REAL(c, f_a)` `probado`, vigente;
2. **la misma revisión de `c`** en las dos instantáneas (incluye lo que `c` expande: si `c` llama a `h` y `h`
   cambió, se rechaza; D9);
3. `C = {f}`;
4. `WD(f_a)` vigente; `EQ(f_d → f_a)` directa; `WD(c)` de clase WD sobre la revisión de `c`.

### 5.5 R-REFUT

`REFUT(c, f_d, w)` vale si `c` es la misma revisión y el intérprete, sobre `S_d`, da `f_d(w)` definida, `c(w)`
definida y salidas distintas (observación de L-OBS). Exigir además la EQ es una condición del contador congelado,
no una necesidad lógica.

### 5.6 Exclusiones

Nunca se **transfieren por EQ**: WD, invariantes de pliegues, CBMC ni el binario (traducción a C y rendimiento).
Sí se pueden **conservar** según §5.1, cuando no cambia la revisión del sujeto, ni el cierre, ni la base de su
clase.

**Base por clase** (§2.1):

| Clase | Base |
|---|---|
| WD, EQ, PROP, REAL y REFUT del núcleo | {z3, módulos de efch del núcleo, canonizador y cierre, reglas}, más L-OBS para PROP |
| Candidata EFCH Lang | La anterior, más el traductor con sus opciones efectivas (si cambian el núcleo traducido, cambia la revisión) |
| CBMC, traducción a C, rendimiento | Además, backend, cbmc, gcc con sus opciones efectivas, ABI, cpu y `workload` |

El presupuesto y el `workload` no forman parte de la identidad: no cambian la verdad de una afirmación del núcleo.
Pero un `desconocido` conservado no predice una ejecución con otro presupuesto, así que solo se conservan `probado` y
`refutado`.

### 5.7 Invariantes que se comprueban

| # | Invariante | Cómo se comprueba |
|---|---|---|
| I1 | Separación de clases y papeles en las premisas | A, comprobador |
| I2 | Revisión exacta de cada premisa y objeto verificado igual a la revisión afirmada | A, comprobador |
| I3 | Cierre completo, contrastado con el **oráculo independiente** (no con la misma función) | A |
| I4 | `C` cubierto por EQ directas (§5.2) | A, comprobador |
| I5 | Vigencia en la instantánea correspondiente (la anterior para el origen, la nueva para lo directo nuevo) | A |
| I6 | Procedencia inmutable; DAG con hojas directas; hash válido | A, comprobador |
| I7 | Base de la clase igual en las dos instantáneas | A |
| I8 | Ninguna conclusión `probado` tiene una premisa que no sea `probado` (o `refutado` con testigo, en R-REFUT) | A, comprobador |
| I9 | Lo transferido o conservado no se contradice con la verificación directa ni con la enumeración | B |
| I10 | Paridad: lo que E no transfiere coincide con B1 (recetas, orden, caché); toda diferencia permitida queda contada | A, B |

## 6. Pruebas

**Oráculos independientes de la base compartida:**
- (a) verificación directa sin caché ni `identidad` (Z3 más intérprete);
- (b) **enumeración exhaustiva con el intérprete** en dominios pequeños (bv de 1 a 4 bits, bytes de longitud ≤ 2);
- (c) el oráculo de dependencias de §3;
- (d) el comprobador independiente de derivaciones.

Cada oráculo documenta **sus propias limitaciones**. La enumeración solo es viable en dominios pequeños. La
verificación directa comparte Z3 y la semántica de `smt`. El comprobador valida la estructura, no las hojas. Que
el código esté escrito por otra persona no basta: ningún oráculo puede reutilizar las reglas de `reglas.py` ni
asumir sus premisas.

**Cobertura adversarial** (decisión del autor). Las cuotas por casilla de §7 no la sustituyen: mil transferencias
correctas de un mismo patrón no compensan una regla a la que le falta una premisa. Para cada regla y cada premisa
de §5 hay al menos un escenario **construido** en el que esa premisa falla y todas las demás se cumplen, y la
transferencia tiene que rechazarse.

**Nivel A (estructural).** Un generador con semilla produce escenarios que fuerzan:
- nombres con signos y homónimos entre clases;
- cambios de dominio, de firma, de tipos de ligadura, de supuestos y de versión del lenguaje;
- cambios solo de la propiedad;
- cambios derivados (`f→g→p`);
- candidatas con llamadas y recarga en `store`;
- ciclos de caché y de justificación;
- premisas obsoletas, indeterminadas o de otra base.

**Nivel B (diferencial).** Cada transferencia o conservación se contrasta con (a) y, si el dominio es pequeño, con
(b). Cada caso se clasifica como `coincide`, `discrepancia` (defecto, confirmado por el intérprete) o `inconcluso`
(`desconocido` o *timeout*; no cuenta como coincidencia).

**Requisitos:**
- semillas registradas;
- límites de CPU, memoria y **tiempo de pared** (M10);
- el reductor conserva a la vez la aceptación, la vía y la discrepancia confirmada;
- los casos encontrados se guardan para siempre en `tests/regresiones-identidad/`;
- no se filtran los casos que E resuelve; el generador y los oráculos los escribe alguien distinto de los
  implementadores de E y de B1.

**Mutaciones.** Las nueve de las revisiones de Sol y una por regla y por invariante. Una mutación solo cuenta como
detectada si el original pasa y el mutante falla **por el motivo esperado**.

Las pruebas aleatorias son evidencia experimental, no una demostración (§6).

## 7. Criterios de aceptación de E-v4

1. Pasan las regresiones históricas de E-v1, v2 y v3 y los reproductores de Sol (v1, v2, v3 y diseño:
   `modelo_dominio`, `modelo_evidencia`, `modelo_i4`, `store_transitiva`, `store_recarga`).
2. **Cobertura mínima**, para que el criterio no se cumpla vacíamente. Son cuotas operativas, no garantías
   estadísticas.
   - N ≥ 2000 escenarios **distintos**.
   - Una matriz regla × vía × familia de escenario, que se fija antes de ejecutar y solo tiene celdas aplicables
     (no hay R-PROP directa). Cada celda tiene ≥ 100 aceptaciones y casos rechazados decididos.
   - Controles positivos: cada control incorrecto y cada mutante producen la discrepancia o el fallo esperado.
   - Inconclusos ≤ 5 % por celda, sobre las comprobaciones intentadas. No se sustituyen familias difíciles por casos
     fáciles para cumplir el umbral.
   - Se publican, por caso: rechazos con su motivo, profundidad del DAG, entradas, fórmulas, contextos,
     derivaciones y veredictos, además de las semillas y las huellas.
3. 0 discrepancias en E y en B1 frente a (a), (b) y (d).
4. Todas las mutaciones detectadas, según la definición de §6.
5. Pasa la suite completa y `efch check` de los ejemplos no empeora. Las identidades de computaciones y candidatas
   del corpus no cambian; las de las propiedades cambian según §3, con el esquema v2.
6. Se congelan, con sus huellas: `core`, `identidad`, `reglas`, B1-v2, E-v4, **E⁻ y los tres controles**
   (migrados a la misma representación), el trabajador y las recetas, los
   verificadores, el generador, los oráculos, el contador, el exportador, el corpus, las semillas y los
   presupuestos. Después, cuarta auditoría sobre los artefactos congelados, atacando las reglas y las invariantes.

**Regla de parada [Decisión del autor].** Si la cuarta auditoría encuentra otro defecto de esta familia, se
detienen las correcciones y se mecanizan las reglas de §5 (comprobador formal) antes de seguir.

## 8. Consecuencias

- **EXP-018 (P2).** Hace falta la enmienda 4 (B1-v1 → B1-v2, con identidad tipada y esquema v2). B1-v1 se conserva.
  La corrección estructural no cambió ninguna cifra pública, pero eso no habla de la reserva, que sigue cerrada.
  Antes de abrirla, el autor decide si el protocolo admite el cambio de referencia como enmienda anterior a los
  resultados.
- **Registro semántico (D8, D9).** Se corrigen en el paso 1. Hay que auditar EXP-002, que usa `store.evolve` y
  `realize`: si algún escenario tenía dependencias transitivas o candidatas con llamadas, sus filas quedan en
  revisión. Las mediciones se conservan.
- **B-02 (P3).** Primero, la distribución prospectiva de costes con datos de desarrollo; el planificador, solo si
  el margen lo justifica.

## 9. Plan

| Paso | Quién | Resultado |
|---|---|---|
| 0 | Codex Sol | v1 no aprobada; v2 casi cerrada; v2.1 incorpora lo que faltaba |
| 1 | Implementador de la referencia (sesión aislada) | Colector en `core`; `identidad`, `reglas`; B1-v2 migrado; D8, D9 y D10 |
| 2 | Implementador de E (sesión aislada; `identidad` y `reglas` de solo lectura) | E-v4, E⁻ y controles. Todo el coste (cierres, certificados, EQ de derivados) se carga a la condición que lo usa |
| 3 | Sonnet o Codex Astra (independiente de los dos) | Generador, oráculos (b), (c) y (d), reductor y mutaciones |
| 4 | — | Congelado (§7.6) |
| 5 | Codex Sol | Cuarta auditoría |
| 6 | Autor | Enmienda 4, validez de EXP-018 y auditoría de EXP-002 |

Los pasos 1 y 3 pueden hacerse en paralelo. El 2 empieza cuando estén congelados `identidad`, `reglas` **y los
oráculos del paso 3**, como exige EXP-018 («Oráculo»: los oráculos se fijan con huella antes de implementar E).

**[Decisión del autor, 26/10/2026] D8: semántica de `store.evolve`.** Hay que distinguir dos cosas:

- **La definición registrada.** Evolucionar `f` no crea una revisión nueva de `g`, que llama a `f`. La revisión
  registrada de `g` sigue intacta.
- **La vigencia de las evidencias.** Una evidencia es verdad para *su* revisión, y eso no cambia. Pero en la
  instantánea nueva la ranura `g` tiene otra revisión, así que sus evidencias ya no son las de la ranura actual.

Al evolucionar `f`, el registro recorre el **cierre inverso** de dependencias. Toda afirmación cuyo cierre contenga
`f` deja de presentarse como `probado` vigente: queda **obsoleta** en la instantánea nueva, y su afirmación nueva
queda en `no comprobado` hasta que se revalide. Esto incluye las WD, las propiedades, las realizaciones y las
refutaciones de las ranuras afectadas: `f`, `g`, los dependientes de ambas y las candidatas que llaman a alguna de
ellas. La revalidación puede ser directa o por §5. Conservar la definición no es conservar la validez de sus
evidencias.

**[Decisión del autor] Evidencias v2.** La incompatibilidad es explícita:
- las evidencias v1 se quedan intactas;
- no hay conversión v1 → v2, ni silenciosa ni automática;
- una evidencia histórica que haga falta se vuelve a verificar con las reglas v2.

Toda afirmación y todo certificado llevan `esquema` (formato de evidencia) y `semantica` (versión de la semántica
del lenguaje). Así, dos afirmaciones formalmente distintas no pueden colisionar aunque el lenguaje cambie (Anexo A).

**[Decisión del autor] Auditoría de EXP-002.** Busca, como mínimo:
- dependencias transitivas;
- candidatas que llaman a computaciones;
- evidencias cuya validez dependa de cómo se resuelven los nombres.

Clasifica cada escenario como `no afectado`, `afectado` o `indeterminado`, con evidencia reproducible. Los resultados
históricos no se modifican. Las conclusiones afectadas quedan suspendidas hasta terminar la auditoría y, si hay
escenarios afectados, se declaran y se evalúan sus consecuencias.

**[Decisión del autor] Enmienda 4: pendiente, no admitida por defecto.** B1-v2 corrige un defecto de corrección y
cambia la representación compartida, así que no es una optimización. Antes de decidir hay que entregar:
- las diferencias verificables entre B1-v1 y B1-v2;
- su impacto sobre los escenarios públicos y sus oráculos;
- la justificación de que son correcciones de validez y no ajustes que favorezcan a E;
- una evaluación independiente de su compatibilidad con el protocolo congelado.

Si cambian sustancialmente las condiciones, EXP-018 se trata como **piloto** y se diseña un confirmatorio nuevo. La
reserva sigue cerrada. La línea B (rendimiento) sigue aparte.

**[Decisión del autor] Requisitos para empezar E-v4** (además de §7, que es para aceptarla):
1. las identidades distinguen objeto, afirmación y certificado;
2. el cierre de dependencias es completo, contrastado con el oráculo (c);
3. D8, D9 y D10 tienen reproductor y regresión permanente;
4. B1-v2 supera una auditoría de corrección;
5. los oráculos detectan mutaciones semánticas deliberadas;
6. la matriz de cobertura está congelada y no se puede aprobar sin transferencias.

**[Decisión del autor, 27/10/2026] Punto de control antes de E-v4.** No basta con que pasen las dos suites. La
referencia, `reglas` y los oráculos independientes tienen que **coincidir en los casos válidos y detectar los
inválidos construidos a propósito**. Además:

1. **Antes de congelar la batería**, los oráculos detectan mutaciones deliberadas de cuatro tipos: identidad,
   dependencias transitivas, hipótesis y procedencia.
2. **Caso de control D8.** `f` evoluciona, `g` llama a `f` y `PROP(p)`, con `p` sobre `g`, estaba `probado`. El
   sistema tiene que distinguir, y mostrarlo en los certificados, cuatro cosas:
   - la definición registrada de `g`, que no cambia;
   - su cierre semántico efectivo, que cambia (`f_d` en lugar de `f_a`);
   - la evidencia histórica de `p`, que se conserva intacta;
   - la vigencia de esa evidencia, que no se reutiliza sin revalidación, ya sea directa o por R-PROP con EQ de `f`
     y de `g`.

   Se comprueba en `store`, en B1-v2 y en los oráculos (c) y (d).

## Anexo A. Formato de intercambio v2 (contrato entre la referencia, E y los oráculos)

Lo implementa `identidad.py`. Los oráculos del paso 3 lo leen con **su propio** analizador; no importan
`identidad`. JSON canónico: claves ordenadas, UTF-8, sin espacios (`separators=(",", ":")`). Los hashes son
sha256 en hexadecimal completo.

```json
{"esquema": "efch-evidencia/2", "semantica": "efch-0.1",
 "revision": {"ranura": {"tipo": "computacion|propiedad|candidata|candidata-lang",
                         "ambito": "<hash de la ranura que implementa | \"\">", "nombre": "f-"},
              "contenido": "<sha256 de la forma canónica cerrada>",
              "forma_fuente": "<sha256 de la forma fuente (§2.2)>"},
 "afirmacion": {"clase": "WD|EQ|PROP|REAL|REFUT",
                "sujetos": {"objeto|nueva|anterior|propiedad|candidata|computacion": "<revision>"},
                "contexto": {"direccion": "d->a", "supuestos": ["L-OBS"], "testigo": {}},
                "id": "<sha256 de la afirmación sin el campo id>"},
 "certificado": {"afirmacion": "<id>", "estado": "probado|refutado|desconocido|no comprobado|fuera de alcance",
                 "via": "directa|conservada|cache|transferida",
                 "regla": "directa|conservacion|R-PROP|R-REAL|R-REFUT",
                 "instantanea": "<hash>", "base": {"z3": "...", "efch": "...", "...": "..."},
                 "cierre": {"<id de ranura>": "<contenido>"},
                 "objeto_verificado": "<contenido de la forma que recibió el verificador>",
                 "premisas": ["<id de certificado>"], "procedencia": "<id de certificado | null>",
                 "id": "<sha256 del certificado sin id>"},
 "coste": {"certificado": "<id>", "cpu_s": 0.0}}
```

- La revisión lleva siempre el objeto canónico completo (`forma_canonica`, texto), para que el oráculo pueda
  recalcular el hash y reelaborarlo.
- Los oráculos reciben, para cada paso, los certificados y las dos instantáneas (definiciones `.efch` y bases).
- Cualquier cambio en este anexo cambia `esquema`.
