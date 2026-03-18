# Firebase Website Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a chat-forward portfolio website as a single `index.html` with inline CSS + vanilla JS, deployed on Firebase Hosting.

**Architecture:** Single HTML file replaces the current Firebase boilerplate. Chat interface is the landing page. Slide-out drawer holds portfolio content. Client-side `fetch()` calls the Flask API at `https://34-10-46-213.sslip.io/query`.

**Tech Stack:** HTML5, CSS3 (custom properties, grid, flexbox, animations), vanilla JavaScript (fetch API, DOM manipulation), Firebase Hosting (Spark plan).

**Spec:** `docs/superpowers/specs/2026-03-17-firebase-website-design.md`

**Note on testing:** This is a zero-dependency static HTML file — no test framework applies. Each task ends with a manual browser verification step via `firebase serve` or opening the file directly. Verify in Chrome DevTools.

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `firebase/public/index.html` | **Rewrite** | Entire website — HTML structure, inline CSS, inline JS |
| `firebase/firebase.json` | **Keep** | Already correct, no changes needed |
| `firebase/public/404.html` | **Keep** | Already exists, untouched |

---

## API Response Reference

The `/query` endpoint returns:

```json
{
  "answer": "string — natural language answer (contains trailing '---\\nRouted as: ...' to strip)",
  "route": "string — 'SQL' | 'VECTOR' | 'HYBRID'",
  "sql_query": "string | null — generated SQL",
  "sql_result": "string | null — agent summary text",
  "vector_results": [
    {
      "name": "Business Name",
      "city": "Phoenix",
      "state": "AZ",
      "categories": "Italian, Pizza",
      "review_stars": 5,
      "business_stars": 4.5,
      "text": "Full review text...",
      "score": 0.7234
    }
  ],
  "error": "string | null"
}
```

---

### Task 1: HTML Skeleton + CSS Theme Foundation

**Files:**
- Rewrite: `firebase/public/index.html`

Build the page shell with CSS custom properties, the dark theme, background pattern, and basic layout containers. No interactivity yet — just a styled empty page with the header bar and input area.

- [ ] **Step 1: Replace index.html with HTML skeleton**

Replace the entire Firebase boilerplate with a clean HTML5 document. Structure:
- `<head>`: meta tags, title, `<style>` block
- `<body>`: header bar, main chat area, input bar
- No Firebase SDK scripts (we don't use any Firebase backend services)

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Yelp Streaming Intelligence</title>
  <style>
    /* CSS goes here — built up across tasks */
  </style>
</head>
<body>
  <header id="header">
    <button id="about-btn" aria-label="About this project">&#9776; About</button>
    <h1>Yelp Streaming Intelligence</h1>
  </header>

  <main id="chat-area">
    <div id="welcome">
      <p class="welcome-text">Ask me anything about Yelp businesses — ratings, reviews, vibes, recommendations.</p>
      <div id="chips">
        <button class="chip" data-query="cozy Italian restaurants in Phoenix">cozy Italian restaurants in Phoenix</button>
        <button class="chip" data-query="average rating for restaurants in Scottsdale">average rating for restaurants in Scottsdale</button>
        <button class="chip" data-query="best restaurants in the top rated cities">best restaurants in the top rated cities</button>
      </div>
    </div>
    <div id="messages"></div>
  </main>

  <footer id="input-bar">
    <textarea id="query-input" placeholder="Ask about Yelp businesses..." rows="1"></textarea>
    <button id="send-btn" aria-label="Send">&#10148;</button>
  </footer>

  <script>
    /* JS goes here — built up across tasks */
  </script>
</body>
</html>
```

- [ ] **Step 2: Add CSS custom properties and base theme**

Inside the `<style>` block, add:

```css
:root {
  --bg: #0a0a0f;
  --bg-pattern: #1a1a2e;
  --card: #1a1a2e;
  --card-border: #2a2a4a;
  --user-bubble: #252540;
  --accent: #00d4ff;
  --accent-purple: #8b5cf6;
  --text: #e0e0e0;
  --text-heading: #f0f0f0;
  --code-bg: #0d0d1a;
  --badge-sql: #3b82f6;
  --badge-vector: #8b5cf6;
  --error: #ff4444;
  --font: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  --font-mono: 'SF Mono', 'Fira Code', 'Cascadia Code', 'Consolas', monospace;
}

*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

body {
  font-family: var(--font);
  background: var(--bg);
  color: var(--text);
  height: 100vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background-image: radial-gradient(circle, var(--bg-pattern) 1px, transparent 1px);
  background-size: 24px 24px;
}
```

- [ ] **Step 3: Add CSS for header, chat area, and input bar**

```css
#header {
  display: flex;
  align-items: center;
  padding: 0.75rem 1rem;
  border-bottom: 1px solid var(--card-border);
  background: rgba(10, 10, 15, 0.95);
  backdrop-filter: blur(8px);
  z-index: 10;
}

