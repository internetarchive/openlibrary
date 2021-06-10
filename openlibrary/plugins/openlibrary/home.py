"""Controller for home page.
"""
import datetime
import random
import web
import logging

from infogami.utils import delegate
from infogami.utils.view import render_template, public
from infogami.infobase.client import storify
from infogami import config

from openlibrary.core import admin, cache, ia, lending, \
    helpers as h
from openlibrary.utils import dateutil
from openlibrary.plugins.upstream.utils import get_blog_feeds
from openlibrary.plugins.worksearch import search, subjects

import six


logger = logging.getLogger("openlibrary.home")

CAROUSELS_PRESETS = {
    'preset:thrillers': '(creator:"Clancy, Tom" OR creator:"King, Stephen" OR creator:"Clive Cussler" OR creator:("Cussler, Clive") OR creator:("Dean Koontz") OR creator:("Koontz, Dean") OR creator:("Higgins, Jack")) AND !publisher:"Pleasantville, N.Y. : Reader\'s Digest Association" AND languageSorter:"English"',
    'preset:comics': '(subject:"comics" OR creator:("Gary Larson") OR creator:("Larson, Gary") OR creator:("Charles M Schulz") OR creator:("Schulz, Charles M") OR creator:("Jim Davis") OR creator:("Davis, Jim") OR creator:("Bill Watterson") OR creator:("Watterson, Bill") OR creator:("Lee, Stan"))',
    'preset:authorsalliance_mitpress': (
        '(openlibrary_subject:(authorsalliance) OR collection:(mitpress) OR '
        'publisher:(MIT Press) OR openlibrary_subject:(mitpress))'
    )
}

