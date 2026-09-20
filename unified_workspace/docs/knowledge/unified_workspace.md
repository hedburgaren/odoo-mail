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
  A `VEVENT` without `DTSTART` is skipped with a warning, and a missing,
  equal or inverted `DTEND` falls back to one hour, so a malformed invite can
  never raise and swallow the email it arrived with.
- `action_parse_calendar_invitation()` creates or updates `calendar.event`
  from the first `.ics` attachment. Rules that matter:
  - Every write goes through `_calendar_sync_context()`
    (`no_mail_to_attendees`, `dont_notify`). Without it Odoo mails
    "Invitation to ..." to every attendee of a future event, from the mailbox
    owner, so the organiser gets an invitation to their own meeting and the
    other guests get a duplicate.
  - Only existing contacts become attendees. An incoming email is no reason to
    create `res.partner` records: spam with a calendar attachment would fill
    the contact register, and a user without Contact Creation would lose the
    event to an `AccessError`. Unknown addresses are appended to the event
    description instead. The mailbox owner is always an attendee.
  - `partner_id` on `calendar.event` is related to `user_id` and cannot be
    written. An external organiser cannot own an Odoo event, so `user_id` is
    only set when the organiser is an internal user.
  - Parsing is triggered once, from the `write()` hook when `attachment_ids`
    is set, inside a savepoint (`_try_parse_calendar_invitation()`). Calling
    the action again on a message that already has an event updates that
    event rather than creating a second one.
- `action_accept_event()` / `action_tentative_event()` /
  `action_decline_event()` update the mailbox owner's attendee state and
  return `True` so the OWL frontend can refresh the reading pane badge.

Thread, draft, activity and timer methods:

- `action_get_thread()` returns the root message and all descendants in
  chronological order for the reading pane thread panel.
- `save_draft()` creates or updates a `mail.personal.mailbox` record in the
  user's Inbox with `state = "draft"` from composer data. There is no separate
  Drafts folder; drafts are found through the Drafts quick filter and reopened
  via the composer's `draftId` prop.
- `action_get_reply_body()` returns the standard quoted reply body for a
  message. `action_get_forward_body()` returns the forward variant with a
  "Forwarded message" header and the original body quoted.
- `action_reply_all()` resolves every address in `From`/`To`/`CC` to partners
  so a reply-all reaches the original recipients, not only the sender.
- `action_move_to_stage(stage_id)` creates a `crm.lead` from the email when
  none is linked, then moves it to the given `crm.stage`. Used by the
  draggable CRM pipeline overlay.
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
flag (`is_default`) is unique per user/shared scope.

Subject and body may contain placeholders written as `{{ namespace.field }}`.
They are resolved by `_render_placeholders()` against a fixed whitelist
(`PLACEHOLDER_FIELDS`): `partner.*` (recipient name, company, email, phone,
city), `user.*` (your name, email, phone, company) and `date`. The aliases in
`PLACEHOLDER_ALIASES` (`recipient.*`, `company.name`) resolve to the same
values. Anything outside the whitelist is left untouched, so a half-finished
template stays visible instead of losing text, and substituted values are
HTML-escaped in the body so a partner name cannot break the markup.
`get_placeholder_fields()` exposes the names and labels to the UI, and the
template form shows them as help text.

`action_use_template(partner_id=None)` renders the placeholders against the
given recipient and returns the subject and body for the composer. Without a
partner the `partner.*` placeholders are left in the text, exactly like an
unknown placeholder: the composer applies the default template when it opens,
before any recipient exists, and rendering them to empty strings there would
delete them before there was anything to fill in. `render_for_partner()` fills
in what is left when the recipient is entered afterwards, and it only touches
the placeholders, never text the user wrote.

Sending is the last pass: `mail.compose.message._render_personal_placeholders()`
renders subject and body once more against the first To recipient, with
`final=True` so an unresolved `partner.*` becomes an empty string. No
`{{ ... }}` from the whitelist can reach the customer, whatever the browser
managed to render, and scheduled sends go through the same composer.

### `res.users`

Adds personal email signatures, internal/external signature selector and
links to personal IMAP/SMTP servers.

