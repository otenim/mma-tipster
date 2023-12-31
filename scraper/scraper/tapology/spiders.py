import scrapy
import copy
from scrapy.http import TextResponse, Request
from collections.abc import Generator
from . import consts
from .errors import NormalizeError, ParseError
from .utils import (
    normalize_text,
    normalize_sport,
    normalize_status,
    parse_date,
    normalize_weight_class,
    normalize_billing,
    parse_round_format,
    parse_last_weigh_in,
    parse_nickname,
    parse_record,
    parse_earnings,
    parse_height,
    parse_reach,
    parse_weight_summary,
    parse_odds,
    parse_end_time,
    parse_title_info,
    parse_method,
    correct_match_url,
    correct_event_url,
    is_na,
    calc_age,
)


class FightersSpider(scrapy.Spider):
    name = "fighters"
    start_urls = [
        "https://www.tapology.com/search/mma-fighters-by-weight-class/Atomweight-105-pounds",
        "https://www.tapology.com/search/mma-fighters-by-weight-class/Strawweight-115-pounds",
        "https://www.tapology.com/search/mma-fighters-by-weight-class/Flyweight-125-pounds",
        "https://www.tapology.com/search/mma-fighters-by-weight-class/Bantamweight-135-pounds",
        "https://www.tapology.com/search/mma-fighters-by-weight-class/Featherweight-145-pounds",
        "https://www.tapology.com/search/mma-fighters-by-weight-class/Lightweight-155-pounds",
        "https://www.tapology.com/search/mma-fighters-by-weight-class/Welterweight-170-pounds",
        "https://www.tapology.com/search/mma-fighters-by-weight-class/Middleweight-185-pounds",
        "https://www.tapology.com/search/mma-fighters-by-weight-class/Light_Heavyweight-205-pounds",
        "https://www.tapology.com/search/mma-fighters-by-weight-class/Heavyweight-265-pounds",
        "https://www.tapology.com/search/mma-fighters-by-weight-class/Super_Heavyweight-over-265-pounds",
    ]

    def __init__(
        self,
        scope: str = "profile",
        *args,
        **kwargs,
    ) -> None:
        super().__init__(*args, **kwargs)
        if scope not in ["profile", "result", "event"]:
            raise ValueError(f"Unsupported scope: {scope}")
        self.scope = scope

    def parse(self, response: TextResponse) -> Generator[Request, None, None]:
        fighters = response.xpath("//table[@class='siteSearchResults']/tr")[1:]
        for fighter in fighters:
            url = fighter.xpath("./td[1]/a/@href").get()
            if url is None:
                name = fighter.xpath("./td[1]/text()").get()
                self.logger.error(f"url is missing for fighter {name}")
                continue
            weight_class = fighter.xpath("./td[5]/text()").get()
            if weight_class is None:
                self.logger.error(f"weight class is missing for fighter {url}")
                continue
            try:
                weight_class = normalize_weight_class(weight_class)
            except NormalizeError as e:
                self.logger.error(e)
                continue
            if self.scope == "profile":
                req = response.follow(url, callback=self.parse_fighter_profile)
                req.cb_kwargs["weight_class"] = weight_class
                yield req
            elif self.scope in ["result", "event"]:
                yield response.follow(url, callback=self.parse_fighter_results)

        # Move to the next page
        next_url = response.xpath(
            "//span[@class='moreLink']/nav[@class='pagination']/span[@class='next']/a/@href"
        ).get()
        if next_url is not None:
            yield response.follow(next_url, callback=self.parse)

    def parse_fighter_profile(
        self, response: TextResponse, weight_class: str
    ) -> dict | None:
        ret = {"weight_class": weight_class}

        # Fighter ID (must)
        ret["id"] = response.url

        # Fighter name (optional)
        name = response.xpath(
            "//div[@class='fighterUpcomingHeader']/h1[not(@*)]/text()"
        ).get()
        if name is None or is_na(name):
            return
        ret["name"] = normalize_text(name)

        # Parse header section (must)
        header_section = response.xpath("//div[@class='fighterUpcomingHeader']")
        if len(header_section) == 0:
            return

        # Nationality (optional)
        nationality = header_section.xpath("./h2[@id='flag']/a/@href").re_first(
            r"country\-(.*)$"
        )
        if nationality is not None:
            ret["nationality"] = normalize_text(nationality)

        # Nickname (optional)
        nickname = header_section.xpath("./h4[@class='preTitle nickname']/text()").get()
        if nickname is not None and not is_na(nickname):
            try:
                ret["nickname"] = parse_nickname(nickname)
            except ParseError as e:
                self.logger.error(e)

        # Parse profile section (must)
        profile_section = response.xpath("//div[@class='details details_two_columns']")
        if len(profile_section) == 0:
            return

        # Pro mma record (optional)
        record = profile_section.xpath(
            "./ul/li/strong[text()='Pro MMA Record:']/following-sibling::span[1]/text()"
        ).get()
        if record is not None and not is_na(record):
            try:
                ret["record"] = parse_record(record)
            except ParseError as e:
                self.logger.error(e)

        # Date of birth (optional)
        date_of_birth = profile_section.xpath(
            "./ul/li/strong[text()='| Date of Birth:']/following-sibling::span[1]/text()"
        ).get()
        if date_of_birth is not None and not is_na(date_of_birth):
            try:
                ret["date_of_birth"] = parse_date(date_of_birth)
            except ParseError as e:
                self.logger.error(e)

        # Last weigh-in (optional)
        last_weigh_in = profile_section.xpath(
            "./ul/li/strong[text()='| Last Weigh-In:']/following-sibling::span[1]/text()"
        ).get()
        if last_weigh_in is not None and not is_na(last_weigh_in):
            try:
                ret["last_weigh_in"] = parse_last_weigh_in(last_weigh_in)
            except ParseError as e:
                self.logger.error(e)

        # Career disclosed earnings (optional)
        earnings = profile_section.xpath(
            "./ul/li/strong[text()='Career Disclosed Earnings:']/following-sibling::span[1]/text()"
        ).get()
        if earnings is not None and not is_na(earnings):
            try:
                ret["earnings"] = parse_earnings(earnings)
            except ParseError as e:
                self.logger.error(e)

        # Affiliation (optional)
        affili_url = profile_section.xpath(
            "./ul/li/strong[text()='Affiliation:']/following-sibling::span[1]/a/@href"
        ).get()
        if affili_url is not None:
            ret["affiliation"] = response.urljoin(affili_url)

        # Height (optional)
        height = profile_section.xpath(
            "./ul/li/strong[text()='Height:']/following-sibling::span[1]/text()"
        ).get()
        if height is not None and not is_na(height):
            try:
                ret["height"] = parse_height(height)
            except ParseError as e:
                self.logger.error(e)

        # Reach (optional)
        reach = profile_section.xpath(
            "./ul/li/strong[text()='| Reach:']/following-sibling::span[1]/text()"
        ).get()
        if reach is not None and not is_na(reach):
            try:
                ret["reach"] = parse_reach(reach)
            except ParseError as e:
                self.logger.error(e)

        # College (optional)
        college = profile_section.xpath(
            "./ul/li/strong[text()='College:']/following-sibling::span[1]/text()"
        ).get()
        if college is not None and not is_na(college):
            ret["college"] = normalize_text(college)

        # Foundation styles (optional)
        styles = profile_section.xpath(
            "./ul/li/strong[text()='Foundation Style:']/following-sibling::span[1]/text()"
        ).get()
        if styles is not None and not is_na(styles):
            ret["foundation_styles"] = []
            for s in normalize_text(styles).split(","):
                ret["foundation_styles"].append(s.strip())

        # Place of born (optional)
        born = profile_section.xpath(
            "./ul/li/strong[text()='Born:']/following-sibling::span[1]/text()"
        ).get()
        if born is not None and not is_na(born):
            ret["born"] = normalize_text(born)

        # Fighting out of (optional)
        out_of = profile_section.xpath(
            "./ul/li/strong[text()='Fighting out of:']/following-sibling::span[1]/text()"
        ).get()
        if out_of is not None and not is_na(out_of):
            ret["out_of"] = normalize_text(out_of)

        # Head Coach (optional)
        head_coach = profile_section.xpath(
            "./ul/li/strong[text()='Head Coach:']/following-sibling::span[1]/text()"
        ).get()
        if head_coach is not None and not is_na(head_coach):
            ret["head_coach"] = normalize_text(head_coach)
        return ret

    def parse_fighter_results(
        self, response: TextResponse
    ) -> Generator[dict | Request, None, None] | None:
        # Parse profile section (must)
        profile_section = response.xpath("//div[@class='details details_two_columns']")
        if len(profile_section) == 0:
            return

        # Date of birth (optional)
        date_of_birth = profile_section.xpath(
            "./ul/li/strong[text()='| Date of Birth:']/following-sibling::span[1]/text()"
        ).get()
        if date_of_birth is not None and not is_na(date_of_birth):
            try:
                date_of_birth = parse_date(date_of_birth)
            except ParseError as e:
                self.logger.error(e)

        # Parse results
        for division in [consts.DIVISION_PRO, consts.DIVISION_AM]:
            result_sections = response.xpath(
                f"//section[@class='fighterFightResults']/ul[@id='{division}Results']/li"
            )
            for result_section in result_sections:
                # Match ID (optional)
                match_url = result_section.xpath(
                    "./div[@class='result']/div[@class='summary']/div[@class='lead']/a/@href"
                ).get()
                if match_url is not None:
                    match_url = correct_match_url(response.urljoin(match_url))

                # Event ID (optional)
                event_url = result_section.xpath(
                    "./div[@class='result']/div[@class='summary']/div[@class='notes']/a[@title='Event Page']/@href"
                ).get()
                if event_url is not None:
                    event_url = correct_event_url(response.urljoin(event_url))

                if self.scope == "event":
                    if event_url is not None:
                        yield response.follow(event_url, callback=self.parse_event)
                elif self.scope == "result":
                    auxiliary = {"fighter": response.url, "division": division}
                    if match_url is not None:
                        auxiliary["match"] = match_url
                    if event_url is not None:
                        auxiliary["event"] = event_url

                    # Ignore inegligible matches
                    text = result_section.xpath(
                        "./div[@class='result']/div[@class='opponent']/div[@class='record nonMma']/text()"
                    ).get()
                    if text is not None and normalize_text(text).startswith(
                        "record ineligible"
                    ):
                        continue

                    # Status of the match (must)
                    status = result_section.xpath("./@data-status").get()
                    if status is None:
                        continue
                    try:
                        auxiliary["status"] = normalize_status(status)
                    except NormalizeError as e:
                        self.logger.error(e)
                        continue

                    # Ignore matches with status = cancelled, upcoming, unknown
                    if auxiliary["status"] in [
                        consts.STATUS_UPCOMING,
                        consts.STATUS_UNKNOWN,
                    ]:
                        continue

                    # Date of the match (must)
                    date = result_section.xpath(
                        "./div[@class='result']/div[@class='date']/text()"
                    ).get()
                    if date is None or is_na(date):
                        continue
                    try:
                        auxiliary["date"] = parse_date(date)
                    except ParseError as e:
                        self.logger.error(e)
                        continue

                    # Sport of the match (must)
                    sport = result_section.xpath("./@data-sport").get()
                    if sport is None:
                        continue
                    try:
                        auxiliary["sport"] = normalize_sport(sport)
                    except NormalizeError as e:
                        self.logger.error(e)
                        continue

                    # Calc age at the match (optional)
                    if date_of_birth is not None and not is_na(date_of_birth):
                        auxiliary["age"] = calc_age(auxiliary["date"], date_of_birth)

                    # Opponent section (must)
                    opponent_section = result_section.xpath(
                        "./div[@class='result']/div[@class='opponent']"
                    )
                    if len(opponent_section) == 0:
                        continue
                    auxiliary["opponent"] = {}

                    # ID of the opponent (must)
                    opponent_url = opponent_section.xpath(
                        "./div[@class='name']/a/@href"
                    ).get()
                    if opponent_url is None:
                        continue
                    auxiliary["opponent"] = response.urljoin(opponent_url)

                    # Record of the fighter (optional)
                    record = opponent_section.xpath(
                        "./div[@class='record']/span[@title='Fighter Record Before Fight']/text()"
                    ).get()
                    if record is not None and not is_na(record):
                        try:
                            parsed = parse_record(record)
                        except ParseError as e:
                            self.logger.error(e)
                        else:
                            auxiliary["record_before"] = parsed
                            auxiliary["record_after"] = parsed
                            status = auxiliary["status"]
                            if status == consts.STATUS_WIN:
                                auxiliary["record_after"]["w"] += 1
                            elif status == consts.STATUS_LOSS:
                                auxiliary["record_after"]["l"] += 1
                            elif status == consts.STATUS_DRAW:
                                auxiliary["record_after"]["d"] += 1

                    # More info (optional)
                    label_sections = result_section.xpath(
                        "./div[@class='details tall']/div[@class='div']/span[@class='label']"
                    )
                    for label_section in label_sections:
                        label = label_section.xpath("./text()").get()
                        if label is None:
                            continue
                        label = normalize_text(label)
                        if label == "billing:":
                            # Billing of the match
                            billing = label_section.xpath(
                                "./following-sibling::span[1]/text()"
                            ).get()
                            if billing is not None and not is_na(billing):
                                try:
                                    auxiliary["billing"] = normalize_billing(billing)
                                except NormalizeError as e:
                                    self.logger.error(e)
                        elif label == "duration:":
                            # Round format of the match
                            round_format = label_section.xpath(
                                "./following-sibling::span[1]/text()"
                            ).get()
                            if round_format is not None and not is_na(round_format):
                                try:
                                    auxiliary["round_format"] = parse_round_format(
                                        round_format
                                    )
                                except ParseError as e:
                                    self.logger.error(e)
                        elif label == "referee:":
                            # Referee of the match
                            referee = label_section.xpath(
                                "./following-sibling::span[1]/text()"
                            ).get()
                            if referee is not None and not is_na(referee):
                                auxiliary["referee"] = normalize_text(referee)
                        elif label == "weight:":
                            # Weight infomation of the match
                            weight_summary = label_section.xpath(
                                "./following-sibling::span[1]/text()"
                            ).get()
                            if weight_summary is not None and not is_na(weight_summary):
                                try:
                                    auxiliary["weight"] = parse_weight_summary(
                                        weight_summary
                                    )
                                except ParseError as e:
                                    if e.text not in ["*numeric weight*"]:
                                        self.logger.error(e)
                        elif label == "odds:":
                            # Odds of the fighter
                            odds = label_section.xpath(
                                "./following-sibling::span[1]/text()"
                            ).get()
                            if odds is not None:
                                try:
                                    auxiliary["odds"] = parse_odds(odds)
                                except ParseError as e:
                                    self.logger.error(e)
                        elif label == "title bout:":
                            # Title infomation
                            title_info = label_section.xpath(
                                "./following-sibling::span[1]/text()"
                            ).get()
                            if title_info is not None:
                                try:
                                    auxiliary["title_info"] = parse_title_info(
                                        title_info
                                    )
                                except ParseError as e:
                                    self.logger.error(e)

                    # Return
                    if "event" in auxiliary and "match" in auxiliary:
                        req = response.follow(
                            url=event_url,
                            callback=self.parse_event_results,
                            dont_filter=True,
                        )
                        req.cb_kwargs["auxiliary"] = auxiliary
                        yield req
                    else:
                        yield auxiliary

    def parse_event(self, response: TextResponse) -> dict | None:
        ret = {"id": response.url}

        # Name of event (must)
        name = response.xpath("//div[@class='eventPageHeaderTitles']/h1/text()").get()
        if name is None or is_na(name):
            self.logger.error(f"no event title available on event {response.url}")
            return
        ret["name"] = normalize_text(name)

        # Details section (must)
        details_section = response.xpath(
            "//div[contains(@class, 'details')]/div[@class='right']/ul"
        )
        if details_section == 0:
            self.logger.error(f"no details section on event {response.url}")
            return

        # Date (must)
        date = details_section.xpath("./li[@class='header']/text()").get()
        if date is None or is_na(date):
            self.logger.error(f"date is unknown on event {response.url}")
            return
        try:
            ret["date"] = parse_date(date)
        except ParseError as e:
            self.logger.error(e)

        # Details (optional)
        for section in details_section.xpath("./li[not(@class='header')]"):
            label = section.xpath("./strong/text()").get()
            if label is None:
                continue
            label = normalize_text(label)
            if label == "promotion:":
                promotion_url = section.xpath("./span/a/@href").get()
                if promotion_url is not None:
                    ret["promotion"] = response.urljoin(promotion_url)
            elif label == "location:":
                location = section.xpath("./span/a/text()").get()
                if location is None:
                    location = section.xpath("./span/text()").get()
                if location is not None:
                    ret["location"] = normalize_text(location)
                region_url = section.xpath("./span/a/@href").get()
                if region_url is not None:
                    ret["region"] = region_url.split("/")[-1]
            elif label == "enclosure:":
                enclosure = section.xpath("./span/text()").get()
                if enclosure is not None:
                    ret["enclosure"] = normalize_text(enclosure)
            elif label == "venue:":
                venue = section.xpath("./span/text()").get()
                if venue is not None:
                    ret["venue"] = normalize_text(venue)
            elif label == "ring announcer:":
                announcer = section.xpath("./span/text()").get()
                if announcer is not None:
                    ret["ring_announcer"] = normalize_text(announcer)
            elif label == "ownership:":
                ownership = section.xpath("./span/text()").get()
                if ownership is not None:
                    ret["ownership"] = normalize_text(ownership)

        # Bout cards (optional)
        bout_card_sections = response.xpath(
            "//ul[@class='fightCard']/li[@class='fightCard']/div[@class='fightCardBout']"
        )
        cards = []
        for bout_card_section in bout_card_sections:
            bout_item = {}

            # Fighters (optional)
            for side in ["left", "right"]:
                fighter_item = {}
                fighter_section = bout_card_section.xpath(
                    f"./div[contains(@class, 'fightCardFighterBout') and contains(@class, '{side}')]/div[@class='fightCardFighterName {side}']"
                )
                # Fighter ID (optional)
                fighter_url = fighter_section.xpath("./a/@href").get()
                if fighter_url is not None:
                    fighter_item["id"] = response.urljoin(fighter_url)

                # Fighter name (optional)
                fighter_name = fighter_section.xpath("./a/text()").get()
                if fighter_name is None:
                    fighter_name = fighter_section.xpath("./text()").get()
                    if fighter_name is not None and not is_na(fighter_name):
                        fighter_item["name"] = normalize_text(fighter_name)
                else:
                    fighter_item["name"] = normalize_text(fighter_name)

                # Fighter status (optional)
                fighter_status = bout_card_section.xpath(
                    f"./div[contains(@class, 'fightCardFighterBout') and contains(@class, '{side}')]/@class"
                ).get()
                if fighter_status is not None:
                    split = normalize_text(fighter_status).split(" ")
                    if len(split) == 3:
                        # fightCardFighterBout left win
                        fighter_status = split[-1]
                        try:
                            fighter_item["status"] = normalize_status(fighter_status)
                        except NormalizeError as e:
                            self.logger.error(e)
                    else:
                        # fightCardFighterBout left
                        fighter_item["status"] = consts.STATUS_UNKNOWN

                bout_item[f"fighter_{side}"] = fighter_item

            # Match ID (optional)
            match_url = bout_card_section.xpath(
                "./div[contains(@class, 'fightCardMatchup')]/table/tr/td/span[@class='billing']/a/@href"
            ).get()
            if match_url is not None and not is_na(match_url):
                bout_item["match"] = response.urljoin(match_url)

            # Sport (optional)
            sport = bout_card_section.xpath(
                "./div[@class='fightCardMatchup sport']/table/tr/td/div[@class='fightCardSport']/text()"
            ).get()
            if sport is not None:
                try:
                    bout_item["sport"] = normalize_sport(sport)
                except NormalizeError as e:
                    self.logger.error(e)
            else:
                bout_item["sport"] = consts.SPORT_MMA

            # Billing (optional)
            billing = bout_card_section.xpath(
                "./div[contains(@class, 'fightCardMatchup')]/table/tr/td/span[@class='billing']/a/text()"
            ).get()
            if billing is not None and not is_na(billing):
                try:
                    bout_item["billing"] = normalize_billing(billing)
                except NormalizeError as e:
                    self.logger.error(e)

            # No of bout (optional)
            no = bout_card_section.xpath(
                "./div[@class='fightCardBoutNumber']/text()"
            ).get()
            if no is not None and not is_na(no):
                bout_item["no"] = int(no)
            cards.append(bout_item)
        ret["cards"] = cards
        ret["total_cards"] = len(cards)
        return ret

    def parse_event_results(self, response: TextResponse, auxiliary: dict) -> dict:
        ret = copy.deepcopy(auxiliary)
        bout_card_sections = response.xpath(
            "//ul[@class='fightCard']/li[@class='fightCard']/div[@class='fightCardBout']"
        )
        for bout_card_section in bout_card_sections:
            match_url = bout_card_section.xpath(
                "./div[contains(@class, 'fightCardMatchup')]/table/tr/td/span[@class='billing']/a/@href"
            ).get()
            if match_url is not None and ret["match"] == response.urljoin(match_url):
                # Method (optional)
                method = bout_card_section.xpath(
                    "./div[@class='fightCardResultHolder']/div[@class='fightCardResult']/span[@class='result']/text()"
                ).get()
                if method is not None and not is_na(method):
                    try:
                        ret["method"] = parse_method(method)
                    except ParseError as e:
                        self.logger.error(e)

                # End time (optional)
                end_time = bout_card_section.xpath(
                    "./div[@class='fightCardResultHolder']/div[@class='fightCardResult']/span[@class='time']/text()"
                ).get()
                if (
                    end_time is not None
                    and not is_na(end_time)
                    and not normalize_text(end_time).startswith("original")
                ):
                    try:
                        ret["end_time"] = parse_end_time(end_time)
                    except ParseError as e:
                        if e.text not in ["rounds"]:
                            self.logger.error(e)
                # Return item
                return ret

        # Check cancelled matches
        cancelled = response.xpath(
            "//ul[@class='eventCancelledBouts']/li[@class='eventCancelledBout']/div[@class='eventCancelledBout']/div[@class='eventCancelledBoutLink']/a/@href"
        ).getall()
        for url in cancelled:
            if ret["match"] == response.urljoin(url):
                return ret

        # Could not find the bout link on the event
        self.logger.error(
            f"could not find match {ret['match']} on event {ret['event']}"
        )
        return ret


