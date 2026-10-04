# Linear Design System Analysis

> Source: https://linear.app/  
> Measured: May 17, 2026  
> Analysis by DesignMD

---

```---
name: Linear
url: https://linear.app/
colors:
  primary: '#5e6ad2'
  background: '#ffffff'
  text-primary: '#62666d'
  text-muted: '#8a8f98'
  border: '#e5e5e6'
  dark-surface: '#0f1011'
  dark-surface-secondary: '#08090a'
  dark-text-primary: '#f7f8f8'
  dark-text-secondary: '#d0d6e0'
  dark-text-muted: '#8a8f98'
  dark-border: '#2a2e33'
  dark-border-subtle: '#24282c'
  accent-purple: '#8b5cf6'
  accent-indigo: '#6366f1'
  accent-red: '#eb5757'
typography:
  display:
    family: 'Inter Variable'
    size: 64px
    weight: 590
    line-height: 1.1
  heading:
    family: 'Inter Variable'
    size: 48px
    weight: 590
    line-height: 1.1
  body:
    family: 'Inter Variable'
    size: 16px
    weight: 400
    line-height: 1.5
  code:
    family: 'Berkeley Mono'
    size: 13px
    weight: 400
    line-height: 1.5
spacing:
  base: 4px
  scale: [4, 8, 12, 16, 20, 24, 32]
radius:
  sm: 4px
  md: 6px
  lg: 12px
  full: 9999px
elevation:
  border: 'rgba(0, 0, 0, 0.2) 0px 0px 0px 1px'
  inset: 'rgba(0, 0, 0, 0.2) 0px 0px 12px 0px inset'
  focus: 'rgba(0, 0, 0, 0.1) 0px 4px 12px, rgba(0, 0, 0, 0.2) 0px 0px 0px 2px'
components:
  button-primary:
    bg: '{colors.dark-text-primary}'
    text: '{colors.dark-surface}'
    radius: '{radius.md}'
    padding: '8px 16px'
  card:
    bg: '{colors.dark-surface}'
    radius: '{radius.lg}'
    border: '1px solid {colors.dark-border}'
    shadow: '{elevation.inset}'
---

## 1. Visual Theme & Atmosphere
Linear's design system is a masterclass in precision and focus, built for high-performance product teams. The aesthetic is anchored in a dark-mode-native environment, using near-black backgrounds like `#0f1011` and `#08090a` to create a deep, immersive canvas. This allows the high-contrast text, primarily `#f7f8f8`, to stand out with exceptional clarity. The typography, led by the versatile `Inter Variable` and the technical `Berkeley Mono` for code, is sharp and dense, prioritizing information hierarchy over decorative flair.

The system's character comes from its restraint. Color is used sparingly, with accents like `#5e6ad2` and `#8b5cf6` reserved for interactive states, status indicators, and subtle highlights. The structure is defined by sharp lines, subtle borders like `#2a2e33`, and a consistent radius scale (4px, 6px, 12px). Micro-interactions, driven by over 150 CSS animations, are swift and purposeful, with elements scaling by `0.97` on active states to provide tactile feedback without being distracting. The signature visual element is the product's own UI: a dense, tool-like interface that feels engineered, not just designed.

**Key Characteristics:**
*   **Dark-First Canvas:** Deep, near-black backgrounds like `#0f1011` create a focused environment.
*   **High-Contrast Typography:** `Inter Variable` set in `#f7f8f8` on dark surfaces ensures legibility.
*   **Precise Geometry:** A tight 4px base spacing scale and a strict `4px`/`6px`/`12px` radius system.
*   **Functional Color:** Accents like `#5e6ad2` are used for function (links, focus) not decoration.
*   **Subtle Depth:** Depth is created with `1px` borders and inset shadows, not prominent drop shadows.
*   **Technical Monospace:** `Berkeley Mono` is used for all code snippets, creating a clear visual distinction.
*   **Responsive Micro-interactions:** Swift CSS animations and `transform: scale(0.97)` on active states.

## 2. Color Palette & Roles
The palette is predominantly monochromatic, creating a focused, low-distraction environment. Color is reserved for status, interaction, and branding.

### Primary
*   **Primary (`#5e6ad2`)**: The main interactive brand color, used for links and focus rings.

