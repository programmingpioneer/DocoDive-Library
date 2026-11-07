"""Homepage presentation defaults, separate from measured database totals."""

COMMUNITY_COUNTER_START = 273839


def community_display_count(registered_users):
    return COMMUNITY_COUNTER_START + max(0, int(registered_users or 0))


def homepage_review_cards(reviews):
    if reviews:
        return [dict(review) for review in reviews]
    comments = (
        'A place to find your next programming book and keep learning at your own pace.',
        'Explore the library, save a useful title and return whenever you are ready to read.',
        'Follow a learning path and discover books that help you practise along the way.',
    )
    return [dict(username='Sample', full_name=f'Sample reader {index}', avatar='',
                 rating=5, comment=comment, sample=True)
            for index, comment in enumerate(comments, 1)]
