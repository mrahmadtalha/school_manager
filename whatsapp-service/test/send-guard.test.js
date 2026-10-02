const test = require('node:test');
const assert = require('node:assert/strict');
const EventEmitter = require('node:events');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const Module = require('node:module');

function loadServer({ registered, lookupAvailable = true, axiosMock = null }) {
  const sessionPath = fs.mkdtempSync(path.join(os.tmpdir(), 'wa-send-guard-'));
  let sentMessageArgs = null;
  const lookupCalls = [];
  const socket = {
    user: { id: '923009999999:1@s.whatsapp.net' },
    ev: new EventEmitter(),
    onWhatsApp: lookupAvailable ? async (jid) => {
      lookupCalls.push(jid);
      return [{ jid, exists: registered }];
    } : undefined,
    sendMessage: async (...args) => { sentMessageArgs = args; },
  };
  const originalLoad = Module._load;
  Module._load = function (request, parent, isMain) {
    if (request === 'axios' && axiosMock) {
      return axiosMock;
    }
    if (request === 'baileys') {
      return {
        default: () => socket,
        useMultiFileAuthState: async () => ({ state: {}, saveCreds: async () => {} }),
        DisconnectReason: { badSession: 500, loggedOut: 401 },
        jidNormalizedUser: (jid) => jid,
      };
    }
    return originalLoad.call(this, request, parent, isMain);
  };

  process.env.SESSION_PATH = sessionPath;
  process.env.SEND_DELAY_MS = '0';
  delete require.cache[require.resolve('../server.js')];
  const server = require('../server.js');
  Module._load = originalLoad;
  return {
    server,
    socket,
    sessionPath,
    lookupCalls,
    get sentMessageArgs() { return sentMessageArgs; },
  };
}

test('sends only through the active QR-linked socket to a registered recipient', async () => {
  const loaded = loadServer({ registered: true });
  const { server, socket, sessionPath } = loaded;
  await server.startSocket();
  socket.ev.emit('connection.update', { connection: 'open' });

  await server.sendMessage('+923001234567', 'test message');

  assert.equal(loaded.sentMessageArgs[0], '923001234567@s.whatsapp.net');
  assert.deepEqual(loaded.sentMessageArgs[1], { text: 'test message' });
  fs.rmSync(sessionPath, { recursive: true, force: true });
});

test('rejects unregistered recipients without sending', async () => {
  const { server, socket, sessionPath } = loadServer({ registered: false });
  let sendCalled = false;
  socket.sendMessage = async () => { sendCalled = true; };
  await server.startSocket();
  socket.ev.emit('connection.update', { connection: 'open' });

  await assert.rejects(server.sendMessage('923001234567', 'test message'), {
    message: 'Not Registered on WhatsApp',
  });
  assert.equal(sendCalled, false);
  fs.rmSync(sessionPath, { recursive: true, force: true });
});

test('sends to the connected account without rejecting it through onWhatsApp', async () => {
  const loaded = loadServer({ registered: false });
  await loaded.server.startSocket();
  loaded.socket.ev.emit('connection.update', { connection: 'open' });

  await loaded.server.sendTestMessage('+92 300-9999999', 'self test');

  assert.deepEqual(loaded.lookupCalls, []);
  assert.equal(loaded.sentMessageArgs[0], loaded.socket.user.id);
  fs.rmSync(loaded.sessionPath, { recursive: true, force: true });
});

test('blank test recipient sends directly to the connected account JID', async () => {
  const loaded = loadServer({ registered: false });
  await loaded.server.startSocket();
  loaded.socket.ev.emit('connection.update', { connection: 'open' });

  await loaded.server.sendTestMessage(null, 'note to self');

  assert.deepEqual(loaded.lookupCalls, []);
  assert.equal(loaded.sentMessageArgs[0], loaded.socket.user.id);
  assert.deepEqual(loaded.sentMessageArgs[1], { text: 'note to self' });
  fs.rmSync(loaded.sessionPath, { recursive: true, force: true });
});

test('test messages fall back to direct send when recipient lookup says unavailable', async () => {
  const loaded = loadServer({ registered: false });
  await loaded.server.startSocket();
  loaded.socket.ev.emit('connection.update', { connection: 'open' });

  await loaded.server.sendTestMessage('923001234567', 'test fallback');

  assert.deepEqual(loaded.lookupCalls, ['923001234567@s.whatsapp.net']);
  assert.equal(loaded.sentMessageArgs[0], '923001234567@s.whatsapp.net');
  fs.rmSync(loaded.sessionPath, { recursive: true, force: true });
});

