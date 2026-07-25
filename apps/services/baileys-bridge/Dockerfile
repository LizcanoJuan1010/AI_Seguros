FROM node:20-alpine
# ffmpeg: Baileys lo usa internamente para transcodificar el audio entrante
# (mp3 de Kokoro) al ogg/opus que WhatsApp exige para que un audio se vea
# como nota de voz (ptt) y no como un archivo adjunto genérico.
RUN apk add --no-cache git ffmpeg
WORKDIR /app
COPY package.json ./
RUN npm install --omit=dev
COPY index.js ./
# Sin `VOLUME` de Docker aquí: Railway lo rechaza en build ("use Railway
# Volumes") y lo gestiona aparte — el volumen persistente en /data/instances
# se adjunta al servicio vía `railway volume add`, no en la imagen.
EXPOSE 8080
CMD ["node", "index.js"]