MONTHLY_READS = {
    2: {
        'title': 'Books for February',
        'url': '/collections/february',
        'query': 'key:(/works/OL18181363W OR /works/OL3481095W OR /works/OL4360244W OR /works/OL20017931W OR /works/OL20615204W OR /works/OL2363176W OR /works/OL17869588W OR /works/OL17784026W OR /works/OL21179764W OR /works/OL8870595W OR /works/OL21054973W OR /works/OL21673730W OR /works/OL20548582W OR /works/OL15279153W OR /works/OL19992836W OR /works/OL15691480W OR /works/OL16305795W OR /works/OL19923407W OR /works/OL16529029W OR /works/OL9242636W OR /works/OL17529769W OR /works/OL3345332W OR /works/OL20013209W OR /works/OL20015483W OR /works/OL19987474W OR /works/OL19992114W OR /works/OL17893900W OR /works/OL18435803W OR /works/OL17314666W OR /works/OL17358927W OR /works/OL15933199W OR /works/OL17858931W OR /works/OL18187603W OR /works/OL16853133W OR /works/OL16894393W OR /works/OL19976062W OR /works/OL20037832W OR /works/OL16885033W OR /works/OL19708155W OR /works/OL17921756W OR /works/OL21037237W OR /works/OL17786027W OR /works/OL17345141W OR /works/OL21294275W OR /works/OL9582417W OR /works/OL9357555W OR /works/OL20907853W OR /works/OL20005568W OR /works/OL3296483W OR /works/OL11983310W OR /works/OL7159886W OR /works/OL1662667W OR /works/OL19990553W OR /works/OL15285884W OR /works/OL6888879W OR /works/OL17900435W OR /works/OL5706069W OR /works/OL2977589W OR /works/OL1593701W OR /works/OL16451688W OR /works/OL16910779W OR /works/OL18215336W OR /works/OL17371695W OR /works/OL3521634W OR /works/OL17355199W OR /works/OL5739152W OR /works/OL20016962W OR /works/OL3191599W OR /works/OL20896695W OR /works/OL19752490W OR /works/OL18335154W OR /works/OL4582875W OR /works/OL16515210W OR /works/OL16868407W OR /works/OL3459949W OR /works/OL16025481W OR /works/OL1928280W OR /works/OL6208302W OR /works/OL17566265W OR /works/OL20652811W OR /works/OL22059158W OR /works/OL4370955W OR /works/OL19998526W OR /works/OL6218060W OR /works/OL16813953W OR /works/OL21179974W OR /works/OL7213898W OR /works/OL17872185W OR /works/OL17340085W OR /works/OL21584979W OR /works/OL21078916W OR /works/OL158519W OR /works/OL4114499W OR /works/OL19638041W OR /works/OL16844793W OR /works/OL20940485W OR /works/OL17392121W OR /works/OL20030448W OR /works/OL15920474W OR /works/OL20544657W)'
    },
    3: {
        'title': 'Books for March',
        'url': '/collections/march',
        'query': 'key:(/works/OL5184754W OR /works/OL133486W OR /works/OL1112900W OR /works/OL15302479W OR /works/OL5353481W OR /works/OL1684657W OR /works/OL16612125W OR /works/OL2987652W OR /works/OL15243975W OR /works/OL5827897W OR /works/OL237034W OR /works/OL20916117W OR /works/OL1881592W OR /works/OL16561534W OR /works/OL17893247W OR /works/OL7000994W OR /works/OL16247899W OR /works/OL19163127W OR /works/OL1146619W OR /works/OL2231866W OR /works/OL1853601W OR /works/OL1794792W OR /works/OL2750502W OR /works/OL1825970W OR /works/OL17991110W OR /works/OL34442W OR /works/OL20886755W OR /works/OL1880057W OR /works/OL9221039W OR /works/OL4782577W OR /works/OL15230140W OR /works/OL7899614W OR /works/OL508764W OR /works/OL18165887W OR /works/OL17538396W OR /works/OL53994W OR /works/OL11817902W OR /works/OL5118902W OR /works/OL68789W OR /works/OL8874375W OR /works/OL158240W OR /works/OL3474021W OR /works/OL3352379W OR /works/OL1826369W OR /works/OL106972W OR /works/OL20623337W OR /works/OL2624393W OR /works/OL47755W OR /works/OL514392W OR /works/OL18820761W OR /works/OL85496W OR /works/OL21625058W OR /works/OL1833297W OR /works/OL15162472W OR /works/OL16289374W OR /works/OL15100036W OR /works/OL17311133W OR /works/OL1826373W OR /works/OL3255337W OR /works/OL7113090W OR /works/OL5408044W OR /works/OL4702292W OR /works/OL8269570W OR /works/OL2626142W OR /works/OL9399062W OR /works/OL6670269W OR /works/OL890505W OR /works/OL523724W OR /works/OL6218068W OR /works/OL1469543W OR /works/OL1001250W OR /works/OL20004703W OR /works/OL679942W OR /works/OL2044569W OR /works/OL15980420W OR /works/OL20016033W OR /works/OL565273W OR /works/OL20019003W OR /works/OL18820945W OR /works/OL3945614W OR /works/OL64468W OR /works/OL5754207W OR /works/OL6218046W OR /works/OL18183638W OR /works/OL21182317W OR /works/OL169921W OR /works/OL6384123W OR /works/OL1870681W OR /works/OL16245602W OR /works/OL17676089W OR /works/OL20848500W OR /works/OL4304829W OR /works/OL17873811W OR /works/OL4968024W OR /works/OL20001088W OR /works/OL3142310W OR /works/OL142101W OR /works/OL19396225W OR /works/OL1230977W OR /works/OL17332299W)'
    },
    4: {
      'title': 'Books for April',
      'url': '/collections/april',
      'query': 'key:(/works/OL6934547W OR /works/OL2000340W OR /works/OL2746188W OR /works/OL2921990W OR /works/OL11476041W OR /works/OL8676892W OR /works/OL1895089W OR /works/OL8463108W OR /works/OL1916767W OR /works/OL17328163W OR /works/OL34364W OR /works/OL2384851W OR /works/OL79422W OR /works/OL142101W OR /works/OL5719058W OR /works/OL548264W OR /works/OL15120217W OR /works/OL14952471W OR /works/OL15188310W OR /works/OL1855830W OR /works/OL3147556W OR /works/OL5843701W OR /works/OL20479918W OR /works/OL17864309W OR /works/OL5857644W OR /works/OL18174472W OR /works/OL13750798W OR /works/OL14869488W OR /works/OL15844569W OR /works/OL510286W OR /works/OL2650512W OR /works/OL83989W OR /works/OL1914072W OR /works/OL5097914W OR /works/OL1927820W OR /works/OL112630W OR /works/OL6218052W OR /works/OL12992964W OR /works/OL8460319W OR /works/OL308951W OR /works/OL14909580W OR /works/OL17077479W OR /works/OL4445284W OR /works/OL17437756W OR /works/OL8193508W OR /works/OL5590179W OR /works/OL166683W OR /works/OL83989W OR /works/OL45869W OR /works/OL3840897W OR /works/OL15289753W OR /works/OL22056274W OR /works/OL2279297W OR /works/OL71856W OR /works/OL45790W OR /works/OL6704886W OR /works/OL9770557W OR /works/OL524611W OR /works/OL45709W OR /works/OL66562W OR /works/OL8455191W OR /works/OL15065463W OR /works/OL1173603W OR /works/OL15692492W OR /works/OL25860W OR /works/OL53908W OR /works/OL2342157W OR /works/OL17324165W OR /works/OL261405W OR /works/OL17324092W OR /works/OL263663W OR /works/OL2695471W OR /works/OL587092W OR /works/OL2695710W OR /works/OL20892865W OR /works/OL15392519W OR /works/OL138536W OR /works/OL88641W OR /works/OL151924W OR /works/OL15021422W OR /works/OL9355810W OR /works/OL5097109W OR /works/OL3368666W OR /works/OL50625W OR /works/OL8076534W OR /works/OL17059208W OR /works/OL3974810W OR /works/OL1910135W OR /works/OL201059W OR /works/OL100672W OR /works/OL17900251W OR /works/OL54031W OR /works/OL76590W OR /works/OL17063120W OR /works/OL3288436W OR /works/OL997592W OR /works/OL19360441W OR /works/OL17857052W OR /works/OL1993508W OR /works/OL17872769W)'
    },
    5: {
      'title': 'Books for May',
      'url': '/collections/may',
      'query': 'key:(/works/OL450777W OR /works/OL362289W OR /works/OL4077051W OR /works/OL2715009W OR /works/OL2205289W OR /works/OL158953W OR /works/OL4662884W OR /works/OL222799W OR /works/OL5859708W OR /works/OL19659784W OR /works/OL2765935W OR /works/OL15834136W OR /works/OL513969W OR /works/OL98501W OR /works/OL464991W OR /works/OL8193418W OR /works/OL61324W OR /works/OL1870400W OR /works/OL50829W OR /works/OL66531W OR /works/OL5717098W OR /works/OL61921W OR /works/OL5475081W OR /works/OL875437W OR /works/OL6034514W OR /works/OL523452W OR /works/OL7711724W OR /works/OL1854080W OR /works/OL9347808W OR /works/OL2676023W OR /works/OL6218070W OR /works/OL10432709W OR /works/OL804244W OR /works/OL12497W OR /works/OL77792W OR /works/OL2721005W OR /works/OL4661335W OR /works/OL831059W OR /works/OL2731827W OR /works/OL21522W OR /works/OL482313W OR /works/OL97440W OR /works/OL3943151W OR /works/OL3521874W OR /works/OL2715015W OR /works/OL66544W OR /works/OL433123W OR /works/OL2068683W OR /works/OL6322288W OR /works/OL1971683W OR /works/OL1069667W OR /works/OL2438133W OR /works/OL17272376W OR /works/OL16482241W OR /works/OL15860364W OR /works/OL151996W OR /works/OL6740249W OR /works/OL15040422W OR /works/OL16069155W OR /works/OL508163W OR /works/OL3291229W OR /works/OL61003W OR /works/OL98491W OR /works/OL5888555W OR /works/OL5827913W OR /works/OL17933404W OR /works/OL1095427W OR /works/OL54915W OR /works/OL13114894W OR /works/OL24338132W OR /works/OL1872916W OR /works/OL15840480W OR /works/OL184431W OR /works/OL2940316W OR /works/OL2647505W OR /works/OL259028W OR /works/OL14915863W OR /works/OL29462W OR /works/OL1734184W OR /works/OL675449W OR /works/OL18591W OR /works/OL221675W OR /works/OL5704260W OR /works/OL15717066W OR /works/OL3863998W OR /works/OL2619717W OR /works/OL64151W OR /works/OL12826W OR /works/OL547889W OR /works/OL66534W OR /works/OL15952404W OR /works/OL2155632W OR /works/OL69503W OR /works/OL61215W OR /works/OL112890W OR /works/OL66562W OR /works/OL15837476W OR /works/OL15178362W OR /works/OL2046569W OR /works/OL2031517W)'
    },
    6: {
      'title': 'Books for June',
      'url': '/collections/june',
      'query': 'key:(/works/OL4452160W OR /works/OL5804905W OR /works/OL7597278W OR /works/OL706761W OR /works/OL1115461W OR /works/OL3350425W OR /works/OL7717951W OR /works/OL77792W OR /works/OL3374551W OR /works/OL15118371W OR /works/OL13845723W OR /works/OL1474735W OR /works/OL249219W OR /works/OL202359W OR /works/OL61981W OR /works/OL1176834W OR /works/OL2295019W OR /works/OL13727180W OR /works/OL5684730W OR /works/OL195165W OR /works/OL503666W OR /works/OL224894W OR /works/OL16248853W OR /works/OL4056537W OR /works/OL8138326W OR /works/OL8268194W OR /works/OL362706W OR /works/OL3753201W OR /works/OL6560544W OR /works/OL4971793W OR /works/OL10432709W OR /works/OL7729178W OR /works/OL263458W OR /works/OL151997W OR /works/OL2790101W OR /works/OL17094386W OR /works/OL88713W OR /works/OL189097W OR /works/OL1858279W OR /works/OL3399858W OR /works/OL2569571W OR /works/OL8713270W OR /works/OL1430148W OR /works/OL2854958W OR /works/OL1794792W OR /works/OL66562W OR /works/OL8542762W OR /works/OL67326W OR /works/OL2005700W OR /works/OL10395689W OR /works/OL24161W OR /works/OL1793589W OR /works/OL4062432W OR /works/OL8193418W OR /works/OL98501W OR /works/OL258850W OR /works/OL4276206W OR /works/OL362427W OR /works/OL16899384W OR /works/OL81588W OR /works/OL7917989W OR /works/OL3871015W OR /works/OL16134139W OR /works/OL5109271W OR /works/OL258134W OR /works/OL17603105W OR /works/OL20604741W OR /works/OL140125W OR /works/OL20386119W OR /works/OL1337528W OR /works/OL5743157W OR /works/OL1132128W OR /works/OL5704208W OR /works/OL15847281W OR /works/OL1197859W OR /works/OL3168678W OR /works/OL1962457W OR /works/OL1973472W OR /works/OL15717002W OR /works/OL6044682W OR /works/OL167183W OR /works/OL53908W OR /works/OL1119456W OR /works/OL98501W OR /works/OL17602317W OR /works/OL19926001W OR /works/OL8961373W OR /works/OL16151517W OR /works/OL8599103W OR /works/OL4623379W OR /works/OL45793W OR /works/OL245200W OR /works/OL17044272W OR /works/OL1854695W OR /works/OL2196066W OR /works/OL57025W OR /works/OL6815134W OR /works/OL488453W OR /works/OL5850538W)'
    }
  }


