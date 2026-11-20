# Logix 3.0 · Compras repetitivas con proveedores fijos

Proyecto del reto **«Automatiza tu Tec»** (Fundamentos de Ingeniería de Software SCC-1007, TecNM Campus Matehuala).

**Qué resuelve:** las compras que se repiten una y otra vez con **proveedores fijos, ya avalados por el Tec**. La petición ya fue **aceptada y validada** antes de Logix. A partir de ahí todo es repetitivo: mandar la orden de compra, esperar el material, pedir y revisar la factura, juntar el expediente para Recursos Financieros, pagar y avisarle a cada quien. Logix lo hace solo, **paga a través de un banco emulado** y avisa por **correo y Telegram**.

**Automatización por excepción:** si todo cuadra, la compra avanza sola hasta el pago. Si algo no cuadra (el material no llega, llega mal, la factura no es válida o el banco responde con error), Logix **cancela o detiene** la compra, explica por qué y avisa solo a quien le toca.

> Todos los datos son **simulados** (nombres, RFC, CLABE, importes y facturas). El banco es **emulado**: no mueve dinero real.

## Supuestos (acordados el 19-nov-2026)
- El **banco es emulado** (`logix/banco_emulado.py`).
- Los **proveedores son fijos** y ya están avalados: no se buscan ni se evalúan, y ya no se revisa la lista 69-B.
- La **confirmación para comprar** ya se validó antes de Logix.
- Personas que intervienen: **Adquisiciones** registra la compra, el **Jefe de Almacén** revisa el material físico y **Recursos Financieros** solo decide cuando el banco responde con un error.

