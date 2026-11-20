# Evidencias · Logix 3.0 (diagrama del 19-nov-2026)

Generadas el 19/11/2026 22:25 con `python capturar_evidencias.py` (datos simulados).

## 01_inicio_de_sesion.png
Pantalla de inicio de sesión (contraseña de prueba logix2026).

![01_inicio_de_sesion.png](01_inicio_de_sesion.png)


## 02_adquisiciones_inicio.png
Inicio de Adquisiciones: tarjetas por etapa y plazo del material (R3).

![02_adquisiciones_inicio.png](02_adquisiciones_inicio.png)


## 03_registrar_compra.png
Adquisiciones captura la compra ya aprobada con un proveedor fijo.

![03_registrar_compra.png](03_registrar_compra.png)


## 04_compra_registrada_OC_enviada.png
R1 generó la OC-2026-0007 en PDF con QR y la mandó al proveedor por correo y Telegram.

![04_compra_registrada_OC_enviada.png](04_compra_registrada_OC_enviada.png)

> Logix: Compra registrada con el folio OC-2026-0007. Logix generó la orden de compra en PDF y ya se la mandó al proveedor por correo y Telegram.
>

## 05_almacen_plazos_7_dias.png
Jefe de Almacén: órdenes esperando material con semáforo del plazo de 7 días (rojo = vence pronto).

![05_almacen_plazos_7_dias.png](05_almacen_plazos_7_dias.png)


## 06_almacen_devolucion_con_razon.png
Devolución: el jefe escribe la razón; la compra se cancela y se avisa a Adquisiciones y al proveedor.

![06_almacen_devolucion_con_razon.png](06_almacen_devolucion_con_razon.png)

> [Se escribió] Razón de la devolución de OC-2026-0003 (no llegó, llegó dañado, incompleto…). Se le enviará a Adquisiciones y al proveedor: → Llegaron 3 cables, 1 con el conector roto
>
> Logix: Compra cancelada por devolución. Logix avisó a Adquisiciones y al proveedor por correo y Telegram.
>

## 07_buzon_factura_valida_y_rechazada.png
R2 validó la factura de la OC-2026-0007 y rechazó la de la OC-2026-0004 (importe distinto → cancelada).

![07_buzon_factura_valida_y_rechazada.png](07_buzon_factura_valida_y_rechazada.png)

> Robot R2: Resultado: VALIDA
>
> Robot R2: Resultado: RECHAZADA Reglas: IMPORTE_DISTINTO
>

## 08_compras_canceladas_con_razon.png
Compras canceladas con su causa y la razón que se le mandó al proveedor.

![08_compras_canceladas_con_razon.png](08_compras_canceladas_con_razon.png)


## 09_almacen_llego_bien_pago_automatico.png
El material llegó bien y la factura ya estaba validada: R4 armó el expediente y R5 pagó en el banco.

![09_almacen_llego_bien_pago_automatico.png](09_almacen_llego_bien_pago_automatico.png)

> Logix: Recepción registrada (entrada ENT-00001, salida SAL-00001). La factura ya estaba validada: Logix mandó el expediente a Finanzas y el pago al banco.
>

## 10_finanzas_pago_confirmado.png
Finanzas ve el pago confirmado por el banco con su clave de rastreo.

![10_finanzas_pago_confirmado.png](10_finanzas_pago_confirmado.png)


## 11_finanzas_error_saldo_insuficiente.png
El banco respondió SALDO_INSUFICIENTE: no se reintenta solo; Finanzas decide (reintentar o cancelar).

![11_finanzas_error_saldo_insuficiente.png](11_finanzas_error_saldo_insuficiente.png)

> Logix: Recepción registrada (entrada ENT-00002, salida SAL-00002). Logix le pidió la factura al proveedor (tiene 48 horas).
>
> Robot R2: Resultado: VALIDA
>

## 12_banco_emulado.png
Banco emulado: saldo, falla simulada y cada respuesta del banco.

![12_banco_emulado.png](12_banco_emulado.png)


## 13_finanzas_reintento_confirmado.png
Con saldo, Finanzas reintentó y el banco confirmó el pago.

![13_finanzas_reintento_confirmado.png](13_finanzas_reintento_confirmado.png)

> Banco emulado: ✔ El banco confirmó el pago.
>

## 14_finanzas_error_general_3_intentos.png
ERROR_GENERAL: el robot reintentó solo 3 veces; después pasó a Finanzas.

![14_finanzas_error_general_3_intentos.png](14_finanzas_error_general_3_intentos.png)

> Logix: Recepción registrada (entrada ENT-00003, salida SAL-00003). Logix le pidió la factura al proveedor (tiene 48 horas).
>
> Robot R2: Resultado: VALIDA
>
> Robots: R2 facturas: 0 R3 plazos: {'recordatorios': 0, 'avisos_cancelacion': 0, 'cancelaciones': 0} R5 reintentos de pago: 1 R6 avisos: {'ENVIADA': 0, 'SIMULADA': 30, 'FALLIDA': 0, 'REINTENTO': 0}
>
> Robots: R2 facturas: 0 R3 plazos: {'recordatorios': 0, 'avisos_cancelacion': 0, 'cancelaciones': 0} R5 reintentos de pago: 1 R6 avisos: {'ENVIADA': 0, 'SIMULADA': 2, 'FALLIDA': 0, 'REINTENTO': 0}
>

## 15_finanzas_cancela_pago.png
Finanzas canceló el pago con motivo: se avisó al proveedor y a Adquisiciones; el material se devuelve.

![15_finanzas_cancela_pago.png](15_finanzas_cancela_pago.png)

> [Se escribió] Motivo de la cancelación de OC-2026-0006 (se le enviará al proveedor y a Adquisiciones): → El banco no responde desde hace dos días; se recompra con otro trámite
>
> Logix: Compra cancelada. Logix avisó al proveedor y a Adquisiciones.
>

## 16_seguimiento_pagada.png
Seguimiento de la OC-2026-0007: Pagada, con su línea de tiempo.

![16_seguimiento_pagada.png](16_seguimiento_pagada.png)


## 17_seguimiento_cancelada.png
Seguimiento de una compra cancelada por factura no válida.

![17_seguimiento_cancelada.png](17_seguimiento_cancelada.png)


## 18_almacen_material_por_devolver.png
Material por devolver al proveedor (compras canceladas).

![18_almacen_material_por_devolver.png](18_almacen_material_por_devolver.png)


## 19_avisos_correo_y_telegram.png
Cola de avisos por correo y Telegram (modo simulado).

![19_avisos_correo_y_telegram.png](19_avisos_correo_y_telegram.png)


## 20_indicadores.png
Indicadores calculados solos desde la base y la bitácora.

![20_indicadores.png](20_indicadores.png)


## 21_bitacora.png
Bitácora de auditoría (no se puede modificar ni borrar).

![21_bitacora.png](21_bitacora.png)


## 22_pdf_orden_de_compra.png
PDF de la orden de compra (001-05) con QR que recibe el proveedor.

![22_pdf_orden_de_compra.png](22_pdf_orden_de_compra.png)


## 23_pdf_expediente_finanzas.png
PDF del expediente para Recursos Financieros (memorándum + revisión automática).

![23_pdf_expediente_finanzas.png](23_pdf_expediente_finanzas.png)


