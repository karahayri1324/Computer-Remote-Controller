class TerminalManager {
    constructor(ws) {
        this.ws = ws;
        this.terminals = {};
        this.activeId = null;
        this._nextId = 1;
        this._resizeTimeout = null;
        this._isMobile = window.innerWidth <= 768;

        this.tabBar = document.getElementById('terminal-tab-list');
        this.addBtn = document.getElementById('terminal-add-btn');
        this.panelsEl = document.getElementById('terminal-panels');

        this.ws.on('shell_output', (msg) => {
            const shellId = msg.payload.shell_id || '1';
            const t = this.terminals[shellId];
            if (t) {
                t.term.write(msg.payload.data);
            }
        });

        this.addBtn.addEventListener('click', () => this.createTerminal());
    }

    init() {
        this.createTerminal();
    }

    createTerminal() {
        const shellId = String(this._nextId++);

        const el = document.createElement('div');
        el.className = 'terminal-panel';
        this.panelsEl.appendChild(el);

        const term = new Terminal({
            cursorBlink: true,
            fontSize: this._isMobile ? 12 : 14,
            fontFamily: "'Fira Code', 'Courier New', monospace",
            theme: {
                background: '#1a1b26',
                foreground: '#a9b1d6',
                cursor: '#c0caf5',
                selectionBackground: '#33467c',
                black: '#15161e',
                red: '#f7768e',
                green: '#9ece6a',
                yellow: '#e0af68',
                blue: '#7aa2f7',
                magenta: '#bb9af7',
                cyan: '#7dcfff',
                white: '#a9b1d6',
                brightBlack: '#414868',
                brightRed: '#f7768e',
                brightGreen: '#9ece6a',
                brightYellow: '#e0af68',
                brightBlue: '#7aa2f7',
                brightMagenta: '#bb9af7',
                brightCyan: '#7dcfff',
                brightWhite: '#c0caf5',
            },
            scrollback: 5000,
            allowProposedApi: true,
            scrollOnUserInput: true,
        });

        const fitAddon = new FitAddon.FitAddon();
        term.loadAddon(fitAddon);
        term.open(el);

        term.onData((data) => {
            this.ws.send('shell_input', { shell_id: shellId, data });
        });

        const tab = document.createElement('div');
        tab.className = 'terminal-tab';
        tab.dataset.shellId = shellId;
        const label = document.createElement('span');
        label.textContent = shellId;
        const closeBtn = document.createElement('button');
        closeBtn.className = 'terminal-tab-close';
        closeBtn.innerHTML = '&times;';
        tab.appendChild(label);
        tab.appendChild(closeBtn);

        label.addEventListener('click', () => this.switchTo(shellId));
        closeBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            this.closeTerminal(shellId);
        });
        this.tabBar.appendChild(tab);

        const ro = new ResizeObserver(() => {
            if (this.activeId === shellId) {
                clearTimeout(this._resizeTimeout);
                this._resizeTimeout = setTimeout(() => this.fit(), 50);
            }
        });
        ro.observe(el);

        if (this._isMobile) {
            el.addEventListener('touchstart', () => {
                const textarea = el.querySelector('.xterm-helper-textarea');
                if (textarea) { textarea.focus(); textarea.click(); }
            }, { passive: true });
        }

        this.terminals[shellId] = { term, fitAddon, el, tab, ro };

        this.ws.send('shell_create', { shell_id: shellId });
        this.switchTo(shellId);
        setTimeout(() => this.fit(), 100);
    }

    closeTerminal(shellId) {
        if (Object.keys(this.terminals).length <= 1) return;

        const t = this.terminals[shellId];
        if (!t) return;

        this.ws.send('shell_close', { shell_id: shellId });

        t.ro.disconnect();
        t.term.dispose();
        t.el.remove();
        t.tab.remove();
        delete this.terminals[shellId];

        if (this.activeId === shellId) {
            const ids = Object.keys(this.terminals);
            this.switchTo(ids[ids.length - 1]);
        }
    }

    switchTo(shellId) {
        const t = this.terminals[shellId];
        if (!t) return;

        for (const [id, entry] of Object.entries(this.terminals)) {
            entry.el.style.display = id === shellId ? '' : 'none';
            entry.tab.classList.toggle('active', id === shellId);
        }

        this.activeId = shellId;
        setTimeout(() => {
            this.fit();
            t.term.focus();
        }, 10);
    }

    fit() {
        const t = this.terminals[this.activeId];
        if (!t) return;
        try {
            t.fitAddon.fit();
            this.ws.send('shell_resize', {
                shell_id: this.activeId,
                cols: t.term.cols,
                rows: t.term.rows,
            });
        } catch (e) {}
    }

    focus() {
        const t = this.terminals[this.activeId];
        if (t) t.term.focus();
    }
}
