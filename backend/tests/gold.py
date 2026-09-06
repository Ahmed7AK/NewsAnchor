"""Hand-labelled clustering gold set.

Each entry is one true story; the tuples inside it are (source_id, headline,
feed summary) as different outlets would have filed it. Single-entry stories
are either distractors or -- more usefully -- near misses deliberately placed
next to a story they must NOT be merged into.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from newsanchor.models import Article

NOW = datetime(2026, 9, 6, 12, 0, tzinfo=timezone.utc)

GOLD: list[list[tuple[str, str, str]]] = [
    [
        ("leftpaper", "Senate passes spending bill in late-night vote",
         "The Senate voted 63-36 late Thursday to approve the 1.7 trillion dollar "
         "spending package, averting a government shutdown."),
        ("rightmag", "Congress averts shutdown as Senate clears spending package",
         "Lawmakers approved the spending measure hours before funding was set to "
         "lapse, sending it to the president."),
        ("intlnews", "US Senate approves spending bill, ending shutdown standoff",
         "The vote ends weeks of brinkmanship over federal funding levels and "
         "agency budgets."),
    ],
    [
        ("intlnews", "Magnitude 6.1 earthquake strikes off coast of Japan",
         "The quake struck at a depth of 40km off Honshu. No tsunami warning was "
         "issued and no casualties reported."),
        ("intlnews2", "Earthquake of magnitude 6.1 hits waters near Japan",
         "Japan's meteorological agency recorded the tremor off the Honshu coast "
         "early Saturday."),
        ("centerwire", "Japan rattled by 6.1 quake, no tsunami warning issued",
         "Buildings swayed in coastal towns but authorities reported no damage or "
         "injuries."),
    ],
    [
        ("leftpaper", "Fed holds interest rates steady amid inflation concerns",
         "The Federal Open Market Committee left the benchmark rate unchanged at "
         "4.25 to 4.5 percent."),
        ("rightpaper", "Federal Reserve leaves rates unchanged as inflation cools",
         "Policymakers held the benchmark rate steady, citing easing price "
         "pressures."),
        ("centerwire", "Powell says Fed will keep rates on hold for now",
         "The Fed chair told reporters the committee is in no hurry to cut the "
         "benchmark rate."),
    ],
    [
        ("intlnews", "Ukraine says drone strike hit Russian oil refinery in Ryazan",
         "Kyiv said the overnight drone attack targeted the Ryazan refinery, one of "
         "Russia's largest."),
        ("intlnews2", "Russian refinery in Ryazan ablaze after Ukrainian drone attack",
         "A fire broke out at the Ryazan oil refinery following a drone strike, "
         "regional officials said."),
    ],
    [
        ("leftmag", "Apple unveils new iPhone with satellite messaging",
         "Apple introduced its latest iPhone lineup, adding two-way satellite "
         "texting."),
        ("rightpaper", "Apple's latest iPhone adds satellite texting features",
         "The new handset can send messages via satellite when no cellular network "
         "is available."),
    ],
    [
        ("intlnews", "Wildfires force evacuations across northern Portugal",
         "Thousands were evacuated as wildfires spread through forested areas of "
         "northern Portugal."),
        ("centerwire", "Portugal battles wildfires as thousands flee homes",
         "Firefighters worked through the night as blazes advanced on villages in "
         "the north."),
    ],
    [
        ("leftpaper", "Supreme Court agrees to hear major tariff case",
         "The justices will review whether the president exceeded his authority in "
         "imposing sweeping tariffs."),
        ("rightmag", "Justices take up challenge to presidential tariff powers",
         "The court granted certiorari in a case testing the limits of executive "
         "trade authority."),
    ],
    # -- near misses: same topic, different event --------------------------
    [("centerwire", "Magnitude 7.2 earthquake devastates central Chile",
      "At least 40 people were killed when a powerful quake struck Chile's central "
      "valley.")],
    [("rightpaper", "Senate rejects amendment to defense authorization act",
      "Senators voted down a proposal to cut funding for overseas troop "
      "deployments.")],
    [("leftpaper", "Supreme Court declines to hear gun rights appeal",
      "The justices left in place a lower court ruling upholding a state assault "
      "weapons ban.")],
    [("rightmag", "Fed governor resigns citing personal reasons",
      "A Federal Reserve governor announced their departure from the board "
      "effective next month.")],
    # -- distractors --------------------------------------------------------
    [("intlnews", "EU agrees new migration pact after marathon talks",
      "Member states reached a deal on asylum burden-sharing after all-night "
      "negotiations.")],
    [("leftmag", "Scientists discover water plumes on Enceladus",
      "New observations reveal jets of water vapour erupting from the Saturn "
      "moon.")],
    [("intlnews2", "Nigeria's central bank raises benchmark rate to 27 percent",
      "The move aims to curb inflation running above 30 percent.")],
    [("intlnews", "Manchester City sign Brazilian winger in record deal",
      "The club confirmed the transfer for a reported club-record fee.")],
    [("centerwire", "Measles outbreak spreads in three US states",
      "Health officials reported dozens of new cases among unvaccinated "
      "children.")],
    [("intlnews2", "India launches lunar sample return mission",
      "The spacecraft lifted off carrying equipment to collect and return lunar "
      "soil.")],
    [("intlnews", "Argentina's inflation slows for third straight month",
      "Monthly price growth eased to 2.1 percent, the statistics agency said.")],
    [("intlnews2", "Major cyberattack disrupts European airports",
      "Check-in systems were knocked offline at several hubs, delaying flights.")],
    [("leftmag", "Study links microplastics to cardiovascular risk",
      "Researchers found plastic particles in arterial plaque samples.")],
    [("intlnews", "Typhoon forces flight cancellations across Taiwan",
      "Airlines grounded hundreds of flights as the storm approached.")],
]


def gold_articles(*, use_summary: bool = True) -> tuple[list[Article], list[int]]:
    articles: list[Article] = []
    truth: list[int] = []
    for story_idx, story in enumerate(GOLD):
        for item_idx, (source_id, title, summary) in enumerate(story):
            articles.append(
                Article(
                    source_id=source_id,
                    title=title,
                    url=f"https://{source_id}.example/{story_idx}-{item_idx}",
                    published_at=NOW - timedelta(minutes=30 + story_idx),
                    summary=summary if use_summary else "",
                )
            )
            truth.append(story_idx)
    return articles, truth
