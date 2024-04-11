function createListFormMarkup(isFilled) {
    const listName = isFilled ? 'My New List' : ''
    const listDescription = isFilled ? 'A list for all of my books' : ''

    return `
      <form method="post" class="floatform" name="new-list" id="new-list">
      <div class="formElement">
          <div class="label">
              <label for="list_label">Name:</label>
          </div>
          <div class="input">
              <input type="text" name="list_label" id="list_label" class="text required" value="${listName}" required="">
          </div>
      </div>
      <div class="formElement">
          <div class="label">
              <label for="list_desc">Description:</label>
          </div>
          <div class="input">
              <textarea name="list_desc" id="list_desc" rows="5" cols="30">${listDescription}</textarea>
          </div>
      </div>
      <div class="formElement">
          <div class="input">
              <button id="create-list-button" type="submit" class="larger">Create new list</button>
              &nbsp; &nbsp;
              <a class="small dialog--close plain red" href="javascript:;">Cancel</a>
          </div>
      </div>
      </form>
    `
}

export const listCreationForm = createListFormMarkup(false)
export const filledListCreationForm = createListFormMarkup(true)

export const showcaseI18nInput = '<input type="hidden" name="list-i18n-strings" value="{&quot;cover_of&quot;: &quot;Cover of: &quot;, &quot;see_this_list&quot;: &quot;See this list&quot;, &quot;remove_from_list&quot;: &quot;Remove from your list?&quot;, &quot;from&quot;: &quot;from&quot;, &quot;you&quot;: &quot;You&quot;}"></input>'

const DEFAULT_COVER_URL = '/images/icons/avatar_book-sm.png'

/**
 * @typedef {Object} ShowcaseDetails
 * @property {string} listKey
 * @property {string} seedKey
 * @property {string} listTitle
 * @property {string} listOwner
 * @property {string} seedType
 */
/**
 *
 * @param {boolean} isActiveShowcase
 * @param {Array<ShowcaseDetails>} showcaseData
 */
function createShowcaseMarkup(isActiveShowcase, showcaseData) {
    const listId = isActiveShowcase ? 'already-lists' : 'list-lists'
    const listClasses = 'listLists'.concat(isActiveShowcase ? ' already-lists' : '')

    let showcaseMarkup = ''

    for (const data of showcaseData) {
        showcaseMarkup += `<li class="actionable-item">
            <span class="image">
              <a href="${data.listKey}"><img src="${DEFAULT_COVER_URL}" alt="Cover of: ${data.listTitle}" title="Cover of: ${data.listTitle}"></a>
            </span>
            <span class="data">
                <span class="label">
                    <a href="${data.listKey}" data-list-title="${data.listTitle}" title="See this list">${data.listTitle}</a>
                    <input type="hidden" name="seed-title" value="${data.listTitle}">
                    <input type="hidden" name="seed-key" value="${data.seedKey}">
                    <input type="hidden" name="seed-type" value="${data.seedType}">

                    <a href="${data.listKey}" class="remove-from-list red smaller arial plain" data-list-key="${data.listKey}" title="Remove from your list?">[X]</a>
                </span>
                <span class="owner">from <a href="${data.listOwner}">You</a></span>
            </span>
        </li>
        `
    }

    return `<ul id="${listId}" class="${listClasses}">
            ${showcaseMarkup}
        </ul>
        `
}

export const showcaseDetailsData = [
    {
        listKey: '/people/openlibrary/lists/OL1L',
        seedKey: '/works/OL54120W',
        listTitle: 'My First List',
        listOwner: '/people/openlibrary',
        seedType: 'work'
    },
    {
        listKey: '/people/openlibrary/lists/OL1L',
        seedKey: '/books/OL3421846M',
        listTitle: 'My First List',
        listOwner: '/people/openlibrary',
        seedType: 'edition'
    },
    {
        listKey: '/people/openlibrary/lists/OL2L',
        seedKey: '/works/OL54120W',
        listTitle: 'Another List',
        listOwner: '/people/openlibrary',
        seedType: 'work'
    },
    {
        listKey: '/people/openlibrary/lists/OL1L',
        seedKey: '/authors/OL18319A',
        listTitle: 'My First List',
        listOwner: '/people/openlibrary',
        seedType: 'author'
    },
    {
        listKey: '/people/openlibrary/lists/OL1L',
        seedKey: 'quotations',
        listTitle: 'My First List',
        listOwner: '/people/openlibrary',
        seedType: 'subject'
    },
]

export const multipleShowcasesOnPage = createShowcaseMarkup(true, [showcaseDetailsData[0], showcaseDetailsData[2]]) + createShowcaseMarkup(false, [showcaseDetailsData[0], showcaseDetailsData[1]])
export const activeListShowcase = createShowcaseMarkup(true, [showcaseDetailsData[0]])
export const listsSectionShowcase = createShowcaseMarkup(false, [showcaseDetailsData[0]])
export const subjectShowcase = createShowcaseMarkup(false, [showcaseDetailsData[4]])
export const authorShowcase = createShowcaseMarkup(false, [showcaseDetailsData[3]])
export const workShowcase = createShowcaseMarkup(false, [showcaseDetailsData[0]])
export const editionShowcase = createShowcaseMarkup(false, [showcaseDetailsData[1]])