### Neutral Scale (Dark Theme)
*   **Dark Surface (`#0f1011`)**: The primary background color for main content areas and application shells.
*   **Dark Surface Secondary (`#08090a`)**: A slightly darker variant used for headers and footers to create subtle separation.
*   **Dark Text Primary (`#f7f8f8`)**: The main text color for body copy, headings, and labels on dark backgrounds. Offers excellent contrast.
*   **Dark Text Secondary (`#d0d6e0`)**: A slightly softer white for secondary information and less critical labels.
*   **Dark Text Muted (`#8a8f98`)**: Used for placeholder text, disabled states, and tertiary metadata.
*   **Dark Border (`#2a2e33`)**: The primary border color for separating UI panels and components.
*   **Dark Border Subtle (`#24282c`)**: A lighter border for more subtle divisions within components.

### Neutral Scale (Light Theme)
*   **Background (`#ffffff`)**: Standard white background for light-mode contexts like the main sign-up button.
*   **Text Primary (`#62666d`)**: The primary body text color on light backgrounds.
*   **Border (`#e5e5e6`)**: The default border color in light mode.

### Accent Colors
*   **Accent Indigo (`#6366f1`)**: A vibrant indigo used for highlights and specific UI states.
*   **Accent Purple (`#8b5cf6`)**: A secondary accent, often used for user avatars or specific feature callouts.
*   **Accent Red (`#eb5757`)**: Reserved for destructive actions, error states, or urgent status indicators.

## 3. Typography Rules
Linear's typography is precise and functional, using a single variable font for the UI and a distinct monospace for code.

*   **Font Family**:
    *   **UI**: `Inter Variable`, "SF Pro Display", -apple-system, BlinkMacSystemFont, "Segoe UI", "Roboto", "Oxygen", "Ubuntu", sans-serif
    *   **Code**: `Berkeley Mono`, "Menlo", "Consolas", "Monaco", monospace

*   **Hierarchy**:

| Role          | Font              | Size  | Weight | Line Height | Letter Spacing (inferred) | Notes                                           |
|---------------|-------------------|-------|--------|-------------|---------------------------|-------------------------------------------------|
| Display       | Inter Variable    | 64px  | 590    | 1.1         | -0.02em                   | For primary marketing headlines.                |
| Heading (H1)  | Inter Variable    | 48px  | 590    | 1.1         | -0.02em                   | Section titles on the marketing page.           |
| Heading (H2)  | Inter Variable    | 24px  | 510    | 1.2         | -0.015em                  | Sub-headings and large component titles.        |
| Heading (H3)  | Inter Variable    | 20px  | 510    | 1.4         | -0.01em                   | Card titles and medium-importance labels.       |
| Body          | Inter Variable    | 16px  | 400    | 1.5         | -0.011em                  | Main paragraph and body text.                   |
| Small         | Inter Variable    | 13px  | 400    | 1.5         | -0.01em                   | Metadata, captions, and secondary labels.       |
| Caption       | Inter Variable    | 12px  | 400    | 1.5         | normal                    | Tertiary information and helper text.           |
| Code/Mono     | Berkeley Mono     | 13px  | 400    | 1.5         | normal                    | Used for all code blocks and inline code.       |

*   **Principles**:
    *   **Clarity and Density**: The system is designed to present a large amount of information clearly. Tighter line heights on headings and negative letter spacing improve scannability.
    *   **Strict Hierarchy**: Font weights and sizes are used consistently to establish a clear information hierarchy, guiding the user's focus.
    *   **Contextual Fonts**: A sharp distinction is maintained between UI text (`Inter Variable`) and content/code text (`Berkeley Mono`), preventing visual ambiguity.

## 4. Component Stylings

### Buttons
Buttons are understated and functional, with clear states for interaction. The primary CTA is a bright, inverted style.

**Primary Button (Light on Dark)**
The main call-to-action, used for key conversion points like "Sign Up". It inverts the site's color scheme for maximum prominence.

```css
.btn-primary {
  background-color: var(--color-dark-text-primary, #f7f8f8);
  color: var(--color-dark-surface, #0f1011);
  font-size: 14px;
  font-weight: 510;
  padding: 8px 16px;
  border-radius: 6px;
  border: 1px solid #e5e5e6; /* (inferred from screenshot) */
  box-shadow: 0px 1px 2px rgba(0, 0, 0, 0.05); /* (inferred from screenshot) */
  cursor: pointer;
  transition: transform 0.1s ease-out, background-color 0.15s ease;
}

.btn-primary:hover {
  background-color: #ffffff; /* (inferred from screenshot) */
  transform: translateY(-1px);
}

.btn-primary:active {
  transform: scale(0.97);
  background-color: #e5e5e6; /* (inferred from screenshot) */
}

.btn-primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
  transform: none;
}
```

**Secondary Button (Dark)**
Used for less critical actions within the dark UI. It relies on a border and subtle background change on hover.

