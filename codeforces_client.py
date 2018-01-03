#!/usr/bin/env python3


import argparse
#import asyncio  # TODO: Do things asynchronously and rigorously
import collections
import configparser
import curses
import hashlib
import json
import logging
import math
import pathlib
import subprocess  # TODO: Use subprocess.call(["vim", "codeforces_client.py"])
import sys
import tempfile
import time
import urllib.request

import selenium.webdriver


__version__ = "0.0.1"


_LOGGER_NAME = "codeforces_client"
_LOGGER = logging.getLogger(_LOGGER_NAME)
_LOGGER.setLevel(logging.NOTSET)


_LOGGING_LEVELS = [
    "CRITICAL",
    "ERROR",
    "WARNING",
    "INFO",
    "DEBUG",
    "NOTSET",
]


class ResponseError(Exception):
    pass


def _hexdigest(string):
    return hashlib.sha256(string.encode("utf-8")).hexdigest()


class CodeforcesClient:
    def __init__(
            self,
            url,
            *,
            api_url=None,
        ):
        if url[-1] != "/":
            self._url = url + "/"
        else:
            self._url = url

        if api_url is None:
            self._api_url = self._url + "api/"
        else:
            self._api_url = api_url

        self._logged_in = False

        chrome_options = selenium.webdriver.ChromeOptions()
        chrome_options.add_argument("-incognito")
        self._client = selenium.webdriver.Chrome(options=chrome_options)

    def __del__(self):
        self._client.close()

    @property
    def logged_in(self):
        return self._logged_in

    def login(self, username, password):
        """Attempt to log in to the Codeforces website."""
        _LOGGER.info(
            "Attempting login to %s with username %s and password (sha256) %s",
            self._url,
            username,
            hashlib.sha256(password.encode("utf-8")).hexdigest(),
        )
        enter_url = self._url + "enter"
        self._client.get(enter_url)
        enter_form = self._client.find_element_by_id("enterForm")
        enter_form.find_element_by_id("handle").send_keys(username)
        enter_form.find_element_by_id("password").send_keys(password)
        enter_form.find_element_by_class_name("submit").click()
        self._logged_in = self._client.current_url == self._url

    def get_contests(self):
        _LOGGER.info("Getting problems via %s", self._api_url)
        response = urllib.request.urlopen(self._api_url + "problemset.problems")
        if response.status == 200:
            response_dict = json.load(response)
            if response_dict["status"] == "OK":
                contests = collections.defaultdict(dict)

                problems = response_dict["result"]["problems"]
                statistics = response_dict["result"]["problemStatistics"]

                assert len(problems) == len(statistics)

                for problem in problems:
                    contest_id = problem["contestId"]
                    index = problem["index"]
                    contests[contest_id][index] = problem

                for statistic in statistics:
                    contest_id = statistic["contestId"]
                    index = statistic["index"]
                    contests[contest_id][index]["solvedCount"] = statistic["solvedCount"]

                return contests
        raise ResponseError


class ContestItem(list):
    def __init__(self, contest_id, iterable):
        self.expanded = False
        self.contest_id = contest_id
        super().__init__(iterable)

    @staticmethod
    def key_contest_id(contest_item):
        return contest_item.contest_id


class ProblemItem:
    def __init__(self, problem_dict):
        self._problem_dict = problem_dict
        self.index = problem_dict["index"]
        self.name = problem_dict["name"]
        self.solved_count = problem_dict["solvedCount"]

    @staticmethod
    def key_index(problem_item):
        return problem_item.index

    @staticmethod
    def key_name(problem_item):
        return problem_item.name

    @staticmethod
    def key_solved_count(problem_item):
        return problem_item.solved_count


