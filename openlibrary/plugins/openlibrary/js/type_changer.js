/**
 * Functionality for TypeChanger.html
 */

export function initTypeChanger(elem) {
  // /about?m=edit - where this code is run

  function changeTemplate() {
    // Change the template of the page based on the selected value
    const searchParams = new URLSearchParams(window.location.search);
    const t = elem.value;
    searchParams.set('t', t);

    // Update the URL and navigate to the new page
    window.location.search = searchParams.toString();
  }

  elem.addEventListener('change', changeTemplate);
}