## El flujo (diagrama completo en `diagramas/01_flujo_proceso.png`)
```
Inicio → petición aceptada y validada → R1: OC en PDF con QR al proveedor (Telegram y correo)
   │
   ▼  Jefe de Almacén revisa el material (máximo 7 días)
   ├─ Aún no llega → R3: recordatorio el día 3 · último aviso 5 h antes del día 7 · día 7: CANCELADA
   ├─ No llegó / mal estado → «Devolución» con razón → CANCELADA (aviso a Adquisiciones y proveedor)
   └─ Llegó bien → entrada y salida automáticas
          │
          ▼  ¿Ya hay factura válida?
          ├─ No → se le pide al proveedor por Telegram y correo (48 h)
          │       ├─ no llega en 48 h → CANCELADA y se devuelve el material
          │       └─ llega → R2 la valida: no válida → CANCELADA y se devuelve el material
          └─ Sí → R4: expediente PDF (SHA-256) a Recursos Financieros
                    → R5: pago automático al banco emulado
                         ├─ confirma → mensaje al proveedor «pago confirmado» + aviso a Adquisiciones y Finanzas → PAGADA
                         └─ error → (error general: 3 reintentos solos) → Finanzas: «Reintentar» o «Cancelar» con motivo
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
| 4. Abrir Logix | doble clic en **INICIAR_LOGIX.bat** (robot + panel) |

Usuarios (contraseña `logix2026`):

| Usuario | Rol | Qué hace en Logix |
|---|---|---|
| `adquisiciones` | Adquisiciones | Registra la compra aprobada; ve las compras canceladas con su razón |
| `almacen` | Jefe de Almacén | «Llegó bien» o «Devolución» con razón; marca el material devuelto |
| `finanzas` | Recursos Financieros | Ve los pagos; si el banco falla: reintentar, cancelar con motivo o corregir la CLABE |
| `admin` | Administrador | Robots y avisos, banco emulado, indicadores y bitácora |

## Robots
| Robot | Qué hace solo | Cuándo | Archivo |
|---|---|---|---|
| R1 · Envío de la OC | Folio, OC (001-05) en PDF con QR y envío al proveedor con el plazo de 7 días | Al registrar la compra | `logix/compras.py`, `pdfs.py` |
| **R2 · Validador de facturas** | Lee el XML y valida RFC emisor y receptor, importe exacto, UUID no repetido, tipo de comprobante y que la OC espere factura. **Si no es válida, cancela la compra** y le explica al proveedor por qué | Al llegar la factura (Telegram o correo) | `logix/cfdi.py`, `validacion.py`, `robot_facturas.py` |
| R3 · Vigilante de plazos | Material: recordatorio el día 3, último aviso 5 h antes del día 7, cancelación el día 7. Factura: cancelación a las 48 h de que llegó el material | Cada minuto | `logix/plazos.py` |
| R4 · Expediente a Finanzas | Con factura válida y material confirmado: PDF (memorándum + expediente) con SHA-256 a Recursos Financieros y ticket `PAG-` al proveedor | En cuanto se juntan las dos cosas | `logix/expediente.py`, `pdfs.py` |
| **R5 · Pago automático** | Manda la transferencia al banco emulado y actúa según la respuesta (tabla de abajo) | Al llegar el expediente y cada minuto (reintentos) | `logix/pagos.py`, `banco_emulado.py` |
| R6 · Notificador | Envía la cola por correo y Telegram con 3 reintentos | Cada minuto | `logix/notificador.py` |
| R7 · Bot de Telegram | Vincula chats, responde el estatus por folio y recibe las facturas XML de los proveedores | Todo el tiempo | `logix/bot_telegram.py`, `telegram.py` |

Todas las cancelaciones pasan por `logix/cancelacion.py`: la OC queda CANCELADA con su causa y razón, se marca el material por devolver (si ya estaba en almacén) y se avisa al **proveedor** y a **Adquisiciones** por **correo y Telegram**.

### Respuestas del banco emulado
| Respuesta | Qué hace Logix |
|---|---|
| CONFIRMADO | OC **PAGADA** · al proveedor: «pago confirmado» con clave de rastreo · aviso a Adquisiciones y Finanzas |
| PAGO_DUPLICADO | Esa OC ya se había pagado → queda PAGADA y no se descuenta otra vez |
| ERROR_GENERAL | Reintenta solo hasta 3 veces (una por vuelta del robot); si sigue fallando → error para Finanzas |
| SALDO_INSUFICIENTE · MONTO_INCORRECTO · DIVISA_INCORRECTA | No reintenta. Aviso a Finanzas; al proveedor: «pago en proceso, hubo un retraso» |
| CUENTA_INVALIDA | Igual, pero al proveedor se le pide su CLABE correcta; Finanzas la corrige y reintenta |

Solo cuando Finanzas presiona **«Cancelar pago»** (con motivo) la compra se cancela y se avisa al proveedor y a Adquisiciones.

Los plazos (7 días, día 3, 5 h, 48 h) y los reintentos del banco están en la tabla `parametros`: se cambian **sin tocar el código**.

## Pruebas
| Comando | Qué prueba | Resultado |
|---|---|---|
| `python -m unittest discover -s tests -t .` | Reglas de la factura, «¿cancela la compra?», CLABE del banco y bot de Telegram con un Telegram falso | 32/32 |
| `python probar_r2_facturas.py` | 10 facturas de prueba por el robot R2 y si la OC queda cancelada o no | 10/10 |
| `python probar_flujo_completo.py` | **Todas las ramas del diagrama** (CP-01 a CP-22); evidencia en `resultados/resultados_pruebas.csv` | 22/22 |
| `python capturar_evidencias.py` | Maneja el panel solo y toma 23 capturas de evidencia en `evidencias/` | — |

> `probar_flujo_completo.py` y `capturar_evidencias.py` **reinician la base**. Al terminar, corre `REINICIAR_DATOS.bat` antes de una demostración.

## Recorrido de demostración (para el video y la prueba SUS)
1. **adquisiciones** › Registrar compra: proveedor «Cómputo Demo», área «Departamento de Sistemas y Computación», 5 «Mouse óptico USB» a $150 → **Registrar y enviar al proveedor**. Anota el folio (`OC-2026-0007`).
2. **adquisiciones** › Buzón de facturas › escribe el folio › **Factura correcta** (simula al proveedor mandando su XML).
3. **almacen** › Recepción › selecciona la OC › **Llegó bien: confirmar** → como la factura ya estaba validada, Logix arma el expediente y **paga solo**.
4. **finanzas** › Pagos: el pago aparece confirmado con su clave de rastreo SPEI.
5. **almacen** › Recepción › selecciona `OC-2026-0002` › **Devolución** y escribe la razón → la compra se cancela y se avisa a Adquisiciones y al proveedor.
6. **adquisiciones** › Buzón › `OC-2026-0004` › **Factura con importe equivocado** → la compra se cancela. Revísalo en **Compras canceladas**.
7. Errores del banco: **finanzas** › Banco emulado › forzar `SALDO_INSUFICIENTE` › Aplicar. Repite los pasos 2 y 3 con `OC-2026-0001` → en **Pagos** sale el error. Regresa la falla a `NINGUNA` y presiona **Reintentar pago**.
8. Cualquiera › Consultar folio: línea de tiempo completa. **admin** › Robots y avisos (todos los mensajes por correo y Telegram), Indicadores y Bitácora.

> Las capturas de cada paso ya están en `evidencias/` (ver `evidencias/LEEME.md`).

## Conectar Telegram (5 minutos, gratis)
1. En Telegram, abre **@BotFather** › `/newbot` › nombre «Logix Asistente» y un usuario que termine en `bot`. Te da un **token**.
2. Pégalo en `.env` como `LOGIX_TELEGRAM_TOKEN=` y cambia `LOGIX_MODO_SIMULADO=0`.
3. Abre `INICIAR_LOGIX.bat`. En el panel, cada usuario ve en **Inicio** su código (`/vincular 123456`). Los códigos de los proveedores están en **Proveedores**.
4. En Telegram: abre tu bot › `/start` › `/vincular <código>`. Desde ahí llegan los avisos, y puedes escribir un folio (`OC-2026-0001`) o, como proveedor, mandar el XML con el folio en el pie.

## Pendiente de conectar (necesita credenciales)
- **Correo real:** cuenta Gmail de Logix + contraseña de aplicación en `.env`. El código ya está (IMAP para leer y SMTP para enviar), pero **no se ha probado con una cuenta real**.
- **Telegram real:** el token del bot (pasos de arriba). Las pruebas usan un Telegram falso; **falta probarlo con el bot real**.

## Estructura
```
panel.py                 Panel de escritorio (CustomTkinter): una pantalla por rol
robot.py                 Corre los robots cada minuto
generar_datos.py         Crea la base logix_db con datos simulados (6 compras, 4 proveedores fijos, banco)
logix/                   Lógica: un archivo por robot (ver tabla) + cancelacion.py + banco_emulado.py
sql/01_esquema.sql       Tablas de la base (14) y bitácora inmutable
diagramas/               Flujo del proceso, estados de la OC y modelo de datos (.drawio editable y .png)
evidencias/              Capturas del panel y de los PDF (se regeneran con capturar_evidencias.py)
tests/                   Pruebas unitarias
probar_r2_facturas.py · probar_flujo_completo.py   Pruebas de integración y de punta a punta
docs/                    Encuesta SUS y cambios al diseño para los documentos
memoria_claude/          (solo en la PC de Angela, no se sube) Bitácora del trabajo con el asistente de IA
```
