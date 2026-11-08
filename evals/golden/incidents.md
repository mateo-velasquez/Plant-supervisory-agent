# Catálogo de incidentes, días 1-7 (T01-T21)

Fuente: solo las bitácoras `T01`-`T21` (turnos T01-T21, snapshots S001-S042). Los días 8-10 no se leyeron. Es un catálogo del lado de la bitácora: dice qué afirma cada bitácora. Si existe un caso, y cuándo se abre o escala, surge de los datos y se decide en los archivos `day_XX.yaml`. El código no lo parsea.

## Notas de autoría del golden

- Los análisis van en español, nunca se usa el símbolo de sección, y las reglas se citan como `criterio N`.
- Entrecomillar cada `justification` en el YAML: la regla (`criterio N` de `criterio.md`), los números, y en las causas el fragmento textual de la bitácora con su id de bitácora.
- Usar `requires: [agent]` en todo ítem que existe solo por el agente: las elevaciones del criterio 5, sus efectos (alertas y novedades causadas por una elevación, y el levantamiento) y las causas declaradas. Los ítems solo con umbrales no llevan `requires`.
- Usar `depends_on` solo para seguimiento (la pregunta abierta en que se apoya el ítem); nunca excluye al ítem del condicionamiento.
- Una causa conserva su origen hasta que el caso se resuelve (Q-38): una bitácora posterior no reescribe la causa de un caso abierto.
- Una bitácora `Txx` es legible solo en el snapshot de cierre de su turno (Q-01), nunca en el snapshot intermedio. El pasaje de turno a snapshot de cierre sale de `turnos.csv` (T01 -> S002, T02 -> S004, ... T21 -> S042).
- Vincular una causa de bitácora con un caso usa la etapa y/o el modelo que nombra la bitácora (Q-02): una parada de montaje de Pickup aplica a todos los mercados de Pickup.
- Cada cita de abajo está copiada textualmente de una sola línea de bitácora, así que se puede verificar con una búsqueda literal.

Resumen: 7 incidentes (I01-I07). El criterio 5 aplica a dos (I03, decidido en Q-39, e I07), con un punto abierto sobre I06.

## Incidentes

### I01 Parada de montaje de Sedán, resuelta en el mismo turno

| Campo | Valor |
|---|---|
| Turno(s) | T02 (lunes 2 de marzo de 2026, tarde, 14:00-22:00) |
| Categoría | `parada_de_linea` |
| Etapa | `montaje` |
| Modelo / mercado | Sedán, mercado no indicado |
| Cita de inicio | "A las 17:20 se paró la línea de montaje de Sedán por una falla en la atornilladora de la estación 14." (T02) |
| Cita de resolución | "Mantenimiento la cambió y la línea volvió a las 18:00." (T02); también "El ritmo se recuperó antes del final del turno." (T02) |
| ¿Aplica el criterio 5? | No. La misma línea dice que el problema se arregló: "la línea volvió a las 18:00". |
| Legible en | S004 |

### I02 Faltante de arneses de Sedán (camión del proveedor demorado)

| Campo | Valor |
|---|---|
| Turno(s) | T04 (martes 3 de marzo, mañana); efecto de recuperación en T05 |
| Categoría | `faltante_de_piezas` |
| Etapa | `montaje` |
| Modelo / mercado | Sedán, mercado no indicado |
| Cita de inicio | "Desde las 7:30 no entraron arneses eléctricos para Sedán: el camión del proveedor llegó recién a las 13:00." (T04) |
| Cita de resolución | "La línea de montaje de Sedán quedó frenada hasta las 13:30 y retomó cuando se descargó el material." (T04); "Compras habló con el proveedor y para mañana el abastecimiento está confirmado en el horario habitual." (T04) |
| ¿Aplica el criterio 5? | No. El material llegó y la línea se reanudó ("retomó cuando se descargó el material"), y el abastecimiento del día siguiente tiene fecha confirmada ("para mañana el abastecimiento está confirmado"). |
| Legible en | S008 |

Línea de efecto, no una causa nueva: "La línea de Sedán trabajó todo el turno a ritmo máximo para recuperar lo que quedó atrás a la mañana." (T05, legible en S010).

### I03 Auditoría de homologación que retiene SUV para Europa

