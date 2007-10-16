import db

_d = {
    'web': 'User reviews (from web).',
    'dev': 'Dev/test reviews.'
}

class ReviewSources:

    def __init__(self):
        self.data = {}

    def load_review_source(self, key):
        self.data[key] = db.get_review_source('rs/%s_reviews' % key, 
                                              description=_d[key],
                                              create=True)

    def get(self, key):
        if key not in _d.keys():
            raise KeyError('Review source \'%s\' does not exist.' % key)
        if key not in self.data.keys():
            self.load_review_source(key) 
        return self.data[key]

data = ReviewSources()
