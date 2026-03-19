# Interactive Filter Sidebar Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a persistent, toggleable filter sidebar to the Firebase website that exposes all queryable BigQuery columns as selectable pills, enabling users to discover and build rich natural language queries.

**Architecture:** Single-file modification (`firebase/public/index.html`). Three areas of change: (1) new right-side filter sidebar with two-tier pill organization, (2) trimmed welcome section with 6 route-typed example query chips, (3) header update with Filters toggle button. No backend/API changes.

**Tech Stack:** HTML, CSS, vanilla JavaScript (no frameworks — matches existing codebase)

**Spec:** `docs/superpowers/specs/2026-03-19-interactive-filter-sidebar-design.md`

---

## File Structure

Only one file is modified:

- **Modify:** `firebase/public/index.html` — all CSS, HTML, and JS changes

Changes are organized in three sections of the file:
1. **CSS** (lines 7–836) — new sidebar styles, filter pill category colors, header layout, welcome trim, query chip grid, mobile overrides
2. **HTML** (lines 838–1021) — header update, sidebar markup, welcome section rewrite
3. **JS** (lines 1023–1372) — sidebar toggle, pill state management, query generation, tier 2 accordion, clear/send controls

---

### Task 1: Add Filter Sidebar CSS

**Files:**
- Modify: `firebase/public/index.html:7-836` (CSS section)

- [ ] **Step 1: Add CSS custom properties for new category colors**

Add after the existing `:root` block (line 25), inside the same `:root` declaration:

```css
--filter-amber: #f59e0b;
--filter-green: #10b981;
--filter-pink: #ec4899;
```

- [ ] **Step 2: Add filter sidebar CSS**

Add after the About Drawer CSS block (after line 815, before `/* ── Responsive ── */`):

