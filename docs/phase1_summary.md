# Phase 1 Summary: Portal MVP

**Status**: ✅ Completed
**Duration**: 4/21/2026 - 4/28/2026

---

## What Was Built

A Next.js-based internal analytics portal with:
- JWT-based authentication
- Dashboard list page with category filtering
- Two end-to-end dashboards (Shopify Sales, Ad Attribution)
- Interactive charts (line, bar) using ECharts
- CSV export functionality
- Tailwind CSS styling

---

## Architecture Decisions

### Why Next.js?
- Single codebase for frontend + API routes (faster MVP delivery)
- TypeScript-first for type safety
- Built-in routing reduces config overhead
- Vercel-ready for free deployment

### Why ECharts over alternatives?
- Open source, no licensing cost
- Mainstream in Chinese tech companies (resume-friendly)
- Superior interactivity vs Chart.js
- Smaller bundle size vs full D3

### Why Mock Data Now?
- Decouples frontend development from upstream data readiness
- Mock data follows the **Data Contract** schema (zero refactor when real data arrives)
- Enables parallel work with the data team

---

## Data Contracts Defined

Pre-defined data contracts for two upstream sources before ingestion:
- `docs/data_contracts/shopify_orders.md`
- `docs/data_contracts/triplewhale_attribution.md`

Each contract specifies:
- Source system & ingestion method
- Schema (column types, nullability)
- Quality expectations
- Layer mapping (ODS / DWD / DWS)
- Downstream consumers

---

## Trade-offs

| Decision | Trade-off |
|---|---|
| Hardcoded users in `users.ts` | Quick MVP; will be replaced with DB + SSO in production |
| Mock data in API routes | Frontend can be demoed before upstream data is ready |
| JWT in httpOnly cookie | Simpler than full session management; secure enough for internal tool |

---

## Lessons Learned

- Defining Data Contracts before code accelerates downstream alignment
- Following real-world schemas in mock data prevents Phase 3 rework
- Tailwind utility-first approach speeds up dashboard layout iteration

---

## Next: Phase 2A — FastAPI Metrics Service Skeleton