### `fetchmail.server` / `mail.thread`

Incoming email whose `To`/`CC` matches an active internal user's email is
routed to `mail.personal.mailbox` instead of alias routing. Body and
attachments are extracted, threads are linked via `In-Reply-To`/`References`,
and `.ics` attachments are parsed automatically.

### `mail.compose.message`

Adds `composition_mode = "personal_email"` and sends personal mail through
`mail.mail` with To/CC/BCC, attachments and the sender's signature applied at
send time, server-side, above the quoted part.

`_save_sent_copy()` is post-send bookkeeping only. It does NOT create a copy in
the Odoo inbox: outgoing personal mail is kept by Gmail's own Sent folder, and
mixing incoming and outgoing in one view was confusing (Chrille 2026-09-07).
What remains is the state transition on the original message
(`replied`/`forwarded`) and the optional log-to-record on a linked
`crm.lead`/`project.task`/`res.partner`. The composer calls the public
`action_send_mail` method and passes To/CC/BCC partners and attachments.

BCC is delivered as one separate `mail.mail` per hidden recipient. Odoo 18 CE
has no `email_bcc` on `mail.mail`, and `email_cc` really is delivered to, so a
single mail would either drop BCC silently or expose the hidden recipients to
each other. The BCC copy carries neither To nor CC addresses.

`signature_type` is `auto` by default, which picks the internal or external
signature from the recipients; `internal` and `external` force the choice.

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
  template selector and draft save/open. Applying a template calls
  `action_use_template` server-side so placeholders resolve against the first
  recipient. Reply/forward prefills recipients and quoted body and links the
  composer to the original message via `personal_mailbox_id`, which is marked
  `replied`/`forwarded` at send time.
- `email_tags`: token input for email addresses.
- `attachment_uploader` / `attachment_list`: drag-and-drop upload, preview,
  download and save-to-record of `ir.attachment` records.
- `thread_panel`: conversation thread list inside the reading pane.
- `calendar_panel`: embedded calendar view for today's agenda and event
  creation.
- `calendar_view`: today's agenda widget, opened as the `agenda` panel from
  the sidebar.
- `pipeline_overlay`: draggable CRM pipeline overlay, rendered as the
  `pipeline` panel next to the email list so messages stay draggable. Each
  column is a `crm.stage`; dropping an email on a column calls
  `action_move_to_stage()`.
- `contact_card`: sender partner card with recent pipeline and open tasks.

### Services

- `mailbox`: reactive state, folder/message loading, search, filters and RPC
  wrappers for actions including calendar RSVP. It supports an "All folders"
  view and quick filters for unread, starred, with-attachments, important and
  drafts. It extends Odoo's `Reactive` class and is consumed by components via
  `useState(useService("mailbox"))` so the UI updates when messages or folders
  change. After an RSVP action the service patches the local message state
  before reloading. It also exposes `openAgenda()` for the daily agenda panel,
  `openPipelineOverlay()` and `moveToStage()` for the CRM pipeline overlay.

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
  reply body quoting, timer start/stop and logging time to a linked project
  task.
- `test_mail_personal_mail_merge`: token rendering and the send loop of the
  mail merge wizard.

Composer, attachment and calendar coverage is explicit:

- Composer: a send without recipients raises `UserError`; `_ensure_signature()`
  inserts the signature once, above the `uw_quote` marker, and appends it when
  no quote exists; `_save_sent_copy()` performs bookkeeping only and never
  creates an inbox copy (see the 2026-09-07 decision above); replies and
  forwards mark the original `replied`/`forwarded`.
- Attachments: saving to a linked lead, a linked project task and the sender
  partner; the record-required guard; DMS and Knowledge storage.
- Calendar: parsing and RSVP, a missing attachment or a non-calendar
  attachment returns `False`, malformed `.ics` data is swallowed with a
  warning, a `VEVENT` without `DTSTART` is skipped, a late or missing `DTEND`
  falls back to one hour, the same `UID` updates the existing event instead of
  creating a second one, and the write hook parses only once per message.

The suite is green as of 2026-09-20: 64 tests, 0 failed, 0 errors.

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
