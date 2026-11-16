/**
 * Tag chips (forms/tag_chips.html.jinja): a many-tags field as chips that toggle,
 * with a hidden input per picked key so the form posts the picks under the
 * group's name. A chip the subjects suggested carries them in ``data-subjects``:
 * hovering or focusing it lights those subjects (``[data-subject]``) in its form.
 * @param {HTMLElement} group - a ``[data-many-choice]`` holding ``ol-chip[data-value]`` elements
 * @returns {void}
 */
export function initTagChips(group) {
    const name = group.dataset.manyChoice;
    const scope = group.closest('form') || document;
    const light = (chip, on) => {
        const subjects = JSON.parse(chip.dataset.subjects);
        scope.querySelectorAll('[data-subject]').forEach(el => el.toggleAttribute('data-lit', on && subjects.includes(el.dataset.subject)));
    };
    for (const chip of group.querySelectorAll('ol-chip[data-subjects]')) {
        chip.addEventListener('mouseenter', () => light(chip, true));
        chip.addEventListener('mouseleave', () => light(chip, false));
        chip.addEventListener('focusin', () => light(chip, true));
        chip.addEventListener('focusout', () => light(chip, false));
    }
    // A saved key with no chip (a retired or unnamed tag) keeps its input, so a save doesn't drop it.
    const values = new Set([...group.querySelectorAll('ol-chip')].map(chip => chip.dataset.value));
    group.querySelectorAll('input[data-pick]').forEach(input => {
        if (!values.has(input.value)) delete input.dataset.pick;
    });
    const sync = () => {
        group.querySelectorAll('input[data-pick]').forEach(input => input.remove());
        // By property: the chip reflects ``selected`` to its attribute only on its next render.
        for (const chip of [...group.querySelectorAll('ol-chip')].filter(chip => chip.selected)) {
            const input = document.createElement('input');
            input.type = 'hidden';
            input.name = name;
            input.value = chip.dataset.value;
            input.dataset.pick = '';
            group.append(input);
        }
    };
    group.addEventListener('ol-chip-select', event => {
        event.target.closest('ol-chip').selected = event.detail.selected;
        sync();
    });
    sync();
}

export function init() {
    document.querySelectorAll('[data-many-choice]').forEach(initTagChips);
}
