# Logix 2.0 · contexto para Claude Code

Proyecto escolar de **Angela** (Fundamentos de Ingeniería de Software SCC-1007, reto «Automatiza tu Tec», TecNM Campus Matehuala). Su consultora se llama **Logix**. Responde siempre en **español**.

## Qué es
Comunicación automatizada entre **Adquisiciones y Recursos Financieros** para compras directas (Instructivo TecNM-AD-IT-001). **Alcance (desde el 18 nov 2026):** empieza cuando la compra **ya está aprobada y comprada**. Adquisiciones registra la OC → R1 la manda al proveedor → R2 valida su factura XML → Almacén confirma el material → R3 manda el expediente a Finanzas → Finanzas devuelve con motivo o programa y registra el pago, con avisos de ida y vuelta (R4). Requisición, firmas y selección del proveedor quedan **fuera** (pasan antes). Ver `docs/CAMBIOS_AL_DISENO.md`.
Principio: **automatización por excepción**. **Logix no mueve dinero**: el pago lo hace Recursos Financieros.

## Pila
Python 3.12+ · CustomTkinter (`panel.py`) · SQL Server + pyodbc (`logix_db`, 14 tablas, bitácora inmutable por trigger) · robot en Python (`robot.py`) · correo (IMAP/SMTP) · **Telegram Bot API** · fpdf2 para los PDF.

## Robots
R1 envío de OC (`logix/compras.py`) · **R2 facturas CFDI** (`cfdi.py`, `validacion.py`, `robot_facturas.py`) · R3 expediente a Finanzas (`expediente.py`, `pdfs.py`) · R4 comunicación Adquisiciones⇄Finanzas y recordatorios (`pagos.py`) · R5 conciliación (`pagos.py`) · R6 cierre de ejercicio, fecha límite 15 dic (`vigilante.py`) · R7 avisos (`notificador.py`) · R8 bot de Telegram (`bot_telegram.py`, `telegram.py`).

## Comandos
- Verificar la instalación: `python verificar_instalacion.py`
- Reiniciar la base con datos simulados: `python generar_datos.py`
- Pruebas: `python -m unittest discover -s tests -t .` (22) · `python probar_r3.py` (9/9) · `python probar_flujo_completo.py` (19/19; **reinicia la base**)
- Usar: `INICIAR_LOGIX.bat` (robot + panel). Usuarios `adquisiciones`, `almacen`, `finanzas`, `admin` con contraseña `logix2026`.
- Git: repositorio `https://github.com/estrella18iortiz-byte/Logix_Automatizacion` (ramas `main` y `develop`). Git está en `C:\Program Files\Git\cmd`.

## Reglas
- **Solo datos simulados.** Nunca uses nombres, RFC, teléfonos ni correos reales.
- **Nunca** escribas, pidas ni muestres el contenido de `.env` (token de Telegram, contraseña de aplicación). `.env` no se sube a Git.
- El trabajo es **individual**: Angela debe entender y poder explicar todo lo que se agregue (tiene una validación oral pendiente). Explica los cambios en lenguaje claro y deja comentarios en español.
- Ella es la autora de los commits. No hagas commits ni pushes sin que lo pida.
- Después de cualquier cambio, corre las pruebas y di el resultado real.
- Si cambias el comportamiento, actualiza `README.md` y `docs/CAMBIOS_AL_DISENO.md`.

## Memoria de Claude
Al iniciar, lee `memoria_claude/` (bitácora de sesiones, resultados de pruebas, explicación de robots y pendientes). Al terminar cada sesión, actualízala. Nunca guardes ahí el contenido de `.env`.