| Campo | Valor |
|---|---|
| Turno(s) | T07 (miércoles 4 de marzo, mañana) a T10 (jueves 5 de marzo, mañana); también T08, T09 |
| Categoría | `retencion_de_calidad` |
| Etapa | `calidad` |
| Modelo / mercado | SUV, Europa ("las SUV de exportación", "las SUV para Europa") |
| Cita de inicio | "A media mañana llegó la auditoría de homologación para Europa y retuvo en calidad las SUV de exportación que pasaban por la estación final." (T07) |
| Citas de continuación | "La auditoría de homologación sigue revisando las SUV para Europa." (T08); "El auditor vuelve mañana a primera hora para terminar la revisión." (T08) |
| Cita de efecto | "Las retenidas no van a estar en patio para el traslado al puerto de las 20:00, así que pierden el buque de este jueves." (T08) |
| Cita de resolución | "La auditoría de homologación terminó a las 8:30 y se liberaron las SUV para Europa que estaban retenidas." (T10); "Salen en el buque del jueves 12." (T10) |
| ¿Aplica el criterio 5? | Sí (Q-39, ver Puntos abiertos). En T07 la bitácora no da fecha de fin de la auditoría. T08 dice "El auditor vuelve mañana a primera hora para terminar la revisión", que es una fecha de regreso del auditor, no de liberación. Elevación en S014, levantada en S020. |
| Legible en | S014 (T07), S016 (T08), S020 (resolución en T10) |

### I04 Diferencia de pintura Gris Grafito, SUV enviadas a repintado

| Campo | Valor |
|---|---|
| Turno(s) | T09 (noche del miércoles 4 al jueves 5 de marzo) a T10 |
| Categoría | `retrabajo` |
| Etapa | `pintura` (las unidades vuelven a la cabina de repintado) |
| Modelo / mercado | SUV en Gris Grafito, mercado no indicado |
| Cita de inicio | "A las 2:00 se separaron las carrocerías de SUV en Gris Grafito que habían salido de pintura desde la tarde, por diferencia de tono con la muestra patrón." (T09) |
| Estimación de tiempo | "Vuelven a la cabina de repintado; se estiman seis horas por unidad." (T09) |
| Cita de resolución | "Calidad de pintura ajustó la mezcla del Gris Grafito y las unidades nuevas salen bien." (T09); "Las SUV en Gris Grafito repintadas empezaron a volver a la línea de montaje." (T10) |
| ¿Aplica el criterio 5? | No. La bitácora dice que la causa se corrigió ("ajustó la mezcla ... las unidades nuevas salen bien") y da un tiempo por unidad ("se estiman seis horas por unidad"), así que no es una causa abierta sin fecha. |
| Legible en | S018 (T09), S020 (T10) |

Se superpone en el tiempo con I03 sobre el modelo SUV (I03 retiene SUV para Europa en `calidad`, I04 manda SUV a `pintura`). Cuál se vincula con un caso depende de la etapa de cuello de botella y del mercado del caso (Q-02); ver Puntos abiertos.

### I05 Retención de Pickup Local por control de torque

| Campo | Valor |
|---|---|
| Turno(s) | T11 (jueves 5 de marzo, tarde) |
| Categoría | `retencion_de_calidad` |
| Etapa | `calidad` |
| Modelo / mercado | Pickup, Local |
| Cita de inicio | "Desde el mediodía, calidad retuvo las pickups para el mercado local por un control de torque en las ruedas." (T11) |
| Cita de resolución | "Se revisaron una por una y se liberaron sin novedad cerca de las 19:00." (T11) |
| ¿Aplica el criterio 5? | No. La misma entrada dice que las unidades se liberaron: "se liberaron sin novedad cerca de las 19:00". |
| Legible en | S022 |

### I06 Sedán esperando al final del montaje, sin causa indicada

| Campo | Valor |
|---|---|
| Turno(s) | T13 (viernes 6 de marzo, mañana) |
| Categoría | `no_declarada` si se vincula un caso de Sedán (no se nombra ninguna causa) |
| Etapa | "ninguna nombrada" (el texto dice "al final de la línea de montaje"; no se nombra ninguna etapa como causa) |
| Modelo / mercado | Sedán, mercado no indicado |
| Cita de inicio | "Quedaron varias Sedán esperando al final de la línea de montaje." (T13) |
| Cita de resolución | ninguna. "Logística lo está viendo." (T13) no es una resolución; T14 dice "Sin paradas ni faltantes de material." (T14) |
| ¿Aplica el criterio 5? | No. No se indica causa, así que no hay una "causa sigue activa y no tiene fecha de resolución" para citar. |
| Legible en | S026 |

### I07 Parada de montaje de Pickup, transportador aéreo roto (elevación del criterio 5)

