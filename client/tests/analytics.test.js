import { afterEach, expect, test } from "vitest";
import { initializeAnalytics } from "../src/helpers/analytics.js";

afterEach(() => {
    document.head.querySelector("script")?.remove();
    delete window.dataLayer;
    delete window.gtag;
    history.replaceState(null, "", "/");
});

test("analytics excludes credential queries and preserves its public event queue", () => {
    history.replaceState(null, "", "/?code=private-code&token=private-token#private-fragment");
    initializeAnalytics();
    const events = window.dataLayer.map(event => [...event]);
    expect(events[0][0]).toBe("js");
    expect(events[0][1]).toBeInstanceOf(Date);
    expect(events[1]).toEqual(["config", "G-GBNVVN54WN", { page_location: location.origin + "/" }]);
    expect(JSON.stringify(events)).not.toContain("private-");
    window.gtag("event", "public-game-event");
    expect([...window.dataLayer.at(-1)]).toEqual(["event", "public-game-event"]);
    const script = document.head.querySelector("script");
    expect(script.src).toBe("https://www.googletagmanager.com/gtag/js?id=G-GBNVVN54WN");
    expect(script.async).toBe(true);
});
