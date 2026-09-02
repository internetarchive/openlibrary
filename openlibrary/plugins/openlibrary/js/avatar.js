/**
 * Avatar (Profile Picture) Upload & Removal module.
 * Consumed by openlibrary/templates/type/user/edit.html.
 */
import '../../../../static/css/components/avatar--js.css';

export const DEFAULT_AVATAR_STRINGS = {
    chooseImagePrompt: 'Please choose an image file first.',
    uploading: 'Uploading...',
    uploadSuccess: 'Uploaded successfully!',
    uploadFailed: 'Upload failed.',
    removing: 'Removing...',
    removeSuccess: 'Photo removed successfully!',
    removeFailed: 'Failed to remove photo.',
};

/**
 * Extracts and merges i18n string overrides from the element's data-i18n attribute.
 *
 * @param {HTMLElement} el
 * @returns {typeof DEFAULT_AVATAR_STRINGS}
 */
export function avatarStringsFromElement(el) {
    let overrides = null;
    try {
        const raw = el?.dataset?.i18n;
        if (raw) {
            overrides = JSON.parse(raw);
        }
    } catch {
        /* fall back to defaults */
    }
    return overrides ? { ...DEFAULT_AVATAR_STRINGS, ...overrides } : DEFAULT_AVATAR_STRINGS;
}

/**
 * Updates status text and styling class.
 *
 * @param {HTMLElement|null} statusSpan
 * @param {string} text
 * @param {'info' | 'success' | 'error'} state
 */
export function setStatus(statusSpan, text, state) {
    if (!statusSpan) return;
    statusSpan.textContent = text;
    statusSpan.classList.remove(
        'avatar-upload-status--info',
        'avatar-upload-status--success',
        'avatar-upload-status--error'
    );
    if (state) {
        statusSpan.classList.add(`avatar-upload-status--${state}`);
    }
}

/**
 * Initializes avatar upload and removal handlers for a given container element.
 *
 * @param {HTMLElement} [container] - The container element (defaults to document).
 */
export function initAvatarUpload(container = document) {
    const uploadBtn = container.querySelector('#avatar-upload-btn');
    const removeBtn = container.querySelector('#avatar-remove-btn');
    const fileInput = container.querySelector('#avatar-file-input');
    const statusSpan = container.querySelector('#avatar-upload-status');
    const img = container.querySelector('#avatar-preview-img');
    const i18nTarget = container.closest?.('.formElement.avatar')
        || container.querySelector?.('.formElement.avatar')
        || container;
    const strings = avatarStringsFromElement(i18nTarget);

    if (fileInput && img) {
        fileInput.addEventListener('change', () => {
            if (fileInput.files && fileInput.files[0]) {
                img.src = URL.createObjectURL(fileInput.files[0]);
                setStatus(statusSpan, '', 'info');
            }
        });
    }

    if (uploadBtn && fileInput) {
        uploadBtn.addEventListener('click', async() => {
            if (!fileInput.files || !fileInput.files[0]) {
                setStatus(statusSpan, strings.chooseImagePrompt, 'error');
                return;
            }

            const formData = new FormData();
            formData.append('file', fileInput.files[0]);

            setStatus(statusSpan, strings.uploading, 'info');

            try {
                const res = await fetch('/account/avatar', {
                    method: 'POST',
                    body: formData,
                });

                if (!res.ok) {
                    let msg = strings.uploadFailed;
                    try {
                        const data = await res.json();
                        if (typeof data.detail === 'string') {
                            msg = data.detail;
                        } else if (Array.isArray(data.detail)) {
                            msg = data.detail
                                .map((e) => `${e.loc ? e.loc.join('.') : ''}: ${e.msg}`)
                                .join('; ');
                        }
                    } catch {
                        // ignore json parse error
                    }
                    throw new Error(msg);
                }

                const data = await res.json();
                setStatus(statusSpan, strings.uploadSuccess, 'success');
                if (fileInput.files && fileInput.files[0] && img) {
                    img.src = URL.createObjectURL(fileInput.files[0]);
                } else if (data.avatar_url && img) {
                    img.src = data.avatar_url;
                }
            } catch (err) {
                setStatus(statusSpan, err.message || strings.uploadFailed, 'error');
            }
        });
    }

    if (removeBtn) {
        removeBtn.addEventListener('click', async() => {
            setStatus(statusSpan, strings.removing, 'info');

            try {
                const res = await fetch('/account/avatar', {
                    method: 'DELETE',
                });

                if (!res.ok) {
                    let msg = strings.removeFailed;
                    try {
                        const data = await res.json();
                        if (data && data.detail) {
                            msg = data.detail;
                        }
                    } catch {
                        // ignore json parse error
                    }
                    throw new Error(msg);
                }

                setStatus(statusSpan, strings.removeSuccess, 'success');
                if (fileInput) {
                    fileInput.value = '';
                }
                if (img) {
                    const basePath = img.getAttribute('data-base-src') || img.src.split('?')[0];
                    img.src = `${basePath}?t=${Date.now()}`;
                }
            } catch (err) {
                setStatus(statusSpan, err.message || strings.removeFailed, 'error');
            }
        });
    }
}
