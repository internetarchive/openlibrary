import {
    DEFAULT_AVATAR_STRINGS,
    avatarStringsFromElement,
    setStatus,
    initAvatarUpload
} from '../../../openlibrary/plugins/openlibrary/js/avatar';

describe('avatar module', () => {
    let container;

    beforeEach(() => {
        document.body.innerHTML = `
            <div class="formElement avatar" data-i18n='{"chooseImagePrompt": "Custom choose prompt"}'>
                <div class="input avatar-container">
                    <div class="avatar-preview-container">
                        <img id="avatar-preview-img"
                             src="/people/testuser/avatar"
                             data-base-src="/people/testuser/avatar"
                             alt="" />
                    </div>
                    <div class="avatar-controls">
                        <input type="file" id="avatar-file-input" accept="image/jpeg,image/png,image/webp,image/gif" />
                        <div class="avatar-button-group">
                            <button type="button" id="avatar-upload-btn" class="avatar-btn avatar-btn--upload">Upload</button>
                            <button type="button" id="avatar-remove-btn" class="avatar-btn avatar-btn--remove">Remove</button>
                        </div>
                        <span id="avatar-upload-status" class="avatar-upload-status"></span>
                    </div>
                </div>
            </div>
        `;
        container = document.querySelector('.formElement.avatar');

        // Mock URL.createObjectURL
        global.URL.createObjectURL = jest.fn(() => 'blob:http://localhost/mock-blob-url');
        // Mock fetch
        global.fetch = jest.fn();
    });

    afterEach(() => {
        jest.restoreAllMocks();
    });

    describe('avatarStringsFromElement', () => {
        test('merges dataset.i18n overrides with default strings', () => {
            const strings = avatarStringsFromElement(container);
            expect(strings.chooseImagePrompt).toBe('Custom choose prompt');
            expect(strings.uploadSuccess).toBe(DEFAULT_AVATAR_STRINGS.uploadSuccess);
        });

        test('returns default strings when element has no dataset or malformed JSON', () => {
            expect(avatarStringsFromElement(null)).toEqual(DEFAULT_AVATAR_STRINGS);

            const badEl = document.createElement('div');
            badEl.dataset.i18n = 'invalid json';
            expect(avatarStringsFromElement(badEl)).toEqual(DEFAULT_AVATAR_STRINGS);
        });
    });

    describe('setStatus', () => {
        test('updates text and applies state classes', () => {
            const statusSpan = document.getElementById('avatar-upload-status');
            setStatus(statusSpan, 'Success text', 'success');
            expect(statusSpan.textContent).toBe('Success text');
            expect(statusSpan.classList.contains('avatar-upload-status--success')).toBe(true);

            setStatus(statusSpan, 'Error text', 'error');
            expect(statusSpan.textContent).toBe('Error text');
            expect(statusSpan.classList.contains('avatar-upload-status--error')).toBe(true);
            expect(statusSpan.classList.contains('avatar-upload-status--success')).toBe(false);

            setStatus(null, 'Nothing', 'info'); // should not throw
        });
    });

    describe('initAvatarUpload', () => {
        test('updates preview image when file is selected', () => {
            initAvatarUpload(container);

            const fileInput = document.getElementById('avatar-file-input');
            const img = document.getElementById('avatar-preview-img');
            const file = new File(['test'], 'avatar.jpg', { type: 'image/jpeg' });

            Object.defineProperty(fileInput, 'files', {
                value: [file],
                writable: true,
            });

            fileInput.dispatchEvent(new Event('change'));
            expect(global.URL.createObjectURL).toHaveBeenCalledWith(file);
            expect(img.src).toBe('blob:http://localhost/mock-blob-url');
        });

        test('shows error when upload is clicked without selecting a file', async() => {
            initAvatarUpload(container);

            const uploadBtn = document.getElementById('avatar-upload-btn');
            const statusSpan = document.getElementById('avatar-upload-status');

            uploadBtn.dispatchEvent(new Event('click'));

            expect(statusSpan.textContent).toBe('Custom choose prompt');
            expect(statusSpan.classList.contains('avatar-upload-status--error')).toBe(true);
            expect(global.fetch).not.toHaveBeenCalled();
        });

        test('keeps the local file preview when the response has no avatar_url (dev mock)', async() => {
            initAvatarUpload(container);

            const uploadBtn = document.getElementById('avatar-upload-btn');
            const fileInput = document.getElementById('avatar-file-input');
            const statusSpan = document.getElementById('avatar-upload-status');
            const img = document.getElementById('avatar-preview-img');
            const file = new File(['test-image-data'], 'test.png', { type: 'image/png' });

            Object.defineProperty(fileInput, 'files', {
                value: [file],
                writable: true,
            });

            fileInput.dispatchEvent(new Event('change'));
            global.fetch.mockResolvedValueOnce({
                ok: true,
                json: async() => ({}),
            });

            uploadBtn.dispatchEvent(new Event('click'));
            await Promise.resolve();
            await Promise.resolve();

            expect(statusSpan.textContent).toBe('Uploaded successfully!');
            expect(global.URL.createObjectURL).toHaveBeenCalledWith(file);
            expect(img.src).toBe('blob:http://localhost/mock-blob-url');
        });

        test('successfully uploads avatar and updates status', async() => {
            initAvatarUpload(container);

            const uploadBtn = document.getElementById('avatar-upload-btn');
            const fileInput = document.getElementById('avatar-file-input');
            const statusSpan = document.getElementById('avatar-upload-status');
            const file = new File(['test-image-data'], 'test.png', { type: 'image/png' });

            Object.defineProperty(fileInput, 'files', {
                value: [file],
                writable: true,
            });

            global.fetch.mockResolvedValueOnce({
                ok: true,
                json: async() => ({
                    avatar_url: 'https://archive.org/services/img/@testuser/avatar.jpg?v=12345',
                }),
            });

            uploadBtn.dispatchEvent(new Event('click'));

            expect(statusSpan.textContent).toBe('Uploading...');
            await Promise.resolve();
            await Promise.resolve();

            expect(global.fetch).toHaveBeenCalledWith('/account/avatar', expect.objectContaining({
                method: 'POST',
            }));
            expect(statusSpan.textContent).toBe('Uploaded successfully!');
            expect(statusSpan.classList.contains('avatar-upload-status--success')).toBe(true);
        });

        test('handles upload error response gracefully', async() => {
            initAvatarUpload(container);

            const uploadBtn = document.getElementById('avatar-upload-btn');
            const fileInput = document.getElementById('avatar-file-input');
            const statusSpan = document.getElementById('avatar-upload-status');
            const file = new File(['test-bad'], 'bad.txt', { type: 'text/plain' });

            Object.defineProperty(fileInput, 'files', {
                value: [file],
                writable: true,
            });

            global.fetch.mockResolvedValueOnce({
                ok: false,
                json: async() => ({ detail: 'Only JPEG, PNG, WEBP, and GIF images are allowed' }),
            });

            uploadBtn.dispatchEvent(new Event('click'));
            await Promise.resolve();
            await Promise.resolve();

            expect(statusSpan.textContent).toBe('Only JPEG, PNG, WEBP, and GIF images are allowed');
            expect(statusSpan.classList.contains('avatar-upload-status--error')).toBe(true);
        });

        test('successfully removes avatar and updates preview and status', async() => {
            initAvatarUpload(container);

            const removeBtn = document.getElementById('avatar-remove-btn');
            const fileInput = document.getElementById('avatar-file-input');
            const statusSpan = document.getElementById('avatar-upload-status');
            const img = document.getElementById('avatar-preview-img');

            global.fetch.mockResolvedValueOnce({
                ok: true,
                json: async() => ({ status: 'success' }),
            });

            removeBtn.dispatchEvent(new Event('click'));
            expect(statusSpan.textContent).toBe('Removing...');

            await Promise.resolve();
            await Promise.resolve();

            expect(global.fetch).toHaveBeenCalledWith('/account/avatar', {
                method: 'DELETE',
            });
            expect(statusSpan.textContent).toBe('Photo removed successfully!');
            expect(statusSpan.classList.contains('avatar-upload-status--success')).toBe(true);
            expect(fileInput.value).toBe('');
            expect(img.src).toContain('/people/testuser/avatar?t=');
        });

        test('handles remove error response gracefully', async() => {
            initAvatarUpload(container);

            const removeBtn = document.getElementById('avatar-remove-btn');
            const statusSpan = document.getElementById('avatar-upload-status');

            global.fetch.mockResolvedValueOnce({
                ok: false,
                json: async() => ({ detail: 'No custom profile picture exists to remove' }),
            });

            removeBtn.dispatchEvent(new Event('click'));
            await Promise.resolve();
            await Promise.resolve();

            expect(statusSpan.textContent).toBe('No custom profile picture exists to remove');
            expect(statusSpan.classList.contains('avatar-upload-status--error')).toBe(true);
        });
    });
});
