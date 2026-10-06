const express = require('express');
const axios = require('axios');
const fs = require('fs');
const path = require('path');
const { default: makeWASocket, useMultiFileAuthState, DisconnectReason, jidNormalizedUser } = require('baileys');
require('dotenv').config();

const app = express();
app.use(express.json());

const PORT = Number(process.env.APP_PORT || 3001);
const HOST = process.env.APP_HOST || '0.0.0.0';
const FLASK_BASE_URL = process.env.FLASK_BASE_URL || 'http://127.0.0.1:5000';
const BRIDGE_TOKEN = process.env.WHATSAPP_BRIDGE_TOKEN || '';
const POLL_INTERVAL_MS = Number(process.env.POLL_INTERVAL_MS || 5000);
const SEND_DELAY_MS = Number(process.env.SEND_DELAY_MS || 15000);
const SESSION_PATH = path.resolve(process.env.SESSION_PATH || './session');

let sock = null;
let qrCode = null;
let connected = false;
let lastError = null;
let status = 'starting';
let statusMessage = 'Starting WhatsApp service...';
let pollTimer = null;
let lastMessageSentAt = null;
let restartAttempts = 0;
let queueProcessing = false;
let socketStarting = false;
let reconnectTimer = null;

function bridgeConfig() {
  return { headers: { 'X-Bridge-Token': BRIDGE_TOKEN } };
}

