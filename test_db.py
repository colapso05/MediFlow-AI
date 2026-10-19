
import os
import psycopg
from dotenv import load_dotenv

load_dotenv()

with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
    with conn.cursor() as cursor:
        cursor.execute("""
            SELECT m.nombre, e.nombre
            FROM medicos m
            JOIN especialidades e
                ON m.especialidad_id = e.id
            ORDER BY m.id
        """)

        print("Médicos disponibles en MediFlow AI:\n")

        for nombre, especialidad in cursor.fetchall():
            print(f"- {nombre}: {especialidad}")
