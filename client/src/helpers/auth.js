export class AuthController {
    constructor({ store, createToken, createOAuth, fetcher = (...args) => fetch(...args), redirect = (url) => location.assign(url), reset }) {
        this.store = store;
        this.createToken = createToken;
        this.createOAuth = createOAuth;
        this.fetcher = fetcher;
        this.redirect = redirect;
        this.reset = reset;
        this.socket = null;
        this.generation = 0;
    }

    async select(method) {
        if (!this.store.availableAuthMethods.includes(method)) {
            throw new Error("Authentication method is unavailable");
        }

        const generation = ++this.generation;
        this.socket?.disconnect();
        this.socket = null;
        this.store.selectedAuthMethod = method;
        this.reset();

        if (method === "oauth") {
            const response = await this.fetcher("/app/oauth/consent", { method: "POST" });

            if (generation !== this.generation) {
                return;
            }

            if (!response.ok) {
                this.redirect("/app/oauth/login");
                return;
            }
        }

        this.socket = method === "token" ? this.createToken() : this.createOAuth();
        this.socket.connect();
    }

    async switchMethod() {
        const previous = this.store.selectedAuthMethod;
        this.generation += 1;
        this.socket?.disconnect();
        this.socket = null;
        this.store.selectedAuthMethod = null;
        this.reset();

        if (previous === "oauth") {
            await this.fetcher("/app/oauth/logout", { method: "POST" });
        }
    }

    requestStats() {
        this.socket?.requestStats();
    }
}
