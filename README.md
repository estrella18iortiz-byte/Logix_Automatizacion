# Logix 2.0 · Adquisiciones ⇄ Recursos Financieros

Proyecto del reto **«Automatiza tu Tec»** (Fundamentos de Ingeniería de Software SCC-1007, TecNM Campus Matehuala).

**Qué resuelve:** cuando una compra **ya está aprobada y comprada**, lo difícil es mover los papeles. Hay que mandarle la orden de compra al proveedor, recibir y revisar su factura, confirmar que el material llegó a almacén y hacer llegar todo a Recursos Financieros para el pago. También hay que saber, de ida y de vuelta, qué falta y cuándo se paga. Logix automatiza esa comunicación para que **Adquisiciones y Recursos Financieros estén conectados**.

**Automatización por excepción:** si todo cuadra, el expediente avanza solo. Si algo no cuadra, Logix lo detiene, explica por qué y avisa solo a quien debe resolverlo.

> Todos los datos son **simulados** (nombres, RFC, importes y facturas). Las facturas de prueba no tienen validez fiscal.

## Alcance
| Dentro de Logix | Fuera de Logix |
|---|---|
| Registro de la compra ya aprobada · envío de la OC al proveedor · validación de la factura (XML) · confirmación de almacén · expediente a Finanzas · devoluciones y reenvíos · fecha de pago · registro y conciliación del pago · avisos | Requisición, firmas de autorización y selección del proveedor (pasan **antes**) · el pago en sí (lo hace Recursos Financieros con su banco) |

## El flujo
```
Adquisiciones            Proveedor            Almacén              Recursos Financieros
─────────────            ─────────            ───────              ────────────────────
Registra la compra  ─R1→ recibe la OC
aprobada                 (PDF con QR)
                         manda su XML  ─R2→  (si la factura no cuadra: se rechaza y se le dice qué corregir)
                                             revisa el material
                                             «Llegó completo» ─R3→ recibe el expediente
                                             («Reportar problema» → avisa a Adquisiciones)
       ◄──────────────────────────────── R4 ───────────────────── devuelve con motivo
corrige y reenvía ─────────────────────── R4 ─────────────────────►
       ◄──────────────────── aviso ─────────────────────────────── programa fecha de pago
                         ◄── aviso ──────────────────────────────── registra/concilia el pago (R5)
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
| `adquisiciones` | Adquisiciones | Registra la compra aprobada, atiende excepciones y devoluciones de Finanzas |
| `almacen` | Almacén | Confirma que el material llegó (o reporta un problema) |
| `finanzas` | Recursos Financieros | Revisa el expediente, lo devuelve si falta algo, programa y registra el pago |
| `admin` | Administrador | Robots y avisos, indicadores y bitácora |

## Robots
| Robot | Qué hace solo | Cuándo | Archivo |
|---|---|---|---|
| R1 · Envío de la OC | Pone folio, genera la OC (001-05) con QR y se la manda al proveedor con instrucciones para facturar | Al registrar la compra | `logix/compras.py`, `pdfs.py` |
| **R2 · Lector de facturas CFDI** | Lee el XML y valida RFC, importe exacto, UUID, receptor, lista 69-B y estatus de la OC; acepta o rechaza explicando por qué | Cada minuto (buzón) o al momento (Telegram) | `logix/cfdi.py`, `validacion.py`, `robot_facturas.py` |
| R3 · Expediente a Finanzas | Revisa que esté completo (OC + factura válida + entrada de almacén), genera el PDF con memorándum y SHA-256 y lo manda a Recursos Financieros; ticket `PAG-` al proveedor | Al confirmar Almacén | `logix/expediente.py`, `pdfs.py` |
| R4 · Comunicación Adquisiciones ⇄ Finanzas | Avisa cada devolución, reenvío, fecha programada y pago; recuerda a quien tenga un expediente detenido (48 h Finanzas, 24 h Adquisiciones) | Al momento y cada minuto | `logix/pagos.py` |
| R5 · Conciliación | Lee el archivo del banco (simulado) y marca PAGADA por folio e importe; lo que no coincide se reporta | Cada minuto | `logix/pagos.py` |
| R6 · Vigilante del cierre | Semáforo 🔴🟡🟢 contra la fecha límite de pagos (**15 de diciembre**) y una alerta diaria | Cada minuto | `logix/vigilante.py` |
| R7 · Notificador | Envía la cola por correo y Telegram con 3 reintentos | Cada minuto | `logix/notificador.py` |
| R8 · Bot de Telegram | Vincula chats con código de un solo uso, responde el estatus por folio y recibe facturas XML de proveedores | Todo el tiempo | `logix/bot_telegram.py`, `telegram.py` |

Las horas de recordatorio, la fecha límite y los días del semáforo están en la tabla `parametros`: se cambian **sin tocar el código**.

## Pruebas
| Comando | Qué prueba | Resultado |
|---|---|---|
| `python -m unittest discover -s tests -t .` | Reglas del lector de facturas (14) y bot de Telegram con un Telegram falso (8) | 22/22 |
| `python probar_r3.py` | 9 facturas de prueba por el robot R2 | 9/9 |
| `python probar_flujo_completo.py` | **Casos de punta a punta** CP-01 a CP-18 ligados a los criterios de aceptación; evidencia en `resultados/resultados_pruebas.csv` | 19/19 |

> `probar_flujo_completo.py` **reinicia la base**. Al terminar, corre `REINICIAR_DATOS.bat` antes de una demostración.

## Recorrido de demostración (para el video y la prueba SUS)
1. **adquisiciones** › Registrar compra: proveedor «Cómputo Demo», área «Departamento de Sistemas y Computación», 10 «Mouse óptico USB» a $150 → **Registrar y enviar al proveedor**. Anota el folio (por ejemplo `OC-2026-0004`).
2. **adquisiciones** › Buzón de facturas › escribe ese folio › **Factura con importe equivocado** (se rechaza y abre una excepción) y luego **Factura correcta** (se valida). Así se simula al proveedor mandando su correo.
3. **almacen** › Recepción › selecciona la OC › **Llegó completo: confirmar** → Logix arma el expediente y lo manda a Finanzas.
4. **finanzas** › Expedientes › **Abrir expediente PDF** › **Devolver a Adquisiciones** con un motivo (por ejemplo «falta el sello del SAT legible»).
5. **adquisiciones** › Devueltas por Finanzas › **Reenviar a Finanzas** con la respuesta.
6. **finanzas** › Expedientes › **Programar fecha** › **Registrar pago manual** (o «Conciliar archivo del banco»).
7. Cualquiera › Consultar folio: la línea de tiempo completa termina en **Pagada**. **admin** › Robots y avisos (todos los mensajes que se mandaron), Indicadores y Bitácora.

> Atajo: `OC-2026-0001` y `OC-2026-0002` ya esperan factura. Usa `datos_prueba/facturas/01_correcta.xml` (OC-2026-0001) o `02_importe_distinto.xml` (OC-2026-0002) con «Simular correo con XML…».

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
generar_datos.py         Crea la base logix_db con datos simulados
logix/                   Lógica: un archivo por robot (ver tabla de robots)
sql/01_esquema.sql       Tablas de la base (14) y bitácora inmutable
tests/                   Pruebas unitarias
probar_r3.py · probar_flujo_completo.py   Pruebas de integración y de punta a punta
docs/                    Encuesta SUS y cambios al diseño para los documentos
memoria_claude/          Bitácora del trabajo con el asistente de IA (para la declaración de IA)
```
