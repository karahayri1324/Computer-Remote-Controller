document.addEventListener('DOMContentLoaded', () => {
    Auth.requireAuth();

    // Show username
    const uname = Auth.getUsername();
    const usernameDisplay = document.getElementById('username-display');
    if (uname && usernameDisplay) usernameDisplay.textContent = uname;

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

    const terminalMgr = new TerminalManager(ws);
    terminalMgr.init();

    const fileBrowser = new FileBrowser(ws, showToast);

    const dashboard = new Dashboard(ws);
    const settings = new Settings();

    const isDesktop = window.innerWidth > 768;
    let remoteScreen = null;
    if (isDesktop) {
        remoteScreen = new RemoteScreen(ws, showToast);
    }

    // File path navigation
    const filePathInput = document.getElementById('file-path');
    const goBtn = document.getElementById('go-btn');
    const fileUpBtn = document.getElementById('file-up-btn');

    goBtn.addEventListener('click', () => {
        const p = filePathInput.value.trim() || '/';
        fileBrowser.navigate(p);
    });

    filePathInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            const p = filePathInput.value.trim() || '/';
            fileBrowser.navigate(p);
            filePathInput.blur();
        }
        if (e.key === 'Escape') filePathInput.blur();
    });

    fileUpBtn.addEventListener('click', () => {
        const cur = fileBrowser.currentPath;
        const parent = cur === '/' ? '/' : cur.split('/').slice(0, -1).join('/') || '/';
        fileBrowser.navigate(parent);
    });

    // Mobile keyboard bar
    const kbBar = document.getElementById('mobile-keyboard-bar');
    if (kbBar) {
        kbBar.addEventListener('click', (e) => {
            const btn = e.target.closest('button');
            if (!btn) return;
            const key = btn.dataset.key;
            if (key) {
                ws.send('shell_input', { shell_id: terminalMgr.activeId, data: key });
                btn.style.background = 'var(--accent)';
                btn.style.color = 'var(--bg-primary)';
                setTimeout(() => {
                    btn.style.background = '';
                    btn.style.color = '';
                }, 120);
            }
        });
    }

    const tabs = document.querySelectorAll('nav button[data-tab]');
    const tabContents = document.querySelectorAll('.tab-content');

    function switchTab(tabName) {
        tabs.forEach(t => t.classList.toggle('active', t.dataset.tab === tabName));
        tabContents.forEach(tc => tc.classList.toggle('active', tc.id === 'tab-' + tabName));

        if (tabName === 'terminal') {
            terminalMgr.fit();
            terminalMgr.focus();
        } else if (tabName === 'files') {
            fileBrowser.navigate(fileBrowser.currentPath);
        } else if (tabName === 'dashboard') {
            dashboard.startPolling();
        } else if (tabName === 'screen' && remoteScreen) {
            remoteScreen.check();
        }

        if (tabName !== 'dashboard') dashboard.stopPolling();
        if (tabName !== 'screen' && remoteScreen && remoteScreen.streaming) remoteScreen.stop();
    }

    tabs.forEach(btn => {
        btn.addEventListener('click', () => switchTab(btn.dataset.tab));
    });

    document.getElementById('logout-btn').addEventListener('click', () => Auth.logout());

    const visualViewport = window.visualViewport;
    if (visualViewport) {
        visualViewport.addEventListener('resize', () => {
            document.body.style.height = visualViewport.height + 'px';
            setTimeout(() => terminalMgr.fit(), 50);
        });
    }

    ws.connect();
    switchTab('terminal');

    setTimeout(() => {
        const ls = document.getElementById('loading-screen');
        if (ls) { ls.style.opacity = '0'; setTimeout(() => ls.remove(), 500); }
    }, 3000);
});
