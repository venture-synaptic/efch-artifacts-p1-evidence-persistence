# Especificación ejecutable del contrato de evidencias v2.7

Estado: **v2.7 congelada, 30/10/2026** (DEC-2026-10-29-03): la revisión r2, aprobada por Codex Sol en la comprobación de cierre (`resultados/codex/sol-cierre-v2.7/`; informe sha256 `e6b2e508bce87b0b2079c607b43e3cfe4aeb3e25edce74b678013e7dc47c3e86`, sobre `huellas-v2.7-r2.txt` = `581a561439c7773f822a98e8b36423597dc866fb243477a7c4cc6efb1ccac7a3`). **Congelada:** `resultados/especificacion-v2.7.sha256`. Cualquier cambio exige una versión nueva y otra auditoría. Contrato de EFCH-CTRL-G6. Parte de la v2.6 congelada (`resultados/especificacion-v2.6.sha256`, commit `78139f5`, que no se modifica) y corrige la identidad de las candidatas y de las ranuras repetidas en la elaboración (§2.2), con la resolución del ámbito y ocho vectores nuevos; §15 da el motivo. Hipótesis H2; puertas G0 y G5. Aplica la **regla de
parada** que decidió el autor tras el punto de control (`resultados/codex/sol-control-1/`). Mientras Sol no apruebe
esta especificación, no se corrige B1-v2 ni `store`, no se congela la batería de Astra, no se empieza E-v4 y la
reserva de EXP-018 sigue cerrada.

Las versiones v2.1 a v2.4 no se aprobaron (`resultados/codex/sol-auditoria-contrato-1/` a `-4/`, que guardan
también cada versión auditada). §13 relaciona cada hallazgo con su resolución.

**Normatividad.**
- Normativos: el código de `especificacion/` (`canon.py`, `contrato.py`, `reglas.py`, `efch_formas.py`,
  `evolucion.py`), los esquemas de `esquemas/` (generados por `esquemas_json.py`) y los vectores de `vectores/`. Este
  texto los explica.
- Si el texto y el código discrepan, es un defecto de la especificación: se corrige aquí, no en una implementación.
- Ni la referencia ni la batería pueden interpretar el contrato. Una duda se resuelve en la especificación.
- La especificación sustituye al Anexo A y a §2–§5 de `docs/diseno-identidad-evidencias.md`. El resto del diseño
  sigue vigente.

## 1. Decisiones del autor que incorpora

| Decisión | Dónde |
|---|---|
| Regla de parada: primero la especificación ejecutable y el contrato único; después, las correcciones | Todo el documento |
| D-2: la base de confianza identifica todo lo que puede alterar el resultado; la invalidación es por clase y conservadora | §3.3 |
| D-3: `desconocido` y las mediciones son registros históricos; nunca son premisa ni procedencia. Se mantiene provisionalmente la política operativa de B1-v1 | §3.4, §12 |
| D8: definición registrada, dependencias efectivas, identidad, evidencia histórica y vigencia son cosas distintas | §9 |
| D9 en `evolve`: un cuerpo nuevo nunca hereda la identidad antigua | §5.2, §9 |
| Una equivalencia bajo `x = 1` nunca justifica una conclusión incondicional | §3.2, §6 |
| Se valida toda la cadena de derivación, no solo el certificado final | §6 |

## 2. Contrato de intercambio (`canon.py`, `contrato.py`, `efch_formas.py`, `esquemas/`)

### 2.1 Forma canónica, dominio y entrada textual (`canon.py`)

**Dominio canónico** de un valor JSON:
- anidamiento de 32 niveles como máximo, comprobado antes que nada y sin recursión;
- enteros en [-2^63, 2^128);
- texto UTF-8 válido, sin sustitutos aislados y **sin normalizar**: el texto se compara por sus bytes, así que el
  contrato no depende de ninguna versión de Unicode;
- ningún número de coma flotante.

Lo que no cumpla esto se rechaza con `no_canonico`. El primer fallo se busca en orden determinista: primero la
profundidad; después, en preorden, con las claves de cada objeto ordenadas.

**Forma canónica:** `json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)`
en UTF-8.

El `id` de un objeto es el sha256 hexadecimal de la forma canónica del objeto **sin** `id`. En un registro se
excluyen además sus `mediciones` del hash, pero **se validan igual**: tienen que ser canónicas y solo texto, entero,
booleano o null. Los identificadores solo se comparan; **nunca se analizan**.

`esquema = "efch-evidencia/2.5"`. Los objetos de versiones anteriores se rechazan. **[Decisión provisional, v2.6]** El identificador de intercambio no cambia: la v2.6 no altera el conjunto de paquetes que acepta `contrato` ni ningún id (`canonicos.json` es idéntico); solo estrecha el esquema hasta lo que `contrato` ya exigía.

**Formato, perfil de aceptación y verificador (v2.7).** Son tres versiones independientes:
- `esquema = "efch-evidencia/2.5"` identifica el **formato** de intercambio: la estructura de los objetos y la regla
  de sus ids. No ha cambiado desde la v2.5, y por eso los ids tampoco.
- El **perfil de aceptación** es qué paquetes acepta el validador. Lo identifica la versión de esta especificación
  con su lista de huellas, no el identificador de formato. El de la v2.7 es más estricto que el de la v2.6: resuelve
  el ámbito de las candidatas (§2.2).
- El **verificador** es la implementación que aplicó el perfil. Su versión se registra aparte cuando determina si
  una evidencia es aplicable.

Consecuencias para los consumidores:
- Un consumidor que reconoce el formato 2.5 no puede suponer, por eso, que un paquete es conforme con la v2.7.
- Un paquete aceptado con el perfil v2.5 o v2.6 se revalida con el perfil v2.7 antes de reutilizarlo.
- Como los ids no cambian, no hay migración de formato.
- Cómo entra la versión del verificador en la base de confianza (D-2, §3.3) queda abierto (§12).

**Entrada textual** (`canon.decodificar`). La entrada normativa son **bytes**: pasar texto de Python es un error de
uso (`TypeError`) y queda fuera del dominio. El validador decodifica los bytes en este orden:
1. UTF-8 estricto;
2. sin convertir nada, profundidad (32) y números de más de 39 cifras;
3. un único valor JSON, sin claves duplicadas, sin números no enteros (`1.0`, `1e3`) y sin `NaN`/`Infinity`;
4. el dominio canónico de todo el valor.

Todo se rechaza con `no_canonico`. Los espacios entre símbolos están permitidos y un escape `\uXXXX` equivale al
carácter escapado: lo canónico se exige a cada objeto, no al archivo.

**Igualdad.** Dos valores JSON son iguales si y solo si lo son sus bytes canónicos. Por ejemplo, `false` ≠ `0` y
`"é"` (NFC) ≠ `"é"` (NFD).

### 2.2 Objetos

