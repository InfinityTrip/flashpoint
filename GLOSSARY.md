# Flashpoint

A public map of news-reported conflict events worldwide, built from the GDELT 2.0 event feed and filterable by region, conflict type and date.

## Events

**Event**:
One GDELT row: a single action between actors, machine-coded from a news article, with a date and a location. A news report of something, not a verified incident.
_Avoid_: incident, attack, report

**Conflict type**:
One of the 7 top-level CAMEO categories from 14 (Protest) to 20 (Mass violence) that Flashpoint keeps.
_Avoid_: category, event class

**Major event**:
An event in a violent category (assault, fight, mass violence, violent protest or violent repression) that at least 2 news sources reported. The site's default view; on the map, each source article appears once, as its most-reported event.
_Avoid_: important event, significant event, verified event

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
A country whose event count in the last 7 days is statistically unusual compared with its baseline.
_Avoid_: spike, hotspot, trend

**Baseline**:
A country's typical daily event count, and how much it varies, over the 3 weeks before the current 7 days.
_Avoid_: normal, average

**Replay**:
Playing back stored events day by day on the globe to show how a situation developed.
_Avoid_: animation, timelapse, playback

**Episode**:
A named, ready-made stretch of history that can be replayed, such as the first weeks of a war.
_Avoid_: scenario, preset, case study

## Pipeline

**Ingest run**:
One execution of the job that fetches the newest GDELT file and stores its conflict events.
_Avoid_: sync, import, crawl

**Retention window**:
How many days of events are kept before the oldest are deleted (35).
_Avoid_: history limit, TTL
