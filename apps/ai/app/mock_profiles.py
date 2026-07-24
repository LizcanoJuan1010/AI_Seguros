"""Perfiles de prueba (mock) para poder construir/validar el cruce con datos
externos (ej. el CSV de afiliados Colsubsidio) sin esperar volumen real de
conversaciones. Genera casos sintéticos variados, los pasa por el MISMO
`profiling.build_profile` que usan las conversaciones reales — el resultado
tiene la misma forma que un perfil real, solo que `fuente='mock'` lo marca
como sintético para no confundirlo en ningún análisis.

Determinista (`random.seed(42)`), mismo patrón que `_seed_demo` en `db.py`.
"""
import random

from . import profiling
from .call_profiling import _save_profile

_NOMBRES_F = ("Valentina", "Camila", "Isabella", "Mariana", "Daniela", "Paula", "Laura")
_NOMBRES_M = ("Andrés", "Santiago", "Julián", "Felipe", "Mateo", "Nicolás", "Sebastián")
_APELLIDOS = ("Gómez", "Rodríguez", "Martínez", "López", "García", "Pérez", "Ramírez")
_CIUDADES = ("Bogotá", "Medellín", "Cali", "Barranquilla", "Bucaramanga")
_OCUPACIONES = ("Ingeniera", "Comerciante independiente", "Docente", "Conductor",
                "Enfermera", "Administrador", "Diseñador")
_ESTADOS_CIVILES = ("Soltero", "Casado", "Unión libre", "Divorciado", "Viudo")


def _caso_sintetico(i: int, rng: random.Random) -> tuple[str, dict, dict]:
    """Un (phone, datos, contexto) sintético — mismo shape que `datos` real
    del intake (ver requisitos_seguros.json), variando las dimensiones clave
    que mueve `profiling.build_profile` (edad, familia, ingresos, activos)."""
    sexo = rng.choice(("F", "M"))
    nombre = rng.choice(_NOMBRES_F if sexo == "F" else _NOMBRES_M)
    apellido = rng.choice(_APELLIDOS)
    edad = rng.randint(19, 78)
    anio_nac = 2026 - edad
    dependientes = rng.choice([0, 0, 1, 2, 3])
    estado_civil = rng.choice(_ESTADOS_CIVILES)
    ingresos = rng.choice([1_300_000, 2_200_000, 3_500_000, 5_000_000, 8_500_000, 15_000_000])
    tiene_vehiculo = rng.random() < 0.4
    es_propietario = rng.random() < 0.35
    tiene_negocio = rng.random() < 0.2
    fumador = rng.random() < 0.15

    datos: dict = {
        "nombre_completo": f"{nombre} {apellido}",
        "sexo": sexo,
        "fecha_nacimiento": f"{anio_nac}-06-15",
        "ciudad": rng.choice(_CIUDADES),
        "ocupacion": rng.choice(_OCUPACIONES),
        "ingresos_mensuales": ingresos,
        "estado_civil": estado_civil,
        "dependientes": dependientes,
        "fumador": "sí" if fumador else "no",
        "enfermedades": "ninguna",
        "preexistencias": "ninguna",
        "deportes_riesgo": "no",
        "es_pep": False,
        "autoriza_habeas_data": True,
    }
    if tiene_vehiculo:
        datos.update({"placa": f"MOK{100 + i}", "marca": "Mock Motors",
                     "modelo_anio": rng.randint(2015, 2025)})
    if es_propietario:
        datos.update({"tenencia": "propietario",
                     "valor_inmueble": rng.choice([180_000_000, 320_000_000, 500_000_000])})
    if tiene_negocio:
        datos.update({"actividad_economica": "independiente", "nit": f"90012345{i}"})

    contexto = {"num_mensajes": rng.randint(2, 12), "cotizo": rng.random() < 0.4,
                "consintio": True}
    phone = f"+57300{700000 + i}"
    return phone, datos, contexto


def seed_mock_profiles(conn, n: int = 15) -> int:
    """Siembra `n` perfiles sintéticos en `customer_profile` (fuente='mock').
    Devuelve cuántos se insertaron. Determinista: mismos `n` -> mismos datos."""
    rng = random.Random(42)
    count = 0
    for i in range(n):
        phone, datos, contexto = _caso_sintetico(i, rng)
        perfil = profiling.build_profile(datos, contexto)
        _save_profile(conn, phone, perfil, fuente="mock")
        count += 1
    return count
