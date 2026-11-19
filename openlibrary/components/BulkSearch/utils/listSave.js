export const LIST_SAVE_POST_THRESHOLD = 50

export function getListSaveAction(selectedListTarget, seeds, matchedBooksCount, newListUrl) {
    if (!selectedListTarget) {
        return { error: 'Please select a list.' }
    }

    if (!seeds) {
        return { error: 'No matched books to add.' }
    }

    const isNewList = selectedListTarget === 'create'
    if (matchedBooksCount < LIST_SAVE_POST_THRESHOLD) {
        return {
            method: 'GET',
            url: isNewList ? newListUrl : `${selectedListTarget}?seeds=${encodeURIComponent(seeds)}`
        }
    }

    return {
        method: 'POST',
        action: isNewList ? '/account/lists/add' : selectedListTarget,
        seeds
    }
}
