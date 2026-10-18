(function () {
    'use strict';

    const container = document.querySelector('.pyrepl');
    if (!container || !window.AndroidPython) {
        throw new Error('Android Python runtime is unavailable.');
    }

    const themeName = container.dataset.theme || 'pyco-crt';
    const theme = window.pyreplThemes?.[themeName];
    if (!theme) {
        throw new Error(`Android Python theme "${themeName}" is unavailable.`);
    }
    const fontSize = Number.parseInt(container.dataset.fontSize || '14', 10);
    container.style.setProperty('--android-terminal-bg', theme.background);
    container.style.setProperty('--android-terminal-fg', theme.foreground);
    container.style.setProperty('--android-prompt', theme.green);
    container.style.setProperty('--android-cursor', theme.cursor);
    container.style.setProperty('--android-font-size', `${fontSize}px`);

    const style = document.createElement('style');
    style.textContent = `
        .repl-container::before {
            background: repeating-linear-gradient(
                0deg,
                rgba(0, 0, 0, 0.15) 0,
                rgba(0, 0, 0, 0.15) 1px,
                transparent 1px,
                transparent 2px
            );
        }
        @keyframes android-cursor-blink {
            0%, 45% { opacity: 1; }
            50%, 95% { opacity: 0; }
            100% { opacity: 1; }
        }
        .pyrepl .android-terminal {
            background: var(--android-terminal-bg);
            color: var(--android-terminal-fg);
            color-scheme: only light;
            display: flex;
            flex: 1;
            flex-direction: column;
            font: var(--android-font-size)/1.35 "Courier New", Consolas, monospace;
            height: 100%;
            min-height: 0;
            overflow: hidden;
        }
        .pyrepl .android-terminal .xterm-viewport {
            display: flex;
            flex: 1;
            flex-direction: column;
            justify-content: flex-start;
            min-height: 0;
            overflow: auto !important;
            padding: 8px;
        }
        .pyrepl .android-terminal .xterm-screen {
            height: auto !important;
        }
        .pyrepl .android-terminal .xterm-rows {
            color: var(--android-terminal-fg);
            font: inherit;
            font-feature-settings: "liga" 0, "calt" 0;
            font-kerning: none;
            font-variant-ligatures: none;
            line-height: 1.35;
            letter-spacing: 0;
            margin: 0;
            min-height: 0;
            overflow-wrap: normal;
            position: static;
            text-rendering: optimizeSpeed;
            white-space: pre;
            word-break: normal;
        }
        .pyrepl .android-system-message {
            white-space: pre-wrap;
            overflow-wrap: anywhere;
        }
        .pyrepl .android-input-row {
            align-items: flex-start;
            display: flex;
            flex-shrink: 0;
            padding: 0;
        }
        .pyrepl .android-prompt {
            color: var(--android-prompt);
            flex: 0 0 auto;
            line-height: 1.35;
            padding-top: 1px;
            white-space: pre;
        }
        .pyrepl .android-input-wrap {
            flex: 1;
            height: 1.35em;
            min-width: 0;
            position: relative;
        }
        .pyrepl .android-highlight {
            color: var(--android-terminal-fg);
            font: inherit;
            font-feature-settings: "liga" 0, "calt" 0;
            font-kerning: none;
            font-variant-ligatures: none;
            inset: 0;
            line-height: 1.35;
            margin: 0;
            overflow: hidden;
            pointer-events: none;
            position: absolute;
            text-rendering: optimizeSpeed;
            white-space: pre;
        }
        .pyrepl textarea.xterm-helper-textarea {
            -webkit-text-fill-color: transparent;
            background: transparent;
            border: 0;
            caret-color: transparent;
            color: transparent;
            font: inherit;
            height: 1.35em;
            inset: 0;
            line-height: 1.35;
            min-height: 1.35em;
            opacity: 1;
            outline: none;
            overflow: hidden;
            padding: 0;
            position: absolute !important;
            resize: none;
            width: 100%;
        }
        .pyrepl .android-cursor {
            animation: android-cursor-blink 1s step-end infinite;
            border-left: 2px solid var(--android-cursor);
            display: inline-block;
            height: 1.1em;
            margin-right: -2px;
            vertical-align: -0.15em;
        }
    `;
    document.head.appendChild(style);

    container.innerHTML = `
        <div class="android-terminal xterm">
            <div class="xterm-viewport">
                <div class="xterm-screen">
                    <pre class="xterm-rows"></pre>
                    <div class="android-input-row">
                        <span class="android-prompt">&gt;&gt;&gt; </span>
                        <div class="android-input-wrap">
                            <pre class="android-highlight"><span class="android-cursor"></span></pre>
                            <textarea class="xterm-helper-textarea" rows="1"
                                autocomplete="off" autocapitalize="off"
                                autocorrect="off" spellcheck="false"></textarea>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    `;

    const viewport = container.querySelector('.xterm-viewport');
    const output = container.querySelector('.xterm-rows');
    const prompt = container.querySelector('.android-prompt');
    const highlight = container.querySelector('.android-highlight');
    const input = container.querySelector('.xterm-helper-textarea');
    const commandHistory = [];
    const pendingCommandLines = [];
    let historyIndex = 0;
    let ready = false;
    let busy = false;
    let waitingForInput = false;
    let continuation = false;
    let escapeSequence = '';
    let escapeTimer = null;

    function escapeHtml(text) {
        return text
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;');
    }

    function tokenStyle(tokenType) {
        const styles = theme.pygmentsStyle || {};
        let name = tokenType.replace(/^Token\.?/, '');
        if (name.startsWith('Literal.')) name = name.slice('Literal.'.length);
        if (name === 'Text.Whitespace') name = 'Whitespace';
        while (name) {
            if (styles[name]) return styles[name];
            const separator = name.lastIndexOf('.');
            name = separator < 0 ? '' : name.slice(0, separator);
        }
        return styles.Token || theme.foreground;
    }

    function styleToCss(style) {
        const parts = String(style).split(/\s+/);
        const declarations = [];
        for (const part of parts) {
            if (part === 'bold') declarations.push('font-weight:bold');
            else if (part === 'italic') declarations.push('font-style:italic');
            else if (part === 'underline') declarations.push('text-decoration:underline');
            else if (part.startsWith('#')) declarations.push(`color:${part}`);
        }
        return declarations.join(';');
    }

    function renderToken(tokenType, value) {
        if (!value) return '';
        return `<span style="${styleToCss(tokenStyle(tokenType))}">${escapeHtml(value)}</span>`;
    }

    function highlightPython(source, cursorPosition) {
        let tokens;
        try {
            tokens = JSON.parse(window.AndroidPython.highlight(source));
        } catch (error) {
            console.error('Native Pygments highlighting failed:', error);
            if (cursorPosition === undefined) return escapeHtml(source);
            return `${escapeHtml(source.slice(0, cursorPosition))}`
                + '<span class="android-cursor"></span>'
                + `${escapeHtml(source.slice(cursorPosition))}`;
        }

        let html = '';
        let offset = 0;
        let cursorInserted = cursorPosition === undefined;
        for (const [tokenType, value] of tokens) {
            const end = offset + value.length;
            if (!cursorInserted && cursorPosition >= offset && cursorPosition <= end) {
                const split = cursorPosition - offset;
                html += renderToken(tokenType, value.slice(0, split));
                html += '<span class="android-cursor"></span>';
                html += renderToken(tokenType, value.slice(split));
                cursorInserted = true;
            } else {
                html += renderToken(tokenType, value);
            }
            offset = end;
        }
        if (!cursorInserted) html += '<span class="android-cursor"></span>';
        return html;
    }

    function renderInput() {
        const cursor = input.selectionStart ?? input.value.length;
        highlight.innerHTML = highlightPython(input.value, cursor);
    }

    function scrollToBottom() {
        requestAnimationFrame(() => {
            viewport.scrollTop = viewport.scrollHeight;
        });
    }

    function appendOutput(text) {
        if (!text) return;
        output.appendChild(document.createTextNode(
            text.endsWith('\n') ? text : `${text}\n`
        ));
        scrollToBottom();
    }

    function appendSubmittedLine(promptText, line, isPython) {
        const promptSpan = document.createElement('span');
        promptSpan.className = 'android-prompt';
        promptSpan.textContent = promptText;
        output.appendChild(promptSpan);

        if (isPython) {
            const codeSpan = document.createElement('span');
            codeSpan.innerHTML = highlightPython(line);
            output.appendChild(codeSpan);
        } else {
            output.appendChild(document.createTextNode(line));
        }
        output.appendChild(document.createTextNode('\n'));
    }

    function appendSystemMessage(text) {
        const message = document.createElement('span');
        message.className = 'android-system-message';
        message.textContent = text.endsWith('\n') ? text : `${text}\n`;
        output.appendChild(message);
        scrollToBottom();
    }

    function setInput(value, cursor) {
        input.value = value;
        const position = cursor === undefined ? value.length : cursor;
        input.setSelectionRange(position, position);
        renderInput();
    }

    function restoreInputFocus() {
        if (!document.body.classList.contains('keyboard-open')) {
            input.focus();
        }
    }

    function currentLine() {
        return `${prompt.textContent}${input.value}`;
    }

    function submit() {
        if (!ready || (busy && !waitingForInput)) return;

        const line = input.value;
        if (continuation && !line.trim() && line.length) {
            setInput(' '.repeat(Math.max(0, line.length - 4)));
            return;
        }
        appendSubmittedLine(prompt.textContent, line, !waitingForInput);
        setInput('');

        if (waitingForInput) {
            waitingForInput = false;
            prompt.textContent = '';
            window.AndroidPython.provideInput(line);
            scrollToBottom();
            return;
        }

        pendingCommandLines.push(line);
        busy = true;
        prompt.textContent = '';
        window.AndroidPython.execute(line);
        scrollToBottom();
    }

    function moveHistory(offset) {
        if (!commandHistory.length || busy) return;
        historyIndex = Math.max(0, Math.min(commandHistory.length, historyIndex + offset));
        setInput(historyIndex === commandHistory.length ? '' : commandHistory[historyIndex]);
    }

    function completeAtCursor() {
        if (busy) return;
        const cursor = input.selectionStart;
        const word = input.value.slice(0, cursor).match(/[\w.]*$/)?.[0] || '';
        if (!word) return;

        let completions;
        try {
            completions = JSON.parse(window.AndroidPython.complete(word));
        } catch (error) {
            console.error('Native Python completion failed:', error);
            return;
        }
        if (completions.length === 1) {
            const before = input.value.slice(0, cursor - word.length);
            const after = input.value.slice(cursor);
            const value = `${before}${completions[0]}${after}`;
            setInput(value, before.length + completions[0].length);
        } else if (completions.length > 1) {
            const width = Math.max(...completions.map(value => value.length)) + 2;
            const columns = Math.max(1, Math.floor(term.cols / width));
            const rows = [];
            for (let index = 0; index < completions.length; index += columns) {
                rows.push(completions.slice(index, index + columns)
                    .map(value => value.padEnd(width))
                    .join('').trimEnd());
            }
            appendOutput(rows.join('\n'));
        }
    }

    function dispatchEscape(sequence) {
        const cursor = input.selectionStart;
        switch (sequence) {
            case '\x1b':
                setInput('');
                break;
            case '\x1b[H':
                setInput(input.value, 0);
                break;
            case '\x1b[F':
                setInput(input.value, input.value.length);
                break;
            case '\x1b[D':
                setInput(input.value, Math.max(0, cursor - 1));
                break;
            case '\x1b[C':
                setInput(input.value, Math.min(input.value.length, cursor + 1));
                break;
            case '\x1b[A':
                moveHistory(-1);
                break;
            case '\x1b[B':
                moveHistory(1);
                break;
        }
    }

    function pushChar(code) {
        if (!ready || (busy && !waitingForInput)) return;
        const character = String.fromCharCode(code);

        if (escapeSequence || character === '\x1b') {
            if (escapeTimer) clearTimeout(escapeTimer);
            escapeSequence += character;
            if (escapeSequence === '\x1b' || escapeSequence === '\x1b[') {
                escapeTimer = setTimeout(() => {
                    dispatchEscape(escapeSequence);
                    escapeSequence = '';
                }, 20);
            } else {
                dispatchEscape(escapeSequence);
                escapeSequence = '';
            }
            return;
        }

        if (character === '\r' || character === '\n') {
            submit();
        } else if (character === '\x7f' || character === '\b') {
            const start = input.selectionStart;
            const end = input.selectionEnd;
            if (start !== end) {
                setInput(input.value.slice(0, start) + input.value.slice(end), start);
            } else if (start > 0) {
                setInput(input.value.slice(0, start - 1) + input.value.slice(end), start - 1);
            }
        } else if (character === '\x0c') {
            output.textContent = '';
        } else if (character === '\t') {
            completeAtCursor();
        } else {
            const start = input.selectionStart;
            const end = input.selectionEnd;
            setInput(input.value.slice(0, start) + character + input.value.slice(end), start + 1);
        }
    }

    input.addEventListener('input', renderInput);
    input.addEventListener('click', renderInput);
    input.addEventListener('keyup', renderInput);
    input.addEventListener('select', renderInput);
    input.addEventListener('keydown', (event) => {
        if (event.isComposing) return;
        switch (event.key) {
            case 'Enter':
                event.preventDefault();
                submit();
                break;
            case 'ArrowUp':
                event.preventDefault();
                moveHistory(-1);
                break;
            case 'ArrowDown':
                event.preventDefault();
                moveHistory(1);
                break;
            case 'Escape':
                event.preventDefault();
                setInput('');
                break;
            case 'Tab':
                event.preventDefault();
                completeAtCursor();
                break;
        }
    });

    const terminalStyle = window.getComputedStyle(output);
    const cellHeight = Number.parseFloat(terminalStyle.lineHeight);
    const canvas = document.createElement('canvas');
    const context = canvas.getContext('2d');
    context.font = terminalStyle.font;
    const cellWidth = context.measureText('M').width;

    const term = {
        buffer: {
            active: {
                baseY: 0,
                cursorY: 0,
                getLine: () => ({ translateToString: () => currentLine() })
            }
        },
        dimensions: { css: { cell: { height: cellHeight, width: cellWidth } } },
        options: {
            fontFamily: terminalStyle.fontFamily,
            fontSize
        },
        get cols() {
            return Math.max(1, Math.floor(viewport.clientWidth / cellWidth));
        },
        scrollLines: (lines) => {
            viewport.scrollTop += lines * cellHeight;
        }
    };

    container.pyreplConsole = { push_char: pushChar, term };
    window.pyreplGet = (name) => window.AndroidPython.get(name);
    window.pyreplCall = (name, argument) => window.AndroidPython.callHelper(name, argument);

    const updateMenuItem = document.getElementById('updatePycoMenuItem');
    const statusBar = document.querySelector('.status-bar');
    let updatingPyco = false;
    let pycoRestartRequired = false;
    const pendingUpdateMessages = [];

    window.pycoAndroidUpdateStatus = (state, message) => {
        if (message) {
            if (ready) appendSystemMessage(message);
            else pendingUpdateMessages.push(message);
        }
        if (state === 'check-error') {
            console.warn(message);
            return;
        }
        if (state === 'updated') pycoRestartRequired = true;
        if (pycoRestartRequired) {
            statusBar.textContent = 'pyco - restarting...';
            updateMenuItem.style.display = 'none';
        } else if (state === 'available' || state === 'update-error') {
            statusBar.textContent = 'pyco - update available';
            updateMenuItem.style.display = '';
        } else {
            statusBar.textContent = 'pyco';
            updateMenuItem.style.display = 'none';
        }
        updatingPyco = false;
        updateMenuItem.textContent = 'Update pyco';
        updateMenuItem.setAttribute('aria-disabled', 'false');
    };

    updateMenuItem.addEventListener('click', () => {
        if (updatingPyco || pycoRestartRequired) return;
        updatingPyco = true;
        updateMenuItem.textContent = 'Updating pyco...';
        updateMenuItem.setAttribute('aria-disabled', 'true');
        window.AndroidPython.updatePyco();
    });

    window.pycoAndroidReady = (jsonResult) => {
        let result;
        try {
            result = JSON.parse(jsonResult);
        } catch (error) {
            result = { error: String(error) };
        }
        appendOutput(result.error || result.result || '');
        pendingUpdateMessages.splice(0).forEach(appendSystemMessage);
        ready = true;
        input.readOnly = false;
        renderInput();
        restoreInputFocus();
    };

    window.pycoAndroidRequestInput = (pendingOutput, inputPrompt) => {
        appendOutput(pendingOutput);
        waitingForInput = true;
        input.readOnly = false;
        prompt.textContent = inputPrompt;
        setInput('');
        restoreInputFocus();
    };

    window.pycoAndroidExecutionComplete = (jsonResult) => {
        let response;
        try {
            response = JSON.parse(jsonResult);
        } catch (error) {
            response = { error: String(error), continuation: false };
        }
        continuation = response.continuation === true;
        busy = false;
        waitingForInput = false;
        prompt.textContent = continuation ? '... ' : '>>> ';
        appendOutput(response.error || response.result || '');
        if (continuation) {
            const previousLine = pendingCommandLines[pendingCommandLines.length - 1] || '';
            let indentation = previousLine.match(/^\s*/)[0];
            if (previousLine.trimEnd().endsWith(':')) indentation += '    ';
            setInput(indentation);
        } else {
            const source = pendingCommandLines.join('\n');
            if (response.recordHistory && source
                    && commandHistory[commandHistory.length - 1] !== source) {
                commandHistory.push(source);
            }
            pendingCommandLines.length = 0;
            historyIndex = commandHistory.length;
        }
        input.readOnly = false;
        if (!continuation) renderInput();
        restoreInputFocus();
    };

    window.pycoAndroidSetViewportHeight = (physicalHeight) => {
        const pageContainer = document.querySelector('.container');
        if (pageContainer) {
            pageContainer.style.height = physicalHeight
                ? `${physicalHeight / window.devicePixelRatio}px`
                : '';
        }
    };

    input.readOnly = true;
    output.textContent = '';
    renderInput();
    if (typeof window.AndroidPython.getViewportHeight === 'function') {
        window.pycoAndroidSetViewportHeight(window.AndroidPython.getViewportHeight());
    }
    const customizationUrl = localStorage.getItem(CUSTOMIZE_KEY) || '';
    window.AndroidPython.initialize(customizationUrl);
    window.AndroidPython.checkForUpdates();
})();
