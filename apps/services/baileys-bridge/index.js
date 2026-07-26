/**
 * Baileys Bridge — Lightweight WhatsApp API compatible with Evolution API endpoints.
 * Replaces Evolution API with direct Baileys connection.
 */
const express = require("express");
const {
  makeWASocket,
  useMultiFileAuthState,
  DisconnectReason,
  fetchLatestBaileysVersion,
  makeCacheableSignalKeyStore,
  downloadMediaMessage,
} = require("baileys");
const QRCode = require("qrcode");
const pino = require("pino");
const fs = require("fs");
const path = require("path");
const axios = require("axios");
const crypto = require("crypto");

const app = express();
app.use(express.json());

const PORT = process.env.PORT || 8080;
const API_KEY = process.env.API_KEY || "";
const WEBHOOK_URL = process.env.WEBHOOK_URL || "";
const AUTH_DIR = process.env.AUTH_DIR || "/data/instances";
const logger = pino({ level: process.env.LOG_LEVEL || "warn" });
// Reusa la infra de Tequendama (proyecto seguria-ai/apps/ai/app/whatsapp_gateway.py):
// mismo API_KEY sirve como el "webhook secret" que ese lado ya manda/exige.
// Un solo secreto compartido en las dos direcciones, no hace falta un tercero.
const TEQUENDAMA_INBOUND_URL = process.env.TEQUENDAMA_INBOUND_URL || "";
// Instancia única que este bridge mantiene para Tequendama (no multi-tenant
// real como el de Diache): si está seteada, se crea/reconecta sola al arrancar
// aunque todavía no tenga sesión pareada (para poder pedir el QR de una vez).
const DEFAULT_INSTANCE = process.env.DEFAULT_INSTANCE || "";

// ---- Fail-fast: API_KEY es obligatoria y debe tener suficiente entropia ----
// Sin esto, cualquiera que alcance el puerto puede crear instancias, leer QR,
// enviar mensajes y leer contactos. Permitir API_KEY vacia era el bug C13.
if (!API_KEY || API_KEY.length < 32) {
  console.error(
    "[Baileys] FATAL: API_KEY vacia o <32 chars. Set env EVOLUTION_API_KEY " +
    "con al menos 32 caracteres aleatorios antes de arrancar el bridge."
  );
  process.exit(1);
}
const API_KEY_BUF = Buffer.from(API_KEY, "utf8");

// ---- In-memory state per instance ----
const instances = new Map();

function getInstanceState(name) {
  return instances.get(name) || null;
}

// ---- Health check (before auth) ----
app.get("/health", (req, res) => {
  res.json({ status: "ok", instances: instances.size, uptime: process.uptime() });
});

// ---- Auth middleware (timing-safe comparison) ----
// Acepta DOS convenciones de header con el MISMO secreto (API_KEY):
//   - `apikey` (estilo Evolution API, las rutas /instance/* y /message/*)
//   - `x-webhook-secret` (estilo Diache/Tequendama, las rutas planas /send*)
// para que whatsapp_gateway.py de Tequendama no tenga que cambiar cómo llama.
function _safeEqual(provided) {
  const buf = Buffer.from(String(provided || ""), "utf8");
  return buf.length === API_KEY_BUF.length && crypto.timingSafeEqual(buf, API_KEY_BUF);
}

app.use((req, res, next) => {
  const provided = req.headers.apikey || req.query.apikey || req.headers["x-webhook-secret"] || "";
  if (!_safeEqual(provided)) {
    return res.status(401).json({ status: 401, error: "Unauthorized" });
  }
  next();
});

// ---- Webhook helper ----
async function sendWebhook(event, instanceName, data) {
  if (!WEBHOOK_URL) return;
  try {
    await axios.post(WEBHOOK_URL, { event, instance: instanceName, data }, {
      headers: { "Content-Type": "application/json" },
      timeout: 10000,
    });
  } catch (err) {
    logger.warn({ event, instance: instanceName, err: err.message }, "Webhook delivery failed");
  }
}

// ---- Forwarder hacia Tequendama (seguria-ai) ----
// Traduce el mensaje crudo de Baileys al shape EXACTO que
// `apps/ai/app/main.py::WaGatewayInbound` espera — el mismo que ya manda
// wa-gateway/server.js de Diache — para no tener que tocar el lado Python.
function _textoDe(msg) {
  const m = msg.message || {};
  return (
    m.conversation ||
    m.extendedTextMessage?.text ||
    m.imageMessage?.caption ||
    m.videoMessage?.caption ||
    ""
  );
}

