ATTENTION: This folder is currently being re-organised. Apologies
in advance for any confusion!

All files in this folder with the '.less' extension specify entry points for CSS files.

There are 2 exceptions:
* legacy.less (kept for legacy reasons - soon to be removed)
* common.less (a common set of styles that should apply to all pages)

## Render blocking CSS
LESS files that begin with the 'page-' prefix specify CSS files which will be loaded in the head of a document as render blocking CSS. Be careful when adding CSS to these files.

## CSS loaded via JavaScript
LESS files that begin with the 'js-' prefix specify CSS files which will be loaded in the document via JavaScript. By design they will not block a page from rendering.

# Components

Groups of styles make up a "component". A "component" is a feature of a page.

If you are designing a component, please place the CSS for that component inside the components folder and reference it from one or more of the entry points.

Note that all.less is an entry point for styles that load on all pages.
If a component is referenced in 'all.less' it should not be referenced in any of the other LESS files.