#header h1 {
  flex: 1;
  text-align: center;
  font-size: 1rem;
  font-weight: 500;
  color: var(--text-heading);
  letter-spacing: 0.02em;
}

#about-btn {
  background: none;
  border: 1px solid var(--card-border);
  color: var(--text);
  padding: 0.4rem 0.75rem;
  border-radius: 6px;
  cursor: pointer;
  font-size: 0.85rem;
  font-family: var(--font);
  transition: border-color 0.2s;
}
#about-btn:hover { border-color: var(--accent); color: var(--accent); }

#chat-area {
  flex: 1;
  overflow-y: auto;
  padding: 1.5rem 1rem;
  display: flex;
  flex-direction: column;
  max-width: 800px;
  width: 100%;
  margin: 0 auto;
}

#input-bar {
  display: flex;
  gap: 0.5rem;
  padding: 0.75rem 1rem;
  border-top: 1px solid var(--card-border);
  background: rgba(10, 10, 15, 0.95);
  backdrop-filter: blur(8px);
  max-width: 800px;
  width: 100%;
  margin: 0 auto;
}

#query-input {
  flex: 1;
  background: var(--card);
  border: 1px solid var(--card-border);
  color: var(--text);
  padding: 0.6rem 0.8rem;
  border-radius: 8px;
  font-family: var(--font);
  font-size: 0.9rem;
  resize: none;
  outline: none;
  transition: border-color 0.2s;
}
#query-input:focus { border-color: var(--accent); }

#send-btn {
  background: var(--accent);
  border: none;
  color: var(--bg);
  width: 42px;
  height: 42px;
  border-radius: 8px;
  cursor: pointer;
  font-size: 1.1rem;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: opacity 0.2s;
}
#send-btn:hover { opacity: 0.85; }
#send-btn:disabled { opacity: 0.4; cursor: not-allowed; }
```

- [ ] **Step 4: Add CSS for welcome area and chips**

```css
#welcome {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  flex: 1;
  text-align: center;
  gap: 1.5rem;
}

.welcome-text {
  font-size: 1.05rem;
  color: var(--text);
  opacity: 0.8;
  max-width: 480px;
}

#chips {
  display: flex;
  flex-wrap: wrap;
  gap: 0.5rem;
  justify-content: center;
}

.chip {
  background: var(--card);
  border: 1px solid var(--card-border);
  color: var(--accent);
  padding: 0.5rem 1rem;
  border-radius: 20px;
  cursor: pointer;
  font-family: var(--font);
  font-size: 0.82rem;
  transition: border-color 0.2s, background 0.2s;
}
.chip:hover { border-color: var(--accent); background: rgba(0, 212, 255, 0.08); }

#welcome { transition: opacity 0.3s ease; }
#welcome.hidden { opacity: 0; pointer-events: none; position: absolute; }
```

- [ ] **Step 5: Verify in browser**

Run: `cd firebase && npx http-server public -p 5500` (or open `firebase/public/index.html` directly)

Expected: Dark page with dot-grid background. Slim header with "≡ About" button and title. Welcome text centered with 3 cyan chip buttons. Empty input bar at bottom with cyan send button.

- [ ] **Step 6: Commit**

```bash
git add firebase/public/index.html
git commit -m "feat(firebase): replace boilerplate with chat-forward skeleton and dark theme"
```

---

### Task 2: Chat Messaging JS (Send, Receive, Display)

**Files:**
- Modify: `firebase/public/index.html` (add to `<script>` block)

Wire up the chat interaction: sending queries, displaying user/bot messages, calling the API, and handling responses.

- [ ] **Step 1: Add message CSS styles**

Add to the `<style>` block:

```css
#messages { display: flex; flex-direction: column; gap: 1rem; }

.message { max-width: 85%; animation: fadeIn 0.3s ease; }
.message.user { align-self: flex-end; }
.message.bot { align-self: flex-start; }

.bubble {
  padding: 0.8rem 1rem;
  border-radius: 12px;
  font-size: 0.9rem;
  line-height: 1.55;
  white-space: pre-wrap;
  word-wrap: break-word;
}

.message.user .bubble {
  background: var(--user-bubble);
  border: 1px solid var(--card-border);
}

.message.bot .bubble {
  background: var(--card);
  border: 1px solid var(--card-border);
}

