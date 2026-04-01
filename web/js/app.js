document.addEventListener('DOMContentLoaded', () => {
    Auth.requireAuth();

    const ws = new WS();
    const statusDot = document.getElementById('status-dot');
    const toastContainer = document.getElementById('toast-container');

    function showToast(message, type = 'info') {
        const toast = document.createElement('div');
        toast.className = `toast ${type}`;
        toast.textContent = message;
        toastContainer.appendChild(toast);
        setTimeout(() => toast.remove(), 4000);
    }

    // Agent status
    ws.on('agent_status', (msg) => {
        statusDot.className = 'status-dot ' + (msg.payload.online ? 'online' : 'offline');
        statusDot.title = msg.payload.online ? 'Agent Online' : 'Agent Offline';
    });
    ws.on('_connected', () => {
        statusDot.className = 'status-dot connecting';
    });
    ws.on('_disconnected', () => {
        statusDot.className = 'status-dot offline';
    });
    ws.on('error', (msg) => {
        showToast(msg.payload.message, 'error');
    });

    // Terminal
    const terminalUI = new TerminalUI(document.getElementById('terminal-container'), ws);
    terminalUI.init();

    // File Browser
    const fileBrowser = new FileBrowser(ws, showToast);

    // Dashboard
    const dashboard = new Dashboard(ws);

    // Screen (desktop only)
    const isDesktop = window.innerWidth > 768;
    let remoteScreen = null;
    if (isDesktop) {
        remoteScreen = new RemoteScreen(ws, showToast);
    }

    // Mobile keyboard bar
    const kbBar = document.getElementById('mobile-keyboard-bar');
    if (kbBar) {
        kbBar.addEventListener('click', (e) => {
            const btn = e.target.closest('button');
            if (!btn) return;
            const key = btn.dataset.key;
            if (key) {
                ws.send('shell_input', { data: key });
                // Brief visual feedback
                btn.style.background = 'var(--accent)';
                btn.style.color = 'var(--bg-primary)';
                setTimeout(() => {
                    btn.style.background = '';
                    btn.style.color = '';
                }, 120);
            }
        });
    }

    // Tab switching
    const tabs = document.querySelectorAll('nav button[data-tab]');
    const tabContents = document.querySelectorAll('.tab-content');

    function switchTab(tabName) {
        tabs.forEach(t => t.classList.toggle('active', t.dataset.tab === tabName));
        tabContents.forEach(tc => tc.classList.toggle('active', tc.id === 'tab-' + tabName));

        if (tabName === 'terminal') {
            terminalUI.fit();
            terminalUI.focus();
        } else if (tabName === 'files') {
            fileBrowser.navigate(fileBrowser.currentPath);
        } else if (tabName === 'dashboard') {
            dashboard.startPolling();
        } else if (tabName === 'screen' && remoteScreen) {
            remoteScreen.check();
        }

        if (tabName !== 'dashboard') {
            dashboard.stopPolling();
        }
        if (tabName !== 'screen' && remoteScreen && remoteScreen.streaming) {
            remoteScreen.stop();
        }
    }

    tabs.forEach(btn => {
        btn.addEventListener('click', () => switchTab(btn.dataset.tab));
    });

    // Logout
    document.getElementById('logout-btn').addEventListener('click', () => {
        Auth.logout();
    });

    // Go button for file path
    document.getElementById('go-btn').addEventListener('click', () => {
        const path = prompt('Enter path:', fileBrowser.currentPath);
        if (path) fileBrowser.navigate(path);
    });

    // Mobile: handle viewport resize (virtual keyboard)
    const visualViewport = window.visualViewport;
    if (visualViewport) {
        visualViewport.addEventListener('resize', () => {
            // Update body height when virtual keyboard opens/closes
            document.body.style.height = visualViewport.height + 'px';
            // Refit terminal
            setTimeout(() => terminalUI.fit(), 50);
        });
    }

    // Connect
    ws.connect();

    // Default tab
    switchTab('terminal');
});