def get_homepage():
    try:
        stats = admin.get_stats()
    except Exception:
        logger.error("Error in getting stats", exc_info=True)
        stats = None
    monthly_reads = MONTHLY_READS.get(datetime.datetime.now().month)
    blog_posts = get_blog_feeds()

    # render tempalte should be setting ctx.cssfile
    # but because get_homepage is cached, this doesn't happen
    # during subsequent called
    page = render_template(
        "home/index",
        stats=stats,
        blog_posts=blog_posts,
        monthly_reads=monthly_reads
    )
    # Convert to a dict so it can be cached
    return dict(page)


def get_cached_homepage():
    five_minutes = 5 * dateutil.MINUTE_SECS
    lang = web.ctx.lang
    pd = web.cookies().get('pd', False)
    key = "home.homepage." + lang
    if pd:
        key += '.pd'

    # Because of caching, memcache will call `get_homepage` on another thread! So we
    # need a way to carry some information to that computation on the other thread.
    # We do that by using a python closure. The outer function is executed on the main
    # thread, so all the web.* stuff is correct. The inner function is executed on the
    # other thread, so all the web.* stuff will be dummy.
    def prethread():
        # web.ctx.lang is undefined on the new thread, so need to transfer it over
        lang = web.ctx.lang

        def main():
            # Leaving this in since this is a bit strange, but you can see it clearly
            # in action with this debug line:
            # web.debug(f'XXXXXXXXXXX web.ctx.lang={web.ctx.get("lang")}; {lang=}')
            delegate.fakeload()
            web.ctx.lang = lang
        return main

    return cache.memcache_memoize(
        get_homepage, key, timeout=five_minutes, prethread=prethread())()