.route-badge {
  display: inline-block;
  padding: 0.15rem 0.55rem;
  border-radius: 10px;
  font-size: 0.7rem;
  font-weight: 600;
  letter-spacing: 0.04em;
  margin-top: 0.5rem;
  text-transform: uppercase;
}
.route-badge.sql { background: var(--badge-sql); color: #fff; }
.route-badge.vector { background: var(--badge-vector); color: #fff; }
.route-badge.hybrid { background: linear-gradient(135deg, var(--accent), var(--accent-purple)); color: #fff; }

.message.error .bubble {
  background: rgba(255, 68, 68, 0.1);
  border-color: rgba(255, 68, 68, 0.3);
  color: #ff8888;
}

.retry-btn {
  background: none;
  border: 1px solid rgba(255, 68, 68, 0.4);
  color: #ff8888;
  padding: 0.3rem 0.7rem;
  border-radius: 6px;
  cursor: pointer;
  font-size: 0.78rem;
  margin-top: 0.5rem;
  font-family: var(--font);
}
.retry-btn:hover { background: rgba(255, 68, 68, 0.1); }

/* Loading dots */
.loading-dots span {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--accent);
  margin: 0 2px;
  animation: pulse 1.4s ease-in-out infinite;
}
.loading-dots span:nth-child(2) { animation-delay: 0.2s; }
.loading-dots span:nth-child(3) { animation-delay: 0.4s; }

@keyframes pulse {
  0%, 80%, 100% { opacity: 0.3; transform: scale(0.8); }
  40% { opacity: 1; transform: scale(1); }
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}
```

- [ ] **Step 2: Add core JS — state, API call, DOM helpers**

Add to the `<script>` block:

```javascript
const API_URL = 'https://34-10-46-213.sslip.io';
const messagesEl = document.getElementById('messages');
const inputEl = document.getElementById('query-input');
const sendBtn = document.getElementById('send-btn');
const welcomeEl = document.getElementById('welcome');
let isLoading = false;
let lastQuery = '';

function stripRouteFooter(text) {
  if (!text) return '';
  return text.replace(/\n\n---\nRouted as:.*$/s, '').trim();
}

function scrollToBottom() {
  const chatArea = document.getElementById('chat-area');
  chatArea.scrollTop = chatArea.scrollHeight;
}

function addUserMessage(text) {
  const div = document.createElement('div');
  div.className = 'message user';
  div.innerHTML = `<div class="bubble">${escapeHtml(text)}</div>`;
  messagesEl.appendChild(div);
  scrollToBottom();
}

function addBotMessage(data) {
  const div = document.createElement('div');
  div.className = 'message bot';

  const answer = stripRouteFooter(data.answer || '');
  const route = (data.route || '').toUpperCase();
  const badgeClass = route.toLowerCase();

  let html = `<div class="bubble">${escapeHtml(answer)}`;
  if (route) {
    html += `<br><span class="route-badge ${badgeClass}">${route}</span>`;
  }
  html += `</div>`;

  // Expandable details built in Task 3
  div.innerHTML = html;
  messagesEl.appendChild(div);
  scrollToBottom();
}

function addErrorMessage(errorText) {
  const div = document.createElement('div');
  div.className = 'message error';
  const bubble = document.createElement('div');
  bubble.className = 'bubble';
  bubble.textContent = errorText;
  const retryBtn = document.createElement('button');
  retryBtn.className = 'retry-btn';
  retryBtn.textContent = 'Try again';
  retryBtn.addEventListener('click', () => sendQuery(lastQuery));
  bubble.appendChild(document.createElement('br'));
  bubble.appendChild(retryBtn);
  div.appendChild(bubble);
  messagesEl.appendChild(div);
  scrollToBottom();
}

function showLoading() {
  const div = document.createElement('div');
  div.className = 'message bot';
  div.id = 'loading-msg';
  div.innerHTML = `<div class="bubble"><span class="loading-dots"><span></span><span></span><span></span></span></div>`;
  messagesEl.appendChild(div);
  scrollToBottom();
}

function removeLoading() {
  const el = document.getElementById('loading-msg');
  if (el) el.remove();
}

function escapeHtml(str) {
  const d = document.createElement('div');
  d.textContent = str;
  return d.innerHTML;
}

async function sendQuery(query) {
  if (isLoading || !query.trim()) return;
  query = query.trim();
  lastQuery = query;
  isLoading = true;
  sendBtn.disabled = true;
  inputEl.disabled = true;

  // Hide welcome chips on first message
  if (welcomeEl && !welcomeEl.classList.contains('hidden')) {
    welcomeEl.classList.add('hidden');
  }

  addUserMessage(query);
  inputEl.value = '';
  showLoading();

  try {
    const res = await fetch(`${API_URL}/query`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query }),
    });
    const data = await res.json();
    removeLoading();

    if (data.error && !data.answer) {
      addErrorMessage(data.error);
    } else {
      addBotMessage(data);
    }
  } catch (err) {
    removeLoading();
    addErrorMessage('The API is currently unavailable. Please try again later.');
  } finally {
    isLoading = false;
    sendBtn.disabled = false;
    inputEl.disabled = false;
    inputEl.focus();
  }
}
```

- [ ] **Step 3: Add event listeners**

```javascript
// Send on click
sendBtn.addEventListener('click', () => sendQuery(inputEl.value));

