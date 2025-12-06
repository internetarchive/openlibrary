# Design Tokens System

A comprehensive, DRY design tokens system for OpenLibrary that reduces magic numbers and increases consistency across the application. Based on the industry-standard two-layer token pattern: **Primitives** → **Semantic Tokens**.

## Overview

This system organizes design values into two layers for maximum flexibility and maintainability:

### Layer 1: Primitives
Raw, base values that are the foundation of the design system. These provide a curated palette that ensures visual harmony. **Never use primitives directly in components.**

### Layer 2: Semantic Tokens
Design intent-based tokens that map to primitive values. Their names communicate **where** and **how** they should be used. These are what you reference throughout the app.

## Benefits

- **DRY (Don't Repeat Yourself)**: Single point of control for design changes
- **Consistency**: All components use the same values
- **Easy Updates**: Changing `@radius-card: @radius-lg` → `@radius-card: @radius-xl` updates all cards instantly
- **Scalability**: New components inherit from established patterns
- **Documentation**: Token names clearly communicate design intent
- **Maintainability**: Reduces scattered magic numbers throughout the codebase

## Directory Structure

```
static/css/
├── tokens/                           # Design tokens system
│   ├── index.less                   # Master import file
│   │
│   ├── PRIMITIVES (Raw values)
│   ├── radius-primitives.less       # Border radius base values
│   ├── spacing-primitives.less      # Padding/margin/gap base values
│   ├── border-primitives.less       # Border width/style base values
│   ├── color-primitives.less        # Color base values (all hues)
│   ├── font-family-primitives.less  # Font stack base values
│   ├── font-size-primitives.less    # Font size base values
│   └── font-weight-primitives.less  # Font weight base values
│   │
│   └── SEMANTIC TOKENS (Design intent)
│       ├── radius-semantic.less     # Where radius values are used
│       ├── spacing-semantic.less    # Where spacing is used (padding/margin/gap)
│       ├── border-semantic.less     # Where borders are used
│       ├── color-semantic.less      # Where colors are used (text/bg/state)
│       ├── font-semantic.less       # Typography combinations
│       └── line-height.less         # Line height values
│
└── less/
    └── index.less                   # Now imports tokens/index.less
```

## Token Categories

### 1. Border Radius

**Primitives** (`radius-primitives.less`):
```less
@radius-sm: 2px;
@radius-md: 4px;
@radius-lg: 8px;
@radius-xl: 12px;
@radius-2xl: 16px;
@radius-3xl: 24px;
@radius-full: 100%;
```

**Semantic** (`radius-semantic.less`):
```less
@radius-button: @radius-md;        // buttons, tabs, pills
@radius-input: @radius-md;         // input fields
@radius-card: @radius-lg;          // cards, panels
@radius-container: @radius-lg;     // containers
@radius-overlay: @radius-xl;       // dialogs, modals
@radius-badge: @radius-sm;         // badges, tags
@radius-avatar: @radius-full;      // circular avatars
```

**Why this matters**: Want to increase card border radius from 8px to 16px? Change one line:
```less
@radius-card: @radius-2xl;  // All cards update instantly
```

### 2. Spacing

**Primitives** (`spacing-primitives.less`):
Uses a 4px base unit scale for consistency:
```less
@space-1: 4px;      // 1 unit
@space-2: 8px;      // 2 units
@space-3: 12px;     // 3 units
@space-4: 16px;     // 4 units
// ... up to @space-24: 96px
```

**Semantic** (`spacing-semantic.less`):
```less
// Padding
@padding-xs: @space-1;
@padding-sm: @space-2;
@padding-md: @space-3;
@padding-lg: @space-4;
@padding-button: @space-3;
@padding-input: @space-3;
@padding-card: @space-4;

// Margin
@margin-xs: @space-1;
@margin-sm: @space-2;
@margin-md: @space-4;
@margin-lg: @space-6;
@margin-xl: @space-8;

// Gaps (for flexbox/grid)
@gap-xs: @space-1;
@gap-sm: @space-2;
@gap-md: @space-3;
@gap-lg: @space-4;
@gap-xl: @space-6;
```

### 3. Colors

**Primitives** (`color-primitives.less`):
All colors organized by hue with numeric suffixes:
```less
// Blues
@color-blue-1: hsl(210, 100%, 20%);
@color-blue-2: hsl(202, 96%, 28%);
@color-blue-4: hsl(202, 96%, 37%);  // Primary brand blue

// Greys
@color-grey-1: hsl(0, 0%, 5%);      // Near black
@color-grey-8: hsl(0, 0%, 46.3%);   // Accessible on white
@color-grey-16: hsl(0, 0%, 98%);    // Near white

// Reds, greens, oranges, etc...
```

**Semantic** (`color-semantic.less`):
Intent-based color tokens:
```less
// Text colors
@text-primary: @color-grey-3;       // Main text
@text-secondary: @color-grey-7;     // Muted text
@text-link: @color-blue-2;          // Links
@text-error: @color-red-2;          // Error messages
@text-success: @color-green-3;      // Success messages

// Backgrounds
@bg-primary: @color-white;
@bg-secondary: @color-grey-16;
@bg-overlay: @color-white;

// Button states
@button-primary-bg: @color-blue-4;
@button-primary-hover-bg: darken(@button-primary-bg, 10%);
@button-disabled-bg: @color-grey-11;

// Input states
@input-border: @color-grey-11;
@input-border-focus: @color-blue-4;
@input-border-error: @color-red-2;

// Card surfaces
@surface-card-bg: @color-white;
@surface-card-border: @color-grey-11;
@surface-card-shadow: rgba(0, 0, 0, 0.08);

// State colors
@state-success-bg: lighten(@color-green-3, 35%);
@state-error-bg: lighten(@color-red-2, 35%);
@state-warning-bg: lighten(@color-orange-1, 35%);
@state-info-bg: lighten(@color-blue-4, 35%);
```

### 4. Borders

**Primitives** (`border-primitives.less`):
```less
@border-width-thin: 1px;
@border-width-base: 1px;
@border-width-thick: 2px;
@border-width-heavy: 3px;

@border-style-solid: solid;
@border-style-dashed: dashed;
```

**Semantic** (`border-semantic.less`):
```less
// Dividers
@border-divider: @border-width-thin @border-style-solid @light-grey;
@border-divider-dark: @border-width-thin @border-style-solid @mid-grey;

// Inputs
@border-input: @border-width-thin @border-style-solid @light-grey;
@border-input-focus: @border-width-thin @border-style-solid @primary-blue;
@border-input-error: @border-width-thin @border-style-solid @red;

// Emphasis
@border-focus: @border-width-thick @border-style-solid @primary-blue;
@border-error: @border-width-thick @border-style-solid @red;
```

### 5. Typography

#### Font Families (Primitives)
```less
@font-family-sans: -apple-system, BlinkMacSystemFont, "Segoe UI", ...
@font-family-serif: Georgia, "Palatino Linotype", ...
@font-family-mono: "Lucida Console", "Courier New", ...
```

#### Font Sizes (Primitives)
Modular scale with display, headline, title, body, label, caption, and code sizes:
```less
@font-size-display-lg: 57px;
@font-size-headline-lg: 32px;
@font-size-title-lg: 22px;
@font-size-body-lg: 16px;  // Base: 1rem
@font-size-label-lg: 14px;
@font-size-caption-lg: 12px;
```

#### Font Weights (Primitives)
```less
@font-weight-light: 300;
@font-weight-normal: 400;
@font-weight-medium: 500;
@font-weight-semi-bold: 600;
@font-weight-bold: 700;
```

#### Line Heights (Primitives & Semantic)
```less
@line-height-tight: 1.1;        // Headlines
@line-height-snug: 1.2;         // Subheadings
@line-height-normal: 1.35;      // Normal text
@line-height-relaxed: 1.5;      // Body text
@line-height-loose: 1.75;       // Sparse text
```

## Usage Examples

### Example 1: Creating a Button Component
```less
.button {
  padding: @padding-button @padding-button;
  border-radius: @radius-button;
  border: @border-button;
  font-size: @font-size-label-lg;
  font-weight: @font-weight-medium;
  line-height: @line-height-label;
  background-color: @button-primary-bg;
  color: @text-inverse;
  
  &:hover {
    background-color: @button-primary-hover-bg;
  }
  
  &:focus {
    border: @border-focus;
  }
  
  &:disabled {
    background-color: @button-disabled-bg;
    color: @button-primary-disabled-text;
  }
}
```

### Example 2: Creating a Card Component
```less
.card {
  padding: @padding-card;
  border: @border-card;
  border-radius: @radius-card;
  background-color: @surface-card-bg;
  box-shadow: 0 2px 4px @surface-card-shadow;
  
  // Increase card padding and border radius globally
  // Just change two lines in radius-semantic.less and spacing-semantic.less
}
```

### Example 3: Creating a Form Input
```less
input {
  padding: @padding-input;
  border: @border-input;
  border-radius: @radius-input;
  font-size: @font-size-body-md;
  line-height: @line-height-form;
  
  &:hover {
    border: @border-input-hover;
  }
  
  &:focus {
    border: @border-input-focus;
    outline: none;
  }
  
  &:disabled {
    background-color: @input-disabled-bg;
    color: @input-disabled-text;
    border: @border-input-disabled;
  }
  
  &.error {
    border: @border-input-error;
  }
}
```

### Example 4: Creating a Message Alert
```less
.message {
  padding: @padding-card;
  border-radius: @radius-card;
  border-left: 3px solid;
  line-height: @line-height-body;
  
  &--success {
    background-color: @state-success-bg;
    color: @state-success-text;
    border-color: @state-success-border;
  }
  
  &--error {
    background-color: @state-error-bg;
    color: @state-error-text;
    border-color: @state-error-border;
  }
  
  &--warning {
    background-color: @state-warning-bg;
    color: @state-warning-text;
    border-color: @state-warning-border;
  }
}
```

## Migration Guide

### Phase 1: New Components
Start using semantic tokens for all new components immediately:
```less
.new-component {
  padding: @padding-card;
  border-radius: @radius-card;
  color: @text-primary;
  background-color: @bg-primary;
}
```

### Phase 2: Refactor Existing Components
Replace hardcoded values gradually:

**Before:**
```less
.button-cta {
  padding: 8px 16px;
  border-radius: 5px;
  color: #ffffff;
  background-color: hsl(202, 96%, 37%);
}
```

**After:**
```less
.button-cta {
  padding: @padding-button;
  border-radius: @radius-button;
  color: @text-inverse;
  background-color: @button-primary-bg;
}
```

### Phase 3: Remove Legacy Variables
Once all components are updated, legacy color and size variables can be fully deprecated.

## Backward Compatibility

All legacy variable names are preserved in `color-semantic.less` for backward compatibility:
```less
// Legacy variables now map to semantic tokens
@primary-blue: @color-blue-4;
@link-blue: @color-blue-2;
@light-grey: @color-grey-11;
// ... and many more
```

This allows gradual migration without breaking existing code.

## Maintaining the System

### Adding a New Token

1. **Add to primitives** if it's a new base value
2. **Add to semantic** file with a clear, descriptive name
3. **Update this README** with the new token
4. **Use throughout** the component or page

Example: Adding a new border radius for compact buttons:
```less
// In radius-primitives.less (if needed)
@radius-compact: 3px;

// In radius-semantic.less
@radius-button-compact: @radius-sm;  // Use existing primitive
```

### Updating Existing Tokens

Change once, cascade everywhere:

**To increase padding throughout the app:**
1. Modify the primitive: `@space-4: 16px` → `@space-4: 18px`
2. All tokens using `@space-4` update automatically

**To change how card radius relates to other components:**
1. Modify the semantic: `@radius-card: @radius-lg` → `@radius-card: @radius-xl`
2. All cards update instantly

## File Organization Rationale

- **Separate primitives and semantics**: Allows changes at either layer without confusion
- **Separate by category**: Easy to find and update related tokens
- **Central index.less**: Single import point for all tokens
- **Legacy compatibility**: Gradual migration path for existing code

## Tools & IDE Support

Most IDEs provide autocomplete for LESS variables:
- **VS Code**: Type `@` to see all available tokens
- **IntelliJ**: Cmd+Space for variable completion
- **Sublime**: Install LESS syntax highlighting

## Best Practices

1. **Always use semantic tokens** - Never use primitives in components
2. **Use existing values first** - Check what tokens exist before creating new ones
3. **Name clearly** - Token names should communicate their purpose (`@text-error` not `@red`)
4. **Group related tokens** - Keep button colors together, spacing together, etc.
5. **Document intent** - Comments explaining when/where to use tokens
6. **Avoid duplication** - Don't create multiple tokens for the same intent
7. **Maintain consistency** - Use the same token for the same purpose across components

## References

- [Design Tokens @ Figma](https://www.figma.com/blog/design-tokens/)
- [Design Tokens at Shopify](https://polaris.shopify.com/design/design-tokens/overview)
- [CSS Variables vs Design Tokens](https://www.smashingmagazine.com/2022/04/functional-css-design-tokens/)

## Contributing

When adding new tokens:
1. Follow the naming convention: `@[category]-[purpose]-[state]`
2. Use descriptive names that communicate intent
3. Document in both the file and this README
4. Ensure backward compatibility where possible
5. Test with existing components

---

**Last Updated**: December 2025  
**System Version**: 1.0 - Foundation Layer  
**Status**: ✅ Ready for use in new components
