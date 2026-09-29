const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

function loadServerWithSession(sessionPath) {
  delete require.cache[require.resolve('../server.js')];
  process.env.SESSION_PATH = sessionPath;
  return require('../server.js');
}

test('valid WhatsApp auth files are not cleared during startup checks', () => {
  const sessionDir = fs.mkdtempSync(path.join(os.tmpdir(), 'wa-session-'));
  fs.writeFileSync(path.join(sessionDir, 'creds.json'), JSON.stringify({
    me: { id: '923001234567:32@s.whatsapp.net' },
    keys: { preKey: 'cached' },
    signalIdentities: [{ identifier: { name: 'pairing' } }],
  }));
  fs.writeFileSync(path.join(sessionDir, 'session-123.json'), JSON.stringify({ ok: true }));

  const server = loadServerWithSession(sessionDir);

  assert.equal(typeof server.detectStaleSession, 'function');
  assert.equal(server.detectStaleSession(), false);
  assert.ok(fs.existsSync(path.join(sessionDir, 'creds.json')));
  assert.ok(fs.existsSync(path.join(sessionDir, 'session-123.json')));
});