// Enter to send, Shift+Enter for newline
inputEl.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendQuery(inputEl.value);
  }
});

// Auto-resize textarea
inputEl.addEventListener('input', () => {
  inputEl.style.height = 'auto';
  inputEl.style.height = Math.min(inputEl.scrollHeight, 120) + 'px';
});

// Chip click handlers
document.querySelectorAll('.chip').forEach(chip => {
  chip.addEventListener('click', () => sendQuery(chip.dataset.query));
});
```

- [ ] **Step 4: Verify in browser**

Run: `cd firebase && npx http-server public -p 5500`

Expected:
- Clicking a chip sends the query, shows user bubble, shows loading dots
- If the live API is reachable: bot response appears with route badge
- If API is unreachable: error bubble appears with "Try again" button
- Enter sends, Shift+Enter adds newline
- Welcome chips disappear after first message
- Chat auto-scrolls on new messages

- [ ] **Step 5: Commit**

```bash
git add firebase/public/index.html
git commit -m "feat(firebase): add chat messaging, API integration, and loading states"
```

---

### Task 3: Expandable Details (Route Transparency)

**Files:**
- Modify: `firebase/public/index.html` (CSS + update `addBotMessage` in JS)

Add the collapsible "Show how this was answered" section under each bot response, showing SQL query, SQL result, and vector match cards.

- [ ] **Step 1: Add CSS for expandable details section**

Add to `<style>`:

```css
.details-toggle {
  background: none;
  border: none;
  color: var(--accent);
  font-size: 0.78rem;
  cursor: pointer;
  padding: 0.4rem 0;
  font-family: var(--font);
  opacity: 0.7;
  transition: opacity 0.2s;
}
.details-toggle:hover { opacity: 1; }

.details-panel {
  max-height: 0;
  overflow: hidden;
  transition: max-height 0.3s ease;
}
.details-panel.open { max-height: 2000px; }

.details-content {
  background: var(--code-bg);
  border: 1px solid var(--card-border);
  border-radius: 8px;
  padding: 0.8rem;
  margin-top: 0.4rem;
  font-size: 0.82rem;
}

.details-content h4 {
  color: var(--accent);
  font-size: 0.75rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: 0.4rem;
}

.details-content h4:not(:first-child) { margin-top: 0.8rem; }

.sql-block {
  background: var(--bg);
  border: 1px solid var(--card-border);
  border-radius: 6px;
  padding: 0.6rem;
  font-family: var(--font-mono);
  font-size: 0.78rem;
  color: var(--accent);
  overflow-x: auto;
  white-space: pre-wrap;
  word-break: break-all;
}

.vector-card {
  background: var(--bg);
  border: 1px solid var(--card-border);
  border-radius: 6px;
  padding: 0.6rem;
  margin-top: 0.4rem;
}

.vector-card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 0.3rem;
}

.vector-card-name {
  font-weight: 600;
  color: var(--text-heading);
  font-size: 0.82rem;
}

.vector-card-score {
  color: var(--accent);
  font-size: 0.72rem;
  font-family: var(--font-mono);
}

.vector-card-meta {
  font-size: 0.72rem;
  color: var(--text);
  opacity: 0.6;
  margin-bottom: 0.3rem;
}

