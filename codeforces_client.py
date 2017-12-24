#!/usr/bin/env python3


import collections
import configparser
import curses
import json
import math
import os
import subprocess
import urllib.request

import selenium.webdriver


CODEFORCES_URL = "http://codeforces.com/"  # TODO: Put in configuration file?


class ResponseError(Exception):
    pass


class CodeforcesClient:
    def __init__(
            self,
            codeforces_url=CODEFORCES_URL,
            codeforces_api_url=None,
        ):
        if codeforces_url[-1] != "/":
            self._codeforces_url = codeforces_url + "/"
        else:
            self._codeforces_url = codeforces_url

        if codeforces_api_url is None:
            self._codeforces_api_url = codeforces_url + "api/"
        else:
            self._codeforces_api_url = codeforces_api_url

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
        self._client.get(self._codeforces_url + "enter")
        enter_form = self._client.find_element_by_id("enterForm")
        enter_form.find_element_by_id("handle").send_keys(username)
        enter_form.find_element_by_id("password").send_keys(password)
        enter_form.find_element_by_class_name("submit").click()
        self._logged_in = self._client.current_url == self._codeforces_url

    def get_contests(self):
        response = urllib.request.urlopen(self._codeforces_api_url + "problemset.problems")
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
        ):
        self.username = username
        self.password = password

        self.screen = None
        self.max_y = None
        self.max_x = None
        self.selected = 0  # Selected problem or contest

        self._codeforces_client = CodeforcesClient()

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
        self.screen = screen
        self.main()

    def _handle_resize(self):
        self.max_y, self.max_x = self.screen.getmaxyx()

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
        if self.screen is None:
            raise RuntimeError

        self.screen.clear()
        self._handle_resize()

        #subprocess.call(["vim", "codeforces_client.py"])

        count = 0
        history = collections.deque(maxlen=10)

        while True:
            c = self.screen.getch()

            # Handle numbers, they modify count
            if c in range(ord("0"), ord("9") + 1):
                count = 10*count + int(c)
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
            # Move to bottom, or any line
            elif c == ord("G"):
                if count == 0:
                    self._move(math.inf)
                else:
                    self._move(-math.inf)
                    self._move(count)
            # Move to bottom
            elif c == curses.KEY_END:
                self._move(math.inf)
            # User breaks the main loop
            elif c == ord("q"):
                break
            # Unhandled, just added to history
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
#            self.screen.addstr(
#                y + 1,
#                0,
#                "  {:>6}  |  {:>12}  |  {}".format(
#                    id_index,
#                    solved_count,
#                    problem_name,
#                ),
#                curses.A_REVERSE if problem_index == selected else curses.A_NORMAL,
#            )
#
#    def clear_list(self):
#        for y in range(1, self.max_y):
#            self.screen.addstr(y, 0, " "*(self.max_x - 3))  # TODO: Betterer


if __name__ == "__main__":
    FILE_PATH = os.path.dirname(os.path.realpath(__file__))

    CONFIG = configparser.ConfigParser()
    CONFIG.read(os.path.join(FILE_PATH, ".codeforces_client.cfg"))

    KEY = CONFIG["Codeforces"]["key"]
    SECRET = CONFIG["Codeforces"]["secret"]

    USERNAME = CONFIG["Codeforces"]["username"]
    PASSWORD = CONFIG["Codeforces"]["password"]

    curses.wrapper(
        Tool(
            username=USERNAME,
            password=PASSWORD,
        )
    )
else:
    raise ImportError("Don't import this for now")
