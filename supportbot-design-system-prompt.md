# SupportBot Studio — Design System Implementation Prompt
# Paste this into Claude Code at the root of your SupportBot Studio project.

---

## TASK: Implement Trust & Authority Design System across Admin and Super Admin panels

### Success Criteria (done when ALL are true)
- [ ] `frontend/src/globals.css` contains the full CSS variable token set below
- [ ] No hardcoded purple/violet hex values remain in any admin or super admin JSX/CSS file
- [ ] All admin buttons, links, and highlights use `var(--color-cta)` (#0369A1)
- [ ] All admin backgrounds use `var(--color-bg)` (#F8FAFC) or `var(--color-surface)` (#FFFFFF)
- [ ] Widget files (`widget.js`, widget-related components) are untouched — widget purple stays
- [ ] Fira Code + Fira Sans fonts are imported in `frontend/index.html`
- [ ] Pre-delivery checklist passes (see bottom)

---

### Step 1 — Read architecture first
Before touching any file:
1. List all `.jsx`, `.css`, and `.html` files under `frontend/src/`
2. Identify which files belong to: admin panel | super admin panel | widget | shared
3. State your file list and classification before proceeding

---

### Step 2 — Update `frontend/src/globals.css`

Replace or extend the `:root` block with these exact tokens:

```css
@import url('https://fonts.googleapis.com/css2?family=Fira+Code:wght@400;500;600;700&family=Fira+Sans:wght@300;400;500;600;700&display=swap');

:root {
  /* ── Admin & Super Admin palette ────────────────────── */
  --color-primary:     #0F172A;   /* Dark Navy — sidebar bg, headers */
  --color-secondary:   #334155;   /* Slate — secondary text, borders */
  --color-cta:         #0369A1;   /* Professional Blue — buttons, links */
  --color-cta-hover:   #0284C7;   /* CTA hover */
  --color-cta-light:   #EFF6FF;   /* Ghost bg, pill badges, row hover */
  --color-bg:          #F8FAFC;   /* Page background */
  --color-surface:     #FFFFFF;   /* Cards, modals, inputs */
  --color-border:      #E2E8F0;   /* Dividers, input borders */
  --color-text:        #020617;   /* Body text */
  --color-muted:       #64748B;   /* Placeholder, inactive nav items */
  --color-success:     #16A34A;   /* Active, online, success */
  --color-warning:     #D97706;   /* Pending, caution */
  --color-danger:      #DC2626;   /* Error, escalation */

  /* ── Typography ─────────────────────────────────────── */
  --font-heading:      'Fira Code', monospace;
  --font-body:         'Fira Sans', sans-serif;

  /* ── Widget palette — DO NOT use in admin panels ─────── */
  --widget-primary:    #7C3AED;
  --widget-secondary:  #A78BFA;
  --widget-cta:        #06B6D4;
  --widget-bg:         #FAF5FF;
}

/* Base resets using tokens */
body {
  font-family: var(--font-body);
  background: var(--color-bg);
  color: var(--color-text);
}

h1, h2, h3, h4, h5, h6 {
  font-family: var(--font-heading);
  color: var(--color-primary);
}
```

---

### Step 3 — Sweep admin and super admin JSX files

For each admin/super admin JSX file:

1. **Find all hardcoded purple/violet values** — any of: `#7C3AED`, `#6D28D9`, `#8B5CF6`, `#A78BFA`, `purple`, `violet`, `indigo` (unless intentional brand use)
2. **Replace with the correct token:**

| Was | Replace with | Token |
|---|---|---|
| Purple button bg | `var(--color-cta)` | #0369A1 |
| Purple button hover | `var(--color-cta-hover)` | #0284C7 |
| Purple sidebar/nav bg | `var(--color-primary)` | #0F172A |
| Purple text accent | `var(--color-secondary)` | #334155 |
| Purple border/divider | `var(--color-border)` | #E2E8F0 |
| Purple highlight/pill | `var(--color-cta-light)` | #EFF6FF |
| Page background | `var(--color-bg)` | #F8FAFC |
| Card/modal bg | `var(--color-surface)` | #FFFFFF |

3. **Do NOT touch** any file that is part of the widget (chat bubble, widget.js, embeddable widget CSS)

---

### Step 4 — Update `frontend/index.html`

Add to `<head>` if not already present:
```html
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Fira+Code:wght@400;500;600;700&family=Fira+Sans:wght@300;400;500;600;700&display=swap" rel="stylesheet">
```

---

### Step 5 — Sidebar / Nav component

The sidebar background should be `var(--color-primary)` (#0F172A — dark navy).
Active nav item: left border `3px solid var(--color-cta)` + `background: var(--color-cta-light)`.
Inactive nav item text: `var(--color-muted)`.
Active nav item text: `var(--color-surface)` (white).

---

### Step 6 — Buttons

Primary button:
```css
background: var(--color-cta);
color: #FFFFFF;
border: none;
border-radius: 6px;
padding: 8px 16px;
font-family: var(--font-body);
font-weight: 500;
cursor: pointer;
transition: background 150ms ease;
```
Hover: `background: var(--color-cta-hover)`

Ghost/secondary button:
```css
background: transparent;
color: var(--color-cta);
border: 1px solid var(--color-cta);
```

Danger button:
```css
background: var(--color-danger);
color: #FFFFFF;
```

---

### Step 7 — Tables

```css
thead { background: var(--color-primary); color: #FFFFFF; font-family: var(--font-heading); }
tbody tr:hover { background: var(--color-cta-light); }
td, th { border-bottom: 1px solid var(--color-border); }
```

---

### Step 8 — Status badges

```css
/* Use these classes — no hardcoded colors */
.badge-success { background: #DCFCE7; color: var(--color-success); }
.badge-warning { background: #FEF3C7; color: var(--color-warning); }
.badge-danger  { background: #FEE2E2; color: var(--color-danger);  }
.badge-muted   { background: var(--color-border); color: var(--color-muted); }
```

---

### NEVER / ALWAYS for this task

**NEVER:**
- Touch widget.js or any widget-related file
- Hardcode a hex color in JSX — always use CSS vars
- Use `purple`, `violet`, or `indigo` in admin/super admin CSS
- Change layout, routing, or logic — design tokens only

**ALWAYS:**
- State the file you're editing and why before editing it
- Show a before/after diff summary per file
- Run a final grep for leftover purple values after all edits:
  ```bash
  grep -r "#7C3AED\|#6D28D9\|#8B5CF6\|#A78BFA\|: purple\|: violet" frontend/src/ --include="*.jsx" --include="*.css"
  ```
- Report the grep result — it must return empty before marking task done

---

### Pre-Delivery Checklist (verify before closing)
- [ ] No emojis as icons (Heroicons/Lucide SVGs only)
- [ ] `cursor-pointer` on all clickable elements
- [ ] Hover transitions 150–300ms on all interactive elements
- [ ] Text contrast ≥ 4.5:1 on light backgrounds
- [ ] Focus states visible for keyboard navigation
- [ ] `prefers-reduced-motion` respected where animations exist
- [ ] Responsive: test at 375px, 768px, 1024px, 1440px
- [ ] grep for purple returns empty