.vector-card-text {
  font-size: 0.78rem;
  color: var(--text);
  opacity: 0.8;
  font-style: italic;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
```

- [ ] **Step 2: Update `addBotMessage` to include expandable details**

Replace the `addBotMessage` function:

```javascript
function buildDetailsHtml(data) {
  const route = (data.route || '').toUpperCase();
  let html = `<div class="details-content">`;
  html += `<h4>Routed as: ${escapeHtml(route)}</h4>`;

  if (data.sql_query) {
    html += `<h4>SQL Query</h4><div class="sql-block">${escapeHtml(data.sql_query)}</div>`;
  }
  if (data.sql_result) {
    html += `<h4>SQL Result</h4><p>${escapeHtml(data.sql_result)}</p>`;
  }
  if (data.vector_results && data.vector_results.length > 0) {
    html += `<h4>Vector Matches (${data.vector_results.length})</h4>`;
    for (const r of data.vector_results) {
      const stars = r.business_stars ? `★${r.business_stars}` : '';
      const meta = [r.city, r.state, r.categories].filter(Boolean).join(' · ');
      const snippet = (r.text || '').slice(0, 200) + ((r.text || '').length > 200 ? '...' : '');
      html += `<div class="vector-card">
        <div class="vector-card-header">
          <span class="vector-card-name">${escapeHtml(r.name || 'Unknown')} ${stars}</span>
          <span class="vector-card-score">${r.score.toFixed(3)}</span>
        </div>
        <div class="vector-card-meta">${escapeHtml(meta)}</div>
        <div class="vector-card-text">"${escapeHtml(snippet)}"</div>
      </div>`;
    }
  }

  html += `</div>`;
  return html;
}

function addBotMessage(data) {
  const div = document.createElement('div');
  div.className = 'message bot';

  const answer = stripRouteFooter(data.answer || '');
  const route = (data.route || '').toUpperCase();
  const badgeClass = route.toLowerCase();
  const hasDetails = data.sql_query || data.sql_result || (data.vector_results && data.vector_results.length > 0);
  const detailsId = 'details-' + Date.now();

  let html = `<div class="bubble">${escapeHtml(answer)}`;
  if (route) {
    html += `<br><span class="route-badge ${badgeClass}">${route}</span>`;
  }
  html += `</div>`;

  if (hasDetails) {
    html += `<button class="details-toggle" onclick="toggleDetails('${detailsId}', this)">&#9656; Show how this was answered</button>`;
    html += `<div class="details-panel" id="${detailsId}">${buildDetailsHtml(data)}</div>`;
  }

  div.innerHTML = html;
  messagesEl.appendChild(div);
  scrollToBottom();
}
```

- [ ] **Step 3: Add `toggleDetails` function**

```javascript
function toggleDetails(id, btn) {
  const panel = document.getElementById(id);
  panel.classList.toggle('open');
  btn.innerHTML = panel.classList.contains('open')
    ? '&#9662; Hide details'
    : '&#9656; Show how this was answered';
  scrollToBottom();
}
```

- [ ] **Step 4: Verify in browser**

Run: `cd firebase && npx http-server public -p 5500`

Expected:
- Send a query that returns SQL data (e.g., "average rating in Scottsdale") — expandable shows SQL Query code block and SQL Result text
- Send a query that returns vector data (e.g., "cozy Italian restaurants in Phoenix") — expandable shows vector match cards with name, stars, score, review snippet
- Send a HYBRID query — expandable shows both SQL and vector sections
- Toggle opens/closes smoothly with height transition
- Toggle text changes between "Show how this was answered" / "Hide details"

- [ ] **Step 5: Commit**

```bash
git add firebase/public/index.html
git commit -m "feat(firebase): add expandable response details with SQL, vector match transparency"
```

---

### Task 4: About Drawer

**Files:**
- Modify: `firebase/public/index.html` (HTML + CSS + JS)

Add the slide-out drawer with the portfolio content: one-liner pitch, architecture diagram, tech stack grid, "why this matters" bullets, and GitHub link.

- [ ] **Step 1: Add drawer HTML after the header element**

Insert into the HTML body, right after the closing `</header>` tag:

```html
<div id="drawer-overlay" class="overlay" onclick="closeDrawer()"></div>
<aside id="drawer">
  <button id="drawer-close" onclick="closeDrawer()" aria-label="Close">&#10005;</button>
  <h2>About This Project</h2>

  <p class="drawer-pitch">A real-time streaming platform that builds the data infrastructure AI agents need &mdash; medallion pipelines feeding dual sinks, with an agentic layer that decides how to answer.</p>

  <h3>Architecture</h3>
  <div class="arch-diagram">
    <div class="arch-flow">
      <div class="arch-node">Yelp Data</div>
      <div class="arch-arrow">&rarr;</div>
      <div class="arch-node">Redpanda</div>
      <div class="arch-arrow">&rarr;</div>
      <div class="arch-node accent">Bronze</div>
      <div class="arch-arrow">&rarr;</div>
      <div class="arch-node accent">Silver</div>
      <div class="arch-arrow">&rarr;</div>
      <div class="arch-node accent">Gold</div>
    </div>
    <div class="arch-split">
      <div class="arch-branch">
        <div class="arch-arrow">&darr;</div>
        <div class="arch-node sql">BigQuery</div>
      </div>
      <div class="arch-branch">
        <div class="arch-arrow">&darr;</div>
        <div class="arch-node vector">Qdrant</div>
      </div>
    </div>
    <div class="arch-flow">
      <div class="arch-node">User</div>
      <div class="arch-arrow">&larr;</div>
      <div class="arch-node accent">Synthesizer</div>
      <div class="arch-arrow">&larr;</div>
      <div class="arch-node accent">Agent Router</div>
    </div>
  </div>

  <h3>Tech Stack</h3>
  <div class="stack-grid">
    <div class="stack-row"><span class="stack-label">Streaming</span><span>Redpanda (Kafka), PySpark</span></div>
    <div class="stack-row"><span class="stack-label">Structured Store</span><span>BigQuery (free tier)</span></div>
    <div class="stack-row"><span class="stack-label">Vector Store</span><span>Qdrant (self-hosted)</span></div>
    <div class="stack-row"><span class="stack-label">LLM / Embeddings</span><span>Gemini Flash-Lite, gemini-embedding-001</span></div>
    <div class="stack-row"><span class="stack-label">Agent Orchestration</span><span>LangGraph + LangChain</span></div>
    <div class="stack-row"><span class="stack-label">API</span><span>Flask on GCP e2-micro</span></div>
    <div class="stack-row"><span class="stack-label">Frontend</span><span>Firebase Hosting (static)</span></div>
  </div>

  <h3>Why This Matters</h3>
  <div class="highlights">
    <div class="highlight">
      <strong>Medallion architecture for AI-ready data</strong>
      <p>Bronze/Silver/Gold streaming pipeline that cleans, joins, and shapes 1M+ reviews into formats both SQL engines and vector databases can serve. The AI layer doesn't wrangle data &mdash; it consumes clean, typed, deduplicated outputs.</p>
    </div>
    <div class="highlight">
      <strong>Dual-sink design</strong>
      <p>A single streaming job fans out to BigQuery (structured analytics) and Qdrant (semantic search) independently. The agent decides which sink to query &mdash; I made sure both are always current and consistent.</p>
    </div>
    <div class="highlight">
      <strong>Agentic routing over structured + unstructured data</strong>
      <p>An explicit LLM router classifies queries into SQL, Vector, or Hybrid paths. Not a free-form ReAct agent &mdash; a deliberate, cost-controlled routing decision. Hybrid runs sequentially: SQL narrows candidates, Vector ranks semantically.</p>
    </div>
    <div class="highlight">
      <strong>Zero-cost production deployment</strong>
      <p>The entire platform runs at $0/month on GCP free tier. 1GB RAM VM serving Qdrant + Flask, BigQuery sandbox for analytics, Gemini free tier for LLM + embeddings. Engineering within constraints, not throwing money at problems.</p>
    </div>
  </div>

  <div class="drawer-footer">
    <a href="https://github.com/rahulpdev/yelp-streaming-intelligence" target="_blank" rel="noopener">View on GitHub &rarr;</a>
  </div>
</aside>
```

**Note:** The GitHub URL above uses a placeholder username. Update to the correct repo URL during implementation.

- [ ] **Step 2: Add drawer CSS**

```css
.overlay {
  display: none;
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.6);
  z-index: 90;
}
.overlay.open { display: block; }

