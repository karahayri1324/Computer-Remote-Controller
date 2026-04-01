class TerminalUI {
    constructor(containerEl, ws) {
        this.ws = ws;
        this.container = containerEl;
        this.term = null;
        this.fitAddon = null;
        this._resizeTimeout = null;
        this._isMobile = window.innerWidth <= 768;
    }

    init() {
        this.term = new Terminal({
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
            // Mobile: allow native scrolling within terminal
            scrollOnUserInput: true,
        });

        this.fitAddon = new FitAddon.FitAddon();
        this.term.loadAddon(this.fitAddon);
        this.term.open(this.container);

        // Initial fit
        setTimeout(() => this.fit(), 100);

        // User types -> send to agent
        this.term.onData((data) => {
            this.ws.send('shell_input', { data });
        });

        // Agent output -> write to terminal
        this.ws.on('shell_output', (msg) => {
            this.term.write(msg.payload.data);
        });

        // Handle resize
        const ro = new ResizeObserver(() => {
            clearTimeout(this._resizeTimeout);
            this._resizeTimeout = setTimeout(() => this.fit(), 50);
        });
        ro.observe(this.container);

        // Mobile: tap terminal area to focus (triggers virtual keyboard)
        if (this._isMobile) {
            this.container.addEventListener('touchstart', (e) => {
                // Focus textarea to trigger virtual keyboard
                const textarea = this.container.querySelector('.xterm-helper-textarea');
                if (textarea) {
                    textarea.focus();
                    textarea.click();
                }
            }, { passive: true });
        }
    }

    fit() {
        if (!this.fitAddon || !this.term) return;
        try {
            this.fitAddon.fit();
            this.ws.send('shell_resize', {
                cols: this.term.cols,
                rows: this.term.rows,
            });
        } catch (e) {}
    }

    focus() {
        if (this.term) this.term.focus();
    }
}
