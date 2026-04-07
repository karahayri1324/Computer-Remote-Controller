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

        // Frame pipeline - drop stale frames, only render latest
        this._pendingFrame = null;
        this._rendering = false;

        // Input coalescing
        this._pendingMove = null;
        this._moveRafId = null;
        this._keyTypeBuffer = '';
        this._keyTypeTimer = null;
        this._mouseHeld = false;

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
            if (this.streaming) this._sendSettings();
        });
        this.qualitySlider.addEventListener('input', () => {
            this.qualityValue.textContent = this.qualitySlider.value;
            if (this.streaming) this._sendSettings();
        });

        this.startBtn.addEventListener('click', () => {
            if (this.streaming) {
                this.stop();
            } else {
                this.start();
            }
        });
    }

    _sendSettings() {
        this.ws.send('screen_start', {
            fps: parseInt(this.fpsSlider.value),
            quality: parseInt(this.qualitySlider.value),
            max_width: 1920,
        });
    }

    start() {
        this._sendSettings();
        this._setStreaming(true);
    }

    stop() {
        this.ws.send('screen_stop', {});
        this._setStreaming(false);
        this._pendingFrame = null;
        this._rendering = false;
    }

    _setStreaming(val) {
        this.streaming = val;
        this.startBtn.textContent = val ? 'Stop' : 'Start';
        this.startBtn.classList.toggle('active', val);
        this.statusEl.textContent = val ? 'Streaming...' : 'Stopped';
    }

    // ── Frame Rendering Pipeline ──
    // Only keeps the latest frame; drops stale frames during decode

    _onFrame(payload) {
        this._pendingFrame = payload;
        if (!this._rendering) {
            this._renderNextFrame();
        }
    }

    _renderNextFrame() {
        const payload = this._pendingFrame;
        if (!payload) {
            this._rendering = false;
            return;
        }
        this._pendingFrame = null;
        this._rendering = true;

        const w = payload.width;
        const h = payload.height;
        if (w !== this._naturalWidth || h !== this._naturalHeight) {
            this._naturalWidth = w;
            this._naturalHeight = h;
        }
        this._fitCanvas();

        // Fast path: base64 → binary → Blob → ImageBitmap (GPU-accelerated decode)
        const binary = atob(payload.data);
        const len = binary.length;
        const bytes = new Uint8Array(len);
        for (let i = 0; i < len; i++) bytes[i] = binary.charCodeAt(i);
        const blob = new Blob([bytes], { type: 'image/jpeg' });

        if (typeof createImageBitmap === 'function') {
            createImageBitmap(blob).then((bmp) => {
                this.ctx.drawImage(bmp, 0, 0, this.canvas.width, this.canvas.height);
                bmp.close();
                this._renderNextFrame();
            }).catch(() => {
                this._fallbackRender(payload);
            });
        } else {
            this._fallbackRender(payload);
        }
    }

    _fallbackRender(payload) {
        const img = new Image();
        img.onload = () => {
            this.ctx.drawImage(img, 0, 0, this.canvas.width, this.canvas.height);
            URL.revokeObjectURL(img.src);
            this._renderNextFrame();
        };
        img.onerror = () => {
            this._rendering = false;
        };
        const binary = atob(payload.data);
        const len = binary.length;
        const bytes = new Uint8Array(len);
        for (let i = 0; i < len; i++) bytes[i] = binary.charCodeAt(i);
        img.src = URL.createObjectURL(new Blob([bytes], { type: 'image/jpeg' }));
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

    // ── Coordinate Mapping ──

    _getRemoteCoords(e) {
        const rect = this.canvas.getBoundingClientRect();
        const scaleX = this._naturalWidth / rect.width;
        const scaleY = this._naturalHeight / rect.height;
        return {
            x: Math.round((e.clientX - rect.left) * scaleX),
            y: Math.round((e.clientY - rect.top) * scaleY),
        };
    }

    _mapButton(e) {
        if (e.button === 2) return 3;
        if (e.button === 1) return 2;
        return 1;
    }

    // ── Input Setup ──

    _setupInput() {
        this.canvas.setAttribute('tabindex', '0');

        this._setupMouse();
        this._setupKeyboard();
    }

    _setupMouse() {
        // ── Mouse Move (RAF-coalesced: only sends latest position per frame) ──
        this.canvas.addEventListener('mousemove', (e) => {
            if (!this.streaming) return;
            this._pendingMove = this._getRemoteCoords(e);
            if (!this._moveRafId) {
                this._moveRafId = requestAnimationFrame(() => {
                    this._moveRafId = null;
                    if (this._pendingMove) {
                        this.ws.send('screen_input', {
                            input_type: 'mouse_move',
                            data: this._pendingMove,
                        });
                        this._pendingMove = null;
                    }
                });
            }
        });

        // ── Mouse Down / Up (proper click + drag support) ──
        this.canvas.addEventListener('mousedown', (e) => {
            if (!this.streaming) return;
            e.preventDefault();
            this.canvas.focus();
            const coords = this._getRemoteCoords(e);
            const button = this._mapButton(e);
            this._mouseHeld = true;
            this.ws.send('screen_input', {
                input_type: 'mouse_down',
                data: { ...coords, button },
            });
        });

        // Listen on window so we catch mouseup even outside canvas
        window.addEventListener('mouseup', (e) => {
            if (!this.streaming || !this._mouseHeld) return;
            this._mouseHeld = false;
            const button = this._mapButton(e);
            // Send coords if mouse is over canvas, otherwise just button
            const rect = this.canvas.getBoundingClientRect();
            const overCanvas =
                e.clientX >= rect.left && e.clientX <= rect.right &&
                e.clientY >= rect.top && e.clientY <= rect.bottom;
            const data = { button };
            if (overCanvas) {
                const coords = this._getRemoteCoords(e);
                data.x = coords.x;
                data.y = coords.y;
            }
            this.ws.send('screen_input', {
                input_type: 'mouse_up',
                data,
            });
        });

        // ── Double Click ──
        this.canvas.addEventListener('dblclick', (e) => {
            if (!this.streaming) return;
            e.preventDefault();
            const coords = this._getRemoteCoords(e);
            this.ws.send('screen_input', {
                input_type: 'mouse_dblclick',
                data: { ...coords, button: 1 },
            });
        });

        // ── Context Menu ──
        this.canvas.addEventListener('contextmenu', (e) => e.preventDefault());

        // ── Scroll (dynamic amount based on actual scroll delta) ──
        this.canvas.addEventListener('wheel', (e) => {
            if (!this.streaming) return;
            e.preventDefault();
            const coords = this._getRemoteCoords(e);

            // Normalize delta to pixels regardless of deltaMode
            let pixels = e.deltaY;
            if (e.deltaMode === 1) pixels *= 40;   // lines → pixels
            if (e.deltaMode === 2) pixels *= 800;  // pages → pixels

            // Convert to scroll "clicks" (1 click ~= 3 lines ~= 60px)
            const clicks = Math.max(1, Math.round(Math.abs(pixels) / 60));

            this.ws.send('screen_input', {
                input_type: 'mouse_scroll',
                data: {
                    ...coords,
                    direction: pixels < 0 ? 'up' : 'down',
                    clicks: clicks,
                },
            });
        }, { passive: false });
    }

    _setupKeyboard() {
        const keyMap = {
            'Enter': 'Return', 'Backspace': 'BackSpace', 'Delete': 'Delete',
            'Tab': 'Tab', 'Escape': 'Escape', 'ArrowUp': 'Up', 'ArrowDown': 'Down',
            'ArrowLeft': 'Left', 'ArrowRight': 'Right', 'Home': 'Home', 'End': 'End',
            'PageUp': 'Prior', 'PageDown': 'Next', 'Insert': 'Insert',
            'F1': 'F1', 'F2': 'F2', 'F3': 'F3', 'F4': 'F4', 'F5': 'F5',
            'F6': 'F6', 'F7': 'F7', 'F8': 'F8', 'F9': 'F9', 'F10': 'F10',
            'F11': 'F11', 'F12': 'F12', ' ': 'space',
        };

        // Ignore standalone modifier keys
        const modifierKeys = new Set(['Control', 'Alt', 'Shift', 'Meta', 'CapsLock', 'NumLock', 'ScrollLock']);

        this.canvas.addEventListener('keydown', (e) => {
            if (!this.streaming) return;
            e.preventDefault();

            if (modifierKeys.has(e.key)) return;

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
                // Batch regular text input: accumulate chars and send as one message
                // Reduces round-trips for fast typing while keeping latency under 1 frame
                this._keyTypeBuffer += e.key;
                if (!this._keyTypeTimer) {
                    this._keyTypeTimer = setTimeout(() => {
                        if (this._keyTypeBuffer) {
                            this.ws.send('screen_input', {
                                input_type: 'key_type',
                                data: { text: this._keyTypeBuffer },
                            });
                            this._keyTypeBuffer = '';
                        }
                        this._keyTypeTimer = null;
                    }, 12);
                }
            } else if (e.key.length === 1) {
                // Key with modifiers (ctrl+c, alt+f, etc.)
                parts.push(e.key);
                this.ws.send('screen_input', {
                    input_type: 'key_press',
                    data: { key: parts.join('+') },
                });
            }
        });

        // Flush pending key buffer when canvas loses focus
        this.canvas.addEventListener('blur', () => {
            this._flushKeyBuffer();
        });
    }

    _flushKeyBuffer() {
        if (this._keyTypeBuffer) {
            this.ws.send('screen_input', {
                input_type: 'key_type',
                data: { text: this._keyTypeBuffer },
            });
            this._keyTypeBuffer = '';
        }
        if (this._keyTypeTimer) {
            clearTimeout(this._keyTypeTimer);
            this._keyTypeTimer = null;
        }
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
