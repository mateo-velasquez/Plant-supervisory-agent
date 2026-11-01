# Reglas de criticidad y criterio de seguimiento

Planta Las Acacias · Área de Control de Producción

Este documento dice cómo se mide un desvío y qué se hace con él. Los números están en `umbrales.yaml`; acá está cómo se aplican y lo que no es un número.

## 1. Qué se mide

**Avance.** Una unidad avanza cuando sale de calidad y entra a patio. Cada snapshot trae en `liberadas` las unidades que salieron de calidad desde el snapshot anterior. El avance real de una combinación modelo × mercado es la suma de sus liberadas desde el primer snapshot de la serie; una unidad que aparece dos veces se cuenta una.

**Plan acumulado.** El plan de producción da las unidades por turno. Dentro del turno el plan se reparte parejo: en el snapshot de mitad de turno corresponde la mitad del plan de ese turno, y en el de cierre, el turno entero.

**Gap.** Avance real menos plan acumulado. Negativo es atraso. Se expresa en unidades y como porcentaje del plan diario de la combinación (el plan del turno por tres).

**Retraso en días.** Se proyecta para cada unidad que todavía no llegó a patio:

- la hora proyectada de llegada a patio es la hora del snapshot, más lo que le falta del tiempo estándar de la etapa en la que está (cero si ya lo superó), más el tiempo estándar de las etapas que le quedan hasta salir de calidad;
- una unidad en pintura con `retrabajos` mayor que cero está en repintado y su tiempo estándar es el de retrabajo;
- el embarque alcanzable es el primero de su mercado cuyo corte en patio es posterior a la hora proyectada;
- el retraso es la diferencia en días entre la salida de ese embarque y la del embarque asignado.

El retraso de la combinación es el de su unidad más atrasada. Las unidades que ya están en patio o en despacho no entran en la cuenta: su embarque ya está definido.

Un camión a Brasil sale todos los días; perderlo es un día de retraso. El buque a Europa sale los jueves; perderlo es una semana.

**Etapa cuello.** La etapa donde la combinación tiene más unidades demoradas: las que llevan en la etapa más que el tiempo estándar más la tolerancia, y las que están en repintado.

## 2. Severidad mínima

Cada combinación tiene una severidad por gap y otra por retraso, según los umbrales. La severidad mínima es la mayor de las dos. Hay desvío cuando la severidad mínima es media o más.

La severidad mínima es un piso. El agente la puede subir cuando tiene una razón concreta (sección 5); no la puede bajar.

## 3. El ciclo de un caso

- Un caso se abre cuando una combinación sin caso activo tiene desvío. Hay a lo sumo un caso activo por combinación.
- En el snapshot en que se abre está `abierto`. Desde el siguiente pasa a `en_seguimiento`.
- Pasa a `escalado` cuando su severidad llega a crítica, por umbral o porque el agente la subió. Sigue escalado hasta que se resuelve, aunque la severidad baje.
- Se da por `resuelto` cuando la combinación pasa dos snapshots consecutivos sin desvío y no hay una severidad subida por el agente vigente. Si después vuelve a haber desvío, es un caso nuevo.

## 4. Qué se avisa y cuándo

**Alerta inmediata.** Sale en el mismo snapshot en que un caso pasa a `escalado`. Es una por caso: un caso que ya está escalado no vuelve a alertar.

**Informe de cierre de turno.** Sale en el snapshot de cierre de cada turno. Tiene dos partes:

- *Novedades:* cada caso cuyo estado o severidad cambió desde el último informe en el que apareció, los casos nuevos, los resueltos en el turno y los que tuvieron en el turno una severidad más alta que la que tienen al cierre. Para esta comparación, `abierto` y `en_seguimiento` cuentan como el mismo estado.
- *Casos activos:* la tabla de todos los casos activos al cierre, con gap, retraso, severidad, estado y etapa cuello.

Cada caso del informe lleva su severidad actual y la máxima que tuvo desde el informe anterior. La máxima sirve para que no se pierda un pico que subió y bajó entre dos cierres.

**Sin aviso.** Si un caso no cambió desde el último informe, no se lo vuelve a nombrar como novedad. Repetir lo que ya se dijo es ruido.

Un snapshot que llega dos veces se procesa una sola vez.

## 5. Cuándo subir la severidad

El agente sube a crítica un caso activo, aunque los umbrales no lo marquen, cuando la bitácora dice que **la causa sigue activa y no tiene fecha de resolución**: una línea parada sin fecha de vuelta, un proveedor sin fecha de entrega. La subida vale para todos los casos activos que tienen esa causa, y para los que se abran mientras siga vigente.

La subida deja de valer cuando una bitácora posterior informa que la causa se resolvió. Desde ahí rige otra vez la severidad mínima.

Si la bitácora da una fecha concreta de resolución, o dice que el problema ya se resolvió, no se sube: alcanza con los umbrales.

## 6. La causa

La causa de un caso tiene una categoría y una etapa:

| Categoría | Cuándo |
|---|---|
| `parada_de_linea` | Una línea o estación detenida |
| `faltante_de_piezas` | Falta un material o componente |
| `retrabajo` | Unidades que vuelven a una etapa anterior |
| `retencion_de_calidad` | Calidad o una auditoría retiene unidades terminadas |
| `ausentismo` | Falta de personal |
| `no_declarada` | Los datos muestran el cuello, pero ninguna bitácora dice por qué |

La causa sale de la bitácora y se cita el fragmento. Si ninguna bitácora la nombra, la categoría es `no_declarada` y la etapa es la que muestran los datos. No se completa con una suposición.
