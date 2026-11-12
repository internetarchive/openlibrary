import { describe, test, expect } from 'vitest';
import { TableRow } from '../../../openlibrary/plugins/openlibrary/js/merge-request-table/MergeRequestTable/TableRow.js';

// GHSA-6xcf: updateCommentViews built the commenter label with
// `innerHTML = `@${this.username}``. username is user-controlled, so an HTML
// payload would execute. The fix uses safe DOM construction. We exercise the
// method directly (the constructor is heavily DOM-coupled) to prove the
// username is rendered as inert text.
function makeRow(username) {
    const tr = Object.create(TableRow.prototype);
    tr.username = username;
    tr.commentPreview = document.createElement('div');
    tr.commentsDisplay = document.createElement('div');
    tr.commentCountDisplay = document.createElement('div');
    tr.commentCountDisplay.innerText = '0';
    return tr;
}

describe('TableRow.updateCommentViews (GHSA-6xcf DOM-XSS)', () => {
    test('renders a malicious username as text, not markup', () => {
        const payload = '<img src=x onerror="window.__xss=1">';
        const tr = makeRow(payload);
        tr.updateCommentViews('a comment');

        expect(tr.commentsDisplay.querySelector('img')).toBeNull();
        expect(tr.commentsDisplay.querySelector('.commenter').textContent).toBe(`@${payload}`);
    });

    test('preserves the commenter label and comment text for benign input', () => {
        const tr = makeRow('alice');
        tr.updateCommentViews('hello world');

        expect(tr.commentsDisplay.querySelector('.commenter').textContent).toBe('@alice');
        expect(tr.commentsDisplay.textContent).toContain('hello world');
        expect(tr.commentCountDisplay.innerText).toBe(1);
    });
});
