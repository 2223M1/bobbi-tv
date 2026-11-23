"""ID-bound movie release-year evidence from the existing detail cache only."""
import re


def cached_movie_years(tmdb_id):
    """Never fetch TMDb from a provider/subtitle worker or trust IPC year lists."""
    identity = cached_movie_identity(tmdb_id)
    return identity['evidence'] if identity else None


def cached_movie_identity(tmdb_id):
    """Read canonical aliases and years from the same cached TMDb response."""
    if isinstance(tmdb_id, bool) or not str(tmdb_id).isdigit() or int(tmdb_id) <= 0:
        return None
    try:
        from bobbi_core.movie_years import from_details
        from lib.api.tmdbv3api.as_obj import AsObj
        from lib.api.tmdbv3api.tmdb import TMDb
        from lib.db.cached import cache
        legacy = 'movie_details|{}|{}'.format(tmdb_id, TMDb().language)
        detail = cache.get(key='movie-years303|' + legacy)
        if detail is None:
            detail = cache.get(key=legacy)
        if isinstance(detail, AsObj):
            detail = detail.to_dict()
        evidence = from_details(detail, int(tmdb_id))
        if evidence is None:
            return None
        aliases = [detail.get('title'), detail.get('original_title')]
        translations = detail.get('translations')
        translations = translations.get('translations') if isinstance(translations, dict) else []
        for item in translations[:128] if isinstance(translations, list) else []:
            if isinstance(item, dict) and isinstance(item.get('data'), dict):
                aliases.append(item['data'].get('title'))
        alternate = detail.get('alternative_titles')
        alternate = alternate.get('titles', alternate.get('results')) if isinstance(alternate, dict) else []
        for item in alternate[:128] if isinstance(alternate, list) else []:
            if isinstance(item, dict):
                aliases.append(item.get('title'))
        aliases = list(dict.fromkeys(value.strip() for value in aliases
            if isinstance(value, str) and 1 <= len(value.strip()) <= 512))
        imdb_id = detail.get('imdb_id')
        if not isinstance(imdb_id, str) or not re.fullmatch(r'tt[0-9]{7,12}', imdb_id):
            imdb_id = None
        return dict(tmdb_id=int(tmdb_id), evidence=evidence, aliases=aliases, imdb_id=imdb_id)
    except (ImportError, OSError, ValueError, TypeError, AttributeError):
        return None
