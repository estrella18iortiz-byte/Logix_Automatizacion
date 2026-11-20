# Cambios al diseño · qué corregir en E1, E2, E3 y E4

Logix tuvo dos recortes de alcance. **El que vale es el segundo (versión 3.0, 19 nov 2026).**

| Versión | Fecha | Alcance |
|---|---|---|
| 1.0 | hasta el 17 nov | De la **requisición** (con 10 firmas) al pago |
| 2.0 | 18 nov | De la compra aprobada al pago; comunicación de ida y vuelta Adquisiciones ⇄ Finanzas; Logix **no** pagaba |
| **3.0** | **19 nov** | **Diagrama de Angela del 19-nov-2026:** tareas repetitivas con **proveedores fijos y avalados**; espera del material (7 días), factura validada antes de pagar, **pago automático con banco emulado**, cancelación con aviso por correo y Telegram |

**Por qué el cambio a 3.0:** el flujo 2.0 no convencía a Angela. Ella dibujó el proceso que de verdad quiere automatizar (`Documentos/diagrama 19-nov-26.drawio.png`). Se revisó con Claude y se le agregaron tres cosas que faltaban para que fuera automatizable:
1. **Validar la factura antes de pagar** (si no es válida, se cancela la compra y se devuelve el material).
2. **Rama del «no» del banco** (qué pasa con cada tipo de error).
3. **Qué pasa al cancelar** cuando el material ya está en almacén (se devuelve y se avisa a todos).

Además Angela definió: material máximo **1 semana**, recordatorio el **día 3**, aviso **5 h antes** de cancelar, confirmación del **Jefe de Almacén** con botón de **Devolución** y razón obligatoria, **pago automático**, y aviso a **Adquisiciones** en pagos y cancelaciones.

Diagramas nuevos para pegar en los documentos: `diagramas/01_flujo_proceso.png`, `02_estados_oc.png`, `03_modelo_datos.png` (los `.drawio` se editan en draw.io).

---

## 1. Antes (2.0) y ahora (3.0)

| | 2.0 (18 nov) | **3.0 (19 nov)** |
|---|---|---|
| Proveedores | Catálogo con revisión de la lista 69-B | **Fijos y ya avalados** (sin 69-B); cada uno con su **CLABE** |
| Orden de los pasos | factura → almacén → Finanzas | **material (7 días) → factura (48 h) → Finanzas → banco** (la factura puede llegar antes) |
| Almacén | «Llegó completo» / «Reportar problema» (no cancelaba) | **Jefe de Almacén**: «Llegó bien» / **«Devolución» con razón → cancela** |
| Plazos | Recordatorios a Finanzas (48 h) y Adquisiciones (24 h) | **Material:** día 3 recordatorio, 5 h antes último aviso, día 7 cancela · **Factura:** 48 h o cancela |
| Factura no válida | Se rechazaba y el proveedor podía corregir | **Se cancela la compra** y se devuelve el material (si ya llegó) |
| Finanzas | Devolver / reenviar / programar fecha / registrar pago | **Recibe el expediente; el pago sale solo.** Solo interviene si el banco falla: reintentar, cancelar o corregir CLABE |
| Pago | Fuera de Logix (conciliación de un archivo del banco) | **Automático con el banco emulado** y su respuesta |
| Semáforo del 15 de diciembre | Sí (R6) | **Se quitó** (no está en el diagrama) |
| Robots | 8 | **7** (ver tabla) |
| Tablas | 14 | **14** (sin `sat_lista_69b` ni `excepciones`; nuevas `banco_cuenta` y `banco_movimientos`; columnas de cancelación en `ordenes_compra`; `pagos` guarda la respuesta del banco) |
| Estados de la OC | ESPERANDO_FACTURA, FACTURA_VALIDADA, EN_FINANZAS, DEVUELTA, PAGADA, DETENIDA | **ESPERANDO_MATERIAL, MATERIAL_RECIBIDO, EN_FINANZAS, PAGO_CON_ERROR, PAGADA, CANCELADA** |
| Pruebas de punta a punta | 19 casos | **22 casos** (todas las ramas del diagrama) |

### Robots (numeración 3.0)
| Robot | Qué hace | En 2.0 era |
|---|---|---|
| R1 · Envío de la OC | PDF 001-05 con QR al proveedor por correo y Telegram, con el plazo de 7 días | R1 |
| R2 · Validador de facturas | 7 reglas (sin 69-B); **si no es válida, cancela la compra** | R2 |
| R3 · Vigilante de plazos | día 3 · 5 h antes · día 7 · 48 h de factura | **nuevo** (reemplaza R4 recordatorios y R6 semáforo) |
| R4 · Expediente a Finanzas | PDF con SHA-256 cuando ya hay factura válida **y** material | R3 |
| R5 · Pago automático (banco emulado) | Transferencia y respuesta a cada error | **nuevo** (reemplaza R5 conciliación y el pago manual) |
| R6 · Notificador | correo y Telegram con 3 reintentos | R7 |
| R7 · Bot de Telegram | vinculación, folios y facturas XML | R8 |