class Tool:
    def __init__(
            self,
            *,
            username,
            password,
            key,
            secret,
            codeforces_url,
        ):
        self._username = username
        self._password = password

        self._key = key
        self._secret = secret

        self._codeforces_client = CodeforcesClient(
            url=codeforces_url,
        )

        self._contests = list(
            ContestItem(
                contest_id,
                (ProblemItem(problem) for problem in problems.values())
            )
            for contest_id, problems
            in self._codeforces_client.get_contests().items()
        )
        self._contests.sort(key=ContestItem.key_contest_id)
        for contest_item in self._contests:
            contest_item.sort(key=ProblemItem.key_index)

        self._screen = None
        self._max_y = None
        self._max_x = None
        self._start = 0
        self._selected = (0, None)
        self._contest_format_string = None

    def __call__(self, screen):
        self._screen = screen
        self.main()

    def main(self):
        if self._screen is None:
            raise RuntimeError

        self._screen.clear()

        self._max_y, self._max_x = self._screen.getmaxyx()

        # TODO: What if screen is too small?
        self._contest_format_string = "     {}"
        self._contest_format_string += " "*(self._max_x - len(self._contest_format_string) - 1)
        self._problem_format_string = "       {}"
        self._problem_format_string += " "*(self._max_x - len(self._problem_format_string) - 1)

        y = 0
        contest_index = 0
        while y < self._max_y - 1:
            contest = self._contests[contest_index]
            contest.expanded = True
            self._place_contest(
                y,
                contest,
                selected=contest_index == 0,
            )
            y += 1
            problem_index = 0
            while y < self._max_y - 1 and problem_index < len(contest):
                self._place_problem(
                    y,
                    contest[problem_index],
                    last=problem_index + 1 == len(contest),
                )
                y += 1
                problem_index += 1
            contest_index += 1


        count = 0
        history = collections.deque(maxlen=3)  # TODO: Maybe use this for something again

        start_contest = (0, None)
        selected = 0
        contest_index = 0
        problem_index = None

        while True:
            _LOGGER.info("Main loop iterating w/ history = %s", history)

            c = self._screen.getch()

            _LOGGER.info("Got character c where ord(c) = %s", c)
            try:
                _LOGGER.info("Character c corresponds to ASCII character %s", repr(chr(c).encode('ascii').decode("ascii")))
            except UnicodeEncodeError:
                pass

            # Handle numbers, they modify count
            if c in range(ord("0"), ord("9") + 1):
                count = 10*count + (c - ord("0"))
                _LOGGER.info(
                    "Character is the number %s and the count becomes %s",
                    chr(c),
                    count,
                )
                history.appendleft(c)
                continue

            # The resizing is a bit of a special case
            if c == curses.KEY_RESIZE:
                #self._handle_resize()
                continue  # Don't care to add to history or destroy count
            # Move down some
            elif c in (ord("j"), curses.KEY_DOWN):
                #self._move(1 if count == 0 else count)
                self._screen.addstr(
                    selected,
                    0,
                    contest_format_string.format(self._contests[selected].contest_id),
                    curses.A_NORMAL,
                )
                selected += 1
                self._screen.addstr(
                    selected,
                    0,
                    contest_format_string.format(self._contests[selected].contest_id),
                    curses.A_REVERSE,
                )
            # Move up some
            elif c in (ord("k"), curses.KEY_UP):
                #self._move(-1 if count == 0 else -count)
                pass
            # Expand if possible
            elif c in (ord("l"), curses.KEY_RIGHT):
                if selected[1] is None:
                    pass
            # Contract if possible
            elif c in (ord("h"), curses.KEY_LEFT):
                if selected[1] is not None:
                    pass
            ## Move down heaps
            #elif c == curses.KEY_NPAGE:
            #    self._move(10 if count == 0 else 10*count)
            ## Move up heaps
            #elif c == curses.KEY_PPAGE:
            #    self._move(-10 if count == 0 else -10*count)
            ## Move to top
            #elif c == curses.KEY_HOME or c == ord("g") and history[0] == ord("g"):
            #    self._move(-math.inf)
            ## Move to bottom
            #elif c == curses.KEY_END or c == ord("G"):
            #    self._move(math.inf)  # TODO: Absolute moving?
            # Select problem to look at
            #elif c == curses.KEY_ENTER:
            #    pass
            # User breaks the main loop
            elif c == ord("q"):
                break
            # Unhandled, just add to history at end of loop
            else:
                pass

            count = 0
            history.appendleft(c)

    def _place_contest(self, y, contest, *, last=False, selected=False):
        color = curses.A_REVERSE if selected else curses.A_NORMAL
        self._screen.addstr(
            y,
            0,
            self._contest_format_string.format(contest.contest_id),
            color,
        )
        self._screen.addch(y, 1, curses.ACS_LTEE, color)
        self._screen.addch(y, 2, curses.ACS_HLINE, color)
        self._screen.addch(
            y,
            3,
            curses.ACS_TTEE if contest.expanded else curses.ACS_HLINE,
            color,
        )

    def _place_problem(self, y, problem, *, last=False, selected=False):
        _LOGGER.debug("Placing problem on line %s", y)
        color = curses.A_REVERSE if selected else curses.A_NORMAL
        self._screen.addstr(
            y,
            0,
            self._problem_format_string.format(problem.name),
            color,
        )
        self._screen.addch(y, 1, curses.ACS_VLINE, color)
        self._screen.addch(
            y,
            3,
            curses.ACS_LLCORNER if last else curses.ACS_LTEE,
            color,
        )
        self._screen.addch(y, 4, curses.ACS_HLINE, color)
        self._screen.addch(y, 5, curses.ACS_HLINE, color)

    def _handle_resize(self):
        self._max_y, self._max_x = self._screen.getmaxyx()
