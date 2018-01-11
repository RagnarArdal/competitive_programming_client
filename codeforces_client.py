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


_LOGGER_NAME = "codeforces_client"
_LOGGER = logging.getLogger(_LOGGER_NAME)


class ResponseError(Exception):
    pass


def _hexdigest(string):
    return hashlib.sha256(string.encode("utf-8")).hexdigest()


class CursesUI:
    """The class that manages the curses window."""
    def __init__(self, screen, ui_item):
        if not isinstance(ui_item, CursesUIItem):
            raise TypeError
        self._screen = screen
        self._stack = [ui_item]
        self.resize()

    def resize(self):
        pass

    def _handle_up(self, n=1):
        pass

    def _handle_down(self, n=1):
        pass

    def _handle_up_level(self, n=1):
        pass

    def _handle_down_level(self, n=1):
        pass

    def append(self, ui_item):
        """Append an item to the currently selected item."""
        if not isinstance(ui_item, CursesUIItem):
            raise TypeError
        raise NotImplementedError

    def extend(self, ui_items):
        """Append multiple items to the currently selected item."""
        ui_items = list(ui_items)
        if not all(isinstance(ui_item, CursesUIItem) for ui_item in ui_items):
            raise TypeError
        raise NotImplementedError


class CursesUIItem:
    """The base class for items of the curses window."""
    def __init__(
            self,
            iterable,
            *,
            obj=None,
        ):
        children = list(iterable)
        if not all(isinstance(item) for items in children):
            raise TypeError
        self.children = children
        self.obj = None
        self._selected = None

    def __str__(self):
        return str(self.obj)


class ContestItem(list):
    def __init__(self, contest_id, iterable):
        super().__init__(iterable)
        self.expanded = False
        self.contest_id = contest_id


class ProblemItem:
    def __init__(self, problem_dict):
        self._problem_dict = problem_dict
        self.contest_id = problem_dict["contestId"]
        self.index = problem_dict["index"]
        self.name = problem_dict["name"]
        self.solved_count = problem_dict["solvedCount"]


class CursesUILabel(CursesUIItem):
    def __init__(self, label, iterable):
        super().__init__(iterable)
        self.obj = label

    def __str__(self):
        return self.label