```css
/* ── Filter Sidebar ── */
#filter-sidebar {
  position: fixed;
  top: 0;
  right: -300px;
  width: 300px;
  max-width: 100vw;
  height: 100vh;
  background: var(--card);
  border-left: 1px solid var(--card-border);
  z-index: 101;
  transition: right 0.35s cubic-bezier(0.4, 0, 0.2, 1);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

#filter-sidebar.open {
  right: 0;
}

.filter-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 18px;
  border-bottom: 1px solid var(--card-border);
  flex-shrink: 0;
}

.filter-header h3 {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-heading);
}

.filter-body {
  flex: 1;
  overflow-y: auto;
  padding: 14px 18px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.filter-body::-webkit-scrollbar { width: 5px; }
.filter-body::-webkit-scrollbar-thumb { background: var(--card-border); border-radius: 3px; }

.filter-group-label {
  font-size: 9px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 1px;
  margin-bottom: 6px;
}

.filter-group-label.cyan { color: var(--accent); }
.filter-group-label.purple { color: var(--accent-purple); }
.filter-group-label.amber { color: var(--filter-amber); }
.filter-group-label.green { color: var(--filter-green); }
.filter-group-label.pink { color: var(--filter-pink); }

.filter-pills {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
}

.filter-pill {
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.08);
  color: #aaa;
  padding: 4px 10px;
  border-radius: 12px;
  font-size: 11px;
  cursor: pointer;
  transition: all 0.25s ease;
}

.filter-pill:hover {
  color: #ddd;
  transform: translateY(-1px);
}

/* Category-specific pill colors */
.filter-pill.cyan { border-color: rgba(0, 212, 255, 0.15); }
.filter-pill.cyan:hover { border-color: rgba(0, 212, 255, 0.4); background: rgba(0, 212, 255, 0.06); }
.filter-pill.cyan.selected { border-color: var(--accent); color: #fff; background: rgba(0, 212, 255, 0.15); box-shadow: 0 0 12px rgba(0, 212, 255, 0.2); }

.filter-pill.purple { border-color: rgba(139, 92, 246, 0.15); }
.filter-pill.purple:hover { border-color: rgba(139, 92, 246, 0.4); background: rgba(139, 92, 246, 0.06); }
.filter-pill.purple.selected { border-color: var(--accent-purple); color: #fff; background: rgba(139, 92, 246, 0.15); box-shadow: 0 0 12px rgba(139, 92, 246, 0.2); }

.filter-pill.amber { border-color: rgba(245, 158, 11, 0.15); }
.filter-pill.amber:hover { border-color: rgba(245, 158, 11, 0.4); background: rgba(245, 158, 11, 0.06); }
.filter-pill.amber.selected { border-color: var(--filter-amber); color: #fff; background: rgba(245, 158, 11, 0.15); box-shadow: 0 0 12px rgba(245, 158, 11, 0.2); }

.filter-pill.green { border-color: rgba(16, 185, 129, 0.15); }
.filter-pill.green:hover { border-color: rgba(16, 185, 129, 0.4); background: rgba(16, 185, 129, 0.06); }
.filter-pill.green.selected { border-color: var(--filter-green); color: #fff; background: rgba(16, 185, 129, 0.15); box-shadow: 0 0 12px rgba(16, 185, 129, 0.2); }

.filter-pill.pink { border-color: rgba(236, 72, 153, 0.15); }
.filter-pill.pink:hover { border-color: rgba(236, 72, 153, 0.4); background: rgba(236, 72, 153, 0.06); }
.filter-pill.pink.selected { border-color: var(--filter-pink); color: #fff; background: rgba(236, 72, 153, 0.15); box-shadow: 0 0 12px rgba(236, 72, 153, 0.2); }

/* Tier 2 collapsible sections */
.filter-tier2-divider {
  border-top: 1px solid rgba(255, 255, 255, 0.06);
  padding-top: 12px;
}

.filter-tier2-header {
  font-size: 10px;
  color: rgba(255, 255, 255, 0.4);
  cursor: pointer;
  padding: 4px 0;
  transition: color 0.2s;
  user-select: none;
}

.filter-tier2-header:hover {
  color: rgba(255, 255, 255, 0.7);
}

.filter-tier2-pills {
  display: none;
  flex-wrap: wrap;
  gap: 5px;
  padding-top: 6px;
}

.filter-tier2-pills.expanded {
  display: flex;
}

/* Sticky query preview at sidebar bottom */
.filter-query-preview {
  flex-shrink: 0;
  padding: 12px 18px;
  border-top: 1px solid var(--card-border);
  background: var(--card);
}

.filter-query-label {
  font-size: 9px;
  color: rgba(255, 255, 255, 0.3);
  margin-bottom: 6px;
}

.filter-query-text {
  padding: 6px 10px;
  background: rgba(0, 212, 255, 0.05);
  border: 1px solid rgba(0, 212, 255, 0.15);
  border-radius: 6px;
  font-size: 11px;
  color: rgba(255, 255, 255, 0.7);
  margin-bottom: 8px;
  min-height: 28px;
  word-wrap: break-word;
}

.filter-query-actions {
  display: flex;
  gap: 6px;
}

.filter-send-btn {
  flex: 1;
  text-align: center;
  padding: 6px;
  background: rgba(0, 212, 255, 0.15);
  border: 1px solid rgba(0, 212, 255, 0.3);
  border-radius: 6px;
  font-size: 10px;
  color: var(--accent);
  cursor: pointer;
  transition: background 0.2s;
}

.filter-send-btn:hover {
  background: rgba(0, 212, 255, 0.25);
}

.filter-clear-btn {
  padding: 6px 12px;
  border: 1px solid rgba(255, 255, 255, 0.1);
  border-radius: 6px;
  font-size: 10px;
  color: rgba(255, 255, 255, 0.4);
  cursor: pointer;
  background: none;
  transition: border-color 0.2s, color 0.2s;
}

.filter-clear-btn:hover {
  border-color: rgba(255, 255, 255, 0.3);
  color: rgba(255, 255, 255, 0.7);
}

/* Filter overlay — shared with About drawer on mobile */
#filter-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.6);
  z-index: 100;
  opacity: 0;
  pointer-events: none;
  transition: opacity 0.3s ease;
}

#filter-overlay.open {
  opacity: 1;
  pointer-events: all;
}

/* Filters header button */
.filters-btn {
  background: none;
  border: 1px solid var(--card-border);
  color: var(--text);
  padding: 6px 14px;
  border-radius: 6px;
  font-size: 13px;
  cursor: pointer;
  transition: border-color 0.2s, color 0.2s;
  white-space: nowrap;
}

.filters-btn:hover {
  border-color: var(--accent);
  color: var(--accent);
}

.filters-btn.active {
  border-color: var(--accent);
  color: var(--accent);
  background: rgba(0, 212, 255, 0.08);
}
```