function wait(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function normalizePhoneNumber(phone) {
  const value = String(phone ?? '').trim();
  if (!value || !/^\+?[\d\s().-]+$/.test(value)) {
    throw new Error('Enter a valid international phone number.');
  }

  let digits = value.replace(/\D/g, '');
  if (digits.startsWith('00')) {
    digits = digits.slice(2);
  } else if (digits.startsWith('0')) {
    digits = `92${digits.slice(1)}`;
  }

  if (!/^[1-9]\d{7,14}$/.test(digits)) {
    throw new Error('Enter a valid international phone number.');
  }
  return digits;
}

function userNumberFromJid(jid) {
  return String(jid || '').split('@')[0].split(':')[0].replace(/\D/g, '');
}

function ensureSessionDir() {
  if (!fs.existsSync(SESSION_PATH)) {
    fs.mkdirSync(SESSION_PATH, { recursive: true });
  }
}

function clearSessionDir() {
  try {
    if (fs.existsSync(SESSION_PATH)) {
      fs.rmSync(SESSION_PATH, { recursive: true, force: true });
    }
    fs.mkdirSync(SESSION_PATH, { recursive: true });
    qrCode = null;
    connected = false;
    sock = null;
    status = 'resetting';
    statusMessage = 'Saved WhatsApp session was invalid. Starting a fresh session...';
    lastError = null;
    console.log('Cleared stale WhatsApp session folder and created a fresh session directory.');
  } catch (error) {
    console.error('Failed to reset WhatsApp session directory:', error.message);
  }
}

function buildHealthPayload() {
  return {
    ok: true,
    connected,
    phonePaired: connected,
    serviceReachable: true,
    messageSent: !!lastMessageSentAt,
    hasQR: !!qrCode,
    status,
    message: statusMessage,
    lastError,
    sessionPath: SESSION_PATH,
    lastMessageSentAt,
  };
}

function detectStaleSession() {
  if (!fs.existsSync(SESSION_PATH)) {
    return false;
  }

  const sessionFiles = fs.readdirSync(SESSION_PATH);
  if (sessionFiles.length === 0) {
    return false;
  }

  const authPatterns = ['creds.json', 'pre-key-1.json'];
  const hasAuthFiles = sessionFiles.some((name) => authPatterns.includes(name) || name.startsWith('pre-key-') || name.startsWith('session-'));
  if (!hasAuthFiles) {
    return false;
  }

  const credsPath = path.join(SESSION_PATH, 'creds.json');
  if (fs.existsSync(credsPath)) {
    try {
      const creds = JSON.parse(fs.readFileSync(credsPath, 'utf8'));
      const looksValid = !!(creds && (creds.me || creds.keys || creds.signalIdentities || creds.auth));
      if (looksValid) {
        console.log('Saved WhatsApp session looks valid; preserving the existing auth state.');
        return false;
      }
    } catch (error) {
      console.warn('Existing WhatsApp session is unreadable; clearing stale auth state.', error.message);
      clearSessionDir();
      return true;
    }
  }

  if (!connected && status !== 'connected') {
    console.log('No usable WhatsApp auth data found; clearing session directory.');
    clearSessionDir();
    return true;
  }

  return false;
}

function scheduleSocketRestart(delay) {
  if (reconnectTimer) return;
  reconnectTimer = setTimeout(() => {
    reconnectTimer = null;
    startSocket().catch((error) => {
      status = 'error';
      statusMessage = error.message || 'Failed to restart WhatsApp service.';
      lastError = statusMessage;
      console.error('Failed to restart WhatsApp service:', error);
    });
  }, delay);
}

async function startSocket() {
  if (socketStarting) return;
  socketStarting = true;

  try {
    ensureSessionDir();
    const { state, saveCreds } = await useMultiFileAuthState(SESSION_PATH);
    const activeSocket = makeWASocket({
      auth: state,
      printQRInTerminal: false,
      syncFullHistory: false,
      // Generous timeouts: Baileys' init-queries handshake regularly exceeds
      // the defaults on slow school connections ("Timed Out" during
      // 'init queries'), and short keep-alives drop good connections.
      connectTimeoutMs: 60000,
      defaultQueryTimeoutMs: 60000,
      keepAliveIntervalMs: 30000,
    });
    sock = activeSocket;

    activeSocket.ev.on('connection.update', async (update) => {
      if (sock !== activeSocket) return;
      const { connection, lastDisconnect, qr } = update;
      const disconnectMessage = lastDisconnect?.error?.message || '';
      const isSessionCorrupted = /\bBad MAC\b|No matching sessions found|bad session|session.*invalid|session.*corrupt/i.test(disconnectMessage);

      if (qr) {
        qrCode = qr;
        connected = false;
        lastError = null;
        status = 'qr_ready';
        statusMessage = 'Scan the WhatsApp QR code on your phone to link the device.';
        console.log('QR generated. Scan it with WhatsApp mobile app.');
      }

      if (connection === 'open') {
        connected = true;
        restartAttempts = 0;
        if (reconnectTimer) {
          clearTimeout(reconnectTimer);
          reconnectTimer = null;
        }
        qrCode = null;
        status = 'connected';
        statusMessage = 'WhatsApp connected successfully.';
        console.log('WhatsApp connected successfully.');
      }

      if (connection === 'close') {
        const statusCode = lastDisconnect?.error?.output?.statusCode;
        connected = false;
        sock = null;

        if (isSessionCorrupted || statusCode === DisconnectReason.badSession) {
          qrCode = null;
          status = 'session_reset';
          statusMessage = 'WhatsApp session was corrupted. Starting a fresh session.';
          lastError = 'Session was invalid. A fresh QR scan is required.';
          console.log('Detected a stale or corrupted WhatsApp session. Resetting auth state...');
          clearSessionDir();
          scheduleSocketRestart(2000);
          return;
        }

        if (statusCode !== DisconnectReason.loggedOut) {
          status = 'reconnecting';
          statusMessage = 'Connection lost. Reconnecting to WhatsApp...';
          lastError = disconnectMessage || 'Connection closed while reconnecting.';
          console.log('Connection closed, retrying...');
          restartAttempts += 1;
          scheduleSocketRestart(Math.min(10000, 2000 * restartAttempts));
        } else {
          qrCode = null;
          status = 'logged_out';
          statusMessage = 'WhatsApp session expired or was logged out. A fresh QR scan is required.';
          lastError = 'Pairing failed. Please scan a fresh QR code.';
          console.log('Session logged out. Resetting session to re-scan.');
          clearSessionDir();
          scheduleSocketRestart(2000);
        }
      }

      if (connection === 'connecting') {
        connected = false;
        status = 'connecting';
        statusMessage = 'Connecting to WhatsApp...';
      }
    });

    activeSocket.ev.on('creds.update', saveCreds);
  } finally {
    socketStarting = false;
  }
}

async function sendMessage(phone, messageText, queueItemId = null, { allowUnregistered = false } = {}) {
  const activeSocket = sock;
  if (!activeSocket || !connected) {
    throw new Error('WhatsApp not connected yet. Scan the QR code first.');
  }
  if (!activeSocket.user?.id) {
    throw new Error('The QR-linked WhatsApp session is not ready to send messages.');
  }

  const normalized = normalizePhoneNumber(phone);
  const isSelfNumber = normalized === userNumberFromJid(activeSocket.user.id);
  const target = isSelfNumber
    ? activeSocket.user.id
    : jidNormalizedUser(`${normalized}@s.whatsapp.net`);
  if (isSelfNumber) {
    console.warn('Test message targets the connected WhatsApp account; attempting direct send.');
  } else if (typeof activeSocket.onWhatsApp !== 'function') {
    if (allowUnregistered) {
      console.warn('WhatsApp recipient lookup is unavailable; attempting direct test-message send.');
    } else {
      throw new Error('The QR-linked WhatsApp session is not ready to send messages.');
    }
  } else {
    const registration = await activeSocket.onWhatsApp(target);
    if (!Array.isArray(registration) || !registration[0]?.exists) {
      if (allowUnregistered) {
        console.warn(`WhatsApp did not confirm recipient ${normalized}; attempting direct test-message send.`);
      } else {
        throw new Error('Not Registered on WhatsApp');
      }
    }
  }
  if (queueItemId !== null && !await authorizeSend(queueItemId, 'qr_scan')) {
    throw new Error('Message is no longer authorized for sending.');
  }
  if (sock !== activeSocket || !connected) {
    throw new Error('WhatsApp connection changed before the message could be sent.');
  }

  await activeSocket.sendMessage(target, { text: messageText });
  lastMessageSentAt = new Date().toISOString();
}

function sendTestMessage(phone, messageText) {
  if (!phone) {
    const activeSocket = sock;
    if (!activeSocket || !connected || !activeSocket.user?.id) {
      throw new Error('WhatsApp not connected yet. Scan the QR code first.');
    }
    if (sock !== activeSocket || !connected) {
      throw new Error('WhatsApp connection changed before the message could be sent.');
    }
    console.warn('No test recipient supplied; sending to the connected account\'s Message Yourself chat.');
    return activeSocket.sendMessage(activeSocket.user.id, { text: messageText })
      .then(() => { lastMessageSentAt = new Date().toISOString(); });
  }
  return sendMessage(phone, messageText, null, { allowUnregistered: true });
}

async function sendMessageWithRetry(phone, messageText, retries = 3, queueItemId = null) {
  let lastAttemptError = null;

  for (let attempt = 1; attempt <= retries; attempt += 1) {
    try {
      status = attempt > 1 ? 'retrying' : 'sending';
      statusMessage = attempt > 1 ? `Retrying WhatsApp message send (${attempt}/${retries})...` : 'Sending WhatsApp message...';
      await sendMessage(phone, messageText, queueItemId);
      status = 'connected';
      statusMessage = 'WhatsApp connected successfully.';
      return;
    } catch (error) {
      lastAttemptError = error;
      if (error.message === 'Not Registered on WhatsApp') {
        break;
      }
      if (attempt < retries) {
        const delay = 1000 * attempt * 2;
        console.warn(`Message send failed attempt ${attempt}/${retries}. Retrying in ${delay}ms...`);
        status = 'retrying';
        statusMessage = `Retrying message send after temporary error (${attempt}/${retries})...`;
        await wait(delay);
      }
    }
  }

  throw lastAttemptError || new Error('Unable to send WhatsApp message.');
}

async function fetchPendingMessages(integrationMethod) {
  try {
    const query = integrationMethod
      ? `?integration_method=${encodeURIComponent(integrationMethod)}`
      : '';
    const res = await axios.get(`${FLASK_BASE_URL}/api/whatsapp/pending${query}`, bridgeConfig());
    return res.data?.items ? res.data : null;
  } catch (error) {
    lastError = error.message;
    return null;
  }
}

async function markSent(id, messageStatus, errorMessage = null) {
  try {
    await axios.post(`${FLASK_BASE_URL}/api/whatsapp/update-status`, {
      id,
      status: messageStatus,
      error_message: errorMessage,
    }, bridgeConfig());
  } catch (error) {
    lastError = error.message;
  }
}

async function authorizeSend(id, integrationMethod) {
  try {
    const response = await axios.post(
      `${FLASK_BASE_URL}/api/whatsapp/authorize-send`,
      { id, integration_method: integrationMethod },
      bridgeConfig(),
    );
    return response.data?.ok === true;
  } catch (error) {
    lastError = error.message;
    return false;
  }
}

async function fetchIntegrationConfiguration() {
  try {
    const response = await axios.get(`${FLASK_BASE_URL}/api/whatsapp/integration`, bridgeConfig());
    return response.data?.ok ? response.data : null;
  } catch (error) {
    lastError = error.message;
    return null;
  }
}

async function sendCloudApiMessage(item, cloudApi) {
  if (!cloudApi?.access_token || !cloudApi?.phone_number_id || !cloudApi?.business_account_id) {
    throw new Error('WhatsApp Cloud API credentials are incomplete.');
  }
  const recipient = normalizePhoneNumber(item.phone);
  const endpoint = `https://graph.facebook.com/v18.0/${encodeURIComponent(cloudApi.phone_number_id)}/messages`;
  const response = await axios.post(endpoint, {
    messaging_product: 'whatsapp',
    recipient_type: 'individual',
    to: recipient,
    type: 'text',
    text: { preview_url: false, body: item.message },
  }, {
    headers: {
      Authorization: `Bearer ${cloudApi.access_token}`,
      'Content-Type': 'application/json',
    },
    timeout: 20000,
  });
  if (!Array.isArray(response.data?.messages) || !response.data.messages.length) {
    throw new Error('WhatsApp Cloud API did not confirm message acceptance.');
  }
  return response.data;
}

async function dispatchTestMessage(phone, messageText) {
  const integration = await fetchIntegrationConfiguration();
  if (!integration) {
    throw new Error('WhatsApp integration configuration is unavailable.');
  }
  if (integration.integration_method === 'cloud_api') {
    if (!phone) {
      throw new Error('Enter a test recipient for Cloud API delivery.');
    }
    return sendCloudApiMessage({ phone, message: messageText }, integration.cloud_api);
  }
  return sendTestMessage(phone, messageText);
}

async function processQueue() {
  if (queueProcessing) {
    return;
  }

  queueProcessing = true;
  try {
    const integration = await fetchIntegrationConfiguration();
    if (!integration) return;

    const integrationMethod = integration.integration_method;
    const useCloudApi = integrationMethod === 'cloud_api';
    if (useCloudApi) {
      status = 'cloud_api';
      statusMessage = 'Official WhatsApp Cloud API is active.';
    } else if (!connected || !sock) {
      if (!sock && !socketStarting) scheduleSocketRestart(0);
      return;
    } else {
      status = 'connected';
      statusMessage = 'WhatsApp connected successfully.';
    }

    const queue = await fetchPendingMessages(integrationMethod);
    if (!queue) return;
    for (const item of queue.items || []) {
      try {
        if (useCloudApi) {
          if (!await authorizeSend(item.id, integrationMethod)) continue;
          await sendCloudApiMessage(item, queue.cloud_api);
        } else {
          await sendMessageWithRetry(item.phone, item.message, 3, item.id);
        }
        await markSent(item.id, 'sent');
        console.log(`Sent message ${item.id} to ${item.phone}`);
        await wait(SEND_DELAY_MS);
      } catch (error) {
        console.error(`Failed to send message ${item.id}:`, error.message);
        await markSent(item.id, 'failed', error.message);
      }
    }
  } finally {
    queueProcessing = false;
  }
}

app.get('/health', (req, res) => {
  res.json(buildHealthPayload());
});

app.get('/qr', (req, res) => {
  if (!qrCode) {
    return res.status(404).json({ ok: false, message: 'No QR available yet.' });
  }
  res.json({ ok: true, qr: qrCode });
});

app.post('/send-test', async (req, res) => {
  const { phone, message } = req.body;
  if (!message) {
    return res.status(400).json({ ok: false, message: 'Message is required.' });
  }

  try {
    await dispatchTestMessage(phone, message);
    return res.json({ ok: true, message: 'Test message sent successfully.' });
  } catch (error) {
    return res.status(400).json({ ok: false, message: error.message });
  }
});

app.get('/status', (req, res) => {
  res.json({
    ...buildHealthPayload(),
    qrReady: !!qrCode,
  });
});

async function initialize() {
  app.listen(PORT, HOST, () => {
    console.log(`WhatsApp service running on http://${HOST}:${PORT}`);
  });

  try {
    const integration = await fetchIntegrationConfiguration();
    if (integration?.integration_method === 'cloud_api') {
      status = 'cloud_api';
      statusMessage = 'Official WhatsApp Cloud API is active.';
    } else {
      ensureSessionDir();
      detectStaleSession();
      await startSocket();
    }
  } catch (error) {
    status = 'error';
    statusMessage = error.message || 'Failed to initialize WhatsApp service.';
    lastError = statusMessage;
    console.error('WhatsApp initialization failed:', error);
  }
  pollTimer = setInterval(processQueue, POLL_INTERVAL_MS);
}

function restartServiceIfExited() {
  if (!pollTimer) return;
  if (status === 'error' || status === 'logged_out' || status === 'reconnecting') {
    console.log('WhatsApp service requires a restart, waiting to reinitialize...');
    scheduleSocketRestart(3000);
  }
}

if (require.main === module) {
  initialize().catch((error) => {
    status = 'error';
    statusMessage = error.message || 'Failed to initialize WhatsApp service.';
    lastError = statusMessage;
    console.error('Fatal WhatsApp startup error:', error);
  });

  setInterval(restartServiceIfExited, 15000);
  process.on('SIGINT', () => {
    if (pollTimer) clearInterval(pollTimer);
    process.exit(0);
  });
  // Transient Baileys errors (e.g. 'unexpected error in init queries' /
  // 'Timed Out' on flaky school connections) must never kill the bridge:
  // the socket restart logic owns recovery, the process stays up.
  process.on('unhandledRejection', (reason) => {
    console.error('Unhandled promise rejection (bridge stays up):',
                  reason && reason.message ? reason.message : reason);
  });
  process.on('uncaughtException', (error) => {
    console.error('Uncaught exception (bridge stays up):', error.message);
    scheduleSocketRestart(2000);
  });
}

module.exports = {
  buildHealthPayload,
  clearSessionDir,
  detectStaleSession,
  ensureSessionDir,
  fetchPendingMessages,
  initialize,
  processQueue,
  sendMessage,
  sendTestMessage,
  sendMessageWithRetry,
  sendCloudApiMessage,
  dispatchTestMessage,
  startSocket,
  normalizePhoneNumber,
  get sock() { return sock; },
  get status() { return status; },
};