| Objeto | Campos | Notas |
|---|---|---|
| `ranura` | `tipo`, `ambito`, `nombre` | El *dónde*. `ambito` es la ranura implementada (candidatas) o `""` |
| `revision` | `ranura`, `contenido`, `forma_canonica`, `fuente`, `forma_fuente`, `firma`, `dependencias` | El *qué* |
| `instantanea` | `revisiones`, `base` | `{ranura: id de revisión}` y `{componente: huella}` |
| `afirmacion` | `clase`, `sujetos`, `contexto` | Qué se dice (§3) |
| `certificado` | `afirmacion`, `estado`, `via`, `regla`, `instantanea`, `base`, `cierre`, `objeto_verificado`, `premisas`, `procedencia` | Por qué se cree (§5–§6) |
| `registro` | `afirmacion`, `resultado`, `via`, `instantanea`, `origen`, `mediciones` | Historia no reutilizable (§3.4) |

Todos llevan `esquema` e `id`. Todos salvo la ranura llevan `semantica` (`"efch-0.1"`).

**Revisión.**
- `contenido = sha256(forma_canonica)` es el **significado expandido**.
- `id` es la **identidad del objeto**: incluye además la fuente, la firma y las dependencias. Dos revisiones con la
  misma expansión y distinta fuente, como `g = f-(x)` y `g = h(x)` con `f- = h = 0`, son objetos distintos.
- `dependencias` es el mapa **transitivo** `{ranura: id de revisión}` de todo lo que se expandió, sin la ranura
  propia. Se comprueba que sea transitivo y coherente (`cierre_incoherente`).
- Instantáneas, cierres y dependencias usan **ids de revisión**: no hay que resolver nada por contenido.

**Identidad de ranura (v2.7).**
- La identidad de un objeto de la definición es su **ranura**: `tipo`, `ambito` y `nombre`. El nombre solo no
  identifica: puede repetirse entre tipos (una computación y una candidata `c`) y entre ámbitos (dos candidatas `c`
  de computaciones distintas son dos ranuras, dos revisiones y dos sujetos de evidencia distintos).
- `ambito` es el **id de la ranura de la computación** que implementa la candidata, nunca su nombre ni otro texto.
  Al validar, el ámbito de cada candidata **alcanzada** por la comprobación (como sujeto o en un cierre, §6.1) se
  resuelve en una ranura del paquete (`referencia_desconocida`) de tipo computación (`ambito_invalido`). La
  prevalidación global (§4) solo comprueba la forma: una ranura que no alcanza ninguna comprobación no se resuelve.
- Una elaboración da **una revisión por ranura**. Dos objetos de la misma ranura con revisiones distintas
  (propiedades homónimas, o candidatas homónimas de la misma computación) la hacen inválida (`RanuraRepetida` en
  `efch_formas`; `contrato.instantanea` tampoco admite dos revisiones de una ranura); si la revisión es la misma,
  es un único objeto. `efch_formas` indexa por id de ranura, nunca por nombre.

**Procedimiento único** para EFCH 0.1 (`efch_formas.py`, con `efch.core` y `efch.sexpr`):

| Tipo | `forma_canonica` | `fuente` | `firma` |
|---|---|---|---|
| computación | `Computation.canonical()` | `sexpr.dumps` de su forma `(computation …)` | `Computation.signature()` |
| propiedad | `(efch 0.1 (property ((x T) …)) canonical(body, variables))` | `sexpr.dumps` de su forma `(property …)` | `(property ((x T) …))` |
| candidata | `Candidate.canonical(comp)` | `Candidate.source_text` | firma de la computación implementada |
| candidata de EFCH Lang | La de la candidata del núcleo que produce el traductor | Ídem | Ídem |

Las dependencias directas son las listas `(call NOMBRE …)` de la fuente, a cualquier profundidad (también en los
argumentos), recorridas como árbol y resueltas en la definición. `vectores/canonicos.json` fija los bytes
resultantes.

### 2.3 Paquete

`{"esquema", "ranuras", "revisiones", "instantaneas", "afirmaciones", "certificados", "registros"}`, sin claves de
más (`campo_desconocido`). Cada tabla está indexada por `id`, y el índice tiene que coincidir con el `id`.

Un paso de B1, de E o del registro exporta un paquete con todo lo que referencian sus certificados.

**Alcance de los esquemas** (`esquemas/`). Validan la forma de cada objeto **aislado**, incluidas las condiciones
entre sus propios campos que dependen del valor de un campo (el ámbito según el tipo de ranura, el contexto fijo
según la clase, los campos de una hoja directa o de una conservación, el origen según la vía del registro). No
expresan las **comparaciones dinámicas de igualdad o pertenencia entre valores arbitrarios** de dos campos: que la procedencia de una transferencia sea su premisa
`origen` y que una revisión no dependa de su propia ranura (vectores `rechazo-procedencia` y
`rechazo-revision-autodependencia`, que el esquema acepta). Tampoco resuelven referencias entre objetos, como el
ámbito de una candidata (v2.7; `rechazo-ambito-propiedad`, `rechazo-ambito-ausente`). Un hash es exactamente 64 hexadecimales en minúscula: el patrón lleva `maxLength: 64`, porque `$` admite un LF final en algunos motores de expresiones regulares. No validan lo que exige calcular hashes, comprobar el dominio canónico o relacionar
objetos: eso lo hacen `contrato` y `reglas`. Un paquete que el esquema acepta puede rechazarlo el validador; al
revés, nunca.

## 3. Afirmaciones

### 3.1 Clases y papeles

| Clase | Papeles y tipos de ranura |
|---|---|
| WD | `objeto`: computación o candidata |
| EQ | `nueva`, `anterior`: computaciones de la **misma ranura y firma** |
| PROP | `propiedad` |
| REAL | `candidata` (con ámbito = la computación), `computacion` |
| REFUT | Los mismos papeles que REAL, con testigo |
| INV | `objeto`: computación |
| CBMC | `candidata`, `computacion` |
| TRADUCCION-C | `objeto`: computación o candidata |
| RENDIMIENTO | `objeto`: computación o candidata |

Solo PROP, REAL y REFUT son destino de una transferencia. Todas las clases se pueden conservar.

### 3.2 Contexto fijo

| Clase | Contexto |
|---|---|
| WD, REAL, INV, CBMC, TRADUCCION-C, RENDIMIENTO | `{}` |
| EQ | `{"direccion": "d->a"}` |
| PROP | `{"supuestos": ["L-OBS"]}` |
| REFUT | `{"testigo": {nombre: valor}}` |

Las hipótesis no se admiten. Cualquier otro contexto se rechaza con `contexto_no_fijo`, **también en una premisa**.

El testigo no es una hipótesis. Sus valores son booleanos, enteros no negativos (bv) o listas de bytes, y puede ser
`{}` en una computación sin entradas. Que el testigo se ajuste a la firma lo garantiza la hoja que lo evalúa (el
intérprete, §6), no el contrato.

### 3.3 Base de confianza por clase (D-2)

| Clase | Componentes |
|---|---|
| WD, EQ, PROP, REAL, INV | `efch-core`, `efch-smt`, `efch-interp`, `z3`, `ejecutor`, `reglas` |
| REFUT | `efch-core`, `efch-interp`, `ejecutor`, `reglas` |
| CBMC | `efch-core`, `efch-c`, `cbmc`, `ejecutor`, `reglas` |
| TRADUCCION-C | `efch-core`, `efch-c`, `gcc`, `abi`, `ejecutor`, `reglas` |
| RENDIMIENTO | `efch-c`, `gcc`, `abi`, `cpu`, `workload`, `ejecutor`, `reglas` |