- [ ] **Step 3: Add welcome section new styles (query chip groups)**

Add after the filter sidebar CSS, before `/* ── Responsive ── */`:

```css
/* ── Welcome Query Chips (grouped by route type) ── */
.welcome-chip-groups {
  display: inline-flex;
  flex-direction: column;
  gap: 10px;
}

.chip-group-row {
  display: flex;
  gap: 10px;
  align-items: center;
  justify-content: center;
}

.chip-group-tag {
  flex-shrink: 0;
  text-align: center;
  width: 58px;
}

.chip-group-tag-label {
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 7px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  font-weight: bold;
}

.chip-group-tag-label.vibe {
  background: rgba(139, 92, 246, 0.15);
  border: 1px solid rgba(139, 92, 246, 0.3);
  color: var(--accent-purple);
}

.chip-group-tag-label.data {
  background: rgba(59, 130, 246, 0.15);
  border: 1px solid rgba(59, 130, 246, 0.3);
  color: var(--badge-sql);
}

.chip-group-tag-label.both {
  background: linear-gradient(90deg, rgba(0, 212, 255, 0.15), rgba(139, 92, 246, 0.15));
  border: 1px solid rgba(0, 212, 255, 0.3);
}

.chip-group-tag-label.both span {
  background: linear-gradient(90deg, var(--accent), var(--accent-purple));
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
}

.chip-group-tag-sub {
  font-size: 6px;
  margin-top: 1px;
}

.chip-group-tag-sub.vibe { color: rgba(139, 92, 246, 0.45); }
.chip-group-tag-sub.data { color: rgba(59, 130, 246, 0.45); }
.chip-group-tag-sub.both { color: rgba(0, 212, 255, 0.45); }

.chip-query {
  padding: 5px 12px;
  background: rgba(255, 255, 255, 0.03);
  border-radius: 16px;
  font-size: 9px;
  color: rgba(255, 255, 255, 0.65);
  cursor: pointer;
  white-space: nowrap;
  transition: all 0.2s;
}

.chip-query:hover {
  color: rgba(255, 255, 255, 0.9);
  transform: translateY(-1px);
}

.chip-query.vibe { border: 1px solid rgba(139, 92, 246, 0.15); }
.chip-query.vibe:hover { border-color: rgba(139, 92, 246, 0.4); background: rgba(139, 92, 246, 0.06); }

.chip-query.data { border: 1px solid rgba(59, 130, 246, 0.15); }
.chip-query.data:hover { border-color: rgba(59, 130, 246, 0.4); background: rgba(59, 130, 246, 0.06); }

.chip-query.both { border: 1px solid rgba(0, 212, 255, 0.12); }
.chip-query.both:hover { border-color: rgba(0, 212, 255, 0.4); background: rgba(0, 212, 255, 0.06); }

.welcome-filter-hint {
  font-size: 10px;
  color: rgba(0, 212, 255, 0.6);
  cursor: pointer;
  transition: color 0.2s;
}

.welcome-filter-hint:hover {
  color: var(--accent);
}

.welcome-ai-note {
  font-size: 14px;
  color: #888;
  max-width: 480px;
  line-height: 1.6;
}
```

- [ ] **Step 4: Update responsive CSS for sidebar + new welcome**

Add inside the existing `@media (max-width: 600px)` block:

```css
#filter-sidebar { width: 100vw; right: -100vw; }

/* Stack query chips vertically on mobile, hide tags */
.chip-group-row { flex-direction: column; gap: 6px; }
.chip-group-tag { display: none; }
.chip-query { white-space: normal; text-align: center; }
```

- [ ] **Step 5: Verify CSS compiles — open in browser**

Run: `cd firebase && firebase serve` (or just open the file in a browser)
Expected: Page loads without errors. No visible changes yet (HTML not added).

- [ ] **Step 6: Commit**

```bash
git add -f firebase/public/index.html
git commit -m "feat: add CSS for filter sidebar, category pill colors, and query chip groups"
```

---

### Task 2: Add Filter Sidebar HTML + Header Update

