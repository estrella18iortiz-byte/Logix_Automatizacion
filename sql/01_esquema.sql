/* ==========================================================================
   LOGIX 3.0 · Base de datos logix_db
   Tareas repetitivas con proveedores FIJOS y ya avalados (diagrama 19-nov-2026).
   La compra YA está aprobada. Logix manda la OC, espera el material (máx. 7 días),
   valida la factura, arma el expediente para Recursos Financieros y PAGA en
   automático a través de un BANCO EMULADO. Avisa por correo y Telegram.

   Cómo correrlo (desde la carpeta logix_app):
       python generar_datos.py      (o doble clic en REINICIAR_DATOS.bat)
   ¡OJO! Borra y vuelve a crear la base logix_db (solo datos simulados).
   ========================================================================== */
SET QUOTED_IDENTIFIER ON;
SET ANSI_NULLS ON;
USE master;
GO
IF DB_ID('logix_db') IS NOT NULL
BEGIN
    ALTER DATABASE logix_db SET SINGLE_USER WITH ROLLBACK IMMEDIATE;
    DROP DATABASE logix_db;
END
GO
CREATE DATABASE logix_db;
GO
USE logix_db;
GO

/* ---------- 1. Configuración ------------------------------------------------
   Parámetros que el área puede cambiar sin tocar el código:
   días de espera del material, horas para la factura, reintentos del banco... */
CREATE TABLE parametros (
    clave        VARCHAR(50)  NOT NULL PRIMARY KEY,
    valor        VARCHAR(200) NOT NULL,
    descripcion  VARCHAR(300) NULL
);

/* ---------- 2. Personas y áreas ---------------------------------------------- */
CREATE TABLE areas (
    id      INT IDENTITY PRIMARY KEY,
    nombre  VARCHAR(120) NOT NULL UNIQUE
);

/* rol: ALMACEN (Jefe de Almacén), FINANZAS, ADMIN
   (Adquisiciones ya no usa Logix: las requisiciones validadas llegan como eventos simulados) */
CREATE TABLE usuarios (
    id             INT IDENTITY PRIMARY KEY,
    nombre         VARCHAR(120) NOT NULL,
    usuario        VARCHAR(40)  NOT NULL UNIQUE,
    hash_password  VARCHAR(128) NOT NULL,          -- PBKDF2-SHA256 (RNF-03)
    sal            VARCHAR(64)  NOT NULL,
    rol            VARCHAR(20)  NOT NULL,
    area_id        INT NULL REFERENCES areas(id),
    correo         VARCHAR(120) NULL,
    telegram_chat_id BIGINT     NULL,               -- se llena al vincularse con el bot
    codigo_telegram  CHAR(6)    NULL,               -- código de vinculación (una vez)
    intentos_fallidos INT NOT NULL DEFAULT 0,
    activo         BIT NOT NULL DEFAULT 1           -- sin borrado físico (RNF-04)
);

/* ---------- 3. Proveedores fijos (ya avalados por el Tec) --------------------
   Ya no se revisa la lista 69-B: el catálogo solo tiene proveedores aprobados.
   La CLABE es la cuenta a la que el banco emulado transfiere el pago. */
CREATE TABLE proveedores (
    id                  INT IDENTITY PRIMARY KEY,
    razon_social        VARCHAR(150) NOT NULL,
    rfc                 VARCHAR(13)  NOT NULL UNIQUE,
    correo              VARCHAR(120) NULL,
    clabe               VARCHAR(18)  NOT NULL,       -- cuenta interbancaria (18 dígitos)
    telegram_chat_id    BIGINT       NULL,
    codigo_telegram     CHAR(6)      NULL,
    activo              BIT NOT NULL DEFAULT 1
);

/* ---------- 4. Requisición validada (evento simulado, formato 001-03) --------
   Un departamento del Tec pide material (Recursos Humanos: hojas y bolígrafos;
   Servicios Generales: jabón y detergente...). La requisición YA viene validada con
   sus 4 firmas (Jefe del área, Planeación y Presupuestos, Subdirección y Dirección)
   y con la partida presupuestal del Clasificador por Objeto del Gasto.
   Logix no la captura: la recibe como evento (simulador.py) y de ahí arma la OC. */
CREATE TABLE requisiciones (
    id               INT IDENTITY PRIMARY KEY,
    folio            VARCHAR(20)  NOT NULL UNIQUE,     -- REQ-2026-0001
    area_solicitante VARCHAR(120) NOT NULL,
    partida          CHAR(5)      NOT NULL,            -- 21101, 21601...
    partida_nombre   VARCHAR(120) NOT NULL,
    justificacion    VARCHAR(500) NOT NULL,
    firmas           VARCHAR(500) NOT NULL,            -- quiénes la validaron (4 firmas)
    fecha            DATETIME2    NOT NULL DEFAULT SYSDATETIME()
);

