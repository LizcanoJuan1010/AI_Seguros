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
app.use((req, res, next) => {
  const provided = req.headers.apikey || req.query.apikey || "";
  const providedBuf = Buffer.from(String(provided), "utf8");
  // timingSafeEqual exige mismo length; pad/truncate para evitar distinct-length leak
  const ok =
    providedBuf.length === API_KEY_BUF.length &&
    crypto.timingSafeEqual(providedBuf, API_KEY_BUF);
  if (!ok) {
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
  if (fs.existsSync(AUTH_DIR)) {
    for (const dir of fs.readdirSync(AUTH_DIR)) {
      const credsFile = path.join(AUTH_DIR, dir, "creds.json");
      if (fs.existsSync(credsFile)) {
        logger.info({ instance: dir }, "Restoring saved instance");
        createBaileysConnection(dir).catch((err) => {
          logger.error({ instance: dir, err: err.message }, "Failed to restore instance");
        });
      }
    }
  }
});
