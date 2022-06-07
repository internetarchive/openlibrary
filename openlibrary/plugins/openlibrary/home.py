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

from openlibrary.core import admin, cache, ia, lending
from openlibrary.i18n import gettext as _
from openlibrary.utils import dateutil
from openlibrary.plugins.upstream.utils import get_blog_feeds, get_coverstore_public_url
from openlibrary.plugins.worksearch import search, subjects

logger = logging.getLogger("openlibrary.home")

CAROUSELS_PRESETS = {
    'preset:thrillers': '(creator:"Clancy, Tom" OR creator:"King, Stephen" OR creator:"Clive Cussler" OR creator:("Cussler, Clive") OR creator:("Dean Koontz") OR creator:("Koontz, Dean") OR creator:("Higgins, Jack")) AND !publisher:"Pleasantville, N.Y. : Reader\'s Digest Association" AND languageSorter:"English"',
    'preset:comics': '(subject:"comics" OR creator:("Gary Larson") OR creator:("Larson, Gary") OR creator:("Charles M Schulz") OR creator:("Schulz, Charles M") OR creator:("Jim Davis") OR creator:("Davis, Jim") OR creator:("Bill Watterson") OR creator:("Watterson, Bill") OR creator:("Lee, Stan"))',
    'preset:authorsalliance_mitpress': (
        '(openlibrary_subject:(authorsalliance) OR collection:(mitpress) OR '
        'publisher:(MIT Press) OR openlibrary_subject:(mitpress))'
    ),
}


