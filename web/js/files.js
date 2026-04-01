class FileBrowser {
    constructor(ws, showToast) {
        this.ws = ws;
        this.showToast = showToast;
        this.currentPath = '/';
        this.pathEl = document.getElementById('file-path');
        this.listEl = document.getElementById('file-list');
        this.uploadDrop = document.getElementById('upload-drop');
        this.fileInput = document.getElementById('file-input');
        this._downloads = {};

        this.ws.on('file_list_res', (msg) => this._renderList(msg.payload));
        this.ws.on('file_download_chunk', (msg) => this._handleDownloadChunk(msg.payload));
        this.ws.on('file_upload_ack', (msg) => this._handleUploadAck(msg.payload));

        this._setupUpload();
    }

    navigate(path) {
        this.currentPath = path;
        this.pathEl.textContent = path;
        this.ws.send('file_list_req', { path });
    }

    _renderList(payload) {
        if (payload.error) {
            this.showToast(payload.error, 'error');
            return;
        }

        this.currentPath = payload.path;
        this.pathEl.textContent = payload.path;
        this.listEl.innerHTML = '';

        // Parent directory entry
        if (payload.path !== '/') {
            const parentPath = payload.path.split('/').slice(0, -1).join('/') || '/';
            const el = this._createEntry({ name: '..', is_dir: true, size: 0, mtime: 0 }, parentPath);
            this.listEl.appendChild(el);
        }

        // Sort: directories first, then files
        const entries = payload.entries.sort((a, b) => {
            if (a.is_dir && !b.is_dir) return -1;
            if (!a.is_dir && b.is_dir) return 1;
            return a.name.localeCompare(b.name);
        });

        for (const entry of entries) {
            const fullPath = payload.path === '/'
                ? '/' + entry.name
                : payload.path + '/' + entry.name;
            const el = this._createEntry(entry, fullPath);
            this.listEl.appendChild(el);
        }
    }

    _createEntry(entry, fullPath) {
        const el = document.createElement('div');
        el.className = 'file-entry';

        const icon = document.createElement('span');
        icon.className = 'file-icon';
        icon.textContent = entry.is_dir ? '\uD83D\uDCC1' : '\uD83D\uDCC4';

        const name = document.createElement('span');
        name.className = 'file-name' + (entry.is_dir ? ' dir' : '');
        name.textContent = entry.name;

        const size = document.createElement('span');
        size.className = 'file-size';
        size.textContent = entry.is_dir ? '' : this._formatSize(entry.size);

        el.appendChild(icon);
        el.appendChild(name);
        el.appendChild(size);

        el.addEventListener('click', () => {
            if (entry.is_dir) {
                this.navigate(fullPath);
            } else {
                this._startDownload(fullPath, entry.name);
            }
        });

        return el;
    }

    _startDownload(path, filename) {
        const id = Math.random().toString(16).slice(2, 10);
        this._downloads[path] = { chunks: [], filename, totalChunks: null };
        this.ws.send('file_download_req', { path });
        this.showToast(`Downloading ${filename}...`, 'success');
    }

    _handleDownloadChunk(payload) {
        const dl = this._downloads[payload.path];
        if (!dl) return;

        dl.totalChunks = payload.total_chunks;
        dl.chunks[payload.chunk_index] = payload.data;

        if (payload.done) {
            // Combine chunks and trigger browser download
            const combined = dl.chunks.join('');
            const bytes = Uint8Array.from(atob(combined), c => c.charCodeAt(0));
            const blob = new Blob([bytes]);
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = dl.filename;
            a.click();
            URL.revokeObjectURL(url);
            delete this._downloads[payload.path];
            this.showToast(`Downloaded ${dl.filename}`, 'success');
        }
    }

    _setupUpload() {
        this.uploadDrop.addEventListener('dragover', (e) => {
            e.preventDefault();
            this.uploadDrop.classList.add('dragover');
        });
        this.uploadDrop.addEventListener('dragleave', () => {
            this.uploadDrop.classList.remove('dragover');
        });
        this.uploadDrop.addEventListener('drop', (e) => {
            e.preventDefault();
            this.uploadDrop.classList.remove('dragover');
            this._uploadFiles(e.dataTransfer.files);
        });
        this.fileInput.addEventListener('change', () => {
            this._uploadFiles(this.fileInput.files);
            this.fileInput.value = '';
        });
    }

    async _uploadFiles(files) {
        for (const file of files) {
            await this._uploadFile(file);
        }
    }

    async _uploadFile(file) {
        const CHUNK_SIZE = 524288;
        const totalChunks = Math.max(1, Math.ceil(file.size / CHUNK_SIZE));
        const targetPath = (this.currentPath === '/' ? '/' : this.currentPath + '/') + file.name;

        this.ws.send('file_upload_start', {
            path: targetPath,
            total_size: file.size,
            total_chunks: totalChunks
        });

        for (let i = 0; i < totalChunks; i++) {
            const slice = file.slice(i * CHUNK_SIZE, (i + 1) * CHUNK_SIZE);
            const buf = await slice.arrayBuffer();
            const b64 = this._arrayBufferToBase64(buf);
            this.ws.send('file_upload_chunk', {
                path: targetPath,
                chunk_index: i,
                data: b64,
                done: i === totalChunks - 1
            });
        }

        this.showToast(`Uploaded ${file.name}`, 'success');
        // Refresh after a short delay
        setTimeout(() => this.navigate(this.currentPath), 500);
    }

    _arrayBufferToBase64(buffer) {
        const bytes = new Uint8Array(buffer);
        let binary = '';
        const chunkSize = 8192;
        for (let i = 0; i < bytes.length; i += chunkSize) {
            const chunk = bytes.subarray(i, i + chunkSize);
            binary += String.fromCharCode.apply(null, chunk);
        }
        return btoa(binary);
    }

    _formatSize(bytes) {
        if (bytes === 0) return '0 B';
        const units = ['B', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(1024));
        return (bytes / Math.pow(1024, i)).toFixed(i > 0 ? 1 : 0) + ' ' + units[i];
    }

    _handleUploadAck(payload) {
        if (!payload.success) {
            this.showToast(`Upload error: ${payload.error}`, 'error');
        }
    }
}
