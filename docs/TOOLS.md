# Agent tools and API

| Tool | Inputs | Result |
|---|---|
| `retrieve_project_knowledge` | question, optional project ID | Ranked source excerpts with page and score |
| `get_township_overview` | none | Acreage, Phase 1, concept, infrastructure |
| `get_project_details` | `A` or `B` | Structured documented features |
| `get_connectivity_information` | optional destination | Assignment distances and proposed corridor note |
| `convert_plot_area` | positive value, from/to unit | Square yard/foot/metre conversion |
| `compare_projects` | none | Supported differences and missing-field note |
| `calculate_property_values` | customer-provided area and rate | Illustrative INR multiplication only |
| `capture_customer_lead` | name, contact, optional interest | Persisted inquiry, with explicit consent |
| `create_site_visit_request` | contact, preferred date/time | Pending-confirmation request |
| `request_human_callback` | contact, optional note | Pending callback request |

Public HTTP routes: `GET /api/health`, `GET /api/projects`, `GET /api/knowledge/search`, `POST /api/chat`, `GET /api/conversations/{id}`, `POST /api/leads`, `POST /api/visits`, `POST /api/callbacks`, and `WS /ws/live`. Contact write bodies require `consent: true` and a mobile number or email. Text chat only permits model-initiated contact writes when `consent_to_store: true` is supplied for that turn.

Admin routes require `X-Admin-Token`: `GET /api/admin/leads`, `GET /api/admin/requests`, `POST /api/admin/ingest` (multipart `file`), and `POST /api/admin/reindex`. Do not expose the admin token to the public browser UI.

Example local search:

```powershell
Invoke-RestMethod 'http://127.0.0.1:8000/api/knowledge/search?q=villa%20plot%20size'
```

