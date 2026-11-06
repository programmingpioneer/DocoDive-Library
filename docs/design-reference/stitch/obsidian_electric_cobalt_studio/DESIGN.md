---
name: Obsidian & Electric Cobalt Studio
colors:
  surface: '#f8f9ff'
  surface-dim: '#cbdbf5'
  surface-bright: '#f8f9ff'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#eff4ff'
  surface-container: '#e5eeff'
  surface-container-high: '#dce9ff'
  surface-container-highest: '#d3e4fe'
  on-surface: '#0b1c30'
  on-surface-variant: '#424754'
  inverse-surface: '#213145'
  inverse-on-surface: '#eaf1ff'
  outline: '#727785'
  outline-variant: '#c2c6d6'
  surface-tint: '#005ac2'
  primary: '#0058be'
  on-primary: '#ffffff'
  primary-container: '#2170e4'
  on-primary-container: '#fefcff'
  inverse-primary: '#adc6ff'
  secondary: '#5a5e6a'
  on-secondary: '#ffffff'
  secondary-container: '#dfe2f1'
  on-secondary-container: '#606471'
  tertiary: '#006947'
  on-tertiary: '#ffffff'
  tertiary-container: '#00855b'
  on-tertiary-container: '#f5fff6'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#d8e2ff'
  primary-fixed-dim: '#adc6ff'
  on-primary-fixed: '#001a42'
  on-primary-fixed-variant: '#004395'
  secondary-fixed: '#dfe2f1'
  secondary-fixed-dim: '#c3c6d4'
  on-secondary-fixed: '#171b26'
  on-secondary-fixed-variant: '#434652'
  tertiary-fixed: '#6ffbbe'
  tertiary-fixed-dim: '#4edea3'
  on-tertiary-fixed: '#002113'
  on-tertiary-fixed-variant: '#005236'
  background: '#f8f9ff'
  on-background: '#0b1c30'
  surface-variant: '#d3e4fe'
typography:
  headline-xl:
    fontFamily: Plus Jakarta Sans
    fontSize: 32px
    fontWeight: '800'
    lineHeight: 40px
    letterSpacing: -0.03em
  headline-xl-mobile:
    fontFamily: Plus Jakarta Sans
    fontSize: 26px
    fontWeight: '800'
    lineHeight: 34px
    letterSpacing: -0.025em
  headline-lg:
    fontFamily: Plus Jakarta Sans
    fontSize: 22px
    fontWeight: '700'
    lineHeight: 30px
    letterSpacing: -0.02em
  headline-md:
    fontFamily: Plus Jakarta Sans
    fontSize: 18px
    fontWeight: '700'
    lineHeight: 26px
    letterSpacing: -0.015em
  headline-sm:
    fontFamily: Plus Jakarta Sans
    fontSize: 15px
    fontWeight: '600'
    lineHeight: 22px
    letterSpacing: -0.01em
  body-lg:
    fontFamily: Plus Jakarta Sans
    fontSize: 15px
    fontWeight: '400'
    lineHeight: 24px
    letterSpacing: 0em
  body-md:
    fontFamily: Plus Jakarta Sans
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 20px
    letterSpacing: 0em
  body-sm:
    fontFamily: Plus Jakarta Sans
    fontSize: 12px
    fontWeight: '400'
    lineHeight: 18px
    letterSpacing: 0.01em
  label-eyebrow:
    fontFamily: Plus Jakarta Sans
    fontSize: 11px
    fontWeight: '700'
    lineHeight: 14px
    letterSpacing: 0.08em
  label-md:
    fontFamily: Plus Jakarta Sans
    fontSize: 13px
    fontWeight: '600'
    lineHeight: 16px
    letterSpacing: 0.01em
  label-sm:
    fontFamily: Plus Jakarta Sans
    fontSize: 11px
    fontWeight: '600'
    lineHeight: 14px
    letterSpacing: 0.02em
  metric-display:
    fontFamily: Plus Jakarta Sans
    fontSize: 30px
    fontWeight: '800'
    lineHeight: 36px
    letterSpacing: -0.03em
rounded:
  sm: 0.25rem
  DEFAULT: 0.5rem
  md: 0.75rem
  lg: 1rem
  xl: 1.5rem
  full: 9999px
spacing:
  gutter: 1.25rem
  gutter-desktop: 1.5rem
  margin: 1rem
  margin-desktop: 2.25rem
  space-xs: 0.25rem
  space-sm: 0.5rem
  space-md: 0.875rem
  space-lg: 1.25rem
  space-xl: 2rem
