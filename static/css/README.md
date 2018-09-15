All files in this folder with the '.less' extension specify entry points for CSS files.
Each entry point should correspond to a group of pages.

If you are designing a component, please place the CSS for that component
inside the components folder and reference it from one or more of the entry
points.

Note that all.less is an entry point for styles that load on all pages.
If a component is referenced in 'all.less' it should not be referenced in any of the other LESS files.