/* ---------- 5. Orden de compra (sale sola de la requisición validada) --------
   El robot R1 la genera en cuanto llega la requisición. Desde aquí corre todo solo.
   estatus:
     ESPERANDO_MATERIAL  OC enviada; el material tiene 7 días para llegar
     MATERIAL_RECIBIDO   el Jefe de Almacén confirmó; se espera la factura (48 h)
     EN_FINANZAS         expediente completo en Recursos Financieros; pago en curso
     PAGO_CON_ERROR      el banco respondió con un error; Finanzas decide
     PAGADA              el banco confirmó el pago (fin)
     CANCELADA           devolución, plazo vencido, factura inválida o pago cancelado (fin) */
CREATE TABLE ordenes_compra (
    id            INT IDENTITY PRIMARY KEY,
    folio         VARCHAR(20)   NOT NULL UNIQUE,     -- OC-2026-0001
    proveedor_id  INT NOT NULL REFERENCES proveedores(id),
    requisicion_id INT NULL REFERENCES requisiciones(id),   -- de qué requisición validada salió
    area_solicitante VARCHAR(120) NOT NULL,          -- área que pidió el material
    total         DECIMAL(12,2) NOT NULL,            -- con IVA
    estatus       VARCHAR(20)   NOT NULL DEFAULT 'ESPERANDO_MATERIAL',
    fecha         DATETIME2     NOT NULL DEFAULT SYSDATETIME(),   -- envío de la OC: inicia los 7 días
    registrada_por INT NULL REFERENCES usuarios(id),  -- NULL: la generó el robot R1
    ruta_pdf      VARCHAR(300)  NULL,
    -- Cancelación (si ocurre): por qué, cuándo y si hay material que regresar al proveedor.
    tipo_cancelacion   VARCHAR(30)   NULL,   -- DEVOLUCION_ALMACEN, MATERIAL_NO_LLEGO, FACTURA_INVALIDA,
                                             -- FACTURA_NO_LLEGO, PAGO_CANCELADO
    motivo_cancelacion VARCHAR(500)  NULL,
    fecha_cancelacion  DATETIME2     NULL,
    material_por_devolver BIT NOT NULL DEFAULT 0,   -- 1 = el material está en almacén y debe regresarse
    material_devuelto     BIT NOT NULL DEFAULT 0
);

/* Renglones de la orden de compra (qué se compró). */
CREATE TABLE oc_detalle (
    id               INT IDENTITY PRIMARY KEY,
    oc_id            INT NOT NULL REFERENCES ordenes_compra(id),
    descripcion      VARCHAR(150)  NOT NULL,
    unidad           VARCHAR(20)   NOT NULL,
    cantidad         DECIMAL(10,2) NOT NULL CHECK (cantidad > 0),
    precio_unitario  DECIMAL(12,2) NOT NULL CHECK (precio_unitario > 0),   -- con IVA
    importe          AS (cantidad * precio_unitario) PERSISTED
);

/* ---------- 5. Factura CFDI · la valida el robot R2 antes de pagar ----------- */
CREATE TABLE facturas (
    id            INT IDENTITY PRIMARY KEY,
    oc_id         INT NULL REFERENCES ordenes_compra(id),
    uuid          CHAR(36)      NOT NULL,
    rfc_emisor    VARCHAR(13)   NOT NULL,
    rfc_receptor  VARCHAR(13)   NOT NULL,
    serie_folio   VARCHAR(60)   NULL,
    total         DECIMAL(12,2) NOT NULL,
    moneda        CHAR(3)       NOT NULL DEFAULT 'MXN',
    fecha_cfdi    DATETIME2     NULL,
    ruta_xml      VARCHAR(300)  NOT NULL,
    resultado     VARCHAR(12)   NOT NULL,            -- VALIDA / RECHAZADA
    detalle       VARCHAR(1000) NULL,
    recibida      DATETIME2     NOT NULL DEFAULT SYSDATETIME()
);
-- Una factura válida no puede registrarse dos veces (UUID repetido).
CREATE UNIQUE INDEX ux_facturas_uuid_valida ON facturas(uuid) WHERE resultado = 'VALIDA';

/* ---------- 6. Recepción en almacén · el Jefe de Almacén confirma ----------
   Solo existe si el material llegó BIEN (la devolución se guarda como cancelación). */
CREATE TABLE recepciones (
    id                 INT IDENTITY PRIMARY KEY,
    oc_id              INT NOT NULL UNIQUE REFERENCES ordenes_compra(id),
    almacen_id         INT NOT NULL REFERENCES usuarios(id),
    fecha_recepcion    DATETIME2 NOT NULL DEFAULT SYSDATETIME(),   -- inicia las 48 h de la factura
    folio_entrada      VARCHAR(20) NOT NULL,         -- entrada y salida simultánea
    folio_salida       VARCHAR(20) NOT NULL,
    observaciones      VARCHAR(500) NULL
);

/* ---------- 7. Expediente digital para Recursos Financieros (robot R4) ------- */
CREATE TABLE expedientes (
    id            INT IDENTITY PRIMARY KEY,
    oc_id         INT NOT NULL UNIQUE REFERENCES ordenes_compra(id),
    ruta_pdf      VARCHAR(300) NOT NULL,
    sha256        CHAR(64)     NOT NULL,
    memorandum    VARCHAR(30)  NOT NULL,             -- MEM-2026-0001
    fecha         DATETIME2    NOT NULL DEFAULT SYSDATETIME()
);

