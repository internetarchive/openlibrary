const SUBJECT_TYPES = ["subject", "person", "place", "time"]

let inputContainer
const inputSetMapping = {}

export function initTagTypeSelector(selector) {
    const subTypeInputs = document.querySelectorAll(".sub-type-inputs__input-set")
    inputContainer = document.querySelector(".sub-type-inputs")

    subTypeInputs.forEach((input) => {
        inputSetMapping[input.dataset.inputType] = input
    })
    inputContainer.textContent = ""

    if (selector.value) {
        if (SUBJECT_TYPES.includes(selector.value)) {
            showSubTypeInputs('subject')
        } else {
            showSubTypeInputs(selector.value)
        }
    }

    selector.addEventListener("change", (event) => {
        const selectedValue = event.target.value
        let selectedType
        if (SUBJECT_TYPES.includes(selectedValue)) {
            selectedType = 'subject'
        } else {
            selectedType = selectedValue
        }

        hideSubTypeInputs()
        if (selectedType) {
            showSubTypeInputs(selectedType)
        }
    })
}

function hideSubTypeInputs() {
    inputContainer.textContent = ""
}

function showSubTypeInputs(inputsToShow) {
    inputContainer.appendChild(inputSetMapping[inputsToShow])
}
