from odoo import api, fields, models, _
from odoo.tools import html_escape


class CrmLead(models.Model):
    _inherit = 'crm.lead'

    whatsapp_phone = fields.Char(index=True, tracking=True)
    whatsapp_account_id = fields.Many2one('whatsapp.crm.account', tracking=True)
    whatsapp_message_ids = fields.One2many('whatsapp.crm.message', 'lead_id')
    whatsapp_message_count = fields.Integer(compute='_compute_whatsapp_message_count')
    whatsapp_last_message = fields.Text()
    whatsapp_summary = fields.Text()
    whatsapp_intent = fields.Char()
    whatsapp_lead_score = fields.Integer(default=0)
    whatsapp_source = fields.Char(default='WhatsApp')
    whatsapp_hot = fields.Boolean(compute='_compute_whatsapp_hot', store=True)
    whatsapp_recommended_reply = fields.Text(compute='_compute_whatsapp_assistant_fields')
    whatsapp_next_action = fields.Char(compute='_compute_whatsapp_assistant_fields')
    whatsapp_last_inbound_at = fields.Datetime(compute='_compute_whatsapp_assistant_fields')
    whatsapp_timeline_html = fields.Html(compute='_compute_whatsapp_timeline_html', sanitize=False)

    @api.depends('whatsapp_message_ids')
    def _compute_whatsapp_message_count(self):
        for rec in self:
            rec.whatsapp_message_count = len(rec.whatsapp_message_ids)

    @api.depends('priority', 'whatsapp_lead_score')
    def _compute_whatsapp_hot(self):
        for rec in self:
            rec.whatsapp_hot = rec.priority == '2' or rec.whatsapp_lead_score >= 70

    @api.depends('whatsapp_message_ids.body', 'whatsapp_message_ids.direction', 'whatsapp_intent', 'whatsapp_lead_score')
    def _compute_whatsapp_assistant_fields(self):
        for rec in self:
            inbound = rec.whatsapp_message_ids.filtered(lambda m: m.direction == 'in').sorted('message_date', reverse=True)
            rec.whatsapp_last_inbound_at = inbound[0].message_date if inbound else False
            intent = (rec.whatsapp_intent or '').lower()
            score = rec.whatsapp_lead_score or 0
            if 'purchase' in intent or score >= 80:
                rec.whatsapp_next_action = _('Call now and share a proposal')
                rec.whatsapp_recommended_reply = _('Thanks for reaching out. I can help you get started today. Would you like pricing, a short demo, or a direct call?')
            elif 'sales' in intent or 'pricing' in intent or score >= 60:
                rec.whatsapp_next_action = _('Send pricing and qualify the use case')
                rec.whatsapp_recommended_reply = _('Thanks for your interest. I can send pricing and answer any questions. Which product or service are you interested in?')
            elif 'support' in intent:
                rec.whatsapp_next_action = _('Triage the issue and request details')
                rec.whatsapp_recommended_reply = _('I can help with that. Please share a short description of the issue, any error message, and a screenshot if available.')
            elif inbound:
                rec.whatsapp_next_action = _('Reply within the current 24-hour window')
                rec.whatsapp_recommended_reply = _('Thanks for your message. How can I help you today?')
            else:
                rec.whatsapp_next_action = _('Start a conversation')
                rec.whatsapp_recommended_reply = _('Hello. Thanks for contacting us on WhatsApp. How can we help you today?')

    @api.depends('whatsapp_message_ids', 'whatsapp_message_ids.body', 'whatsapp_message_ids.direction', 'whatsapp_message_ids.message_date', 'whatsapp_message_ids.state', 'whatsapp_message_ids.message_status')
    def _compute_whatsapp_timeline_html(self):
        for rec in self:
            items = []
            messages = rec.whatsapp_message_ids.sorted('message_date')
            if not messages:
                rec.whatsapp_timeline_html = '<div class="text-muted">No WhatsApp conversation yet.</div>'
                continue
            for msg in messages:
                direction_label = _('Customer') if msg.direction == 'in' else _('Sales Team')
                meta = []
                if msg.message_date:
                    meta.append(fields.Datetime.to_string(msg.message_date))
                if msg.state:
                    meta.append(html_escape(dict(msg._fields['state'].selection).get(msg.state, msg.state)))
                if msg.message_status:
                    meta.append(html_escape(dict(msg._fields['message_status'].selection).get(msg.message_status, msg.message_status)))
                body = html_escape(msg.body or '') or '&nbsp;'
                css = 'background:#e8f5e9;border-left:4px solid #43a047;' if msg.direction == 'out' else 'background:#f5f5f5;border-left:4px solid #7e57c2;'
                items.append(
                    '<div style="margin:0 0 12px 0;padding:12px;border-radius:8px;%s">'
                    '<div style="font-weight:600;margin-bottom:4px;">%s</div>'
                    '<div style="font-size:12px;color:#666;margin-bottom:8px;">%s</div>'
                    '<div style="white-space:pre-wrap;">%s</div>'
                    '</div>' % (css, html_escape(direction_label), ' | '.join(meta), body)
                )
            rec.whatsapp_timeline_html = ''.join(items)

    @api.model
    def _whatsapp_global_auto_create_enabled(self):
        value = self.env['ir.config_parameter'].sudo().get_param('whatsapp_crm_pro.auto_create_lead', 'True')
        return str(value).lower() in ('true', '1', 'yes')

    @api.model
    def _whatsapp_find_or_create_lead(self, account, phone, customer_name, body, analysis):
        lead = self.search([
            ('whatsapp_phone', '=', phone),
            ('type', '=', 'lead'),
            ('active', '=', True),
        ], limit=1)
        vals = {
            'contact_name': customer_name,
            'whatsapp_phone': phone,
            'whatsapp_account_id': account.id,
            'description': (body or '')[:1000],
            'source_id': False,
        }
        if account.team_id:
            vals['team_id'] = account.team_id.id
        if account.auto_assign_salesperson:
            vals['user_id'] = account.salesperson_id.id or self._whatsapp_pick_salesperson(account).id
        if lead:
            lead.write(vals)
            return lead
        if not (self._whatsapp_global_auto_create_enabled() and account.auto_create_lead):
            return self.browse()
        vals.update({
            'name': '%s - %s' % (account.lead_prefix or 'WA', customer_name or phone),
            'type': 'lead',
        })
        return self.create(vals)

    @api.model
    def _whatsapp_pick_salesperson(self, account):
        team = account.team_id
        if team and team.member_ids:
            count_map = []
            for user in team.member_ids:
                count_map.append((self.search_count([('user_id', '=', user.id), ('type', '=', 'lead')]), user))
            count_map.sort(key=lambda x: x[0])
            return count_map[0][1]
        return self.env.user

    def _whatsapp_sync_from_message(self, msg, analysis):
        self.ensure_one()
        self.write({
            'whatsapp_last_message': msg.body,
            'whatsapp_summary': analysis.get('summary'),
            'whatsapp_intent': analysis.get('intent'),
            'whatsapp_lead_score': analysis.get('score', 0),
            'priority': '2' if analysis.get('priority') in ('2', '3') else '1',
        })

    def action_view_whatsapp_messages(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('WhatsApp Messages'),
            'res_model': 'whatsapp.crm.message',
            'view_mode': 'list,form',
            'domain': [('lead_id', '=', self.id)],
            'context': {'default_lead_id': self.id, 'default_customer_phone': self.whatsapp_phone},
        }

    def action_open_send_whatsapp_wizard(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Send WhatsApp Message'),
            'res_model': 'send.whatsapp.message.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_lead_id': self.id,
                'default_account_id': self.whatsapp_account_id.id,
                'default_to_number': self.whatsapp_phone,
                'default_body': self.whatsapp_recommended_reply or '',
            },
        }