// Notas de voz (audioMessage/ptt): se descargan y desencriptan con Baileys
// (downloadMediaMessage pide un re-upload solo si el link original ya
// expiró, por eso necesita `sock.updateMediaMessage`) y se mandan en base64.
// `apps/ai/app/main.py::whatsapp_inbound` las transcribe con Deepgram antes
// de pasarlas al agente — sin transcodificar acá: Deepgram soporta ogg/opus
// directo, que es el formato nativo de las notas de voz de WhatsApp.
async function _audioDe(sock, msg) {
  const audioMsg = msg.message?.audioMessage;
  if (!audioMsg) return null;
  try {
    const buffer = await downloadMediaMessage(
      msg, "buffer", {}, { logger, reuploadRequest: sock.updateMediaMessage }
    );
    return { base64: buffer.toString("base64"), mimetype: audioMsg.mimetype || "audio/ogg" };
  } catch (err) {
    logger.warn({ err: err.message }, "no se pudo descargar la nota de voz");
    return null;
  }
}

async function forwardToTequendama(sock, msg) {
  if (!TEQUENDAMA_INBOUND_URL) return;          // sin configurar = no reenvía (demo)
  if (msg.key?.fromMe) return;                  // eco de nuestros propios envíos
  const jid = msg.key?.remoteJid || "";
  if (jid.endsWith("@g.us") || jid === "status@broadcast") return;  // grupos/estados, no clientes
  const texto = _textoDe(msg).trim();
  const audio = texto ? null : await _audioDe(sock, msg);
  if (!texto && !audio) return;                  // reacciones/protocolo/otros tipos sin texto ni audio
  const from = jid.split("@")[0];
  const payload = { from, text: texto, id: msg.key?.id || null };
  if (audio) {
    payload.audio_base64 = audio.base64;
    payload.audio_mimetype = audio.mimetype;
  }
  try {
    await axios.post(
      TEQUENDAMA_INBOUND_URL,
      { messages: [payload] },
      // timeout más largo que el de texto: audio pesa más y Tequendama
      // transcribe (llamada real a Deepgram) antes de responder al webhook.
      { headers: { "Content-Type": "application/json", "x-webhook-secret": API_KEY }, timeout: 20000 }
    );
  } catch (err) {
    logger.warn({ from, err: err.message }, "no se pudo reenviar el mensaje a Tequendama");
  }
}

// ---- Baileys connection manager ----
async function createBaileysConnection(instanceName) {
  const authDir = path.join(AUTH_DIR, instanceName);
  fs.mkdirSync(authDir, { recursive: true });

  const { state, saveCreds } = await useMultiFileAuthState(authDir);
  const { version } = await fetchLatestBaileysVersion();

  const sock = makeWASocket({
    version,
    auth: {
      creds: state.creds,
      keys: makeCacheableSignalKeyStore(state.keys, logger),
    },
    logger,
    printQRInTerminal: false,
    generateHighQualityLinkPreview: false,
  });

  const inst = {
    name: instanceName,
    sock,
    state: "connecting",
    qr: null,
    qrBase64: null,
    qrCount: 0,
    ownerJid: null,
    profileName: null,
    phoneNumber: null,
    createdAt: new Date().toISOString(),
  };

  instances.set(instanceName, inst);

  sock.ev.on("creds.update", saveCreds);

  sock.ev.on("connection.update", async (update) => {
    const { connection, lastDisconnect, qr } = update;

    if (qr) {
      inst.qrCount++;
      inst.qr = qr;
      try {
        inst.qrBase64 = await QRCode.toDataURL(qr, { width: 300 });
      } catch {
        inst.qrBase64 = null;
      }
      inst.state = "connecting";
      logger.info({ instance: instanceName, qrCount: inst.qrCount }, "QR code generated");
      sendWebhook("qrcode.updated", instanceName, { qrcode: inst.qrBase64 || qr });
    }

    if (connection === "close") {
      inst.qr = null;
      inst.qrBase64 = null;
      const statusCode = lastDisconnect?.error?.output?.statusCode;
      const shouldReconnect = statusCode !== DisconnectReason.loggedOut;

      logger.info({ instance: instanceName, statusCode, shouldReconnect }, "Connection closed");
      inst.state = "close";
      sendWebhook("connection.update", instanceName, { state: "close", statusCode });

      if (shouldReconnect) {
        setTimeout(() => createBaileysConnection(instanceName), 3000);
      } else {
        instances.delete(instanceName);
      }
    }

    if (connection === "open") {
      inst.qr = null;
      inst.qrBase64 = null;
      inst.state = "open";
      inst.ownerJid = sock.user?.id || null;
      inst.profileName = sock.user?.name || null;
      inst.phoneNumber = inst.ownerJid?.split("@")[0]?.split(":")[0] || null;
      logger.info({ instance: instanceName, owner: inst.ownerJid }, "Connected");
      sendWebhook("connection.update", instanceName, { state: "open" });
    }
  });

  sock.ev.on("messages.upsert", async ({ messages, type }) => {
    if (type !== "notify") return;
    for (const msg of messages) {
      sendWebhook("messages.upsert", instanceName, msg);
      forwardToTequendama(sock, msg);
    }
  });

  sock.ev.on("messages.update", async (updates) => {
    for (const update of updates) {
      sendWebhook("messages.update", instanceName, update);
    }
  });

  sock.ev.on("groups.upsert", async (groups) => {
    sendWebhook("groups.upsert", instanceName, groups);
  });

  return inst;
}

