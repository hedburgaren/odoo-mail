# unified_workspace

## Purpose

Extend Odoo 18 Discuss into a unified communication hub that brings personal
email, calendar invitations, chat and tasks into one view. The module reuses
existing Odoo infrastructure (`fetchmail`, `mail.thread`, `calendar.event`,
`web_editor`, `hr_timesheet`) and never duplicates it.

## Models

### `mail.personal.folder`

Personal folders per user. System folders (`inbox`, `sent`, `drafts`, `trash`)
are created automatically and cannot be deleted.

### `mail.personal.mailbox`

Personal email messages. Key fields and behaviours:

- `user_id`, `folder_id`, `name`, `body`, `email_from`, `email_to`, `email_cc`,
  `email_bcc`, `message_id`, `parent_id`, `state`, `is_starred`.
- `partner_id` computed from `email_from`.
- `crm_lead_id`, `project_task_id`, `calendar_event_id` link to CRM, Project
  and Calendar records created from the email. ARC-specific linking is handled
  by the private `odoo_mail_arc_bridge` module.
- `calendar_event_uid` stores the .ics UID to detect duplicate invitations.
- `calendar_rsvp_state` tracks the owner's RSVP (`needsAction`, `tentative`,
  `accepted`, `declined`).

Calendar methods:

- `_find_ics_attachments()` / `_parse_ics_attachment()` parse `vobject` data.
- `action_parse_calendar_invitation()` creates or updates `calendar.event`
  from the first `.ics` attachment.
- `action_accept_event()` / `action_tentative_event()` /
  `action_decline_event()` update the mailbox owner's attendee state and
  return `True` so the OWL frontend can refresh the reading pane badge.

Thread, draft, activity and timer methods:

- `action_get_thread()` returns the root message and all descendants in
  chronological order for the reading pane thread panel.
- `save_draft()` creates or updates a `mail.personal.mailbox` record in the
  user's Drafts folder from composer data.
- `action_get_reply_body()` returns the standard quoted reply body for a
  message.
- `action_log_activity()` opens the standard `mail.activity.schedule` wizard
  prefilled with the email subject and body.
- `action_save_attachments_to_record()` copies the email attachments to the
  linked `crm.lead`, `project.task` or `res.partner` record.
- `action_timer_start()` / `action_timer_stop()` start and stop a timer on the
  email thread; elapsed time is accumulated in `timer_duration` (hours).
- `action_log_time_to_task()` creates an `account.analytic.line` on the linked
  `project.task` and resets the accumulated duration.
- `action_create_lead()` creates a `crm.lead` from the email and links it via
  `crm_lead_id`.
- `action_log_to_lead()` opens a prefilled `crm.lead` form to log the email
  against an existing or new lead.

### `mail.personal.template`

Reusable email templates per user or shared (`user_id` empty). The default
flag (`is_default`) is unique per user/shared scope. `action_use_template()`
returns subject and body for the composer.

### `res.users`

Adds personal email signatures, internal/external signature selector and
links to personal IMAP/SMTP servers.

### `fetchmail.server` / `mail.thread`

Incoming email whose `To`/`CC` matches an active internal user's email is
routed to `mail.personal.mailbox` instead of alias routing. Body and
attachments are extracted, threads are linked via `In-Reply-To`/`References`,
and `.ics` attachments are parsed automatically.

### `mail.compose.message`

Adds `composition_mode = "personal_email"` and saves a copy of sent messages
in the user's Sent folder with signatures applied.

The composer calls the public `action_send_mail` method and passes To/CC/BCC
partners and attachments so the Sent copy preserves the full recipient list
and attachments.

## Security

- `mail.personal.folder`: users see only their own folders.
- `mail.personal.mailbox`: users see only their own messages.
- `mail.personal.template`: users see their own templates plus shared ones.
- `fetchmail.server`: configured by admins; users link their personal server
  via `res.users`.

## Frontend

All components are OWL and registered under `web.assets_backend`.

### Components

- `workspace`: three-column layout (sidebar, email list, reading pane) and
  keyboard shortcuts.
- `sidebar`: folder navigation, system folders and links to Discuss/Calendar.
- `email_list`: message list with unread/starred indicators.
- `reading_pane`: message body, attachments, CRM actions, contact card,
  calendar RSVP buttons, conversation thread panel and time-logging controls
  when the email is linked to a `project.task`.
- `composer`: tokenized To/CC/BCC (`EmailTags`), HTML editor (`Wysiwyg`),
  drag-and-drop attachments (`AttachmentUploader`), signature selector,
  template selector and draft save/open. Reply/forward prefills recipients
  and quoted body and links the sent copy to the parent message.
- `email_tags`: token input for email addresses.
- `attachment_uploader` / `attachment_list`: drag-and-drop upload, preview,
  download and save-to-record of `ir.attachment` records.
- `thread_panel`: conversation thread list inside the reading pane.
- `calendar_panel`: embedded calendar view for today's agenda and event
  creation.
- `calendar_view`: placeholder view for future agenda widgets.
- `contact_card`: sender partner card with recent pipeline and open tasks.

### Services

- `mailbox`: reactive state, folder/message loading, search, filters and RPC
  wrappers for actions including calendar RSVP. It supports an "All folders"
  view and quick filters for unread, starred and with-attachments. It extends
  Odoo's `Reactive` class and is consumed by components via
  `useState(useService("mailbox"))` so the UI updates when messages or folders
  change. After an RSVP action the service patches the local message state
  before reloading.

### Keyboard shortcuts

Shortcuts fire when focus is not inside an editable field and no dialog is
open:

- `E` compose new email.
- `R` reply to selected email.
- `F` forward selected email.
- `#` move selected email to trash.
- `S` toggle star on selected email.
- `Ctrl+Enter` / `Cmd+Enter` send from composer.

## Tests

Python tests in `tests/`:

- `test_fetchmail_routing`: personal routing and fallback behaviour.
- `test_mail_personal_mailbox`: folders, message linking, CRM lead creation,
  calendar invitation parsing, RSVP actions, templates, thread navigation,
  activity scheduling, saving attachments to a linked record, draft save/update,
  reply body quoting, parent linking on sent replies, timer start/stop and
  logging time to a linked project task.

Run with:

```bash
python odoo-bin -c odoo.conf -u unified_workspace --stop-after-init --no-http --test-tags unified_workspace
```

## i18n

All user-facing strings are translatable. Regenerate the `.pot` template with:

```bash
python odoo-bin -c odoo.conf -d unified_workspace --modules=unified_workspace \
  --language=en_US --i18n-export=/path/to/unified_workspace.pot --stop-after-init --no-http
```