Si algún sujeto es una candidata de EFCH Lang, se añade `traductor`. En REAL, además, `efch-c` y `cbmc` (D-20).

- `ejecutor` identifica el trabajador, las recetas y los adaptadores.
- Cada componente es una huella que fija la instantánea: módulos, versiones y opciones efectivas.
- Un cambio invalida **solo** las clases que lo incluyen. Hay vectores para un cambio relevante y para uno
  irrelevante.
- Que las huellas identifiquen realmente todo lo causal es una obligación del productor de la instantánea (§11).

### 3.4 Estados: certificado frente a registro (D-3)

- **Certificado:** solo puede estar `probado` o `refutado` (REAL, REFUT y RENDIMIENTO, solo `probado`). Es lo
  único reutilizable.
- **Registro:**
  - puede ser cualquier resultado (`desconocido`, `no comprobado`, `fuera de alcance`, `evidencia experimental`),
    con sus mediciones;
  - `via` ∈ {`directa`, `conservada-operativa`}; la segunda es la política histórica de B1-v1;
  - **nunca** es premisa ni procedencia de un certificado (`registro_como_premisa`);
  - una medición reutilizada se marca `conservada-operativa` y nunca se presenta como ejecución nueva.

## 4. Validación de forma

### 4.1 Precedencia normativa (el primer fallo da el código)

**Paquete** (`contrato.validar_paquete`):
1. es un objeto (`tipo_invalido`);
2. `esquema` (`esquema_desconocido`);
3. tablas ausentes (`campo_ausente`);
4. claves de más (`campo_desconocido`);
5. en orden alfabético de tabla, que sea un objeto (`tipo_invalido`) y que sus índices sean hashes, en orden
   (`tipo_invalido`).

**Prevalidación global.** En orden alfabético de tabla (`afirmaciones`, `certificados`, `instantaneas`, `ranuras`,
`registros`, `revisiones`) y de id, cada fila pasa por la validación de forma de su objeto. Una fila null da
`tipo_invalido`. Después se comprueba que el índice sea el id (`hash_invalido`). Un objeto mal formado rechaza el
paquete entero, aunque no lo alcance el certificado comprobado.

**Cada objeto:**
1. es un objeto (`tipo_invalido`);
2. `esquema` (`esquema_desconocido`);
3. campos ausentes (`campo_ausente`);
4. campos de más (`campo_desconocido`);
5. tipo JSON de cada campo, en orden alfabético (`tipo_invalido`; tabla siguiente);
6. `semantica` (`semantica_desconocida`);
7. dominio canónico de todo el objeto (`no_canonico`);
8. hash (`hash_invalido`);
9. comprobaciones propias, en este orden:

**Tipos del paso 5** (`contrato.TIPOS_CAMPO`). `texto` es una cadena; `hash`, una cadena de 64 caracteres
hexadecimales en minúscula; `hash?`, un hash o null; `ambito`, un hash o `""`; `objeto`, un objeto JSON. El formato de
hash forma parte del tipo, así que se comprueba en el paso 5, antes que el dominio canónico (paso 7).

| Objeto | Campos y tipos |
|---|---|
| ranura | `ambito` ambito, `esquema` texto, `id` hash, `nombre` texto, `tipo` texto |
| revision | `contenido` hash, `dependencias` objeto, `esquema` texto, `firma` texto, `forma_canonica` texto, `forma_fuente` hash, `fuente` texto, `id` hash, `ranura` hash, `semantica` texto |
| instantanea | `base` objeto, `esquema` texto, `id` hash, `revisiones` objeto, `semantica` texto |
| afirmacion | `clase` texto, `contexto` objeto, `esquema` texto, `id` hash, `semantica` texto, `sujetos` objeto |
| certificado | `afirmacion` hash, `base` objeto, `cierre` objeto, `esquema` texto, `estado` texto, `id` hash, `instantanea` hash, `objeto_verificado` hash?, `premisas` objeto, `procedencia` hash?, `regla` texto, `semantica` texto, `via` texto |
| registro | `afirmacion` hash, `esquema` texto, `id` hash, `instantanea` hash, `mediciones` objeto, `origen` hash?, `resultado` texto, `semantica` texto, `via` texto |

| Objeto | Paso 9 |
|---|---|
| ranura | `tipo` admitido; `nombre` no vacío; `ambito`: un hash en las candidatas y `""` en las demás (todo `tipo_invalido`) |
| revisión | `contenido` (`contenido_invalido`); `forma_fuente` (`fuente_invalida`); `dependencias`: claves y valores hash en orden de clave, y sin la ranura propia (`tipo_invalido`) |
| instantánea | `revisiones`: hashes en orden; `base`: claves conocidas en orden (`componente_desconocido`) y valores de texto |
| afirmación | `clase` (`clase_desconocida`); papeles exactos (`papel_invalido`); sujetos hash; contexto: en REFUT, exactamente `{testigo: objeto}` (`contexto_no_fijo`) con valores admitidos en orden (`tipo_invalido`); en las demás, igual al fijo (`contexto_no_fijo`) |
| certificado | `estado` (`estado_no_reutilizable`); vía y regla (`via_regla_incompatible`); `base` (`componente_desconocido`); `cierre` y `premisas`, hashes; si es directa, `objeto_verificado` hash y ni premisas ni procedencia (`premisa_sobrante`); si no, `objeto_verificado` null (`objeto_verificado_distinto`) y procedencia hash; conservación sin premisas (`premisa_sobrante`); transferencia con procedencia = premisa `origen` (`procedencia_invalida`) |
| registro | `resultado` y `via` (`tipo_invalido`); `origen` coherente con la vía (`procedencia_invalida`); valores de `mediciones` (`tipo_invalido`) |

Un objeto mal formado da siempre el mismo código, sin excepciones de Python ni dependencia del entorno.

## 5. Cierre y vigencia (`reglas.py`)

### 5.1 Cierre

El cierre de una afirmación es la unión, sobre los papeles de cierre, de `{ranura: id}` del sujeto y de sus
`dependencias`. Los papeles de cierre son todos, salvo en EQ, que solo tiene `nueva`.

- **EQ** relaciona dos instantáneas. La revisión `anterior` es un objeto histórico fijado por su id y no tiene que
  estar vigente.
- Si una ranura aparece con dos revisiones, el cierre es incoherente (`cierre_incoherente`).
- El certificado declara su cierre, y tiene que ser exactamente el intrínseco (`cierre_distinto`).

### 5.2 Vigencia

Un certificado está vigente en la instantánea S si cada par `(ranura, id)` de su cierre está en `S.revisiones` y
su base es la base de su clase en S.

La vigencia **se calcula; no se guarda**. Un certificado es válido en su propia instantánea, y para reutilizarlo en
otra hay que llamar a `Validador.reutilizable(cert, S)`. Una hoja directa tiene que declarar como
`objeto_verificado` el contenido del sujeto principal (`objeto_verificado_distinto`).

