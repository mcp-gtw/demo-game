import { GameSocket } from "./GameSocket.js";

export class OAuthGameSocket extends GameSocket {
    constructor(baseUrl, handlers, fetchTicket = () => fetch("/app/oauth/ticket", { method: "POST" })) {
        super(baseUrl, handlers, async () => {
            const response = await fetchTicket();

            if (!response.ok) {
                throw new Error("OAuth browser session unavailable");
            }

            const { ticket } = await response.json();
            return `${baseUrl}?ticket=${encodeURIComponent(ticket)}`;
        });
    }
}
