let isTitleVisible = false

export function initCompactTitle(navbar, title) {
    // Show compact title on page reload:
    if (navbar.getBoundingClientRect().top === 35) {
        title.classList.remove('hidden')
        title.style.top = '0px'
        isTitleVisible = true
    }

    window.addEventListener('scroll', function() {
        onScroll(navbar, title)
    })
}

function onScroll(navbar, title) {
    const navbarY = navbar.getBoundingClientRect().top;

    if (navbarY === 35) {
        if (title.classList.contains('hidden')) {
            title.classList.remove('hidden')
        }
        if (!isTitleVisible) {
            isTitleVisible = true
            title.style.top = '0px'
            title.classList.remove('compact-title--slideout')
            title.classList.add('compact-title--slidein')
        }
    } else {
        if (isTitleVisible) {
            isTitleVisible = false
            title.style.top = '-35px'
            title.classList.remove('compact-title--slidein')
            title.classList.add('compact-title--slideout')
        }
    }
}
