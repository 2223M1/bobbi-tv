"""Choose a continuation from Kodi's actual episode history, never guessed IDs."""


def beginning(episodes):
    """An explicit whole-show restart starts at the first regular episode."""
    valid = [row for row in episodes if row.get('season', -1) >= 0 and row.get('episode', 0) > 0]
    regular = [row for row in valid if row['season'] > 0]
    rows = regular or valid
    if not rows:
        return {'status': 'no_episodes', 'note': '没有可确定季集编号的剧集，请先确认要播放的一集。'}
    order = lambda row: (row['season'], row['episode'])
    start = min(map(order, rows))
    choices = [row for row in rows if order(row) == start]
    if len(choices) != 1:
        return {'status': 'ambiguous', 'candidates': choices, 'note': '开头的剧集有多个版本，请选择要从头播放的一项。'}
    return {'status': 'beginning', 'recommended': choices[0],
            'play': {'kind': 'episode', 'id': choices[0]['episodeid'], 'resume': False}}


def continuation(episodes):
    def order(row):
        return row.get('season', 0), row.get('episode', 0)

    def position(row):
        return (row.get('resume') or {}).get('position', 0)

    def resumable(row):
        total = (row.get('resume') or {}).get('total', 0)
        return position(row) > 0 and (total <= 0 or position(row) < total)

    def completed(row):
        total = (row.get('resume') or {}).get('total', 0)
        return bool(row.get('playcount', 0)) or (total > 0 and position(row) >= total)

    def ambiguous(rows, note, last=None):
        result = {'status': 'ambiguous', 'candidates': rows, 'note': note}
        if last is not None:
            result['last_played'] = last
        return result

    def choose(row, status, note, last):
        if order(row)[0] < 0 or order(row)[1] <= 0:
            return ambiguous([row], '该剧集缺少有效季集编号，请确认后播放。', last)
        # Multiple library copies of the same next episode need user selection.
        versions = [x for x in episodes if order(x) == order(row)]
        if row is not last and len(versions) > 1:
            return ambiguous(versions, '下一集有多个媒体库版本，请让用户选择版本。', last)
        return {'status': status, 'last_played': last, 'recommended': row,
                'play': {'kind': 'episode', 'id': row['episodeid'], 'resume': True}, 'note': note}

    history = [row for row in episodes if row.get('lastplayed') or completed(row) or position(row) > 0]
    if not history:
        return {'status': 'no_history', 'note': '这些剧集没有最近播放时间、已看次数或断点，请询问从哪一集开始。'}
    dated = [row for row in history if row.get('lastplayed')]
    if dated:
        latest = max(row['lastplayed'] for row in dated)
        latest_rows = [row for row in dated if row['lastplayed'] == latest]
        undated = [row for row in history if not row.get('lastplayed') and resumable(row)]
        if undated:
            return ambiguous(latest_rows + undated, '另有剧集保存了断点但缺少播放时间，无法确定最近看的是哪一集，请确认。')
    else:
        latest_rows = history
    unfinished = [row for row in latest_rows if resumable(row)]
    if len(latest_rows) > 1 and (unfinished or any(not completed(row) for row in latest_rows)):
        return ambiguous(latest_rows, '多集的播放时间相同或缺失，不能确定观看先后，请用户确认。')
    last = unfinished[0] if unfinished else max(latest_rows, key=order)
    if resumable(last):
        return choose(last, 'resume', '这一集有明确观看断点，按 play 参数直接续播。', last)
    if not completed(last):
        return choose(last, 'restart_episode', '最近看过这一集但未保存断点，也未标记看完；从该集开头播放并说明原因。', last)
    following = sorted((row for row in episodes if order(row) > order(last) and not completed(row)), key=order)
    if following:
        return choose(following[0], 'next_episode', '按已看记录，播放媒体库中后续第一集未看完的剧集。', last)
    return {'status': 'no_next_episode', 'last_played': last,
            'note': '按已看记录，媒体库中没有后续未看剧集；不要擅自重播。'}