#drawer {
  position: fixed;
  top: 0;
  left: -420px;
  width: 400px;
  max-width: 85vw;
  height: 100vh;
  background: var(--bg);
  border-right: 1px solid var(--card-border);
  z-index: 100;
  overflow-y: auto;
  padding: 1.5rem;
  transition: left 0.3s ease;
}
#drawer.open { left: 0; }

#drawer-close {
  position: absolute;
  top: 1rem;
  right: 1rem;
  background: none;
  border: none;
  color: var(--text);
  font-size: 1.2rem;
  cursor: pointer;
}
#drawer-close:hover { color: var(--accent); }

#drawer h2 {
  color: var(--text-heading);
  font-size: 1.15rem;
  margin-bottom: 1rem;
}

#drawer h3 {
  color: var(--accent);
  font-size: 0.8rem;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  margin: 1.5rem 0 0.6rem;
}

.drawer-pitch {
  color: var(--text);
  font-size: 0.9rem;
  line-height: 1.55;
  opacity: 0.9;
}

/* Architecture diagram */
.arch-diagram {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  align-items: center;
}
.arch-flow {
  display: flex;
  align-items: center;
  gap: 0.3rem;
  flex-wrap: wrap;
  justify-content: center;
}
.arch-split {
  display: flex;
  gap: 2rem;
  justify-content: center;
}
.arch-branch {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.3rem;
}
.arch-node {
  background: var(--card);
  border: 1px solid var(--card-border);
  padding: 0.3rem 0.6rem;
  border-radius: 6px;
  font-size: 0.72rem;
  white-space: nowrap;
}
.arch-node.accent { border-color: var(--accent); color: var(--accent); }
.arch-node.sql { border-color: var(--badge-sql); color: var(--badge-sql); }
.arch-node.vector { border-color: var(--badge-vector); color: var(--badge-vector); }
.arch-arrow { color: var(--accent); font-size: 0.9rem; opacity: 0.6; }

