import { approveRequest, declineRequest } from './MergeRequestService'

export function initMergeRequestEditPage() {
    console.log('[MR EDIT] initMergeRequestEditPage called')

    const panel = document.getElementById('mr-review-panel')
    if (!panel) {
        console.warn('[MR EDIT] No MR review panel found, aborting')
        return
    }

    // ✅ NEW (FIXED): Reads directly from the URL (Source of Truth)
    const urlParams = new URLSearchParams(window.location.search);
    const mrid = urlParams.get('mrid');

    console.log('[MR EDIT] mrid:', mrid)

    if (!mrid) {
        console.warn('[MR EDIT] No mrid found, aborting')
        return
    }

    const approveBtn = document.getElementById('mr-approve-btn')
    const declineBtn = document.getElementById('mr-decline-btn')
    const commentInput = document.getElementById('mr-review-comment')
    const form = document.getElementById('addWork')
    const deleteBtn = document.getElementById('delete-btn')   // ✅ FIX
    const reviewPanel = panel                                // ✅ FIX

    console.log('[MR EDIT] approveBtn:', approveBtn)
    console.log('[MR EDIT] declineBtn:', declineBtn)
    console.log('[MR EDIT] commentInput:', commentInput)
    console.log('[MR EDIT] addWork form:', form)
    console.log('[MR EDIT] deleteBtn:', deleteBtn)

    /**
     * Show MR panel only after clicking Delete
     */
    if (deleteBtn && reviewPanel) {
        deleteBtn.addEventListener('click', () => {
            console.log('[MR EDIT] Delete button clicked — showing MR review panel')
            reviewPanel.classList.remove('hidden')
        })
    }

    const finish = () => {
        console.log('[MR EDIT] finish() called, redirecting')
        approveBtn?.setAttribute('disabled', true)
        declineBtn?.setAttribute('disabled', true)
        window.location.href = '/merges'
    }

    /**
     * APPROVE
     * - Adds _delete=true
     * - Injects mrid
     * - Submits addWork
     * - Backend closes MR
     */
    if (approveBtn) {
        approveBtn.addEventListener('click', () => {
            const comment = commentInput?.value.trim() || null
            console.log('[MR EDIT] approve clicked, comment:', comment)

            if (!form) {
                console.error('[MR EDIT] addWork form not found')
                return
            }

            // Ensure _delete flag
            let deleteInput = form.querySelector('input[name="_delete"]')
            if (!deleteInput) {
                deleteInput = document.createElement('input')
                deleteInput.type = 'hidden'
                deleteInput.name = '_delete'
                deleteInput.value = 'true'
                form.appendChild(deleteInput)
            }

            // Ensure mrid
            let mridInput = form.querySelector('input[name="mrid"]')
            if (!mridInput) {
                mridInput = document.createElement('input')
                mridInput.type = 'hidden'
                mridInput.name = 'mrid'
                form.appendChild(mridInput)
            }
            mridInput.value = mrid

            console.log('[MR EDIT] submitting delete via addWork (backend handles MR)')
            form.submit()
        })
    }

    /**
     * DECLINE
     * - Declines MR only
     * - No delete
     */
    if (declineBtn) {
        declineBtn.addEventListener('click', async () => {
            const comment = commentInput?.value.trim() || null
            console.log('[MR EDIT] decline clicked, comment:', comment)

            await declineRequest(mrid, comment)
            finish()
        })
    }
}