class CursesItemProblem(CursesItem):
    def __init__(
            self,
            iterable=(),
            problem_dict,
        ):
        super().__init__(iterable)
        self.obj = problem_dict

    def __str__(self):
        return "{0[contestId]}/{0[index]}: {0[name]} (solved: {0[solvedCount]})".format(self.obj)


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
    def __init__(
            self,
            *,
            username,
            password,
            key,
            secret,
            codeforces_url,
            path,
        ):
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

        self._screen = None
        self._max_y = None
        self._max_x = None

        # The start (and end) of the contest list, the selected item, and the relative position
        self._start = (0, None)  # The indices of the starting contest and problem
        self._last = None  # The indices of the last contest and problem (calculated on redraw call)
        self._selected = (0, None)  # The indices of the selected contest and problem
        self._relative = 0  # The relative (to the start) position of the selected contest or problem

        # Format string for the contest list
        self._contest_format_string = None
        self._problem_format_string = None

    def __call__(self, screen):
        self._screen = screen
        self.main()

    def _redraw(self, *, starting_at=0):
        """Redraw list starting at the specified line."""

        _LOGGER.debug("Total redraw from %s initiated", starting_at)

        y = starting_at
        if y == 0:
            contest_index = self._start[0]
            problem_index = self._start[1]
        else:
            # Skip until y reached
            raise NotImplementedError

        while True:
            if contest_index == len(self._contests):
                for y in range(y, self._max_y):
                    self._screen.addstr(y, 0, " "*(self._max_x - 1))
                break

            contest = self._contests[contest_index]

            if problem_index is None:
                self._place_contest(
                    y,
                    contest,
                    last=contest_index + 1 == len(self._contests),
                    selected=self._selected == (contest_index, None),
                )
                y += 1
                problem_index = 0

            if y == self._max_y:
                self._last = (contest_index, None)
                break

            if contest.expanded:
                while y < self._max_y and problem_index < len(contest):
                    self._place_problem(
                        y,
                        contest[problem_index],
                        last=problem_index + 1 == len(contest),
                        selected=self._selected == (contest_index, problem_index),
                        continues=contest_index != len(self._contests) - 1,
                    )
                    y += 1
                    problem_index += 1

                if y == self._max_y:
                    self._last = (contest_index, problem_index - 1)
                    break

            contest_index += 1
            problem_index = None

        # TODO: Replacing selected at this point would be faster?

    def _place_contest(self, y, contest, *, last=False, selected=False):
        _LOGGER.debug("Placing contest %s on line %s", contest.contest_id, y)
        color = curses.A_REVERSE if selected else curses.A_NORMAL
        self._screen.addstr(
            y,
            0,
            self._contest_format_string.format(contest.contest_id),
            color,
        )
        self._screen.addch(
            y,
            1,
            curses.ACS_LLCORNER if last else curses.ACS_LTEE,
            color,
        )
        self._screen.addch(
            y,
            2,
            curses.ACS_HLINE,
            color,
        )
        self._screen.addch(
            y,
            3,
            curses.ACS_TTEE if contest.expanded else curses.ACS_HLINE,
            color,
        )

    def _place_problem(self, y, problem, *, last=False, selected=False, continues=False):
        # TODO: Are they keyword-only arguments necessary? Probably not...
        #       Honestly, should the only argument be y?
        #       Perhaps this one and _place_contests() should be merged into one function
        _LOGGER.debug("Placing problem on line %s", y)
        color = curses.A_REVERSE if selected else curses.A_NORMAL
        self._screen.addstr(
            y,
            0,
            self._problem_format_string.format(str(problem.index) + ": " + problem.name),
            color,
        )
        if continues:
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

        # TODO: What if screen is too small? Also, just do better...
        self._contest_format_string = "     {:<" + str(self._max_x - 6) + "}"
        self._problem_format_string = "       {:<" + str(self._max_x - 8) + "}"

        self._start = self._selected
        self._relative = 0

        self._redraw()

    def _handle_move(self, n=0):
        _LOGGER.debug("Handling move %s", n)

        selection_swap = False
        new_selected = self._increment_index(self._selected, n)
        new_relative = self._relative + n

        _LOGGER.debug("Selected goes from %s to %s", self._selected, new_selected)

        if n > 0:
            # Move down (increment index)
            if new_relative >= self._max_y:
                new_relative = self._max_y - 1
                new_start = self._increment_index(new_selected, 1 - self._max_y)
            else:
                selection_swap = True
        elif n < 0:
            if new_relative < 0:
                new_relative = 0
                new_start = new_selected
            else:
                selection_swap = True
        else:
            return

        if not selection_swap:
            _LOGGER.debug(
                "Selection move causes screen to move; the start goes from %s to %s",
                self._start,
                new_start,
            )
            _LOGGER.debug(
                "This also means that relative index only becomes %s (max y - 1)",
                new_relative,
            )
            self._start = new_start
            self._selected = new_selected
            self._relative = new_relative
            self._redraw()
        else:
            # Just swap the selection
            # The new index and relative position have been calculated

            _LOGGER.debug("Relative index goes from %s to %s", self._relative, new_relative)
            _LOGGER.debug("Since screen doesn't move, just swap")

            # Start by making the old selection unselected
            old_contest_index, old_problem_index = self._selected
            old_contest = self._contests[old_contest_index]
            if old_problem_index is None:
                self._place_contest(
                    self._relative,
                    old_contest,
                    last=self._selected[0] == len(self._contests) - 1,
                )
            else:
                old_problem = old_contest[old_problem_index]
                self._place_problem(
                    self._relative,
                    old_problem,
                    last=old_problem_index == len(old_contest) - 1,
                    continues=old_contest_index != len(self._contests) - 1,
                )

            # Then make the new selection selected
            new_contest_index, new_problem_index = new_selected
            new_contest = self._contests[new_contest_index]
            if new_problem_index is None:
                self._place_contest(
                    new_relative,
                    new_contest,
                    last=new_selected[0] == len(self._contests) - 1,
                    selected=True,
                )
            else:
                new_problem = new_contest[new_problem_index]
                self._place_problem(
                    new_relative,
                    new_problem,
                    last=new_problem_index == len(new_contest) - 1,
                    selected=True,
                    continues=new_contest_index != len(self._contests) - 1,
                )

            # Update the variables for bookkeeping
            self._selected = new_selected
            self._relative = new_relative

    def _increment_index(self, index, n=1):
        """Increment list index by n (which can be negative) or as much as possible."""

        assert 0 <= index[0] < len(self._contests)
        assert index[1] is None or self._contests[index[0]].expanded

        _LOGGER.debug("Incrementing %s by %s", index, n)

        if n == math.inf or n == -math.inf:
            if n == math.inf:
                # Index of last contest or problem
                last_contest_index = len(self._contests) - 1
                last_contest = self._contests[-1]
                if last_contest.expanded:
                    result = (last_contest_index, len(last_contest) - 1)
                else:
                    result = (last_contest_index, None)
            else:
                # Index of first contest
                result = (0, None)

            _LOGGER.debug("Trivial case, index becomes %s", result)

            return result

        contest_index, problem_index = index

        if n > 0:
            # Make sure the index pair is that of a contest
            n += 0 if problem_index is None else problem_index + 1
            problem_index = None

            while n > 0:  # Go down
                # Increment the index
                contest = self._contests[contest_index]
                if contest_index == len(self._contests) - 1:
                    _LOGGER.debug("Last contest hit")
                    if contest.expanded:
                        problem_index = min(len(contest) - 1, n - 1)
                    break
                else:
                    if contest.expanded:
                        # Either able to skip over all problems, or not
                        if len(contest) < n:
                            # Skipped over all the problems of the contest on to the next contest
                            n -= len(contest) + 1
                            contest_index += 1
                        else:
                            # Not able to skip over all problems, so we have a problem index
                            problem_index = n - 1
                            n -= n  # Equivalent to break, but makes more sense
                    else:
                        n -= 1
                        contest_index += 1
        elif n < 0:  # Go up
            # Similar to the incrementing

            n = -n
            n -= 0 if problem_index is None else problem_index + 1
            problem_index = None

            while contest_index != 0 and n > 0:
                contest_index -= 1
                contest = self._contests[contest_index]
                n -= len(contest) + 1 if contest.expanded else 1

            if n < 0:
                problem_index = -n - 1
        else:
            _LOGGER.debug("Trivial or unknown case, returning same index")
            return index

        result = (contest_index, problem_index)

        _LOGGER.debug("The result of the calculations is %s", result)

        return result

    def _compare_indices(self, a, b):
        """Return -1 if a < b, 0 if a == b, or 1 if a > b."""
        if a[0] == b[0]:
            if a[1] == b[1]:
                return 0
            elif a[1] is None:
                return -1
            else:
                return 1
        elif a[0] > b[0]:
            return 1
        else:
            return -1

    def main(self):
        if self._screen is None:
            raise RuntimeError

        self._screen.clear()
        self._handle_resize()

        count = 0
        history = collections.deque(maxlen=3)

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
                prefix="codeforces_client_{:03d}_".format(int(time.time())%1000),
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
    config.read(pathlib.Path.home()/".codeforces_client.cfg")
    codeforces_config = config["Codeforces"]

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

    # Wrap and call the Tool object with curses

    _LOGGER.debug("Starting call of wrapped Tool instance")
    curses.wrapper(
        Tool(
            username=username,
            password=password,
            key=key,
            secret=secret,
            codeforces_url=codeforces_url,
            path=path,
        )
    )
    _LOGGER.debug("Call to wrapped Tool instance has ended")


if __name__ == "__main__":
    _main()
