#!/usr/bin/env python3


#import asyncio  # TODO: Do things asynchronously and rigorously
import collections
import configparser
import curses
import hashlib
import json
import logging
import math
import pathlib
import subprocess
import sys
import tempfile
import time
import urllib.request

import selenium.webdriver


LOGGER_NAME = "codeforces_client"
LOGGER = logging.getLogger(LOGGER_NAME)


class ResponseError(Exception):
    pass


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
        LOGGER.info(
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
        LOGGER.info("Getting problems via %s", self._api_url)
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
            codeforces_url,
        ):
        self._username = username
        self._password = password

        self._screen = None
        self._max_y = None
        self._max_x = None
        self._selected = math.inf  # Selected line relative to the top of the list

        self._codeforces_client = CodeforcesClient(
            url=codeforces_url,
        )

        self.contests = list(
            ContestItem(
                contest_id,
                (ProblemItem(problem) for problem in problems.values())
            )
            for contest_id, problems
            in self._codeforces_client.get_contests().items()
        )
        self.contests.sort(key=ContestItem.key_contest_id)
        for contest_item in self.contests:
            contest_item.sort(key=ProblemItem.key_index)

    def __call__(self, screen):
        self._screen = screen
        self.main()

    def _handle_resize(self):
        self._max_y, self._max_x = self._screen.getmaxyx()

    def _move(self, n=0):
        if n == math.inf:
            pass  # Move to top
        elif n == -math.inf:
            pass  # Move to bottom
        elif n > 0:
            pass  # Move down
        elif n < 0:
            pass  # Move up
        else:
            raise RuntimeError

    def main(self):
        if self._screen is None:
            raise RuntimeError

        self._screen.clear()
        self._handle_resize()

        #subprocess.call(["vim", "codeforces_client.py"])

        count = 0
        history = collections.deque(maxlen=3)  # TODO: Maybe use this for something again

        while True:
            LOGGER.info("Main loop iterating w/ history = %s", history)

            c = self._screen.getch()

            LOGGER.info("Got character c where ord(c) = %s", c)

            # Handle numbers, they modify count
            if c in range(ord("0"), ord("9") + 1):
                count = 10*count + (c - ord("0"))
                LOGGER.info(
                    "Character is the number %s and the count becomes %s",
                    chr(c),
                    count,
                )
                history.appendleft(c)
                continue

            # The resizing is a bit of a special case
            if c == curses.KEY_RESIZE:
                self._handle_resize()
                continue  # Don't care to add to history or destroy count
            # Move down some
            elif c in (ord("j"), curses.KEY_DOWN):
                self._move(1 if count == 0 else count)
            # Move up some
            elif c in (ord("k"), curses.KEY_UP):
                self._move(-1 if count == 0 else -count)
            # Move down heaps
            elif c == curses.KEY_NPAGE:
                self._move(10 if count == 0 else 10*count)
            # Move up heaps
            elif c == curses.KEY_PPAGE:
                self._move(-10 if count == 0 else -10*count)
            # Move to top
            elif c == curses.KEY_HOME or c == ord("g") and history[0] == ord("g"):
                self._move(-math.inf)
            # Move to bottom
            elif c == curses.KEY_END or c == ord("G"):
                self._move(math.inf)  # TODO: Absolute moving?
            # User breaks the main loop
            elif c == ord("q"):
                break
            # Unhandled, just add to history at end of loop
            else:
                pass

            count = 0
            history.appendleft(c)

#    def _update_list(self):
#        for y, problem_index in enumerate(range(selected_lo, selected_hi + 1)):
#            problem = problems[problem_index]
#            problem_name = problem["name"]
#            id_index = str(problem["contestId"]) + problem["index"]
#            solved_count = problem["solvedCount"]
#            self._screen.addstr(
#                y + 1,
#                0,
#                "  {:>6}  |  {:>12}  |  {}".format(
#                    id_index,
#                    solved_count,
#                    problem_name,
#                ),
#                curses.A_REVERSE if problem_index == _selected else curses.A_NORMAL,
#            )


def _main(logging_level=None):
    # Init Logger for script

    LOGGER = logging.getLogger("codeforces_client")
    if "--LOG" in argv:
        # Log to temporary log file
        HANDLER = logging.StreamHandler(
            tempfile.NamedTemporaryFile(
                mode="w",
                prefix="codeforces_client_" + str(int(time.time())%1000) + "_",
                suffix=".log",
                delete=False,
            ),
        )
        HANDLER.setLevel(logging.DEBUG)
        HANDLER.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
        LOGGER.addHandler(HANDLER)
        LOGGER.setLevel(logging.DEBUG)

    LOGGER.info("Script run w/ sys.argv = %s", sys.argv)

    # Read config file

    CONFIG = configparser.ConfigParser()
    CONFIG.read(pathlib.Path.home()/".codeforces_client.cfg")
    CONFIG = CONFIG["Codeforces"]

    CODEFORCES_URL = CONFIG["url"]

    KEY = CONFIG["key"]
    SECRET = CONFIG["secret"]

    USERNAME = CONFIG["username"]
    PASSWORD = CONFIG["password"]

    LOGGER.info("Got username from config: %s", USERNAME)
    LOGGER.info(
        "Got password from config: %s (sha256)",
        hashlib.sha256(PASSWORD.encode("utf-8")).hexdigest(),
    )

    # Wrap and call the Tool object with curses

    LOGGER.info("Starting call of wrapped Tool instance")
    curses.wrapper(
        Tool(
            username=USERNAME,
            password=PASSWORD,
            codeforces_url=CODEFORCES_URL,
        )
    )
    LOGGER.info("Call to wrapped Tool instance has ended")


if __name__ == "__main__":