class home(delegate.page):
    path = "/"

    def GET(self):
        cached_homepage = get_cached_homepage()
        # when homepage is cached, home/index.html template
        # doesn't run ctx.setdefault to set the cssfile so we must do so here:
        web.template.Template.globals['ctx']['cssfile'] = 'home'
        return web.template.TemplateResult(cached_homepage)

class random_book(delegate.page):
    path = "/random"

    def GET(self):
        olid = lending.get_random_available_ia_edition()
        if olid:
            raise web.seeother('/books/%s' % olid)
        raise web.seeother("/")


def get_ia_carousel_books(query=None, subject=None, work_id=None, sorts=None,
                          _type=None, limit=None):
    if 'env' not in web.ctx:
        delegate.fakeload()

    elif query in CAROUSELS_PRESETS:
        query = CAROUSELS_PRESETS[query]

    limit = limit or lending.DEFAULT_IA_RESULTS
    books = lending.get_available(limit=limit, subject=subject, work_id=work_id,
                                  _type=_type, sorts=sorts, query=query)
    formatted_books = [format_book_data(book) for book in books if book != 'error']
    return formatted_books

def get_featured_subjects():
    # web.ctx must be initialized as it won't be available to the background thread.
    if 'env' not in web.ctx:
        delegate.fakeload()

    FEATURED_SUBJECTS = [
        'art', 'science_fiction', 'fantasy', 'biographies', 'recipes',
        'romance', 'textbooks', 'children', 'history', 'medicine', 'religion',
        'mystery_and_detective_stories', 'plays', 'music', 'science'
    ]
    return dict([(subject_name, subjects.get_subject('/subjects/' + subject_name, sort='edition_count'))
                 for subject_name in FEATURED_SUBJECTS])

