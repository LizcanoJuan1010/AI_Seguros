# Frontend de Tequendama: build con Vite + servido por nginx con proxy a las APIs.
# Contexto de build: ./apps/frontend
FROM node:20-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
# En producción las llamadas /api las enruta nginx; no hace falta VITE_AI_URL.
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
# nginx.conf se monta desde deploy/ en el compose
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
