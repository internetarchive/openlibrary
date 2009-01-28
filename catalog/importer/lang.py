from db_read import get_things

def get_langs():
    lang = []
    offset = 0
    while True:
        i = get_things({'type': '/type/language', 'limit': 100, 'offset': offset})
        lang += i
        if len(i) != 100:
            break
        offset += 100
    return set(lang)

languages = get_langs()

def add_lang(edition):
    if 'languages' not in edition:
        return
    lang_key = edition['languages'][0]['key']
    if lang_key in ('/l/   ', '/l/|||'):
        del edition['languages']
    elif lang_key not in languages:
        del edition['languages']
