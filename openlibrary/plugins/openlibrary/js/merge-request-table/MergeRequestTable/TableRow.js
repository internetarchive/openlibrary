/**
 * Defines functionality related to librarian request table rows.
 *
 * @module merge-request-table/MergeRequestTable/TableRow
 */

import { claimRequest, commentOnRequest, declineRequest, unassignRequest } from '../MergeRequestService'
import { FadingToast } from '../../Toast'

let i18nStrings;

export function setI18nStrings(localizedStrings) {
  i18nStrings = localizedStrings;
}

/**
 * Represents a row in the librarian request table.
 *
 * A row contains details about a single librarian request, and
 * offers affordances to comment on the request, self-close a request,
 * or claim a request for review.
 *
 * Any references to "this request" in this class's documentation refer
 * to the librarian request that the TableRow refrences.
 *
 * @class
 */
export class TableRow {
  /**
     * Creates a new librarian request table row.
     *
     * Stores reference to each interactive element in a row.
     *
     * @param {HTMLElement} row Root element of a table row
     * @param {string} username `username` of logged-in patron. Empty if unauthenticated.
     */
  constructor(row, username) {
    /**
         * Reference to this row.
         *
         * @param {HTMLElement}
         */
    this.row = row
    /**
         * `username` of authenticated patron, or '' if unauthenticated.
         *
         * @param {HTMLElement}
         */
    this.username = username
    /**
         * Unique identifier for this row.
         *
         * @param {Number}
         */
    this.mrid = row.dataset.mrid
    /**
         * Button used to toggle the full comments display's visibility.
         *
         * @param {HTMLElement}
         */
    this.toggleCommentButton = row.querySelector('.mr-comment-toggle__comment-expand')
    /**
         * Element which displays this row's comment count.
         *
         * @param {HTMLElement}
         */
    this.commentCountDisplay = row.querySelector('.mr-comment-toggle__comment-count')
    /**
         * Element displaying the most recent comment on this request.
         *
         * @param {HTMLElement}
         */
    this.commentPreview = row.querySelector('.mr-details__comment-preview')
    /**
         * Hidden comments display. Also contains reply inputs, if rendered.
         *
         * @param {HTMLElement}
         */
    this.fullCommentsPanel = row.querySelector('.comment-panel')
    /**
         * Element that displays all of the comments for this request.
         *
         * @param {HTMLElement}
         */
    this.commentsDisplay = this.fullCommentsPanel.querySelector('.comment-panel__comment-display')
    /**
         * The comment text input.
         *
         * @param {HTMLElement|null}
         */
    this.commentReplyInput = this.fullCommentsPanel.querySelector('.comment-panel__reply-input')
    /**
         * The comment reply button.
         *
         * @param {HTMLElement|null}
         */
    this.replyButton = this.fullCommentsPanel.querySelector('.comment-panel__reply-btn')
    /**
         * Affordance which allows one to close their own request.
         *
         * Only available on a patron's own open requests.
         *
         * @param {HTMLElement|null}
         */
    this.closeRequestButton = this.row.querySelector('.mr-close-link')
    /**
         * Button used by super-librarians to claim a request.
         *
         * @param {HTMLElement}
         */
    this.reviewButton = this.row.querySelector('.mr-review-actions__review-btn')
    /**
         * Reference to root element of the assignee display.
         *
         * @param {HTMLElement}
         */
    this.assigneeElement = this.row.querySelector('.mr-review-actions__assignee')
    /**
         * Assignee display element which displays the assignee's name.
         *
         * @param {HTMLElement}
         */
    this.assigneeLabel = this.row.querySelector('.mr-review-actions__assignee-name')
    /**
         * Element that unassignees the current reviewer when clicked.
         *
         * @param {HTMLElement}
         */
    this.unassignReviewerButton = this.row.querySelector('.mr-review-actions__unassign')
  }

