/**
 * Enhances export buttons on /account/import so that when an export starts:
 * - The clicked button shows "Downloading..."
 * - The button is disabled and styled as unavailable (grey)
 * - Subsequent clicks are prevented while the download is in progress
 *
 * Implementation detail: We use fetch() to retrieve the CSV as a Blob so we
 * can reliably detect completion across browsers (some do not fire iframe
 * load events when Content-Disposition: attachment is used). Once the blob is
 * received, we trigger a programmatic download and then restore button state.
 */

function getSubmitButton(formElement) {
  // Each export form has a single submit input
  return formElement.querySelector('input[type="submit"], button[type="submit"]');
}

function disableButton(buttonElement) {
  if (!buttonElement) return;
  buttonElement.dataset.originalValue = buttonElement.value || buttonElement.textContent || '';
  if (buttonElement.tagName === 'INPUT') {
    buttonElement.value = 'Downloading...';
  } else {
    buttonElement.textContent = 'Downloading...';
  }
  buttonElement.setAttribute('disabled', 'true');
  buttonElement.setAttribute('aria-disabled', 'true');
  buttonElement.classList.remove('cta-btn--available');
  buttonElement.classList.add('cta-btn--unavailable');
  // Show loading affordance consistent with other unavailable actions
  buttonElement.classList.add('cta-btn--unavailable--load');
}

function enableButton(buttonElement) {
  if (!buttonElement) return;
  const original = buttonElement.dataset.originalValue || '';
  if (buttonElement.tagName === 'INPUT') {
    buttonElement.value = original;
  } else {
    buttonElement.textContent = original;
  }
  buttonElement.removeAttribute('disabled');
  buttonElement.setAttribute('aria-disabled', 'false');
  buttonElement.classList.remove('cta-btn--unavailable');
  buttonElement.classList.remove('cta-btn--unavailable--load');
  buttonElement.classList.add('cta-btn--available');
  delete buttonElement.dataset.originalValue;
}

function buildGetUrlFromForm(formElement) {
  const action = formElement.getAttribute('action') || '';
  const params = new URLSearchParams(new FormData(formElement));
  const query = params.toString();
  return query ? `${action}?${query}` : action;
}

function parseFilenameFromContentDisposition(headerValue) {
  if (!headerValue) return null;
  // RFC 5987 filename*=
  const starMatch = /filename\*=UTF-8''([^;]+)/i.exec(headerValue);
  if (starMatch && starMatch[1]) {
    try {
      return decodeURIComponent(starMatch[1]);
    } catch (_) {
      return starMatch[1];
    }
  }
  // Basic filename="..."
  const plainMatch = /filename="?([^";]+)"?/i.exec(headerValue);
  return plainMatch && plainMatch[1] ? plainMatch[1] : null;
}

async function fetchAndDownload(url) {
  const response = await fetch(url, { credentials: 'same-origin' });
  if (!response.ok) {
    const error = new Error(`Export request failed with status ${response.status}`);
    error.status = response.status;
    throw error;
  }
  const blob = await response.blob();
  const contentDisposition = response.headers.get('Content-Disposition') || response.headers.get('content-disposition');
  const fallbackName = 'OpenLibrary_Export.csv';
  const filename = parseFilenameFromContentDisposition(contentDisposition) || fallbackName;
  const objectUrl = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = objectUrl;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  setTimeout(() => {
    URL.revokeObjectURL(objectUrl);
    if (a.parentNode) a.parentNode.removeChild(a);
  }, 0);
}

export function initPatronExportButtons() {
  // Guard: only on the import page
  if (location.pathname !== '/account/import') return;

  const exportForms = document.querySelectorAll('form[action="/account/export"][method="GET" i]');
  if (!exportForms.length) return;

  exportForms.forEach((form) => {
    const submitButton = getSubmitButton(form);
    if (!submitButton) return;

    // Prevent double-binding
    if (form.dataset.patronExportBound === 'true') return;
    form.dataset.patronExportBound = 'true';

    form.addEventListener('submit', (event) => {
      // If already disabled, block to prevent duplicates
      if (submitButton.hasAttribute('disabled')) {
        event.preventDefault();
        return;
      }

      event.preventDefault();
      disableButton(submitButton);
      const startMs = performance.now();
      const url = buildGetUrlFromForm(form);
      fetchAndDownload(url)
        .catch(() => {
          // Swallow errors but restore button;
        })
        .finally(() => {
          // Ensure state stays visible for at least a short time
          const minDurationMs = 500; 
          const elapsed = performance.now() - startMs;
          const remaining = Math.max(0, minDurationMs - elapsed);
          setTimeout(() => enableButton(submitButton), remaining);
        });
    });

    // Also handle direct button clicks that might bypass submit event ordering
    submitButton.addEventListener('click', (event) => {
      if (submitButton.hasAttribute('disabled')) {
        event.preventDefault();
      }
    });
  });
}


