// Lets the phone install the studio as an app. Always fetches fresh from the PC; nothing is cached.
self.addEventListener('install', e => self.skipWaiting());
self.addEventListener('activate', e => self.clients.claim());
self.addEventListener('fetch', () => {});
