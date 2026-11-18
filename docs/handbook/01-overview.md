# 1. What this app is

## Plain-language summary

This is a **sales CRM with a built-in power dialer** for outbound phone prospecting. A user (or team member) maintains a list of **prospects** (leads), filters them, moves them through a **pipeline**, and calls them through **Twilio**—either manually from the browser (human agent) or via **AI voice agents** that can dial and converse using Cartesia TTS and an LLM.

Think of it as three cooperating desks in one browser tab:

1. **CRM desk** — table of leads, CSV import/export, pipeline board, workflow canvas (preview).
2. **Dialer desk** — start/pause session, multi-line dialing, live transcript, disposition buttons, session goals.
3. **Analytics desk** — performance charts, daily goals, funnel metrics derived from call logs.

## Who uses it and for what

| User | Typical goals |
|------|----------------|
| Outbound sales rep | Work a callable pool by timezone, log outcomes, book meetings |
| Operator / admin | Import CSVs, configure Twilio and scripts, tune pipeline steps |
| Builder / integrator | Run locally with JSON files or connect Supabase + Google sign-in for multi-user cloud storage |

The product language assumes **B2B prospecting** (business name, reviews, industry filter) but the data model is generic JSON on each lead.

## What it is not

- Not a multi-tenant SaaS product out of the box; one Python process per deployment, sessions keyed by Supabase user when cloud storage is enabled.
- Not a React/Vue SPA; it is **static HTML partials** assembled server-side plus **native ES modules**.
- Not realtime-push-first for CRM; the UI **polls** `GET /api/live` about every 1.5 seconds (see `static/features/_dialer/poller.js`).

## Major surfaces (browser tabs)

| Tab | DOM root | Primary scripts |
|-----|-----------|-----------------|
| Dialer (human) | `#dialerTabPanel` | `static/features/dialer.js`, `static/features/_dialer/*` |
| AI Dialer Agent | `#aiDialerAgentTabPanel` | `static/features/ai-dialer-agent.js`, `static/features/_ai_dialer/*` |
| Prospects / Pool | `#prospectsTabPanel`, `#poolTabPanel` | `static/features/prospects.js` |
| Performance | `#performanceTabPanel` | `static/features/performance.js` |
| Pipeline | pipeline panel in prospects HTML | `static/features/pipeline.js` |
| Workflow | `#workflowTabPanel` | `static/features/workflow.js` |
| Settings | settings partial | `static/features/settings.js` |

Navigation is **tab switching** in `static/_core/navigation.js` (`setDashboardTab`), not URL routing.