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
