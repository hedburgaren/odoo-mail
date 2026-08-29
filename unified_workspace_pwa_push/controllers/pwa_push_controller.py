# =============================================================================
# PWA Push HTTP-kontroller
# =============================================================================

import logging

from odoo import http
from odoo.http import request

from odoo.addons.arc_industrial_ui.controllers.pwa import ArcPwaController

_logger = logging.getLogger(__name__)


class PwaPushController(http.Controller):

    @http.route('/pwa/push/status', type='json', auth='public', methods=['POST'])
    def push_status(self, **kw):
        """Returnera inloggningsstatus for push-prenumeration."""
        is_public = request.env.user._is_public()
        return {
            'is_logged_in': not is_public,
            'partner_id': request.env.user.partner_id.id if not is_public else None,
        }

    @http.route('/pwa/vapid_public_key', type='json', auth='public', methods=['POST'])
    def vapid_public_key(self, **kw):
        """Returnera VAPID publik nyckel till frontend."""
        public_key = request.env['ir.config_parameter'].sudo().get_param(
            'unified_workspace_pwa_push.vapid_public_key'
        )
        if not public_key:
            # Generera nycklar om de saknas
            request.env['pwa.push.subscription'].sudo()._get_vapid_keys()
            public_key = request.env['ir.config_parameter'].sudo().get_param(
                'unified_workspace_pwa_push.vapid_public_key'
            )
        return {'public_key': public_key}

    @http.route('/pwa/push/subscribe', type='json', auth='public', methods=['POST'])
    def push_subscribe(self, endpoint=None, p256dh=None, auth=None, **kw):
        """Ta emot en push-prenumeration från webbläsaren."""
        if not endpoint or not p256dh or not auth:
            return {'status': 'error', 'message': 'Saknad prenumerationsdata.'}

        if request.env.user._is_public():
            return {'status': 'error', 'message': 'Push kraver inloggning.'}

        partner = request.env.user.partner_id
        user_id = request.env.user.id
        sub_id = request.env['pwa.push.subscription'].sudo().subscribe(
            partner_id=partner.id,
            endpoint=endpoint,
            p256dh=p256dh,
            auth=auth,
            user_id=user_id,
        )
        return {'status': 'ok', 'subscription_id': sub_id}

    @http.route('/pwa/push/unsubscribe', type='json', auth='public', methods=['POST'])
    def push_unsubscribe(self, endpoint=None, **kw):
        """Avregistrera en push-prenumeration."""
        if not endpoint:
            return {'status': 'error', 'message': 'Saknad endpoint.'}

        request.env['pwa.push.subscription'].sudo().unsubscribe(endpoint)
        return {'status': 'ok'}


class ArcPwaPushController(ArcPwaController):
    """Utöka PWA service workern med push-hantering."""

    @http.route('/pwa/sw.js', type='http', auth='public', website=False, sitemap=False)
    def service_worker(self, **kw):
        """Servera utökad service worker med push-stöd."""
        # Hämta grund-SW från arc_industrial_ui
        response = super(ArcPwaPushController, self).service_worker(**kw)
        base_sw = response.data.decode('utf-8')

        push_sw = """

// ---------------------------------------------------------------------------
// unified_workspace_pwa_push: Web Push-hantering
// ---------------------------------------------------------------------------

self.addEventListener('push', function (event) {
    console.log('[PWA PUSH] Push-mottaget:', event);
    if (!event.data) {
        console.warn('[PWA PUSH] Ingen data i push-event.');
        return;
    }
    let payload;
    try {
        payload = event.data.json();
        console.log('[PWA PUSH] Payload avkodad:', payload);
    } catch (e) {
        console.warn('[PWA PUSH] Kunde inte avkoda payload:', e);
        return;
    }

    const title = payload.title || 'PlastShop';
    const options = {
        body: payload.body || '',
        icon: payload.icon || '/arc_industrial_ui/static/pwa/icon-192.png',
        badge: payload.badge || '/arc_industrial_ui/static/pwa/icon-192.png',
        tag: payload.tag || null,
        requireInteraction: payload.requireInteraction || false,
        data: payload.data || {},
    };

    event.waitUntil(
        self.registration.showNotification(title, options).then(function () {
            console.log('[PWA PUSH] showNotification lyckades.');
            if (self.clients) {
                self.clients.matchAll({type: 'window', includeUncontrolled: true}).then(function (clientList) {
                    clientList.forEach(function (client) {
                        client.postMessage({type: 'push-shown', title: title, body: options.body, tag: options.tag});
                    });
                });
            }
        }).catch(function (err) {
            console.error('[PWA PUSH] showNotification misslyckades:', err);
        })
    );
});

self.addEventListener('notificationclick', function (event) {
    event.notification.close();
    const url = event.notification.data && event.notification.data.url
        ? event.notification.data.url
        : '/';

    event.waitUntil(
        clients.matchAll({ type: 'window', includeUncontrolled: true }).then(function (clientList) {
            for (let client of clientList) {
                if (client.url === url && 'focus' in client) {
                    return client.focus();
                }
            }
            if (clients.openWindow) {
                return clients.openWindow(url);
            }
        })
    );
});

// Test/diagnostik: tillat sidan att trigga en notis via postMessage
self.addEventListener('message', function (event) {
    if (event.data && event.data.type === 'test-push') {
        const title = event.data.title || 'Testnotis';
        const options = event.data.options || { body: 'Test fran service worker.' };
        self.registration.showNotification(title, options).then(function () {
            if (event.ports && event.ports[0]) {
                event.ports[0].postMessage({ok: true});
            }
        }).catch(function (err) {
            if (event.ports && event.ports[0]) {
                event.ports[0].postMessage({ok: false, error: err.message});
            }
        });
    }
});
"""
        extended_sw = base_sw + push_sw
        return request.make_response(
            extended_sw,
            headers=[
                ('Content-Type', 'application/javascript'),
                ('Cache-Control', 'no-cache, no-store, must-revalidate'),
                ('Service-Worker-Allowed', '/'),
            ],
        )
