# -*- coding: utf-8 -*-
{
    'name': 'WhatsApp CRM Pro – Meta WhatsApp Integration',
    'summary': 'WhatsApp CRM integration for Odoo. Convert WhatsApp Business messages into CRM leads and reply directly from Odoo CRM.',
    "description": """
WhatsApp CRM Pro
================

Connect WhatsApp Cloud API with Odoo CRM.

Main Features
-------------
- Receive WhatsApp messages from Meta Cloud API
- Create CRM leads automatically with global auto-create toggle
- Reply to customers from Odoo
- Show WhatsApp conversation timeline inside CRM leads
- Track message history, read/replied analytics, and account activity
- Dashboard and account management
- Scheduled follow-up cron

Setup
-----
1. Install the module
2. Configure WhatsApp account in Odoo
3. Add webhook URL in Meta
4. Start receiving and replying to messages
""",
    "version": "19.0.3.0.1",
    "author": "Forklift Plus inc.",
    "website": "https://forkliftplus.com",
    "license": "LGPL-3",
    "category": "Sales/CRM",
    "price": 89,
    "currency": "USD",
    "depends": [
        "base",
        "crm",
        "mail",
    ],
    "data": [
        "security/ir.model.access.csv",

        "data/ir_sequence.xml",
        "data/ir_cron.xml",

        "views/menu_views.xml",
        "views/dashboard_views.xml",
        "views/whatsapp_account_views.xml",
        "views/whatsapp_message_views.xml",
        "views/crm_lead_views.xml",
        "views/res_config_settings_views.xml",

        "wizard/send_whatsapp_message_wizard_views.xml",
    ],
    "demo": [
        "demo/whatsapp_crm_demo.xml",
    ],
    "images": [
        "static/description/banner.png",
    ],
    "installable": True,
    "application": True,
    "auto_install": False,
}
