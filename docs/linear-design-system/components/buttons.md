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
