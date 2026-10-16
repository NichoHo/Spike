# Spike: Design System

This file is the single source of truth for how Spike looks and behaves.
Read all of it before you write any template or CSS. If a page needs
something this file does not cover, add the rule here first, then build it.

**Reference products:** the Vercel dashboard and the Stripe dashboard.
Neutral greys, one blue accent, flat surfaces, thin borders, small type,
dense tables, no decoration.

**Stack constraints (from BLUEPRINT.md):** FastAPI + Jinja2 + htmx. Plain CSS
with tokens on `:root`. No CSS framework, no build step, no inline scripts
(CSP). Everything is self-hosted. Nothing loads from a CDN.

---

## Contents

1. Principles
2. Files and how to use them
3. Color
4. Typography
5. Spacing and layout
6. Shape, borders, elevation
7. Icons
8. Motion
9. Components
10. Page recipes (every screen)
11. States: loading, empty, error, stale
12. Copy and formatting
13. Accessibility
14. Banned patterns
15. Review checklist (run before every UI change is done)
16. Appendix: token file (copy as is)

---

## 1. Principles

1. **One page, one job.** Every page exists for one task. It has at most one
   primary button. If a page needs two primary actions, it is two pages.
2. **Content is the interface.** Clips, numbers, and statuses carry the
   page. Chrome (borders, backgrounds, headers) stays quiet.
3. **Consistency beats taste.** Use the tokens, classes, and macros in this
   file. Never invent a new color, size, radius, or shadow inside a template.
4. **Dense but calm.** Small type (14px base), tight rows, generous space
   between groups. Spacing groups things. Lines and boxes are a last resort.
5. **Keyboard first.** Every action on the review screens has a shortcut and
   a visible focus state.
6. **Dark by default.** Video looks better on dark. Light theme is a full
   equal, not an afterthought. Test both.

---

## 2. Files and how to use them

```
app/
  static/
    css/
      tokens.css       # Section 16. Colors, type, spacing, radius, shadow, z-index, motion
      base.css         # Reset, body, headings, links, focus, fonts, utilities
      components.css   # Every component in Section 9
    fonts/
      Geist-Variable.woff2
      GeistMono-Variable.woff2
    icons/             # Phosphor SVGs, regular weight, one file per icon
    js/
      htmx.min.js
      app.js           # Theme toggle, shortcuts, toasts, dialogs. No inline JS
  templates/
    base.html          # App shell (Section 9.1)
    macros/ui.html     # Jinja macros for every component (Section 9)
    pages/...          # One template per page (Section 10)
```

Load order in `base.html`: `tokens.css`, `base.css`, `components.css`.

### Hard rules

- **No `style="..."` attributes** in templates. CSP blocks them, and they
  break consistency. The only exception is none. If you need a value, add a
  class.
- **No hex, rgb, or px values in `components.css`** except `1px` borders and
  the values already shown in this file. Everything else is `var(--token)`.
- **Use the macros.** A button is `{{ ui.button(...) }}`, never a hand-written
  `<button class="...">`. This keeps markup identical on every page.
- **Class naming:** BEM-light. Block `.btn`, modifier `.btn--primary`,
  element `.card__header`. State classes start with `is-`: `.is-active`,
  `.is-loading`. No utility soup.

---

## 3. Color

### 3.1 Rules

- **Neutrals do 95% of the work.** Text, borders, surfaces are grey.
- **One accent: blue.** Used only for links, focus rings, selected states,
  progress, and "in progress" statuses. Never for decoration. Never for the
  primary button (that is neutral, see 9.2).
- **Status colors** (green, amber, red) appear only on badges, inline
  alerts, the danger button, and form errors. Never on headings, icons in
  nav, or backgrounds of whole sections.
- **No gradients. No glows. No colored shadows. No transparency effects
  (no blur, no glass).**
- Video areas use `--color-media-bg` (true black). This is the only place
  true black is allowed.

### 3.2 Semantic tokens

Templates and component CSS only use these names. The values live in
Section 16. Contrast ratios were computed for WCAG 2.1.

| Token | Use | Dark | Light |
|---|---|---|---|
| `--color-bg` | Page background, sidebar | `#0a0a0a` | `#fafafa` |
| `--color-bg-subtle` | Table header, card footer, code block | `#111111` | `#f5f5f5` |
| `--color-surface` | Cards, inputs, menus, dialogs | `#161616` | `#ffffff` |
| `--color-surface-hover` | Hovered row, hovered ghost button | `#1f1f1f` | `#f2f2f2` |
| `--color-surface-active` | Pressed, selected nav item, skeleton | `#262626` | `#ebebeb` |
| `--color-border` | Card and table borders, dividers | `#262626` | `#e5e5e5` |
| `--color-border-strong` | Input borders, secondary button border | `#3a3a3a` | `#d4d4d4` |
| `--color-border-hover` | Hovered input border | `#525252` | `#a3a3a3` |
| `--color-text` | Primary text, headings | `#ededed` | `#171717` |
| `--color-text-muted` | Secondary text, labels, descriptions | `#a1a1a1` | `#666666` |
| `--color-text-subtle` | Placeholders, timestamps, table headers | `#808080` | `#737373` |
| `--color-text-disabled` | Disabled text only | `#525252` | `#a3a3a3` |
| `--color-text-inverse` | Text on primary button | `#0a0a0a` | `#ffffff` |
| `--color-primary` | Primary button background | `#ededed` | `#171717` |
| `--color-primary-hover` | Primary button hover | `#d4d4d4` | `#383838` |
| `--color-accent` | Filled accent (checkbox, progress, switch on) | `#0068d6` | `#0068d6` |
| `--color-accent-text` | Links, accent text | `#4ea1ff` | `#0068d6` |
| `--color-accent-subtle` | Accent badge background, selection | `rgb(78 161 255 / 0.12)` | `rgb(0 104 214 / 0.08)` |
| `--color-focus` | Focus ring | `#4ea1ff` | `#0068d6` |
| `--color-success-text` | Success badge text | `#4cc38a` | `#1a7f4b` |
| `--color-success-subtle` | Success badge background | `rgb(76 195 138 / 0.12)` | `rgb(26 127 75 / 0.08)` |
| `--color-warning-text` | Warning badge text | `#f5a524` | `#a35200` |
| `--color-warning-subtle` | Warning badge background | `rgb(245 165 36 / 0.12)` | `rgb(163 82 0 / 0.08)` |
| `--color-danger` | Danger button background | `#d93036` | `#d93036` |
| `--color-danger-hover` | Danger button hover | `#c1272d` | `#c1272d` |
| `--color-danger-text` | Error text, danger badge text | `#ff6166` | `#d93036` |
| `--color-danger-subtle` | Danger badge background | `rgb(255 97 102 / 0.12)` | `rgb(217 48 54 / 0.08)` |
| `--color-media-bg` | Behind video and thumbnails | `#000000` | `#000000` |
| `--color-overlay` | Dialog backdrop | `rgb(0 0 0 / 0.6)` | `rgb(0 0 0 / 0.4)` |

**Contrast notes**

- `--color-text-muted` passes AA (4.5:1) on every surface.
- `--color-text-subtle` passes AA on `--color-bg` and `--color-surface`
  only. Never put it on `--color-surface-hover` or `--color-surface-active`.
- White on `--color-accent` and on `--color-danger` passes AA (above 4.7:1).
- Status text tokens pass AA on their own `-subtle` background.

### 3.3 Status color map (use exactly this everywhere)

Rendered by the `ui.status()` macro (9.9). Never pick a tone by hand.

| Entity | Value | Tone | Label shown |
|---|---|---|---|
| Job (`videos.status`) | `queued` | neutral | Queued |
| | `running` | accent | the stage name, for example "Transcribing" |
| | `ready` | warning | Needs review |
| | `done` | neutral | Done |
| | `failed` | danger | Failed |
| Clip | `rendering` | accent | Rendering |
| | `ready` | warning | Needs review |
| | `approved` | success | Approved |
| | `rejected` | neutral | Rejected |
| | `posted` | success | Posted |
| Post | `scheduled` | accent | Scheduled |
| | `uploading` | accent | Uploading |
| | `posted` | success | Posted |
| | `sent_to_inbox` | success | In TikTok inbox |
| | `failed` | danger | Failed |
| Outreach lead | `found`, `approved`, `rejected`, `sent`, `followup_1`, `followup_2`, `opted_out` | neutral | To review, Waiting for a slot, Rejected, Sent, Follow-up 1 sent, Follow-up 2 sent, Opted out |
| | `clip_queued`, `clip_approved`, queued email | accent | Clipping, Drafting email, Scheduled |
| | `needs_contact`, `clip_ready`, `email_ready` | warning | Needs contact, Clip needs review, Email needs review |
| | `clip_failed`, `bounced` | danger | Clip failed, Bounced |
| | `replied`, `trial`, `client` | success | Replied, Trial, Client |
| Source permission | `own`, `written`, `program` | neutral | Own channel, Written permission, Clipping program |
| | `none` | warning | Review only |
| Score (0 to 100) | 80 and up | success | the number |
| | 60 to 79 | neutral | the number |
| | below 60 | neutral, muted text | the number |

Stage names for `running`: Fetching, Downloading audio, Downloading chat,
Fetching clips, Transcribing, Analyzing, Finding moments, Downloading
sections, Rendering, Notifying, Posting.

---

## 4. Typography

### 4.1 Fonts

- **Geist** for all UI text. **Geist Mono** for code, IDs, file paths,
  timecodes, log lines, and error details. These are the Vercel fonts and
  the closest open alternative to Stripe's Sohne.
- Self-host the variable `.woff2` files in `static/fonts/`. Source: the
  `vercel/geist-font` GitHub releases or the `geist` npm package. License:
  SIL Open Font License (verify when downloading and keep the license file
  next to the fonts).
