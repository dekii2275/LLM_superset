# Superset chart images in PDF reports

## Context

The current report endpoint returns chart query rows. The frontend reconstructs each visualization with a generic Recharts component before rasterizing the report to PDF, so the result does not preserve Superset's chart formatting. This repository uses Superset 6.1.0 and Redis, but does not currently configure the Superset thumbnail pipeline or run a Celery worker.

## Goal

Include rendered images of the saved Superset charts in the existing LLM-generated PDF report so chart styles, labels, and marks match Superset. Keep the current report scope: saved chart configuration, without dashboard filters.

## Design

1. Enable Superset's built-in `THUMBNAILS` screenshot API and configure its thumbnail cache and Celery broker on the existing Redis instance.
2. Install Playwright Chromium in the existing Superset image and add a Celery worker service using that image and configuration.
3. Extend the existing backend report flow to request each chart screenshot through Superset's authenticated API, poll the screenshot cache until ready with a bounded timeout, and include each PNG with its chart metadata and LLM insight in the report response.
4. Render those PNGs in the existing hidden report document in place of reconstructed `DynamicChart` components, then keep the existing browser-side PDF generation and save behavior.

The backend will construct screenshot requests from chart IDs returned by the configured dashboard and only fetch Superset-relative screenshot paths, keeping credentials server-side and avoiding arbitrary URL fetches. A failed screenshot will return a useful report error instead of silently substituting a chart with different styling.

## Out of scope

- Applying current dashboard filter selections to the report.
- Replacing the existing PDF renderer or changing the Save dialog behavior.
- Exporting the entire dashboard as one large screenshot; charts remain alongside their LLM-written insights in the report.

## Verification

- Add backend tests for the screenshot request/polling flow, PNG response handling, and timeout/error behavior.
- Run backend tests and the frontend production build.
- Rebuild/restart the local Superset services and generate a PDF to verify chart images render. Docker access is currently denied in this environment, so this integration check may require restoring Docker access.