@public
def get_cached_featured_subjects():
    return cache.memcache_memoize(
        get_featured_subjects, "home.featured_subjects", timeout=dateutil.HOUR_SECS)()

@public
def generic_carousel(query=None, subject=None, work_id=None, _type=None,
                     sorts=None, limit=None, timeout=None):
    memcache_key = 'home.ia_carousel_books'
    cached_ia_carousel_books = cache.memcache_memoize(
        get_ia_carousel_books, memcache_key, timeout=timeout or cache.DEFAULT_CACHE_LIFETIME)
    books = cached_ia_carousel_books(
        query=query, subject=subject, work_id=work_id, _type=_type,
        sorts=sorts, limit=limit)
    if not books:
        books = cached_ia_carousel_books.update(
            query=query, subject=subject, work_id=work_id, _type=_type,
            sorts=sorts, limit=limit)[0]
    return storify(books) if books else books

@public
def readonline_carousel():
    """Return template code for books pulled from search engine.
       TODO: If problems, use stock list.
    """
    try:
        data = random_ebooks()
        if len(data) > 30:
            data = lending.add_availability(random.sample(data, 30))
            data = [d for d in data if d['availability']['is_readable']]
        return storify(data)

    except Exception:
        logger.error("Failed to compute data for readonline_carousel", exc_info=True)
        return None

