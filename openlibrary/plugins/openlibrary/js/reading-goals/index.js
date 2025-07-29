import { initDialogs } from '../native-dialog'
import { buildPartialsUrl } from '../utils'

/**
 * Adds listener to open reading goal modal.
 *
 * @param {HTMLCollection<HTMLElement>} links Prompts for adding a reading goal
 */
export function initYearlyGoalPrompt(links) {
    for (const link of links) {
        if (!link.classList.contains('goal-set')) {
            link.addEventListener('click', onYearlyGoalClick)
        }
    }
}

/**
 * Finds and shows the yearly goal modal.
 */
function onYearlyGoalClick() {
    const yearlyGoalModal = document.querySelector('#yearly-goal-modal')
    yearlyGoalModal.showModal()
}

/**
 * Updates year to the client's local year.
 *
 * Used to display the correct local year on 1 January.
 *
 * Elements passed to this function are expected to have a
 * `data-server-year` attribute, which is set to the server's
 * local year.
 *
 * @param {HTMLCollection<HTMLElement>} elems ELements which display only the current year
 */
export function displayLocalYear(elems) {
    const localYear = new Date().getFullYear()
    for (const elem of elems) {
        const serverYear = Number(elem.dataset.serverYear)
        if (localYear !== serverYear) {
            elem.textContent = localYear
        }
    }
}

/**
 * Adds click listeners to the given edit goal links.
 *
 * @param {HTMLCollection<HTMLElement>} editLinks Edit goal links
 */
export function initGoalEditLinks(editLinks) {
    for (const link of editLinks) {
        const parent = link.closest('.reading-goal-progress')
        const modal = parent.querySelector('dialog')
        addGoalEditClickListener(link, modal)
    }
}

/**
 * Adds click listener to the given edit link.
 *
 * Given modal will be displayed when the edit link
 * is clicked.
 * @param {HTMLElement} editLink An edit goal link
 * @param {HTMLDialogElement} modal The modal that will be shown
 */
function addGoalEditClickListener(editLink, modal) {
    editLink.addEventListener('click', function() {
        modal.showModal()
    })
}

/**
 * Adds click listeners to given collection of goal submission
 * buttons.
 *
 * @param {HTMLCollection<HTMLElement>} submitButtons Submit goal buttons
 */
export function initGoalSubmitButtons(submitButtons) {
    for (const button of submitButtons) {
        addGoalSubmissionListener(button)
    }
}

/**
 * Adds click listener to given reading goal form submission button.
 *
 * On click, POSTs form to server.  Updates view depending on whether
 * the action set a new goal, or updated an existing goal.
 * @param {HTMLELement} submitButton Reading goal form submit button
 */
function addGoalSubmissionListener(submitButton) {
    submitButton.addEventListener('click', function(event) {
        event.preventDefault()

        const form = submitButton.closest('form')

        if (!form.checkValidity()) {
            form.reportValidity()
            throw new Error('Form invalid')
        }
        const formData = new FormData(form)

        fetch(form.action, {
            method: 'POST',
            headers: {
                'content-type': 'application/x-www-form-urlencoded'
            },
            body: new URLSearchParams(formData)
        })
            .then((response) => {
                if (!response.ok) {
                    throw new Error('Failed to set reading goal')
                }
                const modal = form.closest('dialog')
                if (modal) {
                    modal.close()
                }

                const yearlyGoalSections = document.querySelectorAll('.yearly-goal-section')
                if (formData.get('is_update')) {  // Progress component exists on page
                    yearlyGoalSections.forEach((yearlyGoalSection) => {
                        const goalInput = form.querySelector('input[name=goal]')
                        const isDeleted = Number(goalInput.value) === 0

                        if (isDeleted) {
                            const chipGroup = yearlyGoalSection.querySelector('.chip-group')
                            const goalContainer = yearlyGoalSection.querySelector('#reading-goal-container')
                            if (chipGroup) {
                                chipGroup.classList.remove('hidden')
                            }
                            if (goalContainer) {
                                goalContainer.remove()
                            }
                        } else {
                            const progressComponent = modal.closest('.reading-goal-progress')
                            updateProgressComponent(progressComponent, Number(formData.get('goal')))
                        }
                    })
                } else {
                    const goalYear = formData.get('year')
                    fetchProgressAndUpdateViews(yearlyGoalSections, goalYear)
                    const banner = document.querySelector('.page-banner-mybooks')
                    if (banner) {
                        banner.remove()
                    }
                }
            })
    })
}

/**
 * Updates given reading goal progress component with a new
 * goal.
 *
 * @param {HTMLElement} elem A reading goal progress component
 * @param {Number} goal The new reading goal
 */
function updateProgressComponent(elem, goal) {
    // Calculate new percentage:
    const booksReadSpan = elem.querySelector('.reading-goal-progress__books-read')
    const booksRead = Number(booksReadSpan.textContent)
    const percentComplete = Math.floor((booksRead / goal) * 100)

    // Update view:
    const goalSpan = elem.querySelector('.reading-goal-progress__goal')
    const completedBar = elem.querySelector('.reading-goal-progress__completed')
    goalSpan.textContent = goal
    completedBar.style.width = `${Math.min(100, percentComplete)}%`
}

/**
 * Fetches and displays progress component.
 *
 * Adds listeners to the progress component, and hides
 * link for setting reading goal.
 *
 * @param {NodeList} yearlyGoalElems Containers for progress components and reading goal links.
 * @param {string} goalYear Year that the goal is set for.
 */
function fetchProgressAndUpdateViews(yearlyGoalElems, goalYear) {
    fetch(buildPartialsUrl('ReadingGoalProgress', {year: goalYear}))
        .then((response) => {
            if (!response.ok) {
                throw new Error('Failed to fetch progress element')
            }
            return response.json()
        })
        .then(function(data) {
            const html = data['partials']
            yearlyGoalElems.forEach((yearlyGoalElem) => {
                const progress = document.createElement('SPAN')
                progress.id = 'reading-goal-container'
                progress.innerHTML = html
                yearlyGoalElem.appendChild(progress)

                const link = yearlyGoalElem.querySelector('.set-reading-goal-link');
                if (link) {
                    if (link.classList.contains('li-title-desktop')) {
                        // Remove click listener in mobile views
                        link.removeEventListener('click', onYearlyGoalClick)
                    } else {
                        // Hide desktop "set 20XX reading goal" link
                        link.classList.add('hidden');
                    }
                }

                const progressEditLink = progress.querySelector('.edit-reading-goal-link')
                const updateModal = progress.querySelector('dialog')
                initDialogs([updateModal])
                addGoalEditClickListener(progressEditLink, updateModal)
                const submitButton = updateModal.querySelector('.reading-goal-submit-button')
                addGoalSubmissionListener(submitButton)
            })
        })
}
