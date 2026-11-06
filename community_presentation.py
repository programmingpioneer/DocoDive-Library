"""Read-only community display models. Stored badge tokens remain unchanged."""

MILESTONES = (
    ('first_download', 'First Download', 'downloads', 1, 'download', 'download'),
    ('book_collector', 'Book Collector', 'downloads', 10, 'book', 'downloads'),
    ('library_hoarder', 'Library Hoarder', 'downloads', 50, 'library', 'downloads'),
    ('favoriter', 'Favoriter', 'favorites', 5, 'heart', 'favorites'),
    ('reviewer', 'Reviewer', 'reviews', 3, 'star', 'reviews'),
    ('book_lover', 'Book Lover', 'longest', 7, 'flame', 'days in a streak'),
    ('avid_reader', 'Avid Reader', 'longest', 30, 'award', 'days in a streak'),
    ('bookworm', 'Bookworm', 'longest', 60, 'trophy', 'days in a streak'),
    ('legend', 'Legend', 'longest', 100, 'crown', 'days in a streak'),
)


def achievement_summary(downloads=0, favorites=0, reviews=0, longest=0):
    metrics = dict(zip(('downloads', 'favorites', 'reviews', 'longest'),
                       (max(0, int(n or 0)) for n in (downloads, favorites, reviews, longest))))
    items = []
    for key, name, metric, threshold, icon, unit in MILESTONES:
        value = metrics[metric]
        items.append(dict(key=key, name=name, metric=metric, threshold=threshold,
                          icon=icon, unit=unit, current=value, unlocked=value >= threshold,
                          progress=min(100, value * 100 // threshold), remaining=max(0, threshold-value)))
    count = sum(item['unlocked'] for item in items)
    locked = [item for item in items if not item['unlocked']]
    next_goal = max(locked, key=lambda item: item['progress']) if locked else None
    return dict(items=items, unlocked_count=count, completion=count * 100 // len(items), next=next_goal)


def rank_leaders(people):
    """Competition ranking agrees with the current-user higher-score query."""
    previous_points = None
    rank = 0
    result = []
    for position, person in enumerate(people, 1):
        points = int(person.get('points') or 0)
        if points != previous_points:
            rank = position
        result.append(dict(person, rank=rank))
        previous_points = points
    return result
