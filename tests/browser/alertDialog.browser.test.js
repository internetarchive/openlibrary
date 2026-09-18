/**
 * Browser-mode tests for olConfirm() / olAlert() and the <ol-dialog> API they
 * rest on: alert role, close(returnValue), and label-close. Real <dialog> top
 * layer, real focus, real keyboard — jsdom implements none of them.
 */
import { afterEach, beforeAll, expect, test } from 'vitest';
import { page, userEvent } from 'vitest/browser';
import '../../openlibrary/components/lit/OLButton.js';
import '../../openlibrary/components/lit/OlDialog.js';
import { olAlert, olConfirm } from '../../openlibrary/components/lit/alert-dialog.js';

beforeAll(() => {
    // Document styles beat :host, so this zeroes the open/close animation.
    const style = document.createElement('style');
    style.textContent = 'ol-dialog { --ol-dialog-animation-duration: 0ms; }';
    document.head.append(style);
});

afterEach(() => {
    document.querySelectorAll('ol-dialog, button.trigger').forEach((el) => el.remove());
});

/** The dialog olConfirm() appended, once it has rendered and opened. */
async function openedDialog() {
    await expect.poll(() => document.querySelector('ol-dialog[open]')).toBeTruthy();
    const dialog = document.querySelector('ol-dialog[open]');
    await dialog.updateComplete;
    // Initial focus is set in a rAF.
    await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));
    return dialog;
}

function button(dialog, label) {
    return [...dialog.querySelectorAll('ol-button')].find((b) => b.textContent === label);
}

test('resolves true when the confirm button is pressed, then removes the dialog', async() => {
    const result = olConfirm({ title: 'Delete this list?', message: 'This can’t be undone.', confirmLabel: 'Delete list' });
    const dialog = await openedDialog();

    await userEvent.click(button(dialog, 'Delete list'));

    await expect(result).resolves.toBe(true);
    expect(document.querySelector('ol-dialog')).toBeNull();
});

test('resolves false on Cancel, Escape, the backdrop, and the close button', async() => {
    const dismissals = {
        cancel: (dialog) => userEvent.click(button(dialog, 'Cancel')),
        escape: () => userEvent.keyboard('{Escape}'),
        backdrop: (dialog) => dialog.dialog.dispatchEvent(new MouseEvent('click', { bubbles: true })),
        close: (dialog) => userEvent.click(dialog.shadowRoot.querySelector('.close-button')),
    };
    for (const [name, dismiss] of Object.entries(dismissals)) {
        const result = olConfirm({ title: `Dismiss via ${name}?` });
        await dismiss(await openedDialog());
        await expect(result, name).resolves.toBe(false);
    }
});

test('announces as an alertdialog named by the title and described by the message', async() => {
    olConfirm({ title: 'Delete this list?', message: 'This can’t be undone.' });
    const dialog = await openedDialog();

    await expect.element(page.getByRole('alertdialog', { name: 'Delete this list?' })).toBeVisible();
    const inner = dialog.dialog;
    const describedBy = dialog.shadowRoot.getElementById(inner.getAttribute('aria-describedby'));
    expect(describedBy.classList.contains('body')).toBe(true);

    await userEvent.keyboard('{Escape}');
});

test('destructive confirmations focus Cancel; others focus the confirm button', async() => {
    olConfirm({ title: 'Delete?', confirmLabel: 'Delete', destructive: true });
    let dialog = await openedDialog();
    expect(document.activeElement).toBe(button(dialog, 'Cancel'));
    expect(button(dialog, 'Delete').variant).toBe('primary');
    expect(button(dialog, 'Delete').tone).toBe('danger');
    await userEvent.keyboard('{Escape}');
    await expect.poll(() => document.querySelector('ol-dialog')).toBeNull();

    olConfirm({ title: 'Return this book?', confirmLabel: 'Return' });
    dialog = await openedDialog();
    expect(document.activeElement).toBe(button(dialog, 'Return'));
    expect(button(dialog, 'Return').variant).toBe('primary');
    expect(button(dialog, 'Return').tone).toBeUndefined();
    await userEvent.keyboard('{Escape}');
});

test('Enter on the default focus answers the question', async() => {
    const result = olConfirm({ title: 'Delete?', destructive: true });
    await openedDialog();
    await userEvent.keyboard('{Enter}');
    await expect(result).resolves.toBe(false);
});

test('string messages are text, never HTML; templates are cloned', async() => {
    olConfirm({ title: 'Remove?', message: '<img src=x onerror=alert(1)>' });
    let dialog = await openedDialog();
    expect(dialog.querySelector('img')).toBeNull();
    expect(dialog.textContent).toContain('<img src=x onerror=alert(1)>');
    await userEvent.keyboard('{Escape}');
    await expect.poll(() => document.querySelector('ol-dialog')).toBeNull();

    const template = document.createElement('template');
    template.innerHTML = 'Remove <strong>Dune</strong> from this list?';
    olConfirm({ title: 'Remove?', message: template });
    dialog = await openedDialog();
    expect(dialog.querySelector('strong').textContent).toBe('Dune');
    expect(template.content.querySelector('strong')).not.toBeNull();
    await userEvent.keyboard('{Escape}');
});