**Files:**
- Modify: `firebase/public/index.html` (HTML section)

- [ ] **Step 1: Update header — remove subtitle, add Filters button**

Replace the entire `<header>` block (lines 841–847):

```html
<header>
  <button class="about-btn" onclick="openDrawer()">&#9776; About</button>
  <div class="header-title">
    <h1>Yelp Streaming Intelligence</h1>
  </div>
  <button class="filters-btn" id="filters-btn" onclick="toggleFilterSidebar()">&#128269; Filters</button>
</header>
```

Key changes: removed `<span>` subtitle from header-title, added Filters button on the right.

- [ ] **Step 2: Add filter sidebar HTML + overlay**

Add immediately after the About Drawer closing `</aside>` tag (after line 964):

```html
<!-- ── Filter Sidebar ── -->
<div id="filter-overlay" onclick="closeFilterSidebar()"></div>
<aside id="filter-sidebar" role="dialog" aria-label="Filter sidebar">
  <div class="filter-header">
    <h3>Explore Filters</h3>
    <button class="drawer-close" onclick="closeFilterSidebar()" aria-label="Close">&#215;</button>
  </div>
  <div class="filter-body" id="filter-body">
    <!-- Tier 1: Cities -->
    <div>
      <div class="filter-group-label cyan">Cities</div>
      <div class="filter-pills" id="pills-cities"></div>
    </div>
    <!-- Tier 1: Categories -->
    <div>
      <div class="filter-group-label purple">Categories</div>
      <div class="filter-pills" id="pills-categories"></div>
    </div>
    <!-- Tier 1: Ambiance -->
    <div>
      <div class="filter-group-label amber">Ambiance</div>
      <div class="filter-pills" id="pills-ambiance"></div>
    </div>
    <!-- Tier 1: Price Range -->
    <div>
      <div class="filter-group-label green">Price Range</div>
      <div class="filter-pills" id="pills-price"></div>
    </div>
    <!-- Tier 1: Amenities -->
    <div>
      <div class="filter-group-label pink">Amenities</div>
      <div class="filter-pills" id="pills-amenities"></div>
    </div>
    <!-- Tier 2: Collapsed groups -->
    <div class="filter-tier2-divider">
      <div class="filter-tier2-header" onclick="toggleTier2('parking')">&#9654; Parking (5)</div>
      <div class="filter-tier2-pills" id="pills-parking"></div>
      <div class="filter-tier2-header" onclick="toggleTier2('music')">&#9654; Music (7)</div>
      <div class="filter-tier2-pills" id="pills-music"></div>
      <div class="filter-tier2-header" onclick="toggleTier2('hours')">&#9654; Hours (7)</div>
      <div class="filter-tier2-pills" id="pills-hours"></div>
      <div class="filter-tier2-header" onclick="toggleTier2('more-amenities')">&#9654; More Amenities (11)</div>
      <div class="filter-tier2-pills" id="pills-more-amenities"></div>
    </div>
  </div>
  <!-- Sticky query preview -->
  <div class="filter-query-preview" id="filter-query-preview" style="display:none;">
    <div class="filter-query-label">Generated query:</div>
    <div class="filter-query-text" id="filter-query-text"></div>
    <div class="filter-query-actions">
      <button class="filter-send-btn" onclick="sendFilterQuery()">Send Query</button>
      <button class="filter-clear-btn" onclick="clearAllFilters()">Clear</button>
    </div>
  </div>
</aside>
```

- [ ] **Step 3: Verify HTML renders — open in browser**

Run: Open `firebase/public/index.html` in browser.
Expected: Header shows About on left, title in center, Filters button on right. Clicking Filters does nothing yet (JS not wired). Sidebar HTML exists in DOM but is off-screen.

- [ ] **Step 4: Commit**

```bash
git add -f firebase/public/index.html
git commit -m "feat: add filter sidebar HTML markup and Filters button in header"
```

---

### Task 3: Rewrite Welcome Section HTML

**Files:**
- Modify: `firebase/public/index.html` (welcome section in HTML)

- [ ] **Step 1: Replace the welcome section content**

Replace the entire `<div id="welcome">...</div>` block (lines 968–1006) with:

