import re
import urllib, urllib2
import cookielib

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
opener = urllib2.build_opener(urllib2.HTTPCookieProcessor(cj))
no_redirect_opener = urllib2.build_opener(NoRedirection, urllib2.HTTPCookieProcessor(cj))

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

    Login()

    return oc

####################################################################################################
@route('/video/laracasts/series')
def BySeries():
    oc = ObjectContainer(title2="Browse By Series")

    response = opener.open(SERIES % "")
    page = HTML.ElementFromString(response.read())
    series_elements = page.xpath('//div[@class="Card"]')

    for series_element in series_elements:
        series_title = series_element.xpath('.//*[contains(@class, "Card__title")]/*/text()')[0].strip()
        series_slug = series_element.xpath('.//a/@href')[0].replace('/series/', '')
        series_thumb = series_element.xpath('.//img[contains(@class, "Card__image")]/@src')[0]

        series_title = re.sub( '\s+', ' ', series_title ).strip()

        if series_thumb[0:2] == '//':
            series_thumb = 'https:' + series_thumb

        series_key = Callback(Series, series_slug=series_slug, series_title=series_title, series_thumb=series_thumb)
        series_object = DirectoryObject(key=series_key, title=series_title, thumb=Resource.ContentsOfURLWithFallback(series_thumb))
        oc.add(series_object)

    return oc

####################################################################################################
@route('/video/laracasts/series/{series_slug}')
def Series(series_slug, series_title, series_thumb):
    oc = ObjectContainer(title2=series_title)

    response = opener.open(SERIES % series_slug)
    series_page = HTML.ElementFromString(response.read())

    results = {}

    @parallelize
    def GetAllVideos():
        videos = series_page.xpath('//span[@class="Lesson-List__title"]/a')

        for num in range(len(videos)):
            video = videos[num]

            @task
            def GetVideo(num=num, video=video, results=results):
                url = video.xpath('@href')[0]
                Log.Info(url)

                try:
                    response = opener.open(BASE + url)
                    video_page = HTML.ElementFromString(response.read())

                    video_url = video_page.xpath('//source[@data-quality="HD"]/@src')[0].strip()
                    video_title = video_page.xpath('//h1[@class="Video__title"]/text()')[0]
                    video_summary = "\n".join(video_page.xpath('//div[@class="Video__body"]/text()|//div[@class="Video__body"]/p/text()'))
                    video_duration = Datetime.MillisecondsFromString(video_page.xpath('//li[contains(@class, "Lesson-List__item--is-current")]/span[contains(@class, "Lesson-List__length")]/text()')[0])
                    video_thumb = video_page.xpath('//div[contains(@class, "series-outline")]/*/img/@src')[0]

                    video_title = re.sub( '\s+', ' ', video_title ).strip()
                    video_summary = re.sub( '\s+', ' ', video_summary ).strip()

                    if video_url[0:2] == '//':
                        video_url = 'https:' + video_url

                    if video_thumb[0:2] == '//':
                        video_thumb = 'https:' + video_thumb

                    results[num] = CreateVideoClipObject(
                        title = video_title,
                        summary = video_summary,
                        duration = video_duration,
                        thumb = Resource.ContentsOfURLWithFallback(video_thumb),
                        temp_url = video_url
                    )
                except (IndexError):
                    return

    keys = results.keys()
    keys.sort()

    for key in keys:
        oc.add(results[key])

    return oc

@route('/video/laracasts/play')
def CreateVideoClipObject(title, summary, duration, thumb, temp_url, include_container=False):
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

####################################################################################################
def Login():
    if not Prefs['email'] or not Prefs['password']:
        return

    try:
        response = no_redirect_opener.open(BASE + '/login')
        if response.code == 302:
            Log.Info("Already Authenticated")
            return
        Log.Info("Auth required")
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

        if 'Set-Cookie' in response.info():
            Log.Info("Auth Success")
            return
        Log.Info("Auth Failure")
    except urllib2.HTTPError, e:
        if e.code == 401 or e.code == 403:
            raise Ex.MediaNotAuthorized
        return
    except:
        return