def get_monthly_reads(month):
    """Generates i18n'd monthly carousel for templated/home/index.html

    To be replaced with QueryCarousel macro for cached Lists
    """
    return {
        2: {
            "title": _("Books for February"),
            "url": "/collections/february",
            "query": "key:(%s)"
            % (
                " OR ".join(
                    (
                        "/works/OL18181363W",
                        "/works/OL3481095W",
                        "/works/OL4360244W",
                        "/works/OL20017931W",
                        "/works/OL20615204W",
                        "/works/OL2363176W",
                        "/works/OL17869588W",
                        "/works/OL17784026W",
                        "/works/OL21179764W",
                        "/works/OL8870595W",
                        "/works/OL21054973W",
                        "/works/OL21673730W",
                        "/works/OL20548582W",
                        "/works/OL15279153W",
                        "/works/OL19992836W",
                        "/works/OL15691480W",
                        "/works/OL16305795W",
                        "/works/OL19923407W",
                        "/works/OL16529029W",
                        "/works/OL9242636W",
                        "/works/OL17529769W",
                        "/works/OL3345332W",
                        "/works/OL20013209W",
                        "/works/OL20015483W",
                        "/works/OL19987474W",
                        "/works/OL19992114W",
                        "/works/OL17893900W",
                        "/works/OL18435803W",
                        "/works/OL17314666W",
                        "/works/OL17358927W",
                        "/works/OL15933199W",
                        "/works/OL17858931W",
                        "/works/OL18187603W",
                        "/works/OL16853133W",
                        "/works/OL16894393W",
                        "/works/OL19976062W",
                        "/works/OL20037832W",
                        "/works/OL16885033W",
                        "/works/OL19708155W",
                        "/works/OL17921756W",
                        "/works/OL21037237W",
                        "/works/OL17786027W",
                        "/works/OL17345141W",
                        "/works/OL21294275W",
                        "/works/OL9582417W",
                        "/works/OL9357555W",
                        "/works/OL20907853W",
                        "/works/OL20005568W",
                        "/works/OL3296483W",
                        "/works/OL11983310W",
                        "/works/OL7159886W",
                        "/works/OL1662667W",
                        "/works/OL19990553W",
                        "/works/OL15285884W",
                        "/works/OL6888879W",
                        "/works/OL17900435W",
                        "/works/OL5706069W",
                        "/works/OL2977589W",
                        "/works/OL1593701W",
                        "/works/OL16451688W",
                        "/works/OL16910779W",
                        "/works/OL18215336W",
                        "/works/OL17371695W",
                        "/works/OL3521634W",
                        "/works/OL17355199W",
                        "/works/OL5739152W",
                        "/works/OL20016962W",
                        "/works/OL3191599W",
                        "/works/OL20896695W",
                        "/works/OL19752490W",
                        "/works/OL18335154W",
                        "/works/OL4582875W",
                        "/works/OL16515210W",
                        "/works/OL16868407W",
                        "/works/OL3459949W",
                        "/works/OL16025481W",
                        "/works/OL1928280W",
                        "/works/OL6208302W",
                        "/works/OL17566265W",
                        "/works/OL20652811W",
                        "/works/OL22059158W",
                        "/works/OL4370955W",
                        "/works/OL19998526W",
                        "/works/OL6218060W",
                        "/works/OL16813953W",
                        "/works/OL21179974W",
                        "/works/OL7213898W",
                        "/works/OL17872185W",
                        "/works/OL17340085W",
                        "/works/OL21584979W",
                        "/works/OL21078916W",
                        "/works/OL158519W",
                        "/works/OL4114499W",
                        "/works/OL19638041W",
                        "/works/OL16844793W",
                        "/works/OL20940485W",
                        "/works/OL17392121W",
                        "/works/OL20030448W",
                        "/works/OL15920474W",
                        "/works/OL20544657W",
                    )
                )
            ),
        },
        3: {
            "title": _("Books for March"),
            "url": "/collections/march",
            "query": "key:(%s)"
            % (
                " OR ".join(
                    (
                        "/works/OL5184754W",
                        "/works/OL133486W",
                        "/works/OL1112900W",
                        "/works/OL15302479W",
                        "/works/OL5353481W",
                        "/works/OL1684657W",
                        "/works/OL16612125W",
                        "/works/OL2987652W",
                        "/works/OL15243975W",
                        "/works/OL5827897W",
                        "/works/OL237034W",
                        "/works/OL20916117W",
                        "/works/OL1881592W",
                        "/works/OL16561534W",
                        "/works/OL17893247W",
                        "/works/OL7000994W",
                        "/works/OL16247899W",
                        "/works/OL19163127W",
                        "/works/OL1146619W",
                        "/works/OL2231866W",
                        "/works/OL1853601W",
                        "/works/OL1794792W",
                        "/works/OL2750502W",
                        "/works/OL1825970W",
                        "/works/OL17991110W",
                        "/works/OL34442W",
                        "/works/OL20886755W",
                        "/works/OL1880057W",
                        "/works/OL9221039W",
                        "/works/OL4782577W",
                        "/works/OL15230140W",
                        "/works/OL7899614W",
                        "/works/OL508764W",
                        "/works/OL18165887W",
                        "/works/OL17538396W",
                        "/works/OL53994W",
                        "/works/OL11817902W",
                        "/works/OL5118902W",
                        "/works/OL68789W",
                        "/works/OL8874375W",
                        "/works/OL158240W",
                        "/works/OL3474021W",
                        "/works/OL3352379W",
                        "/works/OL1826369W",
                        "/works/OL106972W",
                        "/works/OL20623337W",
                        "/works/OL2624393W",
                        "/works/OL47755W",
                        "/works/OL514392W",
                        "/works/OL18820761W",
                        "/works/OL85496W",
                        "/works/OL21625058W",
                        "/works/OL1833297W",
                        "/works/OL15162472W",
                        "/works/OL16289374W",
                        "/works/OL15100036W",
                        "/works/OL17311133W",
                        "/works/OL1826373W",
                        "/works/OL3255337W",
                        "/works/OL7113090W",
                        "/works/OL5408044W",
                        "/works/OL4702292W",
                        "/works/OL8269570W",
                        "/works/OL2626142W",
                        "/works/OL9399062W",
                        "/works/OL6670269W",
                        "/works/OL890505W",
                        "/works/OL523724W",
                        "/works/OL6218068W",
                        "/works/OL1469543W",
                        "/works/OL1001250W",
                        "/works/OL20004703W",
                        "/works/OL679942W",
                        "/works/OL2044569W",
                        "/works/OL15980420W",
                        "/works/OL20016033W",
                        "/works/OL565273W",
                        "/works/OL20019003W",
                        "/works/OL18820945W",
                        "/works/OL3945614W",
                        "/works/OL64468W",
                        "/works/OL5754207W",
                        "/works/OL6218046W",
                        "/works/OL18183638W",
                        "/works/OL21182317W",
                        "/works/OL169921W",
                        "/works/OL6384123W",
                        "/works/OL1870681W",
                        "/works/OL16245602W",
                        "/works/OL17676089W",
                        "/works/OL20848500W",
                        "/works/OL4304829W",
                        "/works/OL17873811W",
                        "/works/OL4968024W",
                        "/works/OL20001088W",
                        "/works/OL3142310W",
                        "/works/OL142101W",
                        "/works/OL19396225W",
                        "/works/OL1230977W",
                        "/works/OL17332299W",
                    )
                )
            ),
        },
        4: {
            "title": _("Books for April"),
            "url": "/collections/april",
            "query": "key:(%s)"
            % (
                " OR ".join(
                    (
                        "/works/OL6934547W",
                        "/works/OL2000340W",
                        "/works/OL2746188W",
                        "/works/OL2921990W",
                        "/works/OL11476041W",
                        "/works/OL8676892W",
                        "/works/OL1895089W",
                        "/works/OL8463108W",
                        "/works/OL1916767W",
                        "/works/OL17328163W",
                        "/works/OL34364W",
                        "/works/OL2384851W",
                        "/works/OL79422W",
                        "/works/OL142101W",
                        "/works/OL5719058W",
                        "/works/OL548264W",
                        "/works/OL15120217W",
                        "/works/OL14952471W",
                        "/works/OL15188310W",
                        "/works/OL1855830W",
                        "/works/OL3147556W",
                        "/works/OL5843701W",
                        "/works/OL20479918W",
                        "/works/OL17864309W",
                        "/works/OL5857644W",
                        "/works/OL18174472W",
                        "/works/OL13750798W",
                        "/works/OL14869488W",
                        "/works/OL15844569W",
                        "/works/OL510286W",
                        "/works/OL2650512W",
                        "/works/OL83989W",
                        "/works/OL1914072W",
                        "/works/OL5097914W",
                        "/works/OL1927820W",
                        "/works/OL112630W",
                        "/works/OL6218052W",
                        "/works/OL12992964W",
                        "/works/OL8460319W",
                        "/works/OL308951W",
                        "/works/OL14909580W",
                        "/works/OL17077479W",
                        "/works/OL4445284W",
                        "/works/OL17437756W",
                        "/works/OL8193508W",
                        "/works/OL5590179W",
                        "/works/OL166683W",
                        "/works/OL83989W",
                        "/works/OL45869W",
                        "/works/OL3840897W",
                        "/works/OL15289753W",
                        "/works/OL22056274W",
                        "/works/OL2279297W",
                        "/works/OL71856W",
                        "/works/OL45790W",
                        "/works/OL6704886W",
                        "/works/OL9770557W",
                        "/works/OL524611W",
                        "/works/OL45709W",
                        "/works/OL66562W",
                        "/works/OL8455191W",
                        "/works/OL15065463W",
                        "/works/OL1173603W",
                        "/works/OL15692492W",
                        "/works/OL25860W",
                        "/works/OL53908W",
                        "/works/OL2342157W",
                        "/works/OL17324165W",
                        "/works/OL261405W",
                        "/works/OL17324092W",
                        "/works/OL263663W",
                        "/works/OL2695471W",
                        "/works/OL587092W",
                        "/works/OL2695710W",
                        "/works/OL20892865W",
                        "/works/OL15392519W",
                        "/works/OL138536W",
                        "/works/OL88641W",
                        "/works/OL151924W",
                        "/works/OL15021422W",
                        "/works/OL9355810W",
                        "/works/OL5097109W",
                        "/works/OL3368666W",
                        "/works/OL50625W",
                        "/works/OL8076534W",
                        "/works/OL17059208W",
                        "/works/OL3974810W",
                        "/works/OL1910135W",
                        "/works/OL201059W",
                        "/works/OL100672W",
                        "/works/OL17900251W",
                        "/works/OL54031W",
                        "/works/OL76590W",
                        "/works/OL17063120W",
                        "/works/OL3288436W",
                        "/works/OL997592W",
                        "/works/OL19360441W",
                        "/works/OL17857052W",
                        "/works/OL1993508W",
                        "/works/OL17872769W",
                    )
                )
            ),
        },
        5: {
            "title": _("Books for May"),
            "url": "/collections/may",
            "query": "key:(%s)"
            % (
                " OR ".join(
                    (
                        "/works/OL450777W",
                        "/works/OL362289W",
                        "/works/OL4077051W",
                        "/works/OL2715009W",
                        "/works/OL2205289W",
                        "/works/OL158953W",
                        "/works/OL4662884W",
                        "/works/OL222799W",
                        "/works/OL5859708W",
                        "/works/OL19659784W",
                        "/works/OL2765935W",
                        "/works/OL15834136W",
                        "/works/OL513969W",
                        "/works/OL98501W",
                        "/works/OL464991W",
                        "/works/OL8193418W",
                        "/works/OL61324W",
                        "/works/OL1870400W",
                        "/works/OL50829W",
                        "/works/OL66531W",
                        "/works/OL5717098W",
                        "/works/OL61921W",
                        "/works/OL5475081W",
                        "/works/OL875437W",
                        "/works/OL6034514W",
                        "/works/OL523452W",
                        "/works/OL7711724W",
                        "/works/OL1854080W",
                        "/works/OL9347808W",
                        "/works/OL2676023W",
                        "/works/OL6218070W",
                        "/works/OL10432709W",
                        "/works/OL804244W",
                        "/works/OL12497W",
                        "/works/OL77792W",
                        "/works/OL2721005W",
                        "/works/OL4661335W",
                        "/works/OL831059W",
                        "/works/OL2731827W",
                        "/works/OL21522W",
                        "/works/OL482313W",
                        "/works/OL97440W",
                        "/works/OL3943151W",
                        "/works/OL3521874W",
                        "/works/OL2715015W",
                        "/works/OL66544W",
                        "/works/OL433123W",
                        "/works/OL2068683W",
                        "/works/OL6322288W",
                        "/works/OL1971683W",
                        "/works/OL1069667W",
                        "/works/OL2438133W",
                        "/works/OL17272376W",
                        "/works/OL16482241W",
                        "/works/OL15860364W",
                        "/works/OL151996W",
                        "/works/OL6740249W",
                        "/works/OL15040422W",
                        "/works/OL16069155W",
                        "/works/OL508163W",
                        "/works/OL3291229W",
                        "/works/OL61003W",
                        "/works/OL98491W",
                        "/works/OL5888555W",
                        "/works/OL5827913W",
                        "/works/OL17933404W",
                        "/works/OL1095427W",
                        "/works/OL54915W",
                        "/works/OL13114894W",
                        "/works/OL24338132W",
                        "/works/OL1872916W",
                        "/works/OL15840480W",
                        "/works/OL184431W",
                        "/works/OL2940316W",
                        "/works/OL2647505W",
                        "/works/OL259028W",
                        "/works/OL14915863W",
                        "/works/OL29462W",
                        "/works/OL1734184W",
                        "/works/OL675449W",
                        "/works/OL18591W",
                        "/works/OL221675W",
                        "/works/OL5704260W",
                        "/works/OL15717066W",
                        "/works/OL3863998W",
                        "/works/OL2619717W",
                        "/works/OL64151W",
                        "/works/OL12826W",
                        "/works/OL547889W",
                        "/works/OL66534W",
                        "/works/OL15952404W",
                        "/works/OL2155632W",
                        "/works/OL69503W",
                        "/works/OL61215W",
                        "/works/OL112890W",
                        "/works/OL66562W",
                        "/works/OL15837476W",
                        "/works/OL15178362W",
                        "/works/OL2046569W",
                        "/works/OL2031517W",
                    )
                )
            ),
        },
        6: {
            "title": _("Books for June"),
            "url": "/collections/june",
            "query": "key:(%s)"
            % (
                " OR ".join(
                    (
                        "/works/OL4452160W",
                        "/works/OL5804905W",
                        "/works/OL7597278W",
                        "/works/OL706761W",
                        "/works/OL1115461W",
                        "/works/OL3350425W",
                        "/works/OL7717951W",
                        "/works/OL77792W",
                        "/works/OL3374551W",
                        "/works/OL15118371W",
                        "/works/OL13845723W",
                        "/works/OL1474735W",
                        "/works/OL249219W",
                        "/works/OL202359W",
                        "/works/OL61981W",
                        "/works/OL1176834W",
                        "/works/OL2295019W",
                        "/works/OL13727180W",
                        "/works/OL5684730W",
                        "/works/OL195165W",
                        "/works/OL503666W",
                        "/works/OL224894W",
                        "/works/OL16248853W",
                        "/works/OL4056537W",
                        "/works/OL8138326W",
                        "/works/OL8268194W",
                        "/works/OL362706W",
                        "/works/OL3753201W",
                        "/works/OL6560544W",
                        "/works/OL4971793W",
                        "/works/OL10432709W",
                        "/works/OL7729178W",
                        "/works/OL263458W",
                        "/works/OL151997W",
                        "/works/OL2790101W",
                        "/works/OL17094386W",
                        "/works/OL88713W",
                        "/works/OL189097W",
                        "/works/OL1858279W",
                        "/works/OL3399858W",
                        "/works/OL2569571W",
                        "/works/OL8713270W",
                        "/works/OL1430148W",
                        "/works/OL2854958W",
                        "/works/OL1794792W",
                        "/works/OL66562W",
                        "/works/OL8542762W",
                        "/works/OL67326W",
                        "/works/OL2005700W",
                        "/works/OL10395689W",
                        "/works/OL24161W",
                        "/works/OL1793589W",
                        "/works/OL4062432W",
                        "/works/OL8193418W",
                        "/works/OL98501W",
                        "/works/OL258850W",
                        "/works/OL4276206W",
                        "/works/OL362427W",
                        "/works/OL16899384W",
                        "/works/OL81588W",
                        "/works/OL7917989W",
                        "/works/OL3871015W",
                        "/works/OL16134139W",
                        "/works/OL5109271W",
                        "/works/OL258134W",
                        "/works/OL17603105W",
                        "/works/OL20604741W",
                        "/works/OL140125W",
                        "/works/OL20386119W",
                        "/works/OL1337528W",
                        "/works/OL5743157W",
                        "/works/OL1132128W",
                        "/works/OL5704208W",
                        "/works/OL15847281W",
                        "/works/OL1197859W",
                        "/works/OL3168678W",
                        "/works/OL1962457W",
                        "/works/OL1973472W",
                        "/works/OL15717002W",
                        "/works/OL6044682W",
                        "/works/OL167183W",
                        "/works/OL53908W",
                        "/works/OL1119456W",
                        "/works/OL98501W",
                        "/works/OL17602317W",
                        "/works/OL19926001W",
                        "/works/OL8961373W",
                        "/works/OL16151517W",
                        "/works/OL8599103W",
                        "/works/OL4623379W",
                        "/works/OL45793W",
                        "/works/OL245200W",
                        "/works/OL17044272W",
                        "/works/OL1854695W",
                        "/works/OL2196066W",
                        "/works/OL57025W",
                        "/works/OL6815134W",
                        "/works/OL488453W",
                        "/works/OL5850538W",
                    )
                )
            ),
        },
    }.get(month)


