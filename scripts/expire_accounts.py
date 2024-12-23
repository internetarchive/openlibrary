from datetime import UTC, datetime

import web


def delete_old_links():
    for doc in web.ctx.site.store.values(type="account-link"):
        expiry_date = datetime.strptime(doc["expires_on"], "%Y-%m-%dT%H:%M:%S.%f")
        now = datetime.now(UTC)
        key = doc["_key"]
        if expiry_date > now:
            print(f'Deleting link {key}')
            del web.ctx.site.store[key]
        else:
            print(f'Retaining link {key}')


def main():
    delete_old_links()
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