- No other fonts. No serif. No display fonts. No Google Fonts link.

```css
@font-face {
  font-family: "Geist";
  src: url("/static/fonts/Geist-Variable.woff2") format("woff2");
  font-weight: 100 900;
  font-display: swap;
}
@font-face {
  font-family: "Geist Mono";
  src: url("/static/fonts/GeistMono-Variable.woff2") format("woff2");
  font-weight: 100 900;
  font-display: swap;
}
```

Preload the sans font in `base.html`:
`<link rel="preload" href="/static/fonts/Geist-Variable.woff2" as="font" type="font/woff2" crossorigin>`

### 4.2 Scale

Eight sizes. Nothing else. Base size is 14px, as in the Vercel and Stripe
dashboards.

| Token | Size / line height | Weight | Letter spacing | Use |
|---|---|---|---|---|
| `--text-display` | 32 / 40 | 600 | -0.02em | Big numbers on the Stats page only |
| `--text-title` | 24 / 32 | 600 | -0.02em | Page title (`h1`), one per page |
| `--text-heading` | 16 / 24 | 600 | -0.01em | Section title (`h2`), dialog title |
| `--text-subheading` | 14 / 20 | 600 | 0 | Card title (`h3`), table group title |
| `--text-body` | 14 / 20 | 400 | 0 | Default text, inputs, buttons, table cells |
| `--text-small` | 13 / 18 | 400 | 0 | Descriptions, helper text, meta lines |
| `--text-caption` | 12 / 16 | 500 | 0 | Badges, table headers, kbd, chip on thumbnail |
| `--text-mono` | 13 / 20 | 400 | 0 | Geist Mono: timecodes, IDs, paths, logs |

### 4.3 Rules

- Weights: **400, 500, 600 only.** No 700, no 300.
  - 400 for running text.
  - 500 for buttons, nav items, labels, table headers, emphasized cells.
  - 600 for headings only.
- **Sentence case everywhere.** Page titles, buttons, labels, table
  headers, badges. Never Title Case. Never ALL CAPS.
- **No uppercase eyebrows** (small tracked labels above headings).
- **Numbers that change or line up** (scores, durations, counts, sizes,
  times) use `font-variant-numeric: tabular-nums` (class `.tabular`).
- Running text width max `65ch`. Descriptions under titles max `60ch`.
- Hierarchy comes from **weight and color**, not size. Most of the screen is
  14px. A label is 14/500 text, its description is 13/400 muted.
- Heading levels follow the page structure: one `h1` (page title), then
  `h2`, then `h3`. Do not pick a heading tag for its size.
- Text colors: primary text `--color-text`, supporting text
  `--color-text-muted`. Use `--color-text-subtle` sparingly (placeholders,
  timestamps, table headers).

---

## 5. Spacing and layout

### 5.1 Spacing scale (4px base)

| Token | Value | Typical use |
|---|---|---|
| `--space-1` | 4px | Icon to text in a badge, tight stacks |
| `--space-2` | 8px | Icon to text in a button, label to input, between buttons |
| `--space-3` | 12px | Inside compact components, list item gaps |
| `--space-4` | 16px | Card padding (compact), field to field, grid gaps |
| `--space-5` | 20px | Mobile page gutter is 16, this is rarely used |
| `--space-6` | 24px | Card padding (forms), page header bottom margin, desktop gutter |
| `--space-8` | 32px | Between sections on a page, page top padding |
| `--space-10` | 40px | Between major sections on long pages |
| `--space-12` | 48px | Empty state padding |
| `--space-16` | 64px | Rare. Top of auth or error pages |

**Only these values.** No 6px, 10px, 14px, 18px gaps in layout. Component
internals listed in Section 9 (for example button padding) are the only
exceptions, and they are already set.

### 5.2 Proximity rule

Space shows what belongs together. Inside a group the gap is small, between
groups it is at least twice as large.

- Label to its input: `--space-2` (8)
- Field to next field: `--space-4` (16)
- Group of fields to next group: `--space-8` (32), with an `h2`
- Page header to content: `--space-6` (24)
- Section to section: `--space-8` (32) or `--space-10` (40)

### 5.3 App shell

```
+------------+------------------------------------------------------+
| Spike      |                                                      |
|            |  Page title                          [Primary action]|
| Review   4 |  One line description                                |
| New        |                                                      |
| Sources    |  ---------------- page content ---------------------  |
| Jobs       |                                                      |
| Posts      |                                                      |
|            |                                                      |
| Settings   |                                                      |
|            |                                                      |
| (NH) nikko |                                                      |
+------------+------------------------------------------------------+
   240px                  fluid, content max width per page
```

- Sidebar: 240px fixed, full height, `--color-bg`, 1px right border.
- Main area: `--color-bg`. Padding `--space-8` top, `--space-6` sides,
  `--space-12` bottom.
- Content max width (centered in the main area, left aligned inside):
  - `--content-wide` 1440px: Review grid, Jobs, Posts, Sources list
  - `--content-default` 1120px: Clip detail, Stats
  - `--content-narrow` 640px: New, Source edit, all Settings pages

### 5.4 Breakpoints

CSS variables do not work inside media queries, so use these literal values
and no others.

| Name | Min width | What changes |
|---|---|---|
| base | 0 | Single column. Sidebar hidden, top bar 56px with menu button. Gutter 16px |
| `md` | 768px | Two column layouts allowed. Gutter 24px |
| `lg` | 1024px | Sidebar visible. Clip detail goes side by side |
| `xl` | 1280px | Review grid can show more columns (auto, from `minmax`) |

Under 1024px the sidebar becomes a top bar (wordmark left, menu button
right). The menu button opens the same nav as a full-height sheet from the
left (a native `<dialog>`, see 9.15).

### 5.5 Grids

- Use CSS Grid for page layouts. No percentage width math.
- Review grid: `grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: var(--space-6) var(--space-4);`
- Stats tiles: `repeat(auto-fit, minmax(220px, 1fr))`, gap `--space-4`.
- Form fields stack in one column. Two short fields (for example trim start
  and trim end) may sit side by side on `md` and up.

---

## 6. Shape, borders, elevation

### 6.1 Radius (one system, never mix)

| Token | Value | Use |
|---|---|---|
| `--radius-sm` | 4px | Badges, kbd, checkbox, skeleton lines, thumbnail chip |
| `--radius-md` | 6px | Buttons, inputs, selects, nav items, menu items, segmented control |
| `--radius-lg` | 8px | Cards, tables, menus, popovers, thumbnails, video player, toasts |
| `--radius-xl` | 12px | Dialogs only |
| `--radius-full` | 9999px | Avatar, switch track and thumb, spinner |

### 6.2 Borders

- Always `1px solid`. Never 2px except the focus ring.
- Cards and tables: `--color-border`.
- Inputs and secondary buttons: `--color-border-strong`.
- Divide content with **space first**, a border second. Tables use one
  border between rows (top border on each row after the first), never top
  and bottom.

### 6.3 Elevation

Spike is flat. Things in the page flow have **no shadow**, only a border.
Shadows exist only for things that float above the page.

| Token | Use |
|---|---|
| none | Cards, tables, inputs, buttons, sidebar |
| `--shadow-popover` | Menus, popovers, tooltips, toasts |
| `--shadow-dialog` | Dialogs, mobile nav sheet |

In dark mode shadows are nearly invisible, so floating elements also get a
1px `--color-border`. Shadows are neutral black at low opacity. Never
colored.

### 6.4 Z-index scale

| Token | Value | Use |
|---|---|---|
| `--z-sticky` | 10 | Sticky table header, sticky action bar |
| `--z-sidebar` | 20 | Sidebar, mobile top bar |
| `--z-popover` | 30 | Menus, tooltips |
| `--z-toast` | 40 | Toasts |

Dialogs use the native `<dialog>` top layer and need no z-index. Never write
a raw z-index number.

---

## 7. Icons

- **Library: Phosphor Icons, regular weight only.** MIT license (verify on
  download). Copy each SVG you need from the `phosphor-icons/core` repo
  (`assets/regular/`) into `static/icons/`. Do not draw or edit SVG paths by
  hand.
- Build the SVGs into one sprite (`static/icons/sprite.svg`, see Section 16)
  and render with the `ui.icon(name, size)` macro. It outputs an
  `<svg><use href="...#name"></use></svg>` with `aria-hidden="true"` and the
  size. Icons use `fill="currentColor"`.
- Sizes: **16px** default (buttons, nav, inputs, table actions). **14px** in
  small buttons and badges. **20px** in empty states. Nothing else.
- Color: always `currentColor`, so icons take the text color. Icons are
  never colored on their own, except inside a status badge or alert, where
  they take the status text color.
- Icons support a label. They do not replace it, except in icon buttons,
  which then need `aria-label` and a tooltip.
- **Do not put an icon in front of every heading, label, or list item.**

### Icon map (use these names, do not substitute)

| Meaning | Phosphor name |
|---|---|
| Review | `film-strip` |
| New | `plus` |
| Sources | `broadcast` |
| Jobs | `queue` |
| Posts | `paper-plane-tilt` |
| Outreach | `envelope-simple` |
| Stats | `chart-line` |
| Settings | `gear-six` |
| Approve | `check` |
| Reject | `x` |
| Download | `download-simple` |
| Copy | `copy` |
| Re-render | `arrow-clockwise` |
| Retry | `arrow-clockwise` |
| Cancel job | `stop` |
| Edit | `pencil-simple` |
| Delete | `trash` |
| More actions | `dots-three` |
| Menu (mobile) | `list` |
| Close | `x` |
| External link | `arrow-up-right` |
| Play / pause | `play` / `pause` |
| Upload | `upload-simple` |
| Link / URL | `link-simple` |
| Search | `magnifying-glass` |
| Schedule | `calendar-blank` |
| Info | `info` |
| Warning | `warning` |
| Error | `warning-circle` |
| Success | `check-circle` |
| Chevrons | `caret-down`, `caret-right`, `caret-left` |
| Theme | `sun`, `moon` |
| Sign out | `sign-out` |