/* Tech stack grid */
.stack-grid { display: flex; flex-direction: column; gap: 0.3rem; }
.stack-row {
  display: flex;
  gap: 0.8rem;
  font-size: 0.82rem;
  padding: 0.3rem 0;
  border-bottom: 1px solid rgba(42, 42, 74, 0.4);
}
.stack-label {
  color: var(--accent);
  min-width: 130px;
  font-size: 0.75rem;
  opacity: 0.8;
}

/* Highlight bullets */
.highlights { display: flex; flex-direction: column; gap: 0.8rem; }
.highlight {
  background: var(--card);
  border: 1px solid var(--card-border);
  border-radius: 8px;
  padding: 0.7rem;
}
.highlight strong {
  color: var(--text-heading);
  font-size: 0.85rem;
  display: block;
  margin-bottom: 0.3rem;
}
.highlight p {
  font-size: 0.78rem;
  line-height: 1.5;
  opacity: 0.8;
  margin: 0;
}

.drawer-footer {
  margin-top: 2rem;
  padding-top: 1rem;
  border-top: 1px solid var(--card-border);
}
.drawer-footer a {
  color: var(--accent);
  text-decoration: none;
  font-size: 0.85rem;
}
.drawer-footer a:hover { text-decoration: underline; }
```

- [ ] **Step 3: Add drawer JS**

```javascript
function openDrawer() {
  document.getElementById('drawer').classList.add('open');
  document.getElementById('drawer-overlay').classList.add('open');
}

function closeDrawer() {
  document.getElementById('drawer').classList.remove('open');
  document.getElementById('drawer-overlay').classList.remove('open');
}

document.getElementById('about-btn').addEventListener('click', openDrawer);

// Close drawer on Escape key
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') closeDrawer();
});
```

- [ ] **Step 4: Verify in browser**

Expected:
- Clicking "≡ About" slides the drawer in from the left, overlay dims the chat
- Drawer shows: pitch text, architecture diagram with colored nodes, tech stack grid, 4 highlight cards, GitHub link
- Clicking ✕ or overlay or pressing Escape closes the drawer
- Drawer scrolls if content overflows on small screens
- Architecture diagram nodes are color-coded: cyan for pipeline, blue for BigQuery, purple for Qdrant

- [ ] **Step 5: Commit**

```bash
git add firebase/public/index.html
git commit -m "feat(firebase): add About drawer with architecture, tech stack, and project highlights"
```

---

### Task 5: Polish and Final Verification

**Files:**
- Modify: `firebase/public/index.html`

Final refinements: responsive tweaks, edge cases, and end-to-end verification.

- [ ] **Step 1: Add responsive CSS for narrow screens**

```css
@media (max-width: 600px) {
  #header h1 { font-size: 0.85rem; }
  .chip { font-size: 0.75rem; padding: 0.4rem 0.8rem; }
  .message { max-width: 95%; }
  #drawer { width: 100%; max-width: 100vw; left: -100%; }
  .arch-flow { gap: 0.15rem; }
  .arch-node { font-size: 0.65rem; padding: 0.2rem 0.4rem; }
}
```

- [ ] **Step 2: Handle edge case — textarea auto-height reset after send**

In the `sendQuery` function, after `inputEl.value = '';`, add:

```javascript
inputEl.style.height = 'auto';
```

- [ ] **Step 3: Update GitHub link to correct repository URL**

Verify the GitHub repo URL in the drawer HTML. Update if needed (check `git remote -v` output).

- [ ] **Step 4: Full end-to-end browser verification**

Run: `cd firebase && firebase serve` (or `npx http-server public -p 5500`)

Verify all of these:
1. Page loads with dark theme, dot-grid background, welcome text, 3 chips
2. Click "cozy Italian restaurants in Phoenix" chip — sends query, loading dots appear, response with VECTOR/HYBRID badge arrives, expandable details show vector matches
3. Click "average rating for restaurants in Scottsdale" chip — SQL route, expandable shows SQL query
4. Type a custom query in the input, press Enter — sends correctly
5. Shift+Enter adds a newline, doesn't send
6. Welcome chips disappear after first message
7. "≡ About" opens drawer with all content, Escape closes it
8. Error state: disconnect from internet, send query — error bubble with "Try again" appears
9. "Try again" button re-sends the last query
10. No console errors in Chrome DevTools

- [ ] **Step 5: Commit**

```bash
git add firebase/public/index.html
git commit -m "feat(firebase): polish responsive layout and edge cases"
```

---

### Task 6: Update docs/explanation.md

**Files:**
- Modify: `docs/explanation.md`

Append the Phase 8 section documenting the Firebase website.

- [ ] **Step 1: Append Phase 8 to explanation.md**

First, check the last phase number in `docs/explanation.md` (currently Phase 7). Add to the end of the file:

```markdown
## Phase 8: Firebase Website — Portfolio Showcase + Live Chat

