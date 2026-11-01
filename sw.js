// 最小 Service Worker：满足“添加到主屏幕”的条件，不缓存任何内容
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", e => e.waitUntil(self.clients.claim()));
self.addEventListener("fetch", () => {});