test('test messages can send directly when recipient lookup is unavailable', async () => {
  const loaded = loadServer({ registered: false, lookupAvailable: false });
  await loaded.server.startSocket();
  loaded.socket.ev.emit('connection.update', { connection: 'open' });

  await loaded.server.sendTestMessage('923001234567', 'test without lookup');

  assert.equal(loaded.sentMessageArgs[0], '923001234567@s.whatsapp.net');
  fs.rmSync(loaded.sessionPath, { recursive: true, force: true });
});

test('normalizes local numbers and rejects malformed values before lookup', async () => {
  const loaded = loadServer({ registered: true });
  await loaded.server.startSocket();
  loaded.socket.ev.emit('connection.update', { connection: 'open' });

  assert.equal(loaded.server.normalizePhoneNumber('0300 123-4567'), '923001234567');
  await assert.rejects(loaded.server.sendMessage('12abc345', 'invalid'), {
    message: 'Enter a valid international phone number.',
  });
  assert.deepEqual(loaded.lookupCalls, []);
  assert.equal(loaded.sentMessageArgs, null);
  fs.rmSync(loaded.sessionPath, { recursive: true, force: true });
});

test('Cloud API queue dispatch works without a connected QR socket', async () => {
  const cloudApi = {
    access_token: 'test-access-token',
    phone_number_id: '123456789',
    business_account_id: '987654321',
  };
  const graphCalls = [];
  const statusUpdates = [];
  const getCalls = [];
  const postCalls = [];
  const axiosMock = {
    get: async (url) => {
      getCalls.push(url);
      return { data: url.endsWith('/api/whatsapp/integration')
        ? { ok: true, integration_method: 'cloud_api', cloud_api: cloudApi }
        : { ok: true, integration_method: 'cloud_api', cloud_api: cloudApi, items: [
          { id: 41, phone: '923001234567', message: 'Cloud message' },
        ] } };
    },
    post: async (url, body, options) => {
      postCalls.push(url);
      if (url.startsWith('https://graph.facebook.com/')) {
        graphCalls.push({ url, body, options });
        return { data: { messages: [{ id: 'wamid.test' }] } };
      }
      if (url.endsWith('/authorize-send')) return { data: { ok: true } };
      if (url.endsWith('/update-status')) statusUpdates.push(body);
      return { data: { ok: true } };
    },
  };
  const loaded = loadServer({ registered: true, axiosMock });

  const queue = await loaded.server.fetchPendingMessages('cloud_api');
  assert.ok(queue.items, JSON.stringify({ getCalls, lastError: loaded.server.buildHealthPayload().lastError }));
  assert.deepEqual(queue.items.map((item) => item.id), [41]);
  await loaded.server.processQueue();

  assert.equal(getCalls.length, 3);
  assert.equal(graphCalls.length, 1, JSON.stringify({ getCalls, postCalls, statusUpdates }));
  assert.equal(graphCalls[0].url, 'https://graph.facebook.com/v18.0/123456789/messages');
  assert.equal(graphCalls[0].body.to, '923001234567');
  assert.equal(graphCalls[0].body.text.body, 'Cloud message');
  assert.equal(graphCalls[0].options.headers.Authorization, 'Bearer test-access-token');
  assert.deepEqual(statusUpdates.map((item) => item.status), ['sent']);
  fs.rmSync(loaded.sessionPath, { recursive: true, force: true });
});

test('test-message dispatch follows the active Cloud API integration', async () => {
  const cloudApi = {
    access_token: 'test-access-token',
    phone_number_id: '123456789',
    business_account_id: '987654321',
  };
  let graphRequest = null;
  const axiosMock = {
    get: async () => ({ data: { ok: true, integration_method: 'cloud_api', cloud_api: cloudApi } }),
    post: async (url, body, options) => {
      graphRequest = { url, body, options };
      return { data: { messages: [{ id: 'wamid.test' }] } };
    },
  };
  const loaded = loadServer({ registered: false, axiosMock });

  await loaded.server.dispatchTestMessage('+923001234567', 'Verify Cloud API');

  assert.equal(graphRequest.url, 'https://graph.facebook.com/v18.0/123456789/messages');
  assert.equal(graphRequest.body.to, '923001234567');
  assert.equal(graphRequest.options.headers.Authorization, 'Bearer test-access-token');
  fs.rmSync(loaded.sessionPath, { recursive: true, force: true });
});