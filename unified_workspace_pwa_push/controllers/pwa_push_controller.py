# =============================================================================
# PWA Push HTTP-kontroller
# =============================================================================

import logging

from odoo import http
from odoo.http import request

from odoo.addons.arc_industrial_ui.controllers.pwa import ArcPwaController

_logger = logging.getLogger(__name__)


class PwaPushController(http.Controller):

    @http.route('/pwa/vapid_public_key', type='json', auth='user', methods=['POST'])
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

    @http.route('/pwa/push/subscribe', type='json', auth='user', methods=['POST'])
    def push_subscribe(self, **kw):
        """Ta emot en push-prenumeration från webbläsaren."""
        data = request.jsonrequest or {}
        endpoint = data.get('endpoint')
        p256dh = data.get('p256dh')
        auth = data.get('auth')

        if not endpoint or not p256dh or not auth:
            return {'status': 'error', 'message': 'Saknad prenumerationsdata.'}

        partner = request.env.user.partner_id
        sub_id = request.env['pwa.push.subscription'].sudo().subscribe(
            partner_id=partner.id,
            endpoint=endpoint,
            p256dh=p256dh,
            auth=auth,
            user_id=request.env.user.id,
        )
        return {'status': 'ok', 'subscription_id': sub_id}

    @http.route('/pwa/push/unsubscribe', type='json', auth='user', methods=['POST'])
    def push_unsubscribe(self, **kw):
        """Avregistrera en push-prenumeration."""
        data = request.jsonrequest or {}
        endpoint = data.get('endpoint')
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
    if (!event.data) return;
    let payload;
    try {
        payload = event.data.json();
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
        self.registration.showNotification(title, options)
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
