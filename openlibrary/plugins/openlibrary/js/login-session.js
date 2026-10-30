/**
 * After a login through the login dialog the page is still the one rendered
 * for a visitor, so the header offers Log In and Sign Up to someone who just
 * did. Swap both for a My Books link until the next page load renders the real
 * signed-in header. The label comes from the dialog's translated strings.
 */

const MY_BOOKS_HREF = '/account/books';

function myBooksLink(className, label) {
    const link = document.createElement('a');
    link.className = className;
    link.href = MY_BOOKS_HREF;
    link.textContent = label;
    return link;
}

export function onLoginSuccess() {
    const label = document.querySelector('ol-login-dialog')?.labels?.myBooks || 'My Books';
    const headerAuth = document.querySelector('.header-bar .auth-component');
    if (headerAuth) {
        const item = document.createElement('li');
        item.append(myBooksLink('ol-button-static ol-button-static--primary', label));
        headerAuth.replaceChildren(item);
    }
    const drawerAuth = document.querySelector('.drawer-menu__login-links');
    if (drawerAuth) drawerAuth.replaceChildren(myBooksLink('drawer-menu__login-primary', label));
}

export function initLoginSession() {
    document.addEventListener('ol-login-success', onLoginSuccess);
}