```html
<div id="welcome">
  <h2 class="welcome-heading">Ask anything about Yelp businesses</h2>
  <p class="welcome-sub">1M+ reviews across 10 cities. Tap a query or explore filters to get started.</p>
  <p class="welcome-ai-note">Every answer shows how the AI reasoned — explore the SQL, vector matches, and routing behind each response.</p>
  <span class="welcome-filter-hint" onclick="openFilterSidebar()">Explore filters &rarr; cities, ambiance, parking, music &amp; more</span>

  <div class="welcome-chip-groups">
    <!-- Vibe / Vector -->
    <div class="chip-group-row">
      <div class="chip-group-tag">
        <div class="chip-group-tag-label vibe">Vibe</div>
        <div class="chip-group-tag-sub vibe">vector search</div>
      </div>
      <button class="chip-query vibe" data-query="romantic rooftop dining with a quiet ambiance">romantic rooftop dining with a quiet ambiance</button>
      <button class="chip-query vibe" data-query="cozy cafes perfect for working all day">cozy cafes perfect for working all day</button>
    </div>
    <!-- Data / SQL -->
    <div class="chip-group-row">
      <div class="chip-group-tag">
        <div class="chip-group-tag-label data">Data</div>
        <div class="chip-group-tag-sub data">structured sql</div>
      </div>
      <button class="chip-query data" data-query="top 5 cities by average restaurant rating">top 5 cities by average restaurant rating</button>
      <button class="chip-query data" data-query="percentage of restaurants with outdoor seating by city">percentage of restaurants with outdoor seating by city</button>
    </div>
    <!-- Both / Hybrid -->
    <div class="chip-group-row">
      <div class="chip-group-tag">
        <div class="chip-group-tag-label both"><span>Both</span></div>
        <div class="chip-group-tag-sub both">hybrid search</div>
      </div>
      <button class="chip-query both" data-query="family-friendly seafood places open on Sundays">family-friendly seafood places open on Sundays</button>
      <button class="chip-query both" data-query="highly rated brunch spots with free wifi and delivery">highly rated brunch spots with free wifi and delivery</button>
    </div>
  </div>
</div>
```

- [ ] **Step 2: Verify welcome renders — open in browser**

Expected: Welcome section shows heading, two subtitle lines, cyan filter hint, and 6 query chips in 3 rows with route-type tags on the left. No city/category pills visible. Chips are horizontally laid out per row.

- [ ] **Step 3: Commit**

```bash
git add -f firebase/public/index.html
git commit -m "feat: trim welcome section — replace pills with 6 route-typed query chips"
```

---

### Task 4: Add Filter Sidebar JavaScript — Toggle, Pill Rendering, State

**Files:**
- Modify: `firebase/public/index.html` (JS section)

- [ ] **Step 1: Add filter data definitions and state**

Add at the top of the `<script>` block, after the existing state variables (after line 1030):

```javascript
/* ── Filter Sidebar State ── */
let filterSidebarOpen = false;
const filterSelections = {};

/* ── Filter Data Definitions ── */
const FILTER_GROUPS = {
  cities: {
    label: 'Cities', color: 'cyan', tier: 1,
    pills: ['Philadelphia', 'Tucson', 'Tampa', 'Nashville', 'New Orleans', 'Indianapolis', 'Reno', 'Santa Barbara']
  },
  categories: {
    label: 'Categories', color: 'purple', tier: 1,
    pills: ['Italian', 'Pizza', 'Coffee & Tea', 'Bars', 'Seafood', 'Breakfast & Brunch', 'Nightlife', 'Sandwiches']
  },
  ambiance: {
    label: 'Ambiance', color: 'amber', tier: 1,
    pills: ['Full Bar', 'Beer & Wine', 'Quiet', 'Loud', 'Free WiFi', 'No Smoking']
  },
  price: {
    label: 'Price Range', color: 'green', tier: 1,
    pills: ['$', '$$', '$$$', '$$$$']
  },
  amenities: {
    label: 'Amenities', color: 'pink', tier: 1,
    pills: ['Outdoor Seating', 'Delivery', 'Good for Kids', 'Reservations', 'Good for Groups', 'Dogs Allowed']
  },
  parking: {
    label: 'Parking', color: 'pink', tier: 2,
    pills: ['Garage', 'Street', 'Validated', 'Lot', 'Valet']
  },
  music: {
    label: 'Music', color: 'amber', tier: 2,
    pills: ['DJ', 'Background', 'No Music', 'Jukebox', 'Live', 'Video', 'Karaoke']
  },
  hours: {
    label: 'Hours', color: 'cyan', tier: 2,
    pills: ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
  },
  'more-amenities': {
    label: 'More Amenities', color: 'pink', tier: 2,
    pills: ['Bike Parking', 'Credit Cards', 'Bitcoin', 'Drive Thru', 'Has TV', 'Table Service', 'Take Out', 'Wheelchair Accessible', 'Open 24 Hours', 'By Appointment Only', 'BYOB']
  }
};

// Initialize empty selection arrays for each group
Object.keys(FILTER_GROUPS).forEach(key => { filterSelections[key] = []; });
```

