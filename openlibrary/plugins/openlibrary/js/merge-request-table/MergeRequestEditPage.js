import { approveRequest, declineRequest } from './MergeRequestService'

export function initMergeRequestEditPage() {
    console.log('[MR EDIT] initMergeRequestEditPage called')

    const panel = document.getElementById('mr-review-panel')
    if (!panel) {
        console.warn('[MR EDIT] No MR review panel found, aborting')
        return
    }

    const urlParams = new URLSearchParams(window.location.search);
    const mrid = urlParams.get('mrid');

    console.log('[MR EDIT] mrid from URL:', mrid)

    if (!mrid) {
        console.warn('[MR EDIT] No mrid found, aborting')
        return
    }

    const approveBtn = document.getElementById('mr-approve-btn')
    const declineBtn = document.getElementById('mr-decline-btn')
    const commentInput = document.getElementById('mr-review-comment')
    const deleteForm = document.getElementById('delete-record')  // ✅ CORRECT FORM
    const deleteBtn = document.getElementById('delete-btn')
    const reviewPanel = panel

    console.log('[MR EDIT] Elements found:', {
        approveBtn: !!approveBtn,
        declineBtn: !!declineBtn,
        commentInput: !!commentInput,
        deleteForm: !!deleteForm,
        deleteBtn: !!deleteBtn
    })

    // Log the form's current state
    if (deleteForm) {
        const formData = new FormData(deleteForm)
        console.log('[MR EDIT] Delete form initial state:', {
            action: deleteForm.action,
            method: deleteForm.method,
            _delete: formData.get('_delete'),
            mrid: formData.get('mrid')
        })
    }

    /**
     * Show MR panel only after clicking Delete
     */
    if (deleteBtn && reviewPanel) {
        deleteBtn.addEventListener('click', (e) => {
            e.preventDefault()  // ✅ Prevent immediate submission
            console.log('[MR EDIT] Delete button clicked — showing MR review panel')
            reviewPanel.classList.remove('hidden')
        })
    }

    /**
     * APPROVE
     * - Injects comment into delete-record form
     * - Submits delete-record form
     * - Backend deletes record AND closes MR
     */
    if (approveBtn && deleteForm) {
        approveBtn.addEventListener('click', (e) => {
            e.preventDefault()
            const comment = commentInput?.value.trim() || ''
            
            console.log('[MR EDIT] Approve clicked')
            console.log('[MR EDIT] Comment:', comment || '(empty)')
            console.log('[MR EDIT] MRID being submitted:', mrid)

            // ✅ Inject comment into the correct form
            let commentField = deleteForm.querySelector('input[name="comment"]')
            if (!commentField) {
                commentField = document.createElement('input')
                commentField.type = 'hidden'
                commentField.name = 'comment'
                deleteForm.appendChild(commentField)
            }
            commentField.value = comment

            // ✅ Verify mrid is in the form (it should already be there from template)
            const mridField = deleteForm.querySelector('input[name="mrid"]')
            console.log('[MR EDIT] MRID field value:', mridField?.value)

            // Log final form state before submission
            const finalFormData = new FormData(deleteForm)
            console.log('[MR EDIT] Final form data:', {
                _delete: finalFormData.get('_delete'),
                mrid: finalFormData.get('mrid'),
                comment: finalFormData.get('comment')
            })

            console.log('[MR EDIT] Submitting delete-record form')
            deleteForm.submit()
        })
    }

    /**
     * DECLINE
     * - Calls API to decline MR
     * - No deletion occurs
     */
    if (declineBtn) {
        declineBtn.addEventListener('click', async (e) => {
            e.preventDefault()
            const comment = commentInput?.value.trim() || null
            
            console.log('[MR EDIT] Decline clicked')
            console.log('[MR EDIT] Comment:', comment || '(none)')
            console.log('[MR EDIT] MRID:', mrid)

            try {
                await declineRequest(mrid, comment)
                console.log('[MR EDIT] Decline successful, redirecting')
                window.location.href = '/merges'
            } catch (error) {
                console.error('[MR EDIT] Decline failed:', error)
                alert('Failed to decline merge request. Please try again.')
            }
        })
    }
}