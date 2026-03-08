from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    whatsapp_crm_auto_create_lead = fields.Boolean(
        string="Auto-create lead from WhatsApp message",
        config_parameter="whatsapp_crm_pro.auto_create_lead",
        default=True,
    )
    whatsapp_crm_followup_template = fields.Char(
        string="Default Follow-up Template",
        config_parameter="whatsapp_crm_pro.followup_template",
    )
