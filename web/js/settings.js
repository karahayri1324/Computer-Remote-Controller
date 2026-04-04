class Settings {
    constructor() {
        this.overlay = document.getElementById('settings-overlay');
        this.token = () => sessionStorage.getItem('access_token');
        this._bind();
    }

    _headers() {
        return {
            'Content-Type': 'application/json',
            'Authorization': 'Bearer ' + this.token(),
        };
    }

    _bind() {
        document.getElementById('settings-btn').addEventListener('click', () => this.open());
        document.getElementById('settings-close').addEventListener('click', () => this.close());
        this.overlay.addEventListener('click', (e) => {
            if (e.target === this.overlay) this.close();
        });

        // Password change
        document.getElementById('pw-form').addEventListener('submit', (e) => {
            e.preventDefault();
            this._changePassword();
        });

        // 2FA toggle
        document.getElementById('tfa-toggle-btn').addEventListener('click', () => this._toggleTFA());
        document.getElementById('tfa-verify-btn').addEventListener('click', () => this._verifyTFA());
        document.getElementById('tfa-cancel-btn').addEventListener('click', () => this._resetTFAUI());
        document.getElementById('tfa-disable-confirm-btn').addEventListener('click', () => this._disableTFA());
        document.getElementById('tfa-disable-cancel-btn').addEventListener('click', () => this._resetTFAUI());

        // Auto-filter digits only
        document.getElementById('tfa-verify-code').addEventListener('input', (e) => {
            e.target.value = e.target.value.replace(/\D/g, '');
        });
    }

    open() {
        this.overlay.classList.remove('hidden');
        this._loadTFAStatus();
        // Clear forms
        document.getElementById('pw-old').value = '';
        document.getElementById('pw-new').value = '';
        document.getElementById('pw-confirm').value = '';
        document.getElementById('pw-msg').textContent = '';
    }

    close() {
        this.overlay.classList.add('hidden');
        this._resetTFAUI();
    }

    async _changePassword() {
        const msg = document.getElementById('pw-msg');
        const newPw = document.getElementById('pw-new').value;
        const confirm = document.getElementById('pw-confirm').value;

        if (newPw !== confirm) {
            msg.textContent = 'Passwords do not match';
            msg.style.color = 'var(--danger)';
            return;
        }

        try {
            const resp = await fetch('/api/change-password', {
                method: 'POST',
                headers: this._headers(),
                body: JSON.stringify({
                    old_password: document.getElementById('pw-old').value,
                    new_password: newPw,
                }),
            });
            const data = await resp.json();
            if (!resp.ok) {
                msg.textContent = data.error || 'Failed';
                msg.style.color = 'var(--danger)';
            } else {
                msg.textContent = 'Password changed successfully';
                msg.style.color = 'var(--success)';
                document.getElementById('pw-old').value = '';
                document.getElementById('pw-new').value = '';
                document.getElementById('pw-confirm').value = '';
            }
        } catch {
            msg.textContent = 'Connection error';
            msg.style.color = 'var(--danger)';
        }
    }

    async _loadTFAStatus() {
        const text = document.getElementById('tfa-status-text');
        const btn = document.getElementById('tfa-toggle-btn');

        try {
            const resp = await fetch('/api/2fa/status', { headers: this._headers() });
            const data = await resp.json();
            if (data.enabled) {
                text.textContent = '2FA is enabled';
                text.style.color = 'var(--success)';
                btn.textContent = 'Disable 2FA';
                btn.style.background = 'var(--danger)';
            } else {
                text.textContent = '2FA is not enabled';
                text.style.color = 'var(--text-muted)';
                btn.textContent = 'Enable 2FA';
                btn.style.background = 'var(--accent)';
            }
            btn.style.display = '';
            btn.dataset.enabled = data.enabled;
        } catch {
            text.textContent = 'Could not load status';
        }
    }

    async _toggleTFA() {
        const btn = document.getElementById('tfa-toggle-btn');
        if (btn.dataset.enabled === 'true') {
            // Show disable form
            document.getElementById('tfa-status-area').style.display = 'none';
            document.getElementById('tfa-disable-area').classList.remove('hidden');
            document.getElementById('tfa-disable-pw').value = '';
            document.getElementById('tfa-disable-msg').textContent = '';
        } else {
            // Start setup
            await this._setupTFA();
        }
    }

    async _setupTFA() {
        const msg = document.getElementById('tfa-msg');
        msg.textContent = '';
        try {
            const resp = await fetch('/api/2fa/setup', {
                method: 'POST',
                headers: this._headers(),
            });
            const data = await resp.json();
            if (!resp.ok) {
                msg.textContent = data.error || 'Setup failed';
                msg.style.color = 'var(--danger)';
                return;
            }
            // Show QR + secret
            document.getElementById('tfa-status-area').style.display = 'none';
            document.getElementById('tfa-setup-area').classList.remove('hidden');
            document.getElementById('tfa-qr').innerHTML = data.qr_svg;
            document.getElementById('tfa-secret').value = data.secret;
            document.getElementById('tfa-verify-code').value = '';
            document.getElementById('tfa-verify-code').focus();
        } catch {
            msg.textContent = 'Connection error';
            msg.style.color = 'var(--danger)';
        }
    }

    async _verifyTFA() {
        const msg = document.getElementById('tfa-msg');
        const code = document.getElementById('tfa-verify-code').value.trim();
        if (code.length !== 6) {
            msg.textContent = 'Enter 6-digit code';
            msg.style.color = 'var(--danger)';
            return;
        }
        try {
            const resp = await fetch('/api/2fa/enable', {
                method: 'POST',
                headers: this._headers(),
                body: JSON.stringify({ code }),
            });
            const data = await resp.json();
            if (!resp.ok) {
                msg.textContent = data.error || 'Verification failed';
                msg.style.color = 'var(--danger)';
                document.getElementById('tfa-verify-code').value = '';
                document.getElementById('tfa-verify-code').focus();
            } else {
                this._resetTFAUI();
                this._loadTFAStatus();
            }
        } catch {
            msg.textContent = 'Connection error';
            msg.style.color = 'var(--danger)';
        }
    }

    async _disableTFA() {
        const msg = document.getElementById('tfa-disable-msg');
        const pw = document.getElementById('tfa-disable-pw').value;
        if (!pw) {
            msg.textContent = 'Enter your password';
            msg.style.color = 'var(--danger)';
            return;
        }
        try {
            const resp = await fetch('/api/2fa/disable', {
                method: 'POST',
                headers: this._headers(),
                body: JSON.stringify({ password: pw }),
            });
            const data = await resp.json();
            if (!resp.ok) {
                msg.textContent = data.error || 'Failed';
                msg.style.color = 'var(--danger)';
            } else {
                this._resetTFAUI();
                this._loadTFAStatus();
            }
        } catch {
            msg.textContent = 'Connection error';
            msg.style.color = 'var(--danger)';
        }
    }

    _resetTFAUI() {
        document.getElementById('tfa-status-area').style.display = '';
        document.getElementById('tfa-setup-area').classList.add('hidden');
        document.getElementById('tfa-disable-area').classList.add('hidden');
    }
}