// ============================================================
// API Endpoints (Evolution API compatible)
// ============================================================

// ---- Root ----
app.get("/", (req, res) => {
  res.json({
    status: 200,
    message: "Welcome to Baileys Bridge, it is working!",
    version: "1.0.0",
  });
});

// ---- Instance Management ----

app.post("/instance/create", async (req, res) => {
  try {
    const { instanceName } = req.body;
    if (!instanceName) {
      return res.status(400).json({ status: 400, error: "instanceName required" });
    }
    if (instances.has(instanceName)) {
      return res.status(409).json({ status: 409, error: "Instance already exists" });
    }

    const inst = await createBaileysConnection(instanceName);

    // Wait up to 8s for QR
    let waited = 0;
    while (!inst.qrBase64 && inst.state === "connecting" && waited < 8000) {
      await new Promise((r) => setTimeout(r, 500));
      waited += 500;
    }

    res.json({
      instance: {
        instanceName: inst.name,
        status: inst.state,
      },
      qrcode: inst.qrBase64
        ? { base64: inst.qrBase64, code: inst.qr, count: inst.qrCount }
        : { count: inst.qrCount },
    });
  } catch (err) {
    logger.error(err, "Error creating instance");
    res.status(500).json({ status: 500, error: err.message });
  }
});

app.get("/instance/connect/:instanceName", async (req, res) => {
  const { instanceName } = req.params;
  let inst = getInstanceState(instanceName);

  if (!inst) {
    // Auto-create: start new connection (or reconnect from saved auth)
    try {
      inst = await createBaileysConnection(instanceName);
      let waited = 0;
      while (!inst.qrBase64 && inst.state === "connecting" && waited < 8000) {
        await new Promise((r) => setTimeout(r, 500));
        waited += 500;
      }
    } catch (err) {
      return res.status(500).json({ status: 500, error: err.message });
    }
  }

  if (inst.state === "open") {
    return res.json({ instance: { state: "open" } });
  }

  if (inst.qrBase64) {
    res.json({ base64: inst.qrBase64, code: inst.qr, count: inst.qrCount });
  } else {
    res.json({ count: inst.qrCount });
  }
});

app.get("/instance/connectionState/:instanceName", (req, res) => {
  const inst = getInstanceState(req.params.instanceName);
  res.json({
    instance: {
      instanceName: req.params.instanceName,
      state: inst?.state || "disconnected",
      owner: inst?.phoneNumber || "",
    },
  });
});

app.get("/instance/fetchInstances", (req, res) => {
  const list = [];
  for (const [name, inst] of instances) {
    list.push({
      id: name,
      name,
      connectionStatus: inst.state,
      ownerJid: inst.ownerJid,
      profileName: inst.profileName,
      number: inst.phoneNumber,
      integration: "WHATSAPP-BAILEYS",
    });
  }
  // Also check for saved auth dirs without active connections
  if (fs.existsSync(AUTH_DIR)) {
    for (const dir of fs.readdirSync(AUTH_DIR)) {
      if (!instances.has(dir)) {
        list.push({
          id: dir,
          name: dir,
          connectionStatus: "close",
          ownerJid: null,
          integration: "WHATSAPP-BAILEYS",
        });
      }
    }
  }
  res.json(list);
});

app.delete("/instance/logout/:instanceName", async (req, res) => {
  const inst = getInstanceState(req.params.instanceName);
  if (inst?.sock) {
    try { await inst.sock.logout(); } catch {}
  }
  instances.delete(req.params.instanceName);
  res.json({ status: "SUCCESS", response: { message: "Instance logged out" } });
});

