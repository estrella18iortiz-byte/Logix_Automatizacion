# Cambios al diseño · qué corregir en E1, E2, E3 y E4

**Fecha del cambio:** 18 nov 2026.
**Por qué:** en la revisión le dijeron a Angela que la requisición y sus 4 firmas (pasos 1 y 2 del recorrido) eran demasiado complicadas: implican abastecer a todo el Tecnológico. Se decidió que Logix empiece **cuando la compra ya está aprobada y comprada**. Lo difícil, y lo que se automatiza, es la **comunicación entre Adquisiciones y Recursos Financieros**: mover la orden de compra al proveedor, la factura y la confirmación de almacén hasta Finanzas, y de regreso las devoluciones, la fecha de pago y el pago.

---

## 1. Antes y después

| | Versión anterior | Versión actual |
|---|---|---|
| Alcance | De la **requisición** al pago al proveedor | De la **compra ya aprobada** al pago al proveedor |
| Empieza con | El área captura una requisición | Adquisiciones registra la orden de compra ya autorizada |
| Firmas | 4 de requisición + 3 de OC + 3 de pago (10 en total) | **Ninguna dentro de Logix** (la autorización ya pasó antes) |
| Roles | 11 (solicitante, jefe de área, presupuestos, subdirector, director, adquisiciones, jefe RM, subdir. admin., almacén, finanzas, admin) | **4**: adquisiciones, almacén, finanzas, admin (+ proveedor por Telegram/correo) |
| Confirmación del material | Almacén recibe + el área firma de recibido y califica | **Solo Almacén**: «Llegó completo» o «Reportar problema» |
| Comunicación con Finanzas | Solo de ida (expediente) y «Devolver» | **De ida y vuelta**: expediente → devolución con motivo → reenvío con respuesta → fecha programada → pago (con avisos en cada paso) |
| Robots | 10 (R1 requisición … R10 conciliación) | **8** (ver tabla abajo) |
| Tablas | 20 | 14 (se quitaron partidas, conceptos, requisiciones, requisicion_detalle, oc_requisiciones, flujos_aprobacion, aprobaciones; se agregó oc_detalle) |
| Fecha límite de pagos | 11 de diciembre (supuesto) | **15 de diciembre** (confirmado con la Jefa de Adquisiciones: «a mediados de diciembre, 15 o 16») |
| Pruebas de punta a punta | 24 casos | 19 casos (CP-01 a CP-18 + CP-13b) |

### Robots nuevos (numeración actual)
| Nuevo | Qué hace | Antes era |
|---|---|---|
| R1 · Envío de la OC al proveedor | Folio, PDF 001-05 con QR, envío con instrucciones para facturar | parte de R9 |
| R2 · Lector de facturas CFDI | Igual que antes (8 reglas) | R3 |
| R3 · Expediente a Finanzas | OC + factura + entrada de almacén → PDF con SHA-256 → Finanzas | R4 |
| R4 · Comunicación Adquisiciones ⇄ Finanzas | Avisos de devolución, reenvío, fecha y pago; recordatorios de 48 h y 24 h | nuevo (reemplaza a R2, el de las firmas) |
| R5 · Conciliación bancaria | Igual que antes | R10 |
| R6 · Vigilante del cierre | Igual, con fecha 15 de diciembre | R6 |
| R7 · Notificador | Igual | R5 |
| R8 · Bot de Telegram | Igual (ya no hay folios REQ) | R7 |
| — | Se quitaron: R1 requisición inteligente, R2 enrutador de firmas, R8 proveedor apto | — |

---

## 2. Qué corregir en cada entrega

### E1 (diagnóstico)
- Cambiar el **alcance** a «desde que la compra está aprobada hasta el pago al proveedor».
- En el problema, destacar lo que dijo la entrevista sobre **mover el expediente y la comunicación con Recursos Financieros** (carpetas a mano, no saber si ya se pagó, devoluciones sin explicar).
- Quitar del alcance la requisición, las firmas y la selección de proveedor. Mencionarlas como «fuera de alcance: pasan antes de Logix».

### E2 (requerimientos / diseño)
- **Requerimientos funcionales:** quitar los de requisición, firmas y dictamen de proveedor. Agregar:
  - RF: registrar compra aprobada y enviar la OC al proveedor.
  - RF: Almacén confirma el material o reporta un problema.
  - RF: Finanzas devuelve el expediente con motivo; Adquisiciones lo reenvía con respuesta.
  - RF: Finanzas programa la fecha de pago y Logix avisa a Adquisiciones y al proveedor.
  - RF: recordatorios automáticos por expedientes detenidos.
- **Actores / casos de uso:** solo Adquisiciones, Almacén, Recursos Financieros, Proveedor y Administrador.
- **BPMN TO-BE:** redibujar con 4 carriles (Adquisiciones, Proveedor, Almacén, Recursos Financieros), como el diagrama del README.

### E3 (arquitectura / base de datos)
- **Modelo de datos:** 14 tablas (ver `sql/01_esquema.sql`). Quitar las 7 tablas de requisición y firmas; agregar `oc_detalle`.
- **Estados de la OC:** ESPERANDO_FACTURA → FACTURA_VALIDADA → EN_FINANZAS → PAGADA (y DEVUELTA / DETENIDA fuera del camino normal).
- Mantener lo que ya se había anotado: Python en lugar de n8n, **Telegram** en lugar de WhatsApp, **SQL Server 2025**.

### E4 (pruebas)
- Usar `resultados/resultados_pruebas.csv` (19 casos, 19 aprobados).
- Criterios de aceptación usados en las pruebas:

| Criterio | Casos |
|---|---|
| CA-03 Registro de la compra y envío de la OC | CP-02, CP-03 |
| CA-05 Recepción en almacén | CP-05, CP-07 |
| CA-06 Expediente completo a Finanzas | CP-08 |
| CA-07 Comunicación Adquisiciones ⇄ Finanzas | CP-09, CP-10, CP-11 |
| CA-08 Validación de la factura | CP-04, CP-06 |
| CA-10 Conciliación del pago | CP-13, CP-13b |
| CA-12 Seguimiento y avisos | CP-14, CP-17 |
| CA-14 Recordatorios y semáforo | CP-12, CP-15 |
| CA-15 Inicio de sesión | CP-01 |
| CA-16 Bitácora inmutable | CP-16 |
| RNF-02 Rendimiento | CP-18 |

- Métricas nuevas en el panel (admin › Indicadores): minutos de almacén a Finanzas, horas en Finanzas hasta el pago, devoluciones de Finanzas, % de órdenes con excepción y hojas impresas.

### Libro final
- Explicar este cambio en una sección «Cambios al diseño»: qué se recortó, por qué (comentario del docente) y qué se ganó (un flujo más corto y enfocado).
- **Declaración de IA:** el rediseño del código y de este documento se hizo con apoyo de Claude (ver `memoria_claude/bitacora_sesiones.md`, sesión 2). Angela lo revisó, corrió las pruebas y lo puede explicar.
