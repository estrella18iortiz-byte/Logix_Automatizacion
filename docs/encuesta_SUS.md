# Prueba de usabilidad SUS · Logix 3.1

**Para quién:** al menos **5 usuarios reales** (lo pide la práctica): personal que participa en el proceso. Lo ideal es al menos 1 de **Almacén** y 1 de **Recursos Financieros** (son quienes usan Logix; Adquisiciones ya no, sus requisiciones son eventos simulados); si no se completan 5, suma a otro personal del Tec que haga compras. Todas las personas hacen las 5 tareas. **No anotes nombres**: solo «Participante 1, 2, 3…» y su departamento. Meta: SUS ≥ 70.
**Versión para imprimir:** `docs/Encuesta_SUS_Logix.docx`.
**Duración:** unos 10 minutos por persona. Antes de empezar, corre `REINICIAR_DATOS.bat` y abre `INICIAR_LOGIX.bat`.
Contraseña de todos los usuarios: `logix2026`.

---

## Parte 1 · Tareas (la persona las hace sola; tú solo observas y anotas)

| # | Tarea que le lees a la persona | Usuario | ¿La terminó? (Sí / Con ayuda / No) | Minutos |
|---|---|---|---|---|
| 1 | «Como administrador, simula que llega una requisición del *Departamento de Recursos Humanos*. Dime qué folio de orden de compra generó Logix y quién la validó.» | `admin` | | |
| 2 | «En el Buzón de facturas, simula que el proveedor manda la **factura correcta** de esa orden.» | `admin` | | |
| 3 | «Eres el Jefe de Almacén: llegó el material de esa orden. Revisa qué se aceptó comprar (artículos y cantidades) y **acéptalo** (Logix paga solo).» | `almacen` | | |
| 4 | «La orden *OC-2026-0002* llegó en mal estado: haz la **devolución** escribiendo la razón.» | `almacen` | | |
| 5 | «Eres de Recursos Financieros: revisa si hay alguna **falla de pago** que necesite tu decisión y consulta en qué etapa va la orden de la tarea 1.» | `finanzas` | | |

Notas de lo que se le complicó a la persona:

______________________________________________________________________________

______________________________________________________________________________

---

## Parte 2 · Cuestionario SUS (la persona lo contesta al terminar)

Marca del **1** (totalmente en desacuerdo) al **5** (totalmente de acuerdo).

| # | Afirmación | 1 | 2 | 3 | 4 | 5 |
|---|---|---|---|---|---|---|
| 1 | Creo que me gustaría usar Logix con frecuencia. | ☐ | ☐ | ☐ | ☐ | ☐ |
| 2 | Encontré Logix innecesariamente complejo. | ☐ | ☐ | ☐ | ☐ | ☐ |
| 3 | Pensé que Logix era fácil de usar. | ☐ | ☐ | ☐ | ☐ | ☐ |
| 4 | Creo que necesitaría ayuda de una persona técnica para poder usar Logix. | ☐ | ☐ | ☐ | ☐ | ☐ |
| 5 | Las funciones de Logix están bien integradas. | ☐ | ☐ | ☐ | ☐ | ☐ |
| 6 | Pensé que había demasiadas inconsistencias en Logix. | ☐ | ☐ | ☐ | ☐ | ☐ |
| 7 | Imagino que la mayoría de las personas aprenderían a usar Logix muy rápido. | ☐ | ☐ | ☐ | ☐ | ☐ |
| 8 | Encontré Logix muy complicado de usar. | ☐ | ☐ | ☐ | ☐ | ☐ |
| 9 | Me sentí muy seguro(a) usando Logix. | ☐ | ☐ | ☐ | ☐ | ☐ |
| 10 | Necesité aprender muchas cosas antes de poder usar Logix. | ☐ | ☐ | ☐ | ☐ | ☐ |

¿Qué cambiarías de Logix? ______________________________________________

---

## Cómo se calcula el puntaje (lo hace Claude con tus números)
1. Preguntas **impares** (1, 3, 5, 7, 9): respuesta − 1.
2. Preguntas **pares** (2, 4, 6, 8, 10): 5 − respuesta.
3. Suma las 10 y multiplica por **2.5** → puntaje de 0 a 100 por persona.
4. Promedio de todas las personas = **SUS de Logix**. Más de **68** = por encima del promedio; más de **80** = excelente.

**Para entregarle a Claude:** solo los números de cada persona, por ejemplo `P1: 4,2,5,1,4,2,5,1,4,2`.
