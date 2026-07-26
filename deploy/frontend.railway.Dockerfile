# Frontend de Tequendama para Railway: mismo build que deploy/frontend.Dockerfile
# (Vite + nginx), pero el nginx.conf se genera en el arranque del contenedor a
# partir de deploy/nginx.railway.conf.template vía `envsubst` — mecanismo nativo
# de la imagen nginx:alpine para archivos en /etc/nginx/templates/*.template
# (se procesan solos a /etc/nginx/conf.d/*.conf antes de arrancar nginx).
# Necesario porque en Railway el puerto (${PORT}) y las URLs internas de
# backend/ai (${BACKEND_INTERNAL_URL}/${AI_INTERNAL_URL}) solo se conocen en
# tiempo de EJECUCIÓN, no de build — ver deploy/RAILWAY.md.
#
# A diferencia de frontend.Dockerfile (contexto ./apps/frontend), este usa
# contexto la RAÍZ del repo — Docker no deja hacer COPY de rutas fuera del
# contexto, y necesitamos copiar tanto apps/frontend/ como deploy/. En
# Railway: Root Directory = "." (raíz), Dockerfile Path =
# "deploy/frontend.railway.Dockerfile".
FROM node:20-alpine AS build
WORKDIR /app
COPY apps/frontend/package.json apps/frontend/package-lock.json ./
RUN npm ci
COPY apps/frontend/. .
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY deploy/nginx.railway.conf.template /etc/nginx/templates/default.conf.template
# Sin EXPOSE fijo: Railway asigna $PORT dinámico, y el template ya usa
# `listen ${PORT}` — nginx escucha ahí una vez sustituido en el arranque.
CMD ["nginx", "-g", "daemon off;"]
