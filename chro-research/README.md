# CHRO Research System

A repeatable methodology for CHRO meetings, modeled on two disciplines:
- **Equity-research rigor** (Morgan Stanley style) for pre-meeting intelligence — arrive with a
  thesis, not a blank slate.
- **Panel-survey discipline** (Nielsen style) for in-meeting data capture — same structured
  questions every time, so 30 meetings become one comparable dataset instead of 30 disconnected
  anecdotes.

Research and sales are deliberately kept in separate files so the neutral discovery
questionnaire never gets bent to fit a pitch.

## Workflow

1. **Before the meeting** — fill out `00_pre_meeting_research_brief.md` (copy it per meeting,
   e.g. `2026-07-05_JaneDoe_Acme.md`). 45-60 min of desk research. Ends with 3-5 falsifiable
   hypotheses and a clear primary/secondary objective.

2. **During the meeting** — run `01_discovery_questionnaire.md` verbatim, in order. Same
   instrument every time. Capture answers in the structured format shown (scale/choice/short
   text), not prose — that's what makes them tabulable later.

3. **Only if genuine signal surfaced** — open `02_sales_qualification_addon.md` as a separate
   follow-up exercise. If nothing relevant came up unprompted, skip it — that's a valid,
   informative outcome, not a failure.

4. **Immediately after** — transfer Section A-D answers from the questionnaire into
   `chro_meetings_tracker.csv` as one new row. Do this same-day while it's fresh.

## Why the CSV
One row per meeting means you can eventually sort/filter/pivot on any column — e.g. group by
sector to see if manufacturing CHROs report the same headache as IT-services CHROs, or check
whether "DPDP program in progress" correlates with higher document-management dissatisfaction.
That cross-meeting pattern-finding is the actual point of the Nielsen-style discipline — a
single well-run conversation is useful, but 20 of them run the same way is a dataset.

Open the CSV in Excel/Sheets; add a PivotTable once you have 8-10 rows to start looking for
patterns rather than reading it as a flat list.
