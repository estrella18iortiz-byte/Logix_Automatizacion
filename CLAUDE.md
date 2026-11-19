# Logix 2.0 · contexto para Claude Code

Proyecto escolar de **Angela** (Fundamentos de Ingeniería de Software SCC-1007, reto «Automatiza tu Tec», TecNM Campus Matehuala). Su consultora se llama **Logix**. Responde siempre en **español**.

## Qué es
Seguimiento automatizado del **expediente de compra directa** (Instructivo TecNM-AD-IT-001, formatos 001-01 a 001-05), desde la requisición hasta el pago al proveedor.
Principio: **automatización por excepción**. Si todo cuadra, el expediente avanza solo; si algo no cuadra, se detiene, se explica y se avisa solo a quien debe resolverlo. Las personas solo deciden, autorizan, verifican el bien físico y pagan. **Logix no mueve dinero**: el pago lo hace Recursos Financieros.

## Pila
Python 3.12 · CustomTkinter (`panel.py`) · SQL Server Express + pyodbc (`logix_db`, 20 tablas, bitácora inmutable por trigger) · robot en Python (`robot.py`) · correo (IMAP/SMTP) · **Telegram Bot API** (no WhatsApp) · fpdf2 para los PDF.

## Robots
R1 requisición (`logix/requisiciones.py`) · R2 firmas (`firmas.py`) · **R3 facturas CFDI** (`cfdi.py`, `validacion.py`, `robot_facturas.py`) · R4 expediente (`expediente.py`, `pdfs.py`) · R5 avisos (`notificador.py`) · R6 cierre de ejercicio (`vigilante.py`) · R7 bot de Telegram (`bot_telegram.py`, `telegram.py`) · R8/R9 proveedores y OC (`compras.py`) · R10 conciliación (`pagos.py`).

## Comandos
- Verificar la instalación: `python verificar_instalacion.py`
- Reiniciar la base con datos simulados: `python generar_datos.py`
- Pruebas: `python -m unittest discover -s tests -t .` (22) · `python probar_r3.py` (9/9) · `python probar_flujo_completo.py` (24/24; **reinicia la base**)
- Usar: `INICIAR_LOGIX.bat` (robot + panel). Usuarios de prueba con contraseña `logix2026`.

## Reglas
- **Solo datos simulados.** Nunca uses nombres, RFC, teléfonos ni correos reales.
- **Nunca** escribas, pidas ni muestres el contenido de `.env` (token de Telegram, contraseña de aplicación). `.env` no se sube a Git.
- El trabajo es **individual**: Angela debe entender y poder explicar todo lo que se agregue (tiene una validación oral pendiente). Explica los cambios en lenguaje claro y deja comentarios en español.
- Ella es la autora de los commits. No hagas commits ni pushes sin que lo pida.
- Después de cualquier cambio, corre las pruebas y di el resultado real.
- Si cambias el comportamiento, actualiza `README.md` y avisa qué hay que corregir en los documentos (E2/E3/E4).

## Memoria de Claude
Al iniciar, lee `memoria_claude/` (bitácora de sesiones, resultados de pruebas, explicación de robots y pendientes). Al terminar cada sesión, actualízala. Nunca guardes ahí el contenido de `.env`.

## Pendientes (ver GUIA_ANGELA.md)
Conectar Telegram y correo reales · repositorio Git con su cuenta · SUS con 5 usuarios · video · documentos: correcciones de E1–E3 («Cambios al diseño»: Python en lugar de n8n, Telegram en lugar de WhatsApp, SQL Server 2025), E4 y libro final (entrega: viernes 20 nov, 23:59).