### What Was Built
A chat-forward portfolio website deployed on Firebase Hosting (Spark plan). The chat interface IS the landing page — hiring managers land and immediately interact with the live agent system. A slide-out drawer holds the project narrative: architecture diagram, tech stack, and 4 "why this matters" bullets framed around the core message: "I'm a data engineer who builds the infrastructure that makes AI work."

### Design Decisions

**Chat-forward, not content-forward:** Most portfolio sites make you scroll past a hero section, architecture diagrams, and tech stack lists before finding the demo. This site inverts that — the demo is the first thing you see. The architecture details are pull (click "About"), not push (scroll past them). For a hiring manager spending 2-3 minutes, the interactive chat demonstrates more than any static diagram.

**Single HTML file:** One `index.html` with inline CSS and vanilla JS. Zero dependencies, zero build step. This is a portfolio site for a data engineering role — frontend framework choice is irrelevant. A single file deploys instantly and has no maintenance burden.

**Expandable response details:** Every agent response shows a route badge (SQL / VECTOR / HYBRID) and a collapsible "Show how this was answered" section revealing the generated SQL, query results, and vector match cards with similarity scores. This transparency is the portfolio pitch — it shows the system's decision-making live, not just the final answer.

**Dark data/AI visual theme:** Near-black background with electric cyan and purple accents, matching the visual language of Databricks, Snowflake, and Qdrant marketing sites. Signals "data + AI" before a single word is read.

### What the Drawer Contains
- One-liner pitch connecting data engineering to AI
- CSS-rendered architecture diagram (Yelp Data → Redpanda → Bronze → Silver → Gold → BigQuery + Qdrant → Agent Router → User)
- Tech stack grid (7 layers)
- 4 narrative bullets: medallion architecture for AI, dual-sink design, agentic routing, zero-cost deployment

### Deployment
Firebase Hosting on Spark plan (free): 1GB storage, 10GB transfer/month. The HTML file is ~30KB. Static-only — all dynamic behavior is client-side JavaScript calling the Flask API on the GCP VM via HTTPS.
```

- [ ] **Step 2: Commit**

```bash
git add docs/explanation.md
git commit -m "docs: append Phase 8 Firebase website to explanation.md"
```

---

### Task 7: Firebase Deployment

**Files:**
- None modified — deployment only

Deploy to Firebase Hosting and verify the live site.

- [ ] **Step 1: Verify Firebase project is linked**

```bash
cd firebase && firebase projects:list
```

If no project is linked, run `firebase use <project-id>` (the user must have created the project per the Prerequisites section of the spec).

- [ ] **Step 2: Deploy to Firebase Hosting**

```bash
cd firebase && firebase deploy --only hosting
```

Expected: Deployment succeeds, prints the live URL (`https://<project-id>.web.app`).

- [ ] **Step 3: Verify live site**

Open the deployed URL in a browser. Run the same verification checklist from Task 5 Step 4 against the live site. Specifically verify:
- Chat works end-to-end (query → API → response)
- CORS is not blocking requests (check DevTools Network tab)
- Drawer opens and displays correctly

- [ ] **Step 4: Update CORS origin if needed**

If CORS errors appear, update `CORS_ORIGIN` on the GCP VM to include the Firebase Hosting domain:
```bash
gcloud compute ssh yelp-vm --zone=us-central1-a
# Edit .env to set CORS_ORIGIN=https://<project-id>.web.app
# Restart: cd ~/yelp-api && docker compose -f build/docker-compose.yml up -d --build api
```

- [ ] **Step 5: Commit any final changes and record the live URL**

Only commit if files were modified (e.g., CORS origin update):
```bash
git add firebase/public/index.html
git commit -m "deploy: firebase hosting live at https://<project-id>.web.app"
```
