/**
 * File dropzone functionality for drag-and-drop file uploads.
 * Handles the UI for selecting files via drag-and-drop or click-to-browse.
 */
export function initFileDropzone() {
    const dropzone = document.getElementById('csv-dropzone');
    const input = document.getElementById('csv-input');
    const browseBtn = document.getElementById('browse-btn');
    const loadBtn = document.getElementById('load-books-btn');
    const fileNameEl = document.getElementById('dropzone-filename');
    const dropzoneText = document.querySelector('.dropzone-text');

    if (!dropzone || !input || !browseBtn || !loadBtn || !fileNameEl || !dropzoneText) {
        return;
    }

    function updateLoadButton() {
        loadBtn.disabled = !input.files.length;
    }

    function showFileName() {
        if (input.files.length > 0) {
            const fileName = input.files[0].name;
            fileNameEl.textContent = fileName;
            fileNameEl.style.display = 'block';
            dropzoneText.style.display = 'none';
            dropzone.classList.add('has-file');
        } else {
            fileNameEl.style.display = 'none';
            dropzoneText.style.display = 'block';
            dropzone.classList.remove('has-file');
        }
    }

    // Click to browse
    browseBtn.addEventListener('click', function (e) {
        e.preventDefault();
        e.stopPropagation();
        input.click();
    });

    // File input change
    input.addEventListener('change', function () {
        updateLoadButton();
        showFileName();
    });

    // Drag and drop events
    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(function (eventName) {
        dropzone.addEventListener(
            eventName,
            function (e) {
                e.preventDefault();
                e.stopPropagation();
            },
            false
        );
    });

    ['dragenter', 'dragover'].forEach(function (eventName) {
        dropzone.addEventListener(
            eventName,
            function () {
                dropzone.classList.add('drag-active');
            },
            false
        );
    });

    ['dragleave', 'drop'].forEach(function (eventName) {
        dropzone.addEventListener(
            eventName,
            function () {
                dropzone.classList.remove('drag-active');
            },
            false
        );
    });

    dropzone.addEventListener(
        'drop',
        function (e) {
            const files = e.dataTransfer.files;
            if (files.length) {
                input.files = files;
                updateLoadButton();
                showFileName();
            }
        },
        false
    );

    // Click on dropzone to trigger file input
    dropzone.addEventListener('click', function (e) {
        if (e.target !== browseBtn && e.target !== input) {
            input.click();
        }
    });

    // Initial state
    updateLoadButton();
}
