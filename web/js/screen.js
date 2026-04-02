class RemoteScreen {
    constructor(ws, showToast) {
        this.ws = ws;
        this.showToast = showToast;
        this.canvas = document.getElementById('screen-canvas');
        this.ctx = this.canvas.getContext('2d');
        this.streaming = false;
        this.available = false;
        this._naturalWidth = 0;
        this._naturalHeight = 0;

        this.fpsSlider = document.getElementById('screen-fps');
        this.qualitySlider = document.getElementById('screen-quality');
        this.fpsValue = document.getElementById('screen-fps-value');
        this.qualityValue = document.getElementById('screen-quality-value');
        this.startBtn = document.getElementById('screen-start-btn');
        this.statusEl = document.getElementById('screen-status');

        this.ws.on('screen_frame', (msg) => this._onFrame(msg.payload));
        this.ws.on('screen_error', (msg) => {
            this.showToast(msg.payload.message, 'error');
            this._setStreaming(false);
        });
        this.ws.on('screen_check_res', (msg) => {
            this.available = msg.payload.available;
            this._updateUI();
        });

        this._setupControls();
        this._setupInput();
    }

    check() {
        this.ws.send('screen_check', {});
    }

    _setupControls() {
        this.fpsSlider.addEventListener('input', () => {
            this.fpsValue.textContent = this.fpsSlider.value;
        });
        this.qualitySlider.addEventListener('input', () => {
            this.qualityValue.textContent = this.qualitySlider.value;
        });

        this.startBtn.addEventListener('click', () => {
            if (this.streaming) {
                this.stop();
            } else {
                this.start();
            }
        });
    }

    start() {
        this.ws.send('screen_start', {
            fps: parseInt(this.fpsSlider.value),
            quality: parseInt(this.qualitySlider.value),
            max_width: 1920,
        });
        this._setStreaming(true);
    }

    stop() {
        this.ws.send('screen_stop', {});
        this._setStreaming(false);
    }

    _setStreaming(val) {
        this.streaming = val;
        this.startBtn.textContent = val ? 'Stop' : 'Start';
        this.startBtn.classList.toggle('active', val);
        this.statusEl.textContent = val ? 'Streaming...' : 'Stopped';
    }

    _onFrame(payload) {
        const w = payload.width;
        const h = payload.height;

        if (w !== this._naturalWidth || h !== this._naturalHeight) {
            this._naturalWidth = w;
            this._naturalHeight = h;
        }
        this._fitCanvas();

        const img = new Image();
        img.onload = () => {
            this.ctx.drawImage(img, 0, 0, this.canvas.width, this.canvas.height);
        };
        img.src = 'data:image/jpeg;base64,' + payload.data;
    }

    _fitCanvas() {
        const container = this.canvas.parentElement;
        const cw = container.clientWidth;
        const ch = container.clientHeight;
        const ratio = this._naturalWidth / this._naturalHeight;
        let w, h;
        if (cw / ch > ratio) {
            h = ch;
            w = h * ratio;
        } else {
            w = cw;
            h = w / ratio;
        }
        const newW = Math.floor(w);
        const newH = Math.floor(h);
        if (this.canvas.width !== newW || this.canvas.height !== newH) {
            this.canvas.width = newW;
            this.canvas.height = newH;
        }
    }

    _setupInput() {
        const getRemoteCoords = (e) => {
            const rect = this.canvas.getBoundingClientRect();
            const scaleX = this._naturalWidth / rect.width;
            const scaleY = this._naturalHeight / rect.height;
            return {
                x: Math.round((e.clientX - rect.left) * scaleX),
                y: Math.round((e.clientY - rect.top) * scaleY),
            };
        };

        let lastMove = 0;
        this.canvas.addEventListener('mousemove', (e) => {
            if (!this.streaming) return;
            const now = Date.now();
            if (now - lastMove < 16) return;
            lastMove = now;
            const coords = getRemoteCoords(e);
            this.ws.send('screen_input', {
                input_type: 'mouse_move',
                data: coords,
            });
        });

        this.canvas.addEventListener('mousedown', (e) => {
            if (!this.streaming) return;
            e.preventDefault();
            this.canvas.focus();
            const coords = getRemoteCoords(e);
            let button = 1;
            if (e.button === 2) button = 3;
            else if (e.button === 1) button = 2;
            this.ws.send('screen_input', {
                input_type: 'mouse_click',
                data: { ...coords, button },
            });
        });

        this.canvas.addEventListener('dblclick', (e) => {
            if (!this.streaming) return;
            e.preventDefault();
            const coords = getRemoteCoords(e);
            this.ws.send('screen_input', {
                input_type: 'mouse_dblclick',
                data: { ...coords, button: 1 },
            });
        });

        this.canvas.addEventListener('contextmenu', (e) => {
            e.preventDefault();
        });

        this.canvas.addEventListener('wheel', (e) => {
            if (!this.streaming) return;
            e.preventDefault();
            const coords = getRemoteCoords(e);
            this.ws.send('screen_input', {
                input_type: 'mouse_scroll',
                data: {
                    ...coords,
                    direction: e.deltaY < 0 ? 'up' : 'down',
                    clicks: '3',
                },
            });
        }, { passive: false });

        const keyMap = {
            'Enter': 'Return', 'Backspace': 'BackSpace', 'Delete': 'Delete',
            'Tab': 'Tab', 'Escape': 'Escape', 'ArrowUp': 'Up', 'ArrowDown': 'Down',
            'ArrowLeft': 'Left', 'ArrowRight': 'Right', 'Home': 'Home', 'End': 'End',
            'PageUp': 'Prior', 'PageDown': 'Next', 'Insert': 'Insert',
            'F1': 'F1', 'F2': 'F2', 'F3': 'F3', 'F4': 'F4', 'F5': 'F5',
            'F6': 'F6', 'F7': 'F7', 'F8': 'F8', 'F9': 'F9', 'F10': 'F10',
            'F11': 'F11', 'F12': 'F12', ' ': 'space',
        };

        this.canvas.setAttribute('tabindex', '0');

        this.canvas.addEventListener('keydown', (e) => {
            if (!this.streaming) return;
            e.preventDefault();

            let parts = [];
            if (e.ctrlKey) parts.push('ctrl');
            if (e.altKey) parts.push('alt');
            if (e.shiftKey && keyMap[e.key]) parts.push('shift');
            if (e.metaKey) parts.push('super');

            const mapped = keyMap[e.key];
            if (mapped) {
                parts.push(mapped);
                this.ws.send('screen_input', {
                    input_type: 'key_press',
                    data: { key: parts.join('+') },
                });
            } else if (e.key.length === 1 && !e.ctrlKey && !e.altKey && !e.metaKey) {
                this.ws.send('screen_input', {
                    input_type: 'key_type',
                    data: { text: e.key },
                });
            } else if (e.key.length === 1) {
                parts.push(e.key);
                this.ws.send('screen_input', {
                    input_type: 'key_press',
                    data: { key: parts.join('+') },
                });
            }
        });
    }

    _updateUI() {
        if (!this.available) {
            this.statusEl.textContent = 'Not available (install mss + Pillow on PC)';
            this.startBtn.disabled = true;
        } else {
            this.startBtn.disabled = false;
            this.statusEl.textContent = 'Ready';
        }
    }
}