## 6. Reglas

**Base de confianza.** Hay dos tipos de objetos que las reglas no comprueban por dentro:
1. **Hojas directas:** su veredicto lo contrastan los oráculos (a) y (b).
2. **Elaboración:** revisiones e instantáneas. Que `forma_canonica`, `fuente`, `firma` y `dependencias`
   correspondan de verdad a la definición, y que la instantánea sea la elaboración de las definiciones vigentes, lo
   contrasta el oráculo (e) de elaboración (§11).

Sol mostró (`soundness.fuente_no_fiel`) que con una revisión infiel R-PROP puede aceptar una conclusión falsa. Esto
**no** es un hueco de las reglas: es la frontera declarada de la confianza, y por eso se exige su oráculo. Tampoco
se comprueba por dentro que el `objeto_verificado` sea la entrada real del verificador: es una obligación del
`ejecutor` (componente de base), que contrasta el oráculo (a).

### 6.1 Precedencia semántica

1. **Cadena en postorden, sin recursión.** Se recorren los hijos de cada certificado: primero la procedencia y
   luego las premisas, por nombre. Cada hijo se valida entero antes que su consumidor. Un hijo ausente da
   `referencia_desconocida` y un registro da `registro_como_premisa`, en su turno: un fallo de la cadena precede
   siempre a los de su consumidor. No hay cota de profundidad.
2. **En cada certificado:**
   1. la afirmación;
   2. sus sujetos, en orden de papel; de cada uno, por este orden:
      - la revisión y su ranura; en una candidata, su ámbito: una ranura del paquete (`referencia_desconocida`)
        de tipo computación (`ambito_invalido`) (v2.7);
      - cada dependencia, en orden: que sea una computación (`tipo_invalido`), que exista, que sea de esa ranura y
        que el mapa sea transitivo (`cierre_incoherente`);
      - la semántica (`semantica_distinta`);
      - el tipo de ranura del papel (`tipo_sujeto_invalido`);
   3. el ámbito de la candidata (`tipo_sujeto_invalido`) y, en EQ, ranura y firma (`ranura_distinta`,
      `firma_distinta`);
   4. la instantánea;
   5. la semántica del certificado y de su instantánea;
   6. el estado de la clase (`estado_invalido`);
   7. el cierre (`cierre_incoherente`, `cierre_distinto`);
   8. la base (`base_incompleta`, `base_distinta`);
   9. la vigencia propia (`no_vigente`);
   10. la regla.
3. **Regla:**
   - **directa:** objeto verificado;
   - **conservación:** afirmación, estado y base de la procedencia;
   - **transferencia:** clase de la regla (`regla_clase_incompatible`); `origen` (ausente, clase, estado, base);
     las comprobaciones específicas en el orden de las tablas siguientes; las premisas en ese orden (cada una:
     ausente, clase y sujetos, estado y vigencia); y, al final, las sobrantes.
     - R-PROP: ranura y firma, fuente, ranuras del cierre y, por cada ranura cambiada en orden, `eq`, `wd_a` y
       `wd_d`.
     - R-REAL: candidata, ranura y firma de `f`, cobertura (sobre la unión de ranuras de los dos cierres, en
       orden) y, después, `eq`, `wd_a` y `wd_c`.
     - R-REFUT: candidata, ranura y firma de `f`, testigo, `evaluacion` (y `evaluacion_no_directa`) y la `eq`
       opcional.
4. **`reutilizable(c, S)`:** primero la validez de `c` y después su vigencia en S.

**Validación de la cadena.** Un certificado es válido si:
- su forma es válida;
- sus sujetos son los que exige su clase;
- su estado es uno de los de su clase;
- su cierre y su base son los de su instantánea, y está vigente en ella;
- cumple su regla, con **todas** sus premisas y su procedencia validadas recursivamente hasta hojas directas.

Sobre la cadena:
- una premisa que sobra o que falta es un rechazo;
- un registro nunca es premisa ni procedencia;
- la cadena se valida **sin recursión**, en postorden: primero la procedencia, luego las premisas por nombre y,
  por último, el certificado. Un fallo en la cadena tiene, por tanto, precedencia sobre los de su consumidor;
- no hay cota de profundidad: un paquete válido lo es con cualquier límite de pila (vector
  `valido-cadena-profunda`, 1100 conservaciones);
- en cada certificado, el orden de comprobación es: estado, cierre, base, vigencia y regla.

**Conservación** (`conservada` o `cache`). La procedencia O tiene que ser válida, con la misma afirmación, el mismo
estado y la misma base, y el certificado tiene que estar vigente en su instantánea.

**R-PROP: de PROP(p_a) a PROP(p_d)**, con el mismo estado que el origen.

| Premisa | Condición |
|---|---|
| `origen` | PROP válida (en S_a = su instantánea), con el mismo estado y la misma base de clase |
| — | Misma ranura y firma de `p`; **misma `forma_fuente`** (`fuente_distinta`) |
| — | Mismas ranuras en los dos cierres (`ranura_nueva`); C = las ranuras cuya revisión cambia, sin contar la propia `p` |
| `eq:<ranura>`, para cada computación de C | EQ(nueva = s_d, anterior = s_a) `probado`, vigente en S_d |
| `wd_a:<ranura>` | WD(s_a) `probado`, vigente en S_a |
| `wd_d:<ranura>` | WD(s_d) `probado`, vigente en S_d |

**R-REAL: de REAL(c, f_a) a REAL(c, f_d)**, solo `probado`.

| Premisa | Condición |
|---|---|
| `origen` | REAL válida, con la misma base |
| — | **Misma revisión (id) de `c`** (`candidata_distinta`); misma ranura y firma de `f` |
| — | Todo cambio del cierre está en `f` o en sus dependencias, contando las ranuras que el cierre gana o pierde (si `f_d` pasa a llamar a `h`, la EQ de `f` lo cubre). No se exige el mismo conjunto de ranuras, a diferencia de R-PROP |
| `eq` | EQ(f_d → f_a) `probado`, vigente en S_d |
| `wd_a` | WD(f_a) `probado`, vigente en S_a |
| `wd_c` | WD(c) `probado`, vigente en S_d |

**R-REFUT: de REFUT(c, f_a, w) a REFUT(c, f_d, w)**, solo `probado`.

| Premisa | Condición |
|---|---|
| `origen` | REFUT válida, con el mismo testigo (`testigo_distinto`) y la misma base |
| — | Misma revisión de `c`; misma ranura y firma de `f` |
| `evaluacion` | **Hoja directa** de la misma afirmación de destino, vigente en S_d (el intérprete reevalúa w) |
| `eq` (opcional) | Si está, EQ(f_d → f_a) `probado`, vigente en S_d |

La EQ de R-REFUT no es necesaria para la validez. El contador de EXP-018 la exige, y por eso es una premisa
**opcional admitida**: si está, se valida como cualquier otra; si no, no se exige.

**Nunca se transfieren:** WD, EQ, INV, CBMC, TRADUCCION-C ni RENDIMIENTO.

