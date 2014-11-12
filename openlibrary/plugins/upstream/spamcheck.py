import web

def get_spam_words():
    doc = web.ctx.site.store.get("spamwords") or {}
    return doc.get("spamwords", [])

def get_spam_domains():
    doc = web.ctx.site.store.get("spamwords") or {}
    return doc.get("domains", [])

def set_spam_words(words):
    words = [w.strip() for w in words]
    _update_spam_doc(spamwords=words)

def set_spam_domains(domains):
    domains = [d.strip() for d in domains]
    _update_spam_doc(domains=domains)

def _update_spam_doc(**kwargs):
    doc = web.ctx.site.store.get("spamwords") or {}
    doc.update(_key="spamwords", **kwargs)
    web.ctx.site.store["spamwords"] = doc
    
def is_spam(i=None):
    user = web.ctx.site.get_user()
    email = user and user.get_email() or ""
    if is_spam_email(email):
        return True

    # For some odd reason, blocked accounts are still allowed to make edits.
    # Hack to stop that.
    account = user and user.get_account()
    if account and account.get('status') != 'active':
        return True

    spamwords = get_spam_words()
    if i is None:
        i = web.input()
    text = str(dict(i)).lower()
    return any(w.lower() in text for w in spamwords)

def is_spam_email(email):
    domain = email.split("@")[-1].lower()
    return domain in get_spam_domains()
