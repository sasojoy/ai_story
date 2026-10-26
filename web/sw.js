// 手機通知（減法季批 9）：伺服器經推送服務送來一則（server_push.WebPush，內文是 {title, body, tag, url} 的 JSON），這裡把它跳出來；
// 點了回到遊戲（已經開著的分頁就叫到前面，沒有就開一個）。只管通知，不攔任何網路請求、不存快取。
self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", (event) => event.waitUntil(self.clients.claim()));

self.addEventListener("push", (event) => {
  let data = {};
  try {
    data = event.data ? event.data.json() : {};
  } catch (e) {
    data = { body: event.data ? event.data.text() : "" };
  }
  const title = data.title || "天下大勢";
  event.waitUntil(self.registration.showNotification(title, {
    body: data.body || "",
    tag: data.tag || undefined,
    renotify: !!data.tag,
    icon: "/static/icon.svg",
    badge: "/static/icon.svg",
    data: { url: data.url || "/" },
  }));
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const url = (event.notification.data && event.notification.data.url) || "/";
  event.waitUntil(self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((list) => {
    for (const c of list) {
      if ("focus" in c) return c.focus();
    }
    return self.clients.openWindow(url);
  }));
});
