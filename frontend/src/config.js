// Centralized API configuration supporting environment variables and relative URLs
export const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/$/, '');

// The Vite dev-server proxy buffers multipart/x-mixed-replace (MJPEG) streams
// and never flushes frames to the browser. Stream endpoints must bypass the proxy
// and talk directly to Flask. In production, VITE_API_BASE_URL covers both.
export const STREAM_BASE_URL = (
  import.meta.env.VITE_API_BASE_URL ||
  import.meta.env.VITE_STREAM_BASE_URL ||
  'http://127.0.0.1:5000'
).replace(/\/$/, '');

export function getApiUrl(path) {
  const cleanPath = path.startsWith('/') ? path : `/${path}`;
  return `${API_BASE_URL}${cleanPath}`;
}

/** Use this for /video_feed and /raw_feed — bypasses the Vite proxy. */
export function getStreamUrl(path) {
  const cleanPath = path.startsWith('/') ? path : `/${path}`;
  return `${STREAM_BASE_URL}${cleanPath}`;
}