| Campo | Valor |
|---|---|
| Turno(s) | T17 (sábado 7 de marzo, tarde) a T19 (domingo 8 de marzo, mañana); T18 en el medio |
| Categoría | `parada_de_linea` |
| Etapa | `montaje` |
| Modelo / mercado | Pickup, todos los mercados (Q-02: modelo + etapa; la bitácora no nombra mercado) |
| Cita de inicio | "A las 15:00 se paró la línea de montaje de Pickup por la rotura del transportador aéreo de la estación 3." (T17) |
| Citas sin fecha | "Mantenimiento espera el repuesto y por ahora no hay fecha confirmada de vuelta." (T17); "La línea de montaje de Pickup sigue parada." (T18); "El repuesto del transportador viene desde la casa matriz y todavía no tiene horario de llegada." (T18) |
| Cita de efecto | "Carrocería y pintura de Pickup siguen trabajando y las unidades se acumulan antes de montaje." (T17) |
| Cita de resolución | "El repuesto del transportador llegó a las 7:30 y la línea de montaje de Pickup volvió a las 10:00." (T19) |
| ¿Aplica el criterio 5? | Sí, desde T17. "por ahora no hay fecha confirmada de vuelta" es una línea parada sin fecha de regreso, y T18 repite "todavía no tiene horario de llegada". La elevación lleva `requires: [agent]`, aplica a todo caso activo de Pickup con esta causa y a los casos abiertos mientras siga vigente. |
| Elevación decidida en | S034 (T17 legible). T18 (S036) confirma que sigue vigente. |
| Levantamiento | T19 informa la resolución, legible en S038. La elevación se levanta en S038 (Q-11) y desde ahí vuelve a aplicar la severidad mínima. |
| Legible en | S034, S036, S038 |

Líneas de recuperación tras el levantamiento (no son una causa nueva, y no resuelven el caso por sí solas; la resolución del ciclo de vida sigue el criterio 3): "Desde ahí trabaja a ritmo máximo para bajar lo acumulado." (T19); "Montaje de Pickup sigue a ritmo máximo; el acumulado antes de la línea bajó a la mitad." (T20).

## Distractores

Líneas que parecen causas o tareas pero no declaran una causa para un caso.

Seguridad:
- "Se reportó un casi accidente en el pasillo del patio: un autoelevador giró sin tocar bocina. Se habló con el operador." (T04; la misma línea aparece también en T07, T08, T10, T12, T13)
- "Se repuso un extintor vencido en la cabina de pintura 2." (T11; también T14, T16, T17, T19)
- "Se reforzó el uso de protección auditiva en carrocería." (T05; también T18)
- "Charla de seguridad de cinco minutos al inicio, sobre manejo de cargas." (T01; también T02, T09, T20)

Tareas pendientes:
- "Seguir el consumo de sellador en carrocería; quedó justo para el próximo turno." (T02; también T04, T07, T09, T17, T21). Es un ítem de seguimiento, no un faltante: ninguna bitácora de T01-T21 informa un faltante.
- "Revisar el ruido en el transportador de la estación 3 de montaje de Pickup; mantenimiento lo tiene anotado." (T03; también T06, T11, T12, T15). Precede a I07 (T17, mismo transportador, estación 3) pero no informa ninguna parada, así que no es causa de ningún caso antes de T17.
- "Confirmar con logística el horario del camión de Brasil." (T16; también T18, T19). Es una tarea sobre el horario de un camión, no una causa.

Personal (no es causa tal como está escrito):
- "Faltó un operario en carrocería y se cubrió con un polivalente." (T11; también T15). Una ausencia cubierta por un operario polivalente, sin impacto de `ausentismo` indicado.
- "Dos operarios nuevos en entrenamiento en calidad, acompañados por el referente." (T02; también T03, T05, T07, T09, T10, T13, T18)
- "Rotación habitual de puestos en montaje a mitad de turno." (T04; también T06, T12, T21)

Otro ruido:
- "A las 3:40 hubo un corte de energía de diez minutos en carrocería de SUV. Volvió sin consecuencias." (T18). Una parada de 10 minutos resuelta de inmediato, sin consecuencia indicada. Si existe un caso de SUV en `carroceria` en S036, esta es la única línea que podría vincularse; ver Puntos abiertos.
- "Mantenimiento preventivo de la cabina de pintura 1 según el programa, sin impacto en el ritmo." (T13; también T14). Planificado, sin impacto.
- "Logística avisó que el patio está al 70 % de su capacidad." (T02; también T08, T17, T20, T21)
- "Auditoría 5S en el sector de calidad, sin observaciones mayores." (T03; también T04, T05, T09). Contiene "Auditoría" pero no es una retención: no es `retencion_de_calidad`.
- "Se recibió el lote semanal de pintura base, sin observaciones." (T01; también T07, T15)
- "Se cambiaron las lámparas de inspección del túnel de calidad." (T06; también T16)
- "Limpieza de la fosa de pretratamiento al cierre, según el cronograma." (T18; también T19)
- "Reunión de arranque con los líderes de línea, sin temas fuera de lo habitual." (T10; también T11, T12)
- Líneas de producción como "Se liberaron 61 unidades de calidad, contra 72 del plan del turno." (T04). Indican una cantidad, no una causa; los datos deciden el gap.
- "Sin paradas ni faltantes de material." (T01; también T03, T06, T12, T14, T15, T16, T21). Indica que no hay causa, así que los casos de esos turnos no tienen causa declarada en esa bitácora.

