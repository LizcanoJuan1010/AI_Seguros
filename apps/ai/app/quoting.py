"""Motor de cotización determinista.

prima_mensual = prima_base * factor_edad * factores_de_riesgo * (suma/suma_base)
(+ componente porcentual sobre valor del bien en auto/hogar/pyme),
convertida a moneda local con la última tasa FX del regulador.
"""
import json
from typing import Any

import psycopg

from .db import COUNTRY_CURRENCY, COUNTRY_NAMES, latest_fx


def _age_factor(age_table: dict[str, float], age: int) -> tuple[float, str]:
    bands = []
    for rng, factor in age_table.items():
        lo, hi = (int(x) for x in rng.split("-"))
        if lo <= age <= hi:
            return factor, rng
        bands.append((lo, hi, rng, factor))
    # Fuera de todas las bandas: usar la banda CONTIGUA (la más cercana en edad),
    # no la de mayor factor.
    lo_min = min(bands, key=lambda b: b[0])
    hi_max = max(bands, key=lambda b: b[1])
    lo, hi, rng, factor = lo_min if age < lo_min[0] else hi_max
    return factor, f"{rng} (extrapolado)"


def quote_product(conn: psycopg.Connection, product: dict, *,
                  country: str, age: int | None, sum_assured_usd: float | None,
                  extras: dict[str, Any]) -> dict[str, Any]:
    factores = json.loads(product["factores"])
    coberturas = json.loads(product["coberturas"])
    suma_base = product["suma_base_usd"]
    suma = sum_assured_usd or suma_base
    breakdown: dict[str, Any] = {"prima_base_usd": product["prima_base_usd"]}

    premium = product["prima_base_usd"] * (suma / suma_base)
    breakdown["ajuste_suma"] = round(suma / suma_base, 3)

    if "edad" in factores and age is not None:
        f, band = _age_factor(factores["edad"], age)
        premium *= f
        breakdown["factor_edad"] = {"banda": band, "factor": f}

    # Factores booleanos declarados en el catálogo (fumador, zona_alto_riesgo, etc.)
    for key, factor in factores.items():
        if key in ("edad",) or key.endswith("_pct") or key.endswith("_por_hijo"):
            continue
        if extras.get(key):
            premium *= factor
            breakdown[f"factor_{key}"] = factor

    # Recargo por dependientes (salud/vida familiar)
    per_child = next((v for k, v in factores.items() if k.endswith("_por_hijo")), None)
    dependents = int(extras.get("dependientes", 0) or 0)
    if per_child and dependents:
        premium *= 1 + per_child * dependents
        breakdown["factor_dependientes"] = {"n": dependents, "recargo": round(per_child * dependents, 3)}

    # Componente % sobre valor del bien (vehículo, inmueble, activos pyme)
    pct_key = next((k for k in factores if k.endswith("_pct")), None)
    asset_value = float(extras.get("valor_bien_usd", 0) or 0)
    if pct_key and asset_value:
        extra_premium = asset_value * factores[pct_key]
        premium += extra_premium
        breakdown["componente_valor_bien_usd"] = round(extra_premium, 2)

    # Viaje: prima por día × días (default de viaje típico si no se informa,
    # nunca cobrar un solo día por omisión)
    if product["prima_por_dia"]:
        days = int(extras.get("dias_viaje", 0) or 0) or 15
        premium *= days
        breakdown["dias_viaje"] = days
        breakdown["dias_asumidos"] = "dias_viaje" not in extras or not extras.get("dias_viaje")

    currency = COUNTRY_CURRENCY.get(country, "USD")
    rate = latest_fx(conn, currency)
    premium_usd = round(premium, 2)
    return {
        "product_id": product["id"],
        "producto": product["nombre"],
        "tipo": product["tipo"],
        "aseguradora": product["aseguradora"],
        "pais": COUNTRY_NAMES.get(country, country),
        "country": country,
        "moneda": currency,
        "suma_asegurada_usd": suma,
        "prima_mensual_usd": premium_usd,
        "prima_mensual_local": round(premium_usd * rate, 2),
        "tasa_fx": rate,
        "coberturas": coberturas,
        "breakdown": breakdown,
        "periodicidad": "por viaje" if product["prima_por_dia"] else "mensual",
    }


def recommend(conn: psycopg.Connection, *, country: str, tipo: str | None,
              age: int | None, sum_assured_usd: float | None,
              budget_monthly_usd: float | None, extras: dict[str, Any],
              max_options: int = 3) -> list[dict[str, Any]]:
    """Cotiza todos los productos elegibles y devuelve las mejores opciones."""
    rows = conn.execute("SELECT * FROM products").fetchall()
    options = []
    for p in rows:
        if country not in json.loads(p["paises"]):
            continue
        if tipo and p["tipo"] != tipo:
            continue
        options.append(quote_product(conn, p, country=country, age=age,
                                     sum_assured_usd=sum_assured_usd, extras=extras))
    if budget_monthly_usd:
        in_budget = [o for o in options if o["prima_mensual_usd"] <= budget_monthly_usd]
        options = in_budget or sorted(options, key=lambda o: o["prima_mensual_usd"])
    options.sort(key=lambda o: o["prima_mensual_usd"])
    return options[:max_options]
