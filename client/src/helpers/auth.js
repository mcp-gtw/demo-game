const METHOD_KEY = "mcp-game-auth-method";

export class AuthController {
    constructor({ store, createToken, createOAuth, fetcher = (...args) => fetch(...args), redirect = (url) => location.assign(url), storage = localStorage, tabStorage = sessionStorage, reset }) {
        this.store = store;
        this.createToken = createToken;
        this.createOAuth = createOAuth;
        this.fetcher = fetcher;
        this.redirect = redirect;
        this.reset = reset;
        this.storage = storage;
        this.tabStorage = tabStorage;
        this.socket = null;
        this.generation = 0;
    }

    async restore(callback = false) {
        if (callback && this.store.availableAuthMethods.includes("oauth")) {
            await this.select("oauth");
            return;
        }

        const method = this.tabStorage.getItem(METHOD_KEY) ?? this.storage.getItem(METHOD_KEY);

        if (this.store.availableAuthMethods.includes(method)) {
            await this.select(method, true);
        }
    }

    expire() {
        this.generation += 1;
        this.socket?.disconnect();
        this.socket = null;
        this.store.selectedAuthMethod = null;
        this.storage.removeItem(METHOD_KEY);
        this.tabStorage.removeItem(METHOD_KEY);
        this.reset();
    }

    async select(method, resume = false) {
        if (!this.store.availableAuthMethods.includes(method)) {
            throw new Error("Authentication method is unavailable");
        }

        const generation = ++this.generation;
        this.socket?.disconnect();
        this.socket = null;
        this.store.selectedAuthMethod = method;
        this.storage.setItem(METHOD_KEY, method);
        this.tabStorage.setItem(METHOD_KEY, method);
        this.reset();

        if (method === "oauth") {
            const endpoint = resume ? "/app/oauth/session" : "/app/oauth/consent";
            let response;

            try {
                response = await this.fetcher(endpoint, { method: "POST" });
            } catch (error) {
                if (generation === this.generation) {
                    this.store.selectedAuthMethod = null;
                    this.reset();
                }

                throw error;
            }

            if (generation !== this.generation) {
                return;
            }

            if (!response.ok) {
                if (response.status === 429 || response.status >= 500) {
                    this.store.selectedAuthMethod = null;
                    this.reset();
                    throw new Error("OAuth session temporarily unavailable");
                }

                if (resume) {
                    this.expire();
                } else {
                    this.redirect("/app/oauth/login");
                }

                return;
            }
        }

        this.socket = method === "token" ? this.createToken() : this.createOAuth();
        this.socket.connect();
    }

    async switchMethod() {
        const previous = this.store.selectedAuthMethod;
        this.expire();

        if (previous === "oauth") {
            await this.fetcher("/app/oauth/logout", { method: "POST" });
        }
    }

    requestStats() {
        this.socket?.requestStats();
    }
}
