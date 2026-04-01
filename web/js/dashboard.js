class Dashboard {
    constructor(ws) {
        this.ws = ws;
        this.container = document.getElementById('dashboard-grid');
        this._pollInterval = null;
        this._prevNet = null;
        this._prevNetTime = null;

        this.ws.on('sysinfo_res', (msg) => this._update(msg.payload));
    }

    startPolling() {
        this.ws.send('sysinfo_req', {});
        this._pollInterval = setInterval(() => {
            this.ws.send('sysinfo_req', {});
        }, 3000);
    }

    stopPolling() {
        if (this._pollInterval) {
            clearInterval(this._pollInterval);
            this._pollInterval = null;
        }
    }

    _update(data) {
        this.container.innerHTML = '';

        // System Info Card
        this._addCard('System', `
            <div class="info-row"><span class="info-label">Hostname</span><span class="info-value">${data.hostname}</span></div>
            <div class="info-row"><span class="info-label">Platform</span><span class="info-value">${data.platform}</span></div>
            <div class="info-row"><span class="info-label">Uptime</span><span class="info-value">${this._formatUptime(data.uptime)}</span></div>
            ${data.battery ? `<div class="info-row"><span class="info-label">Battery</span><span class="info-value">${data.battery.percent}%${data.battery.plugged ? ' (plugged)' : ''}</span></div>` : ''}
        `);

        // CPU Card
        const cpuAvg = data.cpu_percent.length > 0
            ? (data.cpu_percent.reduce((a, b) => a + b, 0) / data.cpu_percent.length).toFixed(1)
            : 0;
        let cpuBars = '<div class="cpu-bars">';
        for (const pct of data.cpu_percent) {
            const color = pct > 80 ? 'var(--danger)' : pct > 50 ? 'var(--warning)' : 'var(--accent)';
            cpuBars += `<div class="cpu-bar" style="height:${Math.max(2, pct)}%;background:${color}" title="${pct}%"></div>`;
        }
        cpuBars += '</div>';
        this._addCard(`CPU (${data.cpu_count} cores) - ${cpuAvg}%`, cpuBars);

        // Memory Card
        const memUsed = this._formatBytes(data.mem.used);
        const memTotal = this._formatBytes(data.mem.total);
        const memClass = data.mem.percent > 80 ? 'danger' : data.mem.percent > 60 ? 'warning' : 'normal';
        this._addCard('Memory', `
            <div class="info-row"><span class="info-label">Used / Total</span><span class="info-value">${memUsed} / ${memTotal}</span></div>
            <div class="progress-bar"><div class="progress-fill ${memClass}" style="width:${data.mem.percent}%"></div></div>
            <div class="info-row"><span class="info-label">${data.mem.percent}% used</span><span class="info-value">${this._formatBytes(data.mem.available)} free</span></div>
        `);

        // Disk Cards
        let diskHtml = '';
        for (const d of data.disk) {
            const diskClass = d.percent > 90 ? 'danger' : d.percent > 75 ? 'warning' : 'normal';
            diskHtml += `
                <div style="margin-bottom:10px">
                    <div class="info-row"><span class="info-label">${d.mountpoint}</span><span class="info-value">${this._formatBytes(d.used)} / ${this._formatBytes(d.total)}</span></div>
                    <div class="progress-bar"><div class="progress-fill ${diskClass}" style="width:${d.percent}%"></div></div>
                    <div class="info-row"><span class="info-label">${d.percent}%</span><span class="info-value">${d.fstype}</span></div>
                </div>
            `;
        }
        this._addCard('Disk', diskHtml);

        // Network Card
        let netHtml = `
            <div class="info-row"><span class="info-label">Total Sent</span><span class="info-value">${this._formatBytes(data.net.bytes_sent)}</span></div>
            <div class="info-row"><span class="info-label">Total Received</span><span class="info-value">${this._formatBytes(data.net.bytes_recv)}</span></div>
        `;
        const now = Date.now();
        if (this._prevNet && this._prevNetTime) {
            const dt = (now - this._prevNetTime) / 1000;
            if (dt > 0) {
                const upSpeed = (data.net.bytes_sent - this._prevNet.bytes_sent) / dt;
                const downSpeed = (data.net.bytes_recv - this._prevNet.bytes_recv) / dt;
                netHtml += `
                    <div class="info-row"><span class="info-label">Upload</span><span class="info-value">${this._formatBytes(upSpeed)}/s</span></div>
                    <div class="info-row"><span class="info-label">Download</span><span class="info-value">${this._formatBytes(downSpeed)}/s</span></div>
                `;
            }
        }
        this._prevNet = data.net;
        this._prevNetTime = now;
        this._addCard('Network', netHtml);

        // GPU Card(s)
        if (data.gpu && data.gpu.length > 0) {
            for (const g of data.gpu) {
                const gpuUtilClass = g.gpu_util > 80 ? 'danger' : g.gpu_util > 50 ? 'warning' : 'normal';
                const memClass = g.mem_percent > 80 ? 'danger' : g.mem_percent > 60 ? 'warning' : 'normal';
                const tempClass = g.temp > 85 ? 'danger' : g.temp > 70 ? 'warning' : 'normal';
                let gpuHtml = `
                    <div class="info-row"><span class="info-label">GPU Usage</span><span class="info-value">${g.gpu_util}%</span></div>
                    <div class="progress-bar"><div class="progress-fill ${gpuUtilClass}" style="width:${g.gpu_util}%"></div></div>
                    <div class="info-row" style="margin-top:8px"><span class="info-label">VRAM</span><span class="info-value">${g.mem_used} / ${g.mem_total} MB</span></div>
                    <div class="progress-bar"><div class="progress-fill ${memClass}" style="width:${g.mem_percent}%"></div></div>
                    <div class="info-row" style="margin-top:8px"><span class="info-label">Temperature</span><span class="info-value ${tempClass === 'danger' ? '' : ''}">${g.temp}°C</span></div>
                    <div class="progress-bar"><div class="progress-fill ${tempClass}" style="width:${Math.min(g.temp, 100)}%"></div></div>
                `;
                if (g.fan_speed > 0) {
                    gpuHtml += `<div class="info-row" style="margin-top:4px"><span class="info-label">Fan</span><span class="info-value">${g.fan_speed}%</span></div>`;
                }
                if (g.power_draw > 0) {
                    gpuHtml += `<div class="info-row"><span class="info-label">Power</span><span class="info-value">${g.power_draw}W / ${g.power_limit}W</span></div>`;
                }
                this._addCard(`GPU ${g.index}: ${g.name}`, gpuHtml);
            }
        }
    }

    _addCard(title, content) {
        const card = document.createElement('div');
        card.className = 'dash-card';
        card.innerHTML = `<h3>${title}</h3>${content}`;
        this.container.appendChild(card);
    }

    _formatUptime(seconds) {
        const d = Math.floor(seconds / 86400);
        const h = Math.floor((seconds % 86400) / 3600);
        const m = Math.floor((seconds % 3600) / 60);
        let parts = [];
        if (d > 0) parts.push(`${d}d`);
        if (h > 0) parts.push(`${h}h`);
        parts.push(`${m}m`);
        return parts.join(' ');
    }

    _formatBytes(bytes) {
        if (bytes === 0) return '0 B';
        const units = ['B', 'KB', 'MB', 'GB', 'TB'];
        const i = Math.floor(Math.log(bytes) / Math.log(1024));
        return (bytes / Math.pow(1024, i)).toFixed(i > 0 ? 1 : 0) + ' ' + units[i];
    }
}