---

## 8. Motion

Motion only shows that something changed or responded. No decorative
animation, no page transitions, no entrance animations on load, no
infinite loops (except the spinner and skeleton pulse).

| Token | Value | Use |
|---|---|---|
| `--duration-fast` | 120ms | Color, background, border changes on hover |
| `--duration-base` | 200ms | Menus, tooltips, toasts, dialogs appearing |
| `--ease-out` | `cubic-bezier(0.16, 1, 0.3, 1)` | Everything that enters |
| `--ease-in-out` | `cubic-bezier(0.4, 0, 0.2, 1)` | Everything else |

Rules:

- Animate only `opacity`, `transform`, `background-color`, `border-color`,
  `color`. Never width, height, top, left.
- Enter: fade from `opacity: 0` and `translateY(4px)` (menus, toasts) or
  `scale(0.98)` (dialogs). Exit: fade only, `--duration-fast`.
- Buttons: no scale or lift on press. Only the background changes.
- htmx swaps: no animation. Content just replaces.
- `prefers-reduced-motion: reduce` sets every duration to `0.01ms` and stops
  the skeleton pulse (already in `base.css`, Section 16).

---

## 9. Components

Every component has a CSS block in `components.css` and a macro in
`macros/ui.html`. The CSS below is the reference implementation. Copy it.

### 9.1 App shell (`base.html`)

```html
<!doctype html>
<html lang="en" data-theme="{{ theme or 'dark' }}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{{ page_title }} | Spike</title>
  <link rel="preload" href="/static/fonts/Geist-Variable.woff2" as="font" type="font/woff2" crossorigin>
  <link rel="stylesheet" href="/static/css/tokens.css">
  <link rel="stylesheet" href="/static/css/base.css">
  <link rel="stylesheet" href="/static/css/components.css">
  <script src="/static/js/htmx.min.js" defer></script>
  <script src="/static/js/app.js" defer></script>
</head>
<body>
  <a class="skip-link" href="#main">Skip to content</a>
  <div class="shell">
    {% include "partials/sidebar.html" %}
    <main id="main" class="shell__main">
      <div class="page page--{{ page_width or 'wide' }}">
        {% block content %}{% endblock %}
      </div>
    </main>
  </div>
  <div class="toast-region" aria-live="polite" aria-atomic="false"></div>
</body>
</html>
```

The theme comes from a cookie and is rendered on the server into
`data-theme`. This avoids a flash of the wrong theme and needs no inline
script. The theme menu item posts to `/settings/theme` and reloads.

```css
.shell { display: grid; grid-template-columns: 1fr; min-height: 100dvh; }
.shell__main { min-width: 0; padding: var(--space-6) var(--space-4) var(--space-12); }
.page { margin-inline: auto; width: 100%; }
.page--wide { max-width: var(--content-wide); }
.page--default { max-width: var(--content-default); }
.page--narrow { max-width: var(--content-narrow); }

@media (min-width: 768px) {
  .shell__main { padding: var(--space-8) var(--space-6) var(--space-12); }
}
@media (min-width: 1024px) {
  .shell { grid-template-columns: var(--sidebar-width) 1fr; }
}
```

### 9.2 Sidebar and nav

- Wordmark at top: the text "Spike", `--text-heading`, weight 600. No logo
  graphic, no icon.
- Nav items in this order: Review, New, Sources, Jobs, Posts, Stats. Then a
  flexible gap, then Settings (admins only). Then the user row.
- Review shows a count of clips waiting for review, right aligned, as plain
  `--text-caption` muted tabular text. Not a colored bubble.
- User row: 24px avatar circle with initials (`--color-surface-active`
  background, `--text-caption`), then the login, truncated. Clicking opens a
  menu: Theme (Dark, Light), Sign out (if fallback auth is used).

```css
.sidebar {
  display: none;
  position: sticky; top: 0; height: 100dvh;
  flex-direction: column; gap: var(--space-1);
  padding: var(--space-4) var(--space-3);
  border-right: 1px solid var(--color-border);
  background: var(--color-bg);
  z-index: var(--z-sidebar);
}
@media (min-width: 1024px) { .sidebar { display: flex; } }

.sidebar__brand { font-size: 16px; line-height: 24px; font-weight: 600; letter-spacing: -0.01em; padding: var(--space-1) var(--space-2) var(--space-4); }
.sidebar__spacer { flex: 1; }

.nav-item {
  display: flex; align-items: center; gap: var(--space-2);
  height: 32px; padding: 0 var(--space-2);
  border-radius: var(--radius-md);
  color: var(--color-text-muted); font-weight: 500; text-decoration: none;
  transition: background-color var(--duration-fast) var(--ease-in-out), color var(--duration-fast) var(--ease-in-out);
}
.nav-item:hover { background: var(--color-surface-hover); color: var(--color-text); }
.nav-item.is-active { background: var(--color-surface-active); color: var(--color-text); }
.nav-item__count { margin-left: auto; font-size: 12px; color: var(--color-text-muted); font-variant-numeric: tabular-nums; }
```

Mark the current page with `class="nav-item is-active"` and
`aria-current="page"`.

Mobile top bar (under 1024px): 56px high, `--color-bg`, bottom border,
wordmark left, icon button (`list`) right with `aria-label="Open menu"`.

### 9.3 Page header

Every page starts with exactly this.

```
Page title                                    [Secondary] [Primary]
Optional one line description, muted, max 60ch
```

```html
{{ ui.page_header("Sources", description="Streamers and channels Spike watches for new videos.", actions=[ui.button("Add source", variant="primary", icon="plus", href="/sources/new")]) }}
```

```css
.page-header { display: flex; flex-wrap: wrap; align-items: flex-start; justify-content: space-between; gap: var(--space-4); margin-bottom: var(--space-6); }
.page-header__title { font-size: var(--text-title-size); line-height: var(--text-title-lh); font-weight: 600; letter-spacing: -0.02em; }
.page-header__description { margin-top: var(--space-1); color: var(--color-text-muted); max-width: 60ch; }
.page-header__actions { display: flex; gap: var(--space-2); }
```

- Detail pages add a back link above the title: `caret-left` icon + parent
  page name, `--text-small`, muted, hover text color. Not a full breadcrumb.
- Actions on the right: at most one primary and one secondary. More actions
  go into a "More" menu (`dots-three` icon button).

### 9.4 Buttons

| Variant | Look | Use |
|---|---|---|
| `primary` | `--color-primary` background, `--color-text-inverse` text | The one main action of the page. Max one per page (one per dialog) |
| `secondary` | `--color-surface` background, `--color-border-strong` border, text color | All other actions |
| `ghost` | Transparent, muted text, hover surface | Low-priority actions, table row actions, toolbar actions |
| `danger` | `--color-danger` background, white text | Only the confirm button inside a delete or reject dialog |

| Size | Height | Padding X | Font | Icon | Use |
|---|---|---|---|---|---|
| `sm` | 28px | 10px | 13px / 500 | 14px | Table rows, toolbars, dense areas |
| `md` | 32px | 12px | 14px / 500 | 16px | Default everywhere |
| `lg` | 40px | 16px | 14px / 500 | 16px | Only the submit button on the New page |

```css
.btn {
  display: inline-flex; align-items: center; justify-content: center; gap: var(--space-2);
  height: 32px; padding: 0 12px;
  border: 1px solid transparent; border-radius: var(--radius-md);
  font: inherit; font-size: 14px; line-height: 20px; font-weight: 500;
  white-space: nowrap; text-decoration: none; cursor: pointer;
  transition: background-color var(--duration-fast) var(--ease-in-out), border-color var(--duration-fast) var(--ease-in-out), color var(--duration-fast) var(--ease-in-out);
}
.btn svg { width: 16px; height: 16px; flex: none; }
.btn--sm { height: 28px; padding: 0 10px; font-size: 13px; gap: 6px; }
.btn--sm svg { width: 14px; height: 14px; }
.btn--lg { height: 40px; padding: 0 16px; }

.btn--primary { background: var(--color-primary); color: var(--color-text-inverse); }
.btn--primary:hover { background: var(--color-primary-hover); }
.btn--secondary { background: var(--color-surface); border-color: var(--color-border-strong); color: var(--color-text); }
.btn--secondary:hover { background: var(--color-surface-hover); border-color: var(--color-border-hover); }
.btn--ghost { background: transparent; color: var(--color-text-muted); }
.btn--ghost:hover { background: var(--color-surface-hover); color: var(--color-text); }
.btn--danger { background: var(--color-danger); color: #fff; }
.btn--danger:hover { background: var(--color-danger-hover); }

.btn--icon { width: 32px; padding: 0; }
.btn--icon.btn--sm { width: 28px; }

.btn:disabled, .btn[aria-disabled="true"] { opacity: 0.5; cursor: not-allowed; pointer-events: none; }

.btn.is-loading { position: relative; color: transparent; pointer-events: none; }
.btn.is-loading::after {
  content: ""; position: absolute; width: 14px; height: 14px;
  border: 2px solid currentColor; border-right-color: transparent; border-radius: var(--radius-full);
  color: var(--color-text); animation: spin 0.6s linear infinite;
}
.btn--primary.is-loading::after { color: var(--color-text-inverse); }
.btn--danger.is-loading::after { color: #fff; }
```

Rules:

- Labels are a **verb + noun**, 1 to 3 words: "Approve clip", "Start job",
  "Add source", "Save changes", "Retry". Never "Submit", "OK", "Click here".
