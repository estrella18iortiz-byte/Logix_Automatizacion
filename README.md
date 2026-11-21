# Logix 3.1 · Compras repetitivas con proveedores fijos

[![Pruebas de Logix](https://github.com/estrella18iortiz-byte/Logix_Automatizacion/actions/workflows/pruebas.yml/badge.svg)](https://github.com/estrella18iortiz-byte/Logix_Automatizacion/actions/workflows/pruebas.yml)

Proyecto del reto **«Automatiza tu Tec»** (Fundamentos de Ingeniería de Software SCC-1007, TecNM Campus Matehuala).

**Qué resuelve:** las compras que se repiten una y otra vez con **proveedores fijos, ya avalados por el Tec**. Los departamentos piden material (Recursos Humanos: hojas y bolígrafos; Servicios Generales: jabón y detergente; Sistemas: mouse y tóner...) y su **requisición llega ya validada**. A partir de ahí todo es repetitivo: generar y mandar la orden de compra, esperar el material, pedir y revisar la factura, juntar el expediente para Recursos Financieros, pagar y avisarle a cada quien. Logix lo hace solo, **paga a través de un banco emulado** y avisa por **correo y Telegram**.

**Automatización por excepción:** si todo cuadra, la compra avanza sola desde la requisición hasta el pago. Las personas solo intervienen donde hace falta **ver algo físico** (Jefe de Almacén) o **tomar una decisión de dinero** (Recursos Financieros, solo cuando el banco falla).

> Todos los datos son **simulados** (nombres, RFC, CLABE, importes y facturas). El banco es **emulado**: no mueve dinero real.

## Supuestos (acordados el 19 y 20-nov-2026)
- **Adquisiciones ya no usa Logix.** Sus requisiciones son **eventos simulados** (`logix/simulador.py`): cada hora llega una requisición de un departamento, como viene reglamentado en el Tec:
  - Requisición de bienes y servicios (**formato 001-03**) con folio `REQ-2026-0001`.
  - **Partida presupuestal** del Clasificador por Objeto del Gasto: 21101 oficina, 21401 tecnologías de la información, 21601 limpieza, 24601 eléctrico.
  - Justificación del área y **4 firmas que la validan**: Jefe(a) del área, Planeación y Presupuestos (suficiencia presupuestal), Subdirección (Académica o de Servicios Administrativos) y Dirección.
- El **banco es emulado** (`logix/banco_emulado.py`).
- Los **proveedores son fijos** y ya están avalados, uno por partida: no se buscan ni se evalúan, y ya no se revisa la lista 69-B.
- Personas que intervienen: el **Jefe de Almacén** revisa el material físico contra lo que se aceptó, y **Recursos Financieros** solo ve las fallas del banco.

## El flujo (diagrama completo en `diagramas/01_flujo_proceso.png`)
```
Inicio → R0: llega una requisición YA validada (001-03, partida, 4 firmas) · evento simulado
       → R1: genera sola la OC (001-05) en PDF con QR y la manda al proveedor fijo (Telegram y correo)
   │
   ▼  Jefe de Almacén compara lo que llegó con lo que se aceptó (máximo 7 días)
   ├─ Aún no llega → R3: recordatorio el día 3 · último aviso 5 h antes del día 7 · día 7: CANCELADA
   ├─ No llegó / mal estado → «Devolución» con razón → CANCELADA (aviso al proveedor)
   └─ «Aceptar: llegó bien» → entrada y salida automáticas
          │
          ▼  ¿Ya hay factura válida?
          ├─ No → se le pide al proveedor por Telegram y correo (48 h)
          │       ├─ no llega en 48 h → CANCELADA y se devuelve el material
          │       └─ llega → R2 la valida: no válida → CANCELADA y se devuelve el material
          └─ Sí → R4: expediente PDF (SHA-256) a Recursos Financieros
                    → R5: pago automático al banco emulado
                         ├─ confirma → mensaje al proveedor «pago confirmado» → PAGADA (Finanzas no hace nada)
                         └─ error → (error general: 3 reintentos solos) → bandeja de fallas de Finanzas:
                                    «Reintentar», «Corregir CLABE» o «Cancelar» con motivo
```

## Requisitos
- Windows con **SQL Server** (Express o Developer; instancia `.\SQLEXPRESS` o `localhost`)
- **ODBC Driver 18 for SQL Server**
- Python **3.12 o superior** · `pip install -r requirements.txt`

## Arranque
| Paso | Comando |
|---|---|
| 1. Instalar librerías | doble clic en **INSTALAR.bat** |
| 2. Revisar la máquina | doble clic en **VERIFICAR.bat** (crea `.env` si no existe y dice qué arreglar) |
| 3. Base y datos simulados | doble clic en **REINICIAR_DATOS.bat** (o `python generar_datos.py`) |
| 4. Abrir Logix | doble clic en **INICIAR_LOGIX.bat** (robot + panel). Deja abierta la ventana del robot: ahí llegan las requisiciones simuladas |

Usuarios (contraseña `logix2026`):

| Usuario | Rol | Qué ve en Logix |
|---|---|---|
| `almacen` | Jefe de Almacén | **Recepción**: al seleccionar una orden ve qué se aceptó (requisición, artículos, unidades y cantidades) y presiona **«Aceptar»** o **«Devolución»** con razón; marca el material devuelto |
| `finanzas` | Recursos Financieros | **Fallas de pago**: solo los pagos que el banco rechazó, por qué fallaron, qué decidir y el dinero detenido; reintentar, corregir la CLABE o cancelar con motivo |
| `admin` | Administrador | Todo lo demás: requisiciones simuladas, buzón de facturas (simular al proveedor), compras canceladas, proveedores, robots y avisos, banco emulado, indicadores y bitácora |

## Robots
| Robot | Qué hace solo | Cuándo | Archivo |
|---|---|---|---|
| **R0 · Simulador de requisiciones** | Simula los eventos: llega una requisición validada (001-03, partida, 4 firmas) de un departamento. Si es de cómputo (Cómputo Demo, el proveedor vinculado a Telegram) deja lista su factura correcta en `datos_prueba/facturas_telegram/` | Cada hora (parámetro `MINUTOS_ENTRE_REQUISICIONES`; 0 = apagado) | `logix/simulador.py` |
| R1 · Orden de compra | Genera la OC (001-05) en PDF con QR con el proveedor fijo de la partida y se la manda con el plazo de 7 días | En cuanto llega la requisición | `logix/compras.py`, `pdfs.py` |
| **R2 · Validador de facturas** | Lee el XML y valida RFC emisor y receptor, importe exacto, UUID no repetido, tipo de comprobante y que la OC espere factura. **Si no es válida, cancela la compra** y le explica al proveedor por qué | Al llegar la factura (Telegram o correo) | `logix/cfdi.py`, `validacion.py`, `robot_facturas.py` |
| R3 · Vigilante de plazos | Material: recordatorio el día 3, último aviso 5 h antes del día 7, cancelación el día 7. Factura: cancelación a las 48 h de que llegó el material | Cada minuto | `logix/plazos.py` |
| R4 · Expediente a Finanzas | Con factura válida y material confirmado: PDF (memorándum + expediente) con SHA-256 y ticket `PAG-` al proveedor | En cuanto se juntan las dos cosas | `logix/expediente.py`, `pdfs.py` |
| **R5 · Pago automático** | Programa el pago y lo manda al banco emulado **5 a 10 minutos después** del expediente (como un banco real; parámetros `MINUTOS_PAGO_MIN/MAX`, 0 = inmediato) y actúa según la respuesta (tabla de abajo) | Cada minuto (pagos programados y reintentos) | `logix/pagos.py`, `banco_emulado.py` |
| R6 · Notificador | Envía la cola por correo y Telegram con 3 reintentos | Cada minuto | `logix/notificador.py` |
| R7 · Bot de Telegram | Vincula chats, responde el estatus por folio y recibe las facturas XML de los proveedores | Todo el tiempo | `logix/bot_telegram.py`, `telegram.py` |

Todas las cancelaciones pasan por `logix/cancelacion.py`: la OC queda CANCELADA con su causa y razón, se marca el material por devolver (si ya estaba en almacén) y se avisa al **proveedor** por **correo y Telegram** (y a Almacén o Finanzas cuando les toca).

### Respuestas del banco emulado
| Respuesta | Qué hace Logix |
|---|---|
| CONFIRMADO | OC **PAGADA** · al proveedor: «pago confirmado» con clave de rastreo · Finanzas no recibe nada |
| PAGO_DUPLICADO | Esa OC ya se había pagado → queda PAGADA y no se descuenta otra vez |
| ERROR_GENERAL | Reintenta solo hasta 3 veces (una por vuelta del robot); si sigue fallando → falla para Finanzas |
| SALDO_INSUFICIENTE · MONTO_INCORRECTO · DIVISA_INCORRECTA | No reintenta. Falla para Finanzas; al proveedor: «pago en proceso, hubo un retraso» |
| CUENTA_INVALIDA | Igual, pero al proveedor se le pide su CLABE correcta; Finanzas la corrige y reintenta |

Solo cuando Finanzas presiona **«Cancelar pago»** (con motivo) la compra se cancela y se avisa al proveedor.

Los plazos (7 días, día 3, 5 h, 48 h), los reintentos del banco y cada cuánto llega una requisición están en la tabla `parametros`: se cambian **sin tocar el código**.

## Pruebas
| Comando | Qué prueba | Resultado |
|---|---|---|
| `python -m unittest discover -s tests -t .` | Reglas de la factura, «¿cancela la compra?», CLABE del banco y bot de Telegram con un Telegram falso | 32/32 |
| `python probar_r2_facturas.py` | 10 facturas de prueba por el robot R2 y si la OC queda cancelada o no | 10/10 |
| `python probar_flujo_completo.py` | **Todas las ramas del diagrama** (CP-01 a CP-22 + CP-03b simulador + CP-11b pago a los 5–10 min); evidencia en `resultados/resultados_pruebas.csv` | 24/24 |
| `python capturar_evidencias.py` | Maneja el panel solo y toma 23 capturas de evidencia en `evidencias/` | — |

**En GitHub (sin instalar nada):** las pruebas unitarias, las de facturas R2 y las de punta a punta corren solas en cada cambio, con un SQL Server propio y datos simulados (`.github/workflows/pruebas.yml`). Pestaña **Actions** › «Pruebas de Logix» › abre una ejecución: se ve cada paso, la tabla de resultados y la evidencia descargable (CSV y PDF generados).

> `probar_flujo_completo.py` y `capturar_evidencias.py` **reinician la base**. Al terminar, corre `REINICIAR_DATOS.bat` antes de una demostración.

## Recorrido de demostración (para el video y la prueba SUS)
1. **admin** › Requisiciones › elige «Departamento de Recursos Humanos» › **Simular requisición ahora**. Llega la `REQ-2026-0007` validada y Logix genera sola la `OC-2026-0007` (selecciónala para ver la partida, la justificación y las 4 firmas). Si el robot está abierto, cada hora llega otra sola.
2. **admin** › Buzón de facturas › escribe `OC-2026-0007` › **Factura correcta** (simula al proveedor mandando su XML).
3. **almacen** › Recepción › selecciona `OC-2026-0007`: abajo aparece qué se aceptó (artículos, unidades y cantidades) › **Aceptar: llegó bien** → como la factura ya estaba validada, Logix arma el expediente y **paga solo**.
4. **finanzas** › Fallas de pago: «No hay fallas», el pago salió solo.
5. **almacen** › Recepción › selecciona `OC-2026-0002` › **Devolución** y escribe la razón → la compra se cancela y se avisa al proveedor.
6. **admin** › Buzón › `OC-2026-0004` › **Factura con importe equivocado** → la compra se cancela. Revísalo en **Compras canceladas**.
7. Falla del banco: **admin** › Banco emulado › forzar `SALDO_INSUFICIENTE` › Aplicar. Repite los pasos 2 y 3 con `OC-2026-0001` → en **finanzas** › Fallas de pago aparece por qué falló y qué decidir. Regresa la falla a `NINGUNA` y presiona **Reintentar pago**.
8. Cualquiera › Consultar folio: línea de tiempo completa. **admin** › Robots y avisos (todos los mensajes por correo y Telegram), Indicadores y Bitácora.

> Las capturas de cada paso ya están en `evidencias/` (ver `evidencias/LEEME.md`).

## Qué recibe el proveedor por Telegram (y correo)
1. **Orden de compra:** qué se compró, el plazo de 7 días, cómo mandar su factura, que puede escribir el folio para ver cómo va y **el PDF oficial adjunto** (identidad de Logix, tabla de productos y QR).
2. Recordatorio el día 3 y último aviso 5 h antes del día 7 (si no ha llegado el material).
3. **Material recibido:** el Almacén confirmó su material (y, si falta, que mande su factura en 48 h).
4. **Factura recibida y validada** (o rechazada con el motivo).
5. **Ticket de pago `PAG-`:** su factura y su material pasan al banco; el pago sale en unos minutos.
6. **Pago confirmado** con la clave de rastreo SPEI (o «pago en proceso» / «envíe su CLABE» si el banco falla).
7. **Compra cancelada** con la causa y la razón.

Desde el bot el proveedor puede escribir su folio (`OC-…` o `PAG-…`) para ver cómo va, y mandar el XML con el folio en el pie.

**Factura para la demostración:** cada orden de cómputo deja sola su factura correcta en `datos_prueba/facturas_telegram/<folio>_factura_correcta.xml`. Para cualquier otra orden (o para la versión con importe equivocado) usa **GENERAR_FACTURA.bat**.

## Conectar Telegram (5 minutos, gratis)
1. En Telegram, abre **@BotFather** › `/newbot` › nombre «Logix Asistente» y un usuario que termine en `bot`. Te da un **token**.
2. Pégalo en `.env` como `LOGIX_TELEGRAM_TOKEN=` y cambia `LOGIX_MODO_SIMULADO=0`. Corre **VERIFICAR.bat**: debe decir «Bot conectado».
3. Abre `INICIAR_LOGIX.bat`. En el panel, `almacen` y `finanzas` ven su código arriba de su pantalla (`/vincular 123456`); `admin` lo ve en **Inicio**. Los códigos de los proveedores están en **admin › Proveedores**.
4. En Telegram: abre tu bot › `/start` › `/vincular <código>`. Desde ahí llegan los avisos, y puedes escribir un folio (`OC-2026-0001`) o, como proveedor, mandar el XML con el folio en el pie.

## Pendiente de conectar (necesita credenciales)
- **Correo real:** cuenta Gmail de Logix + contraseña de aplicación en `.env`. El código ya está (IMAP para leer y SMTP para enviar), pero **no se ha probado con una cuenta real**.
- **Telegram real:** bot **@Asist_tec_bot** conectado el 20-nov-2026 (`VERIFICAR.bat` → «Bot conectado»). Las pruebas automáticas usan un Telegram falso; falta el recorrido con el bot real (vincular y recibir la OC).

## Estructura
```
panel.py                 Panel de escritorio (CustomTkinter): una pantalla por rol
robot.py                 Corre los robots cada minuto (incluye el simulador de requisiciones R0)
generar_datos.py         Crea la base logix_db con datos simulados (6 requisiciones validadas, 4 proveedores fijos, banco)
logix/                   Lógica: un archivo por robot (ver tabla) + simulador.py + cancelacion.py + banco_emulado.py
sql/01_esquema.sql       Tablas de la base (15) y bitácora inmutable
diagramas/               Flujo del proceso, estados de la OC y modelo de datos (.drawio editable y .png)
evidencias/              Capturas del panel y de los PDF (se regeneran con capturar_evidencias.py)
tests/                   Pruebas unitarias
probar_r2_facturas.py · probar_flujo_completo.py   Pruebas de integración y de punta a punta
docs/                    Encuesta SUS y cambios al diseño para los documentos
memoria_claude/          (solo en la PC de Angela, no se sube) Bitácora del trabajo con el asistente de IA
```