- [ ] **Step 2: Add sidebar toggle functions**

Add after the filter data definitions:

```javascript
/* ── Filter Sidebar Toggle ── */
function openFilterSidebar() {
  document.getElementById('filter-sidebar').classList.add('open');
  document.getElementById('filter-overlay').classList.add('open');
  document.getElementById('filters-btn').classList.add('active');
  filterSidebarOpen = true;

  // On mobile, close About drawer if open and lock background scroll
  if (window.innerWidth <= 600) {
    closeDrawer();
    document.body.style.overflow = 'hidden';
  }
}

function closeFilterSidebar() {
  document.getElementById('filter-sidebar').classList.remove('open');
  document.getElementById('filter-overlay').classList.remove('open');
  document.getElementById('filters-btn').classList.remove('active');
  filterSidebarOpen = false;

  // Restore scroll if About drawer is also closed
  if (!document.getElementById('drawer').classList.contains('open')) {
    document.body.style.overflow = '';
  }
}

function toggleFilterSidebar() {
  if (filterSidebarOpen) {
    closeFilterSidebar();
  } else {
    openFilterSidebar();
  }
}
```

- [ ] **Step 3: Add pill rendering function**

Add after the toggle functions:

```javascript
/* ── Render Filter Pills ── */
function renderFilterPills() {
  Object.entries(FILTER_GROUPS).forEach(([groupKey, group]) => {
    const container = document.getElementById(`pills-${groupKey}`);
    if (!container) return;
    container.innerHTML = '';
    group.pills.forEach(pillLabel => {
      const btn = document.createElement('button');
      btn.className = `filter-pill ${group.color}`;
      btn.textContent = pillLabel;
      btn.addEventListener('click', () => toggleFilterPill(groupKey, pillLabel, btn));
      container.appendChild(btn);
    });
  });
}
```

- [ ] **Step 4: Add pill toggle function**

```javascript
/* ── Toggle Filter Pill Selection ── */
function toggleFilterPill(groupKey, value, btnEl) {
  const arr = filterSelections[groupKey];
  const idx = arr.indexOf(value);

  if (idx >= 0) {
    arr.splice(idx, 1);
    btnEl.classList.remove('selected');
  } else {
    arr.push(value);
    btnEl.classList.add('selected');
  }

  updateFilterQueryPreview();
}
```

- [ ] **Step 5: Add tier 2 accordion toggle**

```javascript
/* ── Tier 2 Accordion Toggle ── */
function toggleTier2(groupKey) {
  const pillsEl = document.getElementById(`pills-${groupKey}`);
  const headerEl = pillsEl.previousElementSibling;
  const isExpanded = pillsEl.classList.contains('expanded');

  pillsEl.classList.toggle('expanded', !isExpanded);
  headerEl.innerHTML = `${isExpanded ? '&#9654;' : '&#9660;'} ${FILTER_GROUPS[groupKey].label} (${FILTER_GROUPS[groupKey].pills.length})`;
}
```

- [ ] **Step 6: Initialize pills on page load**

Add at the bottom of the `<script>` block (before `</script>`):

```javascript
/* ── Initialize filter pills on page load ── */
renderFilterPills();
```

- [ ] **Step 7: Verify sidebar opens and pills render**

