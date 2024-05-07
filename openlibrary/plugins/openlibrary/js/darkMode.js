export function initDarkMode() {
    const body = document.querySelector('body');
    const icon = document.getElementById('darkModeIcon')
    const cookie = document.cookie
    if (!cookie.includes('dm=True')) {
        const dm = 'dm'
        const darkModeValue ='True';
        const cookieStr = `${dm}=${encodeURIComponent(darkModeValue)}`;
        document.cookie = cookieStr;
        body.classList.add('dark-theme');
        icon.src = "./static/images/sunIcon.png"
    } else {
        document.cookie = 'dm=; path=/'
        body.classList.remove('dark-theme');
        icon.src = "./static/images/moonIcon.png"
    }
}