```css
.btn-secondary {
  background-color: transparent;
  color: var(--color-dark-text-secondary, #d0d6e0);
  font-size: 13px;
  font-weight: 510;
  padding: 6px 12px;
  border-radius: 6px;
  border: 1px solid var(--color-dark-border, #2a2e33);
  cursor: pointer;
  transition: background-color 0.15s ease, color 0.15s ease, transform 0.1s ease-out;
}

.btn-secondary:hover {
  background-color: rgba(255, 255, 255, 0.05); /* (inferred from screenshot) */
  color: var(--color-dark-text-primary, #f7f8f8);
}

.btn-secondary:active {
  transform: scale(0.97);
  background-color: rgba(255, 255, 255, 0.02); /* (inferred from screenshot) */
}

.btn-secondary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
  background-color: transparent;
}
```

**Ghost Button**
Used for tertiary actions, often in toolbars or headers. It has no border or background until hovered.

```css
.btn-ghost {
  background-color: transparent;
  color: var(--color-dark-text-muted, #8a8f98);
  font-size: 13px;
  font-weight: 400;
  padding: 4px 8px;
  border-radius: 6px;
  border: none;
  cursor: pointer;
  transition: background-color 0.15s ease, color 0.15s ease;
}

.btn-ghost:hover {
  background-color: rgba(255, 255, 255, 0.05); /* (inferred from screenshot) */
  color: var(--color-dark-text-primary, #f7f8f8);
}

.btn-ghost:active {
  background-color: rgba(255, 255, 255, 0.02); /* (inferred from screenshot) */
}

.btn-ghost:disabled {
  opacity: 0.4;
  cursor: not-allowed;
  color: var(--color-dark-text-muted, #8a8f98);
}
```

### Cards & Containers
Cards are the fundamental building blocks of the UI, featuring subtle depth and clean lines.

```css
.card {
  background-color: var(--color-dark-surface, #0f1011);
  border-radius: 12px;
  border: 1px solid var(--color-dark-border, #2a2e33);
  box-shadow: rgba(0, 0, 0, 0.2) 0px 0px 12px 0px inset;
  padding: 24px;
  transition: filter 0.15s ease, border-color 0.15s ease;
}

.card:hover {
  filter: brightness(1.2);
  border-color: var(--color-dark-border-subtle, #383b3f); /* (inferred from screenshot) */
}
```

### Inputs & Forms
Form elements are minimal and integrate seamlessly into the dark theme.

```css
.form-label {
  color: var(--color-dark-text-secondary, #d0d6e0);
  font-size: 13px;
  font-weight: 510;
  margin-bottom: 8px;
}

.text-input {
  background-color: var(--color-dark-surface-secondary, #08090a);
  color: var(--color-dark-text-primary, #f7f8f8);
  font-size: 14px;
  font-weight: 400;
  padding: 8px 12px;
  border-radius: 6px;
  border: 1px solid var(--color-dark-border, #2a2e33);
  transition: border-color 0.15s ease, box-shadow 0.15s ease;
  outline: none;
}

.text-input:focus,
.text-input:focus-visible {
  border-color: var(--color-primary, #5e6ad2);
  box-shadow: 0 0 0 3px rgba(94, 106, 210, 0.3); /* (inferred from screenshot) */
}

.text-input:disabled {
  opacity: 0.5;
  cursor: not-allowed;
  background-color: var(--color-dark-border, #2a2e33);
}
```

### Navigation

**Top Navigation Bar**
The main header is fixed, using a slightly darker shade to distinguish itself from the content below.

```css
.nav-bar {
  background-color: var(--color-dark-surface-secondary, #08090a);
  padding: 12px 24px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-bottom: 1px solid var(--color-dark-border, #2a2e33);
}
```

**Navigation Link**
Links in the navigation are subtle, brightening on hover to indicate interactivity.

```css
.nav-link {
  color: var(--color-dark-text-muted, #8a8f98);
  font-size: 13px;
  font-weight: 400;
  padding: 8px 12px;
  border-radius: 9999px;
  text-decoration: none;
  transition: color 0.15s ease, background-color 0.15s ease;
}

.nav-link:hover {
  color: var(--color-dark-text-primary, #f7f8f8);
  background-color: rgba(255, 255, 255, 0.05); /* (inferred from screenshot) */
}

.nav-link[aria-current="page"],
.nav-link.active {
  color: var(--color-dark-text-primary, #f7f8f8);
}
```

### Links

**Standard Link**
Inline text links are colored with the primary accent for clear affordance.

