const Auth = {
    getToken() { return localStorage.getItem('access_token'); },
    setToken(token) { localStorage.setItem('access_token', token); },
    getUsername() { return localStorage.getItem('rc_username'); },
    setUsername(u) { localStorage.setItem('rc_username', u); },
    clearToken() {
        localStorage.removeItem('access_token');
        localStorage.removeItem('rc_username');
    },
    requireAuth() {
        if (!this.getToken()) window.location.href = '/';
    },
    logout() {
        this.clearToken();
        window.location.href = '/';
    }
};
