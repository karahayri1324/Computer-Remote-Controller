class WS {
    constructor() {
        this.ws = null;
        this.handlers = {};
        this._reconnectDelay = 1000;
        this._maxReconnectDelay = 30000;
    }

    connect() {
        const token = Auth.getToken();
        if (!token) return;

        const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
        const url = `${proto}//${location.host}/ws/client?token=${encodeURIComponent(token)}`;

        this.ws = new WebSocket(url);

        this.ws.onopen = () => {
            this._reconnectDelay = 1000;
            this._dispatch('_connected', {});
        };

        this.ws.onmessage = (event) => {
            try {
                const msg = JSON.parse(event.data);
                this._dispatch(msg.type, msg);
            } catch (e) {
                console.error('WS parse error:', e);
            }
        };

        this.ws.onclose = (event) => {
            this._dispatch('_disconnected', {});
            if (event.code === 4001) {
                Auth.logout();
                return;
            }
            setTimeout(() => this.connect(), this._reconnectDelay);
            this._reconnectDelay = Math.min(this._reconnectDelay * 2, this._maxReconnectDelay);
        };

        this.ws.onerror = () => {};
    }

    send(type, payload = {}) {
        const msg = { type, payload };
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify(msg));
        }
    }

    on(type, callback) {
        if (!this.handlers[type]) this.handlers[type] = [];
        this.handlers[type].push(callback);
    }

    _dispatch(type, msg) {
        const cbs = this.handlers[type] || [];
        cbs.forEach(cb => {
            try { cb(msg); } catch (e) { console.error('Handler error:', e); }
        });
    }
}