## Intentos de inyección

No se encontró ninguno en T01-T21. Ninguna línea de bitácora se dirige al sistema ni le dice que ignore, marque, oculte o cambie algo ("ignorá", "marcá como", "no informes" y similares están ausentes). Las 21 bitácoras se leyeron completas.

## Puntos abiertos para el usuario

1. **I03 y criterio 5 (T07/T08).** **Decidido: Q-39 (el criterio 5 aplica, elevación S014, levantamiento S020).** El texto de T07 no nombra fecha de fin de la auditoría, lo que coincide literalmente con el criterio 5 ("la causa sigue activa y no tiene fecha de resolución"). "El auditor vuelve mañana a primera hora para terminar la revisión" de T08 es cuándo vuelve el auditor, no una fecha de resolución, así que no levanta la elevación; T10 (legible en S020) informa el fin y sí la levanta. Una elevación sola nunca abre un caso (Q-25): SUV × Europa se abre en S015 ya escalado (Q-08). Los ítems golden que existen solo por la elevación llevan `requires: [agent]` y `depends_on: ["Q-39"]`.
2. **I03 frente a I04 sobre el modelo SUV (Q-02).** **Decidido para el golden: modelo + etapa, acotado por el mercado nombrado; depends_on Q-02.** I03 se vincula con SUV × Europa en `calidad`, I04 con SUV × el mercado cuyo cuello de botella es `pintura` (SUV × Local en S017-S018). Un caso sin causa coincidente es `no_declarada`, con `etapa` según Q-17 y Q-32 (null cuando no hay cuello de botella). **Excepción decidida: Q-40.** Un caso solo por gap (sin cuello de botella) se vincula por modelo cuando los datos muestran que su faltante son las unidades que la bitácora nombra: SUV × Brasil (S019) toma I04, `retrabajo` / `pintura`, porque su faltante de 3 u son las 3 SUV × Brasil en Gris Grafito enviadas a repintado en S017.
3. **Categoría de I04.** `retrabajo` encaja (criterio 6: "Unidades que vuelven a una etapa anterior"). El texto también tiene un ángulo de calidad ("diferencia de tono con la muestra patrón"). Recomendación: `retrabajo`, etapa `pintura`. La `etapa_cuello` del caso sale de los datos y puede diferir.
4. **I06 no tiene causa indicada.** "Quedaron varias Sedán esperando al final de la línea de montaje" da un síntoma y ningún motivo. Recomendación: usar `no_declarada` con la etapa de los datos, nunca una conjetura (criterio 6), y marcar el ítem golden con `depends_on` con el Q-xx que se elija para esto. Si los datos no muestran un caso de Sedán en S026, quitar I06 del golden.
5. **Origen de la causa con incidentes superpuestos (Q-38).** Un caso de Sedán que se abre en T02 o T04 conserva su causa hasta que se resuelve, aunque la misma combinación vea después otra causa de bitácora (por ejemplo I06). Recomendación: el golden registra solo la causa de origen por caso, y las bitácoras posteriores no la cambian.
6. **I01 e I02 existen solo si se abre un caso.** Ambos se resuelven dentro de su propio turno. Si hay un caso de Sedán abierto en S004 o S008, la causa está declarada y el criterio 5 no aplica. Si existe un caso es una cuestión de datos para los archivos golden de day-01/day-02.
7. **Corte de energía de T18.** "A las 3:40 hubo un corte de energía de diez minutos en carrocería de SUV. Volvió sin consecuencias." podría leerse como una `parada_de_linea`, pero está resuelto y declarado sin consecuencias. Recomendación: no tratarlo como causa de ningún caso (figura en Distractores), salvo que un caso de SUV tenga cuello de botella en `carroceria` en S036.
8. **Momento del levantamiento de I07.** La resolución está en T19, legible en S038 (Q-01), aunque la línea volvió a las 10:00 de T19, antes del snapshot intermedio de T19 en S037. Recomendación: levantar en S038, nunca en S037. Además, el caso en sí se resuelve recién tras dos snapshots limpios (criterio 3), independientemente del levantamiento.
9. **Alcance de mercado de I07.** La bitácora no nombra mercado, así que Q-02 hace que la elevación cubra todos los mercados de Pickup. El golden debería listar los casos de Pickup activos en S034-S037 según los datos; no los calculé.
