
CREATE EXTENSION IF NOT EXISTS btree_gist;

CREATE TABLE especialidades (
    id SERIAL PRIMARY KEY,
    nombre VARCHAR(100) NOT NULL UNIQUE
);

CREATE TABLE medicos (
    id SERIAL PRIMARY KEY,
    nombre VARCHAR(150) NOT NULL,
    especialidad_id INTEGER NOT NULL
        REFERENCES especialidades(id),
    activo BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE pacientes (
    id SERIAL PRIMARY KEY,
    nombre VARCHAR(150) NOT NULL,
    email VARCHAR(150) UNIQUE,
    telefono VARCHAR(30),
    verificado BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE horarios (
    id SERIAL PRIMARY KEY,
    medico_id INTEGER NOT NULL
        REFERENCES medicos(id),
    inicio TIMESTAMPTZ NOT NULL,
    fin TIMESTAMPTZ NOT NULL,
    CHECK (fin > inicio),
    UNIQUE (id, medico_id),
    EXCLUDE USING gist (
        medico_id WITH =,
        tstzrange(inicio, fin, '[)') WITH &&
    )
);

CREATE TABLE citas (
    id SERIAL PRIMARY KEY,
    paciente_id INTEGER NOT NULL
        REFERENCES pacientes(id),
    medico_id INTEGER NOT NULL
        REFERENCES medicos(id),
    horario_id INTEGER NOT NULL,
    estado VARCHAR(20) NOT NULL DEFAULT 'confirmada',
    creada_en TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    canal VARCHAR(20) NOT NULL DEFAULT 'agente',
    idempotency_key UUID,
    idempotency_fingerprint CHAR(64),

    FOREIGN KEY (horario_id, medico_id)
        REFERENCES horarios(id, medico_id),

    CHECK (estado IN (
        'confirmada', 'cancelada', 'completada'
    )),
    CHECK (canal IN ('agente', 'whatsapp', 'web', 'recepcion'))
);

-- Un horario solo puede tener una cita activa.
CREATE UNIQUE INDEX citas_horario_activo_idx
ON citas(horario_id)
WHERE estado IN ('confirmada', 'completada');

-- Reintentos idempotentes del agente.
CREATE UNIQUE INDEX citas_idempotency_key_idx
ON citas (idempotency_key)
WHERE idempotency_key IS NOT NULL;

CREATE INDEX citas_paciente_idx ON citas (paciente_id);
CREATE INDEX citas_medico_idx ON citas (medico_id);
CREATE INDEX horarios_inicio_idx ON horarios (inicio);

-- Trazabilidad de conversaciones del agente (CRM y auditoría).
CREATE TABLE conversaciones (
    id SERIAL PRIMARY KEY,
    telefono VARCHAR(30),
    sesion VARCHAR(60),
    rol VARCHAR(12) NOT NULL CHECK (rol IN ('user', 'assistant')),
    contenido TEXT NOT NULL,
    creada_en TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX conversaciones_sesion_idx ON conversaciones (sesion, creada_en);

-- ---------------------------------------------------------------------------
-- Datos completamente ficticios para demostración.
-- ---------------------------------------------------------------------------

INSERT INTO especialidades (nombre) VALUES
('Medicina General'),
('Dermatología'),
('Cardiología'),
('Pediatría'),
('Traumatología'),
('Ginecología'),
('Oftalmología'),
('Psiquiatría');

INSERT INTO medicos (nombre, especialidad_id) VALUES
('Dra. Camila Rojas', 1),
('Dr. Felipe Torres', 2),
('Dra. Valentina Muñoz', 3),
('Dr. Matías Herrera', 4),
('Dra. Sofía Morales', 5),
('Dra. Antonia Fuentes', 6),
('Dr. Cristóbal Silva', 7),
('Dra. Josefa Contreras', 8);

INSERT INTO pacientes (nombre, email, telefono, verificado) VALUES
('Paciente Demo Uno', 'paciente1@example.com', '+56911110001', TRUE),
('Paciente Demo Dos', 'paciente2@example.com', '+56911110002', TRUE),
('María José Fuentes', 'mj.fuentes@example.com', '+56911110003', FALSE),
('Rodrigo Peña', 'rodrigo.pena@example.com', '+56911110004', FALSE),
('Carolina Vergara', 'c.vergara@example.com', '+56911110005', FALSE),
('Luis Alarcón', 'luis.alarcon@example.com', '+56911110006', FALSE),
('Fernanda Ibáñez', 'f.ibanez@example.com', '+56911110007', FALSE),
('Jorge Navarrete', 'j.navarrete@example.com', '+56911110008', FALSE);

-- Agenda de las próximas dos semanas: días de semana, 09:00-12:30 y 15:00-18:00.
INSERT INTO horarios (medico_id, inicio, fin)
SELECT
    m.id,
    (d.dia + t.hora) AT TIME ZONE 'America/Santiago',
    (d.dia + t.hora + INTERVAL '30 minutes') AT TIME ZONE 'America/Santiago'
FROM medicos m
CROSS JOIN (
    SELECT (CURRENT_DATE + g) AS dia
    FROM generate_series(1, 14) AS g
    WHERE EXTRACT(ISODOW FROM (CURRENT_DATE + g)) < 6
) AS d
CROSS JOIN (
    VALUES
        (TIME '09:00'), (TIME '09:30'), (TIME '10:00'), (TIME '10:30'),
        (TIME '11:00'), (TIME '11:30'), (TIME '12:00'), (TIME '12:30'),
        (TIME '15:00'), (TIME '15:30'), (TIME '16:00'), (TIME '16:30'),
        (TIME '17:00'), (TIME '17:30'), (TIME '18:00')
) AS t(hora)
WHERE m.activo;

-- Agenda pasada (5 días) para que el CRM muestre historia y citas completadas.
INSERT INTO horarios (medico_id, inicio, fin)
SELECT
    m.id,
    (d.dia + t.hora) AT TIME ZONE 'America/Santiago',
    (d.dia + t.hora + INTERVAL '30 minutes') AT TIME ZONE 'America/Santiago'
FROM medicos m
CROSS JOIN (
    SELECT (CURRENT_DATE - g) AS dia
    FROM generate_series(1, 5) AS g
    WHERE EXTRACT(ISODOW FROM (CURRENT_DATE - g)) < 6
) AS d
CROSS JOIN (
    VALUES (TIME '09:00'), (TIME '10:00'), (TIME '11:00'), (TIME '16:00')
) AS t(hora)
WHERE m.activo;

-- Citas de ejemplo: mezcla de confirmadas y canceladas en días próximos.
WITH cupos AS (
    SELECT
        h.id AS horario_id,
        h.medico_id,
        ROW_NUMBER() OVER (PARTITION BY h.medico_id ORDER BY h.inicio) AS rn
    FROM horarios h
    WHERE h.inicio > NOW()
), elegidos AS (
    SELECT * FROM cupos WHERE rn <= 5
)
INSERT INTO citas (
    paciente_id, medico_id, horario_id, estado, creada_en, canal,
    idempotency_key, idempotency_fingerprint
)
SELECT
    p.id,
    e.medico_id,
    e.horario_id,
    CASE WHEN e.rn = 5 THEN 'cancelada' ELSE 'confirmada' END,
    NOW() - ((e.rn + 1) || ' hours')::interval,
    CASE WHEN e.rn % 2 = 0 THEN 'whatsapp' ELSE 'agente' END,
    gen_random_uuid(),
    md5(random()::text) || md5(random()::text)
FROM elegidos e
JOIN LATERAL (
    SELECT id FROM pacientes
    ORDER BY id
    OFFSET ((e.rn + e.medico_id) % 8)
    LIMIT 1
) AS p ON TRUE;

-- Citas completadas en la agenda pasada.
WITH cupos AS (
    SELECT
        h.id AS horario_id,
        h.medico_id,
        ROW_NUMBER() OVER (PARTITION BY h.medico_id ORDER BY h.inicio DESC) AS rn
    FROM horarios h
    WHERE h.inicio < NOW()
), elegidos AS (
    SELECT * FROM cupos WHERE rn <= 3
)
INSERT INTO citas (
    paciente_id, medico_id, horario_id, estado, creada_en, canal,
    idempotency_key, idempotency_fingerprint
)
SELECT
    p.id,
    e.medico_id,
    e.horario_id,
    'completada',
    NOW() - ((e.rn + 3) || ' days')::interval,
    'recepcion',
    gen_random_uuid(),
    md5(random()::text) || md5(random()::text)
FROM elegidos e
JOIN LATERAL (
    SELECT id FROM pacientes
    ORDER BY id
    OFFSET ((e.rn * 2 + e.medico_id) % 8)
    LIMIT 1
) AS p ON TRUE;
