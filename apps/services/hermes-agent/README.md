# Agente Tequendama sobre Hermes — configuración real

> Válido para Hermes Agent v0.19+. Config global en `~/.hermes/`
> (`config.yaml` en YAML, secretos en `~/.hermes/.env`).
> **Para desplegar con Docker** ver [../deploy/DEPLOYMENT.md](../deploy/DEPLOYMENT.md);
> esta guía es para instalación **nativa** en la máquina.

Este directorio es el workspace: `SOUL.md` (persona), `AGENTS.md` (reglas operativas,
leídas del CWD) y `skills/` (7 skills).

## Atajo: cablear todo con un script
```bash
bash ../scripts/deploy_agent.sh        # persona + skills + proveedor DeepSeek (no destructivo)
```
Hace lo mismo que los pasos manuales de abajo, respaldando lo que sobrescribe.

## Pasos manuales

### 1. Instalar Hermes (si no está)
```bash
curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash
hermes --version
```

### 2. Conectar DeepSeek (proveedor integrado, no interactivo)
```bash
echo "DEEPSEEK_API_KEY=sk-tu-key" >> ~/.hermes/.env
hermes config set model.provider deepseek
hermes config set model.default  deepseek-v4-flash   # deepseek-v4-pro para análisis gerencial
```
Alternativas: `provider: custom` + `base_url: https://api.deepseek.com` (OpenAI-compatible),
u OpenRouter/Anthropic.

### 3. Cargar la persona y las skills de Tequendama
- **Persona** (SOUL.md es GLOBAL en Hermes, no se lee del CWD):
  ```bash
  cp SOUL.md ~/.hermes/SOUL.md      # respalda antes si ya tenías uno
  ```
- **Skills** (Hermes las descubre en `~/.hermes/skills/`, no en el CWD): enlaza cada una:
  ```bash
  for d in skills/*/; do ln -sfn "$(pwd)/$d" ~/.hermes/skills/"seguria-$(basename "$d")"; done
  ```
  (o añade la carpeta a `skills.external_dirs` en `config.yaml`).
- **Reglas del proyecto**: `AGENTS.md` SÍ se lee del CWD, así que arranca desde aquí.

### 4. Arrancar el agente
```bash
cd /home/juan/dev/HackathonColsupcidio/agent && hermes      # TUI interactivo
# o headless / una sola respuesta:
hermes -z "Soy de Colombia, 34 años, quiero proteger a mi familia"
```
Verifica en el TUI: `/personality` (Tequendama) y `/skills` (las 7 seguria-*).

### 5. Gateway de WhatsApp
```bash
echo "WHATSAPP_ENABLED=true" >> ~/.hermes/.env
hermes gateway install     # crea el servicio systemd de usuario hermes-gateway
hermes whatsapp            # imprime el QR; escanéalo con el teléfono del negocio
hermes gateway status
```
El emparejamiento persiste en `~/.hermes/platforms/whatsapp/`. Las notas de voz
entrantes se transcriben solas (STT integrado); las salientes usan la skill `voz`.

**Producción**: para evitar bloqueos del número, usa WhatsApp Cloud API oficial de Meta
(cliente en `../services/insurance-api/app/reference/whatsapp_official_client.py`) o el
`baileys-bridge`.

### 6. Voz (Kokoro TTS) y presentaciones (OfficeCLI)
```bash
bash ../scripts/setup.sh voz        # Kokoro-FastAPI en :8880 (Docker, español)
bash ../scripts/setup.sh officecli  # binario officecli
```

### 7. Variables de entorno del agente
```bash
export SEGURIA_API_URL=http://localhost:8085
export MANAGER_API_KEY=demo-gerente-2026
export SERVICE_API_KEY=demo-service-2026
export MANAGER_PHONES=+573001234567   # números con rol gerente (también en el .env de la API)
```

### 8. Seguimiento proactivo (cron, estilo Erica)
En el TUI: `programa una tarea diaria a las 10:00 que ejecute la skill seguimiento-proactivo`.