```css
.link {
  color: var(--color-primary, #5e6ad2);
  text-decoration: none;
  transition: color 0.15s ease;
}

.link:hover {
  color: var(--color-accent-indigo, #6366f1);
  text-decoration: underline;
}

.link:visited {
  color: var(--color-primary, #5e6ad2);
}
```

### Badges
Badges are used within the product UI to convey status. They are small, pill-shaped, and use subtle colors.

```css
.badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  font-weight: 510;
  padding: 2px 8px;
  border-radius: 9999px;
}

/* Example: "In Progress" badge */
.badge-status-inprogress {
  background-color: rgba(139, 92, 246, 0.1); /* (inferred from screenshot) */
  color: var(--color-accent-purple, #8b5cf6);
}

/* Example: "High" priority badge */
.badge-status-high {
  background-color: rgba(235, 87, 87, 0.1); /* (inferred from screenshot) */
  color: var(--color-accent-red, #eb5757);
}
```

## 5. Layout Principles

*   **Spacing System**: The system is built on a `4px` base unit. All padding, margins, and gaps use multiples of this base.
    *   **Scale**: `4px`, `8px`, `12px`, `16px`, `20px`, `24px`, `32px`
    *   **Usage Context**:
        *   `4px`: Gaps between icons and text, fine-tuning alignment.
        *   `8px`: Gaps between small elements, padding within compact components.
        *   `12px`: Padding for buttons and inputs.
        *   `16px`: Standard gap between elements, small container padding.
        *   `24px`: Main content padding inside cards and containers.
        *   `32px`: Gaps between major sections or large cards.

*   **Grid & Container**:
    _Note: Container widths and column counts are not extracted from the source. The values below are reasonable defaults inferred from the visible layout density._
    *   **Max Width**: `1440px` for marketing pages, with content often centered in a `1100px` column. The app itself is fluid.
    *   **Section Padding**: `32px` horizontally, `64px` or `96px` vertically between major page sections.

*   **Whitespace Philosophy**: Whitespace is used with intention and precision. It's not expansive or airy, but rather serves to cleanly delineate functional blocks within a dense, information-rich interface. Consistent gaps and padding create a predictable rhythm that helps users navigate complex layouts.

*   **Border Radius Scale**:
    *   **4px (sm)**: Used for small, inline elements like tags.
    *   **6px (md)**: The default radius for most interactive elements like buttons and inputs.
    *   **12px (lg)**: Applied to larger containers like cards and modals for a softer, modern feel.
    *   **9999px (full)**: For pill-shaped elements like badges and some navigation links.

## 6. Depth & Elevation
Linear avoids traditional, heavy drop shadows. Instead, depth and layering are achieved through a combination of opacity, `1px` borders, subtle inset shadows, and high `z-index` values for modals and menus.

| Level | Treatment                                                               | z-index | Use                                     |
|-------|-------------------------------------------------------------------------|---------|-----------------------------------------|
| z-0   | Flat, no shadow                                                         | 0       | Base page background.                   |
| z-1   | `1px` solid border (`#2a2e33`)                                           | 1-10    | Cards, panels, inputs, static elements. |
| z-2   | `1px` border + inset shadow (`rgba(0,0,0,0.2) 0 0 12px inset`)           | 50      | Footers, sticky headers.                |
| z-3   | Focus ring (`0 0 0 3px rgba(94,106,210,0.3)`)                            | 100     | Interactive elements in focus state.    |
| z-4   | `rgba(0,0,0,0.1) 0 4px 12px, rgba(0,0,0,0.2) 0 0 0 2px`                   | 5000+   | Tooltips, dropdowns, popovers.          |
| z-5   | Backdrop overlay + shadow                                               | 10000+  | Modals, command palettes (e.g., Cmd+K). |

*   **Shadow Philosophy**: The philosophy is to maintain a visually flat but structurally layered UI. Shadows are almost invisible, serving to lift an element from its background just enough to define its boundary or state, as seen in focus rings. The primary method of separation is the `1px` border, which provides a crisp, technical edge to all components.

## 7. Do's and Don'ts

### Do
*   **Do** use `#f7f8f8` text on `#0f1011` backgrounds for primary content to ensure AAA contrast.
*   **Do** apply a `12px` border-radius to all primary containers and cards.
*   **Do** use the `6px` radius for all standard interactive controls like buttons and inputs.
*   **Do** use `Berkeley Mono` for any text representing code, file paths, or technical identifiers.
*   **Do** use the primary brand color `#5e6ad2` exclusively for interactive links and focus states.
*   **Do** separate UI panels using a `1px` solid border with the `#2a2e33` color.
*   **Do** use the 4px base spacing scale (`4, 8, 12, 16, 24, 32px`) for all margins and padding.
*   **Do** indicate active states with a `transform: scale(0.97)` for immediate feedback.
*   **Do** use accent colors like `#eb5757` and `#8b5cf6` only for status badges or avatars.
*   **Do** ensure all interactive elements have a visible focus state with the standard focus ring.

