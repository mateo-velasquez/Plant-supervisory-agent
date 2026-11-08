# Incident catalog, days 1-7 (T01-T21)

Source: logbooks `T01`-`T21` only (shifts T01-T21, snapshots S001-S042). Days 8-10 were not read. This is a log-side catalog: it says what each logbook states. Whether a case exists, and when it opens or escalates, comes from the data and is decided in the `day_XX.yaml` files. Not parsed by code.

## Golden authoring notes

- Quote every `justification` in the YAML: rule section (`criterio.md` §n), the numbers, and for causes the verbatim logbook fragment with its logbook id.
- Use `requires: [agent]` for every item that only exists because of the agent: §5 raises, their effects (alerts and news caused by a raise, and the lift) and declared causes. Threshold-only items carry no `requires`.
- Use `depends_on` for tracking only (open question the item rests on); it never excludes the item from gating.
- A cause keeps its origin until the case resolves (Q-38): a later logbook does not rewrite the cause of an open case.
- A logbook `Txx` is readable only at its shift's closing snapshot (Q-01), never at the mid snapshot. Shift to closing snapshot comes from `turnos.csv` (T01 -> S002, T02 -> S004, ... T21 -> S042).
- Linking a logbook cause to a case uses the stage and/or model named in the logbook (Q-02): a Pickup assembly stop applies to every Pickup market.
- Every quote below is copied verbatim from a single logbook line, so it can be checked with a literal search.

Summary: 7 incidents (I01-I07). §5 applies to one (I07), with open points on I03 and I06.

## Incidents

### I01 Sedán assembly stop, resolved in the same shift

| Field | Value |
|---|---|
| Shift(s) | T02 (Monday 2 March 2026, tarde, 14:00-22:00) |
| Category | `parada_de_linea` |
| Stage | `montaje` |
| Model / market | Sedán, market not stated |
| Start quote | "A las 17:20 se paró la línea de montaje de Sedán por una falla en la atornilladora de la estación 14." (T02) |
| Resolution quote | "Mantenimiento la cambió y la línea volvió a las 18:00." (T02); also "El ritmo se recuperó antes del final del turno." (T02) |
| §5 applies? | No. The same line says the problem was fixed: "la línea volvió a las 18:00". |
| Readable at | S004 |

### I02 Sedán harness shortage (supplier truck late)

| Field | Value |
|---|---|
| Shift(s) | T04 (Tuesday 3 March, mañana); recovery effect in T05 |
| Category | `faltante_de_piezas` |
| Stage | `montaje` |
| Model / market | Sedán, market not stated |
| Start quote | "Desde las 7:30 no entraron arneses eléctricos para Sedán: el camión del proveedor llegó recién a las 13:00." (T04) |
| Resolution quote | "La línea de montaje de Sedán quedó frenada hasta las 13:30 y retomó cuando se descargó el material." (T04); "Compras habló con el proveedor y para mañana el abastecimiento está confirmado en el horario habitual." (T04) |
| §5 applies? | No. The material arrived and the line resumed ("retomó cuando se descargó el material"), and the supply for the next day has a confirmed date ("para mañana el abastecimiento está confirmado"). |
| Readable at | S008 |

Effect line, not a new cause: "La línea de Sedán trabajó todo el turno a ritmo máximo para recuperar lo que quedó atrás a la mañana." (T05, readable at S010).

### I03 Homologation audit holding SUV for Europe

