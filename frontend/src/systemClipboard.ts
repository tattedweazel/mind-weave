/**
 * Single place that calls the browser Clipboard API (easier to mock in tests than `navigator` on globalThis).
 */

export async function writeTextToSystemClipboard(text: string): Promise<void> {
    await globalThis.navigator.clipboard.writeText(text);
}
