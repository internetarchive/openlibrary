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
            panel.classList.remove('hidden');
            panel.scrollIntoView({ behavior: 'smooth' });
        });
    }

    // 2. APPROVE: Inject MR details into the delete form and submit
    if (approveBtn) {
        approveBtn.addEventListener('click', (e) => {
            e.preventDefault();

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

            deleteForm.submit();
        });
    }

    // 3. DECLINE: Async API call
    if (declineBtn) {
        declineBtn.addEventListener('click', async (e) => {
            e.preventDefault();

            const comment = commentInput ? commentInput.value.trim() : null;
            declineBtn.disabled = true;

            try {
                await declineRequest(mrid, comment);
                window.location.href = '/merges';
            } catch (error) {
                alert('Failed to decline merge request.');
                declineBtn.disabled = false;
            }
        });
    }
}
