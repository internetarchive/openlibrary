// Tracks reading history for open access and borrowable books
// Stores edition IDs in localStorage with timestamps

const STORAGE_KEY = 'ol_reading_history';
const MAX_ITEMS = 100; // keep last 100 items

export class ReadingHistory {
    // Get all entries from localStorage
    static getAll() {
        try {
            const stored = localStorage.getItem(STORAGE_KEY);
            if (!stored) {
                return [];
            }
            const parsed = JSON.parse(stored);
            // Make sure we return an array even if stored data is corrupted
            return Array.isArray(parsed) ? parsed : [];
        } catch (e) {
            // eslint-disable-next-line no-console
            console.warn('Failed to read reading history from localStorage:', e);
            return [];
        }
    }

    // Save entries to localStorage, keeping only the most recent ones
    static save(entries) {
        try {
            // Keep only the last MAX_ITEMS entries (most recent)
            const limited = entries.slice(-MAX_ITEMS);
            localStorage.setItem(STORAGE_KEY, JSON.stringify(limited));
        } catch (e) {
            // Handle case where localStorage is full (private browsing, quota exceeded, etc)
            if (e.name === 'QuotaExceededError') {
                // eslint-disable-next-line no-console
                console.warn('localStorage quota exceeded, clearing old entries');
                // Try saving with half the items
                const reduced = entries.slice(-Math.floor(MAX_ITEMS / 2));
                try {
                    localStorage.setItem(STORAGE_KEY, JSON.stringify(reduced));
                } catch (e2) {
                    // eslint-disable-next-line no-console
                    console.error('Failed to save reading history after quota error:', e2);
                }
            } else {
                // eslint-disable-next-line no-console
                console.error('Failed to save reading history:', e);
            }
        }
    }

    // Add a new edition to reading history
    // If it already exists, we remove the old one and add it again (so it's most recent)
    static add(editionId) {
        if (!editionId) {
            return;
        }

        const entries = this.getAll();
        const now = Date.now();

        // Remove any existing entry with the same editionId
        const filtered = entries.filter(entry => entry.editionId !== editionId);

        // Add the new entry at the end
        filtered.push({
            editionId: editionId,
            timestamp: now
        });

        this.save(filtered);
    }

    // Get edition IDs, sorted by most recent first
    static getEditionIds(limit = null) {
        const entries = this.getAll();
        // Sort by timestamp (newest first)
        const sorted = entries.sort((a, b) => b.timestamp - a.timestamp);
        const ids = sorted.map(entry => entry.editionId);
        return limit ? ids.slice(0, limit) : ids;
    }

    // Clear all reading history
    static clear() {
        try {
            localStorage.removeItem(STORAGE_KEY);
        } catch (e) {
            // eslint-disable-next-line no-console
            console.warn('Failed to clear reading history:', e);
        }
    }

    // Get count of entries
    static getCount() {
        return this.getAll().length;
    }

    // Check if localStorage is available (some browsers disable it in private mode)
    static isAvailable() {
        try {
            const test = '__reading_history_test__';
            localStorage.setItem(test, test);
            localStorage.removeItem(test);
            return true;
        } catch (e) {
            return false;
        }
    }
}