---

## Brand & Style

The design system establishes a high-performance, focused administrative environment tailored for digital publishing, archival curation, and reader community management. Built around a duality between a deep, immersive midnight command bar and luminous, analytical workspaces, the aesthetic merges technical discipline with architectural elegance.

### Emotional Disposition
- **Clarity & Command:** Dense data hierarchies structured into digestible visual bites, removing cognitive clutter while preserving comprehensive oversight.
- **Editorial Sophistication:** Subtle, razor-thin borders paired with crisp typography celebrate textual curation and high-volume literature catalogs.
- **Dynamic Intelligence:** Precise telemetry indicators, vibrant categorical accents, and focused status metrics communicate realtime community pulse.

### Visual Style
The aesthetic aligns with **Modern Precision SaaS with Dual-Toned Spatial Architecture**. It balances an ultra-deep charcoal/midnight navigation spine (`#0B0F19`) against crisp, airy canvas surfaces (`#F8FAFC`, `#FFFFFF`), held together by hairline structural dividers (`#E2E8F0`), restrained ambient drop shadows, and high-impact electric royal indigo focal points.

## Colors

The color palette operates on a purposeful dual-tone split:
1. **Primary (`#3B82F6` / `#4338CA` gradient spectrum):** Electric cobalt into royal indigo anchors prime calls-to-action, high-priority interactive states, key performance visualizers, and active breadcrumbs.
2. **Secondary / Structural Anchor (`#0B0F19`):** Deep midnight slate provides an impenetrable, focused backdrop for persistent global navigation and dark toolbars.
3. **Tertiary / Telemetry Accents (`#10B981` Emerald, `#F59E0B` Amber, `#8B5CF6` Violet, `#06B6D4` Cyan):** Reserved for data visualization series, sentiment metrics, operational status flags, and badge indicators.
4. **Neutrals & Surfaces:**
   - App Workspace Canvas: `#F8FAFC`
   - Card Surfaces: `#FFFFFF`
   - Hairline Borders & Dividers: `#E2E8F0`
   - Subtle Hover Backgrounds: `#F1F5F9`
   - High-contrast Text: `#0F172A`
   - Secondary Label Text: `#64748B`
   - Inactive / Placeholder: `#94A3B8`

## Typography

The typography system uses **Plus Jakarta Sans** across display, body, and micro-metric contexts. Its geometric construction, spacious counters, and sturdy verticals deliver clarity in dense admin tables, telemetry charts, and high-level editorial headers.

### Typographic Rhythm & Execution
- **Eyebrow Pre-headers (`label-eyebrow`):** Rendered in uppercase with +0.08em tracking in primary blue (`#3B82F6`) to categorize functional views prior to primary titles.
- **Metric Displays (`metric-display`):** Heavyweight figures (`800`) paired with subtle lower-case or capitalized subtext for immediate scanning across KPI arrays.
- **Hierarchical Anchoring:** Section headlines maintain negative letter spacing (`-0.015em` to `-0.03em`) to prevent optical looseness in larger bold weights.

## Layout & Spacing

The structural layout uses a fixed-width left command column (240px–260px) paired with an elastic content stage that responds smoothly to desktop viewports.

### Grid & Layout Rules
- **Desktop (1200px+):** Two-column split: fixed navigation sidebar dock + 12-column responsive fluid grid canvas with `gutter-desktop` (24px) and page margins of `margin-desktop` (36px).
- **Tablet (768px - 1199px):** Sidebar collapses to an icon-only dock (72px) or dismissible overlay drawer; content grid shifts to 6 columns with 20px gutters.
- **Mobile (<768px):** Navigation transitions to a top sticky bar with hamburger access; content grid folds into a single unified column with 16px margins (`margin`). Multi-card metric banks scroll horizontally or collapse into a 2x2 matrix.
- **Spacing Density:** Analytical cards prioritize a compact layout rhythm: 16px to 20px of internal padding (`space-lg`), keeping chart visualizations aligned without expanding screen boundaries.

## Elevation & Depth

Visual hierarchy uses a crisp surface-layering strategy that pairs delicate borders with soft, ambient drop shadows. Heavy elevation tiers are deliberately avoided to maintain an editorial, document-first posture.

