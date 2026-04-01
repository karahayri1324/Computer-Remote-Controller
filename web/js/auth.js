const Auth = {
    getToken() {
        return sessionStorage.getItem('access_token');
    },
    setToken(token) {
        sessionStorage.setItem('access_token', token);
    },
    clearToken() {
        sessionStorage.removeItem('access_token');
    },
    requireAuth() {
        if (!this.getToken()) {
            window.location.href = '/index.html';
        }
    },
    logout() {
        this.clearToken();
        window.location.href = '/index.html';
    }
};
