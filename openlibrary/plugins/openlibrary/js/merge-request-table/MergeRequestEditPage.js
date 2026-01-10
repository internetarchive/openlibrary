import {declineRequest } from './MergeRequestService'

export function initMergeRequestEditPage() {
    const panel = document.getElementById('mr-review-panel')
    if (!panel) {
        return
    }

    const urlParams = new URLSearchParams(window.location.search)
    const mrid = urlParams.get('mrid')

    if (!mrid) {
        return
    }

    const approveBtn = document.getElementById('mr-approve-btn')
    const declineBtn = document.getElementById('mr-decline-btn')
    const commentInput = document.getElementById('mr-review-comment')
    const deleteForm = document.getElementById('delete-record')
    const deleteBtn = document.getElementById('delete-btn')
    const reviewPanel = panel

    /**
     * Show MR panel only after clicking Delete
     */
    if (deleteBtn && reviewPanel) {
        deleteBtn.addEventListener('click', (e) => {
            e.preventDefault()
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

            let commentField = deleteForm.querySelector('input[name="comment"]')
            if (!commentField) {
                commentField = document.createElement('input')
                commentField.type = 'hidden'
                commentField.name = 'comment'
                deleteForm.appendChild(commentField)
            }
            commentField.value = comment

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

            try {
                await declineRequest(mrid, comment)
                window.location.href = '/merges'
            } catch (error) {
                alert('Failed to decline merge request. Please try again.')
            }
        })
    }
}
