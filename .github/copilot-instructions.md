# GitHub Copilot Instructions for Open Library

This file provides custom instructions for GitHub Copilot when reviewing Pull Requests and assisting with code development for the Open Library project.

## Front-End Code Review Guidelines

When reviewing Pull Requests that contain front-end changes (especially CSS, LESS, HTML templates, or JavaScript files), please apply the following guidelines from our [Frontend Guide](https://github.com/internetarchive/openlibrary/wiki/Frontend-Guide).

### Detecting Front-End Changes

A PR contains front-end changes if it modifies files in these locations:
- `static/css/**/*.less` - CSS/LESS stylesheets
- `static/css/**/*.css` - CSS files
- `openlibrary/templates/**/*.html` - HTML templates
- `openlibrary/macros/**/*.html` - Template macros
- `openlibrary/plugins/openlibrary/js/**/*.js` - JavaScript files
- `static/build/**` - Built assets (note: these should generally not be committed directly)

### CSS Conventions and Best Practices

#### 1. Write Native CSS (Avoid LESS-specific features)

We are migrating away from LESS, so avoid using LESS-specific features:

**❌ Avoid:**
```less
/* Mixins */
.border-radius(@radius) {
  border-radius: @radius;
}
.my-component {
  .border-radius(5px);
}

/* Color functions */
.my-button {
  background: lighten(@primary-color, 10%);
  color: fade(@text-color, 80%);
}
```

**✅ Preferred:**
```css
/* Use standard CSS */
.my-component {
  border-radius: 5px;
}

.my-button {
  background: #007bff; /* Use actual color values or CSS custom properties */
  color: rgba(0, 0, 0, 0.8);
}
```

#### 2. Use BEM Notation

We use [BEM (Block Element Modifier)](https://getbem.com/) for CSS class naming in most instances. 

**Exceptions:** Web Components and Vue components (which provide built-in CSS encapsulation).

**✅ BEM Examples:**
```css
/* Block */
.book-card { }

/* Element (part of the block) */
.book-card__title { }
.book-card__cover { }

/* Modifier (variation of block or element) */
.book-card--featured { }
.book-card__title--large { }
```

#### 3. Avoid Styling Bare HTML Elements

**❌ Avoid:**
```css
/* Affects every paragraph globally */
p { margin-bottom: 1rem; }
```

**✅ Acceptable in specific contexts:**
```css
/* In a prose/content context that's explicitly opted into */
.prose p { margin-bottom: 1em; }
```

**✅ Preferred:**
```css
/* Explicit class */
.book-description__text { margin-bottom: 1em; }
```

#### 4. Avoid IDs for Styling

IDs have high specificity and are meant for JavaScript hooks or anchor links, not styling.

**❌ Avoid:**
```css
#main-header { }
```

**✅ Preferred:**
```css
.main-header { }
```

#### 5. Avoid Deep Nesting

Deeply nested selectors make it difficult to trace where styles are coming from and lead to specificity battles.

**❌ Avoid:**
```css
.book-list .book-card .book-card__title { }
```

**✅ Preferred:**
```css
.book-card__title { }
```

#### 6. Use Design Tokens (Not Magic Numbers)

Design tokens provide consistent styling and make global updates easier. We use a two-tier system:

1. **Primitives** - Raw values (DON'T use directly)
2. **Semantic tokens** - Intent-based names (USE these)

**Design token files location:**
- `static/css/less/borders.less` - Border styles and widths
- `static/css/less/colors.less` - Color palette
- `static/css/less/font-families.less` - Font definitions
- `static/css/less/line-heights.less` - Line height values
- `static/css/less/breakpoints.less` - Responsive breakpoints

**❌ Don't do this:**
```less
/* Using primitives directly */
.my-card {
  border-radius: @border-radius-lg;  /* Use @border-radius-card instead */
}

/* Hardcoding values */
.profile-pic {
  border-radius: 50%;  /* Use @border-radius-avatar instead */
}
```

**✅ Do this:**
```less
/* Use semantic tokens */
.my-card {
  border-radius: @border-radius-card;
}

.profile-pic {
  border-radius: @border-radius-avatar;
}
```

**Example Border Radius Semantic Tokens:**
- `@border-radius-button` - For buttons, tabs
- `@border-radius-input` - For inputs, textareas
- `@border-radius-thumbnail` - For small images
- `@border-radius-media` - For large images, videos
- `@border-radius-card` - For cards
- `@border-radius-overlay` - For dialogs, modals
- `@border-radius-badge` - For badges, tags
- `@border-radius-notification` - For notifications, alerts
- `@border-radius-avatar` - For avatars, profile pictures

**Note:** Design Tokens implementation began December 2025 and is a work in progress. See [issue #11555](https://github.com/internetarchive/openlibrary/issues/11555) for progress.

### Bundle Size Considerations

When reviewing CSS changes, check for bundle size impacts:

**Watch for:**
- CSS files on the critical path (render-blocking)
- Increases to bundle sizes beyond allowed thresholds
- Example error: `FAIL static/build/page-plain.css: 18.81KB > maxSize 18.8KB (gzip)`

**Recommendations:**
- Consider placing styles in JavaScript entrypoint files (e.g., `<file_name>--js.less`)
- Load via `static/css/js-all.less` using `@import` for non-critical CSS
- JavaScript-loaded CSS has a higher bundle size threshold

**Reference:** See [CSS directory README](https://github.com/internetarchive/openlibrary/blob/master/static/css/README.md) for information on render-blocking vs JS-loaded CSS files.

### Build Process

After CSS or JS changes, assets must be recompiled:

**One-off build:**
```bash
docker compose run --rm home npm run build-assets
```

**Watch for changes:**
```bash
# For CSS
docker compose run --rm home npm run-script watch:css

# For JavaScript
docker compose run --rm home npm run-script watch
```

### File Organization

- **CSS/LESS files:** `static/css/`
- **JavaScript files:** `openlibrary/plugins/openlibrary/js/`
- **Templates:** `openlibrary/templates/`
- **Macros:** `openlibrary/macros/`
- **Built assets:** `static/build/` (should not be committed directly)

## Additional Review Considerations

### HTML Templates

- Open Library uses [Templetor](http://webpy.org/docs/0.3/templetor) template syntax
- Templates are located in `openlibrary/templates/`
- Macros are in `openlibrary/macros/`
- The home page is cached; changes may require `docker compose restart memcached`

### JavaScript

- Most JavaScript lives in `openlibrary/plugins/openlibrary/js/`
- New JavaScript files must be linked through `index.js`
- We use jQuery and Vue
- Follow the existing patterns for hooking up JavaScript to templates

### Browser Support

- Support Firefox and Chromium-based browsers (desktop and mobile)
- Things should function in IE11 but can look wonky
- Use progressive enhancement approaches

## General Code Review Guidelines

Beyond front-end specific guidelines:

1. **Code Quality:** Check for readability, maintainability, and adherence to project conventions
2. **Security:** Look for potential security vulnerabilities
3. **Performance:** Consider performance implications of changes
4. **Testing:** Ensure changes include appropriate tests where applicable
5. **Documentation:** Verify that significant changes are documented

## How to Use These Instructions

When reviewing PRs:
1. First, identify if the PR contains front-end changes by checking modified file paths
2. If front-end changes are present, apply the CSS conventions and best practices above
3. Provide constructive feedback with specific examples
4. Continue to review all other aspects of the PR (backend, tests, documentation, etc.)
5. These front-end guidelines are **additional** checks, not a replacement for comprehensive code review