#
#    def _move(self, n=0):
#        if n == math.inf:
#            pass  # Move to top
#        elif n == -math.inf:
#            pass  # Move to bottom
#        elif n > 0:
#            pass  # Move down
#        elif n < 0:
#            pass  # Move up
#        else:
#            raise RuntimeError


def _main():
    """The main function for running this module as a script."""
    arg_parser = argparse.ArgumentParser()
    arg_parser.add_argument(
        "--version",
        action="store_true",
        help="show the version and exit",
    )
    arg_parser.add_argument(
        "-v",
        "--verbose",
        action="count",
        help="increase verbosity (unimplemented)",
    )
    arg_parser.add_argument(
        "-l",
        "--log",
        default=None,
        choices=_LOGGING_LEVELS,
        dest="logging_level",
        help="set logging level and log to temp file",
    )
    args = arg_parser.parse_args()

    if args.version:
        print("Codeforces Client", __version__)
        sys.exit(0)

    if args.logging_level is not None:
        # Log to temporary log file
        handler = logging.StreamHandler(
            tempfile.NamedTemporaryFile(
                mode="w",
                prefix="codeforces_client_{:03d}_".format(int(time.time())%1000),
                suffix=".log",
                delete=False,
            ),
        )
        handler.setFormatter(logging.Formatter("%(levelname)s - %(asctime)s - %(message)s"))
        _LOGGER.addHandler(handler)
        logging.getLogger().setLevel(args.logging_level)

    _LOGGER.info("Script run w/ sys.argv = %s", sys.argv)
    _LOGGER.info("Argparse yields %s, args")

    # Read config file

    config = configparser.ConfigParser()
    config.read(pathlib.Path.home()/".codeforces_client.cfg")
    config = config["Codeforces"]

    codeforces_url = config["url"]

    key = config["key"]
    secret = config["secret"]

    _LOGGER.info(
        "Got key from config w/ sha256: %s",
        _hexdigest(key),
    )
    _LOGGER.info(
        "Got secret from config w/ sha256: %s",
        _hexdigest(secret),
    )

    username = config["username"]
    password = config["password"]

    _LOGGER.info("Got username from config: %s", username)
    _LOGGER.info(
        "Got password from config w/ sha256: %s",
        _hexdigest(password),
    )

    # Wrap and call the Tool object with curses

    _LOGGER.info("Starting call of wrapped Tool instance")
    curses.wrapper(
        Tool(
            username=username,
            password=password,
            key=key,
            secret=secret,
            codeforces_url=codeforces_url,
        )
    )
    _LOGGER.info("Call to wrapped Tool instance has ended")


if __name__ == "__main__":
    _main()