app.delete("/instance/delete/:instanceName", async (req, res) => {
  const inst = getInstanceState(req.params.instanceName);
  if (inst?.sock) {
    try { inst.sock.end(); } catch {}
  }
  instances.delete(req.params.instanceName);
  const authDir = path.join(AUTH_DIR, req.params.instanceName);
  fs.rmSync(authDir, { recursive: true, force: true });
  res.json({ status: "SUCCESS", response: { message: "Instance deleted" } });
});

// ---- Messaging ----

app.post("/message/sendText/:instanceName", async (req, res) => {
  const inst = getInstanceState(req.params.instanceName);
  if (!inst?.sock || inst.state !== "open") {
    return res.status(400).json({ status: 400, error: "Instance not connected" });
  }
  const { number, text } = req.body;
  const jid = number.includes("@") ? number : `${number}@s.whatsapp.net`;
  try {
    const result = await inst.sock.sendMessage(jid, { text });
    res.json({ key: result.key, status: "PENDING" });
  } catch (err) {
    res.status(500).json({ status: 500, error: err.message });
  }
});

app.post("/message/sendMedia/:instanceName", async (req, res) => {
  const inst = getInstanceState(req.params.instanceName);
  if (!inst?.sock || inst.state !== "open") {
    return res.status(400).json({ status: 400, error: "Instance not connected" });
  }
  const { number, mediatype, media, caption } = req.body;
  const jid = number.includes("@") ? number : `${number}@s.whatsapp.net`;
  try {
    const msgContent = {};
    if (mediatype === "image") {
      msgContent.image = { url: media };
      if (caption) msgContent.caption = caption;
    } else if (mediatype === "video") {
      msgContent.video = { url: media };
      if (caption) msgContent.caption = caption;
    } else if (mediatype === "document") {
      msgContent.document = { url: media };
      if (caption) msgContent.caption = caption;
    } else {
      msgContent.image = { url: media };
      if (caption) msgContent.caption = caption;
    }
    const result = await inst.sock.sendMessage(jid, msgContent);
    res.json({ key: result.key, status: "PENDING" });
  } catch (err) {
    res.status(500).json({ status: 500, error: err.message });
  }
});

app.post("/message/sendPoll/:instanceName", async (req, res) => {
  const inst = getInstanceState(req.params.instanceName);
  if (!inst?.sock || inst.state !== "open") {
    return res.status(400).json({ status: 400, error: "Instance not connected" });
  }
  const { number, name: question, values, selectableCount } = req.body;
  const jid = number.includes("@") ? number : `${number}@s.whatsapp.net`;
  try {
    const result = await inst.sock.sendMessage(jid, {
      poll: {
        name: question,
        values: values,
        selectableCount: selectableCount || 1,
      },
    });
    res.json({ key: result.key, status: "PENDING" });
  } catch (err) {
    res.status(500).json({ status: 500, error: err.message });
  }
});

// ---- API plana estilo Diache ({tenant,to,...}, no /:instanceName) ----
// `apps/ai/app/whatsapp_gateway.py` (proyecto Tequendama) llama a este
// gateway con esta forma — se agregó para que este bridge pueda sustituir
// directo al gateway Baileys de Diache reusado en producción, sin tener que
// tocar código de ese otro proyecto. `tenant` == `instanceName` de este bridge.

app.post("/send", async (req, res) => {
  const { tenant, to, text } = req.body;
  if (!tenant || !to || !text) {
    return res.status(400).json({ status: 400, error: "tenant, to, text required" });
  }
  const inst = getInstanceState(tenant);
  if (!inst?.sock || inst.state !== "open") {
    return res.status(400).json({ status: 400, error: "Instance not connected" });
  }
  const jid = to.includes("@") ? to : `${to}@s.whatsapp.net`;
  try {
    const result = await inst.sock.sendMessage(jid, { text });
    res.json({ key: result.key, status: "PENDING" });
  } catch (err) {
    res.status(500).json({ status: 500, error: err.message });
  }
});

