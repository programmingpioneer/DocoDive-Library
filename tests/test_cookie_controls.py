"""Run the real consent controller in an offline browser-boundary fixture."""

from pathlib import Path
import shutil
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
NODE = shutil.which("node") or str(
    Path.home()
    / ".cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe"
)


JAVASCRIPT_TESTS = r"""
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const controllerPath = process.argv[1];
assert.ok(fs.existsSync(controllerPath), 'The cookie consent controller is not implemented');
const source = fs.readFileSync(controllerPath, 'utf8');
const KEY = 'docodive_cookie_preferences';
const NOW = 1793404800000;
const DAY = 86400000;

// Only browser boundaries are replaced: storage, DOM, script insertion, and reload.
// The production script owns all validation, UI events, and provider decisions.
function browser(options = {}) {
  const listeners = new Map();
  const elements = new Map();
  const scripts = [];
  const cookies = [];
  const storage = new Map();
  let reloads = 0;
  let dataAtReload;
  if (options.stored !== undefined) storage.set(KEY, options.stored);
  class Element {
    constructor(id) {
      this.id = id; this.hidden = true; this.checked = false;
      this.textContent = ''; this.dataset = {}; this.open = false;
      this.events = new Map(); this.attributes = new Map();
    }
    addEventListener(type, handler) {
      if (!this.events.has(type)) this.events.set(type, []);
      this.events.get(type).push(handler);
    }
    dispatch(type, event = {}) {
      event.preventDefault = () => { event.prevented = true; };
      for (const handler of this.events.get(type) || []) handler(event);
      return event;
    }
    setAttribute(name, value) { this.attributes.set(name, value); }
    removeAttribute(name) { this.attributes.delete(name); }
    showModal() { this.open = true; document.activeElement = this; }
    close() { this.open = false; this.dispatch('close'); }
    focus() { document.activeElement = this; }
    closest(selector) {
      if (selector === '[data-cookie-settings]' && this.dataset.cookieSettings !== undefined) return this;
      if (selector === '[data-cookie-action]' && this.dataset.cookieAction) return this;
      return null;
    }
  }
  for (const id of ['cookie-banner', 'cookie-preferences', 'cookie-form',
    'cookie-analytics', 'cookie-support', 'cookie-status',
    'cookie-status-message', 'cookie-dialog-status']) elements.set(id, new Element(id));
  const document = {
    readyState: 'complete',
    currentScript: { dataset: { preview: options.preview ? 'true' : 'false' } },
    body: { dataset: { pageHome: options.home === false ? 'false' : 'true' } },
    activeElement: null,
    head: { appendChild: element => scripts.push(element) },
    getElementById: id => elements.get(id) || scripts.find(script => script.id === id) || null,
    createElement: () => new Element(''),
    addEventListener(type, handler) {
      if (!listeners.has(type)) listeners.set(type, []);
      listeners.get(type).push(handler);
    },
    get cookie() {
      if (options.cookiesBlocked) throw new Error('Cookies denied');
      return '_ga=old; _ga_ABC=old; session=keep; csrf_token=keep';
    },
    set cookie(value) {
      if (options.cookieWritesBlocked) throw new Error('Cookies denied');
      cookies.push(value);
    }
  };
  const localStorage = {
    getItem(key) {
      if (options.storageBlocked) throw new Error('Storage denied');
      return storage.get(key) ?? null;
    },
    setItem(key, value) {
      if (options.storageBlocked || options.writeBlocked) throw new Error('Storage denied');
      storage.set(key, value);
    }
  };
  const window = {
    document, localStorage,
    location: {
      hostname: 'www.library.example', pathname: '/books',
      reload() { reloads += 1; dataAtReload = storage.get(KEY); }
    },
    addEventListener() {},
    setTimeout: fn => { fn(); return 1; }
  };
  class Clock extends Date { static now() { return NOW; } }
  const context = vm.createContext({window, document, Date: Clock, console,
    setTimeout: window.setTimeout, clearTimeout() {}});
  vm.runInContext(source, context, { filename: controllerPath });
  function click(action) {
    const element = new Element('button');
    if (action === 'preferences') element.dataset.cookieSettings = '';
    else element.dataset.cookieAction = action;
    document.activeElement = element;
    const event = { target: element, preventDefault() {} };
    for (const handler of listeners.get('click') || []) handler(event);
    return element;
  }
  function save(analytics, support) {
    elements.get('cookie-analytics').checked = analytics;
    elements.get('cookie-support').checked = support;
    elements.get('cookie-form').dispatch('submit');
  }
  return { window, document, elements, scripts, storage, cookies, click, save,
    executeAgain() { vm.runInContext(source, context); },
    get reloads() { return reloads; }, get dataAtReload() { return dataAtReload; } };
}

function stored(analytics, support, overrides = {}) {
  return JSON.stringify({version: 1, analytics, support,
    savedAt: NOW - DAY, expiresAt: NOW + 179 * DAY, ...overrides});
}
let count = 0;
function test(name, run) {
  run(); count += 1; console.log('PASS ' + name);
}

test('first visit has no optional scripts or provider globals', () => {
  const page = browser();
  assert.equal(page.elements.get('cookie-banner').hidden, false);
  assert.equal(page.elements.get('cookie-analytics').checked, false);
  assert.equal(page.elements.get('cookie-support').checked, false);
  assert.equal(page.scripts.length, 0);
  assert.equal(page.window.gtag, undefined);
  assert.equal(page.window.BrevoConversations, undefined);
});
test('essential-only choice persists without enabling providers', () => {
  const page = browser(); page.click('essential');
  const choice = JSON.parse(page.storage.get(KEY));
  assert.equal(choice.version, 1);
  assert.equal(choice.analytics, false); assert.equal(choice.support, false);
  assert.equal(choice.expiresAt - choice.savedAt, 15552000000);
  assert.equal(page.elements.get('cookie-banner').hidden, true);
  assert.equal(page.scripts.length, 0);
});
test('accept optional loads each selected provider once', () => {
  const page = browser(); page.click('accept'); page.click('accept'); page.executeAgain();
  assert.equal(page.scripts.length, 2);
  assert.ok(page.scripts.some(s => s.src === 'https://www.googletagmanager.com/gtag/js?id=G-3GC4V3QX2W'));
  assert.ok(page.scripts.some(s => s.src === 'https://conversations-widget.brevo.com/brevo-conversations.js'));
  assert.equal(page.window.BrevoConversationsID, '6a551981edd95b5e7d08467b');
  assert.ok(page.window.dataLayer.some(args => args[0] === 'config' && args[1] === 'G-3GC4V3QX2W'));
});
test('analytics-only choice never loads support', () => {
  const page = browser(); page.click('preferences'); page.save(true, false);
  assert.equal(page.scripts.length, 1);
  assert.match(page.scripts[0].src, /googletagmanager/);
  assert.equal(page.window.BrevoConversations, undefined);
});
test('support-only choice never enables analytics', () => {
  const page = browser(); page.save(false, true);
  assert.equal(page.scripts.length, 1);
  assert.match(page.scripts[0].src, /brevo/);
  assert.equal(page.window.gtag, undefined);
});
test('support consent loads chat only on the home page', () => {
  const page = browser({home: false, stored: stored(false, true)});
  assert.equal(page.scripts.length, 0);
  assert.equal(page.window.BrevoConversations, undefined);
  assert.equal(page.elements.get('cookie-banner').hidden, true);
});
test('valid saved choices are applied on the next page', () => {
  const page = browser({stored: stored(true, false)});
  assert.equal(page.scripts.length, 1);
  assert.equal(page.elements.get('cookie-banner').hidden, true);
});
test('expired choices require a fresh decision', () => {
  const page = browser({stored: stored(true, true, {expiresAt: NOW})});
  assert.equal(page.scripts.length, 0);
  assert.equal(page.elements.get('cookie-banner').hidden, false);
});
test('malformed and untrusted preference schemas fail closed', () => {
  for (const value of ['null', '[]', '{', '{}',
    stored('false', true), stored(true, true, {version: 2}),
    stored(true, true, {savedAt: NOW + DAY}),
    stored(true, true, {expiresAt: NOW + 181 * DAY}),
    stored(true, true, {expiresAt: null})]) {
    const page = browser({stored: value});
    assert.equal(page.scripts.length, 0, value);
    assert.equal(page.elements.get('cookie-banner').hidden, false, value);
  }
});
test('blocked storage retains a choice for this visit and explains the limit', () => {
  const page = browser({storageBlocked: true});
  page.click('accept');
  assert.equal(page.scripts.length, 2);
  assert.equal(page.elements.get('cookie-status').hidden, false);
  assert.match(page.elements.get('cookie-status-message').textContent, /visit/i);
  page.click('preferences');
  assert.equal(page.elements.get('cookie-analytics').checked, true);
  assert.equal(page.elements.get('cookie-support').checked, true);
});
test('footer preferences can reopen and cancel without changing a saved choice', () => {
  const page = browser(); page.click('essential');
  const button = page.click('preferences');
  assert.equal(page.elements.get('cookie-preferences').open, true);
  page.elements.get('cookie-analytics').checked = true;
  page.click('cancel');
  assert.equal(page.elements.get('cookie-preferences').open, false);
  assert.equal(page.document.activeElement, button);
  page.click('preferences');
  assert.equal(page.elements.get('cookie-analytics').checked, false);
  assert.equal(page.scripts.length, 0);
});
test('closing untouched preferences does not imply consent', () => {
  const page = browser(); page.click('preferences');
  page.elements.get('cookie-preferences').dispatch('cancel');
  assert.equal(page.storage.size, 0);
  assert.equal(page.scripts.length, 0);
  assert.equal(page.elements.get('cookie-banner').hidden, false);
});
test('revocation is persisted before reload and does not loop on the next page', () => {
  const page = browser({stored: stored(true, true)});
  page.click('preferences'); page.save(false, false);
  assert.equal(page.reloads, 1);
  const choice = JSON.parse(page.dataAtReload);
  assert.equal(choice.analytics, false); assert.equal(choice.support, false);
  assert.equal(page.window['ga-disable-G-3GC4V3QX2W'], true);
  const next = browser({stored: page.dataAtReload});
  assert.equal(next.scripts.length, 0); assert.equal(next.reloads, 0);
});
test('revocation with blocked writes does not reload into the old consent', () => {
  const page = browser({stored: stored(true, true), writeBlocked: true});
  page.save(false, false);
  assert.equal(page.reloads, 0);
  assert.equal(page.window['ga-disable-G-3GC4V3QX2W'], true);
  assert.match(page.elements.get('cookie-status-message').textContent, /close|running/i);
  page.click('preferences');
  assert.equal(page.elements.get('cookie-analytics').checked, false);
});
test('revocation only attempts to clear analytics cookies', () => {
  const page = browser({stored: stored(true, false)}); page.save(false, false);
  assert.ok(page.cookies.length > 0);
  assert.ok(page.cookies.every(value => value.startsWith('_ga=') || value.startsWith('_ga_ABC=')));
});
test('denied cookie access does not interrupt saving a rejection', () => {
  for (const options of [{cookiesBlocked: true}, {cookieWritesBlocked: true}]) {
    const page = browser(options); page.click('essential');
    assert.equal(page.elements.get('cookie-banner').hidden, true);
    assert.equal(JSON.parse(page.storage.get(KEY)).analytics, false);
    assert.equal(page.scripts.length, 0);
  }
});
test('a same-visit opt-in after blocked revocation enables analytics again', () => {
  const page = browser({stored: stored(true, false), writeBlocked: true});
  page.save(false, false); page.save(true, false);
  assert.equal(page.window['ga-disable-G-3GC4V3QX2W'], false);
  assert.equal(page.scripts.length, 1);
});
test('preview mode exercises consent without contacting providers', () => {
  const page = browser({preview: true}); page.click('accept');
  assert.equal(page.scripts.length, 0);
  assert.equal(page.window.gtag, undefined);
  assert.equal(page.window.BrevoConversations, undefined);
  assert.equal(JSON.parse(page.storage.get(KEY)).analytics, true);
});
console.log(count + ' consent behavior checks passed');
"""


class CookieControlsTests(unittest.TestCase):
    def test_offline_browser_consent_behaviors(self):
        result = subprocess.run(
            [NODE, "-e", JAVASCRIPT_TESTS, str(ROOT / "static/js/privacy.js")],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
