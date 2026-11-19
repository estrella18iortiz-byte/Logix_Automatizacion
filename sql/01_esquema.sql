/* ==========================================================================
   LOGIX 2.0 · Base de datos logix_db
   Seguimiento automatizado del expediente de compra directa (TecNM-AD-IT-001)

   Cómo correrlo (desde la carpeta logix_app):
       sqlcmd -S .\SQLEXPRESS -E -C -I -i sql\01_esquema.sql
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
   Parámetros que el área puede cambiar sin tocar el código (RNF mantenibilidad):
   fecha límite de cierre, días de alerta, horas para recordar y escalar, etc. */
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

/* rol: SOLICITANTE, JEFE_AREA, PRESUPUESTOS, SUBDIRECTOR, DIRECTOR,
        ADQUISICIONES, JEFE_RM, SUBDIR_ADMIN, ALMACEN, FINANZAS, ADMIN      */
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

/* ---------- 3. Catálogos ----------------------------------------------------- */
CREATE TABLE partidas (
    id           INT IDENTITY PRIMARY KEY,
    clave        VARCHAR(10)   NOT NULL UNIQUE,     -- p. ej. 21101
    descripcion  VARCHAR(150)  NOT NULL,
    saldo        DECIMAL(12,2) NOT NULL CHECK (saldo >= 0)
);

/* Conceptos: lo que el área escribe ("plumones") se liga a su partida y a un
   precio de referencia (último precio pagado). Base de R1 (requisición). */
CREATE TABLE conceptos (
    id                 INT IDENTITY PRIMARY KEY,
    descripcion        VARCHAR(150)  NOT NULL UNIQUE,
    unidad             VARCHAR(20)   NOT NULL,
    partida_id         INT NOT NULL REFERENCES partidas(id),
    precio_referencia  DECIMAL(12,2) NOT NULL       -- con IVA, como en la OC
);

/* Catálogo de proveedores (001-04) con su selección (001-01) y evaluación (001-02). */
CREATE TABLE proveedores (
    id                  INT IDENTITY PRIMARY KEY,
    razon_social        VARCHAR(150) NOT NULL,
    rfc                 VARCHAR(13)  NOT NULL UNIQUE,
    correo              VARCHAR(120) NULL,
    telegram_chat_id    BIGINT       NULL,
    codigo_telegram     CHAR(6)      NULL,
    puntaje_seleccion   INT NULL,                    -- 001-01 (mínimo 70)
    puntaje_evaluacion  INT NULL,                    -- 001-02 (mínimo 70)
    fecha_evaluacion    DATE NULL,                   -- se reevalúa cada año
    activo              BIT NOT NULL DEFAULT 1
);

/* Copia SIMULADA de la lista pública del SAT (art. 69-B, EFOS). */
CREATE TABLE sat_lista_69b (
    rfc        VARCHAR(13)  NOT NULL PRIMARY KEY,
    situacion  VARCHAR(40)  NOT NULL                 -- Presunto, Definitivo...
);

/* ---------- 4. Requisición (paso 3 del instructivo) ------------------------- */
CREATE TABLE requisiciones (
    id              INT IDENTITY PRIMARY KEY,
    folio           VARCHAR(20)  NOT NULL UNIQUE,    -- REQ-2026-0001
    area_id         INT NOT NULL REFERENCES areas(id),
    solicitante_id  INT NOT NULL REFERENCES usuarios(id),
    justificacion   VARCHAR(500) NOT NULL,
    total           DECIMAL(12,2) NOT NULL DEFAULT 0,
    estatus         VARCHAR(20)  NOT NULL DEFAULT 'EN_FIRMAS',
                    -- EN_FIRMAS, EN_CORRECCION, VALIDADA, EN_OC, CANCELADA
    fecha           DATETIME2    NOT NULL DEFAULT SYSDATETIME()
);

CREATE TABLE requisicion_detalle (
    id               INT IDENTITY PRIMARY KEY,
    requisicion_id   INT NOT NULL REFERENCES requisiciones(id),
    concepto_id      INT NOT NULL REFERENCES conceptos(id),
    cantidad         DECIMAL(10,2) NOT NULL CHECK (cantidad > 0),
    precio_unitario  DECIMAL(12,2) NOT NULL CHECK (precio_unitario > 0),
    importe          AS (cantidad * precio_unitario) PERSISTED
);

/* ---------- 5. Orden de compra (pasos 4, 5 y 7) ------------------------------ */
CREATE TABLE ordenes_compra (
    id            INT IDENTITY PRIMARY KEY,
    folio         VARCHAR(20)   NOT NULL UNIQUE,     -- OC-2026-0001
    proveedor_id  INT NOT NULL REFERENCES proveedores(id),
    total         DECIMAL(12,2) NOT NULL,            -- con IVA
    estatus       VARCHAR(20)   NOT NULL DEFAULT 'EN_FIRMAS',
                  -- EN_FIRMAS, ESPERANDO_FACTURA, FACTURA_VALIDADA, RECIBIDA,
                  -- EN_FIRMAS_PAGO, EN_FINANZAS, PAGADA, DETENIDA
    fecha         DATETIME2     NOT NULL DEFAULT SYSDATETIME(),
    ruta_pdf      VARCHAR(300)  NULL
);