test('passes translated labels through, including the close button name', async() => {
    olConfirm({ title: '¿Eliminar?', confirmLabel: 'Eliminar', cancelLabel: 'Cancelar', labelClose: 'Cerrar' });
    const dialog = await openedDialog();

    expect(button(dialog, 'Eliminar')).toBeTruthy();
    expect(button(dialog, 'Cancelar')).toBeTruthy();
    expect(dialog.shadowRoot.querySelector('.close-button').getAttribute('aria-label')).toBe('Cerrar');
    await userEvent.keyboard('{Escape}');
});

test('restores focus to the trigger after closing', async() => {
    const trigger = document.createElement('button');
    trigger.className = 'trigger';
    trigger.textContent = 'Delete';
    document.body.append(trigger);
    trigger.focus();

    const result = olConfirm({ title: 'Delete?' });
    await openedDialog();
    await userEvent.keyboard('{Escape}');
    await result;

    await expect.poll(() => document.activeElement).toBe(trigger);
});

test('olAlert resolves once acknowledged', async() => {
    const result = olAlert({ title: 'No primary record', message: 'Select one first.', okLabel: 'Got it' });
    const dialog = await openedDialog();

    expect(dialog.querySelectorAll('ol-button')).toHaveLength(1);
    expect(document.activeElement).toBe(button(dialog, 'Got it'));
    await userEvent.click(button(dialog, 'Got it'));
    await expect(result).resolves.toBeUndefined();
});

test('a confirmation opened from inside a dialog traps Tab and leaves the parent open', async() => {
    const parent = document.createElement('ol-dialog');
    parent.label = 'Notes';
    parent.innerHTML = '<textarea></textarea><button class="delete-note">Delete note</button>';
    document.body.append(parent);
    parent.open = true;
    await parent.updateComplete;

    const result = olConfirm({ title: 'Delete this note?', confirmLabel: 'Delete', destructive: true });
    await expect.poll(() => document.querySelectorAll('ol-dialog[open]').length).toBe(2);
    const confirmDialog = [...document.querySelectorAll('ol-dialog[open]')].find((d) => d !== parent);
    await confirmDialog.updateComplete;
    await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)));

    let parentFocused = 0;
    parent.addEventListener('focusin', () => parentFocused++);

    for (let i = 0; i < 4; i++) {
        await userEvent.keyboard('{Tab}');
        const active = document.activeElement;
        expect(confirmDialog.contains(active) || confirmDialog.shadowRoot.contains(confirmDialog.shadowRoot.activeElement)).toBe(true);
        expect(parent.contains(active)).toBe(false);
    }
    expect(parentFocused).toBe(0);

    await userEvent.keyboard('{Escape}');
    await expect(result).resolves.toBe(false);
    expect(parent.open).toBe(true);
    expect(parent.dialog.open).toBe(true);
});

test('<ol-dialog> close(returnValue) reports it on ol-close and ol-after-close, and resets on reopen', async() => {
    const dialog = document.createElement('ol-dialog');
    dialog.label = 'Save?';
    document.body.append(dialog);
    dialog.open = true;
    await dialog.updateComplete;

    const seen = [];
    dialog.addEventListener('ol-close', (e) => seen.push(['close', e.detail.returnValue]));
    dialog.addEventListener('ol-after-close', (e) => seen.push(['after-close', e.detail.returnValue]));

    dialog.close('save');
    await expect.poll(() => seen.length).toBe(2);
    expect(seen).toEqual([['close', 'save'], ['after-close', 'save']]);
    expect(dialog.returnValue).toBe('save');

    dialog.open = true;
    await dialog.updateComplete;
    expect(dialog.returnValue).toBe('');
    await userEvent.keyboard('{Escape}');
    await expect.poll(() => seen.length).toBe(4);
    expect(seen.slice(2)).toEqual([['close', ''], ['after-close', '']]);
});

test('the confirmation gets the small width preset', async() => {
    // width drives :host([width=…]) rules, so the property has to reach the attribute.
    olConfirm({ title: 'Delete?' });
    const dialog = await openedDialog();

    expect(dialog.getAttribute('width')).toBe('small');
    expect(dialog.dialog.getBoundingClientRect().width).toBe(400);

    await userEvent.keyboard('{Escape}');
});

test('<ol-dialog> keeps role="dialog" and no description unless alert is set', async() => {
    const dialog = document.createElement('ol-dialog');
    dialog.label = 'Edit profile';
    document.body.append(dialog);
    await dialog.updateComplete;

    expect(dialog.dialog.getAttribute('role')).toBe('dialog');
    expect(dialog.dialog.hasAttribute('aria-describedby')).toBe(false);
    expect(dialog.shadowRoot.querySelector('.close-button').getAttribute('aria-label')).toBe('Close dialog');
});
