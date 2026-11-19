/* ==========================================================================
   LOGIX 2.0 · Base de datos logix_db
   Comunicación automatizada entre Adquisiciones y Recursos Financieros:
   la compra YA está aprobada y comprada; Logix mueve la orden de compra,
   la factura, la confirmación de almacén y el pago entre los departamentos.

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
   fecha límite de pagos de diciembre, días del semáforo, horas para recordar. */
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

/* rol: ADQUISICIONES, ALMACEN, FINANZAS, ADMIN */
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

/* ---------- 3. Proveedores --------------------------------------------------- */
CREATE TABLE proveedores (
    id                  INT IDENTITY PRIMARY KEY,
    razon_social        VARCHAR(150) NOT NULL,
    rfc                 VARCHAR(13)  NOT NULL UNIQUE,
    correo              VARCHAR(120) NULL,
    telegram_chat_id    BIGINT       NULL,
    codigo_telegram     CHAR(6)      NULL,
    activo              BIT NOT NULL DEFAULT 1
);

/* Copia SIMULADA de la lista pública del SAT (art. 69-B, EFOS). */
CREATE TABLE sat_lista_69b (
    rfc        VARCHAR(13)  NOT NULL PRIMARY KEY,
    situacion  VARCHAR(40)  NOT NULL                 -- Presunto, Definitivo...
);

/* ---------- 4. Orden de compra (ya aprobada y comprada) --------------------
   Adquisiciones la registra en Logix cuando la compra YA fue autorizada.
   Desde aquí empieza la automatización. */
CREATE TABLE ordenes_compra (
    id            INT IDENTITY PRIMARY KEY,
    folio         VARCHAR(20)   NOT NULL UNIQUE,     -- OC-2026-0001
    proveedor_id  INT NOT NULL REFERENCES proveedores(id),
    area_solicitante VARCHAR(120) NOT NULL,          -- área que pidió el material
    total         DECIMAL(12,2) NOT NULL,            -- con IVA
    estatus       VARCHAR(20)   NOT NULL DEFAULT 'ESPERANDO_FACTURA',
                  -- ESPERANDO_FACTURA, FACTURA_VALIDADA, EN_FINANZAS, DEVUELTA, PAGADA, DETENIDA
    fecha         DATETIME2     NOT NULL DEFAULT SYSDATETIME(),
    registrada_por INT NULL REFERENCES usuarios(id),
    ruta_pdf      VARCHAR(300)  NULL
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

/* ---------- 5. Factura CFDI · la lee el robot R2 ----------------------------- */
CREATE TABLE facturas (
    id            INT IDENTITY PRIMARY KEY,
    oc_id         INT NULL REFERENCES ordenes_compra(id),
    uuid          CHAR(36)      NOT NULL,
    rfc_emisor    VARCHAR(13)   NOT NULL,
    rfc_receptor  VARCHAR(13)   NOT NULL,
    serie_folio   VARCHAR(60)   NULL,
    total         DECIMAL(12,2) NOT NULL,
    fecha_cfdi    DATETIME2     NULL,
    ruta_xml      VARCHAR(300)  NOT NULL,
    ruta_pdf      VARCHAR(300)  NULL,
    resultado     VARCHAR(12)   NOT NULL,            -- VALIDA / RECHAZADA
    detalle       VARCHAR(1000) NULL,
    recibida      DATETIME2     NOT NULL DEFAULT SYSDATETIME()
);
-- Una factura válida no puede registrarse dos veces (UUID repetido).
CREATE UNIQUE INDEX ux_facturas_uuid_valida ON facturas(uuid) WHERE resultado = 'VALIDA';

/* ---------- 6. Recepción en almacén · confirma que el material llegó -------- */
CREATE TABLE recepciones (
    id                 INT IDENTITY PRIMARY KEY,
    oc_id              INT NOT NULL UNIQUE REFERENCES ordenes_compra(id),
    almacen_id         INT NOT NULL REFERENCES usuarios(id),
    fecha_recepcion    DATETIME2 NOT NULL DEFAULT SYSDATETIME(),
    folio_entrada      VARCHAR(20) NOT NULL,         -- entrada y salida simultánea
    folio_salida       VARCHAR(20) NOT NULL,
    fds_entregada      BIT NOT NULL DEFAULT 0,       -- hoja de seguridad, si aplica
    observaciones      VARCHAR(500) NULL
);

/* ---------- 7. Expediente digital · lo arma el robot R3 ---------------------- */
CREATE TABLE expedientes (
    id            INT IDENTITY PRIMARY KEY,
    oc_id         INT NOT NULL UNIQUE REFERENCES ordenes_compra(id),
    ruta_pdf      VARCHAR(300) NOT NULL,
    sha256        CHAR(64)     NOT NULL,
    memorandum    VARCHAR(30)  NOT NULL,             -- MEM-2026-0001
    fecha         DATETIME2    NOT NULL DEFAULT SYSDATETIME()
);

/* ---------- 8. Pago · Recursos Financieros paga fuera de Logix --------------- */
CREATE TABLE pagos (
    id                INT IDENTITY PRIMARY KEY,
    oc_id             INT NOT NULL UNIQUE REFERENCES ordenes_compra(id),
    fecha_turno       DATETIME2 NOT NULL DEFAULT SYSDATETIME(),   -- llegó a Finanzas
    fecha_programada  DATE NULL,
    referencia        VARCHAR(40) NULL,
    fecha_pago        DATE NULL,
    conciliado        BIT NOT NULL DEFAULT 0
);

/* ---------- 9. Excepciones · lo único que revisa una persona -----------------
   Incluye las devoluciones de Finanzas a Adquisiciones (DEVUELTA_FINANZAS). */
CREATE TABLE excepciones (
    id          INT IDENTITY PRIMARY KEY,
    oc_id       INT NULL REFERENCES ordenes_compra(id),
    tipo        VARCHAR(40)   NOT NULL,              -- IMPORTE_DISTINTO, DEVUELTA_FINANZAS...
    detalle     VARCHAR(1000) NOT NULL,
    estatus     VARCHAR(10)   NOT NULL DEFAULT 'ABIERTA',   -- ABIERTA, RESUELTA
    fecha       DATETIME2     NOT NULL DEFAULT SYSDATETIME(),
    resuelta_por INT NULL REFERENCES usuarios(id),
    fecha_resuelta DATETIME2 NULL
);

/* ---------- 10. Notificaciones (correo y Telegram) con reintentos ------------ */
CREATE TABLE notificaciones (
    id            INT IDENTITY PRIMARY KEY,
    canal         VARCHAR(10)   NOT NULL,            -- CORREO, TELEGRAM
    destinatario  VARCHAR(120)  NOT NULL,
    asunto        NVARCHAR(200)  NULL,
    mensaje       NVARCHAR(2000) NOT NULL,
    estatus       VARCHAR(10)   NOT NULL DEFAULT 'PENDIENTE', -- PENDIENTE, ENVIADA, FALLIDA
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