/* Una OC puede surtir varias requisiciones (campo 9 del formato 001-05). */
CREATE TABLE oc_requisiciones (
    oc_id           INT NOT NULL REFERENCES ordenes_compra(id),
    requisicion_id  INT NOT NULL REFERENCES requisiciones(id),
    PRIMARY KEY (oc_id, requisicion_id)
);

/* ---------- 6. Factura CFDI (paso 9) · la lee el robot R3 -------------------- */
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

/* ---------- 7. Recepción en almacén (pasos 9 y 10) --------------------------- */
CREATE TABLE recepciones (
    id                 INT IDENTITY PRIMARY KEY,
    oc_id              INT NOT NULL UNIQUE REFERENCES ordenes_compra(id),
    almacen_id         INT NOT NULL REFERENCES usuarios(id),
    fecha_recepcion    DATETIME2 NOT NULL DEFAULT SYSDATETIME(),
    folio_entrada      VARCHAR(20) NOT NULL,         -- entrada y salida simultánea
    folio_salida       VARCHAR(20) NOT NULL,
    fds_entregada      BIT NOT NULL DEFAULT 0,       -- hoja de seguridad (paso 8)
    firma_area_id      INT NULL REFERENCES usuarios(id),
    fecha_firma_area   DATETIME2 NULL,
    calificacion       TINYINT NULL CHECK (calificacion BETWEEN 1 AND 5)
);

/* ---------- 8. Expediente digital (paso 12) · lo arma el robot R4 ------------ */
CREATE TABLE expedientes (
    id            INT IDENTITY PRIMARY KEY,
    oc_id         INT NOT NULL UNIQUE REFERENCES ordenes_compra(id),
    ruta_pdf      VARCHAR(300) NOT NULL,
    sha256        CHAR(64)     NOT NULL,
    memorandum    VARCHAR(30)  NOT NULL,             -- MEM-2026-0001
    fecha         DATETIME2    NOT NULL DEFAULT SYSDATETIME()
);

/* ---------- 9. Aprobaciones (un solo motor para todas las firmas) -----------
   tipo = REQ (4 niveles), OC (3) o PAGO (3). Los niveles salen de flujos_aprobacion,
   así se ajustan si el área confirma otro orden, sin cambiar el código. */
CREATE TABLE flujos_aprobacion (
    tipo   VARCHAR(5)  NOT NULL,
    nivel  TINYINT     NOT NULL,
    rol    VARCHAR(20) NOT NULL,
    PRIMARY KEY (tipo, nivel)
);

CREATE TABLE aprobaciones (
    id                INT IDENTITY PRIMARY KEY,
    tipo              VARCHAR(5)  NOT NULL,          -- REQ, OC, PAGO
    referencia_id     INT         NOT NULL,          -- id de requisición u OC
    nivel             TINYINT     NOT NULL,
    rol               VARCHAR(20) NOT NULL,
    estatus           VARCHAR(10) NOT NULL DEFAULT 'PENDIENTE',
                      -- PENDIENTE, APROBADA, DEVUELTA, ESPERA (nivel aún no activo)
    usuario_id        INT NULL REFERENCES usuarios(id),
    motivo            VARCHAR(500) NULL,
    fecha_asignacion  DATETIME2 NULL,
    fecha_respuesta   DATETIME2 NULL,
    recordatorios     TINYINT NOT NULL DEFAULT 0,
    escalada          BIT     NOT NULL DEFAULT 0
);

/* ---------- 10. Pago (pasos 12 y 13) · Finanzas paga fuera de Logix ---------- */
CREATE TABLE pagos (
    id                INT IDENTITY PRIMARY KEY,
    oc_id             INT NOT NULL UNIQUE REFERENCES ordenes_compra(id),
    fecha_turno       DATETIME2 NOT NULL DEFAULT SYSDATETIME(),
    fecha_programada  DATE NULL,
    referencia        VARCHAR(40) NULL,
    fecha_pago        DATE NULL,
    conciliado        BIT NOT NULL DEFAULT 0
);

/* ---------- 11. Excepciones · lo único que revisa una persona ---------------- */
CREATE TABLE excepciones (
    id          INT IDENTITY PRIMARY KEY,
    oc_id       INT NULL REFERENCES ordenes_compra(id),
    tipo        VARCHAR(40)   NOT NULL,              -- IMPORTE_DISTINTO, RFC_DISTINTO...
    detalle     VARCHAR(1000) NOT NULL,
    estatus     VARCHAR(10)   NOT NULL DEFAULT 'ABIERTA',   -- ABIERTA, RESUELTA
    fecha       DATETIME2     NOT NULL DEFAULT SYSDATETIME(),
    resuelta_por INT NULL REFERENCES usuarios(id),
    fecha_resuelta DATETIME2 NULL
);

/* ---------- 12. Notificaciones (correo y Telegram) con reintentos ------------ */
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

/* ---------- 13. Bitácora de auditoría (no se puede editar ni borrar) -------- */
CREATE TABLE bitacora (
    id              BIGINT IDENTITY PRIMARY KEY,
    fecha           DATETIME2    NOT NULL DEFAULT SYSDATETIME(),
    actor           VARCHAR(60)  NOT NULL,           -- usuario o 'ROBOT-R3'
    entidad         VARCHAR(30)  NOT NULL,           -- REQ, OC, FACTURA...
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