Open in browser. Click "Filters" button in header.
Expected: Sidebar slides in from right with all Tier 1 pill groups populated. Tier 2 groups are collapsed headers. Clicking a pill toggles its selected state. Clicking a Tier 2 header expands to show pills.

- [ ] **Step 8: Commit**

```bash
git add -f firebase/public/index.html
git commit -m "feat: add filter sidebar JS — toggle, pill rendering, state management, tier 2 accordion"
```

---

### Task 5: Add Query Generation Logic

**Files:**
- Modify: `firebase/public/index.html` (JS section)

- [ ] **Step 1: Add query generation function**

Add after the `toggleFilterPill` function:

```javascript
/* ── Generate Natural Language Query from Selections ── */
function generateFilterQuery() {
  const cities = filterSelections.cities;
  const categories = filterSelections.categories;
  const ambiance = filterSelections.ambiance;
  const price = filterSelections.price;
  const amenities = filterSelections.amenities;
  const parking = filterSelections.parking;
  const music = filterSelections.music;
  const hours = filterSelections.hours;
  const moreAmenities = filterSelections['more-amenities'];

  // Collect all "with" qualifiers
  const withParts = [];
  if (ambiance.length > 0) withParts.push(...ambiance.map(a => a.toLowerCase()));
  if (amenities.length > 0) withParts.push(...amenities.map(a => a.toLowerCase()));
  if (parking.length > 0) withParts.push(...parking.map(p => `${p.toLowerCase()} parking`));
  if (music.length > 0) withParts.push(...music.map(m => `${m.toLowerCase()} music`));
  if (moreAmenities.length > 0) withParts.push(...moreAmenities.map(a => a.toLowerCase()));
  if (price.length > 0) withParts.push(...price.map(p => `${p} price range`));

  // Hours
  const hourParts = hours.map(h => `open on ${h}s`);

  // Build category phrase
  const catPhrase = categories.length > 0 ? categories.join(' or ') : '';
  // Build city phrase
  const cityPhrase = cities.length > 0 ? cities.join(', ') : '';

  // Count total filter parts
  const totalParts = (catPhrase ? 1 : 0) + (cityPhrase ? 1 : 0) + withParts.length + hourParts.length;

  if (totalParts === 0) return '';

  // 5+ filters — use dash-list format
  if (totalParts >= 5) {
    const allParts = [];
    if (catPhrase) allParts.push(catPhrase);
    allParts.push(...withParts);
    allParts.push(...hourParts);
    const base = cityPhrase ? `restaurants in ${cityPhrase}` : 'restaurants';
    return `${base} — ${allParts.join(', ')}`;
  }

  // Build natural sentence
  let query = '';

  if (catPhrase && cityPhrase) {
    query = `best ${catPhrase} in ${cityPhrase}`;
  } else if (cityPhrase) {
    query = `top rated restaurants in ${cityPhrase}`;
  } else if (catPhrase) {
    query = `best ${catPhrase} restaurants`;
  } else {
    query = 'restaurants';
  }

  const allQualifiers = [...withParts, ...hourParts];
  if (allQualifiers.length > 0) {
    query += ` with ${allQualifiers.join(' and ')}`;
  }

  return query;
}
```

- [ ] **Step 2: Add query preview update function**

```javascript
/* ── Update Query Preview in Sidebar ── */
function updateFilterQueryPreview() {
  const query = generateFilterQuery();
  const previewEl = document.getElementById('filter-query-preview');
  const textEl = document.getElementById('filter-query-text');

  if (query) {
    textEl.textContent = query;
    previewEl.style.display = 'block';
    // Also update the main input field
    inputEl.value = query;
  } else {
    previewEl.style.display = 'none';
    inputEl.value = '';
  }
}
```

- [ ] **Step 3: Add send and clear functions**

```javascript
/* ── Send query from sidebar ── */
function sendFilterQuery() {
  const query = generateFilterQuery();
  if (query) {
    sendQuery(query);
    clearAllFilters();
  }
}

/* ── Clear all filter selections ── */
function clearAllFilters() {
  Object.keys(filterSelections).forEach(key => { filterSelections[key] = []; });
  document.querySelectorAll('.filter-pill.selected').forEach(el => el.classList.remove('selected'));
  updateFilterQueryPreview();
}
```

- [ ] **Step 4: Verify query generation — open in browser**

