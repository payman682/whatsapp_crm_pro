import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class WhatsappWebhookController(http.Controller):

    @http.route('/whatsapp_crm/webhook/<int:account_id>', auth='public', methods=['GET'], csrf=False)
    def whatsapp_verify(self, account_id, **kwargs):
        account = request.env['whatsapp.crm.account'].sudo().browse(account_id)
        mode = kwargs.get('hub.mode')
        token = kwargs.get('hub.verify_token')
        challenge = kwargs.get('hub.challenge')
        if account.exists() and mode == 'subscribe' and token == account.verify_token:
            return request.make_response(challenge or '')
        return request.make_response('Verification failed', status=403)

    @http.route('/whatsapp_crm/webhook/<int:account_id>', auth='public', methods=['POST'], type='http', csrf=False)
    def whatsapp_receive(self, account_id, **kwargs):
        account = request.env['whatsapp.crm.account'].sudo().browse(account_id)
        if not account.exists():
            return request.make_json_response({'status': 'error', 'message': 'Account not found'}, status=404)
        try:
            payload = request.get_json_data()
            request.env['whatsapp.crm.message'].sudo().process_incoming_webhook(account, payload or {})
            return request.make_json_response({'status': 'ok'})
        except Exception as exc:
            _logger.exception('Webhook processing failed: %s', exc)
            return request.make_json_response({'status': 'error', 'message': str(exc)}, status=500)