- Same intent, same label, everywhere in the app (see 12.3).
- Label never wraps. If it does not fit, shorten it.
- Leading icon only when it helps scanning (Download, Copy, Add). Never a
  trailing arrow.
- Icon-only buttons (`btn--icon`) always have `aria-label` and a tooltip.
- For htmx requests, add `.is-loading` while the request runs
  (`hx-indicator` or the `htmx:beforeRequest` hook in `app.js`). The button
  keeps its width.
- Disabled buttons must also say why nearby (helper text or tooltip).
- Button groups: gap `--space-2`. Order in a row: secondary left, primary
  right. In dialogs: Cancel, then the action.

Macro signature:

```jinja
{% macro button(label, variant="secondary", size="md", icon=None, href=None, type="button", icon_only=False, attrs={}) %}
```

`href` renders an `<a class="btn ...">`, otherwise a `<button>`.
`icon_only=True` renders the icon with `aria-label=label` and
`data-tooltip=label`.

### 9.5 Form fields

Anatomy, top to bottom, gap `--space-2`:

1. Label: 14px / 500, `--color-text`. Optional marker: " (optional)" in
   muted text. Never mark required fields with a red star. Most fields are
   required.
2. Control.
3. Helper text: 13px, `--color-text-muted`. Optional.
4. Error text: 13px, `--color-danger-text`, with `warning-circle` 14px
   icon. Replaces the helper text while shown.

```css
.field { display: flex; flex-direction: column; gap: var(--space-2); }
.field + .field { margin-top: var(--space-4); }
.field__label { font-weight: 500; }
.field__optional { color: var(--color-text-muted); font-weight: 400; }
.field__help { font-size: 13px; line-height: 18px; color: var(--color-text-muted); }
.field__error { display: flex; gap: var(--space-1); align-items: center; font-size: 13px; line-height: 18px; color: var(--color-danger-text); }

.input, .select, .textarea {
  width: 100%; height: 32px; padding: 0 10px;
  background: var(--color-surface); color: var(--color-text);
  border: 1px solid var(--color-border-strong); border-radius: var(--radius-md);
  font: inherit; font-size: 14px; line-height: 20px;
  transition: border-color var(--duration-fast) var(--ease-in-out);
}
.input::placeholder, .textarea::placeholder { color: var(--color-text-subtle); }
.input:hover, .select:hover, .textarea:hover { border-color: var(--color-border-hover); }
.input[aria-invalid="true"], .select[aria-invalid="true"], .textarea[aria-invalid="true"] { border-color: var(--color-danger-text); }
.input:disabled, .select:disabled, .textarea:disabled { background: var(--color-bg-subtle); color: var(--color-text-disabled); cursor: not-allowed; }
.textarea { height: auto; min-height: 80px; padding: 6px 10px; resize: vertical; }
.select { appearance: none; padding-right: 32px; background-image: var(--select-caret); background-repeat: no-repeat; background-position: right 10px center; background-size: 16px; }
.input--mono { font-family: var(--font-mono); font-size: 13px; }
.input--number { font-variant-numeric: tabular-nums; }
```

`--select-caret` is a `caret-down` SVG as a data URI, defined once per theme
in `tokens.css` (one for each text-muted color).

Rules:

- **Label above the control, always.** No placeholder-as-label. No floating
  labels. Placeholders show an example format only ("https://twitch.tv/videos/...").
- Every control has an `id` and its label has a matching `for`. Helper and
  error text are linked with `aria-describedby`.
- Inline validation runs on submit and on blur, not on every keystroke.
- On a failed submit: keep every value the user typed, show each field's
  error under it, and focus the first invalid field.
- Field widths follow the expected content: number fields 120px
  (`.input--short`), URLs and text full width.
- Form actions sit at the end of the form, right aligned, in the card
  footer (9.7). Never at the top.
- Checkboxes and radios: native inputs with `accent-color: var(--color-accent)`,
  16px, label to the right with gap `--space-2`.

### 9.6 Switch, segmented control, tabs

**Switch** (on/off settings that apply right away or on save, for example
"Auto-process new VODs", "Music"). It is a native checkbox with
`role="switch"`.

```css
.switch { appearance: none; position: relative; width: 32px; height: 20px; border-radius: var(--radius-full); background: var(--color-surface-active); border: 1px solid var(--color-border-strong); cursor: pointer; transition: background-color var(--duration-fast) var(--ease-in-out); }
.switch::after { content: ""; position: absolute; top: 2px; left: 2px; width: 14px; height: 14px; border-radius: var(--radius-full); background: var(--color-text-muted); transition: transform var(--duration-fast) var(--ease-in-out), background-color var(--duration-fast) var(--ease-in-out); }
.switch:checked { background: var(--color-accent); border-color: var(--color-accent); }
.switch:checked::after { transform: translateX(12px); background: #fff; }
```

**Segmented control** (pick one of 2 to 4 short options, for example layout
`face_track / split / center / letterbox`, caption style). Built from a
`<fieldset>` of radio inputs styled as joined buttons.

```css
.segmented { display: inline-flex; padding: 2px; gap: 2px; background: var(--color-bg-subtle); border: 1px solid var(--color-border); border-radius: var(--radius-md); }
.segmented input { position: absolute; opacity: 0; pointer-events: none; }
.segmented label { height: 26px; padding: 0 10px; display: inline-flex; align-items: center; border-radius: 4px; font-size: 13px; font-weight: 500; color: var(--color-text-muted); cursor: pointer; }
.segmented label:hover { color: var(--color-text); }
.segmented input:checked + label { background: var(--color-surface); color: var(--color-text); box-shadow: 0 0 0 1px var(--color-border-strong); }
.segmented input:focus-visible + label { outline: 2px solid var(--color-focus); outline-offset: 1px; }
```

More than 4 options: use a `<select>`.

**Tabs** (switch between views of the same page, for example New: Upload,
URL, Streamer). Tabs are links with `?tab=` query, rendered on the server.
Underline style.

```css
.tabs { display: flex; gap: var(--space-4); border-bottom: 1px solid var(--color-border); margin-bottom: var(--space-6); }
.tab { position: relative; padding: var(--space-2) 0 var(--space-3); color: var(--color-text-muted); font-weight: 500; text-decoration: none; }
.tab:hover { color: var(--color-text); }
.tab.is-active { color: var(--color-text); }
.tab.is-active::after { content: ""; position: absolute; left: 0; right: 0; bottom: -1px; height: 2px; background: var(--color-text); }
```

The active tab underline is the text color, not the accent.

### 9.7 Card

A card groups one form or one table. **Never nest cards.** Never put a card
around a single line of text.

```css
.card { background: var(--color-surface); border: 1px solid var(--color-border); border-radius: var(--radius-lg); }
.card__header { padding: var(--space-6) var(--space-6) 0; }
.card__title { font-size: 16px; line-height: 24px; font-weight: 600; letter-spacing: -0.01em; }
.card__description { margin-top: var(--space-1); color: var(--color-text-muted); font-size: 13px; line-height: 18px; max-width: 60ch; }
.card__body { padding: var(--space-6); }
.card__footer { display: flex; align-items: center; justify-content: space-between; gap: var(--space-4); padding: var(--space-3) var(--space-6); background: var(--color-bg-subtle); border-top: 1px solid var(--color-border); border-radius: 0 0 var(--radius-lg) var(--radius-lg); }
.card__footer-note { color: var(--color-text-muted); font-size: 13px; }
.card__footer .btn:last-child { margin-left: auto; }
.card--compact .card__header { padding: var(--space-4) var(--space-4) 0; }
.card--compact .card__body { padding: var(--space-4); }
```

The settings pattern (Vercel style): one card per setting group. Title,
description, fields in the body, footer with an optional note on the left
("Changes apply to new jobs.") and the Save button on the right.

### 9.8 Table

The main way to list things (Sources, Jobs, Posts, Users, Accounts).

```css
.table-wrap { border: 1px solid var(--color-border); border-radius: var(--radius-lg); overflow-x: auto; background: var(--color-surface); }
.table { width: 100%; border-collapse: collapse; font-size: 14px; }
.table th { height: 36px; padding: 0 var(--space-4); text-align: left; font-size: 12px; font-weight: 500; color: var(--color-text-subtle); background: var(--color-bg-subtle); white-space: nowrap; border-bottom: 1px solid var(--color-border); }
.table td { height: 44px; padding: var(--space-2) var(--space-4); vertical-align: middle; }
.table tbody tr + tr td { border-top: 1px solid var(--color-border); }
.table tbody tr.is-link { cursor: pointer; }
.table tbody tr.is-link:hover td { background: var(--color-surface-hover); }
.table .num { text-align: right; font-variant-numeric: tabular-nums; }
.table .actions { width: 1%; white-space: nowrap; text-align: right; }
.table .primary-cell { font-weight: 500; color: var(--color-text); }
.table .secondary-line { display: block; font-size: 13px; color: var(--color-text-muted); }
```

Rules:

- Column order: name/title first (500 weight, links to detail), then
  status badge, then numbers (right aligned, tabular), then time, then
  actions last.
- Header text is sentence case, never uppercase.
- A row may have a second line (`.secondary-line`) for one piece of muted
  context. Never three lines.
- Row actions: up to 2 visible `ghost sm` buttons, everything else in a
  `dots-three` menu. Destructive actions always go in the menu.
- If the whole row opens a detail page, make the name cell a real `<a>` and
  add `.is-link` to the row (`app.js` forwards row clicks to that link).
- Long text truncates with ellipsis and has a `title` attribute with the
  full value.
- More than 50 rows: paginate (9.17). Never infinite scroll.
- Times show relative ("12 min ago") with the full local time in `title`.

### 9.9 Badge and status