| Field | Value |
|---|---|
| Shift(s) | T07 (Wednesday 4 March, mañana) to T10 (Thursday 5 March, mañana); also T08, T09 |
| Category | `retencion_de_calidad` |
| Stage | `calidad` |
| Model / market | SUV, Europa ("las SUV de exportación", "las SUV para Europa") |
| Start quote | "A media mañana llegó la auditoría de homologación para Europa y retuvo en calidad las SUV de exportación que pasaban por la estación final." (T07) |
| Continuation quotes | "La auditoría de homologación sigue revisando las SUV para Europa." (T08); "El auditor vuelve mañana a primera hora para terminar la revisión." (T08) |
| Effect quote | "Las retenidas no van a estar en patio para el traslado al puerto de las 20:00, así que pierden el buque de este jueves." (T08) |
| Resolution quote | "La auditoría de homologación terminó a las 8:30 y se liberaron las SUV para Europa que estaban retenidas." (T10); "Salen en el buque del jueves 12." (T10) |
| §5 applies? | Open (Q-pending, see Open points). At T07 the logbook gives no end date for the audit. At T08 it says "El auditor vuelve mañana a primera hora para terminar la revisión", which is a return date for the auditor but not a committed release date. |
| Readable at | S014 (T07), S016 (T08), S020 (T10 resolution) |

### I04 Gris Grafito paint mismatch, SUV sent to repaint

| Field | Value |
|---|---|
| Shift(s) | T09 (night of Wednesday 4 to Thursday 5 March) to T10 |
| Category | `retrabajo` |
| Stage | `pintura` (units go back to the repaint booth) |
| Model / market | SUV in Gris Grafito, market not stated |
| Start quote | "A las 2:00 se separaron las carrocerías de SUV en Gris Grafito que habían salido de pintura desde la tarde, por diferencia de tono con la muestra patrón." (T09) |
| Time estimate | "Vuelven a la cabina de repintado; se estiman seis horas por unidad." (T09) |
| Resolution quote | "Calidad de pintura ajustó la mezcla del Gris Grafito y las unidades nuevas salen bien." (T09); "Las SUV en Gris Grafito repintadas empezaron a volver a la línea de montaje." (T10) |
| §5 applies? | No. The logbook says the cause was corrected ("ajustó la mezcla ... las unidades nuevas salen bien") and gives a time per unit ("se estiman seis horas por unidad"), so it is not an open-ended cause without a date. |
| Readable at | S018 (T09), S020 (T10) |

Overlaps in time with I03 on the SUV model (I03 holds SUV for Europa in `calidad`, I04 sends SUV to `pintura`). Which one links to a case depends on the case's bottleneck stage and market (Q-02); see Open points.

### I05 Pickup Local torque control hold

| Field | Value |
|---|---|
| Shift(s) | T11 (Thursday 5 March, tarde) |
| Category | `retencion_de_calidad` |
| Stage | `calidad` |
| Model / market | Pickup, Local |
| Start quote | "Desde el mediodía, calidad retuvo las pickups para el mercado local por un control de torque en las ruedas." (T11) |
| Resolution quote | "Se revisaron una por una y se liberaron sin novedad cerca de las 19:00." (T11) |
| §5 applies? | No. The same entry says the units were released: "se liberaron sin novedad cerca de las 19:00". |
| Readable at | S022 |

### I06 Sedán units waiting at the end of assembly, no cause given

| Field | Value |
|---|---|
| Shift(s) | T13 (Friday 6 March, mañana) |
| Category | `no_declarada` if a Sedán case is linked to it (no cause is named) |
| Stage | "none named" (the text says "al final de la línea de montaje"; no stage is named as the cause) |
| Model / market | Sedán, market not stated |
| Start quote | "Quedaron varias Sedán esperando al final de la línea de montaje." (T13) |
| Resolution quote | none. "Logística lo está viendo." (T13) is not a resolution; T14 says "Sin paradas ni faltantes de material." (T14) |
| §5 applies? | No. No cause is stated, so there is no "causa sigue activa y no tiene fecha de resolución" to quote. |
| Readable at | S026 |

### I07 Pickup assembly stop, overhead conveyor broken (section 5 raise)

