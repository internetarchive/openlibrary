// src/merge-request-table/AuthorMergeRequestEditPage.js

import { declineRequest } from './MergeRequestService';

export function initAuthorMergeRequestEditPage() {
    const urlParams = new URLSearchParams(window.location.search);
    const mrid = urlParams.get('mrid');

    if (!mrid) return;

    const panel = document.getElementById('mr-review-panel');
    const deleteForm = document.getElementById('delete-record');
    const deleteBtn = document.getElementById('delete-btn');

    const approveBtn = document.getElementById('mr-approve-btn');
    const declineBtn = document.getElementById('mr-decline-btn');
    const commentInput = document.getElementById('mr-review-comment');

    if (!deleteForm || !panel) return;

    // 1. Intercept the standard "Delete Record" button to show the panel
    if (deleteBtn) {
        deleteBtn.addEventListener('click', (e) => {
            e.preventDefault();
            console.log('[AUTHOR MR] Delete button clicked - showing review panel');
            panel.classList.remove('hidden');
            panel.scrollIntoView({ behavior: 'smooth' });
        });
    }

    // 2. APPROVE: Inject MR details into the delete form and submit
    if (approveBtn) {
        approveBtn.addEventListener('click', (e) => {
            e.preventDefault();
            console.log('[AUTHOR MR] === Approve Button Clicked ===');

            const comment = commentInput ? commentInput.value.trim() : '';

            // Inject 'comment'
            let commentField = deleteForm.querySelector('input[name="comment"]');
            if (!commentField) {
                commentField = document.createElement('input');
                commentField.type = 'hidden';
                commentField.name = 'comment';
                deleteForm.appendChild(commentField);
            }
            commentField.value = comment;

            // Inject 'mrid'
            let mridField = deleteForm.querySelector('input[name="mrid"]');
            if (!mridField) {
                mridField = document.createElement('input');
                mridField.type = 'hidden';
                mridField.name = 'mrid';
                deleteForm.appendChild(mridField);
            }
            mridField.value = mrid;

            // Ensure '_delete' signal exists
            let deleteSignal = deleteForm.querySelector('input[name="_delete"]');
            if (!deleteSignal) {
                deleteSignal = document.createElement('input');
                deleteSignal.type = 'hidden';
                deleteSignal.name = '_delete';
                deleteSignal.value = 'true';
                deleteForm.appendChild(deleteSignal);
            }

            // --- LOGGING THE DATA ---
            console.log('[AUTHOR MR] Preparing to submit form...');
            console.log(`[AUTHOR MR] Target Action/URL: ${deleteForm.action || window.location.href}`);

            // Create a FormData object just to inspect what is inside the form
            const formData = new FormData(deleteForm);
            console.log('[AUTHOR MR] Form Data Payload:');
            for (const [key, value] of formData.entries()) {
                console.log(`   KEY: ${key}  |  VALUE: ${value}`);
            }
            console.log('[AUTHOR MR] Submitting now...');
            // ------------------------

            deleteForm.submit();
        });
    }

    // 3. DECLINE: Async API call
    if (declineBtn) {
        declineBtn.addEventListener('click', async (e) => {
            e.preventDefault();
            console.log('[AUTHOR MR] === Decline Button Clicked ===');

            const comment = commentInput ? commentInput.value.trim() : null;
            console.log(`[AUTHOR MR] Declining MRID: ${mrid} with comment: "${comment}"`);

            declineBtn.disabled = true;

            try {
                await declineRequest(mrid, comment);
                console.log('[AUTHOR MR] Decline successful, redirecting...');
                window.location.href = '/merges';
            } catch (error) {
                console.error('[AUTHOR MR] Failed to decline:', error);
                alert('Failed to decline merge request.');
                declineBtn.disabled = false;
            }
        });
    }
}
