# WhatsApp CRM Pro

Stable marketplace-ready Odoo 19 module.

## Highlights
- WhatsApp Cloud API webhook verification and inbound processing
- Global auto lead creation toggle in Settings → WhatsApp CRM
- Per-account automation and multi-number support
- Conversation timeline embedded inside CRM leads
- Unified incoming and outgoing message log
- Read / replied message analytics field
- Reply popup from both lead and message records
- AI-style intent detection, summary, and lead scoring
- Follow-up automation with delivery/read status sync

## Setup
1. Install the module.
2. Go to **Settings → WhatsApp CRM** and choose whether leads should be auto-created.
3. Create a WhatsApp account in **WhatsApp CRM → Accounts**.
4. Copy the webhook path into Meta.
5. Save the same verify token in Meta.
6. Subscribe the `messages` and `message_status` webhook fields.
7. Test with an allowed phone number in Meta test mode.

## Notes
- In Meta test mode, outbound messages work only for allowed recipient numbers.
- For production, connect a live WhatsApp Business number.
