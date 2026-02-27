import { setGlobalPreferences, getGlobalPreferences, onGlobalPreferencesChange, mapPreferencesToBackend, updateAllCarousels } from './preferences.js';

function getCookie(name) {
  const value = `; ${document.cookie}`;
  const parts = value.split(`; ${name}=`);
  if (parts.length === 2) return parts.pop().split(';').shift();
}

let selectedLang = null;

document.addEventListener("DOMContentLoaded", () => {
  const storedPrefs = localStorage.getItem('preferences');
  if (!storedPrefs || storedPrefs === '{}') {
    const mode = getCookie('ol_mode');
    const language = getCookie('ol_lang');
    const dateCookie = getCookie('ol_date');

    if (mode || language || dateCookie) {
      const date = dateCookie ? dateCookie.split(',').map(Number) : [1900, 2025];
      const cookiePrefs = {
        mode: mode || 'all',
        language: language || 'en',
        date: date,
      };
      setGlobalPreferences(cookiePrefs);
      updateAllCarousels();
    }
  }

  document.querySelectorAll('.locale-options').forEach(select => {
    select.addEventListener("change", (e) => {
      selectedLang = select.value || 'en';
      console.log('Selected language:', selectedLang);
    });
  });

  document.getElementById("save-preferences-btn").addEventListener("click", () => {
    const startYear = parseInt(document.getElementById("global-date-start").value) || 1900;
    const endYear = parseInt(document.getElementById("global-date-end").value) || 2025;
    const prefs = {
      mode: document.getElementById("global-mode-select").value || 'all',
      language: selectedLang || 'en',
      date: [startYear, endYear]
    };
    setGlobalPreferences(prefs);

    fetch("/account/preferences", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...prefs, redirect: false })
    }).then(res => res.json()).then(() => {
      // 3. Trigger local UI update (carousel reload)
      updateAllCarousels();
    });

    // Close filter panel
    const filterPanel = document.getElementById("filter-panel");
    const filterTrigger = document.getElementById("filter-panel-trigger");
    filterPanel.classList.remove('show');
    filterPanel.classList.add('hidden');
    filterTrigger.setAttribute('aria-expanded', 'false');
    filterTrigger.focus();

    // Simulate UI update for testing
    const backendPrefs = mapPreferencesToBackend(prefs);
    console.log('Simulated carousel update with preferences:', backendPrefs);

    // Trigger updates in other tabs
    onGlobalPreferencesChange((newPrefs) => {
      console.log('Preferences updated in another tab:', newPrefs);
      // Simulate carousel update for testing
      console.log('Simulated carousel update with new preferences:', mapPreferencesToBackend(newPrefs));
    });
  });
});

// Commented out backend-dependent code for UI-only testing
/*
function updateCarousel(carouselId) {
  const prefs = getGlobalPreferences();
  const backendPrefs = mapPreferencesToBackend(prefs);
  fetch(`/carousel/${carouselId}?prefs=${encodeURIComponent(JSON.stringify(backendPrefs))}`)
    .then(response => {
      if (!response.ok) throw new Error('Failed to fetch carousel data');
      return response.json();
    })
    .then(data => {
      console.log('Carousel updated:', data);
      // Update carousel UI here, e.g., update DOM elements with data
    })
    .catch(e => console.error('Error updating carousel:', e));
}
*/