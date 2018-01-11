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
import subprocess
import sys
import tempfile
import time
import urllib.request

import selenium.webdriver


__version__ = "0.0.1"


_LOGGER_NAME = "cpc"
_LOGGER = logging.getLogger(_LOGGER_NAME)


class ResponseError(Exception):
    pass


def _hexdigest(string):
    return hashlib.sha256(string.encode("utf-8")).hexdigest()


class CursesUI:
    """The class that manages the curses window."""

    # TODO: Do checks that the methods are being used correctly

    Status = collections.namedtuple(
        "Status",
        [
            "index",
            "viewport_start",
        ],
    )

    def __init__(self, screen):
        self._screen = screen
        self._screen.clear()

        self._index = None  # The index of the currently selected item of the selection
        self._viewport_start = None  # The start of the viewport relative to the selection

        self._selection = None  # The non-empty list of strings to select from

        self._status_bar = ""  # The current string displayed in the status bar

    @property
    def status(self):
        current_status = self.Status(
            index=self._index,
            viewport_start=self._viewport_start,
        )
        return current_status

    def refresh(self):
        """Redraw the entire thing."""
        self._refresh_viewport()
        self._set_status_bar(self._status_bar)

    def set_selection(self, selection, *, status=None):
        self._selection = selection
        if status is None:
            self._index = 0
            self._viewport_start = 0
        else:
            if isinstance(status, self.Status):
                self._index = status.index
                self._viewport_start = status.viewport_start
                self._refresh_viewport()
            else:
                raise TypeError

    def set_status_bar(self, message):
        if isinstance(message, str):
            self._status_bar = message
            line = self._prepare_string(message)
            self._screen.addstr(y, 0, line, curses.A_DIM)
        else:
            raise TypeError

    def move_selection(self, n=1):
        # Calculate new index without going above or below the selection
        new_index = self._index + n
        if new_index < 0:
            new_index = 0
        elif new_index >= len(self._selection):
            new_index = len(self._selection) - 1

        # TODO: Either do a total or selective update of the selection
        #       Also move viewport, like, smartly-like

        self._refresh_viewport()

    def move_viewport(self, n=1):
        self._viewport_start += n
        self._refresh_viewport()

    def _prepare_string(self, string, padding=" "):
        """Truncate and pad a string so it is exactly the screens width."""
        _, max_x = self._screen.getmaxyx()
        return "{{{1}:<{0}.{0}}}".format(max_x - 1, padding).format(string)

    def _refresh_viewport(self):
        if self._index is None or self._viewport_start is None:
            return

        index = self._viewport_start
        max_y, max_x = self._screen.getmaxyx()
        for y in range(max_y - 1):
            if 0 <= index < len(self._selection):
                line = self._prepare_string(self._selection[index])
            else:
                line = " "*(max_x - 1)
            color = curses.A_REVERSE if index == self._index else curses.A_NORMAL
            self._screen.addstr(y, 0, line, color)
            index += 1


