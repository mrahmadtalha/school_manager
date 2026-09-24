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

function wait(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
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

async function startSocket() {
  ensureSessionDir();

  const { state, saveCreds } = await useMultiFileAuthState(SESSION_PATH);

  sock = makeWASocket({
    auth: state,
    printQRInTerminal: false,
    syncFullHistory: false,
  });

  sock.ev.on('connection.update', async (update) => {
    const { connection, lastDisconnect, qr } = update;
    const disconnectMessage = lastDisconnect?.error?.message || '';
    const isSessionCorrupted = /Bad MAC|No matching sessions found|bad session|session.*invalid|session.*corrupt/i.test(disconnectMessage);

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
      qrCode = null;
      status = 'connected';
      statusMessage = 'WhatsApp connected successfully.';
      console.log('WhatsApp connected successfully.');
    }

    if (connection === 'close') {
      const statusCode = lastDisconnect?.error?.output?.statusCode;
      connected = false;

      if (isSessionCorrupted || statusCode === DisconnectReason.badSession) {
        qrCode = null;
        status = 'session_reset';
        statusMessage = 'WhatsApp session was corrupted. Starting a fresh session.';
        lastError = 'Session was invalid. A fresh QR scan is required.';
        console.log('Detected a stale or corrupted WhatsApp session. Resetting auth state...');
        clearSessionDir();
        setTimeout(startSocket, 2000);
        return;
      }

      if (statusCode !== DisconnectReason.loggedOut) {
        status = 'reconnecting';
        statusMessage = 'Connection lost. Reconnecting to WhatsApp...';
        lastError = disconnectMessage || 'Connection closed while reconnecting.';
        console.log('Connection closed, retrying...');
        restartAttempts += 1;
        setTimeout(startSocket, Math.min(10000, 2000 * restartAttempts));
      } else {
        qrCode = null;
        status = 'logged_out';
        statusMessage = 'WhatsApp session expired or was logged out. A fresh QR scan is required.';
        lastError = 'Pairing failed. Please scan a fresh QR code.';
        console.log('Session logged out. Resetting session to re-scan.');
        clearSessionDir();
        setTimeout(startSocket, 2000);
      }
    }

    if (connection === 'connecting') {
      connected = false;
      status = 'connecting';
      statusMessage = 'Connecting to WhatsApp...';
    }
  });

  sock.ev.on('creds.update', saveCreds);
}

async function sendMessage(phone, messageText) {
  if (!sock || !connected) {
    throw new Error('WhatsApp not connected yet. Scan the QR code first.');
  }

  const normalized = phone.toString().replace(/[^\d]/g, '');
  if (!normalized) {
    throw new Error('No phone number provided.');
  }

  const jid = `${normalized}@s.whatsapp.net`;
  const target = jidNormalizedUser(jid);

  await sock.sendMessage(target, { text: messageText });
  lastMessageSentAt = new Date().toISOString();
}

async function sendMessageWithRetry(phone, messageText, retries = 3) {
  let lastAttemptError = null;

  for (let attempt = 1; attempt <= retries; attempt += 1) {
    try {
      status = attempt > 1 ? 'retrying' : 'sending';
      statusMessage = attempt > 1 ? `Retrying WhatsApp message send (${attempt}/${retries})...` : 'Sending WhatsApp message...';
      await sendMessage(phone, messageText);
      status = 'connected';
      statusMessage = 'WhatsApp connected successfully.';
      return;
    } catch (error) {
      lastAttemptError = error;
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

async function fetchPendingMessages() {
  try {
    const res = await axios.get(`${FLASK_BASE_URL}/api/whatsapp/pending`);
    return res.data?.items || [];
  } catch (error) {
    lastError = error.message;
    return [];
  }
}

async function markSent(id, status, errorMessage = null) {
  try {
    await axios.post(`${FLASK_BASE_URL}/api/whatsapp/update-status`, {
      id,
      status,
      error_message: errorMessage,
    });
  } catch (error) {
    lastError = error.message;
  }
}

async function processQueue() {
  if (!connected || !sock) {
    return;
  }

  const pending = await fetchPendingMessages();

  for (const item of pending) {
    try {
      await sendMessageWithRetry(item.phone, item.message, 3);
      await markSent(item.id, 'sent');
      console.log(`Sent message ${item.id} to ${item.phone}`);
      await wait(SEND_DELAY_MS);
    } catch (error) {
      console.error(`Failed to send message ${item.id}:`, error.message);
      await markSent(item.id, 'failed', error.message);
    }
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
  if (!phone || !message) {
    return res.status(400).json({ ok: false, message: 'Phone and message are required.' });
  }

  try {
    await sendMessage(phone, message);
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
    // Only check for a leftover/corrupted session from a PREVIOUS run here,
    // once, at true process startup. Do not repeat this on every reconnect —
    // Baileys closes the connection once as a normal part of completing
    // pairing, and re-running this check there would wipe out the session
    // that was just successfully created.
    ensureSessionDir();
    detectStaleSession();

    await startSocket();
    pollTimer = setInterval(processQueue, POLL_INTERVAL_MS);
  } catch (error) {
    status = 'error';
    statusMessage = error.message || 'Failed to initialize WhatsApp service.';
    lastError = statusMessage;
    console.error('WhatsApp initialization failed:', error);
  }
}

function restartServiceIfExited() {
  if (!pollTimer) {
    return;
  }

  if (status === 'error' || status === 'logged_out' || status === 'reconnecting') {
    console.log('WhatsApp service requires a restart, waiting to reinitialize...');
    setTimeout(() => {
      startSocket().catch((error) => {
        status = 'error';
        statusMessage = error.message || 'Failed to restart WhatsApp service.';
        lastError = statusMessage;
        console.error('Failed to restart WhatsApp service:', error);
      });
    }, 3000);
  }
}

if (require.main === module) {
  initialize().catch((error) => {
    status = 'error';
    statusMessage = error.message || 'Failed to initialize WhatsApp service.';
    lastError = statusMessage;
    console.error('Fatal WhatsApp startup error:', error);
  });

  setInterval(() => {
    restartServiceIfExited();
  }, 15000);

  process.on('SIGINT', () => {
    if (pollTimer) clearInterval(pollTimer);
    process.exit(0);
  });
}

module.exports = {
  buildHealthPayload,
  clearSessionDir,
  detectStaleSession,
  ensureSessionDir,
  initialize,
  processQueue,
  sendMessage,
  sendMessageWithRetry,
  startSocket,
  status,
  sock,
};