```css
.badge { display: inline-flex; align-items: center; gap: var(--space-1); height: 20px; padding: 0 6px; border-radius: var(--radius-sm); font-size: 12px; line-height: 16px; font-weight: 500; white-space: nowrap; background: var(--color-surface-active); color: var(--color-text-muted); }
.badge svg { width: 12px; height: 12px; }
.badge--accent { background: var(--color-accent-subtle); color: var(--color-accent-text); }
.badge--success { background: var(--color-success-subtle); color: var(--color-success-text); }
.badge--warning { background: var(--color-warning-subtle); color: var(--color-warning-text); }
.badge--danger { background: var(--color-danger-subtle); color: var(--color-danger-text); }
.badge--score { font-variant-numeric: tabular-nums; min-width: 28px; justify-content: center; }
.badge--muted { color: var(--color-text-subtle); }
```

- `ui.status(entity, value)` maps a status to tone and label using the
  table in 3.3. Templates never call `ui.badge` with a tone for a status.
- Running statuses (`accent` tone, job running, clip rendering, post
  uploading) show a 10px spinner before the label. No other badge has an
  icon or dot.
- `ui.score(n)` renders the score badge with the band tone from 3.3.

### 9.10 Clip card (Review grid)

```
+------------------+
|                  |
|   9:16 thumb     |
|                  |
|           0:32   |   <- duration chip, bottom right
+------------------+
He did not expect that jump        <- title, 14/500, max 2 lines
[86]  xQc  ·  2 h ago             <- score badge, source, time
```

```css
.clip-card { display: flex; flex-direction: column; gap: var(--space-2); text-decoration: none; color: inherit; }
.clip-card__media { position: relative; aspect-ratio: 9 / 16; background: var(--color-media-bg); border-radius: var(--radius-lg); overflow: hidden; outline: 1px solid var(--color-border); outline-offset: -1px; }
.clip-card__media img, .clip-card__media video { width: 100%; height: 100%; object-fit: cover; display: block; }
.clip-card__media video { position: absolute; inset: 0; opacity: 0; transition: opacity var(--duration-fast) var(--ease-in-out); }
.clip-card:hover .clip-card__media video, .clip-card:focus-visible .clip-card__media video { opacity: 1; }
.clip-card:hover .clip-card__media { outline-color: var(--color-border-hover); }
.clip-card__duration { position: absolute; right: var(--space-2); bottom: var(--space-2); padding: 2px 6px; border-radius: var(--radius-sm); background: rgb(0 0 0 / 0.72); color: #fff; font-family: var(--font-mono); font-size: 12px; line-height: 16px; }
.clip-card__title { font-weight: 500; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
.clip-card__meta { display: flex; align-items: center; gap: var(--space-2); font-size: 13px; color: var(--color-text-muted); min-width: 0; }
```

- The whole card is one link to the clip detail page.
- Hover or keyboard focus: the muted preview `<video preload="none">` loads
  and plays (`app.js` sets `src` on first hover). Pauses on leave.
- The thumbnail never has text, badges, or overlays on it except the
  duration chip.
- Titles are untrusted LLM text: always autoescaped, never `|safe`.

### 9.11 Video player (Clip detail)

- 9:16 frame, `--color-media-bg`, `--radius-lg`, width 360px on `lg` and
  up, full width (max 360px, centered) below.
- Native `<video controls>`. Do not build custom controls.
- Below the player, one row of `ghost sm` buttons: Download, Copy caption.

### 9.12 Inline alert

For persistent messages about this page (job failed, account token expired,
source is review-only). Not for transient success (use a toast).

```css
.alert { display: flex; gap: var(--space-3); padding: var(--space-3) var(--space-4); border: 1px solid var(--color-border); border-radius: var(--radius-lg); background: var(--color-surface); font-size: 14px; }
.alert svg { width: 16px; height: 16px; flex: none; margin-top: 2px; }
.alert__title { font-weight: 500; }
.alert__body { color: var(--color-text-muted); }
.alert--warning svg { color: var(--color-warning-text); }
.alert--danger svg { color: var(--color-danger-text); }
.alert--info svg { color: var(--color-accent-text); }
```

The alert box stays neutral. Only the icon is colored. Max one alert per
page section. Text: what happened, then what to do (12.4).

### 9.13 Toast

Confirms an action that just finished ("Clip approved", "Caption copied").

- Region: fixed bottom right, `--space-6` from edges (bottom center on
  mobile), width 360px, stack gap `--space-2`, max 3 visible.
- Look: `--color-surface`, 1px `--color-border`, `--radius-lg`,
  `--shadow-popover`, padding `--space-3` `--space-4`, 14px text.
- Auto-dismiss after 5s. Pauses on hover. Close button (`x`, icon button sm).
- May contain one text action ("Undo"), styled as a link.
- Errors that need the user to act are **not** toasts. Show them inline.
- Triggered from the server with an `HX-Trigger: {"toast": {"message": "..."}}`
  response header. `app.js` renders it with `textContent`, never
  `innerHTML`.

### 9.14 Menu (dropdown)

Use the native `popover` attribute with a trigger button
(`popovertarget`). Items are buttons or links.

```css
.menu { min-width: 180px; padding: var(--space-1); background: var(--color-surface); border: 1px solid var(--color-border); border-radius: var(--radius-lg); box-shadow: var(--shadow-popover); }
.menu__item { display: flex; align-items: center; gap: var(--space-2); width: 100%; height: 32px; padding: 0 var(--space-2); border: 0; border-radius: var(--radius-md); background: none; color: var(--color-text); font: inherit; text-align: left; text-decoration: none; cursor: pointer; }
.menu__item:hover, .menu__item:focus-visible { background: var(--color-surface-hover); outline: none; }
.menu__item svg { width: 16px; height: 16px; color: var(--color-text-muted); }
.menu__item--danger, .menu__item--danger svg { color: var(--color-danger-text); }
.menu__separator { height: 1px; margin: var(--space-1) 0; background: var(--color-border); }
```

Destructive items go last, after a separator, in danger color. Position the
menu under its trigger, right aligned, 4px gap (`app.js`, or CSS anchor
positioning where the browser supports it).

### 9.15 Dialog

Native `<dialog>` opened with `showModal()`. Used for: confirming a
destructive action, reject reason, schedule post, mobile nav.

```css
.dialog { width: min(440px, calc(100vw - 32px)); padding: 0; border: 1px solid var(--color-border); border-radius: var(--radius-xl); background: var(--color-surface); color: var(--color-text); box-shadow: var(--shadow-dialog); }
.dialog--md { width: min(560px, calc(100vw - 32px)); }
.dialog::backdrop { background: var(--color-overlay); }
.dialog__body { padding: var(--space-6); }
.dialog__title { font-size: 16px; line-height: 24px; font-weight: 600; }
.dialog__text { margin-top: var(--space-2); color: var(--color-text-muted); }
.dialog__footer { display: flex; justify-content: flex-end; gap: var(--space-2); padding: var(--space-4) var(--space-6); background: var(--color-bg-subtle); border-top: 1px solid var(--color-border); border-radius: 0 0 var(--radius-xl) var(--radius-xl); }
```

Rules:

- Title is the question or action: "Delete source?", "Reject clip".
- Body says what will happen, with the object name in 500 weight.
- Footer: Cancel (secondary) then the action (primary, or danger if
  destructive). The action label repeats the verb: "Delete source", not
  "Yes" or "Confirm".
- Escape and backdrop click close it. Focus goes to the first field, or to
  Cancel for destructive dialogs. Focus returns to the trigger on close.
- Never open a dialog from inside a dialog.

### 9.16 Tooltip

Only for icon-only buttons and truncated text. CSS only, from
`data-tooltip`.

```css
[data-tooltip] { position: relative; }
[data-tooltip]:hover::after, [data-tooltip]:focus-visible::after {
  content: attr(data-tooltip); position: absolute; bottom: calc(100% + 6px); left: 50%; transform: translateX(-50%);
  padding: 4px 8px; border-radius: var(--radius-md); background: var(--color-primary); color: var(--color-text-inverse);
  font-size: 12px; line-height: 16px; font-weight: 500; white-space: nowrap; pointer-events: none; z-index: var(--z-popover);
}
```

Tooltip text is a label ("More actions"), not a sentence. Include the
shortcut if one exists: "Approve (A)".

### 9.17 Pagination

Below tables, right aligned: "1 to 50 of 214" muted text on the left,
Previous / Next `secondary sm` buttons on the right. No numbered pages.

### 9.18 Keyboard hint (kbd)

```css
.kbd { display: inline-flex; align-items: center; justify-content: center; min-width: 20px; height: 20px; padding: 0 4px; border: 1px solid var(--color-border-strong); border-bottom-width: 2px; border-radius: var(--radius-sm); font-family: var(--font-mono); font-size: 12px; color: var(--color-text-muted); background: var(--color-bg-subtle); }
```

Shown in tooltips, in the shortcuts dialog (`?` key), and in a single muted
hint line at the bottom of the clip detail page. Never inside buttons.

### 9.19 Progress and meter

- Disk usage (Jobs page): native `<meter>` styled as a 6px bar,
  `--radius-full`, track `--color-surface-active`, fill `--color-text`
  normally, `--color-warning-text` above 80%, `--color-danger-text` above
  90%. Label above it: "412 GB of 1 TB used" (tabular).
- Job progress: no bar. Show the stage badge and "Stage 5 of 11" muted
  text. Stage durations are unknown, so a bar would lie.

### 9.20 Spinner

14px circle, 2px border, one transparent side, 0.6s linear spin. Only inside
buttons, running badges (10px), and next to "Rendering" text. **Never as a
page or section loader.** Use skeletons for that.

### 9.21 Skeleton

```css
.skeleton { background: var(--color-surface-active); border-radius: var(--radius-sm); animation: pulse 1.6s var(--ease-in-out) infinite; }
.skeleton--text { height: 12px; }
.skeleton--media { aspect-ratio: 9 / 16; border-radius: var(--radius-lg); }
```