Open in browser. Open sidebar. Select "Tampa" (city) + "Italian" (category) + "Quiet" (ambiance).
Expected: Query preview shows `best Italian in Tampa with quiet`. Main input field also populated with same text. Click "Send Query" sends the query and clears all selections.

- [ ] **Step 5: Commit**

```bash
git add -f firebase/public/index.html
git commit -m "feat: add natural language query generation from filter pill selections"
```

---

### Task 6: Wire Up Query Chips + Remove Old Pill Logic + Escape Key

**Files:**
- Modify: `firebase/public/index.html` (JS section)

- [ ] **Step 1: Remove old pill/chip code and replace with new chip handlers**

Remove ALL of the following old code (approximately lines 1310–1353):
- The old chip click handler block: `document.querySelectorAll('.chip').forEach(...)` (lines 1310–1315)
- The `selectedCities` and `selectedCategories` variable declarations (lines 1318–1319)
- The `updateInputFromPills()` function (lines 1321–1335)
- The `document.querySelectorAll('.pill').forEach(...)` block (lines 1337–1353)

Replace with new chip-query click handlers:

```javascript
/* ── Query chip click handlers ── */
document.querySelectorAll('.chip-query').forEach(chip => {
  chip.addEventListener('click', () => {
    const query = chip.dataset.query;
    if (query) sendQuery(query);
  });
});
```

- [ ] **Step 2: Update Escape key handler to close filter sidebar too**

Replace the existing Escape key handler (line 1369–1371) with:

```javascript
// Escape key closes drawers
document.addEventListener('keydown', e => {
  if (e.key === 'Escape') {
    closeDrawer();
    closeFilterSidebar();
  }
});
```

- [ ] **Step 3: Update About drawer open to close filter sidebar on mobile**

Modify the existing `openDrawer()` function to add mobile-awareness:

```javascript
function openDrawer() {
  document.getElementById('drawer').classList.add('open');
  document.getElementById('drawer-overlay').classList.add('open');
  document.body.style.overflow = 'hidden';
  // On mobile, close filter sidebar if open
  if (window.innerWidth <= 600) {
    closeFilterSidebar();
  }
}
```

- [ ] **Step 4: Full integration test in browser**

Test the following scenarios:
1. Page loads — welcome shows with 6 query chips grouped by type, no city/category pills
2. Click a query chip — sends query, welcome hides, chat shows response
3. Click "Explore filters →" hint — sidebar opens from right
4. Click "Filters" in header — sidebar toggles open/closed
5. Select pills across categories — query preview updates, input field updates
6. Click "Send Query" in sidebar — sends query, clears selections
7. Click "Clear" — all pills deselect, preview hides
8. Tier 2 headers expand/collapse on click
9. Escape key closes sidebar
10. On mobile viewport: sidebar is full-width overlay, only one drawer at a time
11. About drawer still works independently on desktop

Expected: All 11 scenarios pass.

- [ ] **Step 5: Commit**

```bash
git add -f firebase/public/index.html
git commit -m "feat: wire up query chips, remove old pill logic, integrate sidebar with keyboard and drawers"
```

---

### Task 7: Final Polish + Deploy Verification

**Files:**
- Modify: `firebase/public/index.html` (minor tweaks if needed)

- [ ] **Step 1: Test with Firebase serve locally**

```bash
cd firebase && npx firebase-tools serve --only hosting
```

Open `http://localhost:5000` in browser. Verify all functionality from Task 6 Step 4.

- [ ] **Step 2: Deploy to Firebase Hosting**

```bash
cd firebase && npx firebase-tools deploy --only hosting
```

Expected: Successful deploy. Verify at the live Firebase URL.

- [ ] **Step 3: Update docs/explanation.md**

Append a new section to `docs/explanation.md` documenting the interactive filter sidebar:
- What was built (filter sidebar, trimmed welcome, query chips)
- Why (users couldn't discover filterable fields after first query)
- Design decisions (right-side sidebar, two-tier pills, natural language generation)
- What it demonstrates (enterprise UX patterns, progressive disclosure)

- [ ] **Step 4: Final commit**

```bash
git add -f firebase/public/index.html docs/explanation.md
git commit -m "feat: interactive filter sidebar — complete implementation with docs"
```
