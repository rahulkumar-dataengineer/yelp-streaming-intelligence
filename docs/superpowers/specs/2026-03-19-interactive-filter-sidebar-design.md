# Interactive Filter Sidebar — Design Spec

**Date:** 2026-03-19
**Scope:** Firebase website (`firebase/public/index.html`) — frontend-only changes, no API/VM modifications.

## Problem

The current website shows filter pills (cities + categories) only in the welcome section. After the first query, these disappear permanently. Users lose visibility into what the dataset offers and default to generic queries. The 65-column BigQuery gold layer has rich filterable attributes (parking, music, ambiance, price, amenities, hours) that users never discover.

## Design Summary

1. **Right-side filter sidebar** — persistent, toggleable from a header button. Contains all filterable fields organized as selectable pills.
2. **Trimmed welcome section** — removes city/category pills (moved to sidebar), keeps heading + subtitle + 6 example query chips grouped by route type + sidebar hint.
3. **Natural language query generation** — pill selections build readable sentences in the input field. No API changes required.

## Component 1: Filter Sidebar

### Position & Behavior
- Opens from the **right side** (About drawer stays on the left)
- Toggle button in header: `🔍 Filters` (right-aligned)
- When open: sidebar is 260px wide, chat area shrinks to remaining width
- When closed: chat area is full-width, toggle button always visible in header
- Mobile (<600px): full-width overlay with close button (same pattern as About drawer)
- Slide-in animation matching About drawer's existing transition

### Sidebar Structure
```
┌─────────────────────┐
│ Explore Filters      │  ← Title
├─────────────────────┤
│ CITIES               │  ← Tier 1 (expanded)
│ [pill] [pill] [pill] │
│ [pill] [pill] ...    │
├─────────────────────┤
│ CATEGORIES           │
│ [pill] [pill] [pill] │
├─────────────────────┤
│ AMBIANCE             │
│ [pill] [pill] [pill] │
├─────────────────────┤
│ PRICE RANGE          │
│ [$] [$$] [$$$] [$$$$]│
├─────────────────────┤
│ AMENITIES            │
│ [pill] [pill] [pill] │
├─────────────────────┤
│ ▸ Parking (5)        │  ← Tier 2 (collapsed)
│ ▸ Music (7)          │
│ ▸ Hours (7)          │
│ ▸ More Amenities (11)│
├─────────────────────┤
│ Generated query:     │  ← Sticky bottom
│ "quiet Italian in.." │
│ [Send Query] [Clear] │
└─────────────────────┘
```

### Tier 1 — Always Expanded (~27 pills)

**Cities** (8 pills, cyan theme — `#00d4ff`):
Philadelphia, Tucson, Tampa, Nashville, New Orleans, Indianapolis, Reno, Santa Barbara

**Categories** (8 pills, purple theme — `#8b5cf6`):
Italian, Pizza, Coffee & Tea, Bars, Seafood, Breakfast & Brunch, Nightlife, Sandwiches

**Ambiance** (6 pills, amber theme — `#f59e0b`):
- Alcohol: `Full Bar`, `Beer & Wine` (from `alcohol` column values)
- Noise: `Quiet`, `Loud` (from `noise_level` column values)
- `Free WiFi` (from `wifi` column)
- `No Smoking` (from `smoking` column)

**Price Range** (4 pills, green theme — `#10b981`):
`$` (1), `$$` (2), `$$$` (3), `$$$$` (4) — maps to `restaurants_price_range` integer values

**Amenities** (6 pills, pink theme — `#ec4899`):
`Outdoor Seating`, `Delivery`, `Good for Kids`, `Reservations`, `Good for Groups`, `Dogs Allowed`

### Tier 2 — Collapsed (expand on click)

Separated by a subtle divider below Tier 1. Each group shows as a clickable header with count. Expands inline to reveal pills.

**Parking** (5 pills, uses pink theme):
`Garage`, `Street`, `Validated`, `Lot`, `Valet`

**Music** (7 pills, uses amber theme):
`DJ`, `Background`, `No Music`, `Jukebox`, `Live`, `Video`, `Karaoke`

**Hours** (7 pills, uses cyan theme):
`Monday`, `Tuesday`, `Wednesday`, `Thursday`, `Friday`, `Saturday`, `Sunday`
- These generate queries like "open on Sundays" — boolean presence check, not time-range filtering

**More Amenities** (11 pills, uses pink theme):
`Bike Parking`, `Credit Cards`, `Bitcoin`, `Drive Thru`, `Has TV`, `Table Service`, `Take Out`, `Wheelchair Accessible`, `Open 24 Hours`, `By Appointment Only`, `BYOB`

