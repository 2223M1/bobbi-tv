# -*- coding: utf-8 -*-
"""
Juku Built-in Movie Scraper (TMDB Direct Acceleration)
巨库内置电影刮削器（基于 Go 守护进程 DoH 直连加速）
"""

import sys
import re
import json
import urllib.parse
import urllib.request
import xbmc
import xbmcgui
import xbmcplugin
import xbmcaddon

DAEMON_BASE_URL = "http://127.0.0.1:17654"

def proxied_image_url(raw_url):
    if not raw_url:
        return ""
    if "image.tmdb.org" in raw_url and "127.0.0.1:17654/api/image/proxy" not in raw_url:
        return f"{DAEMON_BASE_URL}/api/image/proxy?url={urllib.parse.quote(raw_url, safe='')}"
    return raw_url

def parse_movie_identifiers(text):
    """
    从标题或文件名中提取 tmdb_id、年份和纯净片名
    例如：
      "火遮眼 (2025) {tmdbid-1280738}" -> title="火遮眼", year=2025, tmdb_id=1280738
      "奥本海默.Oppenheimer.2023" -> title="奥本海默", year=2023, tmdb_id=None
    """
    if not text:
        return "", None, None

    tmdb_id = None
    year = None

    # 1. 提取 {tmdbid=12345} 或 {tmdbid-12345}
    tmdb_match = re.search(r'\{tmdbid[-=:](\d+)\}', text, re.IGNORECASE)
    if tmdb_match:
        try:
            tmdb_id = int(tmdb_match.group(1))
        except ValueError:
            pass
        text = re.sub(r'\{tmdbid[-=:]\d+\}', '', text, flags=re.IGNORECASE)

    # 2. 提取 (2025) 或 .2025.
    year_match = re.search(r'[\(\[\.\s](\d{4})[\)\]\.\s]?', text)
    if year_match:
        y = int(year_match.group(1))
        if 1900 <= y <= 2100:
            year = y
            text = text[:year_match.start()] + text[year_match.end():]

    # 3. 清理残留的多余括号、版本标签与符号
    clean_title = re.sub(r'[\[\(].*?[\]\)]', '', text)
    clean_title = clean_title.replace('.', ' ').replace('_', ' ').replace('-', ' ')
    clean_title = re.sub(r'\s+', ' ', clean_title).strip()

    return clean_title, year, tmdb_id

