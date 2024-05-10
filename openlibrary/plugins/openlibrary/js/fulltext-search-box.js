export function initFulltextSearchBox(fulltextSearchBox) {
  console.log('MACRO LOADED')
  getPartials(fulltextSearchBox)
}

async function getPartials(fulltextSearchBox) {

  return fetch('/partials.json?_component=FulltextSearchBox')
      .then((resp) => {
          if (resp.status !== 200) {
              throw new Error(`Failed to fetch partials. Status code: ${resp.status}`)
          }
          return resp.json()
      })
      .then((data) => {
        console.log('DATA FROM PARTIAL CALL', data)
        fulltextSearchBox.innerHTML = data['partials']
      })
}