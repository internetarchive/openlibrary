# Lit Web Components

This directory contains web components built with [Lit](https://lit.dev/), a lightweight library for building fast, reusable web components.

## Why Lit?

- **Small bundle size**: ~5KB core library vs 300KB+ for Vue components
- **Web Standards**: Built on native Web Components APIs
- **Framework agnostic**: Works with any framework or vanilla JS
- **Modern DX**: Reactive properties, declarative templates, scoped styles

## Directory Structure

```
openlibrary/components-lit/
├── ol-button.js          # Button component
├── README.md             # This file
└── [future-component].js # Additional components...
```

## Building Components

Components are built automatically as part of the standard build process:

```bash
# Build all components (Vue + Lit)
make components

# Or use npm
npm run build-assets:components
```

Built files are output to: `static/build/components/production/`

## Using Components in Templates

Load and use components in your Mako templates:

```html
<!-- Load the component -->
<script type="module" src="/static/build/components/production/ol-button.js"></script>

<!-- Use the component -->
<ol-button variant="primary" size="medium">Click Me</ol-button>
```

## Available Components

### ol-button

A customizable button component with variants, sizes, and loading states.

**Properties:**

- `variant` (String): 'primary' | 'secondary' | 'destructive' (default: 'primary')
- `size` (String): 'small' | 'medium' | 'large' (default: 'medium')
- `loading` (Boolean): Shows loading state and disables button (default: false)

**Examples:**

```html
<!-- Primary button (default) -->
<ol-button>Submit</ol-button>

<!-- Secondary outlined button -->
<ol-button variant="secondary">Cancel</ol-button>

<!-- Destructive action -->
<ol-button variant="destructive" size="small">Delete</ol-button>

<!-- Loading state -->
<ol-button loading>Processing</ol-button>

<!-- Large primary button -->
<ol-button variant="primary" size="large">Get Started</ol-button>
```

**Event Handling:**

All native button events bubble up naturally. Attach event listeners as you would with regular buttons:

```html
<ol-button onclick="handleClick()">Click Me</ol-button>
<ol-button onmousedown="handleMouseDown()">Press Me</ol-button>
```

Or with JavaScript:

```javascript
const button = document.querySelector('ol-button');
button.addEventListener('click', (e) => {
  console.log('Button clicked!');
});
```

**Form Submission:**

The component handles form submission automatically when `type="submit"` is set:

```html
<form action="/login" method="post">
  <input type="text" name="username" />
  <ol-button type="submit">Log In</ol-button>
</form>
```

Note: Due to Shadow DOM encapsulation, the component manually finds and submits the closest form element when clicked. This is a workaround for the limitation that buttons inside Shadow DOM cannot directly submit forms in the light DOM.

## Development

### Creating New Components

1. Create a new `.js` file in this directory
2. Import Lit: `import { LitElement, html, css } from 'lit';`
3. Define your component class extending `LitElement`
4. Register with `customElements.define('ol-component-name', YourComponent);`
5. Build with `make components`

### Component Template

```javascript
import { LitElement, html, css } from 'lit';

export class OLMyComponent extends LitElement {
    static properties = {
        myProp: { type: String }
    };

    static styles = css`
        :host {
            display: block;
        }
        /* Your styles here */
    `;

    constructor() {
        super();
        this.myProp = 'default';
    }

    render() {
        return html`
            <div>Content: ${this.myProp}</div>
        `;
    }
}

customElements.define('ol-my-component', OLMyComponent);
```

## Testing

After building, test your components:

1. Start the development server: `docker compose up`
2. Navigate to a page that uses your component
3. Open browser DevTools to inspect and debug
4. Test all properties and event handlers

## Resources

- [Lit Documentation](https://lit.dev/)
- [Lit Playground](https://lit.dev/playground/)
- [Web Components Best Practices](https://web.dev/custom-elements-best-practices/)
- [Open Library Frontend Guide](https://github.com/internetarchive/openlibrary/wiki/Frontend-Guide)

## When to Use Lit vs Vue

**Use Lit for:**
- Simple, reusable UI components (buttons, inputs, cards)
- Components that need minimal bundle size
- Standalone components with no complex state management

**Use Vue for:**
- Complex, stateful applications (BarcodeScanner, LibraryExplorer)
- Components requiring advanced reactivity
- When you need a full framework ecosystem

