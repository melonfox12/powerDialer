# Linear Design System — Theme

Companion: [components.md](components.md)

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

