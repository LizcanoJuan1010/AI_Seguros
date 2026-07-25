---
name: presentaciones-seguros
description: Crea o edita presentaciones PowerPoint (.pptx) por tipo de seguro o informes ejecutivos para gerentes, usando OfficeCLI. Usar cuando pidan "presentación", "pptx", "slides" o material comercial.
---

# Presentaciones con OfficeCLI

El binario es **`officecli`** (v1.0.139). Verifica con `officecli --version`; si falta,
ejecuta `bash scripts/setup.sh officecli`. Descubre la sintaxis exacta con la ayuda
integrada antes de construir: `officecli help pptx` (y `officecli help pptx slide`, etc.).

## Presentación comercial por tipo de seguro
1. Trae los productos reales: `curl -s "${SEGURIA_API_URL:-http://localhost:8085}/api/products?tipo=vida"`.
2. Crea la presentación (estructura sugerida de 6 diapositivas):
   - Portada (Tequendama + tipo de seguro), la necesidad que resuelve, productos y
     coberturas comparadas, ejemplo de cotización real, proceso de contratación, cierre.
```bash
officecli create pptx presentacion_vida.pptx
# Añade diapositivas/contenido según la sintaxis que muestre `officecli help pptx`
# (el CLI expone add/set/get/view; usa la ayuda para los argumentos exactos).
officecli view presentacion_vida.pptx --format png   # render para verificar
```
3. Mira el PNG renderizado, corrige lo que se vea mal (ciclo render→ver→corregir) y
   entrega el .pptx como adjunto.

## Alternativa vía MCP (más robusta que shell)
OfficeCLI trae servidor MCP. Regístralo una vez en Hermes y llama sus herramientas en
vez de shell: `officecli mcp claude` (o añade `officecli mcp` como servidor stdio a la
config MCP de Hermes). La herramienta MCP recibe un único parámetro `command` que se
pasa verbatim al CLI, p.ej. `{"command":"help pptx"}`.

## Informe ejecutivo para gerentes
Igual, pero con datos de `GET /api/insights/summary` (KPIs, funnel, por país). Una
diapositiva por sección, gráficos de barras para país/producto.

Guarda los archivos en `generated_docs/` del workspace.
