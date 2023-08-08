import { CreateListForm } from './CreateListForm'
import { MyBooksDropper } from './MyBooksDropper'
import myBooksStore from './store'
import { getListPartials } from '../lists/ListService'
import { ShowcaseItem, createActiveShowcaseItem, toggleActiveShowcaseItems } from '../lists/ShowcaseItem'
import { removeChildren } from '../utils'

// XXX : jsdoc
// XXX : decompose
export function initMyBooksAffordances(dropperElements, showcaseElements) {
    const showcases = []
    for (const elem of showcaseElements) {
        const showcase = new ShowcaseItem(elem)
        showcase.initialize()

        showcases.push(showcase)
    }

    myBooksStore.set('SHOWCASES', showcases)

    const form = document.querySelector('#create-list-form')
    const createListForm = new CreateListForm(form)
    createListForm.initialize()

    /** @type {Array<MyBooksDropper>} */
    const droppers = []
    /** @type {Array<string>} */
    const seedKeys = []
    for (const dropper of dropperElements) {
        const myBooksDropper = new MyBooksDropper(dropper)
        myBooksDropper.initialize()

        droppers.push(myBooksDropper)
        seedKeys.push(myBooksDropper.getSeedKeys())
    }

    // Remove duplicate keys:
    const seedKeySet = new Set(...seedKeys)

    // Get user key from first Dropper and add to store:
    const userKey = droppers[0].readingLists.userKey
    myBooksStore.set('USER_KEY', userKey)

    myBooksStore.set('DROPPERS', droppers)

    getListPartials()
        .then(response => response.json())
        .then((data) => {
            // XXX : convert this block to one or two function calls
            const listData = data.listData
            /** @type {Array<HTMLLIElement>} */
            const activeShowcaseItems = []
            for (const listKey in listData) {
                // Check for matches between seed keys and list members
                // If match, create new active showcase item

                for (const seedKey of listData[listKey].members) {
                    if (seedKeySet.has(seedKey)) {
                        activeShowcaseItems.push(createActiveShowcaseItem(listKey, seedKey, listData[listKey].listName))
                    }
                }
            }

            const activeListsShowcaseElem = document.querySelector('.already-lists')

            if (activeListsShowcaseElem) {
                // Remove the loading indicator:
                removeChildren(activeListsShowcaseElem)

                for (const li of activeShowcaseItems) {
                    activeListsShowcaseElem.appendChild(li)

                    const showcase = new ShowcaseItem(li)
                    showcase.initialize()

                    showcases.push(showcase)
                }
                toggleActiveShowcaseItems(false)
            }

            // Update dropper content:
            for (const dropper of droppers) {
                dropper.updateReadingLists(data['dropper'])
            }
        })
}
