/**
 * Centralized Application Configuration
 *
 * Reads backend URL from environment variables:
 * - VITE_BACKEND_URL (configured in .env)
 *
 * Exports:
 * - API_BASE (and alias API_BASE_URL): HTTP/HTTPS base URL without trailing slash
 * - WS_BASE (and alias WS_BASE_URL): WebSocket WS/WSS base URL without trailing slash
 * - getWsUrl(): Helper to convert any HTTP(S) URL to WS(S)
 */

const rawBackendUrl = (import.meta.env.VITE_BACKEND_URL || '').trim();

// Normalize backend URL by removing any trailing slashes
export const API_BASE = rawBackendUrl.replace(/\/+$/, '');
export const API_BASE_URL = API_BASE;

/**
 * Dynamically converts HTTP(S) URL to WebSocket WS(S) URL:
 * - https:// -> wss://
 * - http://  -> ws://
 *
 * @param {string} [httpUrl=API_BASE]
 * @returns {string} WebSocket base URL without trailing slash
 */
export const getWsUrl = (httpUrl = API_BASE) => {
    if (!httpUrl) return '';
    return httpUrl
        .replace(/^https:\/\//i, 'wss://')
        .replace(/^http:\/\//i, 'ws://')
        .replace(/\/+$/, '');
};

export const WS_BASE = getWsUrl(API_BASE);
export const WS_BASE_URL = WS_BASE;

export default {
    API_BASE,
    API_BASE_URL,
    WS_BASE,
    WS_BASE_URL,
    getWsUrl,
};

