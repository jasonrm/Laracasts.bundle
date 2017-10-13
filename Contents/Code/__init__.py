import re
import urllib, urllib2
import cookielib
import os
import ssl
import time

NAME = 'Laracasts'
BASE = 'https://laracasts.com'
SERIES = '%s/series/%%s' % BASE
ICONS = {
    'series': R('icon-series.png')
}
NAME = 'Laracasts'
PREFIX = '/video/laracasts'
ICON = 'icon-default.png'
ART = 'art-default.png'

class NoRedirection(urllib2.HTTPErrorProcessor):

    def http_response(self, request, response):
        return response

    https_response = http_response

cj = cookielib.CookieJar()
cacerts = Core.storage.join_path(Core.app_support_path, Core.config.bundles_dir_name, 'Laracasts.bundle', "Contents", "Resources", "cacert.pem")
Log.Info(cacerts);
cxt = ssl.create_default_context(cafile=cacerts)
opener = urllib2.build_opener(urllib2.HTTPCookieProcessor(cj), urllib2.HTTPSHandler(context=cxt))
no_redirect_opener = urllib2.build_opener(NoRedirection, urllib2.HTTPCookieProcessor(cj), urllib2.HTTPSHandler(context=cxt))
common_headers = [
    ('User-agent', 'Laracasts Plex Plugin/1.0 (+https://github.com/jasonrm/Laracasts.bundle)')
]
opener.addheaders = common_headers
no_redirect_opener.addheaders = common_headers

# Source: http://jonebird.com/2012/02/07/python-memoize-decorator-with-ttl-argument/
class memoized_ttl(object):
    """Decorator that caches a function's return value each time it is called within a TTL
    If called within the TTL and the same arguments, the cached value is returned,
    If called outside the TTL or a different value, a fresh value is returned.
    """
    def __init__(self, ttl):
        self.cache = {}
        self.ttl = ttl
    def __call__(self, f):
        def wrapped_f(*args):
            now = time.time()
            try:
                value, last_update = self.cache[args]
                if self.ttl > 0 and now - last_update > self.ttl:
                    raise AttributeError
                #print 'DEBUG: cached value'
                return value
            except (KeyError, AttributeError):
                value = f(*args)
                self.cache[args] = (value, now)
                #print 'DEBUG: fresh value'
                return value
            except TypeError:
                # uncachable -- for instance, passing a list as an argument.
                # Better to not cache than to blow up entirely.
                return f(*args)
        return wrapped_f

####################################################################################################
def Start():
    ObjectContainer.title1 = NAME
    ObjectContainer.art = R(ART)

####################################################################################################
@handler(PREFIX, NAME, ICON, ART)
def MainMenu():

    oc = ObjectContainer()

    oc.add(DirectoryObject(key = Callback(BySeries), title='Browse By Series', thumb=ICONS['series']))
    # oc.add(DirectoryObject(key = Callback(AllCategories), title = 'All Categories'))
    oc.add(PrefsObject(title = L('Preferences...')))

    try:
        Login()
    except Ex.MediaNotAuthorized:
        return MessageContainer(header=unicode('Auth Error'), message=unicode("Invalid username and/or password."))

    return oc

####################################################################################################
@route('/video/laracasts/series')
def BySeries():
    oc = ObjectContainer(title2="Browse By Series")
    html = cacheable_open(SERIES % "")
    page = HTML.ElementFromString(html)
    series_elements = page.xpath('//div[contains(concat(" ", normalize-space(@class), " "), " series-card ")]')

    for series_element in series_elements:
        series_title = series_element.xpath('.//*[contains(@class, "series-card-title")]/text()')[0].strip()
        series_title = re.sub( '\s+', ' ', series_title ).strip()
        Log.Info('series_title: %s' % series_title)

        series_slug = series_element.xpath('.//a/@href')[0].replace('/series/', '')
        Log.Info('series_slug: %s' % series_slug)

        series_thumb = series_element.xpath('.//*[contains(@class, "series-card-thumbnail")]/img/@src')[0]
        series_thumb = BASE + series_thumb
        Log.Info('series_thumb: %s' % series_thumb)

        series_key = Callback(Series, series_slug=series_slug, series_title=series_title, series_thumb=series_thumb)
        series_object = DirectoryObject(key=series_key, title=series_title, thumb=Resource.ContentsOfURLWithFallback(series_thumb))
        oc.add(series_object)

    return oc