def get_homepage():
    try:
        stats = admin.get_stats()
    except Exception:
        logger.error("Error in getting stats", exc_info=True)
        stats = None
    monthly_reads = get_monthly_reads(datetime.datetime.now().month)
    blog_posts = get_blog_feeds()

    # render template should be setting ctx.cssfile
    # but because get_homepage is cached, this doesn't happen
    # during subsequent called
    page = render_template(
        "home/index", stats=stats, blog_posts=blog_posts, monthly_reads=monthly_reads
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

    return cache.memcache_memoize(
        get_homepage, key, timeout=five_minutes, prethread=caching_prethread()
    )()


# Because of caching, memcache will call `get_homepage` on another thread! So we
# need a way to carry some information to that computation on the other thread.
# We do that by using a python closure. The outer function is executed on the main
# thread, so all the web.* stuff is correct. The inner function is executed on the
# other thread, so all the web.* stuff will be dummy.
def caching_prethread():
    # web.ctx.lang is undefined on the new thread, so need to transfer it over
    lang = web.ctx.lang

    def main():
        # Leaving this in since this is a bit strange, but you can see it clearly
        # in action with this debug line:
        # web.debug(f'XXXXXXXXXXX web.ctx.lang={web.ctx.get("lang")}; {lang=}')
        delegate.fakeload()
        web.ctx.lang = lang

    return main


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


def get_ia_carousel_books(
    query=None, subject=None, work_id=None, sorts=None, _type=None, limit=None
):
    if 'env' not in web.ctx:
        delegate.fakeload()

    elif query in CAROUSELS_PRESETS:
        query = CAROUSELS_PRESETS[query]

    limit = limit or lending.DEFAULT_IA_RESULTS
    books = lending.get_available(
        limit=limit,
        subject=subject,
        work_id=work_id,
        _type=_type,
        sorts=sorts,
        query=query,
    )
    formatted_books = [format_book_data(book) for book in books if book != 'error']
    return formatted_books


def get_featured_subjects():
    # web.ctx must be initialized as it won't be available to the background thread.
    if 'env' not in web.ctx:
        delegate.fakeload()

    FEATURED_SUBJECTS = [
        {'key': '/subjects/art', 'presentable_name': _('Art')},
        {'key': '/subjects/science_fiction', 'presentable_name': _('Science Fiction')},
        {'key': '/subjects/fantasy', 'presentable_name': _('Fantasy')},
        {'key': '/subjects/biographies', 'presentable_name': _('Biographies')},
        {'key': '/subjects/recipes', 'presentable_name': _('Recipes')},
        {'key': '/subjects/romance', 'presentable_name': _('Romance')},
        {'key': '/subjects/textbooks', 'presentable_name': _('Textbooks')},
        {'key': '/subjects/children', 'presentable_name': _('Children')},
        {'key': '/subjects/history', 'presentable_name': _('History')},
        {'key': '/subjects/medicine', 'presentable_name': _('Medicine')},
        {'key': '/subjects/religion', 'presentable_name': _('Religion')},
        {
            'key': '/subjects/mystery_and_detective_stories',
            'presentable_name': _('Mystery and Detective Stories'),
        },
        {'key': '/subjects/plays', 'presentable_name': _('Plays')},
        {'key': '/subjects/music', 'presentable_name': _('Music')},
        {'key': '/subjects/science', 'presentable_name': _('Science')},
    ]
    return [
        {**subject, **(subjects.get_subject(subject['key'], limit=0) or {})}
        for subject in FEATURED_SUBJECTS
    ]


@public
def get_cached_featured_subjects():
    return cache.memcache_memoize(
        get_featured_subjects,
        f"home.featured_subjects.{web.ctx.lang}",
        timeout=dateutil.HOUR_SECS,
        prethread=caching_prethread(),
    )()


@public
def generic_carousel(
    query=None,
    subject=None,
    work_id=None,
    _type=None,
    sorts=None,
    limit=None,
    timeout=None,
):
    memcache_key = 'home.ia_carousel_books'
    cached_ia_carousel_books = cache.memcache_memoize(
        get_ia_carousel_books,
        memcache_key,
        timeout=timeout or cache.DEFAULT_CACHE_LIFETIME,
    )
    books = cached_ia_carousel_books(
        query=query,
        subject=subject,
        work_id=work_id,
        _type=_type,
        sorts=sorts,
        limit=limit,
    )
    if not books:
        books = cached_ia_carousel_books.update(
            query=query,
            subject=subject,
            work_id=work_id,
            _type=_type,
            sorts=sorts,
            limit=limit,
        )[0]
    return storify(books) if books else books


def format_list_editions(key):
    """Formats the editions of a list suitable for display in carousel."""
    if 'env' not in web.ctx:
        delegate.fakeload()

    seed_list = web.ctx.site.get(key)
    if not seed_list:
        return []

    editions = {}
    for seed in seed_list.seeds:
        if not isinstance(seed, str):
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
format_list_editions = cache.memcache_memoize(
    format_list_editions, "home.format_list_editions", timeout=5 * 60
)


def pick_best_edition(work):
    return next(e for e in work.editions if e.ocaid)


def format_work_data(work):
    d = dict(work)

    key = work.get('key', '')
    # New solr stores the key as /works/OLxxxW
    if not key.startswith("/works/"):
        key = "/works/" + key

    d['url'] = key
    d['title'] = work.get('title', '')

    if 'author_key' in work and 'author_name' in work:
        d['authors'] = [
            {"key": key, "name": name}
            for key, name in zip(work['author_key'], work['author_name'])
        ]

    if 'cover_edition_key' in work:
        coverstore_url = get_coverstore_public_url()
        d['cover_url'] = f"{coverstore_url}/b/olid/{work['cover_edition_key']}-M.jpg"

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