**Reutilización.** B1, E y el registro solo reutilizan un certificado si `reutilizable(cert, S_actual)` lo acepta.
Esto vale también para la caché.

## 7. Códigos de rechazo

| Grupo | Códigos |
|---|---|
| Forma | `esquema_desconocido`, `semantica_desconocida`, `campo_ausente`, `campo_desconocido`, `tipo_invalido`, `no_canonico`, `hash_invalido`, `contenido_invalido`, `fuente_invalida`, `componente_desconocido`, `estado_no_reutilizable`, `via_regla_incompatible`, `procedencia_invalida`, `objeto_verificado_distinto`, `premisa_sobrante` |
| Afirmaciones | `clase_desconocida`, `papel_invalido`, `contexto_no_fijo`, `tipo_sujeto_invalido`, `ranura_distinta`, `firma_distinta`, `semantica_distinta` |
| Referencias | `referencia_desconocida`, `registro_como_premisa`, `ciclo`, `ambito_invalido` |
| Cierre, base y vigencia | `cierre_incoherente`, `cierre_distinto`, `base_incompleta`, `base_distinta`, `no_vigente`, `estado_invalido` |
| Reglas | `premisa_ausente`, `premisa_clase`, `premisa_estado`, `conservacion_afirmacion_distinta`, `conservacion_estado_distinto`, `regla_clase_incompatible`, `clase_no_transferible`, `fuente_distinta`, `ranura_nueva`, `cambio_no_cubierto`, `candidata_distinta`, `testigo_distinto`, `evaluacion_no_directa` |

**Inalcanzables** con las comprobaciones actuales (son defensivos; `vectores.INALCANZABLES` da el motivo):
- `semantica_distinta`, `clase_no_transferible` y `cambio_no_cubierto`: otros rechazos los preceden
  (estructuralmente);
- `ciclo`: exige un ciclo de preimágenes de SHA-256, computacionalmente inviable bajo el supuesto criptográfico
  habitual (no es imposible lógicamente).

El resto lo cubre al menos un vector (`vectores.cobertura`).

## 8. Exploración acotada (`exploracion.py`)

`python3 -m especificacion.exploracion --salida resultados/exploracion.json --exportar resultados/exploracion-muestra.json.gz`

**[Experimento] Modelo semántico abstracto, independiente de EFCH.**
- Dominio {0, 1}; valores {0, 1, ⊥}.
- Computaciones base `f` y `h`. `g` llama a `f` con un combinador (`id`, `neg` o `k0`). La propiedad `p` habla de
  `g`. La candidata `c` implementa `f` y es una tabla o una llamada a `h`.
- En EQ, un ⊥ de la revisión anterior vale 0, como en la codificación total de SMT.
- Las hojas directas y las revisiones son verídicas (la base de confianza de §6).
- **Alcance (v2.7).** Hay una sola candidata, `c` de `f`. El modelo no contiene candidatas homónimas ni ámbitos
  repetidos, así que no cubre la clase de defectos de identidad de §2.2 y §15. Repetirla con la v2.7 muestra que no
  cambian las reglas en este modelo, no que la identidad sea correcta. Esa clase la cubren los vectores y pruebas
  de §15.

**Enumeración.** Exhaustiva sobre los pares de instantáneas del generador.
- En cada mundo se construyen los intentos honestos de R-PROP, R-REAL y R-REFUT. Después se quita cada premisa, y
  cada grupo de premisas del mismo tipo, y se sustituye cada una por cada hoja del almacén: hojas con hipótesis,
  EQ invertidas y hojas de la otra instantánea.
- Además, se prueba una conservación sobre una R-PROP persistida sin EQ ni WD.
- Cada intento se juzga con la semántica de un paquete que solo contiene su cierre de certificados. Un intento que
  alcanza un objeto mal formado (una hoja con hipótesis) se rechaza con ese código, igual que haría la
  prevalidación global de §4.
- Las relajaciones son monótonas: una premisa relajada que esté presente se ignora; no cuenta como sobrante.

**Criterios.**
1. Cero certificados aceptados que sean falsos en el modelo.
2. Con cada comprobación relajada (y con pares que se enmascaran), la exploración encuentra un contraejemplo, o la
   comprobación se declara no observable en el modelo.

### 8.1 Resultados

`resultados/exploracion.json`, v2.3, 27/10/2026.

**[Resultado] Corrección en el modelo.** 1476 mundos y 422 545 intentos. Se aceptaron 1902 R-PROP, 154 R-REAL,
762 R-REFUT y 273 conservaciones, con **0 contraejemplos**. Son las mismas cifras que en la v2.1: el cambio a ids de
revisión no altera ningún veredicto del modelo. En la v2.3, con relajaciones monótonas, las cifras de EQ y WD
aumentan (antes muchas variantes caían por `premisa_sobrante`).

**[Resultado] Contraejemplos al relajar cada comprobación.**

| Comprobación relajada | Contraejemplos | Lectura |
|---|---:|---|
| Contexto fijo, también en premisas | 715 | Necesaria |
| Validación recursiva de la cadena | 460 | Necesaria |
| Estado del origen | 244 | Necesaria |
| EQ | 3773 | Necesaria |
| WD(s_d) | 3336 | Necesaria |
| WD(s_a) | 222 | Necesaria |
| Fuente de la propiedad | 32 | Necesaria |
| Evaluación directa del testigo | 468 | Necesaria |
| Testigo más evaluación | 744 | El testigo añade 276 a la evaluación sola |
| Candidata invariable más cobertura | 5 | Hace falta al menos una de las dos barreras; cada una enmascara a la otra |
| WD(c), también junto con el estado del origen | 0 (244 = el estado del origen solo) | **Redundante en el modelo:** relajada, se aceptan 839 R-REAL (frente a 154) sin ninguna falsa; REAL(c, f_a) `probado` sobre la misma `c` ya implica WD(c). Se mantiene como defensa en profundidad y por el contrato de EXP-018 |
| Vigencia, base, cierre, objeto verificado | 0 | **No observables en el generador:** no representa herramientas ni metadatos mal declarados. Los cubren los vectores |

La muestra exportada (`exploracion-muestra.json.gz`) tiene 30 mundos. De cada uno guarda el paquete y el veredicto
de los intentos **con forma válida y sin alcanzar ninguna afirmación mal formada**. Los demás intentos se rechazan
por forma, y esos casos los cubren los vectores. Es evidencia experimental en un modelo finito; no demuestra la corrección en
EFCH.

**Límites.**
- No representa herramientas, presupuestos, tipos de EFCH, bytes, opciones ni más de dos instantáneas por mundo.
- No altera la fidelidad de las revisiones, que es base de confianza (§6).
- «No observable» describe el generador; no acredita resistencia frente a esas mutaciones. Lo que no depende de la
  semántica lo cubren los vectores.
- Sol ensayó un modelo propio más rico (ocho valores, cuatro instantáneas, varias llamadas, cadenas y EQ no
  consecutivas) y casos reales de EFCH, sin falsos positivos con revisiones fieles
  (`resultados/codex/sol-auditoria-contrato-1/soundness/`, `real_efch.py`).

