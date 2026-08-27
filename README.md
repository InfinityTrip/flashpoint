# Flashpoint

An OSINT (open-source intelligence) conflict-tracking platform: aggregates live geopolitical incident data from the **ACLED** and **GDELT** APIs across active conflict zones, stores it in a time-series-oriented PostgreSQL schema, and serves filterable map visualizations (by region, conflict type, and date) through a FastAPI backend and a React + Leaflet frontend.

Read `ARCHITECTURE.md` for the full design reasoning before writing code — start a session here with "read ARCHITECTURE.md, let's start on the ingestion pipeline."

This is a companion learning project to a separate MUN crisis-simulator project — deliberately chosen to teach a different set of skills (data pipelines, geospatial querying, analytical schema design, and query performance at scale) rather than the real-time/WebSocket skills that project focuses on.
