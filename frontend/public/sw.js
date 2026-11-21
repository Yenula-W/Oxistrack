// OxisTrack service worker. The app needs the server for data and AI, so nothing is cached:
// this exists so browsers treat OxisTrack as an installable app.
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => event.waitUntil(self.clients.claim()));
self.addEventListener("fetch", () => {});
