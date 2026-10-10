import { GameSocket } from "./GameSocket.js";

export class OAuthGameSocket extends GameSocket {
    constructor(baseUrl, handlers, fetchTicket = () => fetch("/app/oauth/ticket", { method: "POST" })) {
        super(baseUrl, handlers, async (generation) => {
            const response = await fetchTicket();

            if (!response.ok) {
                if ((response.status === 401 || response.status === 403) && !this.stopped && generation === this.generation) {
                    handlers.onAuthRequired?.();
                }

                throw new Error("OAuth browser session unavailable");
            }

            const { ticket } = await response.json();
            return `${baseUrl}?ticket=${encodeURIComponent(ticket)}`;
        });
    }
}
