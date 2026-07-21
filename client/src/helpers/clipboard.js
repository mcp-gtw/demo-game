// copy text to the clipboard, falling back to a hidden textarea outside a secure context.

export async function copyText(text) {
    if (navigator.clipboard) {
        try {
            await navigator.clipboard.writeText(text);
            return;
        } catch {
            // the clipboard api is blocked outside a secure context, use the selection path
        }
    }

    const field = document.createElement("textarea");
    field.value = text;
    field.style.position = "fixed";
    field.style.opacity = "0";
    document.body.appendChild(field);
    field.select();
    document.execCommand("copy");
    field.remove();
}