| Field | Value |
|---|---|
| Shift(s) | T17 (Saturday 7 March, tarde) to T19 (Sunday 8 March, mañana); T18 in between |
| Category | `parada_de_linea` |
| Stage | `montaje` |
| Model / market | Pickup, every market (Q-02: model + stage; logbook names no market) |
| Start quote | "A las 15:00 se paró la línea de montaje de Pickup por la rotura del transportador aéreo de la estación 3." (T17) |
| No-date quotes | "Mantenimiento espera el repuesto y por ahora no hay fecha confirmada de vuelta." (T17); "La línea de montaje de Pickup sigue parada." (T18); "El repuesto del transportador viene desde la casa matriz y todavía no tiene horario de llegada." (T18) |
| Effect quote | "Carrocería y pintura de Pickup siguen trabajando y las unidades se acumulan antes de montaje." (T17) |
| Resolution quote | "El repuesto del transportador llegó a las 7:30 y la línea de montaje de Pickup volvió a las 10:00." (T19) |
| §5 applies? | Yes, from T17. "por ahora no hay fecha confirmada de vuelta" is a line stopped without a return date, and T18 repeats "todavía no tiene horario de llegada". The raise is `requires: [agent]`, applies to every active Pickup case with this cause and to cases opened while it stays in force. |
| Raise decided at | S034 (T17 readable). T18 (S036) confirms it still holds. |
| Lift | T19 reports the resolution, readable at S038. The raise is lifted at S038 (Q-11) and the minimum severity applies again from there. |
| Readable at | S034, S036, S038 |

Recovery lines after the lift (not a new cause, and they do not resolve the case by themselves; lifecycle resolution follows §3): "Desde ahí trabaja a ritmo máximo para bajar lo acumulado." (T19); "Montaje de Pickup sigue a ritmo máximo; el acumulado antes de la línea bajó a la mitad." (T20).

## Distractors

Lines that look like causes or tasks but do not declare a cause for a case.

Safety:
- "Se reportó un casi accidente en el pasillo del patio: un autoelevador giró sin tocar bocina. Se habló con el operador." (T04; the same line also appears in T07, T08, T10, T12, T13)
- "Se repuso un extintor vencido en la cabina de pintura 2." (T11; also T14, T16, T17, T19)
- "Se reforzó el uso de protección auditiva en carrocería." (T05; also T18)
- "Charla de seguridad de cinco minutos al inicio, sobre manejo de cargas." (T01; also T02, T09, T20)

Pending tasks:
- "Seguir el consumo de sellador en carrocería; quedó justo para el próximo turno." (T02; also T04, T07, T09, T17, T21). This is a watch item, not a shortage: no shortage is reported in any logbook T01-T21.
- "Revisar el ruido en el transportador de la estación 3 de montaje de Pickup; mantenimiento lo tiene anotado." (T03; also T06, T11, T12, T15). It precedes I07 (T17, same conveyor, station 3) but reports no stop, so it is not a cause of any case before T17.
- "Confirmar con logística el horario del camión de Brasil." (T16; also T18, T19). A task about truck timing, not a cause.

Personnel (not a cause as written):
- "Faltó un operario en carrocería y se cubrió con un polivalente." (T11; also T15). One absence covered by a polyvalent operator, no `ausentismo` impact stated.
- "Dos operarios nuevos en entrenamiento en calidad, acompañados por el referente." (T02; also T03, T05, T07, T09, T10, T13, T18)
- "Rotación habitual de puestos en montaje a mitad de turno." (T04; also T06, T12, T21)