/* ---------- 8. Pago automático (robot R5) ------------------------------------
   Una fila por OC que llegó a Finanzas. Guarda la última respuesta del banco emulado.
   estatus: PROGRAMADO (sale al banco en 5–10 min), EN_PROCESO, REINTENTO (error general: se reintenta solo), ERROR (lo decide
            Finanzas), CONFIRMADO (el banco pagó), CANCELADO (Finanzas canceló). */
CREATE TABLE pagos (
    id                INT IDENTITY PRIMARY KEY,
    oc_id             INT NOT NULL UNIQUE REFERENCES ordenes_compra(id),
    fecha_turno       DATETIME2 NOT NULL DEFAULT SYSDATETIME(),   -- llegó a Finanzas
    monto             DECIMAL(12,2) NOT NULL,
    moneda            CHAR(3)       NOT NULL DEFAULT 'MXN',
    estatus           VARCHAR(12)   NOT NULL DEFAULT 'EN_PROCESO',
    intentos          TINYINT       NOT NULL DEFAULT 0,
    programado_para   DATETIME2     NULL,     -- PROGRAMADO: el robot lo manda al banco a esta hora (5–10 min)
    codigo_error      VARCHAR(30)   NULL,     -- ERROR_GENERAL, SALDO_INSUFICIENTE, MONTO_INCORRECTO,
                                              -- DIVISA_INCORRECTA, CUENTA_INVALIDA
    detalle_error     VARCHAR(500)  NULL,
    referencia_banco  VARCHAR(40)   NULL,     -- clave de rastreo SPEI cuando el banco confirma
    fecha_pago        DATETIME2     NULL
);

/* ---------- 9. BANCO EMULADO ---------------------------------------------------
   Simula al banco del Tec (NO es un banco real). Tiene una cuenta con saldo y
   registra cada transferencia que Logix le pide, con su respuesta. */
CREATE TABLE banco_cuenta (
    id               INT PRIMARY KEY,                 -- siempre 1 (la cuenta del Tec)
    titular          VARCHAR(150)  NOT NULL,
    saldo            DECIMAL(14,2) NOT NULL,
    limite_operacion DECIMAL(14,2) NOT NULL,          -- monto máximo por transferencia
    falla_simulada   VARCHAR(30)   NOT NULL DEFAULT 'NINGUNA'   -- para demostrar los errores
);

CREATE TABLE banco_movimientos (
    id             INT IDENTITY PRIMARY KEY,
    fecha          DATETIME2     NOT NULL DEFAULT SYSDATETIME(),
    referencia     VARCHAR(20)   NOT NULL,          -- folio de la OC que se paga
    clabe_destino  VARCHAR(18)   NOT NULL,
    monto          DECIMAL(12,2) NOT NULL,
    moneda         CHAR(3)       NOT NULL,
    resultado      VARCHAR(30)   NOT NULL,          -- CONFIRMADO o el código del error
    clave_rastreo  VARCHAR(40)   NULL               -- solo si se confirmó
);

/* ---------- 10. Notificaciones (correo y Telegram) con reintentos ------------ */
CREATE TABLE notificaciones (
    id            INT IDENTITY PRIMARY KEY,
    canal         VARCHAR(10)   NOT NULL,            -- CORREO, TELEGRAM
    destinatario  VARCHAR(120)  NOT NULL,
    asunto        NVARCHAR(200)  NULL,
    mensaje       NVARCHAR(2000) NOT NULL,
    adjunto       VARCHAR(300)  NULL,               -- PDF que se manda junto con el aviso (ej. la OC)
    estatus       VARCHAR(10)   NOT NULL DEFAULT 'PENDIENTE', -- PENDIENTE, ENVIADA, SIMULADA, FALLIDA
    intentos      TINYINT       NOT NULL DEFAULT 0,
    error         VARCHAR(500)  NULL,
    creada        DATETIME2     NOT NULL DEFAULT SYSDATETIME(),
    enviada       DATETIME2     NULL
);

/* ---------- 11. Bitácora de auditoría (no se puede editar ni borrar) -------- */
CREATE TABLE bitacora (
    id              BIGINT IDENTITY PRIMARY KEY,
    fecha           DATETIME2    NOT NULL DEFAULT SYSDATETIME(),
    actor           VARCHAR(60)  NOT NULL,           -- usuario o 'ROBOT-R2'
    entidad         VARCHAR(30)  NOT NULL,           -- OC, FACTURA, USUARIO...
    entidad_id      INT          NULL,
    accion          VARCHAR(60)  NOT NULL,
    valor_anterior  VARCHAR(200) NULL,
    valor_nuevo     VARCHAR(200) NULL,
    detalle         VARCHAR(1000) NULL
);
GO
CREATE TRIGGER tr_bitacora_inmutable ON bitacora
INSTEAD OF UPDATE, DELETE
AS
BEGIN
    RAISERROR('La bitacora no se puede modificar ni borrar (RNF-04).', 16, 1);
END
GO
PRINT 'Esquema logix_db creado.';