## 9. Modelo de evolución (`evolucion.py`)

| Concepto | Dónde vive | Al evolucionar `f` |
|---|---|---|
| Definición registrada (fuente, llamadas y firma) | `Registro.fuentes` | Solo cambia la de `f` |
| Dependencias efectivas | `revision.dependencias` en la instantánea | Cambian las de todo lo que expande `f` |
| Identidad | `revision.id` (y su `contenido`) | Cambia la de `f` y la de su cierre inverso |
| Evidencia histórica | Almacén inmutable | Nunca cambia ni se borra |
| Vigencia | `reutilizable(cert, S)` | Se recalcula: queda obsoleta toda evidencia cuyo cierre contenga `f` |

- La forma canónica del modelo incluye la firma: cambiar solo la firma cambia la identidad.
- **D8.** WD, propiedades, realizaciones y refutaciones de `f`, de quien la llama y de las candidatas que la llaman
  quedan obsoletas en la instantánea nueva, aunque siguen siendo válidas en la suya.
- **D9.** Un cuerpo nuevo es otra revisión, y `publicar` exige `objeto_verificado` = el contenido del sujeto. D9
  queda cerrado **si la hoja es fiel**, y la fidelidad es obligación del ejecutor (§6).
- Pruebas: `tests/test_especificacion.py`, clases `Evolucion` y `FormasEFCH`.

## 10. Vectores (`vectores/`)

`python3 -m especificacion.vectores --comprobar especificacion/vectores` (regenerarlos: `--salida`; son
deterministas).

**110 vectores. Válidos:**
- todas las reglas;
- cadenas largas (R-PROP, caché, R-PROP) y EQ no consecutivas (de S_a a S_e);
- una PROP refutada transferida;
- propiedades con varias llamadas y con llamadas en argumentos;
- R-REFUT con y sin la EQ opcional;
- INV, CBMC, TRADUCCION-C y RENDIMIENTO;
- un cambio de base irrelevante;
- REAL de EFCH Lang (varint) con la base ampliada;
- testigos vacíos y de bytes;
- una cadena de 1100 conservaciones;
- entrada textual con espacios y con escapes `\uXXXX`;
- un nombre con combinantes sin normalizar (sintético: asocia la revisión de `f-` a una ranura de otro nombre; prueba que el texto se compara por bytes, §2.1, no la fidelidad de la elaboración EFCH, que comprueba el oráculo (e) de §11.3);
- una R-REAL en la que `f` pasa a llamar a `h`;
- (v2.7) REAL de cada una de dos candidatas `c`, de `f` y de `g`, en la misma instantánea.

**Rechazos:**
- todos los códigos alcanzables de §7, incluidos los tres críticos del control y las decisiones del autor (D-2,
  D-3, D8 directa y transitiva, D9);
- precedencia con varios errores a la vez;
- prevalidación global (un registro no alcanzado con mediciones inválidas);
- igualdad tipada del testigo (`false` frente a `0`);
- entrada textual con número no entero, clave duplicada, UTF-8 inválido, entero de 5000 cifras, 2000 niveles de
  anidamiento o un sustituto (en `entrada_b64`);
- 40 niveles de anidamiento en un objeto;
- una fila null;
- varios errores en el contenedor;
- referencias ausentes que preceden a otros fallos del consumidor;
- un id con formato inválido junto con un flotante (el paso 5 gana al 7);
- (v2.6) un registro directo con origen y uno conservado sin origen, que también rechaza el esquema, y una revisión que depende de su propia ranura, que el esquema no puede rechazar (§2.3);
- (v2.6) un hash con LF final en un campo (`origen`) y en una clave (`cierre`), que rechazan el esquema y `contrato`;
- (v2.7) la REAL que une la `c` de `f` con `g`, y la que conserva o transfiere (R-REAL) la evidencia de una `c` como la de la otra; un
  ámbito que es la ranura de una propiedad, uno ausente del paquete y uno que es el nombre de la computación (este
  último lo rechaza también el esquema).

`canonicos.json` da los bytes y el id de cada objeto del escenario base, de las ranuras, revisiones e instantánea
del mundo de las candidatas homónimas (v2.7) y de un registro con otras mediciones que conserva su id.

## 11. Obligaciones de las implementaciones

1. **Referencia (B1-v2, `store`), E y la batería:**
   - producen las revisiones con el procedimiento de §2.2 y reproducen `canonicos.json` byte a byte;
   - dan el resultado esperado de **todos** los vectores con su propio validador (los de `entrada_b64`, desde los
     bytes y con su propio decodificador conforme a §2.1), y también el de la muestra
     exportada de la exploración (`resultados/exploracion-muestra.json.gz`: paquetes de mundos y el veredicto de
     cada intento);
   - exportan un paquete por paso.
2. **B1-v2, E y `store`** reutilizan solo a través de la comprobación de §6 (la suya, conforme a los vectores).
3. **Oráculos de la batería:**
   - (a) directo;
   - (b) exhaustivo;
   - (c) dependencias;
   - (d) derivaciones: no puede importar ni copiar `especificacion.reglas` ni `especificacion.contrato`, solo
     `canon` (serialización); se escribe a partir de este texto y de los vectores;
   - (e) **elaboración, nuevo:** reelabora cada revisión e instantánea desde las definiciones del escenario y
     comprueba `forma_canonica`, `fuente`, `firma`, `dependencias` y la correspondencia entre la instantánea y las
     definiciones vigentes.
   Una revisión independiente comprueba que no son copias.
4. **Producción de bases:** el productor de cada instantánea documenta qué identifica cada componente (módulos,
   versiones, opciones). La completitud causal de las huellas no la puede comprobar el contrato.
5. **Divergencias.** Toda divergencia entre una implementación y la especificación se registra como hallazgo y la
   resuelve el autor de la especificación. Ninguna implementación reinterpreta el contrato.

## 12. Limitaciones y asuntos abiertos

- **[Decisión del autor] D-3 frente a §5.6 del diseño.** El diseño decía «solo se conservan `probado` y
  `refutado`». B1 mantiene, provisionalmente, la conservación operativa de un `desconocido` (y de las mediciones)
  como **registro**. Es una discrepancia registrada expresamente. El protocolo congelado no se corrige en
  silencio.
- **Base de confianza** (§6): las hojas directas y la elaboración. Sus oráculos son (a), (b) y (e).
- **Residuo de D10** (`evidencia.py:70`, `lang.py:1011` y `:1020`): **defecto abierto**. El traductor congelado no
  se modifica, por la comparabilidad con D-S1-2.
- **Elaborador compartido.** `efch_formas` usa `efch.core`, y los oráculos (b) y (e) también. La exploración de §8
  y el modelo de Sol son independientes de `core`, pero no lo auditan.
- **Versión del verificador y base de confianza (v2.7).** El formato, el perfil de aceptación y el verificador
  se identifican por separado (§2.1). Falta decidir cómo entra la versión del verificador en la base de confianza
  (D-2) y en la invalidación por cambios de esa base.
