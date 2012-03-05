"""Script to detect bad author merges from infobase write logs.

It is noticed that some author merges reverting some work pages to an older
revision when updating the author info.

https://github.com/internetarchive/openlibrary/issues/89

It can be identified by looking at the revision in `changes` of the changeset
and the input query given. The difference between the revisions should be
exactly 1 if everything is alright. It is a bad-merge if the difference is
more than 1.
"""
import sys
import json

def read():
    for line in sys.stdin:
        try:
            yield json.loads(line.strip())
        except ValueError:
            # bad JSON
            pass

def read_author_merges():
    return (row for row in read() 
                if row.get('action') == 'save_many' 
                and row['data']['changeset']['kind'] == 'merge-authors')

def is_bad_merge(row):
    """A merge is bad if the difference between revision of any modified page
    in the input and after merge is more than 1.
    
    Returns the list of keys of effected docs. It will be empty list if the merge is alright.
    """
    # revisions from the input query
    revs = dict((doc['key'], doc.get('revision')) for doc in row['data']['query'])
    # (key, revision) tuples from changeset changes
    changes = [(c['key'], c['revision']) for c in row['data']['changeset']['changes']]    
    return [key for key, rev in changes if revs[key] is not None and rev - revs[key] > 1]

def main():
    for row in read_author_merges():
        keys = is_bad_merge(row)
        if keys:
            print row['timestamp'], row['data']['changeset']['id'], " ".join(keys)

if __name__ == '__main__':
    main()