### Pill Interaction
- **Multi-select** within and across categories
- **Selected state**: highlighted background + colored border + `✕` suffix (matches current site's pill styling)
- **Deselected state**: subtle border, transparent background
- Clicking a selected pill deselects it (toggle behavior)
- Each category has its own color theme for visual grouping

### Query Generation (Bottom Section)

Sticky at the bottom of the sidebar. Updates in real-time as pills are selected.

**Generation rules:**
- Categories and cities are primary: `"Italian in Tampa"`
- Ambiance/amenities append with "with": `"Italian in Tampa with outdoor seating and free wifi"`
- Multiple values in same category use "or": `"Italian or Pizza"`
- Multiple cities use comma: `"Tampa, Nashville"`
- Price maps to text: `"$$$"` → `"upscale"` or stays as `"$$$"`
- Hours append as: `"open on Sundays"`
- 5+ filters use dash-list format: `"restaurants in Tampa — Italian, outdoor seating, free wifi, quiet, has TV"`

**Controls:**
- `Send Query` button — sends the generated text to the API (same as pressing Enter in input)
- `Clear` button — deselects all pills, clears generated query
- Generated query also populates the main input field (editable before sending)

### Color Theme Reference

| Category | Color | CSS |
|----------|-------|-----|
| Cities | Cyan | `#00d4ff` / `rgba(0,212,255,*)` |
| Categories | Purple | `#8b5cf6` / `rgba(139,92,246,*)` |
| Ambiance | Amber | `#f59e0b` / `rgba(245,158,11,*)` |
| Price Range | Green | `#10b981` / `rgba(16,185,129,*)` |
| Amenities | Pink | `#ec4899` / `rgba(236,72,153,*)` |
| Tier 2 headers | Muted white | `rgba(255,255,255,0.4)` |

## Component 2: Trimmed Welcome Section

### What stays
- 🔍 icon
- Heading: "Ask anything about Yelp businesses"
- Subtitle: "1M+ reviews across 10 cities. Tap a query or explore filters to get started."
- AI transparency line: "Every answer shows how the AI reasoned — explore the SQL, vector matches, and routing behind each response." (same 10px size as subtitle)
- Sidebar hint: "Explore filters → cities, ambiance, parking, music & more" (cyan, clickable — opens sidebar)

### What's removed
- All city pills (moved to sidebar)
- All category pills (moved to sidebar)

### What's new — 6 Example Query Chips

Grouped by route type with left-aligned tags and horizontal query pairs. Tags include a sub-label explaining the search type.

**Layout:**
```
[VIBE  ]   [romantic rooftop dining with a quiet ambiance]   [cozy cafes perfect for working all day]
vector search

[DATA  ]   [top 5 cities by average restaurant rating]   [percentage of restaurants with outdoor seating by city]
structured sql

[BOTH  ]   [family-friendly seafood places open on Sundays]   [highly rated brunch spots with free wifi and delivery]
hybrid search
```

**Tag styling:**
- **VIBE** — purple background (`rgba(139,92,246,0.15)`), sub-label "vector search"
- **DATA** — blue background (`rgba(59,130,246,0.15)`), sub-label "structured sql"
- **BOTH** — cyan-to-purple gradient, sub-label "hybrid search"

**Chip styling:**
- Rounded pills (border-radius 16px), border color matches tag color
- Subtle background (`rgba(255,255,255,0.03)`)
- On click: sends the query text directly (same as current chip behavior)

**Centered block:** The tag+queries block uses `inline-flex` to shrink-wrap content and center on screen.

### Welcome hide behavior
- Hides after first message sent (same as current — `.hidden` class with fade)
- Sidebar toggle in header remains visible permanently

## Component 3: Header Changes

Current header: `[☰ About] [Title] [Subtitle]`

New header: `[☰ About] [Title] [🔍 Filters]`

- Subtitle removed from header (it's in the welcome section)
- Filters button right-aligned
- Active state when sidebar is open: `🔍 Filters ✕` with highlighted border
- Both About and Filters can be open simultaneously (About=left, Filters=right) — but on mobile only one at a time

## Mobile Behavior (<600px)

- Sidebar renders as full-width overlay (same as About drawer)
- Filter button always in header
- Query chips in welcome stack vertically (single column, no tags — just pills)
- Only one drawer open at a time: opening Filters closes About and vice versa

## What Does NOT Change

- API endpoint, request/response format — zero backend changes
- Chat message rendering (user/bot/error bubbles)
- Bot message details (expandable SQL/vector sections)
- Input bar position and behavior (fixed bottom)
- About drawer (stays on left, unchanged)
- Loading animation, error handling, retry logic
- Dark theme, color palette, typography
- Route badge styling on bot messages

## File Changes

Only one file changes: `firebase/public/index.html`

- New CSS: sidebar styles, filter pill styles per category, header layout update, welcome section trim, query chip grid
- New HTML: sidebar markup, filter button in header, query chips replacing city/category pills
- New JS: sidebar toggle, pill multi-select state per category, query generation logic, tier 2 accordion expand/collapse, clear/send controls
- Modified JS: `updateInputFromPills()` rewritten for multi-category query generation
- Modified JS: welcome section `hideWelcome()` unchanged — sidebar toggle is independent
- Removed HTML: city pills and category pills from welcome section
