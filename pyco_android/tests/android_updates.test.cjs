const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const source = fs.readFileSync(
    path.join(__dirname, '..', '..', 'pyco_web', 'android_runtime.js'), 'utf8'
);

function createRuntime() {
    function element() {
        return {
            textContent: '', value: '', style: { setProperty() {} },
            dataset: {}, handlers: {}, children: [], attributes: {},
            selectionStart: 0,
            addEventListener(name, handler) { this.handlers[name] = handler; },
            appendChild(child) { this.children.push(child); },
            setAttribute(name, value) { this.attributes[name] = value; },
            setSelectionRange(start) { this.selectionStart = start; },
            focus() {}
        };
    }
    const selectors = Object.fromEntries([
        '.pyrepl', '.xterm-viewport', '.xterm-rows', '.android-prompt',
        '.android-highlight', '.xterm-helper-textarea', '.status-bar'
    ].map(name => [name, element()]));
    selectors['.pyrepl'].querySelector = name => selectors[name] || element();
    const menu = element();
    menu.style.display = 'none';
    const calls = [];
    const window = {
        pyreplThemes: { 'pyco-crt': {} },
        getComputedStyle: () => ({ lineHeight: '14', font: '14px monospace' }),
        AndroidPython: {
            initialize: url => calls.push(['initialize', url]),
            checkForUpdates: () => calls.push(['check']),
            updatePyco: () => calls.push(['update']),
            highlight: text => JSON.stringify([['Token.Text', text]]),
            execute: text => calls.push(['execute', text])
        }
    };
    const document = {
        querySelector: name => selectors[name],
        getElementById: () => menu,
        createTextNode: text => ({ textContent: text }),
        createElement: () => ({
            getContext: () => ({ measureText: () => ({ width: 8 }) })
        }),
        head: { appendChild() {} },
        body: { classList: { contains: () => false } }
    };
    vm.runInNewContext(source, {
        window, document, CUSTOMIZE_KEY: 'custom',
        localStorage: { getItem: () => null },
        requestAnimationFrame: callback => callback(),
        console: { warn() {}, error() {} }
    });
    return {
        window, menu, calls,
        status: selectors['.status-bar'],
        input: selectors['.xterm-helper-textarea'],
        outputNodes: selectors['.xterm-rows'].children,
        output: () => selectors['.xterm-rows'].children.map(node => node.textContent).join('')
    };
}

test('starts initialization and update check independently', () => {
    const runtime = createRuntime();
    assert.deepEqual(runtime.calls, [['initialize', ''], ['check']]);
    assert.equal(runtime.menu.style.display, 'none');
});

test('only shows the update action when an update is available', () => {
    const { window, status, menu } = createRuntime();
    window.pycoAndroidUpdateStatus('current', '');
    assert.equal(status.textContent, 'pyco');
    assert.equal(menu.style.display, 'none');
    window.pycoAndroidUpdateStatus('available', '');
    assert.equal(status.textContent, 'pyco - update available');
    assert.equal(menu.style.display, '');
});

test('suppresses duplicate downloads while native restart is pending', () => {
    const runtime = createRuntime();
    runtime.window.pycoAndroidReady('{}');
    runtime.input.value = '12 + 30';
    runtime.window.pycoAndroidUpdateStatus('available', '');
    runtime.menu.handlers.click();
    runtime.menu.handlers.click();
    assert.equal(runtime.calls.filter(call => call[0] === 'update').length, 1);
    assert.equal(runtime.menu.attributes['aria-disabled'], 'true');
    runtime.window.pycoAndroidUpdateStatus(
        'updated', 'Updated pyco. Restarting for more happy calculating!'
    );
    assert.equal(runtime.status.textContent, 'pyco - restarting...');
    assert.equal(runtime.menu.style.display, 'none');
    assert.match(runtime.output(), /Restarting for more happy calculating!/);
    assert.equal(runtime.outputNodes.at(-1).className, 'android-system-message');
    assert.equal(runtime.input.value, '12 + 30');
    runtime.menu.handlers.click();
    assert.equal(runtime.calls.filter(call => call[0] === 'update').length, 1);
});

test('failed downloads remain visible and can be retried', () => {
    const runtime = createRuntime();
    runtime.window.pycoAndroidReady('{}');
    runtime.menu.handlers.click();
    runtime.window.pycoAndroidUpdateStatus('update-error', 'Unable to update pyco.py: offline');
    assert.match(runtime.output(), /offline/);
    assert.equal(runtime.menu.style.display, '');
    assert.equal(runtime.menu.attributes['aria-disabled'], 'false');
    runtime.menu.handlers.click();
    assert.equal(runtime.calls.filter(call => call[0] === 'update').length, 2);
});

test('queues early errors until startup output is printed', () => {
    const runtime = createRuntime();
    runtime.window.pycoAndroidUpdateStatus('check-error', 'Unable to check: offline');
    assert.equal(runtime.output(), '');
    runtime.window.pycoAndroidReady('{"result":"Welcome"}');
    assert.equal(runtime.output(), 'Welcome\nUnable to check: offline\n');
    assert.equal(runtime.outputNodes.at(-1).className, 'android-system-message');
    assert.equal(runtime.menu.style.display, 'none');
});

test('late check results cannot clear the restart notification', () => {
    const runtime = createRuntime();
    runtime.window.pycoAndroidUpdateStatus('updated', 'Restart');
    runtime.window.pycoAndroidUpdateStatus('current', '');
    assert.equal(runtime.status.textContent, 'pyco - restarting...');
    assert.equal(runtime.menu.style.display, 'none');
});