class TMDBMovieScraper:
    def __init__(self, base_url=DAEMON_BASE_URL):
        self.base_url = base_url

    def find_movie(self, title, year=None):
        """
        在 TMDB 中搜索电影
        """
        clean_title, parsed_year, tmdb_id = parse_movie_identifiers(title)
        if parsed_year and not year:
            year = parsed_year

        # 如果已经直接提取出 tmdb_id，直接获取详情
        if tmdb_id:
            detail = self.get_movie_detail(tmdb_id)
            if detail:
                return [{
                    'id': tmdb_id,
                    'title': detail.get('title', clean_title),
                    'year': detail.get('release_date', '')[:4] if detail.get('release_date') else str(year or ''),
                    'url': f"{self.base_url}/api/tmdb/movie/{tmdb_id}"
                }]

        # 调用 Go 守护进程 TMDB 搜索接口
        q = urllib.parse.urlencode({
            'query': clean_title,
            'year': str(year or '')
        })
        req_url = f"{self.base_url}/api/tmdb/search/movie?{q}"

        try:
            req = urllib.request.Request(req_url, headers={'User-Agent': 'Juku Kodi Scraper'})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                if data.get('success') and data.get('data'):
                    results = data['data'].get('results', [])
                    items = []
                    for item in results:
                        items.append({
                            'id': item.get('id'),
                            'title': item.get('title') or item.get('original_title'),
                            'year': (item.get('release_date') or '')[:4],
                            'url': f"{self.base_url}/api/tmdb/movie/{item.get('id')}"
                        })
                    return items
        except Exception as e:
            xbmc.log(f"[JukuScraper] 搜索 TMDB 失败: {e}", xbmc.LOGWARNING)

        return []

    def get_movie_detail(self, tmdb_id):
        """
        通过 Go 守护进程获取 TMDB 电影完整元数据
        """
        if not tmdb_id:
            return None

        req_url = f"{self.base_url}/api/tmdb/movie/{tmdb_id}?language=zh-CN"
        try:
            req = urllib.request.Request(req_url, headers={'User-Agent': 'Juku Kodi Scraper'})
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode('utf-8'))
                if data.get('success') and data.get('data'):
                    return data['data']
        except Exception as e:
            xbmc.log(f"[JukuScraper] 获取 TMDB 详情失败 (ID={tmdb_id}): {e}", xbmc.LOGERROR)

        return None

    def populate_listitem_metadata(self, list_item, tmdb_data):
        """
        将 TMDB 详情数据完整组装注入到 Kodi 的 ListItem / VideoInfoTag 中
        """
        if not list_item or not tmdb_data:
            return

        title = tmdb_data.get('title', '')
        original_title = tmdb_data.get('original_title', '')
        plot = tmdb_data.get('overview', '')
        release_date = tmdb_data.get('release_date', '')
        year = int(release_date[:4]) if release_date and len(release_date) >= 4 and release_date[:4].isdigit() else 0
        rating = float(tmdb_data.get('vote_average', 0.0))
        votes = int(tmdb_data.get('vote_count', 0))
        runtime = int(tmdb_data.get('runtime', 0)) * 60

        genres = [g.get('name') for g in tmdb_data.get('genres', []) if g.get('name')]
        
        # 演职员表
        cast_list = []
        directors = []
        writers = []

        credits = tmdb_data.get('credits', {})
        for cast in credits.get('cast', [])[:30]:
            name = cast.get('name', '')
            character = cast.get('character', '')
            profile_path = cast.get('profile_path')
            thumb = proxied_image_url(f"https://image.tmdb.org/t/p/w185{profile_path}") if profile_path else ""
            if name:
                cast_list.append({
                    'name': name,
                    'role': character,
                    'thumbnail': thumb
                })

        for crew in credits.get('crew', []):
            job = crew.get('job', '')
            name = crew.get('name', '')
            if not name:
                continue
            if job == 'Director' and name not in directors:
                directors.append(name)
            elif job in ('Screenplay', 'Writer') and name not in writers:
                writers.append(name)

        # 艺术图 (海报与同人画)
        poster_path = tmdb_data.get('poster_path')
        backdrop_path = tmdb_data.get('backdrop_path')
        poster_url = proxied_image_url(f"https://image.tmdb.org/t/p/w500{poster_path}") if poster_path else ""
        fanart_url = proxied_image_url(f"https://image.tmdb.org/t/p/original{backdrop_path}") if backdrop_path else ""

        # Kodi 20/21 新版 getVideoInfoTag API
        try:
            tag = list_item.getVideoInfoTag()
            tag.setMediaType('movie')
            if title: tag.setTitle(title)
            if original_title: tag.setOriginalTitle(original_title)
            if plot: tag.setPlot(plot)
            if year > 0: tag.setYear(year)
            if release_date: tag.setPremiered(release_date)
            if rating > 0: tag.setRating(rating)
            if votes > 0: tag.setVotes(votes)
            if runtime > 0: tag.setDuration(runtime)
            if genres: tag.setGenres(genres)
            if directors: tag.setDirectors(directors)
            if writers: tag.setWriters(writers)
            if cast_list:
                try:
                    # Kodi 20+ setCast
                    from xbmc import Actor
                    tag.setCast([Actor(c['name'], c['role'], 0, c['thumbnail']) for c in cast_list])
                except (ImportError, AttributeError):
                    tag.setCast([{'name': c['name'], 'role': c['role'], 'thumbnail': c['thumbnail']} for c in cast_list])

            # 外部 ID
            unique_ids = {'tmdb': str(tmdb_data.get('id', ''))}
            ext_ids = tmdb_data.get('external_ids', {})
            if ext_ids.get('imdb_id'):
                unique_ids['imdb'] = ext_ids['imdb_id']
            tag.setUniqueIDs(unique_ids, 'tmdb')
        except Exception:
            # 降级支持旧版 setInfo
            info = {
                'mediatype': 'movie',
                'title': title,
                'originaltitle': original_title,
                'plot': plot,
                'year': year,
                'premiered': release_date,
                'rating': rating,
                'votes': votes,
                'duration': runtime,
                'genre': ' / '.join(genres),
                'director': ' / '.join(directors),
                'writer': ' / '.join(writers),
            }
            list_item.setInfo('video', info)

        art = {}
        if poster_url:
            art['poster'] = poster_url
            art['thumb'] = poster_url
        if fanart_url:
            art['fanart'] = fanart_url
        if art:
            list_item.setArt(art)


def main():
    """
    Kodi 官方刮削器入口分发
    """
    if len(sys.argv) < 2:
        return

    action = sys.argv[1]
    scraper = TMDBMovieScraper()

    if action == "find":
        # 查找电影
        title = sys.argv[2] if len(sys.argv) > 2 else ""
        year = sys.argv[3] if len(sys.argv) > 3 else ""
        results = scraper.find_movie(title, year)
        # 将结果输出至 Kodi 刮削器管道或标准输出
        xbmc.log(f"[JukuScraper] 找到 {len(results)} 部候选电影: {title}", xbmc.LOGINFO)

    elif action == "getdetails":
        url = sys.argv[2] if len(sys.argv) > 2 else ""
        # 提取 tmdb_id
        m = re.search(r'/movie/(\d+)', url)
        if m:
            tmdb_id = int(m.group(1))
            detail = scraper.get_movie_detail(tmdb_id)
            if detail:
                xbmc.log(f"[JukuScraper] 成功获取电影详情: {detail.get('title')}", xbmc.LOGINFO)

if __name__ == "__main__":
    main()
