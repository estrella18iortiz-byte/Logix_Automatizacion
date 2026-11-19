# Logix 2.0

Seguimiento automatizado del expediente de compra directa (Instructivo TecNM-AD-IT-001), desde la requisición hasta el pago al proveedor.
**Automatización por excepción:** si todo cuadra, el expediente avanza solo; si algo no cuadra, Logix lo detiene, explica por qué y avisa solo a quien debe resolverlo. Las personas solo **deciden, autorizan, verifican el bien físico y pagan**.

> Todos los datos son **simulados** (nombres, RFC, importes y facturas). Las facturas de prueba no tienen validez fiscal.

## Requisitos
- Windows con **SQL Server Express** (instancia `.\SQLEXPRESS`) y `sqlcmd`
- **ODBC Driver 18 for SQL Server**
- Python 3.12 · `pip install -r requirements.txt`

## Arranque
| Paso | Comando |
|---|---|
| 1. Configuración | `copy .env.example .env` (con `LOGIX_MODO_SIMULADO=1` no se envía nada) |
| 2. Base y datos simulados | `python generar_datos.py` o doble clic en **REINICIAR_DATOS.bat** |
| 3. Abrir Logix | doble clic en **INICIAR_LOGIX.bat** (robot + panel) |

Usuarios (contraseña `logix2026`): `solicitante`, `jefe.area`, `presupuestos`, `subdirector`, `director`, `adquisiciones`, `jefe.rm`, `subdir.admin`, `almacen`, `finanzas`, `admin`.

## Pruebas
| Comando | Qué prueba | Resultado |
|---|---|---|
| `python -m unittest discover -s tests -t .` | Reglas del lector de facturas (14) y bot de Telegram con un Telegram falso (8) | 22/22 |
| `python probar_r3.py` | 9 facturas de prueba por el robot R3 | 9/9 |
| `python probar_flujo_completo.py` | **23 casos de punta a punta** (CP-01 a CP-23) ligados a los criterios de aceptación; deja la evidencia en `resultados/resultados_pruebas.csv` | 24/24 (CP-17 tiene dos partes) |

> `probar_flujo_completo.py` **reinicia la base**. Al terminar, corre `REINICIAR_DATOS.bat` antes de una demostración.

## Robots (`python robot.py`, cada 60 s)
| Robot | Qué hace solo | Archivo |
|---|---|---|
| R1 · Requisición inteligente | Asigna la partida, propone el precio de referencia, valida el saldo (y que el precio no se desvíe más del 30 %) y la manda a firmas | `logix/requisiciones.py` |
| R2 · Enrutador de firmas | Turna en orden (4 · 3 · 3 niveles), no deja saltar niveles, recuerda a las 24 h y escala a las 48 h | `logix/firmas.py` |
| **R3 · Lector de facturas CFDI** | Lee el XML del buzón y valida RFC, importe exacto, UUID, receptor, lista 69-B y estatus de la OC; acepta o rechaza explicando por qué | `logix/cfdi.py`, `validacion.py`, `robot_facturas.py` |
| R4 · Expediente | Revisa la triada y genera el PDF (memorándum + expediente) con SHA-256; lo turna a firmas de pago y a Finanzas | `logix/expediente.py`, `pdfs.py` |
| R5 · Notificador | Envía la cola por correo y Telegram con 3 reintentos; tiene lista blanca de correo para la demostración | `logix/notificador.py` |
| R7 · Bot de Telegram | Vincula chats con un código de un solo uso, responde el estatus por folio (cada proveedor solo ve sus órdenes) y **recibe facturas XML** que valida al momento | `logix/bot_telegram.py`, `telegram.py` |
| R6 · Vigilante del cierre | Semáforo 🔴🟡🟢 contra la fecha límite de diciembre y una alerta diaria | `logix/vigilante.py` |
| R8 · Proveedor apto | Dictamen automático: puntaje > 70, evaluación vigente, lista 69-B | `logix/compras.py` |
| R9 · Orden de compra | PDF 001-05 con QR y envío al proveedor al autorizarse | `logix/compras.py`, `pdfs.py` |
| R10 · Conciliación | Lee el archivo del banco (simulado) y marca PAGADA | `logix/pagos.py` |

## Recorrido de demostración (para el video y las tareas del SUS)
1. **solicitante** › Nueva requisición: 10 «Mouse óptico USB» → Enviar. *(Prueba: 100 tóner → «Saldo insuficiente».)*
2. **jefe.area** › Firmas pendientes › Aprobar. Repetir con **presupuestos**, **subdirector** y **director**.
3. **adquisiciones** › Generar orden de compra: elegir la requisición y el proveedor sugerido (los no aptos dicen por qué).
4. **adquisiciones**, **jefe.rm** y **subdir.admin** › Firmas pendientes › Aprobar la OC (se genera el PDF y se envía al proveedor).
5. **adquisiciones** › Buzón de facturas › escribir el folio de la OC › «Factura con importe equivocado» (se rechaza y abre una excepción) y luego «Factura correcta» (se valida). Así se simula al proveedor enviando su correo.
6. **almacen** › Recepción › confirmar. **jefe.area** › Recibir material › firmar con calificación → se arma el expediente.
7. **adquisiciones**, **jefe.rm** y **subdir.admin** aprueban el pago → **finanzas** › Pagos › abrir el expediente PDF › conciliar o registrar el pago.
8. Cualquiera › Consultar folio: línea de tiempo completa. **admin** › Robots y avisos, Indicadores y Bitácora.

> Atajo para la demo: OC-2026-0001 y OC-2026-0002 ya están esperando factura. Usa `datos_prueba/facturas/01_correcta.xml` (OC-2026-0001) o `02_importe_distinto.xml` (OC-2026-0002) para ver el rechazo.

## Conectar Telegram (5 minutos, gratis)
1. En Telegram, abre **@BotFather** › `/newbot` › nombre «Logix Asistente» y un usuario que termine en `bot`. Te da un **token**.
2. Pégalo en `.env` como `LOGIX_TELEGRAM_TOKEN=` y cambia `LOGIX_MODO_SIMULADO=0`.
3. Abre `INICIAR_LOGIX.bat`. En el panel, cada usuario ve en **Inicio** su código (`/vincular 123456`). Los códigos de los proveedores están en **Proveedores**.
4. En Telegram: abre tu bot › `/start` › `/vincular <código>`. Desde ahí llegan los avisos, y puedes escribir un folio (`OC-2026-0001`) o, como proveedor, mandar el XML con el folio en el pie.

## Pendiente de conectar (necesita credenciales)
- **Correo real:** cuenta Gmail de Logix + contraseña de aplicación en `.env`. El código ya está (IMAP para leer y SMTP para enviar), pero **no se ha probado con una cuenta real**.
- **Telegram real:** el token del bot (pasos de arriba). Las pruebas usan un Telegram falso; **falta probarlo con el bot real**.
