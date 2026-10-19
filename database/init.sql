
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

    FOREIGN KEY (horario_id, medico_id)
        REFERENCES horarios(id, medico_id),

    CHECK (estado IN (
        'confirmada', 'cancelada', 'completada'
    ))
);

-- Un horario solo puede tener una cita activa.
CREATE UNIQUE INDEX citas_horario_activo_idx
ON citas(horario_id)
WHERE estado IN ('confirmada', 'completada');

-- Datos completamente ficticios para demostración.
INSERT INTO especialidades (nombre) VALUES
('Medicina General'),
('Dermatología'),
('Cardiología'),
('Pediatría'),
('Traumatología');

INSERT INTO medicos (nombre, especialidad_id) VALUES
('Dra. Camila Rojas', 1),
('Dr. Felipe Torres', 2),
('Dra. Valentina Muñoz', 3),
('Dr. Matías Herrera', 4),
('Dra. Sofía Morales', 5);

INSERT INTO pacientes (nombre, email, telefono) VALUES
('Paciente Demo Uno', 'paciente1@example.com', '+56900000001'),
('Paciente Demo Dos', 'paciente2@example.com', '+56900000002');

-- Horarios futuros de demostración.
-- La zona horaria de Santiago se aplica explícitamente.
INSERT INTO horarios (medico_id, inicio, fin)
SELECT
    m.id,
    (
        (CURRENT_TIMESTAMP AT TIME ZONE 'America/Santiago')::date
        + 1 + TIME '15:00'
    ) AT TIME ZONE 'America/Santiago',
    (
        (CURRENT_TIMESTAMP AT TIME ZONE 'America/Santiago')::date
        + 1 + TIME '15:30'
    ) AT TIME ZONE 'America/Santiago'
FROM medicos m
WHERE m.nombre = 'Dr. Felipe Torres';