def random_ebooks(limit=2000):
    solr = search.get_solr()
    sort = "edition_count desc"
    result = solr.select(
        query='has_fulltext:true -public_scan_b:false',
        rows=limit,
        sort=sort,
        fields=[
            'has_fulltext',
            'key',
            'ia',
            "title",
            "cover_edition_key",
            "author_key", "author_name",
        ])

    return [format_work_data(doc) for doc in result.get('docs', []) if doc.get('ia')]

# cache the results of random_ebooks in memcache for 15 minutes
random_ebooks = cache.memcache_memoize(random_ebooks, "home.random_ebooks", timeout=15*60)

def format_list_editions(key):
    """Formats the editions of a list suitable for display in carousel.
    """
    if 'env' not in web.ctx:
        delegate.fakeload()

    seed_list = web.ctx.site.get(key)
    if not seed_list:
        return []

    editions = {}
    for seed in seed_list.seeds:
        if not isinstance(seed, six.string_types):
            if seed.type.key == "/type/edition":
                editions[seed.key] = seed
            else:
                try:
                    e = pick_best_edition(seed)
                except StopIteration:
                    continue
                editions[e.key] = e
    return [format_book_data(e) for e in editions.values()]

# cache the results of format_list_editions in memcache for 5 minutes
format_list_editions = cache.memcache_memoize(format_list_editions, "home.format_list_editions", timeout=5*60)

def pick_best_edition(work):
    return next((e for e in work.editions if e.ocaid))

def format_work_data(work):
    d = dict(work)

    key = work.get('key', '')
    # New solr stores the key as /works/OLxxxW
    if not key.startswith("/works/"):
        key = "/works/" + key

    d['url'] = key
    d['title'] = work.get('title', '')

    if 'author_key' in work and 'author_name' in work:
        d['authors'] = [{"key": key, "name": name} for key, name in
                        zip(work['author_key'], work['author_name'])]

    if 'cover_edition_key' in work:
        d['cover_url'] = h.get_coverstore_url() + "/b/olid/%s-M.jpg" % work['cover_edition_key']

    d['read_url'] = "//archive.org/stream/" + work['ia'][0]
    return d

def format_book_data(book):
    d = web.storage()
    d.key = book.get('key')
    d.url = book.url()
    d.title = book.title or None
    d.ocaid = book.get("ocaid")
    d.eligibility = book.get("eligibility", {})
    d.availability = book.get('availability', {})

    def get_authors(doc):
        return [web.storage(key=a.key, name=a.name or None) for a in doc.get_authors()]

    work = book.works and book.works[0]
    d.authors = get_authors(work if work else book)
    d.work_key = work.key if work else book.key
    cover = work.get_cover() if work and work.get_cover() else book.get_cover()

    if cover:
        d.cover_url = cover.url("M")
    elif d.ocaid:
        d.cover_url = 'https://archive.org/services/img/%s' % d.ocaid

    if d.ocaid:
        collections = ia.get_metadata(d.ocaid).get('collection', [])

        if 'lendinglibrary' in collections or 'inlibrary' in collections:
            d.borrow_url = book.url("/borrow")
        else:
            d.read_url = book.url("/borrow")
    return d

def setup():
    pass
