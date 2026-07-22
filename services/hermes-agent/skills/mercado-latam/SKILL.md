---
name: mercado-latam
description: Conocimiento del mercado asegurador LATAM - aseguradoras reales por país y tasas de cambio, desde los datos regulatorios del repo. Usar cuando pregunten por una aseguradora, comparen mercados o pidan contexto país.
---

# Mercado asegurador LATAM

Datos copiados de reguladores oficiales (SSN, SFC, SBS, SUGESE, SSRP, etc.) en
`data/market/` del repo:

- `aseguradoras_latam.csv` — 1.338 aseguradoras reales con nombre canónico, columnas:
  `country, raw_table, source_entity_code, source_entity_name, row_count,
  canonical_entity_name, notes`.
- `fx_rates.csv` — tasas moneda local/USD por fecha (ARS, CLP, COP, CRC, DOP, GTQ,
  MXN, PEN, UYU).

## Uso típico
```bash
# ¿Existe/cómo se llama formalmente una aseguradora que menciona el cliente?
grep -i "sura" data/market/aseguradoras_latam.csv | cut -d, -f1,6 | sort -u

# ¿Qué aseguradoras hay en un país?
awk -F, '$1=="PE" {print $6}' data/market/aseguradoras_latam.csv | sort -u | head -30
```

Úsalo para: validar nombres de aseguradoras que el cliente menciona, dar contexto de
mercado a gerentes ("en Perú operan N aseguradoras de vida"), y responder con
propiedad sobre monedas. Las primas SIEMPRE salen de la API, no de estos archivos.