- **Fuente y ranura (O1, v2.7).** En un paquete genérico, `fuente` es opaca: el contrato no comprueba que la fuente
  de una revisión declare el nombre de su ranura. En la elaboración EFCH, una discrepancia sin un renombrado fiel la
  detecta el oráculo (e); los canónicos no sustituyen ese control. No es un rechazo automático del contrato
  (auditoría de Sol, v2.7).
- **Versiones de Python:** solo se ha ensayado Python 3.14.4. Otras versiones no están verificadas.
- **Corpus de desarrollo.** Los 2400 escenarios de Astra son material de desarrollo. La evaluación final
  necesitará un corpus nuevo y reservado.

## 13. Respuesta a la auditoría de la v2.1

| Hallazgo de Sol | Gravedad | Resolución en v2.2 |
|---|---|---|
| 1. Revisión infiel (la fuente no corresponde a la expansión): transferencia falsa | Alta | La fidelidad de la elaboración es base de confianza declarada, con su oráculo (e) obligatorio (§6, §11.3) |
| 1. Críticos 1 y 2 | Cerrados | Sin cambios |
| 2. Potencia de §8 y alcance de su garantía; recuento de mundos | Media | Eliminación por grupos, pares enmascarados y cambios de fuente; límites reescritos; se cita el modelo de Sol; cifras de la nueva ejecución |
| 3. Sin procedimiento único para fuente y firma | Alta | `efch_formas.py` normativo, con vectores reales (§2.2) |
| 3. Mediciones: esquema y código en desacuerdo | Alta | Se validan canónicas, de texto, entero, booleano o null, en el código y en el esquema |
| 3. Veredictos no deterministas y `AttributeError` | Media | Orden de clave y comprobación de tipo antes de usar; paquete con claves exactas (§4) |
| 3. Dominio de serialización y testigos | Media | Sustitutos aislados y enteros fuera de rango dan `no_canonico`; testigo `{}` admitido; firma a cargo de la hoja (§3.2) |
| 3. Vectores con 27 de 45 códigos | Alta | 74 vectores: todos los alcanzables y los inalcanzables documentados (§7, §10) |
| 4. Cierre de EQ solo con `nueva` | Sin objeción | Sin cambios |
| 5. Historia auténtica que vuelve ambigua una evidencia (`revision_ambigua`) | Alta | Ids de revisión en instantáneas, cierres y dependencias; no hay resolución por contenido |
| 5. El modelo de evolución confundía la firma | Media | La firma entra en la forma y en la definición registrada |
| 5. D9, «imposible por construcción» | Media | Precisado: cerrado si la hoja es fiel (§9) |
| 6. Base y D-3 | Sin objeción | Completitud causal de las huellas como obligación del productor (§11.4) |
| 7. Exploración no reproducible por otro validador | Media | Muestra exportada de mundos y veredictos (§11.1) |
| 7. EQ en R-REFUT: texto y código contradictorios | Media | Premisa opcional admitida y validada (§6) |

**Segunda auditoría (v2.2 → v2.3; `resultados/codex/sol-auditoria-contrato-2/`).**

| Hallazgo de Sol | Gravedad | Resolución en v2.3 |
|---|---|---|
| Validador no total: `TypeError` con `via` no textual; orden de campos incumplido | Alta | Tipo JSON de cada campo antes de usarlo y precedencia normativa en 9 pasos (§4); vectores `precedencia-*` |
| Un paquete válido depende del límite de recursión | Media | Validación iterativa en postorden y dependencias comprobadas sin recursión (§6); vector `valido-cadena-profunda` |
| Decodificación textual JSON sin fijar (duplicados, `1.0`) | Alta | `canon.decodificar` normativo y vectores `texto-*` (§2.1) |
| Igualdad de testigos (`False` = `0`) | Media | Igualdad por bytes canónicos (§2.1); vector `testigo-tipado` |
| Mediciones no revisadas si el registro no se alcanza | Media | Prevalidación global de la forma (§4); vector `prevalidacion` |
| `ciclo`: inalcanzabilidad criptográfica, no lógica | Baja | Redactado (§7) |
| Lectura de las relajaciones: candidata más cobertura; WD(c) no monótona | Media | Relajaciones monótonas; tabla de §8.1 releída |
| Conformidad finita: regresión, no prueba general | Alta para G5 | Más vectores de frontera; la prueba general queda para el contraste con implementaciones independientes (§11) |

**Tercera auditoría (v2.3 → v2.4; `resultados/codex/sol-auditoria-contrato-3/`).** Ninguna transferencia falsa;
quedan hallazgos de totalidad, precedencia y conformidad.

| Hallazgo de Sol | Gravedad | Resolución en v2.4 |
|---|---|---|
| Listas anidadas: `RecursionError` o veredicto según la pila | Alta | Profundidad ≤ 32, comprobada sin recursión antes que nada; validación iterativa en orden determinista (§2.1) |
| El decodificador filtra `ValueError` o `RecursionError` (enteros largos, JSON profundo) | Alta | Exploración previa del texto: profundidad y cifras antes de convertir (§2.1) |
| NFC depende de la versión de Unicode | Alta para G5 | El texto no se normaliza: se compara por bytes (§2.1); vector `valido-unicode-sin-normalizar` |
| Postorden incumplido con referencias ausentes | Media | Las aristas ausentes se resuelven en su turno (§6.1); vectores `postorden-*` |
| Una fila null daba `referencia_desconocida` | Media | `tipo_invalido` en la prevalidación (§4.1); vector `fila-null` |
| El texto no fijaba por sí solo toda la precedencia | Media | §4.1 (contenedor, prevalidación, 9 pasos y paso 9 por objeto) y §6.1 (cadena, certificado, reglas) escritos completos; ausentes antes que sobrantes también en el contenedor |
| Alcance de los esquemas | Media | Condiciones internas de cada objeto añadidas; alcance declarado (§2.3) |
| Contrato de conformidad incompleto | Alta para G5 | 95 vectores con las fronteras anteriores; el contraste con implementaciones independientes sigue en §11 |
| La muestra no tenía todos los intentos anunciados | Baja | Alcance corregido (§8.1) |

**Cuarta auditoría (v2.4 → v2.5; `resultados/codex/sol-auditoria-contrato-4/`).** Cierra la totalidad, la entrada
textual, Unicode, el postorden, la fila null, los esquemas y la muestra. Sin transferencias falsas. Un validador
independiente escrito desde el texto coincide en 95 de 95 vectores y en 3167 de 3167 intentos. Quedaban dos
defectos de unicidad entre el texto y el código:

| Hallazgo de Sol | Gravedad | Resolución en v2.5 |
|---|---|---|
| R-REAL: el código exigía el mismo conjunto de ranuras y el texto, no; rechazaba un caso verdadero (`f` pasa a llamar a `h`) | Media | Se alinea el código con el texto: la cobertura incluye las ranuras ganadas o perdidas dentro de `f`; vector `valido-r_real-gana-ranura` |
| El texto remitía los tipos del paso 5 al código (formato de hash) | Media | Tabla completa de tipos en §4.1; vector `rechazo-tipo-y-canonico` |
| `decodificar` con texto de Python filtraba `UnicodeEncodeError` | Baja | La entrada normativa son bytes; texto de Python da `TypeError` (§2.1) |
| Solo se ensayó Python 3.14.4 | Limitación | Declarada (§12) |

