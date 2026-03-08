import json
import logging
import re

import requests

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)
PHONE_CLEAN_RE = re.compile(r'\D+')


class WhatsappAccount(models.Model):
    _name = 'whatsapp.crm.account'
    _description = 'WhatsApp CRM Account'
    _order = 'sequence, id'

    name = fields.Char(required=True)
    active = fields.Boolean(default=True)
    sequence = fields.Integer(default=10)
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company, required=True)
    phone_number_id = fields.Char(string='Phone Number ID', required=True)
    business_account_id = fields.Char(string='Business Account ID')
    display_phone = fields.Char(string='Display Phone')
    access_token = fields.Char(string='Access Token', groups='base.group_system')
    verify_token = fields.Char(string='Verify Token', required=True, default=lambda self: self._default_verify_token())
    webhook_path = fields.Char(string='Webhook Path', compute='_compute_webhook_path')
    auto_create_lead = fields.Boolean(default=lambda self: self._default_auto_create_lead())
    auto_reply_enabled = fields.Boolean(default=True)
    auto_reply_template = fields.Text(default='Hello 👋 Thanks for contacting us. A sales agent will reply shortly.')
    auto_assign_salesperson = fields.Boolean(default=True)
    salesperson_id = fields.Many2one('res.users', string='Default Salesperson')
    team_id = fields.Many2one('crm.team', string='Sales Team')
    lead_prefix = fields.Char(default='WA')
    message_ids = fields.One2many('whatsapp.crm.message', 'account_id')
    message_count = fields.Integer(compute='_compute_message_count')
    inbound_message_count = fields.Integer(compute='_compute_message_count')
    outbound_message_count = fields.Integer(compute='_compute_message_count')
    graph_api_version = fields.Char(default='v23.0')
    last_webhook_at = fields.Datetime(readonly=True)

    @api.model
    def _default_verify_token(self):
        return self.env['ir.sequence'].next_by_code('whatsapp.crm.verify.token') or 'wa_verify_token'

    @api.model
    def _default_auto_create_lead(self):
        value = self.env['ir.config_parameter'].sudo().get_param('whatsapp_crm_pro.auto_create_lead', 'True')
        return str(value).lower() in ('true', '1', 'yes')

    def _compute_webhook_path(self):
        base_url = self.env['ir.config_parameter'].sudo().get_param('web.base.url', '')
        for rec in self:
            rec.webhook_path = '%s/whatsapp_crm/webhook/%s' % (base_url, rec.id or '') if rec.id else ''

    @api.depends('message_ids', 'message_ids.direction')
    def _compute_message_count(self):
        for rec in self:
            rec.message_count = len(rec.message_ids)
            rec.inbound_message_count = len(rec.message_ids.filtered(lambda m: m.direction == 'in'))
            rec.outbound_message_count = len(rec.message_ids.filtered(lambda m: m.direction == 'out'))

    def action_view_messages(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Messages'),
            'res_model': 'whatsapp.crm.message',
            'view_mode': 'list,form',
            'domain': [('account_id', '=', self.id)],
        }

    def _graph_api_url(self):
        self.ensure_one()
        return f'https://graph.facebook.com/{self.graph_api_version}/{self.phone_number_id}/messages'

    @api.model
    def _normalize_whatsapp_number(self, number):
        return PHONE_CLEAN_RE.sub('', number or '')

    def send_text_message(self, to_number, body, lead=None):
        self.ensure_one()
        if not self.access_token:
            raise UserError(_('Missing WhatsApp access token on account %s.') % self.display_name)
        if not body or not body.strip():
            raise UserError(_('Message body cannot be empty.'))

        to_number = self._normalize_whatsapp_number(to_number)
        if not to_number:
            raise UserError(_('Recipient phone number is missing or invalid.'))

        payload = {
            'messaging_product': 'whatsapp',
            'recipient_type': 'individual',
            'to': to_number,
            'type': 'text',
            'text': {'body': body.strip()},
        }
        headers = {
            'Authorization': f'Bearer {self.access_token}',
            'Content-Type': 'application/json',
        }
        try:
            response = requests.post(self._graph_api_url(), headers=headers, data=json.dumps(payload), timeout=30)
        except requests.RequestException as exc:
            _logger.exception('WhatsApp send request failed: %s', exc)
            raise UserError(_('WhatsApp request failed: %s') % exc) from exc

        if response.status_code >= 300:
            _logger.error('WhatsApp send failed: %s', response.text)
            raise UserError(_('WhatsApp send failed: %s') % response.text)

        data = response.json()
        self.env['whatsapp.crm.message'].create([{
            'name': body[:80],
            'account_id': self.id,
            'direction': 'out',
            'customer_phone': to_number,
            'customer_name': lead.contact_name if lead else False,
            'body': body,
            'lead_id': lead.id if lead else False,
            'state': 'sent',
            'message_type': 'text',
            'meta_message_id': (data.get('messages') or [{}])[0].get('id'),
            'raw_payload': json.dumps(data),
            'replied_by_id': self.env.user.id,
        }])
        self.env['whatsapp.crm.message']._mark_incoming_as_replied(lead=lead if lead else False, phone=to_number)
        return data
