import json

import web

from infogami.utils import delegate
from openlibrary.core.likes import Likes


class likes_control(delegate.page):
    path = "/api/like"

    def POST(self):
        user = web.ctx.site.get_user()
        data = json.loads(web.data())
        key = data.get("key")
        if not user:
            raise web.unauthorized()
        value = data.get("value", 1)
        username = user.key.split("/")[-1]
        try:
            Likes.like(username, key, value)
        except ValueError as e:
            raise web.badrequest(str(e))

        return delegate.RawText(json.dumps({"key": key, "value": value}))

    def DELETE(self):
        user = web.ctx.site.get_user()
        data = json.loads(web.data())
        key = data.get("key")
        if not user:
            raise web.unauthorized()
        username = user.key.split("/")[-1]
        Likes.unlike(username, key)
        return delegate.RawText(
            json.dumps(
                {
                    "key": key,
                }
            )
        )


class get_likes_record(delegate.page):
    path = "/api/likes"

    def GET(self):
        i = web.input(key="")
        key = i.key
        if not key:
            raise web.badrequest()
        count = Likes.get_count(key)
        if user := web.ctx.site.get_user():
            username = user.key.split("/")[-1]
            patron_liked = Likes.patron_liked(username, key)
            result = {
                "likes": count["likes"],
                "dislikes": count["dislikes"],
                "patron_liked": patron_liked,
            }
        else:
            patron_liked = False
            result = {
                "likes": count["likes"],
                "dislikes": count["dislikes"],
                "patron_liked": patron_liked,
            }
        return delegate.RawText(json.dumps(result))


class get_patron_likes(delegate.page):
    path = "/api/patron/likes"

    def GET(self):
        i = web.input(username="", limit=50, offset=0)
        likes = Likes.get_for_patron(i.username, int(i.limit), int(i.offset))
        return delegate.RawText(json.dumps(list(likes), default=str))
