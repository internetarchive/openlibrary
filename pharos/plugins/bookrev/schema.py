# type definitions: (<name>, <properties>)

reviewsource = ('type/reviewsource', {
    'description': 'type/string'
})

bookreview = ('type/bookreview', {
    'book': 'type/edition', 
    'author': 'type/user', 
    'title': 'type/string',
    'source': 'type/reviewsource', 
    'text': 'type/text',
    'url': 'type/string'
})

vote = ('type/vote', {
    'review': 'type/bookreview', 
    'user': 'type/user',
    'weight': 'type/int'
})

comment = ('type/comment', {
    'running_id': 'type/int',
    'target': 'type/type',
    'author': 'type/user',
    'parent_comment': 'type/type', # makes impl simpler
    'text': 'type/text'
})


# backreferences: (<type_name>, <prop_name>, <ref_type_name>, <ref_prop_name>)

backreferences = [
    ('type/user', 'reviews', 'type/bookreview', 'author'),
    ('type/edition', 'reviews', 'type/bookreview', 'book'),
    ('type/bookreview', 'votes', 'type/vote', 'review'),
    ('type/bookreview', 'comments', 'type/comment', 'target')
]

