import logging

from helpers import _
from helpers import clean_id
from helpers import flair
from helpers import flair_post
from helpers import get_parent_post_id
from helpers import update_user_flair
from strings import already_claimed
from strings import claim_already_complete
from strings import claim_success
from strings import done_cannot_find_transcript
from strings import done_completed_transcript
from strings import done_still_unclaimed
from strings import reddit_url
from strings import rules_comment_unknown_format
from strings import summoned_submit_title


def process_mention(mention, r, tor):
    """
    Handles username mentions and handles the formatting and posting of
    those calls as workable jobs to ToR.
    
    :param mention: the Comment object containing the username mention.
    :param r: Active Reddit instance.
    :param tor: A shortcut; the Subreddit instance for ToR.
    :return: None.
    """
    # We have to do this entire parent / parent_permalink thing twice because
    # the method for calling a permalink changes for each object. Laaaame.
    if not mention.is_root:
        # this comment is in reply to something. Let's grab a comment object.
        parent = r.comment(id=clean_id(mention.parent_id))
        parent_permalink = parent.permalink()
        # a comment does not have a title attribute. Let's fake one by giving
        # it something to work with.
        parent.title = 'Unknown Content'
    else:
        # this is a post.
        parent = r.submission(id=clean_id(mention.parent_id))
        parent_permalink = parent.permalink
        # format that sucker so it looks right in the template.
        parent.title = '"' + parent.title + '"'

    logging.info(
        'Posting call for transcription on ID {}'.format(mention.parent_id)
    )

    # noinspection PyBroadException
    try:
        result = tor.submit(
            title=summoned_submit_title.format(
                sub=mention.subreddit.display_name,
                commentorpost=parent.__class__.__name__.lower(),
                title=parent.title
            ),
            url=reddit_url.format(parent_permalink)
        )
        result.reply(_(rules_comment_unknown_format))
        flair_post(result, flair.summoned_unclaimed)
        logging.info(
            'Posting success message in response to caller, u/{}'.format(mention.author)
        )
        mention.reply(_(
            'The transcribers have been summoned! Please be patient '
            'and we\'ll be along as quickly as we can.')
        )
    # I need to figure out what errors can happen here
    except Exception as e:
        logging.error(e)
        logging.error(
            'Posting failure message in response to caller, u/{}'.format(mention.author)
        )
        mention.reply(_(
            'Something appears to have gone wrong. Please message the '
            'moderators of r/TranscribersOfReddit to have them look at '
            'this. Thanks!')
        )


def process_claim(post, r):
    """
    Handles comment replies containing the word 'claim' and routes
    based on a basic decision tree.
    
    :param post: The Comment object containing the claim.
    :param r: Active Reddit object.
    :return: None.
    """
    top_parent = get_parent_post_id(post, r)

    if 'Unclaimed' in top_parent.link_flair_text:
        # need to get that "Summoned - Unclaimed" in there too
        post.reply(_(claim_success))
        flair_post(top_parent, flair.in_progress)
        logging.info(
            'Claim on ID {} by {} successful'.format(
                top_parent.fullname, post.author
            )
        )
    # can't claim something that's already claimed
    elif top_parent.link_flair_text == flair.in_progress:
        post.reply(_(already_claimed))
    elif top_parent.link_flair_text == flair.completed:
        post.reply(_(claim_already_complete))


def verified_posted_transcript(post, r):
    """
    Because we're using basic gamification, we need to put in at least
    a few things to make it difficult to game the system. When a user
    says they've completed a post, we check the parent post for a top-level
    comment by the user who is attempting to complete the post. If it's
    there, we update their flair and mark it complete. Otherwise, we
    ask them to please contact the mods.

    :param post: The Comment object that contains the string 'done'.
    :param r: Active Reddit object.
    :return: True if a post is found, False if not.
    """
    top_parent = get_parent_post_id(post, r)
    # get source link, check all comments, look for root level comment
    # by the author of the post. Return True if found, False if not.
    linked_resource = r.submission(top_parent.id_from_url(top_parent.url))
    for top_level_comment in linked_resource.comments:
        if post.author == top_level_comment.author:
            return True
    return False


def process_done(post, r, tor):
    """
    Handles comments where the user says they've completed a post.
    Also includes a basic decision tree to enable verification of
    the posts to try and make sure they actually posted a
    transcription.
    
    :param post: the Comment object which contains the string 'done'.
    :param r: Active Reddit object.
    :param tor: Shortcut; a Subreddit object for ToR.
    :return: None.
    """
    top_parent = get_parent_post_id(post, r)

    if flair.unclaimed in top_parent.link_flair_text:
        post.reply(_(done_still_unclaimed))
    elif top_parent.link_flair_text == flair.in_progress:
        if verified_posted_transcript(post, r):
            # we need to double-check these things to keep people
            # from gaming the system
            post.reply(_(done_completed_transcript))
            flair_post(top_parent, flair.completed)
            update_user_flair(post, tor, r)
            logging.info(
                'Post {} completed by {}!'.format(
                    top_parent.fullname, post.author
                )
            )
        else:
            logging.info(
                'Post {} does not appear to have a post by claimant {}. '
                'Hrm...'.format(
                    top_parent.fullname, post.author
                )
            )
            post.reply(_(done_cannot_find_transcript))
