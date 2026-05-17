// Central viewport breakpoint constants.
// CSS media queries in component stylesheets must duplicate these as literals.
export const BREAKPOINTS = {
    mobile: 600,  // full-screen overlay threshold (JS + CSS @media)
    narrow: 785,  // icon-only trigger in header   (CSS @media only)
    wide: 900,  // panel right-align vs. centered (JS _positionPanel only)
};
