from web import Storage

urls = Storage({
    'robots_txt': '/robots.txt',
    'service_health': '/health',
    'home_page': '/',
    'random_page': '/random',
    'apis': Storage({
        'availability_v2': '/availability/v2',
        'suggest': Storage({
            'search': '/suggest/search',
            'blurb': '/suggest/blurb/(.*)',
            'thumbnail': '/suggest/thumbnail'
        })
    }),
    'libraries': Storage({
        'notes': '(/libraries/[^/]+)/notes',
        'dashboard': '/libraries/dashboard',
        'pending_libraries': '/(libraries/pending-\d+)',
        'register': '/libraries/register',
        'locations': '/libraries/locations.txt',
        'stats': '/libraries/stats',
        'stats_per_library': '/libraries/stats/(.*).csv'
    }),
    'developers': Storage({
        'design': '/developers/design'
    }),
    'works': Storage({
        'ratings': '/works/OL(\d+)W/ratings',
        'editions': '(/works/OL\d+W)/editions',
        'bookshelves': '/works/OL(\d+)W/bookshelves',
        'edit': '(/works/OL\d+W)/edit',
        'autocomplete': '/works/_autocomplete'
    }),
    'authors': Storage({
        'home': '/authors',
        'search': '/search/authors',
        'works': '(/authors/OL\d+A)/works',
        'add': '/addauthor',
        'edit': '(/works/OL\d+W)/edit',
        'autocomplete': '/authors/_autocomplete'
    }),
    'books': Storage({
        'add_redir': '/addbook',
        'add': '/books/add',
        'edit': '(/books/OL\d+M)/edit',
        'lending': Storage({
            'borrow': '(/books/.*)/borrow',
            'borrow_status': '(/books/.*)/_borrow_status',
            'borrow_admin': '(/books/.*)/borrow_admin'
        }),
        'page_lookup': r'/(isbn|oclc|lccn|ia|ISBN|OCLC|LCCN|IA)/([^/]*)(/.*)?',
        'widget': '/(works|books)/(OL\d+[W|M])/widget',  # change to embed?
        'merge_editions': '/books/merge',
        'formats': Storage({
            'daisy': '(/books/.*)/daisy'
        })
    }),
    'lists': Storage({
        'home': '/lists',
        'by': '(/(?:people|books|works|authors|subjects)/[^/]+)/lists',
        'delete': '(/people/\w+/lists/OL\d+L)/delete',
        'user_list': Storage({            
            'home': '(/people/[^/]+/lists/OL\d+L)',
            'editions': '(/people/\w+/lists/OL\d+L)/editions',
            'subjects': '(/people/\w+/lists/OL\d+L)/subjects',
            'seeds': '(/people/\w+/lists/OL\d+L)/seeds',
            'embed': '(/people/\w+/lists/OL\d+L)/embed',
            'export': '(/people/\w+/lists/OL\d+L)/export',
            'atom_feed': '(/people/[^/]+/lists/OL\d+L)/feeds/(updates).(atom)'
        })
    }),
    'accounts': Storage({
        'create': '/account/create',
        'login': '/account/login',
        'loans': '/account/loans',
        'audit': '/account/audit',
        'manage': Storage({
            'privacy': '/account/privacy',
            'notifications': '/account/notifications',
            'lists': '/account/lists',
            'reading_log_redir': '/account/books',
            'reading_log': '/account/books/([a-zA-Z_-]+)'
        }),
        'public': Storage({
            'reading_log_redir': '/people/([^/]+)/books',
            'reading_log': '/people/([^/]+)/books/([a-zA-Z_-]+)'
        }),
        'verify': '/account/verify/([0-9a-f]*)',
        'verify_email': '/internal/account/audit',
        'update_email': '/account/email',
        'forgot_email_ol': '/account/email/forgot',
        'forgot_email_ia': '/account/email/forgot-ia',
        'forgot_password': '/account/password/forgot',
        'reset_password': '/account/password/reset/([0-9a-f]*)',
        'update_password': '/account/password'
    }),
    'languages': Storage({
        'autocomplete': '/languages/_autocomplete'
    }),
    'borrow': '/borrow',
    'borrow_ia': '/borrow/ia/(.*)',
    'lending': Storage({
        'receive_acs_borrow_updates': '/borrow/receive_notification',
        'receive_ia_borrow_updates': '/borrow/notify'
    }),
    'read': '/read',
    'about': Storage({
        'borrow': '/borrow/about'
    }),
    'internal': Storage({
        'invalidate_host': '/system/invalidate',
        'account_audit': '/internal/account/audit',
        'account_migration': '/internal/account/migration',
        'debug_memory': '/debug/memory',
        'spoofed': Storage({
            'availability': '/internal/fake/availability',
            'loans': '/internal/fake/loans',
            'xauth': '/internal/fake/xauth'
        })
    })
})
