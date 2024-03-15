import requests
import re
import json
from fake_useragent import UserAgent
from environs import Env
import logging


UA = UserAgent()
GET_USER_URL = (
    "https://twitter.com/i/api/graphql/SAMkL5y_N9pmahSw8yy6gw/UserByScreenName"
)
GET_TWEETS_URL = "https://twitter.com/i/api/graphql/XicnWRbyQ3WgVY__VataBQ/UserTweets"

FEATURES_USER = '{"hidden_profile_likes_enabled":false,"hidden_profile_subscriptions_enabled":true,"responsive_web_graphql_exclude_directive_enabled":true,"verified_phone_label_enabled":false,"subscriptions_verification_info_is_identity_verified_enabled":false,"subscriptions_verification_info_verified_since_enabled":true,"highlights_tweets_tab_ui_enabled":true,"creator_subscriptions_tweet_preview_api_enabled":true,"responsive_web_graphql_skip_user_profile_image_extensions_enabled":false,"responsive_web_graphql_timeline_navigation_enabled":true}'
FEATURES_TWEETS = '{"rweb_lists_timeline_redesign_enabled":true,"responsive_web_graphql_exclude_directive_enabled":true,"verified_phone_label_enabled":false,"creator_subscriptions_tweet_preview_api_enabled":true,"responsive_web_graphql_timeline_navigation_enabled":true,"responsive_web_graphql_skip_user_profile_image_extensions_enabled":false,"tweetypie_unmention_optimization_enabled":true,"responsive_web_edit_tweet_api_enabled":true,"graphql_is_translatable_rweb_tweet_is_translatable_enabled":true,"view_counts_everywhere_api_enabled":true,"longform_notetweets_consumption_enabled":true,"responsive_web_twitter_article_tweet_consumption_enabled":false,"tweet_awards_web_tipping_enabled":false,"freedom_of_speech_not_reach_fetch_enabled":true,"standardized_nudges_misinfo":true,"tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled":true,"longform_notetweets_rich_text_read_enabled":true,"longform_notetweets_inline_media_enabled":true,"responsive_web_media_download_video_enabled":false,"responsive_web_enhance_cards_enabled":false}'

HEADERS = {
    "authority": "twitter.com",
    "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
    "accept-language": "ru-RU,ru;q=0.9",
    "cache-control": "max-age=0",
    "sec-ch-ua": '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Linux"',
    "sec-fetch-dest": "document",
    "sec-fetch-mode": "navigate",
    "sec-fetch-site": "same-origin",
    "sec-fetch-user": "?1",
    "upgrade-insecure-requests": "1",
    "user-agent": UA.chrome,
}


def get_mask_page(auth_headers: dict, params: dict, proxies: dict) -> dict:
    resp = requests.get("https://twitter.com/", headers=HEADERS, proxies=proxies)
    guest_token = resp.cookies.get_dict().get("gt") or "".join(
        re.findall(r"(?<=\"gt\=)[^;]+", resp.text)
    )
    auth_headers["x-guest-token"] = guest_token
    response = requests.get(
        GET_USER_URL, params=params, headers=auth_headers, proxies=proxies
    )

    json_response = response.json()

    result = json_response.get("data", {}).get("user", {}).get("result", {})
    legacy = result.get("legacy", {})

    response_data = {"id": result.get("rest_id"), "full_name": legacy.get("name")}
    return response_data


def parse_tweets(
    user_id: str,
    full_name: str,
    result: dict,
    item_result: dict,
    legacy: dict,
    tweet_id: str,
) -> dict:
    medias = legacy.get("entities").get("media")
    if medias:
        medias = ", ".join(
            [
                "%s (%s)" % (media.get("media_url_https"), media.get("type"))
                for media in legacy.get("entities").get("media")
            ]
        )
    else:
        medias = None

    parse_data = {
        "id": result.get("rest_id"),
        "tweet_url": f"https://twitter.com/elonmusk/status/{tweet_id}",
        "name": full_name,
        "user_id": user_id,
        "username": "elonmusk",
        "published_at": legacy.get("created_at"),
        "content": legacy.get("full_text"),
        "views_count": item_result.get("views", {}).get("count"),
        "retweet_count": legacy.get("retweet_count"),
        "likes": legacy.get("favorite_count"),
        "quote_count": legacy.get("quote_count"),
        "reply_count": legacy.get("reply_count"),
        "bookmarks_count": legacy.get("bookmark_count"),
        "medias": medias,
    }
    return parse_data


def iter_twits(user: dict, auth_headers: dict, proxies: dict, limit=30) -> list:
    full_name = user.get("full_name")
    user_id = user.get("id")
    cursor = None
    _tweets = []

    while True:
        var = {
            "userId": user_id,
            "count": 100,
            "cursor": cursor,
            "includePromotedContent": True,
            "withQuickPromoteEligibilityTweetFields": True,
            "withVoice": True,
            "withV2Timeline": True,
        }

        params = {
            "variables": json.dumps(var),
            "features": FEATURES_TWEETS,
        }

        response = requests.get(
            GET_TWEETS_URL, params=params, headers=auth_headers, proxies=proxies
        )

        json_response = response.json()

        result = json_response.get("data", {}).get("user", {}).get("result", {})
        timeline = (
            result.get("timeline_v2", {}).get("timeline", {}).get("instructions", {})
        )
        entries = [
            x.get("entries") for x in timeline if x.get("type") == "TimelineAddEntries"
        ]
        if entries:
            entries = entries[0]
        else:
            entries = []

        for entry in entries:
            content = entry.get("content")
            entry_type = content.get("entryType")
            tweet_id = entry.get("sortIndex")
            if entry_type == "TimelineTimelineItem":
                item_result = (
                    content.get("itemContent", {})
                    .get("tweet_results", {})
                    .get("result", {})
                )
                legacy = item_result.get("legacy")

                tweet_data = parse_tweets(
                    user_id, full_name, result, item_result, legacy, tweet_id
                )
                _tweets.append(tweet_data)

            if (
                entry_type == "TimelineTimelineCursor"
                and content.get("cursorType") == "Bottom"
            ):
                cursor = content.get("value")

            if len(_tweets) >= limit:
                break

        if len(_tweets) >= limit or cursor is None or len(entries) == 2:
            break

    return _tweets


def get_twits_text(twits_data: list) -> list:
    twits_text = []
    for twit in twits_data:
        twit_text = twit.get("content")
        twits_text.append(twit_text)
    return twits_text


def log_twits(twits_text: list) -> None:
    logging.basicConfig(level=logging.INFO, filename="twits.log", filemode="w")
    logging.info("Information about twits")
    twit_count = 0
    for number, twit in enumerate(twits_text):
        twit = twit.split("http")
        twit = twit[0]
        if twit:
            twit_count += 1
            logging.info(f"{twit_count} twit:  {twit}")
            print(f"{twit_count} twit:  {twit}")
            if twit_count == 10:
                break


def main():
    env = Env()
    env.read_env()
    http_proxie = env("HTTP")
    https_proxie = env("HTTPS")

    proxies = {
        "http": http_proxie,
        "https": https_proxie,
    }
    arguments = {"screen_name": "elonmusk", "withSafetyModeUserFields": True}

    params = {
        "variables": json.dumps(arguments),
        "features": FEATURES_USER,
    }
    auth_headers = {
        "authorization": "Bearer AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA",
        "x-guest-token": None,
    }
    elon = get_mask_page(auth_headers, params, proxies)
    iter_data = iter_twits(elon, auth_headers, proxies, limit=30)
    twits = get_twits_text(iter_data)
    log_twits(twits)


if __name__ == "__main__":
    main()
