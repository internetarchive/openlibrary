def get_cover_url(edition):
    if edition.get('cover'):
        return edition['cover']
    return url_for('static', filename='images/no-cover.png')
