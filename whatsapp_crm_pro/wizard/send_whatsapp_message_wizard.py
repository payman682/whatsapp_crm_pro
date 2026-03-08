from odoo import fields, models, _
from odoo.exceptions import UserError


class SendWhatsappMessageWizard(models.TransientModel):
    _name = 'send.whatsapp.message.wizard'
    _description = 'Send WhatsApp Message Wizard'

    lead_id = fields.Many2one('crm.lead', required=True)
    account_id = fields.Many2one('whatsapp.crm.account', required=True)
    to_number = fields.Char(required=True)
    body = fields.Text(required=True)

    def action_use_suggested_reply(self):
        self.ensure_one()
        if self.lead_id and self.lead_id.whatsapp_recommended_reply:
            self.body = self.lead_id.whatsapp_recommended_reply
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'send.whatsapp.message.wizard',
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_send(self):
        self.ensure_one()
        if not self.account_id:
            raise UserError(_('Please choose a WhatsApp account.'))
        if not self.body or not self.body.strip():
            raise UserError(_('Please enter a message before sending.'))
        self.account_id.send_text_message(self.to_number, self.body, lead=self.lead_id)
        self.lead_id.message_post(body=_('WhatsApp reply sent:<br/>%s') % self.body)
        return {'type': 'ir.actions.act_window_close'}
