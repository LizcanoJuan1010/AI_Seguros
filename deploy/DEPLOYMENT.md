# Despliegue de SegurIA (Docker)

> **Estado verificado (2026-07-21):** stack construido y probado end-to-end en esta
> máquina. `seguria-api` (healthy), `seguria-tts` (Kokoro genera MP3 en español) y
> `hermes-agent` (7 skills SegurIA cargadas, alcanza API y TTS por la red interna,
> OfficeCLI incluido) arriba con `docker compose up -d`. Falta solo aportar la
> `DEEPSEEK_API_KEY` (cerebro conversacional) y escanear el QR de WhatsApp.

Todo el sistema corre con `docker compose`. Cuatro servicios en una red interna;
el agente habla con la API y el TTS por nombre de servicio.

```
┌─────────────────────────────────────────────────────────────┐
│ red compose "seguria"                                        │
│                                                              │
│  hermes-agent ──HTTP──> seguria-api:8085  (catálogo/cotizador)│
│   (WhatsApp,   ──HTTP──> seguria-tts:8880  (voz Kokoro)        │
│    persona,    ──CLI───> officecli (en la misma imagen)       │
│    skills)                                                    │
│  baileys-bridge (perfil "baileys", plan B WhatsApp)          │
└─────────────────────────────────────────────────────────────┘
   Puertos publicados al host: 8085 (API+SPA), 8880 (TTS), 8080 (baileys)
```

## 1. Requisitos
- Docker + Docker Compose v2. (Verificado con Docker 29.6.)
- Opcional GPU: sin `nvidia-container-toolkit` el TTS usa la imagen CPU (suficiente
  para notas de voz asíncronas). Con toolkit puedes cambiar a la imagen GPU de Kokoro.

## 2. Configura el entorno
```bash
cp .env.example .env
# Edita .env y pon al menos:
#   DEEPSEEK_API_KEY=sk-...        (obligatoria para el cerebro conversacional)
#   MANAGER_PHONES=+57300...       (números con rol gerente)
#   MANAGER_API_KEY / SERVICE_API_KEY  (cambia los defaults demo en producción)
```

## 3. Arranca el stack
```bash
docker compose up -d --build           # API + TTS + agente Hermes
docker compose ps                      # todos "Up" / healthy
```
- SPA y API: http://localhost:8085  (chat cliente + panel gerencial)
- TTS (docs): http://localhost:8880/docs
- Pruébalo sin WhatsApp: abre la SPA, o `curl` los endpoints (ver README).

## 4. Conecta WhatsApp (emparejamiento QR, una sola vez)
El contenedor `hermes-agent` arranca por defecto en modo `idle` (vivo para configurar).
El compose ya deja el bot **abierto a cualquier remitente** (`WHATSAPP_MODE=bot`,
`WHATSAPP_DM_POLICY=open`, `WHATSAPP_ALLOWED_USERS=*`); para cerrarlo tras la demo,
pon `WHATSAPP_DM_POLICY=pairing` en `.env`.

> ⚠️ **Trampa conocida (regresión Hermes #27602)**: el asistente `hermes whatsapp`
> guarda la sesión en `~/.hermes/whatsapp/session` (ruta *legacy*), que queda **fuera**
> del volumen `hermes-platforms`. Si emparejas en un contenedor efímero, el QR escanea
> bien, el wizard dice "Pairing complete"… y las credenciales se pierden. Por eso el
> procedimiento monta esa ruta y copia la sesión al volumen.

```bash
# 1) cambia el modo a gateway en .env:  HERMES_MODE=gateway
docker compose stop hermes-agent
# 2) empareja en un contenedor aparte con la ruta real de la sesión montada
#    (imprime el QR en la terminal; escanéalo con el teléfono del negocio):
docker compose run --rm -e HERMES_MODE=cli \
  -v "$PWD/.wa-pairing:/root/.hermes/whatsapp" hermes-agent whatsapp
# 3) instala la sesión donde el gateway la busca (ajusta el prefijo del volumen
#    al nombre del proyecto compose: docker volume ls | grep hermes-platforms):
docker run --rm -v "$PWD/.wa-pairing:/src" \
  -v hackathoncolsupcidio_hermes-platforms:/dst alpine \
  sh -c "mkdir -p /dst/whatsapp/session && cp -a /src/session/. /dst/whatsapp/session/"
# 4) arranca el gateway; a partir de aquí la sesión persiste en el volumen:
docker compose up -d hermes-agent
docker exec -it $(docker compose ps -q hermes-agent) \
  sh -c 'tail -f /root/.hermes/platforms/whatsapp/bridge.log'   # "✅ WhatsApp connected!"
```
Si el bot contesta "Provider authentication failed": la imagen es vieja (traía un
`base_url` de OpenRouter que rompe la key de DeepSeek; el entrypoint actual lo fija a
`https://api.deepseek.com`) — reconstruye con `docker compose build hermes-agent`.
Producción sin riesgo de bloqueo: usa WhatsApp Cloud API oficial de Meta (cliente de
referencia en `apps/ai/app/reference/whatsapp_official_client.py`) o el
`baileys-bridge` (`docker compose --profile baileys up -d`).

## 5. Prueba el agente sin WhatsApp (modo headless)
```bash
docker compose exec hermes-agent hermes -z "Soy un cliente de Colombia, tengo 34 años y quiero proteger a mi familia"
```

## 6. Operación
```bash
docker compose logs -f hermes-agent      # ver la actividad del agente
docker compose exec hermes-agent hermes cron list   # tareas (seguimiento proactivo)
docker compose down                      # detener (los volúmenes persisten datos)
```

## Volúmenes que persisten datos
- `seguria-state`: base SQLite (leads, cotizaciones) y PDFs generados.
- `hermes-platforms`: emparejamiento de WhatsApp (creds).
- `hermes-sessions`, `hermes-memories`: memoria e historial del agente.
- `kokoro-cache`: pesos del modelo de voz.

## Alternativa sin Docker (systemd)
Para la API sola como servicio del sistema: `deploy/seguria-api.service`
(ver README). El agente Hermes también puede instalarse nativo con
`hermes gateway install` (ver `agent/README.md`).