app.post("/send-audio", async (req, res) => {
  // Nota de voz (ptt): `audio_base64` viaja en base64 (mp3 de Kokoro-FastAPI,
  // ver apps/ai/app/whatsapp_gateway.py::enviar_nota_voz). Baileys transcodifica
  // a ogg/opus con ffmpeg (ver Dockerfile) para que WhatsApp lo muestre como
  // nota de voz real, no como adjunto genérico.
  const { tenant, to, audio_base64, mimetype } = req.body;
  if (!tenant || !to || !audio_base64) {
    return res.status(400).json({ status: 400, error: "tenant, to, audio_base64 required" });
  }
  const inst = getInstanceState(tenant);
  if (!inst?.sock || inst.state !== "open") {
    return res.status(400).json({ status: 400, error: "Instance not connected" });
  }
  const jid = to.includes("@") ? to : `${to}@s.whatsapp.net`;
  try {
    const buffer = Buffer.from(audio_base64, "base64");
    const result = await inst.sock.sendMessage(jid, {
      audio: buffer,
      ptt: true,
      mimetype: mimetype || "audio/mpeg",
    });
    res.json({ key: result.key, status: "PENDING" });
  } catch (err) {
    res.status(500).json({ status: 500, error: err.message });
  }
});

// ---- Contacts ----

app.post("/chat/whatsappNumbers/:instanceName", async (req, res) => {
  const inst = getInstanceState(req.params.instanceName);
  if (!inst?.sock || inst.state !== "open") {
    return res.status(400).json({ status: 400, error: "Instance not connected" });
  }
  const { numbers } = req.body;
  try {
    const results = [];
    for (const num of numbers || []) {
      const jid = num.includes("@") ? num : `${num}@s.whatsapp.net`;
      const [result] = await inst.sock.onWhatsApp(jid);
      results.push({ number: num, exists: result?.exists || false, jid: result?.jid || jid });
    }
    res.json(results);
  } catch (err) {
    res.status(500).json({ status: 500, error: err.message });
  }
});

// ---- Groups ----

app.get("/group/fetchAllGroups/:instanceName", async (req, res) => {
  const inst = getInstanceState(req.params.instanceName);
  if (!inst?.sock || inst.state !== "open") {
    return res.status(400).json({ status: 400, error: "Instance not connected" });
  }
  try {
    const groups = await inst.sock.groupFetchAllParticipating();
    const list = Object.values(groups).map((g) => ({
      id: g.id,
      subject: g.subject,
      size: g.size || g.participants?.length || 0,
      owner: g.owner,
      creation: g.creation,
    }));
    res.json(list);
  } catch (err) {
    res.status(500).json({ status: 500, error: err.message });
  }
});

app.post("/group/acceptInviteCode/:instanceName", async (req, res) => {
  const inst = getInstanceState(req.params.instanceName);
  if (!inst?.sock || inst.state !== "open") {
    return res.status(400).json({ status: 400, error: "Instance not connected" });
  }
  const { inviteCode } = req.body;
  try {
    const groupId = await inst.sock.groupAcceptInvite(inviteCode);
    res.json({ groupId });
  } catch (err) {
    res.status(500).json({ status: 500, error: err.message });
  }
});

// ---- Chat ----

app.post("/chat/findMessages/:instanceName", async (req, res) => {
  // Baileys doesn't have a built-in message store for history queries
  // Return empty array - messages are tracked by PipeOs storage
  res.json([]);
});

// ---- Start server ----
app.listen(PORT, "0.0.0.0", () => {
  logger.info(`Baileys Bridge running on port ${PORT}`);
  console.log(`Baileys Bridge running on port ${PORT}`);

  // Reconnect saved instances on startup
  const restored = new Set();
  if (fs.existsSync(AUTH_DIR)) {
    for (const dir of fs.readdirSync(AUTH_DIR)) {
      const credsFile = path.join(AUTH_DIR, dir, "creds.json");
      if (fs.existsSync(credsFile)) {
        logger.info({ instance: dir }, "Restoring saved instance");
        restored.add(dir);
        createBaileysConnection(dir).catch((err) => {
          logger.error({ instance: dir, err: err.message }, "Failed to restore instance");
        });
      }
    }
  }
  // Instancia única de Tequendama: si no había sesión pareada todavía, la crea
  // igual para que el QR quede disponible de inmediato en
  // GET /instance/connect/:instanceName sin tener que llamar /instance/create a mano.
  if (DEFAULT_INSTANCE && !restored.has(DEFAULT_INSTANCE)) {
    logger.info({ instance: DEFAULT_INSTANCE }, "Creando instancia por defecto (sin pareo previo)");
    createBaileysConnection(DEFAULT_INSTANCE).catch((err) => {
      logger.error({ instance: DEFAULT_INSTANCE, err: err.message }, "Failed to create default instance");
    });
  }
});
