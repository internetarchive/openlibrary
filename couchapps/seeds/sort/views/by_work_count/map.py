def map(doc):
    if 'works' in doc:
        yield doc['works'], None