  /**
     * Hydrates interactive elements in this row.
     */
  initialize() {
    this.toggleCommentButton.addEventListener('click', () => this.toggleComments())
    if (this.closeRequestButton) {
      this.closeRequestButton.addEventListener('click', () => this.closeRequest())
    }
    if (this.replyButton && this.commentReplyInput) {
      this.replyButton.addEventListener('click', () => this.addComment())
    }
    this.reviewButton.addEventListener('click', () => this.claimRequest())
    if (this.unassignReviewerButton) {
      this.unassignReviewerButton.addEventListener('click', () => this.unassignReviewer())
    }
  }

  /**
     * Toggles which comment display is currently visible.
     *
     * On page load the comment preview display is visible, while
     * the full comments panel is hidden. This function toggles
     * each element's visibility.
     */
  toggleComments() {
    this.commentPreview.classList.toggle('hidden')
    this.fullCommentsPanel.classList.toggle('hidden')

    // Add depressed effect to toggle button:
    this.toggleCommentButton.classList.toggle('mr-comment-toggle__comment-expand--active');
  }

  /**
     * Closes the request linked to this row, and removes this
     * row from the DOM.
     */
  async closeRequest() {
    const comment = prompt(i18nStrings['close_request_comment_prompt'])
    if (comment !== null) {  // Comment will be `null` if "Cancel" button pressed
      await declineRequest(this.mrid, comment)
        .then(result => result.json())
        .then(data => {
          if (data.status === 'ok') {
            this.row.parentElement.removeChild(this.row)
          }
        })
        .catch(e => {
          // XXX : toast?
          throw e
        })
    }
  }

  /**
     * `POST`s a new comment to the server.
     *
     * Updates the view on success.
     */
  async addComment() {
    const comment = this.commentReplyInput.value.trim()
    if (comment) {
      await commentOnRequest(this.mrid, comment)
        .then(result => result.json())
        .then(data => {
          if (data.status === 'ok') {
            this.updateCommentViews(comment)
            this.commentReplyInput.value = ''
          } else {
            new FadingToast(i18nStrings['comment_submission_failure_message']).show()
          }
        })
        .catch(e => {
          throw e
        })
    }
  }

  /**
     * Updates row, setting given comment as most recent.
     *
     * First, escapes given comment. Replaces text of comment
     * preview with escaped comment. Add new comment element to
     * full comments display. Increments the row's comment count.
     *
     * @param {string} comment The newly added comment.
     */
  updateCommentViews(comment) {
    const escapedComment = document.createTextNode(comment)

    // Update preview:
    this.commentPreview.innerText = escapedComment.textContent

    // Update full display:
    const newComment = document.createElement('div')
    newComment.classList.add('comment-panel__comment')
    newComment.innerHTML = `<span class="commenter">@${this.username}</span> `
    newComment.appendChild(escapedComment)

    this.commentsDisplay.appendChild(newComment)
    this.commentsDisplay.scrollTop = this.commentsDisplay.scrollHeight

    // Update comment count:
    const count = Number(this.commentCountDisplay.innerText) + 1
    this.commentCountDisplay.innerText = count
  }

  /**
     * `POST`s claim to review this request, then updates the view.
     *
     * Hides the review button, and shows the assignee display.
     */
  async claimRequest() {
    await claimRequest(this.mrid)
      .then(result => result.json())
      .then(data => {
        if (data.status === 'ok') {
          this.assigneeLabel.innerText = `@${this.username}`
          this.assigneeElement.classList.remove('hidden')
          this.reviewButton.classList.add('hidden')
        }
      })
  }

  /**
     * `POST`s request to remove current assignee, then updates the view.
     *
     * Hides the assignee display and shows the review button on success.
     */
  async unassignReviewer() {
    await unassignRequest(this.mrid)
      .then(result => result.json())
      .then(data => {
        if (data.status === 'ok') {
          this.assigneeElement.classList.add('hidden')
          this.reviewButton.classList.remove('hidden')
        }
      })
  }
}