---

## 2. Qué corregir en cada entrega

### E1 (diagnóstico)
- **Alcance:** «compras repetitivas con proveedores fijos ya avalados, desde que la petición está aceptada y validada hasta que el banco confirma el pago al proveedor».
- **Supuestos:** banco emulado; proveedores fijos; la confirmación para comprar ya se validó.
- **Fuera de alcance:** requisición, firmas, selección y evaluación de proveedores, banca real.
- **Problema:** tareas repetitivas que hoy se hacen a mano: recordar al proveedor, revisar facturas, juntar el expediente, pagar y avisar a todos.

### E2 (requerimientos / diseño)
- **RF nuevos:**
  - RF-01 Registrar la compra aprobada y enviar la OC en PDF al proveedor (correo y Telegram).
  - RF-02 Vigilar el plazo del material: recordatorio el día 3, aviso 5 h antes del día 7, cancelación el día 7.
  - RF-03 El Jefe de Almacén confirma el material o hace la devolución con razón obligatoria.
  - RF-04 Pedir la factura al proveedor y cancelar si no llega en 48 h.
  - RF-05 Validar la factura antes de pagar; si no es válida, cancelar la compra y devolver el material.
  - RF-06 Enviar el expediente a Recursos Financieros cuando hay factura válida y material confirmado.
  - RF-07 Pagar en automático con el banco emulado y avisar el resultado al proveedor, a Adquisiciones y a Finanzas.
  - RF-08 Ante un error del banco: reintento automático (error general, 3 veces), y si no, Finanzas reintenta o cancela con motivo.
  - RF-09 Avisar cada cancelación con su razón al proveedor y a Adquisiciones por correo y Telegram.
  - RF-10 Consultar el estado de una compra por folio (panel y Telegram).
- **Actores:** Adquisiciones, Jefe de Almacén, Recursos Financieros, Proveedor, Banco (emulado), Administrador.
- **Diagrama de flujo / BPMN TO-BE:** usar `diagramas/01_flujo_proceso.png` (basado en el tuyo).

### E3 (arquitectura / base de datos)
- **Modelo de datos:** `diagramas/03_modelo_datos.png` y `sql/01_esquema.sql` (14 tablas).
- **Estados de la OC:** `diagramas/02_estados_oc.png`.
- **Componente nuevo:** banco emulado (`logix/banco_emulado.py`). Valida la CLABE con el dígito verificador oficial, el saldo, el límite por operación, la moneda (MXN) y los duplicados. Tiene una «falla simulada» para la demostración.
- Se mantiene: Python en lugar de n8n, **Telegram** en lugar de WhatsApp, **SQL Server 2025**.

### E4 (pruebas)
- Usar `resultados/resultados_pruebas.csv` (22 casos, 22 aprobados) y las capturas de `evidencias/`.

| Criterio | Casos |
|---|---|
| CA-03 Registro de la compra y envío de la OC | CP-02, CP-03 |
| CA-05 Jefe de Almacén (llegó bien / devolución) | CP-07, CP-08 |
| CA-07 Expediente y pago automático | CP-11 |
| CA-08 Factura (48 h, inválida, llega antes del material) | CP-09, CP-10, CP-12 |
| CA-10 Respuestas del banco | CP-13 (error general), CP-14 (saldo), CP-15 (CLABE), CP-16 (divisa), CP-17 (monto), CP-18 (duplicado) |
| CA-12 Seguimiento y avisos | CP-19, CP-21 |
| CA-14 Plazos del material | CP-04 (día 3), CP-05 (5 h antes), CP-06 (día 7) |
| CA-15 Inicio de sesión | CP-01 |
| CA-16 Bitácora inmutable | CP-20 |
| RNF-02 Rendimiento | CP-22 |

- Métricas (admin › Indicadores): compras pagadas y canceladas, % canceladas, cancelaciones por causa, facturas rechazadas, respuestas de error del banco, segundos de Finanzas al pago, horas hasta el material y hojas impresas.
- **SUS:** las tareas 3 y 4 cambiaron (confirmar como Jefe de Almacén y hacer una devolución). Ya están actualizadas en `docs/Encuesta_SUS_Logix.docx` y `docs/encuesta_SUS.md`.

### Libro final
- Sección «Cambios al diseño»: 1.0 → 2.0 → 3.0, por qué cada uno y qué se ganó (un flujo más corto, totalmente automático y con pago).
- **Declaración de IA:** el análisis del diagrama, el rediseño del código, los diagramas, las pruebas y las evidencias de la versión 3.0 se hicieron con apoyo de Claude (ver `memoria_claude/bitacora_sesiones.md`, sesión 4). Angela definió las reglas del proceso, revisó los resultados y los puede explicar.