Other noise:
- "A las 3:40 hubo un corte de energía de diez minutos en carrocería de SUV. Volvió sin consecuencias." (T18). A 10-minute stop resolved at once, with no consequence stated. If a SUV `carroceria` case exists at S036, this is the only line that could be matched; see Open points.
- "Mantenimiento preventivo de la cabina de pintura 1 según el programa, sin impacto en el ritmo." (T13; also T14). Planned, no impact.
- "Logística avisó que el patio está al 70 % de su capacidad." (T02; also T08, T17, T20, T21)
- "Auditoría 5S en el sector de calidad, sin observaciones mayores." (T03; also T04, T05, T09). It contains "Auditoría" but it is not a retention: it is not `retencion_de_calidad`.
- "Se recibió el lote semanal de pintura base, sin observaciones." (T01; also T07, T15)
- "Se cambiaron las lámparas de inspección del túnel de calidad." (T06; also T16)
- "Limpieza de la fosa de pretratamiento al cierre, según el cronograma." (T18; also T19)
- "Reunión de arranque con los líderes de línea, sin temas fuera de lo habitual." (T10; also T11, T12)
- Production lines such as "Se liberaron 61 unidades de calidad, contra 72 del plan del turno." (T04). They state a count, not a cause; the data decides the gap.
- "Sin paradas ni faltantes de material." (T01; also T03, T06, T12, T14, T15, T16, T21). It states there is no cause, so cases in those shifts have no declared cause from that logbook.

## Injection attempts

none found in T01-T21. No logbook line addresses the system or tells it to ignore, mark, hide or change anything ("ignorá", "marcá como", "no informes" and similar are absent). All 21 logbooks were read in full.

## Open points for the user

1. **I03 and §5 (T07/T08).** The T07 text names no end date for the audit, which literally matches §5 ("la causa sigue activa y no tiene fecha de resolución"), but an audit of this kind with a next-morning return ("El auditor vuelve mañana a primera hora para terminar la revisión", T08) reads like a date. Recommendation: treat §5 as not applying to I03, because the cause is a time-limited external review, the retained units are released within a day, and the golden should not depend on the agent reading intent. Alternative: mark the T07 raise as `requires: [agent]` and lift at S020. Needs your decision. If a raise is wanted, T08 does not lift it (not a resolution) and T10 (S020) does.
2. **I03 versus I04 on the SUV model (Q-02).** Both name SUV in T07-T10. Linking by model only would attach both causes to any SUV case, whereas stage matching separates them: `calidad` for I03 (Europa) and `pintura` for I04. Recommendation: match on stage first, then model, and use the market from I03 ("Europa") to keep I03 away from SUV Local and SUV Brasil cases. Confirm that this is the intended reading of Q-02.
3. **I04 category.** `retrabajo` fits (§6: "Unidades que vuelven a una etapa anterior"). The text also has a quality angle ("diferencia de tono con la muestra patrón"). Recommendation: `retrabajo`, stage `pintura`. The case's `etapa_cuello` comes from the data and may differ.
4. **I06 has no stated cause.** "Quedaron varias Sedán esperando al final de la línea de montaje" gives a symptom and no reason. Recommendation: use `no_declarada` with the stage from the data, never a guess (§6), and mark the golden item `depends_on` with the Q-xx you choose for this. If the data show no Sedán case at S026, drop I06 from the golden.
5. **Cause origin across overlapping incidents (Q-38).** A Sedán case that opens in T02 or T04 keeps its cause until the case resolves, even if the same combination later sees a different logbook cause (for example I06). Recommendation: the golden records only the origin cause per case, and later logbooks do not change it.
6. **I01 and I02 exist only if a case opens.** Both are resolved within their own shift. If a Sedán case is open at S004 or S008, the cause is declared and §5 does not apply. Whether a case exists is a data question for the day-01/day-02 golden files.
7. **T18 power cut.** "A las 3:40 hubo un corte de energía de diez minutos en carrocería de SUV. Volvió sin consecuencias." could be read as a `parada_de_linea`, but it is resolved and stated as without consequence. Recommendation: do not treat it as a cause for any case (listed under Distractors), unless a SUV case is bottlenecked at `carroceria` at S036.
8. **I07 lift timing.** The resolution is in T19, readable at S038 (Q-01), although the line returned at 10:00 of T19, before the T19 mid snapshot at S037. Recommendation: lift at S038, never S037. Also note that the case itself resolves only after two clean snapshots (§3), independent of the lift.
9. **I07 market scope.** The logbook names no market, so Q-02 makes the raise cover every Pickup market. The golden should list the Pickup cases active at S034-S037 by data; I did not compute them.
