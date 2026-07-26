"""
Data models for the lead management backend.

These are plain dataclasses - no ORM, no database.  They define the shape
of the data that flows between the voice agent and the lead service.
"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class Vehicle:
    """El vehículo del cliente (adaptado de PropertyAddress — seguro de carro,
    no de hogar)."""
    brand: str
    model: str
    year: int
    city: str

    def display(self) -> str:
        return f"{self.brand} {self.model} {self.year}, {self.city}"


@dataclass
class Lead:
    """A lead from the CRM - represents a consumer who submitted a quote request."""
    lead_id: str
    first_name: str
    last_name: str
    phone: str
    email: str
    vehicle: Vehicle
    current_insurance_status: str   # switching, first_time_buyer, lapsed, none
    desired_coverage_start: str     # YYYY-MM-DD
    quote_submitted_at: str         # ISO 8601 timestamp
    source: str = "website_quote_form"

    def display(self) -> str:
        """Human-readable summary for logging."""
        return (
            f"{self.first_name} {self.last_name} | "
            f"{self.vehicle.display()} | "
            f"Coverage start: {self.desired_coverage_start}"
        )


@dataclass
class ConsultationSlot:
    """An available time slot for a licensed agent consultation."""
    datetime: str       # ISO 8601 with timezone (e.g. 2026-03-05T10:00:00-06:00)
    agent_name: str

    def display(self) -> str:
        """Descripción legible para que el agente la lea en voz alta.

        En español, sin depender del locale del sistema (python:3.12-slim no
        trae es_CO/es_ES — strftime('%A'/'%B') daría nombres en inglés)."""
        _DIAS_ES = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
        _MESES_ES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
                    "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
        try:
            # Bug real del repo original: `datetime_module.fromisoformat` no
            # existe (fromisoformat es de la CLASE datetime.datetime, no del
            # módulo) — el except Exception amplio lo enmascaraba
            # silenciosamente y siempre caía al string ISO crudo, incluso en
            # inglés.
            dt = datetime_module.datetime.fromisoformat(self.datetime)
            hour = dt.hour
            periodo = "a.m." if hour < 12 else "p.m."
            display_hour = hour if hour <= 12 else hour - 12
            if display_hour == 0:
                display_hour = 12
            fecha = f"{_DIAS_ES[dt.weekday()]} {dt.day} de {_MESES_ES[dt.month - 1]}"
            return f"{fecha} a las {display_hour} {periodo} con {self.agent_name}"
        except Exception:
            return f"{self.datetime} con {self.agent_name}"


# Alias to avoid shadowing the datetime field name
import datetime as datetime_module


@dataclass
class Appointment:
    """A booked consultation with a licensed agent."""
    confirmation_id: str
    lead_id: str
    slot: ConsultationSlot
    booked_at: datetime = field(default_factory=datetime.now)

    def display(self) -> str:
        return f"Consultation {self.confirmation_id}: {self.slot.display()}"