## 14. Hallazgo de la batería sobre la v2.5 (v2.5 → v2.6)

Durante la adaptación de la batería (Codex Astra, 27/10/2026; `resultados/p4-bateria-v2.5/propuesta-v2.6.md`), la
regla de parada se aplicó a una discrepancia entre el texto y los esquemas. No hay aceptación falsa: `contrato`
rechazaba ya los dos casos.

| Hallazgo | Gravedad | Resolución en v2.6 |
|---|---|---|
| `registro.schema.json` admitía `directa` con origen y `conservada-operativa` sin origen, aunque §2.3 promete las condiciones internas y §4.1 y `contrato` las exigen (`procedencia_invalida`) | Media (unicidad entre texto y esquema) | Condición `via` → `origen` en el esquema; vectores `rechazo-registro-directo-origen` y `rechazo-registro-conservado-sin-origen` (el esquema y `contrato` los rechazan) |
| Barrido de los mismos casos: la rama de `contrato` de un registro incoherente y la de la autodependencia de una revisión no tenían vector | Baja | Vectores nuevos; §2.3 declara qué condiciones internas no expresa el esquema y la prueba lo comprueba |

**Auditoría del borrador (Codex Sol, 29/10/2026; `resultados/codex/sol-auditoria-v2.6/`): sí, con dos cambios
menores**, aplicados en esta versión:

| Hallazgo de Sol | Gravedad | Resolución |
|---|---|---|
| El patrón `^[0-9a-f]{64}$` admite 64 hexadecimales seguidos de LF (defecto heredado de la v2.5); `contrato` lo rechaza (`tipo_invalido`) | Menor (unicidad entre esquema y código) | `maxLength: 64` en todos los hashes, también en `propertyNames`; vectores `rechazo-hash-lf-campo` y `rechazo-hash-lf-clave` |
| «Comparan dos campos» incluía, literalmente, relaciones ya expresadas, como vía y regla | Menor (redacción) | §2.3: «comparaciones dinámicas de igualdad o pertenencia entre valores arbitrarios» |
| Identificador `efch-evidencia/2.5` | Sin objeción | Se mantiene; la versión de los esquemas se distingue por la versión del documento y su huella |

Sin cambios: `canon.py`, `contrato.py`, `reglas.py`, `efch_formas.py`, `evolucion.py`, la exploración y su muestra, y
`canonicos.json`. Un paquete que `contrato` acepta en la v2.5 lo acepta en la v2.6, y al revés; solo cambia lo que acepta el esquema.

**Comprobación de cierre (Codex Sol, 30/10/2026; `resultados/codex/sol-cierre-v2.6/`): sí, sin cambios.** 124/124 huellas, 102/102 vectores (también con el validador independiente), esquemas idénticos a los generados, ningún formato de hash inválido aceptado en 5464 mutaciones, §2.3 coherente con los esquemas y G0 con 257 pruebas sin fallos. Tras el cierre solo cambian el título, esta línea de estado y este párrafo.

## 15. Hallazgo de la batería sobre la v2.6 (v2.6 → v2.7)

**Hallazgo (Codex Astra, EFCH-CTRL-G6, 30/10/2026; `resultados/p4-bateria-v2.6/propuesta-v2.7.md`).**
`Formas.candidata` memorizaba con la clave `(tipo, nombre)`, sin el ámbito: dos candidatas `c` de `f` y de `g`
recibían la misma revisión y `Formas.todas` perdía una. Heredado de la v2.5. Gravedad: **alta** (identidad).

**Investigación del coordinador** (`resultados/v2.7-investigacion/`):

| Ruta | Defecto | Resolución |
|---|---|---|
| `Formas.candidata` | Clave sin ámbito (K1) | Índice por id de ranura |
| `Formas.propiedad` y `Formas.candidata` | Ranura repetida con otra revisión aceptada en silencio; se quedaba la primera (K2) | `RanuraRepetida` |
| `contrato.instantanea` | Dos revisiones de una ranura: se quedaba la última, sin aviso | `ValueError` |
| `reglas.Validador.ranura` | El ámbito de una candidata no se resolvía: aceptaba la ranura de una propiedad o un hash ausente | `referencia_desconocida` y `ambito_invalido` |
| `vectores` (generador) | Revisiones por nombre, sin tipo ni ámbito | `por_nombre`, que falla si un nombre se repite |
| `exploracion` (modelo de §8) | Etiquetas `f`, `g`, `h`, `p` y `c` de un universo cerrado sin colisiones | Ninguna: es una simplificación del modelo, no un cambio de identidad. Limita la cobertura (§8) |

Sin cambios: `canon.py`, `esquemas_json.py` y los esquemas, `evolucion.py` (ya indexa por id), la exploración y su
muestra. Ocho vectores nuevos (110). Los 102 vectores de la v2.6 y los 111 objetos de `canonicos.json` se regeneran idénticos byte a byte.
Eso muestra que esas identidades se conservan. **No** se deduce de que haya una revisión por ranura (I1 ≠ I5 en
la matriz de invariantes). Fuera de ese conjunto, la conservación solo se afirma en el alcance que se ha comprobado
(`resultados/v2.7-investigacion/`).

**Auditoría de Sol (30/10/2026; `resultados/codex/sol-auditoria-v2.7/`): candidato a congelación, sí con tres cambios
menores**, aplicados en la revisión r2 sin cambio semántico:

| Cambio | Dónde |
|---|---|
| Separar el formato 2.5 del perfil de aceptación v2.7 y explicar las consecuencias para los consumidores antiguos | §2.1, §12 |
| Precisar la matriz de invariantes (I1 frente a I5), el alcance de la exploración y que el vector Unicode es sintético | §8, §10, §15 y `matriz-invariantes-r2.md` |
| Acotar el barrido y la migración: ámbito por paquete, errores aparte, archivos únicos | `resultados/v2.7-investigacion/*-r2/` (fuera del contrato) |

**[Decisión] Migración (Sol, C4, aceptada por el autor):**
- se mantienen el formato `efch-evidencia/2.5` y los ids, y el perfil v2.7 se identifica por sus huellas (§2.1);
- antes de reutilizar evidencia anterior se revalida con el perfil v2.7, y los originales se conservan;
- los casos K1, K2, los ámbitos irresolubles y la procedencia dudosa se aíslan para reelaborarlos y verificarlos;
- no se transfiere evidencia por nombre ni se invalida en masa a partir de una muestra.

**Comprobación de cierre de la r2 (Codex Sol, 30/10/2026; `resultados/codex/sol-cierre-v2.7/`): sí.** La r2 corrige documentación y metodología, conserva la semántica auditada y sus resultados son reproducibles con los límites declarados (132/132 huellas, solo cambia este texto, 262 pruebas, 110 vectores y 120 canónicos con el validador independiente). Tras el cierre solo cambian el título y la línea de estado, y se añade este párrafo de referencia.
