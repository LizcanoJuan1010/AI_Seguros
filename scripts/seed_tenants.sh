#!/usr/bin/env bash
# Siembra multitenant demo: equipos, agentes, clientes, leads y alertas.
# Idempotente: si ya existen equipos no vuelve a sembrar.
# Uso: ./scripts/seed_tenants.sh [BASE_URL]   (default http://localhost:3001/api/v1)
set -euo pipefail

BASE="${1:-http://localhost:3001/api/v1}"

existing=$(curl -sf "$BASE/teams" | jq -r '.meta.total')
if [ "$existing" != "0" ]; then
  echo "Ya hay $existing equipo(s); no se siembra de nuevo."
  exit 0
fi

post() { # post <path> <json> -> id
  curl -sf -X POST "$BASE/$1" -H 'Content-Type: application/json' -d "$2" | jq -r '.id'
}

echo "Sembrando equipos..."
T_BOG=$(post teams '{"name":"Equipo Bogotá"}')
T_MED=$(post teams '{"name":"Equipo Medellín"}')

echo "Sembrando agentes..."
U_ELENA=$(post users "{\"fullName\":\"Elena Gómez\",\"email\":\"elena@tequendama.ai\",\"role\":\"GERENTE\",\"teamId\":\"$T_BOG\"}")
U_JULIAN=$(post users "{\"fullName\":\"Julián Restrepo\",\"email\":\"julian@tequendama.ai\",\"role\":\"AGENTE\",\"teamId\":\"$T_BOG\"}")
U_SOFIA=$(post users "{\"fullName\":\"Sofía Méndez\",\"email\":\"sofia@tequendama.ai\",\"role\":\"AGENTE\",\"teamId\":\"$T_BOG\"}")
U_RICARDO=$(post users "{\"fullName\":\"Ricardo Silva\",\"email\":\"ricardo@tequendama.ai\",\"role\":\"GERENTE\",\"teamId\":\"$T_MED\"}")
U_LAURA=$(post users "{\"fullName\":\"Laura Cárdenas\",\"email\":\"laura@tequendama.ai\",\"role\":\"AGENTE\",\"teamId\":\"$T_MED\"}")

echo "Asignando gerentes de equipo..."
curl -sf -X PATCH "$BASE/teams/$T_BOG" -H 'Content-Type: application/json' \
  -d "{\"managerId\":\"$U_ELENA\"}" >/dev/null
curl -sf -X PATCH "$BASE/teams/$T_MED" -H 'Content-Type: application/json' \
  -d "{\"managerId\":\"$U_RICARDO\"}" >/dev/null

echo "Sembrando clientes y leads..."
C1=$(post customers '{"fullName":"Carlos Ruiz","phone":"+573101234567","email":"c.ruiz@email.com","city":"Bogotá"}')
C2=$(post customers '{"fullName":"Marta Ríos","phone":"+573205550199","email":"m.rios@email.com","city":"Bogotá"}')
C3=$(post customers '{"fullName":"Juan Pérez","phone":"+573007776001","email":"j.perez@email.com","city":"Medellín"}')
C4=$(post customers '{"fullName":"Ana Beltrán","phone":"+573007776002","email":"a.beltran@email.com","city":"Medellín"}')

post leads "{\"customerId\":\"$C1\",\"agentId\":\"$U_JULIAN\",\"insuranceType\":\"VIDA\",\"status\":\"CONTACTADO\",\"intent\":\"CALIENTE\"}" >/dev/null
post leads "{\"customerId\":\"$C2\",\"agentId\":\"$U_SOFIA\",\"insuranceType\":\"AUTO\",\"status\":\"COTIZADO\",\"intent\":\"TIBIO\"}" >/dev/null
post leads "{\"customerId\":\"$C3\",\"agentId\":\"$U_LAURA\",\"insuranceType\":\"SALUD\",\"status\":\"NUEVO\",\"intent\":\"FRIO\"}" >/dev/null
post leads "{\"customerId\":\"$C4\",\"agentId\":\"$U_LAURA\",\"insuranceType\":\"VIDA\",\"status\":\"NEGOCIACION\",\"intent\":\"CALIENTE\"}" >/dev/null

echo "Sembrando alertas..."
post alerts "{\"teamId\":\"$T_BOG\",\"message\":\"Hay 3 leads VIP esperando contacto hace más de 15 min.\",\"severity\":\"alta\"}" >/dev/null
post alerts "{\"teamId\":\"$T_BOG\",\"message\":\"Campaña Seguros Vida bajó un 10% en la última hora.\",\"severity\":\"media\"}" >/dev/null
post alerts "{\"teamId\":\"$T_MED\",\"message\":\"Lead caliente de SALUD sin asignar en Medellín.\",\"severity\":\"alta\"}" >/dev/null

echo "OK: 2 equipos, 5 usuarios, 4 clientes, 4 leads, 3 alertas."
