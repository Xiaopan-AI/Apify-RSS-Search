# Apify SDK - toolkit for building Apify Actors (Read more at https://docs.apify.com/sdk/python)
from apify import Actor
import bs4
import asyncio
import aiohttp
import argparse
import feedparser
import pandas as pd
from thefuzz import fuzz


async def process_one_entry(
    entry: dict,
    query: str,
    method: str = "token_set_ratio"
) -> int:
    """Process one entry, match with query, return its relevancy score and other data

    Args:
        entry (dict): Contains one entry data parsed from the feed
        query (str): String to be matched with data

    Returns:
        int: score from thefuzz
    """
    title = entry["title"]
    link = entry["link"]
    # Use beautifulsoup to only extract text from the possible HTML that is in the description
    soup = bs4.BeautifulSoup(entry["description"], "html.parser")
    description = soup.get_text()

    match method:
        case "token_set_ratio":
            match_func = fuzz.token_set_ratio
        case _:
            match_func = fuzz.ratio
    title_score = match_func(query, title)
    description_score = match_func(query, description)
    return {
        "title": title,
        "link": link,
        "text": description,
        "title_score": title_score,
        "description_score": description_score,
    }


async def parse_one_feed(
    url: str,
    query: str,
    proxy: bool | None = None,
    actor: Actor | None = None,
    timeout: int = 60,
) -> dict:
    """
    Parse and match one RSS feed, return a data dict
    """
    if proxy:
        proxy_configuration = await actor.create_proxy_configuration()
        proxy = await proxy_configuration.new_url()
    async with aiohttp.ClientSession() as session:
        async with session.get(url, proxy=proxy, timeout=timeout) as response:
            text = await response.text()
    feed = feedparser.parse(text)
    match_tasks = [process_one_entry(entry, query) for entry in feed.entries]
    results = await asyncio.gather(*match_tasks)
    return results


def process_results(
    res: list[list],
    top_n: int,
    sort_by: str = "score",
) -> list[dict]:
    """Get top n results from the parsed feeds

    Args:
        res (list[list]): List of lists containing parsed feeds
        top_n (int): Number of top results to be shown

    Returns:
        list[dict]: List of dicts containing top n results
    """
    # Results is a list of lists, flatten it
    results = [item for sublist in res for item in sublist]
    df = pd.DataFrame(results)
    df["score"] = df["title_score"] * df["description_score"]
    # Show top 10 results based on score
    return df.sort_values(sort_by, ascending=False).head(top_n).reset_index(drop=True)


async def main():
    async with Actor:
        Actor.log.info("RSS Search Actor Initialized")
        # Write your code here
        actor_input = await Actor.get_input() or {}
        query = actor_input.get("query")
        feeds = actor_input.get("feeds")
        top_n = actor_input.get("top_n", 10)
        # Start parsing
        await Actor.set_status_message("Parsing feeds")
        parse_tasks = [parse_one_feed(url, query, proxy=True, actor=Actor) for url in feeds]
        results = await asyncio.gather(*parse_tasks)
        await Actor.set_status_message("Processing results")
        # Process results
        results = process_results(results, top_n)
        await Actor.push_data(results.to_dict(orient="records"))


async def local_test():
    parser = argparse.ArgumentParser()
    parser.add_argument("-f", "--feed", nargs="+", type=str, required=True, help="Feed URLs to be parsed")
    parser.add_argument("-q", "--query", type=str, required=True, help="Query string to be matched with the feed")
    parser.add_argument("--method", type=str, default="token_set_ratio", help="Method used for fuzzy matching")
    parser.add_argument("-n", "--top_n", type=int, default=10, help="Number of top results to be shown")
    args = parser.parse_args()
    # Start parsing
    parse_tasks = [parse_one_feed(url, args.query) for url in args.feed]
    results = await asyncio.gather(*parse_tasks)
    # Process results
    results = process_results(results, args.top_n)
    print(results.to_dict(orient="records"))

if __name__ == "__main__":
    asyncio.run(local_test())