class PromotionsSpider(scrapy.Spider):
    name = "promotions"
    start_urls = ["https://www.tapology.com/fightcenter/promotions"]

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

    def parse(self, response: TextResponse) -> Generator[dict | Request, None, None]:
        promotions = response.xpath(
            "//div[@class='promotionsIndex']/ul[@class='promotions']/li"
        )
        for promotion in promotions:
            ret = {}

            # Name section (must)
            name_section = promotion.xpath("./div[@class='name']")
            if len(name_section) == 0:
                self.logger.error("name section is missing")
                continue

            # ID (must)
            url = name_section.xpath("./span[1]/a/@href").get()
            if url is None:
                self.logger.error("url is missing")
                continue
            ret["id"] = response.urljoin(url)

            # Name of promotion (must)
            name = name_section.xpath("./span[1]/a/text()").get()
            if name is None:
                self.logger.error("name is missing")
                continue
            ret["name"] = normalize_text(name)

            # Shorten name (optional)
            shorten = name_section.xpath("./span[2]/text()").get()
            if shorten is not None:
                ret["shorten"] = normalize_text(shorten)

            # Headquarter (two-character country code, optional)
            flag = promotion.xpath("./div[@class='headquarters']/img/@src").get()
            if flag is not None:
                code = normalize_text(flag.split("/")[-1].split("-")[0])
                if len(code) == 2:
                    ret["headquarter"] = code
                else:
                    self.logger.erro(f"not a two-character country code: {code}")
            yield ret

        # To the next page
        next_url = response.xpath(
            "//span[@class='moreLink']/nav[@class='pagination']/span[@class='next']/a/@href"
        ).get()
        if next_url is not None:
            yield response.follow(next_url, callback=self.parse)


class FemaleSpider(scrapy.Spider):
    name = "female"
    start_urls = ["https://www.tapology.com/search/misc/female-mixed-martial-artists"]

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

    def parse(self, response: TextResponse) -> Generator[dict | Request, None, None]:
        fighters = response.xpath("//table[@class='siteSearchResults']/tr")[1:]
        for fighter in fighters:
            url = fighter.xpath("./td[1]/a/@href").get()
            name = fighter.xpath("./td[1]/a/text()").get()
            if url is not None and name is not None:
                yield {"id": response.urljoin(url), "name": normalize_text(name)}
        next_url = response.xpath(
            "//span[@class='moreLink']/nav[@class='pagination']/span[@class='next']/a/@href"
        ).get()
        if next_url is not None:
            yield response.follow(next_url, callback=self.parse)
