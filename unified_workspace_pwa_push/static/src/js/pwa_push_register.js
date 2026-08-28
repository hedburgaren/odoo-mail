/** @odoo-module **/

// =============================================================================
// unified_workspace_pwa_push - frontend-registrering av push-prenumeration
// =============================================================================

import { _t } from "@web/core/l10n/translation";
import { rpc } from "@web/core/network/rpc";

function urlBase64ToUint8Array(base64String) {
    const padding = '='.repeat((4 - (base64String.length % 4)) % 4);
    const base64 = (base64String + padding)
        .replace(/\-/g, '+')
        .replace(/_/g, '/');
    const rawData = window.atob(base64);
    return Uint8Array.from([...rawData].map((char) => char.charCodeAt(0)));
}

async function subscribePush(registration) {
    if (!('PushManager' in window)) {
        console.warn('[PWA PUSH] PushManager stöds inte.');
        return;
    }

    const permission = await Notification.requestPermission();
    if (permission !== 'granted') {
        console.warn('[PWA PUSH] Notistillåtelse ej beviljad:', permission);
        return;
    }

    let publicKey;
    try {
        const result = await rpc('/pwa/vapid_public_key', {});
        publicKey = result.public_key;
    } catch (e) {
        console.error('[PWA PUSH] Kunde inte hämta VAPID-nyckel:', e);
        return;
    }

    if (!publicKey) {
        console.error('[PWA PUSH] Ingen VAPID-nyckel returnerad.');
        return;
    }

    let subscription;
    try {
        subscription = await registration.pushManager.subscribe({
            userVisibleOnly: true,
            applicationServerKey: urlBase64ToUint8Array(publicKey),
        });
    } catch (e) {
        console.error('[PWA PUSH] Prenumeration misslyckades:', e);
        return;
    }

    const subJson = subscription.toJSON();
    try {
        await rpc('/pwa/push/subscribe', {
            endpoint: subJson.endpoint,
            p256dh: subJson.keys.p256dh,
            auth: subJson.keys.auth,
        });
        console.log('[PWA PUSH] Prenumeration sparad.');
    } catch (e) {
        console.error('[PWA PUSH] Kunde inte spara prenumeration:', e);
    }
}

document.addEventListener('DOMContentLoaded', function () {
    if (!('serviceWorker' in navigator)) return;
    if (!('PushManager' in window)) return;

    navigator.serviceWorker.ready.then(function (registration) {
        registration.pushManager.getSubscription().then(function (subscription) {
            if (subscription === null) {
                subscribePush(registration);
            } else {
                // Synka befintlig prenumeration till servern
                const subJson = subscription.toJSON();
                rpc('/pwa/push/subscribe', {
                    endpoint: subJson.endpoint,
                    p256dh: subJson.keys.p256dh,
                    auth: subJson.keys.auth,
                }).catch(function (e) {
                    console.warn('[PWA PUSH] Kunde inte synka prenumeration:', e);
                });
            }
        });
    });
});