Skeletons copy the shape of the real content (same grid, same row height,
same widths roughly). Show them only if loading takes over 300ms.

### 9.22 Empty state

```
            [ icon in 40px bordered square ]
            No clips to review
            New clips show up here when a job finishes.
            [ Submit a video ]
```

```css
.empty { display: flex; flex-direction: column; align-items: center; text-align: center; gap: var(--space-2); padding: var(--space-12) var(--space-6); border: 1px dashed var(--color-border-strong); border-radius: var(--radius-lg); }
.empty__icon { display: grid; place-items: center; width: 40px; height: 40px; margin-bottom: var(--space-2); border: 1px solid var(--color-border); border-radius: var(--radius-lg); background: var(--color-surface); color: var(--color-text-muted); }
.empty__icon svg { width: 20px; height: 20px; }
.empty__title { font-weight: 600; }
.empty__text { color: var(--color-text-muted); max-width: 40ch; }
.empty .btn { margin-top: var(--space-2); }
```

Title says what is missing. Text says how to fill it. One button, which is
the page's primary action, so the page header hides its own primary
button while the empty state shows.

### 9.23 Description list (key/value)

For read-only details: clip signal breakdown, job metadata, source summary.

```css
.dl { display: grid; grid-template-columns: max-content 1fr; gap: var(--space-2) var(--space-6); font-size: 14px; }
.dl dt { color: var(--color-text-muted); }
.dl dd { margin: 0; font-variant-numeric: tabular-nums; }
```

### 9.24 Stat tile (Stats page)

Inside a compact card: label (13px muted), value (`--text-display`,
tabular), optional change line (13px, muted; success or danger text color
only for the arrow and number). No icons, no sparkline backgrounds.

### 9.25 Charts (Stats page, Phase 7)

- Load the `dataviz` skill before writing chart code.
- One series: `--color-text` line or bars. Comparison series: accent plus
  muted grey. No rainbow palettes.
- Gridlines: horizontal only, `--color-border`. Axis labels 12px subtle.
- Every chart has a title (`h2`) and a one-line description of what to look
  for. Values on hover via `title` or a small tooltip.

---

## 10. Page recipes

Each page lists its single job, its one primary action, and its layout. Do
not add sections not listed here without updating this file.

### 10.1 Review (home, `/`)

- **Job:** pick the next clip to review.
- **Primary action:** none in the header. Each card is the action.
- **Width:** wide.

```
Review                                            [Filter: All sources v]
12 clips need review

Job: xQc, Sep 30 stream                    6 clips   3 h 12 min source
[card] [card] [card] [card] [card] [card]

Job: Podcast ep. 41                        4 clips
[card] [card] [card] [card]
```

- Grouped by job, newest job first. Each group: `h2` with source and video
  title (16/600), right side muted meta. Gap between groups `--space-10`.
- Inside a group, sorted by score, highest first.
- Filter is one `select` in the header actions (source). No other filters.
- Empty state: "No clips to review" / "New clips show up here when a job
  finishes." / button "Submit a video" (links to New).

### 10.2 Clip detail (`/clips/<id>`)

- **Job:** decide on one clip: approve or reject it, after optional edits.
- **Primary action:** Approve clip (`a`). Secondary: Reject (`r`), opens the
  reject dialog. Post and schedule are on the Post page (10.3), shown as a
  link after approval.
- **Width:** default.

```
< Review
He did not expect that jump        [86] Needs review   [Reject] [Approve clip]
xQc, Sep 30 stream, at 1:02:03

+-----------+   Why this clip
|           |   Setup, fail, and chat eruption all in 28 s.
|  player   |   Score  86   Chat rate  +3.1   Hype  +2.4   Loudness  +1.2
|   9:16    |
|           |   Trim
|           |   Start [ 1:02:03.4 ] [-0.5] [+0.5]   End [ 1:02:31.9 ] [-0.5] [+0.5]
+-----------+
[Download] [Copy caption]   Layout     ( Face | Split | Center | Letterbox )
                            Captions   ( Bold pop | Clean | Karaoke )
                            Music      [switch]
                            Caption text  [Edit captions]

                            [Re-render]   Renders in about a minute.

j / k next and previous, space play, a approve, r reject, e edit captions, ? all shortcuts
```

- Two columns on `lg` and up (player 360px, inspector 1fr, gap
  `--space-8`). Stacked below `lg`, player first.
- Inspector sections, each with an `h2` 16/600, separated by
  `--space-8`: Why this clip (reason + `.dl` of signals), Trim, Look
  (layout, captions, music), Caption text.
- Re-render is a `secondary` button at the end of the inspector, because
  approving is the page's main job. While rendering, the player shows a
  skeleton with "Rendering" and a spinner, and Approve is disabled with the
  reason in its tooltip.
- After approve: toast "Clip approved", then go to the next clip in the job
  (or back to Review if none).
- Timecodes in Geist Mono. Trim inputs are `.input--mono` 120px wide.

### 10.3 Post clip (`/clips/<id>/post`)

- **Job:** send one approved clip to platforms.
- **Primary action:** Post now, or Schedule post when a time is picked
  (same button, label changes).
- **Width:** narrow. One card: account checkboxes (disabled with reason if
  permission is `none` or token expired), caption textarea prefilled,
  hashtags, time (Now / next slot / custom `datetime-local`).
- If the source is `permission = none`, the page shows a warning alert and
  no form.

### 10.4 New (`/new`)

- **Job:** start one job.
- **Primary action:** Start job (`lg` size, at the end of the form).
- **Width:** narrow.
- Tabs: Upload file, Paste URL, From a streamer.
  - Upload: a drop zone (dashed `--color-border-strong`, `--radius-lg`,
    160px high, `upload-simple` icon 20px, "Drop a video or browse", muted
    line with the size limit and allowed types). After choosing: file name,
    size, and a Remove ghost button replace the drop zone.
  - URL: one input, helper text "Twitch and YouTube links only."
  - Streamer: source select, then a select of recent VODs (title, date,
    length).
- "Options" section below, collapsed in a `<details>` (summary 14/500 with
  `caret-right` that rotates): clip count, length range, layout.
- After submit: redirect to the job's row on Jobs with toast "Job queued".

### 10.5 Sources (`/sources`)

- **Job:** see which sources Spike watches.
- **Primary action:** Add source.
- **Width:** wide. Table columns: Name (with platform as second line),
  Permission (status badge), Auto-process (On/Off text, not a switch: edit
  happens on the detail page), Last VOD (relative time), Clips (num), More
  menu (Edit, Delete).

### 10.6 Source edit (`/sources/<id>`, `/sources/new`)

- **Job:** configure one source.
- **Primary action:** Save changes (Create source on new).
- **Width:** narrow. One form, sections with `h2`: Source (platform, id,
  name), Permission (select + note textarea, warning alert when `none`),
  Processing (auto-process switch, language, style notes), Look (layout,
  facecam box, caption style, caption position, music), Advanced in a
  `<details>` (chat offset, hype emotes).
- Facecam box editor: the frame grab image inside a `--radius-lg` frame
  with a 1px `--color-accent` rectangle the user drags. Handles are 8px
  squares, `--color-accent` fill.
- One Save button in a sticky bottom action bar (`--color-bg`, top border,
  `--z-sticky`), right aligned, with "Unsaved changes" muted text on the
  left when the form is dirty.
- Delete source lives in the Sources table menu, not on this page.

### 10.7 Jobs (`/jobs`)

- **Job:** watch progress and fix failures.
- **Primary action:** none (monitoring page). Row actions: Retry (failed),
  Cancel (queued or running, in menu).
- **Width:** wide.
- Top: disk usage meter (9.19) in a compact card, max width 360px.
- Table columns: Video (title + source second line), Status (badge, stage
  name when running), Stage (Stage 5 of 11), Elapsed (tabular), Started
  (relative), actions.
- Failed rows show the error as the second line in `--color-danger-text`,
  truncated, full text in an expandable row (`<details>` in the cell) in
  Geist Mono.
- Running rows refresh with `hx-trigger="every 5s"` on the table body only.

### 10.8 Posts (`/posts`)

- **Job:** see what was posted or is scheduled.
- **Primary action:** none.
- Tabs: Scheduled, Posted, Failed. Table: Clip (title, thumbnail 32x56
  `--radius-sm`), Account, Status, Time, Link (`arrow-up-right` ghost icon
  button), Views (num, after Phase 7).

### 10.9 Stats (`/stats`, Phase 7)

- **Job:** see whether scoring predicts views.
- **Primary action:** none. Stat tiles row, then charts, each in its own
  card.

### 10.9b Outreach (`/outreach`, OUTREACH.md §6.5)

- **Job:** move leads through three reviews: streamer, clip, email.
- **Tabs** (`?tab=`, with counts): Streamers to review, Needs contact,
  Clips in progress, Ready to email, Sent, Replies, Clients, Stats, Finder
  settings.
- **Bulk tables:** a checkbox column (`.check`), a sticky `.bulk-bar` above
  the table with the selected count on the left and actions on the right.
  The tab's main action is the one primary button (Approve, Send selected,
  Mark trial). Destructive bulk actions ask first (`data-confirm`).
- **Ready to email:** one card per draft (`.draft`): 9:16 clip preview on the
  left, To, Subject and Message fields on the right. One column on mobile.
- **Row forms in tables** use the `form="..."` attribute with hidden empty
  forms outside the card body, so no form nests inside a table.
- **Finder settings:** settings cards (9.7). Members see them read only.
- **Add lead:** a secondary header button opens a `.dialog--md.dialog--form`
  (`data-open-dialog`). On a form error the server re-renders the page with
  the dialog open (`data-open-on-load`), the alert inside it, and the typed
  values kept. Never put the values in the URL: they include an email.