### Don't
*   **Don't** use traditional drop shadows; prefer the subtle `1px` border or inset shadow.
*   **Don't** use colors other than `#5e6ad2` for inline text links.
*   **Don't** use `Inter Variable` for code blocks; always use `Berkeley Mono`.
*   **Don't** introduce spacing values outside the `4px` scale (e.g., `10px` or `18px`).
*   **Don't** use a border-radius other than `4px`, `6px`, `12px`, or `9999px`.
*   **Don't** use text color `#62666d` on background `#0f1011`; its 3.3:1 contrast ratio fails AA for normal text.
*   **Don't** use pure black `#000000`; stick to the nuanced `#0f1011` and `#08090a` surfaces.
*   **Don't** create buttons without a distinct `:hover` and `:active` state.
*   **Don't** use font weights other than `400` for body copy or `510`/`590` for headings.
*   **Don't** make links or buttons smaller than a `32px` touch target on mobile.

## 8. Responsive Behavior
_Note: The breakpoints below are measured directly from the source CSS. They should be used as the ground truth for implementation._

*   **Measured Breakpoints**:

| Breakpoint Name | Width           | Key Changes                                                                                             |
|-----------------|-----------------|---------------------------------------------------------------------------------------------------------|
| Mobile          | `< 640px`       | Single-column layout. Navigation collapses into a hamburger menu. Font sizes decrease slightly.         |
| Tablet          | `641px - 768px` | Two-column layouts may appear. Horizontal padding is reduced.                                           |
| Laptop          | `769px - 1024px`| Main navigation is visible. Complex UI patterns like multi-column views are standard.                   |
| Desktop         | `1025px - 1280px`| Layouts gain more whitespace. Sidebars may become permanently visible instead of being overlays.        |
| Desktop Large   | `> 1280px`      | The main content container is maxed out at `~1440px`, with margins increasing on either side.           |

*   **Touch Targets**:
    *   All interactive elements (buttons, links, inputs) must have a minimum interactive area of `32px` by `32px`.
    *   Ensure at least `8px` of space between tappable elements to prevent accidental touches.

*   **Collapsing Strategy**:
    *   **Navigation**: The top navigation bar collapses its text links into a mobile menu icon. The primary "Sign Up" CTA remains visible.
    *   **Cards**: Cards stack vertically in a single column on mobile screens.
    *   **Typography**: Display headings (`64px`/`48px`) scale down significantly on mobile to prevent overflow and improve readability.
    *   **Padding**: Horizontal padding on sections and containers is reduced from `24px`/`32px` to `16px`.
    *   **Forms**: Inputs and labels stack vertically, with inputs taking up the full width of the container.

## 9. Agent Prompt Guide

*   **Quick Color Reference**:
    *   Primary Action/Link: `#5e6ad2`
    *   Dark Background: `#0f1011`
    *   Dark Header/Footer BG: `#08090a`
    *   Dark Text: `#f7f8f8`
    *   Dark Muted Text: `#8a8f98`
    *   Dark Border: `#2a2e33`
    *   Light Button BG: `#f7f8f8`
    *   Light Button Text: `#0f1011`

*   **Iteration Guide**:
    1.  **Always** use a dark background (`#0f1011`) with light text (`#f7f8f8`).
    2.  **Always** use `Inter Variable` for UI text and `Berkeley Mono` for code.
    3.  **Always** use the `4px` spacing scale: `4, 8, 12, 16, 24, 32px`.
    4.  **Always** use one of three radii: `6px` for controls, `12px` for containers, `9999px` for pills.
    5.  **Always** separate containers with a `1px` border of `#2a2e33`, not drop shadows.
    6.  The primary CTA is the **only** major light-background element: a `#f7f8f8` button.
    7.  Interactive elements **must** have hover, active (`scale: 0.97`), and focus states.
    8.  Focus rings **must** use a soft shadow based on the `#5e6ad2` primary color.
    9.  Text links are **always** colored `#5e6ad2` and are not underlined by default.
    10. On mobile (`<640px`), switch to a single-column layout and collapse the main navigation.
    11. **Never** use `#62666d` text on a dark background; its contrast is too low.
    12. All new components should be built with these dark-theme tokens first.