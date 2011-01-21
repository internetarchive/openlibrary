
The works database stores the denormalized work documents.

Sample doc:

    {
        "key": "/works/OL1W",
        "type": {"key": "/type/work"},
        "title": "...",
        "editions": [
            {
                "key": "/books/OL1W",
                ...
            },
            ...       
        ]
    }
