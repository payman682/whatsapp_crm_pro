import json
import logging
import re
from datetime import timedelta

from odoo import api, fields, models, _
from odoo.tools import html_escape

_logger = logging.getLogger(__name__)
PHONE_CLEAN_RE = re.compile(r'\D+')


class WhatsappMessage(models.Model):
    _name = 'whatsapp.crm.message'
    _description = 'WhatsApp CRM Message'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'message_date desc, id desc'

    name = fields.Char(required=True, tracking=True, default='New WhatsApp Message')
    active = fields.Boolean(default=True)
    account_id = fields.Many2one('whatsapp.crm.account', required=True, ondelete='cascade')
    lead_id = fields.Many2one('crm.lead', tracking=True)
    customer_phone = fields.Char(required=True, index=True, tracking=True)
    customer_name = fields.Char(tracking=True)
    direction = fields.Selection([('in', 'Incoming'), ('out', 'Outgoing')], required=True, default='in', tracking=True)
    message_type = fields.Selection([('text', 'Text'), ('interactive', 'Interactive'), ('button', 'Button'), ('system', 'System')], default='text', required=True, tracking=True)
    body = fields.Text(tracking=True)
    summary = fields.Text()
    intent = fields.Char()
    priority = fields.Selection([('0', 'Low'), ('1', 'Normal'), ('2', 'High'), ('3', 'Urgent')], default='1')
    state = fields.Selection([('received', 'Received'), ('sent', 'Sent'), ('delivered', 'Delivered'), ('read', 'Read'), ('failed', 'Failed')], default='received', tracking=True)
    message_status = fields.Selection([('read', 'Read'), ('replied', 'Replied')], default='read', tracking=True)
    meta_message_id = fields.Char(index=True)
    raw_payload = fields.Text()
    replied_by_id = fields.Many2one('res.users', string='Replied By')
    message_date = fields.Datetime(default=fields.Datetime.now, required=True)
    needs_followup = fields.Boolean(default=False)
    followup_date = fields.Datetime()

    _sql_constraints = [
        ('meta_message_id_unique', 'unique(meta_message_id)', 'Meta message id must be unique.'),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('name'):
                phone = vals.get('customer_phone') or 'Unknown'
                direction = vals.get('direction') or 'in'
                label = 'Incoming' if direction == 'in' else 'Outgoing'
                body = (vals.get('body') or '').strip()
                vals['name'] = body[:80] if body else '%s WhatsApp Message - %s' % (label, phone)
        return super().create(vals_list)

    @api.model
    def _clean_phone(self, phone):
        return PHONE_CLEAN_RE.sub('', phone or '')

    @api.model
    def _extract_message_body(self, item):
        msg_type = item.get('type') or 'text'
        if msg_type == 'text':
            return ((item.get('text') or {}).get('body') or '').strip(), 'text'
        if msg_type == 'button':
            button = item.get('button') or {}
            return (button.get('text') or button.get('payload') or '').strip(), 'button'
        if msg_type == 'interactive':
            interactive = item.get('interactive') or {}
            button_reply = interactive.get('button_reply') or {}
            list_reply = interactive.get('list_reply') or {}
            return (button_reply.get('title') or list_reply.get('title') or list_reply.get('description') or '').strip(), 'interactive'
        return '', 'system'

    @api.model
    def ai_analyze_message(self, body):
        text = (body or '').lower()
        priority = '1'
        intent = 'general inquiry'
        score = 30
        tags = []

        if any(k in text for k in ['price', 'pricing', 'quote', 'cost', 'demo']):
            intent = 'sales inquiry'
            priority = '2'
            score += 30
            tags.append('pricing')
        if any(k in text for k in ['buy', 'order', 'subscribe', 'start today']):
            intent = 'purchase intent'
            priority = '3'
            score += 40
            tags.append('ready_to_buy')
        if any(k in text for k in ['problem', 'issue', 'not working', 'error', 'help']):
            intent = 'support request'
            priority = '2'
            tags.append('support')
        if len(text.split()) > 25:
            score += 10

        return {
            'summary': 'Customer said: %s' % ((body or '').strip()[:240]),
            'intent': intent,
            'priority': priority,
            'score': min(score, 100),
            'tags': tags,
        }

    @api.model
    def _mark_incoming_as_replied(self, lead=False, phone=False):
        domain = [('direction', '=', 'in'), ('message_status', '=', 'read')]
        if lead:
            domain.append(('lead_id', '=', lead.id))
        elif phone:
            domain.append(('customer_phone', '=', phone))
        incoming = self.search(domain)
        if incoming:
            incoming.write({'message_status': 'replied'})

    @api.model
    def _update_delivery_statuses(self, account, value):
        for status in value.get('statuses', []) or []:
            if not isinstance(status, dict):
                continue
            meta_message_id = status.get('id')
            if not meta_message_id:
                continue
            mapped = {'sent': 'sent', 'delivered': 'delivered', 'read': 'read', 'failed': 'failed'}.get(status.get('status'))
            if not mapped:
                continue
            msg = self.search([('account_id', '=', account.id), ('meta_message_id', '=', meta_message_id)], limit=1)
            if msg:
                vals = {'state': mapped, 'raw_payload': json.dumps(status)}
                if mapped == 'read' and msg.direction == 'in':
                    vals['message_status'] = 'read'
                msg.write(vals)

    @api.model
    def process_incoming_webhook(self, account, payload):
        created = self.browse()
        account.sudo().write({'last_webhook_at': fields.Datetime.now()})
        for entry in payload.get('entry', []):
            if not isinstance(entry, dict):
                continue
            for change in entry.get('changes', []):
                if not isinstance(change, dict):
                    continue
                value = change.get('value', {}) or {}
                if not isinstance(value, dict):
                    continue
                self._update_delivery_statuses(account, value)
                contacts = value.get('contacts', []) or []
                contact_map = {c.get('wa_id'): c for c in contacts if isinstance(c, dict)}
                for item in value.get('messages', []) or []:
                    if not isinstance(item, dict):
                        continue
                    phone = self._clean_phone(item.get('from'))
                    if not phone:
                        continue
                    meta_message_id = item.get('id')
                    if meta_message_id and self.search_count([('meta_message_id', '=', meta_message_id)]):
                        continue
                    body, message_type = self._extract_message_body(item)
                    if not body and message_type == 'system':
                        continue
                    contact = contact_map.get(item.get('from'), {})
                    profile = contact.get('profile') if isinstance(contact, dict) else {}
                    customer_name = (profile or {}).get('name')
                    analysis = self.ai_analyze_message(body)
                    lead = self.env['crm.lead']._whatsapp_find_or_create_lead(account, phone, customer_name, body, analysis)
                    msg = self.create([{
                        'name': body[:80] or 'Incoming WhatsApp Message - %s' % phone,
                        'account_id': account.id,
                        'lead_id': lead.id if lead else False,
                        'customer_phone': phone,
                        'customer_name': customer_name,
                        'direction': 'in',
                        'message_type': message_type,
                        'body': body,
                        'summary': analysis['summary'],
                        'intent': analysis['intent'],
                        'priority': analysis['priority'],
                        'message_status': 'read',
                        'meta_message_id': meta_message_id,
                        'raw_payload': json.dumps(item),
                        'needs_followup': analysis['priority'] in ('2', '3'),
                        'followup_date': (fields.Datetime.now() + timedelta(hours=24)) if analysis['priority'] in ('2', '3') else False,
                    }])[0]
                    if lead:
                        lead._whatsapp_sync_from_message(msg, analysis)
                        lead.message_post(body=html_escape('WhatsApp incoming message from %s:<br/>%s' % ((msg.customer_name or msg.customer_phone), msg.body)))
                    created |= msg
                    if account.auto_reply_enabled and account.auto_reply_template:
                        try:
                            account.send_text_message(phone, account.auto_reply_template, lead=lead if lead else False)
                        except Exception as exc:
                            _logger.exception('Auto-reply failed: %s', exc)
        return created

    def action_open_lead(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'res_model': 'crm.lead', 'res_id': self.lead_id.id, 'view_mode': 'form'}

    def action_reply_whatsapp(self):
        self.ensure_one()
        if not self.lead_id:
            return False
        return {
            'type': 'ir.actions.act_window',
            'name': _('Send WhatsApp Message'),
            'res_model': 'send.whatsapp.message.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_lead_id': self.lead_id.id,
                'default_account_id': self.account_id.id,
                'default_to_number': self.customer_phone,
                'default_body': '',
            },
        }

    @api.model
    def cron_send_followups(self):
        due_messages = self.search([('needs_followup', '=', True), ('followup_date', '<=', fields.Datetime.now()), ('direction', '=', 'in'), ('lead_id', '!=', False)], limit=50)
        template = self.env['ir.config_parameter'].sudo().get_param('whatsapp_crm_pro.followup_template', 'Hello, just following up on your WhatsApp inquiry. Do you want pricing, a demo, or help from sales?')
        for msg in due_messages:
            try:
                msg.account_id.send_text_message(msg.customer_phone, template, lead=msg.lead_id)
                msg.needs_followup = False
            except Exception as exc:
                _logger.exception('Follow-up failed for %s: %s', msg.id, exc)
