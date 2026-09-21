import { ref } from 'vue';

const states = new Map();

function readValue(key, defaultValue) {
    if (typeof window === 'undefined') return defaultValue;

    try {
        const item = window.localStorage.getItem(key);
        return item === null ? defaultValue : JSON.parse(item);
    } catch {
        return defaultValue;
    }
}

/**
 * Provides a shared reactive value backed by localStorage.
 *
 * @param {string} key
 * @param {*} defaultValue
 * @returns {{ value: import('vue').Ref<*>, setValue: (data: *) => void }}
 */
export function useLocalStorage(key, defaultValue = null) {
    if (!states.has(key)) {
        states.set(key, ref(readValue(key, defaultValue)));
    }

    const value = states.get(key);

    function setValue(data) {
        value.value = data;
        if (typeof window === 'undefined') return;

        try {
            if (data === null || data === undefined) {
                window.localStorage.removeItem(key);
            } else {
                window.localStorage.setItem(key, JSON.stringify(data));
            }
        } catch {
            // Ignore disabled storage and quota errors.
        }
    }

    return { value, setValue };
}
