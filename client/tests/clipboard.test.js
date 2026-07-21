import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { copyText } from "../src/helpers/clipboard.js";

let exec;

beforeEach(() => {
    exec = vi.fn().mockReturnValue(true);
    document.execCommand = exec;
});

afterEach(() => {
    delete navigator.clipboard;
    delete document.execCommand;
});

describe("copyText", () => {
    it("uses the clipboard api when it succeeds", async () => {
        const writeText = vi.fn().mockResolvedValue();
        navigator.clipboard = { writeText };
        await copyText("hello");
        expect(writeText).toHaveBeenCalledWith("hello");
        expect(exec).not.toHaveBeenCalled();
    });

    it("falls back to a textarea when the clipboard api throws", async () => {
        navigator.clipboard = { writeText: vi.fn().mockRejectedValue(new Error("blocked")) };
        await copyText("world");
        expect(exec).toHaveBeenCalledWith("copy");
    });

    it("falls back when there is no clipboard api", async () => {
        await copyText("plain");
        expect(exec).toHaveBeenCalledWith("copy");
    });
});
