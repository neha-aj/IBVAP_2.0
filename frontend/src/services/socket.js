import { tokenStorage } from "../utils/tokenStorage";

// See api.js's BASE_URL comment: "127.0.0.1", not "localhost", to avoid the
// IPv6 black-hole this Docker Desktop setup hits on "localhost".
const WS_URL = import.meta.env.VITE_WS_URL || "ws://127.0.0.1:8080/ws";
const MAX_BACKOFF_MS = 30_000;

// Thin wrapper around the Realtime Gateway's WebSocket contract (API Spec
// §8): `{"action":"subscribe","topics":[...]}` out, `{"event":...,"data":...}`
// in. A single shared connection for the whole app -- every hook that wants
// live updates (useCameras, useAlerts, useEvents) subscribes its own topics
// and registers its own event listeners here rather than opening its own
// socket, so a page rendering all three doesn't open three connections.
class RealtimeSocket {
  constructor() {
    this.ws = null;
    this.topics = new Set();
    this.listeners = new Map(); // eventName -> Set<callback>
    this.statusListeners = new Set();
    this.status = "closed";
    this.reconnectAttempt = 0;
    this.reconnectTimer = null;
    this.intentionallyClosed = false;
  }

  _setStatus(status) {
    this.status = status;
    this.statusListeners.forEach((cb) => cb(status));
  }

  onStatusChange(callback) {
    this.statusListeners.add(callback);
    callback(this.status);
    return () => this.statusListeners.delete(callback);
  }

  connect() {
    if (this.ws && (this.ws.readyState === WebSocket.OPEN || this.ws.readyState === WebSocket.CONNECTING)) {
      return;
    }
    const token = tokenStorage.getAccessToken();
    if (!token) return; // not logged in yet -- callers retry after login

    this.intentionallyClosed = false;
    this._setStatus(this.reconnectAttempt > 0 ? "reconnecting" : "connecting");

    const ws = new WebSocket(`${WS_URL}?token=${encodeURIComponent(token)}`);
    this.ws = ws;

    ws.onopen = () => {
      this.reconnectAttempt = 0;
      this._setStatus("open");
      if (this.topics.size > 0) {
        ws.send(JSON.stringify({ action: "subscribe", topics: [...this.topics] }));
      }
    };

    ws.onmessage = (event) => {
      let message;
      try {
        message = JSON.parse(event.data);
      } catch {
        return;
      }
      const callbacks = this.listeners.get(message.event);
      callbacks?.forEach((cb) => cb(message.data));
    };

    ws.onclose = () => {
      if (this.intentionallyClosed) {
        this._setStatus("closed");
        return;
      }
      this._scheduleReconnect();
    };

    ws.onerror = () => {
      ws.close();
    };
  }

  _scheduleReconnect() {
    this._setStatus("reconnecting");
    const delay = Math.min(1000 * 2 ** this.reconnectAttempt, MAX_BACKOFF_MS);
    this.reconnectAttempt += 1;
    clearTimeout(this.reconnectTimer);
    this.reconnectTimer = setTimeout(() => this.connect(), delay);
  }

  disconnect() {
    this.intentionallyClosed = true;
    clearTimeout(this.reconnectTimer);
    this.ws?.close();
    this.ws = null;
    this.topics.clear();
    this._setStatus("closed");
  }

  subscribe(topics) {
    const newTopics = topics.filter((t) => !this.topics.has(t));
    topics.forEach((t) => this.topics.add(t));
    if (newTopics.length === 0) return;

    this.connect();
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ action: "subscribe", topics: newTopics }));
    }
  }

  unsubscribe(topics) {
    topics.forEach((t) => this.topics.delete(t));
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ action: "unsubscribe", topics }));
    }
  }

  on(eventName, callback) {
    if (!this.listeners.has(eventName)) this.listeners.set(eventName, new Set());
    this.listeners.get(eventName).add(callback);
    return () => this.listeners.get(eventName)?.delete(callback);
  }
}

export const socket = new RealtimeSocket();