problem_format_string = "{0[contestId]}/{0[index]}: {0[name]} (solved: {0[solvedCount]})"


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
        _LOGGER.debug(
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
        _LOGGER.debug("Getting problems via %s", self._api_url)
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

    def load_problem(self, problem):
        url = "{}problemset/problem/{}/{}".format(
            self._url,
            problem.contest_id,
            problem.index,
        )
        _LOGGER.debug("Getting %s", url)
        if self._client.current_url != url:
            self._client.get(url)
            self._client.execute_script(
                "return arguments[0].scrollIntoView();",
                self._client.find_element_by_class_name("problem-statement"),
            )
            self._client.execute_script("window.scrollBy(-window.screenX, 0)")

    def submit_solution(self, problem, solution_path):
        if solution_path.exists():
            self.load_problem(problem)
            file_input = self._client.find_element_by_css_selector("input[name=sourceFile]")
            file_input.send_keys(str(solution_path))  # TODO: str necessary?
            submit_button = self._client.find_element_by_css_selector("input.submit")
            self._client.execute_script("arguments[0].click();", submit_button)


class Tool:
    def __init__(self, config):
        self._config = config

        # Store path
        self._path = pathlib.Path(config["cpc"]["path"]).expanduser()

        # Format string for the contest list
        self._contest_format_string = None
        self._problem_format_string = None

    def __call__(self, screen):
        self._screen = screen
        self._ui = CursesUI(screen)
        self.main()

    def main(self):
        if self._screen is None:
            raise RuntimeError

        count = 0
        history = collections.deque(maxlen=3)
        command = ""

        while True:
            _LOGGER.debug("Main loop iterating w/ history = %s", history)

            c = self._screen.getch()

            _LOGGER.debug("Got character c where ord(c) = %s", c)
            try:
                _LOGGER.debug(
                    "Character c corresponds to ASCII character %s",
                    repr(chr(c).encode('ascii').decode("ascii")),
                )
            except UnicodeEncodeError:
                pass

            # Handle numbers, they modify count
            if c in range(ord("0"), ord("9") + 1):
                count = 10*count + (c - ord("0"))
                _LOGGER.debug("This causes the count to become %s", count)
                history.appendleft(c)
                continue

            # The resizing is a bit of a special case
            if c == curses.KEY_RESIZE:
                self._handle_resize()
                continue  # Don't care to add to history or destroy count
            # Move down some
            elif c in (ord("j"), curses.KEY_DOWN):
                self._handle_move(1 if count == 0 else count)
            # Move up some
            elif c in (ord("k"), curses.KEY_UP):
                self._handle_move(-1 if count == 0 else -count)
            # Expand if possible
            elif c in (ord("l"), curses.KEY_RIGHT):
                contest_index, problem_index = self._selected
                contest = self._contests[contest_index]
                if problem_index is None:
                    contest.expanded = True
                    self._redraw()
                else:
                    problem = contest[problem_index]
                    self._codeforces_client.load_problem(problem)
            # Contract if possible
            elif c in (ord("h"), curses.KEY_LEFT):
                contest_index, problem_index = self._selected
                contest = self._contests[contest_index]
                if problem_index is not None:
                    # Move up to contest
                    self._handle_move(-problem_index - 1)
                    contest.expanded = False
                    self._redraw()
                elif contest.expanded:
                    contest.expanded = False
                    self._redraw()
            # Move down heaps
            elif c == curses.KEY_NPAGE:
                self._handle_move(10 if count == 0 else 10*count)
            # Move up heaps
            elif c == curses.KEY_PPAGE:
                self._handle_move(-10 if count == 0 else -10*count)
            # Move to top
            elif c == curses.KEY_HOME or c == ord("g") and history and history[0] == ord("g"):
                self._handle_move(-math.inf)
            # Move to bottom
            elif c == curses.KEY_END or c == ord("G"):
                self._handle_move(math.inf)
            # Select problem to look at
            elif c == ord("\n"):
                contest_index, problem_index = self._selected
                contest = self._contests[contest_index]
                if problem_index is not None:
                    problem = contest[problem_index]
                    self._codeforces_client.load_problem(problem)
                else:
                    contest.expanded = not contest.expanded
                    self._redraw()
            # User breaks the main loop
            # Move list down
            elif c == ord("\x05"):  # Ctrl+e
                pass
            # Move list up
            elif c == ord("\x19"):  # Ctrl+y
                pass
            # Edit solution
            elif c == ord("e"):
                contest_index, problem_index = self._selected
                if problem_index is not None:
                    problem = contest[problem_index]
                    problem_path = self._path/str(problem.contest_id)/str(problem.index)
                    problem_path.mkdir(parents=True, exist_ok=True)
                    solution_path = problem_path/"solution.py"
                    solution_path.touch(exist_ok=True)
                    subprocess.call(["vim", str(solution_path)])
                    self._handle_resize()  # To avoid residual effects
            # Submit solution
            elif c == ord("s"):
                contest_index, problem_index = self._selected
                if problem_index is not None:
                    problem = contest[problem_index]
                    solution_path = self._path/str(problem.contest_id)/str(problem.index)/"solution.py"
                    self._codeforces_client.submit_solution(problem, solution_path)
            elif c == ord("q"):
                break
            # Unhandled, just add to history at end of loop
            else:
                pass

            count = 0
            history.appendleft(c)


    def _codeforces(self):
        self._username = username
        self._password = password

        self._key = key
        self._secret = secret

        self._codeforces_client = CodeforcesClient(
            url=codeforces_url,
        )

        self._codeforces_client.login(username, password)

        # Store path, making sure it exists on file system as well
        self._path = path
        #path.mkdir(parents=True, exist_ok=True)

        # Get contests TODO: This is prime material for asyncio
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

        # Format string for the contest list
        self._contest_format_string = None
        self._problem_format_string = None




        codeforces_config = config["codeforces"]

        codeforces_url = codeforces_config["url"]

        key = codeforces_config["key"]
        secret = codeforces_config["secret"]

        _LOGGER.info(
            "Got key from config w/ sha256: %s",
            _hexdigest(key),
        )
        _LOGGER.info(
            "Got secret from config w/ sha256: %s",
            _hexdigest(secret),
        )

        username = codeforces_config["username"]
        password = codeforces_config["password"]

        _LOGGER.info("Got username from config: %s", username)
        _LOGGER.info(
            "Got password from config w/ sha256: %s",
            _hexdigest(password),
        )

        path = pathlib.Path(config["Local"]["path"]).expanduser()

        _LOGGER.info("Got contest directory %s from config", path)


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
        choices=logging._levelToName.values(),  # TODO: Can this be found elsewhere?
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
                prefix="cpc{:03d}_".format(int(time.time())%1000),
                suffix=".log",
                delete=False,
            ),
        )
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s - %(levelname)-8s - %(funcName)15.15s() - %(message)s"
            )
        )

        _LOGGER.addHandler(handler)
        logging.getLogger().setLevel(args.logging_level)

    _LOGGER.debug("Script run w/ sys.argv = %s", sys.argv)
    _LOGGER.debug("Argparse yields %s, args")

    # Read config file

    config = configparser.ConfigParser()
    config.read(pathlib.Path.home()/".competitive_programming_client.cfg")

    # Wrap and call the Tool object with curses

    _LOGGER.debug("Starting call of curses wrapped Tool instance")
    curses.wrapper(Tool(config))
    _LOGGER.debug("Call to curses wrapped Tool instance has ended")


if __name__ == "__main__":
    _main()
