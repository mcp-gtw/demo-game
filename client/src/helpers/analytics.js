export function initializeAnalytics() {
    const measurementId = "G-GBNVVN54WN";
    window.dataLayer = [];
    window.gtag = function gtag() {
        window.dataLayer.push(arguments);
    };
    window.gtag("js", new Date());
    window.gtag("config", measurementId, { page_location: location.origin + location.pathname });

    const tag = document.createElement("script");
    tag.async = true;
    tag.src = `https://www.googletagmanager.com/gtag/js?id=${measurementId}`;
    document.head.append(tag);
}
