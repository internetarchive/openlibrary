import { describe, test, expect } from 'vitest';
import { safeSameOriginUrl } from '../../../openlibrary/plugins/openlibrary/js/breadcrumb_select/index.js';

// GHSA-6xcf: breadcrumb <select> values flow into `window.location`. A value is
// user-influenced, so a `javascript:`/`data:` or cross-origin value must never
// be navigated to. safeSameOriginUrl is the guard; these prove the vector is
// closed (each malicious case would have navigated before the guard existed).
describe('safeSameOriginUrl (GHSA-6xcf breadcrumb navigation guard)', () => {
    test('allows a same-origin relative path', () => {
        expect(safeSameOriginUrl('/works/OL1W')).toBe(`${window.location.origin}/works/OL1W`);
    });

    test('rejects a javascript: URI (XSS vector)', () => {
        expect(safeSameOriginUrl('javascript:window.__xss=1')).toBeNull();
    });

    test('rejects a data: URI', () => {
        expect(safeSameOriginUrl('data:text/html,<script>window.__xss=1</script>')).toBeNull();
    });

    test('rejects a cross-origin URL (open-redirect/phishing vector)', () => {
        expect(safeSameOriginUrl('https://evil.example/phish')).toBeNull();
    });
});