####################################################################################################
@route('/video/laracasts/series/{series_slug}')
def Series(series_slug, series_title, series_thumb):
    oc = ObjectContainer(title2=series_title)

    html = cacheable_open(SERIES % series_slug)
    series_page = HTML.ElementFromString(html)

    results = {}

    @parallelize
    def GetAllVideos():
        videos = series_page.xpath('//*[contains(concat(" ", normalize-space(@class), " "), " episode-list-item ")]')

        for num in range(len(videos)):
            video = videos[num]

            @task
            def GetVideo(num=num, video=video, results=results):
                url = BASE + video.xpath('.//a/@href')[0]
                Log.Info('video url: %s', url)

                try:
                    html = cacheable_open(url)
                    video_page = HTML.ElementFromString(html)

                    video_url = video_page.xpath('//source[@data-quality="HD"]/@src')[0].strip()
                    if video_url[0:2] == '//':
                        video_url = 'https:' + video_url
                    Log.Info('video_url: %s' % video_url)

                    video_title = video_page.xpath('//li[contains(concat(" ", normalize-space(@class), " "), " is-active ")]/*[contains(concat(" ", normalize-space(@class), " "), " episode-title ")]/text()')[0].strip()
                    video_title = re.sub( '\s+', ' ', video_title ).strip()
                    video_title = "%d: %s" % (num + 1, video_title)
                    Log.Info('video_title: %s' % video_title)

                    video_summary = "\n".join(video_page.xpath('//*[contains(concat(" ", normalize-space(@class), " "), " video-description ")]//text()')).strip()
                    video_summary = re.sub( '\s+', ' ', video_summary ).strip()
                    Log.Info('video_summary: %s' % video_summary)

                    video_duration = Datetime.MillisecondsFromString(video_page.xpath('//li[contains(concat(" ", normalize-space(@class), " "), " is-active ")]/*[contains(concat(" ", normalize-space(@class), " "), " length ")]/text()')[0])

                    results[num] = CreateVideoClipObject(
                        title = video_title,
                        summary = video_summary,
                        duration = video_duration,
                        temp_url = video_url,
                        thumb = series_thumb
                    )
                except (IndexError):
                    return

    keys = results.keys()
    keys.sort()

    for key in keys:
        oc.add(results[key])

    return oc

@route('/video/laracasts/play')
def CreateVideoClipObject(title, summary, duration, temp_url, thumb=None, include_container=False):
    items = []

    items.append(
        MediaObject(
            parts = [PartObject(key=temp_url)],
            container = Container.MP4,
            audio_codec = AudioCodec.AAC,
            video_codec = VideoCodec.H264,
            audio_channels = 2,
            optimized_for_streaming = True
        )
    )
    items.reverse()

    videoclip_obj = VideoClipObject(
        key = Callback(CreateVideoClipObject, title=title, summary=summary, duration=duration, thumb=thumb, temp_url=temp_url, include_container=True),
        rating_key = temp_url,
        title = title,
        summary = summary,
        duration = int(duration),
        thumb = thumb,
        items = items
    )

    if include_container:
        return ObjectContainer(objects=[videoclip_obj])
    else:
        return videoclip_obj

@memoized_ttl(900)
def cacheable_open(url):
    html = opener.open(url).read()
    return html

####################################################################################################
def Login():
    if not Prefs['email'] or not Prefs['password']:
        return

    try:
        response = no_redirect_opener.open(BASE + '/login')
        if response.code == 302:
            Log.Info("Already Authenticated")
            return
        Log.Info("Authentication required")
    except urllib2.HTTPError, e:
        if e.code == 401 or e.code == 403:
            raise Ex.MediaNotAuthorized
        return
    except:
        return

    html = response.read()
    page = HTML.ElementFromString(html)
    token = page.xpath('//input[@name="_token"]/@value')[0]
    if not token:
        raise Ex.MediaNotAuthorized

    try:
        post = {
            'email': Prefs['email'],
            'password': Prefs['password'],
            '_token': token
        }
        response = no_redirect_opener.open(BASE + '/sessions', data=urllib.urlencode(post))

        if response.info()['Location'] == BASE + '/dashboard':
            Log.Info("Authentication Success")
            return
        raise Ex.MediaNotAuthorized
        Log.Info("Authentication Failure")
    except urllib2.HTTPError, e:
        if e.code == 401 or e.code == 403:
            raise Ex.MediaNotAuthorized
        return
