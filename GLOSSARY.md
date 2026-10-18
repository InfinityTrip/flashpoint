# Flashpoint

A public map of news-reported conflict events worldwide, built from the GDELT 2.0 event feed and filterable by region, conflict type and date.

## Events

**Event**:
One GDELT row: a single action between actors, machine-coded from a news article, with a date and a location. A news report of something, not a verified incident.
_Avoid_: incident, attack, report

**Conflict type**:
One of the 7 top-level CAMEO categories from 14 (Protest) to 20 (Mass violence) that Flashpoint keeps.
_Avoid_: category, event class

**Location precision**:
How exactly GDELT placed an event: city, province, or only the country's centre point.
_Avoid_: accuracy, geo type

## Places

**Country**:
A country as GDELT identifies it, by its FIPS code (for example `SU` for Sudan), linked to its ISO code and name.
_Avoid_: nation

**Region**:
One of the 7 World Bank world regions that countries are grouped into.
_Avoid_: area, zone, admin1

## Analysis

**Surge**:
A country whose event count in the last 7 days is well above its baseline.
_Avoid_: spike, hotspot, trend

**Baseline**:
A country's average weekly event count over the 3 weeks before the current 7 days.
_Avoid_: normal, average

## Pipeline

**Ingest run**:
One execution of the job that fetches the newest GDELT file and stores its conflict events.
_Avoid_: sync, import, crawl

**Retention window**:
How many days of events are kept before the oldest are deleted (35).
_Avoid_: history limit, TTL
