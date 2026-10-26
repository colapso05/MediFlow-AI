"""Migración: agrega rut a pacientes y rellena las fichas existentes."""
import os
import sys

sys.path.insert(0, r"C:\Users\demis\Projects\MediFlow-AI")
import psycopg
from psycopg.rows import dict_row
from dotenv import load_dotenv

from backend.rut import calcular_dv, validar_rut

load_dotenv(r"C:\Users\demis\Projects\MediFlow-AI\.env")

ASIGNACION = {
    "+56911110001": "16903812-0",
    "+56911110002": "18818860-5",
    "+56911110003": "26289515-7",
    "+56911110004": "17231261-6",
    "+56911110005": "23154570-0",
    "+56911110006": "21785801-1",
    "+56911110007": "24092469-2",
    "+56911110008": "16503194-6",
}

con = psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row)
with con:
    con.execute("ALTER TABLE pacientes ADD COLUMN IF NOT EXISTS rut VARCHAR(12)")

    for telefono, rut in ASIGNACION.items():
        con.execute(
            "UPDATE pacientes SET rut = %s WHERE telefono = %s AND rut IS NULL",
            (rut, telefono),
        )

    # Cualquier ficha sin RUT (creadas en pruebas) recibe uno válido y único.
    pendientes = con.execute(
        "SELECT id, nombre, telefono FROM pacientes WHERE rut IS NULL ORDER BY id"
    ).fetchall()
    base = 27000000
    for fila in pendientes:
        candidato = f"{base + fila['id']}-{calcular_dv(str(base + fila['id']))}"
        con.execute("UPDATE pacientes SET rut = %s WHERE id = %s", (candidato, fila["id"]))
        print("  asignado", candidato, "a", fila["nombre"], fila["telefono"])

    con.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS pacientes_rut_idx ON pacientes (rut)"
    )

    filas = con.execute(
        "SELECT id, nombre, rut, telefono FROM pacientes ORDER BY id"
    ).fetchall()

print(f"\n{len(filas)} pacientes:")
invalidos = 0
for f in filas:
    rut, error = validar_rut(f["rut"])
    if error:
        invalidos += 1
    print(f"  {f['id']:>3} {f['nombre'][:26]:26} {str(f['rut']):12} {f['telefono']} {'OK' if not error else 'ERROR: ' + error}")
print(f"\ninvalidos: {invalidos}")
con.close()