### 10.10 Settings (admin, `/settings/...`)

- **Job:** one settings area per page.
- Left sub-nav on `md` and up (180px, same `.nav-item` style, no icons):
  General, Users, Accounts, Model, Scoring, Retention, Notifications. Below
  `md` it becomes a `select`.
- Each page: one card, one Save changes button in the card footer.
- Users and Accounts are tables with an "Invite user" / "Connect account"
  primary button in the page header instead.
- Danger zone (for example "Delete all media") is its own card at the end
  of the relevant page: `--color-danger-text` title color only, danger
  secondary button that opens a confirm dialog.

### 10.11 Error pages (403, 404, 500)

- Centered in the main area, `--space-16` from top. Title 24/600 ("You
  don't have access to this page"), one muted sentence, error id in Geist
  Mono for 500s, one secondary button "Go to Review". No illustrations.

---

## 11. States: loading, empty, error, stale

Every page and every htmx partial defines all four. Write them at the same
time as the success state.

| State | What to show |
|---|---|
| Loading (first load) | Skeleton in the shape of the content. No spinner. Only after 300ms |
| Loading (action) | `.is-loading` on the button that started it. The rest of the page stays usable |
| Empty | Empty state component (9.22). Different copy for "nothing yet" and "no results for this filter" (the second has a "Clear filter" secondary button instead) |
| Error (page) | Inline danger alert at the top of the content: what failed, and a Retry button. Keep any data already shown |
| Error (form) | Field errors under each field plus focus on the first one. Server errors not tied to a field go in an alert above the form actions |
| Error (htmx request) | `app.js` catches `htmx:responseError` and shows a toast "Something went wrong. Try again." with the error id |
| Stale | When live data is older than expected (worker heartbeat over 2 min, a Jobs table that failed to refresh), a warning alert: "Worker not responding since 14:02. Jobs are paused." |

---

## 12. Copy and formatting

### 12.1 Voice

- Plain, short, calm. Speak like a good internal tool, not a marketing site.
- Sentence case. No exclamation marks. No emojis. No "Oops", "Whoops",
  "Awesome", "Let's".
- No em dashes or en dashes anywhere in UI text. Use a period, comma,
  colon, or parentheses.
- Second person when talking to the user ("Your clip"), but prefer no
  pronoun at all ("Clip approved").
- Name things the same everywhere (12.3).

### 12.2 Formatting

All formatting goes through Jinja filters. Never format in a template by
hand.

| Filter | Input | Output |
|---|---|---|
| `timecode` | seconds | `1:02:03.4` (under 1 h: `2:03.4`). Geist Mono |
| `duration` | seconds | `0:32`, `12:05`, `3:12:40`. Tabular |
| `duration_words` | seconds | `3 h 12 min`, `45 min`, `28 s` |
| `relative_time` | UTC datetime | `just now`, `12 min ago`, `3 h ago`, `Yesterday 19:00`, `Sep 28, 19:00`, `Sep 28, 2025` (other years) |
| `local_time` | UTC datetime | `Sep 30, 2026, 19:00` for `title` attributes |
| `filesize` | bytes | `214 MB`, `1.2 GB` |
| `number` | int | `12,480` |
| `compact_number` | int | `12.5K`, `1.2M` (views only) |
| `percent` | float | `47%` (no decimals unless under 10%: `4.2%`) |

Times are shown in the viewer's local timezone (stored per user, default
the PC's timezone). Clock is 24 hour.

### 12.3 Glossary (one word for one thing)

| Use | Never use |
|---|---|
| Clip | Short, video, cut |
| Job | Task, run, process |
| Source | Channel, streamer (in UI labels) |
| Video | VOD (except the Twitch-specific "Twitch VOD" in the New tab) |
| Approve / Reject | Accept, decline, OK |
| Re-render | Regenerate, rebuild |
| Post | Publish, upload, share |
| Account | Connection, integration |
| Score | Rating, rank |

### 12.4 Message patterns

- **Error:** what happened, then what to do. "Download failed. Twitch
  returned an error for this VOD. Retry, or check the link." Never blame
  the user, never show a stack trace (log it, show the error id).
- **Empty:** what is missing, then how to fill it.
- **Confirm dialog:** "Delete source?" / "xQc and its 4 queued jobs will be
  removed. Rendered clips stay." / Cancel, Delete source.
- **Toast:** past tense, 2 to 4 words. "Clip approved", "Caption copied",
  "Job queued", "Settings saved".
- **Helper text:** one sentence, says the effect or the format. "Applies to
  new jobs only."

---

## 13. Accessibility

Required on every page. Not optional polish.

- **Focus:** `:focus-visible { outline: 2px solid var(--color-focus); outline-offset: 2px; }`
  on everything interactive. Never `outline: none` without a replacement.
- **Contrast:** text AA (4.5:1), large text and UI borders that carry
  meaning 3:1. The tokens already pass; do not add new colors.
- **Semantics:** real `<button>` for actions, `<a>` for navigation, `<table>`
  for tables, `<label>` for every field, one `<h1>` per page, landmarks
  (`<nav>`, `<main>`).
- **Icon buttons:** `aria-label` plus `data-tooltip`.
- **Status is never color only:** badges always have a text label.
- **Live regions:** toast region is `aria-live="polite"`. Status badges that
  change via htmx are inside an `aria-live="polite"` container on the Jobs
  page.
- **Keyboard:** every action reachable by Tab. Shortcuts (BLUEPRINT 10.1)
  are off while focus is in an input or textarea. `?` opens the shortcuts
  dialog.
- **Skip link** to `#main`, visible on focus.
- **Targets:** at least 24x24px (sm buttons are 28px). On touch screens
  (`@media (pointer: coarse)`), buttons and nav items grow to 40px high.
- **Media:** autoplay previews are muted and have no sound controls. The
  detail player has native controls.
- **Zoom:** layout works at 200% zoom and 320px width with no horizontal
  page scroll (tables scroll inside `.table-wrap`).

---

## 14. Banned patterns

If you see any of these in a diff, remove it.

**Visual**
- Gradients of any kind (backgrounds, text, borders, buttons).
- Glows, colored shadows, neon, blur, glassmorphism.
- Shadows on cards, tables, buttons, or inputs.
- Emojis anywhere (UI, copy, toasts, empty states, commit-visible strings).
- Illustrations, decorative SVGs, mascots, hand-drawn icons.
- Icons from any set other than Phosphor regular. Colored nav icons.
- An icon in front of every heading or list item.
- Colored dots before list items, nav items, or labels.
- Purple, pink, or teal accents. Any second accent color.
- Pure black or pure white backgrounds (except `--color-media-bg`).
- Fonts other than Geist and Geist Mono. Font weights 300 or 700.
- Text sizes not in the scale (4.2). Spacing not in the scale (5.1).
- Radius values not in the scale (6.1). Mixed radii on the same kind of
  element.

**Layout**
- Cards inside cards. Cards around single values or single lines.
- Hero sections, big banners, welcome headers ("Welcome back, Nick").
- Centered page layouts (except empty states and error pages).
- Three equal "feature" cards in a row.
- Uppercase eyebrows or tracked small-caps labels.
- More than one primary button on a page (or in a dialog).
- Action buttons at the top of a form.
- Borders on both top and bottom of every table row.
- Infinite scroll. Carousels. Accordions for primary content.

**Behavior**
- Spinners as page or section loaders.
- Toasts for errors the user must fix.
- Animations on page load, on scroll, or on htmx swap.
- Hover-only access to an action (it must also work on focus and touch).
- `|safe` on any transcript, chat, title, caption, or LLM text.
- Inline `style` attributes or inline `<script>`.

**Copy**
- Title Case, ALL CAPS, exclamation marks, em dashes, en dashes.
- "Submit", "OK", "Click here", "Oops", "Something awesome".
- Fake or filler data in production templates.

---

## 15. Review checklist

Run this before calling any page or component done. Every box must be
true.

- [ ] Page has one `h1` (page header macro) and at most one primary button.
- [ ] Every color, size, space, radius, shadow, z-index is a token from
      this file. No new values.
- [ ] Every button, badge, field, icon, and status uses its macro.
- [ ] Statuses use `ui.status()` and match the map in 3.3.
- [ ] Loading, empty, error, and stale states exist and were looked at.
- [ ] Checked in dark and light theme.
- [ ] Checked at 375px, 768px, 1024px, and 1440px wide. No horizontal page
      scroll.
- [ ] Tab through the page: every control reachable, focus ring visible,
      order makes sense. Shortcuts work and are off inside inputs.
- [ ] Icon-only buttons have `aria-label` and tooltip.
- [ ] Numbers are tabular and right aligned in tables. Times use the
      filters in 12.2.
- [ ] Copy follows Section 12: sentence case, glossary words, no dashes,
      no exclamation marks, verb + noun button labels.
- [ ] Nothing from Section 14 is present.
- [ ] Untrusted text (titles, captions, chat, transcript, LLM output) is
      autoescaped.
- [ ] Before calling the UI done: run the `impeccable` skill, then the
      `web-design-guidelines` check (per BLUEPRINT 10, Design system).

---

## 16. Appendix: token file (copy as is)

`static/css/tokens.css`:

```css
:root {
  color-scheme: dark;

  /* Fonts */
  --font-sans: "Geist", ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
  --font-mono: "Geist Mono", ui-monospace, "SFMono-Regular", "Cascadia Mono", Consolas, monospace;

  /* Type scale: size / line height */
  --text-display-size: 32px;  --text-display-lh: 40px;
  --text-title-size: 24px;    --text-title-lh: 32px;
  --text-heading-size: 16px;  --text-heading-lh: 24px;
  --text-body-size: 14px;     --text-body-lh: 20px;
  --text-small-size: 13px;    --text-small-lh: 18px;
  --text-caption-size: 12px;  --text-caption-lh: 16px;

  /* Spacing */
  --space-1: 4px;
  --space-2: 8px;
  --space-3: 12px;
  --space-4: 16px;
  --space-5: 20px;
  --space-6: 24px;
  --space-8: 32px;
  --space-10: 40px;
  --space-12: 48px;
  --space-16: 64px;

  /* Layout */
  --sidebar-width: 240px;
  --content-wide: 1440px;
  --content-default: 1120px;
  --content-narrow: 640px;

  /* Radius */
  --radius-sm: 4px;
  --radius-md: 6px;
  --radius-lg: 8px;
  --radius-xl: 12px;
  --radius-full: 9999px;

  /* Z-index */
  --z-sticky: 10;
  --z-sidebar: 20;
  --z-popover: 30;
  --z-toast: 40;

  /* Motion */
  --duration-fast: 120ms;
  --duration-base: 200ms;
  --ease-out: cubic-bezier(0.16, 1, 0.3, 1);
  --ease-in-out: cubic-bezier(0.4, 0, 0.2, 1);

  /* Colors: dark (default) */
  --color-bg: #0a0a0a;
  --color-bg-subtle: #111111;
  --color-surface: #161616;
  --color-surface-hover: #1f1f1f;
  --color-surface-active: #262626;
  --color-border: #262626;
  --color-border-strong: #3a3a3a;
  --color-border-hover: #525252;
  --color-text: #ededed;
  --color-text-muted: #a1a1a1;
  --color-text-subtle: #808080;
  --color-text-disabled: #525252;
  --color-text-inverse: #0a0a0a;
  --color-primary: #ededed;
  --color-primary-hover: #d4d4d4;
  --color-accent: #0068d6;
  --color-accent-text: #4ea1ff;
  --color-accent-subtle: rgb(78 161 255 / 0.12);
  --color-focus: #4ea1ff;
  --color-success-text: #4cc38a;
  --color-success-subtle: rgb(76 195 138 / 0.12);
  --color-warning-text: #f5a524;
  --color-warning-subtle: rgb(245 165 36 / 0.12);
  --color-danger: #d93036;
  --color-danger-hover: #c1272d;
  --color-danger-text: #ff6166;
  --color-danger-subtle: rgb(255 97 102 / 0.12);
  --color-media-bg: #000000;
  --color-overlay: rgb(0 0 0 / 0.6);

  /* Shadows (floating elements only) */
  --shadow-popover: 0 4px 12px rgb(0 0 0 / 0.4);
  --shadow-dialog: 0 16px 48px rgb(0 0 0 / 0.5);

  /* Select caret, color matches --color-text-muted */
  --select-caret: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 256 256' fill='%23a1a1a1'%3E%3Cpath d='M213.66,101.66l-80,80a8,8,0,0,1-11.32,0l-80-80A8,8,0,0,1,53.66,90.34L128,164.69l74.34-74.35a8,8,0,0,1,11.32,11.32Z'/%3E%3C/svg%3E");
}

:root[data-theme="light"] {
  color-scheme: light;

  --color-bg: #fafafa;
  --color-bg-subtle: #f5f5f5;
  --color-surface: #ffffff;
  --color-surface-hover: #f2f2f2;
  --color-surface-active: #ebebeb;
  --color-border: #e5e5e5;
  --color-border-strong: #d4d4d4;
  --color-border-hover: #a3a3a3;
  --color-text: #171717;
  --color-text-muted: #666666;
  --color-text-subtle: #737373;
  --color-text-disabled: #a3a3a3;
  --color-text-inverse: #ffffff;
  --color-primary: #171717;
  --color-primary-hover: #383838;
  --color-accent: #0068d6;
  --color-accent-text: #0068d6;
  --color-accent-subtle: rgb(0 104 214 / 0.08);
  --color-focus: #0068d6;
  --color-success-text: #1a7f4b;
  --color-success-subtle: rgb(26 127 75 / 0.08);
  --color-warning-text: #a35200;
  --color-warning-subtle: rgb(163 82 0 / 0.08);
  --color-danger: #d93036;
  --color-danger-hover: #c1272d;
  --color-danger-text: #d93036;
  --color-danger-subtle: rgb(217 48 54 / 0.08);
  --color-overlay: rgb(0 0 0 / 0.4);

  --shadow-popover: 0 4px 12px rgb(0 0 0 / 0.08), 0 1px 2px rgb(0 0 0 / 0.04);
  --shadow-dialog: 0 16px 48px rgb(0 0 0 / 0.12), 0 2px 4px rgb(0 0 0 / 0.04);

  --select-caret: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 256 256' fill='%23666666'%3E%3Cpath d='M213.66,101.66l-80,80a8,8,0,0,1-11.32,0l-80-80A8,8,0,0,1,53.66,90.34L128,164.69l74.34-74.35a8,8,0,0,1,11.32,11.32Z'/%3E%3C/svg%3E");
}
```

`static/css/base.css` (start of file):

```css
@font-face { font-family: "Geist"; src: url("/static/fonts/Geist-Variable.woff2") format("woff2"); font-weight: 100 900; font-display: swap; }
@font-face { font-family: "Geist Mono"; src: url("/static/fonts/GeistMono-Variable.woff2") format("woff2"); font-weight: 100 900; font-display: swap; }

*, *::before, *::after { box-sizing: border-box; }
* { margin: 0; }
html { -webkit-text-size-adjust: 100%; }
body {
  min-height: 100dvh;
  background: var(--color-bg);
  color: var(--color-text);
  font-family: var(--font-sans);
  font-size: var(--text-body-size);
  line-height: var(--text-body-lh);
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  text-rendering: optimizeLegibility;
}
img, video, svg { display: block; max-width: 100%; }
button, input, select, textarea { font: inherit; color: inherit; }
h1, h2, h3 { font-weight: 600; }
h1 { font-size: var(--text-title-size); line-height: var(--text-title-lh); letter-spacing: -0.02em; }
h2 { font-size: var(--text-heading-size); line-height: var(--text-heading-lh); letter-spacing: -0.01em; }
h3 { font-size: var(--text-body-size); line-height: var(--text-body-lh); }
code, kbd, samp, pre { font-family: var(--font-mono); font-size: 13px; }

a { color: var(--color-accent-text); text-decoration: none; }
a:hover { text-decoration: underline; text-underline-offset: 2px; }

:focus-visible { outline: 2px solid var(--color-focus); outline-offset: 2px; }
::selection { background: var(--color-accent-subtle); }
input[type="checkbox"], input[type="radio"] { accent-color: var(--color-accent); width: 16px; height: 16px; }

.skip-link { position: absolute; left: var(--space-4); top: -100px; padding: var(--space-2) var(--space-3); background: var(--color-primary); color: var(--color-text-inverse); border-radius: var(--radius-md); z-index: var(--z-toast); }
.skip-link:focus { top: var(--space-4); }

/* Utilities: this is the full list. Do not add more without updating DESIGN.md */
.tabular { font-variant-numeric: tabular-nums; }
.mono { font-family: var(--font-mono); font-size: 13px; }
.muted { color: var(--color-text-muted); }
.subtle { color: var(--color-text-subtle); }
.small { font-size: var(--text-small-size); line-height: var(--text-small-lh); }
.truncate { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; min-width: 0; }
.stack { display: flex; flex-direction: column; gap: var(--space-4); }
.stack--sm { gap: var(--space-2); }
.stack--lg { gap: var(--space-8); }
.row { display: flex; align-items: center; gap: var(--space-2); }
.row--between { justify-content: space-between; }
.visually-hidden { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; border: 0; }

@keyframes spin { to { transform: rotate(360deg); } }
@keyframes pulse { 50% { opacity: 0.5; } }

@media (pointer: coarse) {
  .btn, .nav-item, .menu__item { min-height: 40px; }
}

@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { animation-duration: 0.01ms !important; animation-iteration-count: 1 !important; transition-duration: 0.01ms !important; }
}
```

`templates/macros/ui.html` (reference for the two most used macros; build
the rest the same way):

```jinja
{# _svg is shared because the button's `icon` parameter shadows the icon macro #}
{% macro _svg(name, size=16) -%}
  <svg width="{{ size }}" height="{{ size }}" aria-hidden="true" focusable="false">
    <use href="/static/icons/sprite.svg#{{ name }}"></use>
  </svg>
{%- endmacro %}

{% macro icon(name, size=16) -%}{{ _svg(name, size) }}{%- endmacro %}

{% macro button(label, variant="secondary", size="md", icon=None, href=None, type="button", icon_only=False, attrs={}) -%}
  {%- set cls = "btn btn--" ~ variant ~ (" btn--" ~ size if size != "md" else "") ~ (" btn--icon" if icon_only else "") -%}
  {%- set extra = attrs | xmlattr -%}
  {%- if href -%}
    <a class="{{ cls }}" href="{{ href }}" {% if icon_only %}aria-label="{{ label }}" data-tooltip="{{ label }}"{% endif %} {{ extra }}>
  {%- else -%}
    <button class="{{ cls }}" type="{{ type }}" {% if icon_only %}aria-label="{{ label }}" data-tooltip="{{ label }}"{% endif %} {{ extra }}>
  {%- endif -%}
    {%- if icon %}{{ _svg(icon, 14 if size == "sm" else 16) }}{% endif -%}
    {%- if not icon_only %}<span>{{ label }}</span>{% endif -%}
  {%- if href %}</a>{% else %}</button>{% endif -%}
{%- endmacro %}
```

Build `static/icons/sprite.svg` once from the Phosphor SVGs in Section 7:
each icon becomes a `<symbol id="name" viewBox="0 0 256 256">` with its
paths and `fill="currentColor"`. A small script in `scripts/build_icons.py`
does this. Add an icon by adding its file and re-running the script.