### Surface Tiers & Depth Mechanics
- **Base Level (Canvas):** `#F8FAFC`. The foundational backdrop for the operational work area.
- **Elevated Surfaces (Cards & Tables):** `#FFFFFF` surfaces bounded by a continuous 1px hairline border in `#E2E8F0`. Depth is conveyed via a dual-ring ambient shadow:
  `box-shadow: 0 1px 3px 0 rgba(15, 23, 42, 0.03), 0 1px 2px -1px rgba(15, 23, 42, 0.02)`.
- **Interactive Hover Surfaces:** Cards subtly rise on mouseover using an adjusted shadow:
  `box-shadow: 0 4px 12px -2px rgba(15, 23, 42, 0.06), 0 2px 6px -1px rgba(15, 23, 42, 0.03)` with a border shift to `#CBD5E1`.
- **Global Sidebar (Structural Plane):** `#0B0F19` sits flush to the viewport on the left, grounding the interface with an authoritative, dark contrast column.
- **Overlays & Modals:** Floated at `z-index: 1000` backed by a 40% opacity midnight mask (`rgba(11, 15, 25, 0.45)`) paired with `backdrop-filter: blur(8px)`.

## Shapes

The design system adopts a balanced roundedness (`roundedness: 2`, standard 8px to 16px radius curve). This balances software precision with approachable editorial design.

### Corner Radii Guidelines
- **Input Fields, Toolbars & Micro-Badges:** 8px (`0.5rem`) for compact alignment and razor-sharp form fields.
- **Data Cards, Chart Containers & Surface Panels:** 16px (`1.0rem`) to soften high-density metrics and present clean visual modules.
- **Interactive Quick-Action Prompts (Hero Action Cards):** 16px (`1.0rem`) for welcoming entry points into tasks.
- **Pill Badges & Status Chips:** Fully rounded (`9999px`) for quick visual scanning of statuses and categorical flags.

## Components

### Buttons
- **Primary Button:** `#3B82F6` solid fill, `#FFFFFF` text, `font-weight: 600`. Subtle top inset highlight (`box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.2)`). Hover transitions to `#2563EB`. Active state scales smoothly to `0.98`.
- **Secondary / Outline Button:** `#FFFFFF` background, 1px border `#E2E8F0`, `#0F172A` text. Hover shifts to `#F8FAFC` and border `#CBD5E1`.
- **Ghost Action Button:** Transparent background, `#64748B` text. Hover shifts to `#F1F5F9` with `#0F172A` text.

### Cards & Analytical Panels
- **Telemetry KPI Card:** 16px rounded surface in `#FFFFFF`, hairline border in `#E2E8F0`. Features a 12px uppercase category label (`#64748B`), an oversized metric value (`#0F172A`, 30px weight 800), and an optional baseline trend chip.
- **Quick Action Guidance Cards (Top Horizon):** Compact white panels framed with an interactive icon badge on the top-left (light tinted indigo background `#EEF2FF` housing an electric blue glyph), header, and arrow-linked sub-label (`Review submissions →`).
- **Data Visualization Canvas:** Enclosed in standard 16px radius cards. Charts (donut breakdowns, multi-line telemetry, and bar distribution) use clean `#3B82F6`, `#8B5CF6`, and `#10B981` strokes over muted horizontal gridlines (`#F1F5F9`).

### Form Inputs & Filters
- **Text Inputs & Dropdowns:** 8px corner radius, `#FFFFFF` background, 1px border `#E2E8F0`, 14px text.
- **Focus State:** 1px border `#3B82F6` paired with an electric focus glow (`box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.15)`).
- **Timeframe / Filter Selector:** Pill-bordered or compact select box with right chevron, tracking clean contextual changes (e.g., `30 days ⌄`).

### Navigation Items (Sidebar)
- **Base Item:** 8px corner radius, transparent background, `#94A3B8` text and 18px stroke icons, `padding: 10px 14px`.
- **Hover Item:** Background `rgba(255, 255, 255, 0.05)`, `#F8FAFC` text.
- **Active Navigation Item:** Background `rgba(59, 130, 246, 0.12)`, text `#60A5FA` with matching glowing glyph and crisp left accent pip or subtle high-contrast white glyph text.

### Badges & Status Chips
- **Success / Approved:** Background `#ECFDF5`, text `#059669`, 9999px radius.
- **Warning / Review Required:** Background `#FFFBEB`, text `#D97706`, 9999px radius.
- **Pending / Inactive:** Background `#F1F5F9`, text `#64748B`, 9999px radius.