# Logix 3.1 · contexto para Claude Code

Proyecto escolar de **Angela** (Fundamentos de Ingeniería de Software SCC-1007, reto «Automatiza tu Tec», TecNM Campus Matehuala). Su consultora se llama **Logix**. Responde siempre en **español**.

## Qué es
**Logix 3.0 (desde el 19 nov 2026, diagrama de Angela `Documentos/diagrama 19-nov-26.drawio.png`):** compras repetitivas con **proveedores fijos y avalados**; la petición ya está aceptada y validada; el **banco es emulado**. R1 manda la OC → el material tiene máx. 7 días (R3: recordatorio día 3, aviso 5 h antes, cancela día 7) → el **Jefe de Almacén** confirma («Llegó bien») o hace la **Devolución** con razón → factura en 48 h, **R2 la valida antes de pagar** (inválida = compra cancelada y material devuelto) → R4 expediente a Finanzas → **R5 paga en automático** en el banco emulado (errores: general con 3 reintentos; saldo, monto, divisa, CLABE → Finanzas reintenta o cancela). Toda cancelación avisa al proveedor y a Adquisiciones por correo y Telegram (`cancelacion.py`). Ver `docs/CAMBIOS_AL_DISENO.md`.
**3.1 (20 nov 2026):** **Adquisiciones ya no usa Logix.** Las requisiciones llegan como **eventos simulados** (`simulador.py`, robot R0, cada `MINUTOS_ENTRE_REQUISICIONES`, 60 min): formato 001-03, partida presupuestal (21101, 21401, 21601, 24601), justificación y 4 firmas; R1 genera la OC sola con el proveedor fijo de la partida. **Finanzas solo ve las fallas** del banco (pantalla «Fallas de pago»; sin avisos si todo sale bien). El **Jefe de Almacén ve qué se aceptó** (requisición y artículos) y presiona «Aceptar» o «Devolución». Usuarios: `almacen`, `finanzas`, `admin`.
Principio: **automatización por excepción**.

## Pila
Python 3.12+ · CustomTkinter (`panel.py`) · SQL Server + pyodbc (`logix_db`, 15 tablas, bitácora inmutable por trigger) · robot en Python (`robot.py`) · correo (IMAP/SMTP) · **Telegram Bot API** · fpdf2 para los PDF.

## Robots
R0 simulador de requisiciones validadas (`logix/simulador.py`) · R1 genera y envía la OC (`logix/compras.py`) · **R2 validador de facturas** (`cfdi.py`, `validacion.py`, `robot_facturas.py`) · R3 vigilante de plazos (`plazos.py`) · R4 expediente a Finanzas (`expediente.py`, `pdfs.py`) · R5 pago automático (`pagos.py`, `banco_emulado.py`) · R6 avisos (`notificador.py`) · R7 bot de Telegram (`bot_telegram.py`, `telegram.py`). Cancelaciones: `cancelacion.py`.

## Comandos
- Verificar la instalación: `python verificar_instalacion.py`
- Reiniciar la base con datos simulados: `python generar_datos.py`
- Pruebas: `python -m unittest discover -s tests -t .` (32) · `python probar_r2_facturas.py` (10/10) · `python probar_flujo_completo.py` (24/24; **reinicia la base**)
- Evidencias: `python capturar_evidencias.py` (23 capturas en `evidencias/`; **reinicia la base**) · Diagramas: `python diagramas/generar_diagramas.py`
- Usar: `INICIAR_LOGIX.bat` (robot + panel). Usuarios `almacen` (Jefe de Almacén), `finanzas`, `admin` con contraseña `logix2026`.
- Git: repositorio `https://github.com/estrella18iortiz-byte/Logix_Automatizacion` (ramas `main` y `develop`). Git está en `C:\Program Files\Git\cmd`.

## Reglas
- **Solo datos simulados.** Nunca uses nombres, RFC, teléfonos ni correos reales.
- **Nunca** escribas, pidas ni muestres el contenido de `.env` (token de Telegram, contraseña de aplicación). `.env` no se sube a Git.
- El trabajo es **individual**: Angela debe entender y poder explicar todo lo que se agregue (tiene una validación oral pendiente). Explica los cambios en lenguaje claro y deja comentarios en español.
- Ella es la autora de los commits. No hagas commits ni pushes sin que lo pida.
- Después de cualquier cambio, corre las pruebas y di el resultado real.
- Si cambias el comportamiento, actualiza `README.md` y `docs/CAMBIOS_AL_DISENO.md`.

## Memoria de Claude
Al iniciar, lee `memoria_claude/` (bitácora de sesiones, resultados de pruebas, explicación de robots y pendientes). Al terminar cada sesión, actualízala. Nunca guardes ahí el contenido de `.env`. **`memoria_claude/` nunca se sube a GitHub ni a internet** (está en `.gitignore`).
