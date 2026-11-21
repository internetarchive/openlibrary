/**
 * Measures how many patrons could use on-device AI features (e.g.
 * https://internetarchive.github.io/local-chat/) powered by Chrome's built-in
 * Prompt API: https://developer.chrome.com/docs/ai/prompt-api
 *
 * Sends one analytics event per browser tab session (#14046):
 * - category: LocalLanguageModel
 * - action: Unsupported | NotDownloaded | Ready (see AVAILABILITY_GROUPS)
 * - label: the detailed availability, e.g. 'unsupported', 'downloadable'
 */
import { trackEvent } from './ol.analytics.js';

// Languages the Prompt API supports, the same ones <local-chat> checks for
const SUPPORTED_LANGUAGES = ['de', 'en', 'es', 'fr', 'ja'];

const SESSION_STORAGE_KEY = 'ol-local-ai-availability-tracked';

export const AVAILABILITY_GROUPS = {
    // No Prompt API in the browser
    unsupported: 'Unsupported',
    // Prompt API is there, but the device can't run the model
    unavailable: 'Unsupported',
    // Prompt API failed to tell
    error: 'Unsupported',
    // The model must be downloaded first
    downloadable: 'NotDownloaded',
    downloading: 'NotDownloaded',
    // Ready to use
    available: 'Ready'
};

function pageLanguage() {
    const lang = document.documentElement.lang.split('-')[0]?.toLowerCase();
    return SUPPORTED_LANGUAGES.includes(lang) ? lang : 'en';
}

/**
 * @returns {Promise<string>} 'unsupported', 'error', or a value of
 *     LanguageModel.availability(): 'unavailable', 'downloadable', 'downloading', 'available'
 */
export async function getLocalAiAvailability() {
    const LanguageModel = window.LanguageModel;
    if (typeof LanguageModel?.availability !== 'function') {
        return 'unsupported';
    }
    const languages = [pageLanguage()];
    try {
        return await LanguageModel.availability({
            expectedInputs: [{ type: 'text', languages }],
            expectedOutputs: [{ type: 'text', languages }]
        });
    } catch {
        return 'error';
    }
}

/**
 * Claims this tab session's one event. sessionStorage may be unavailable
 * (e.g. blocked site data), in which case we track on every page instead of
 * not at all.
 *
 * @returns {boolean} whether the event was already sent in this session
 */
function wasTrackedInThisSession() {
    try {
        if (window.sessionStorage.getItem(SESSION_STORAGE_KEY) !== null) return true;
        window.sessionStorage.setItem(SESSION_STORAGE_KEY, '1');
    } catch {
        // Ignore
    }
    return false;
}

/**
 * Call after analytics is set up. Never throws.
 */
export async function trackLocalAiAvailability() {
    // Nothing would record the event, e.g. for bots or with analytics disabled
    if (!window._paq && !window.archive_analytics) return;
    if (wasTrackedInThisSession()) return;

    const availability = await getLocalAiAvailability();
    trackEvent('LocalLanguageModel', AVAILABILITY_GROUPS[availability] ?? 'Unknown', availability);
}
