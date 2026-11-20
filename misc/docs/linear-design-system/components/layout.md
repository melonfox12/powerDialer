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
