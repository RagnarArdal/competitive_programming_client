#!/usr/bin/env python3


import abc
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


EDIT = ":edit"
TEST = ":test"
COMPILE = ":compile"
SUBMIT = ":submit"


#
# Programming language classes
#


class ProgrammingLanguage(metaclass=abc.ABCMeta):
    """A base class for classes containing everything pertaining a programming language."""
    @property
    @abc.abstractmethod
    def name(self):
        """The simple version of the name of the programming language."""
        pass

    @property
    @abc.abstractmethod
    def extension(self):
        """The file extension of a file written in the programming language."""
        pass

    @abc.abstractmethod
    def compile(self, source_file_path):
        """Compile file and return the compiled file's path."""
        _LOGGER.debug("Compiling %s", source_file_path)

    @abc.abstractmethod
    def run(
            self,
            program_file_path,
            input_stream,
            output_stream,
        ):
        """Run a compiled program with input and output streams."""
        pass


class Python(ProgrammingLanguage):
    """The Python programming language."""
    name = "python"
    extension = ".py"

    def compile(self, source_file_path):
        return source_file_path

    def run(
            self,
            program_file_path,
            input_stream=sys.stdin,
            output_stream=sys.stdout,
        ):
        return subprocess.call(
            ["python", program_file_path],
            stdin=input_stream,
            stdout=output_stream,
        )


class CPP(ProgrammingLanguage):
    """The c++ programming language."""
    name = "c++"
    extension = ".cpp"

    def compile(self, source_file_path):
        super().compile(source_file_path)
        out_file_path = source_file_path.with_suffix(".out")
        _LOGGER.debug("The output file is %s", out_file_path)
        return_code = subprocess.call(["g++", source_file_path, "-o", out_file_path])
        _LOGGER.debug("Return code of compilation is %s", return_code)
        return out_file_path

    def run(
            self,
            program_file_path,
            input_stream=sys.stdin,
            output_stream=sys.stdout,
        ):
        return subprocess.call(
            [program_file_path],
            stdin=input_stream,
            stdout=output_stream,
        )


class Java(ProgrammingLanguage):
    """The Java programming language."""
    name = "java"
    extension = ".java"

    def compile(self, source_file_path):
        super().compile(source_file_path)
        directory = source_file_path.parent
        _LOGGER.debug("Directory is %s", directory)
        return_code = subprocess.call(["javac", source_file_path, "-d", directory])
        _LOGGER.debug("Return code of compilation is %s", return_code)
        out_file_path = source_file_path.with_suffix(".class")
        _LOGGER.debug("The output file should be %s", out_file_path)
        return out_file_path

    def run(
            self,
            program_file_path,
            input_stream=sys.stdin,
            output_stream=sys.stdout,
        ):
        return subprocess.call(
            ["java", program_file_path],
            stdin=input_stream,
            stdout=output_stream,
        )


#
# UI class
#


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
        curses.curs_set(False)  # Hide cursor
        self._screen = screen
        self._screen.clear()

        self._index = None  # The index of the currently selected item of the selection
        self._viewport_start = None  # The start of the viewport relative to the selection

        self._selection = None  # The non-empty list of strings to select from

        self._status_bar = None  # The current string displayed in the status bar

        self.set_status_bar("")

    @property
    def status(self):
        """Return the status tuple of the UI."""
        current_status = self.Status(
            index=self._index,
            viewport_start=self._viewport_start,
        )
        return current_status

    def refresh(self):
        """Redraw the entire thing."""
        self._screen.clear()
        self._refresh_viewport()
        self.set_status_bar(self._status_bar)
        self._screen.refresh()

    def set_loading(self):
        clear_line = self._prepare_string("")
        max_y = self._screen.getmaxyx()[0]
        for y in range(max_y - 1):
            if y == 0:
                self._screen.addstr(
                    y,
                    0,
                    self._prepare_string("Loading..."),
                    curses.A_BLINK,  # pylint: disable=undefined-variable
                )
            else:
                self._screen.addstr(
                    y,
                    0,
                    clear_line,
                )
        self._screen.refresh()

    def set_selection(self, selection, *, status=None):
        """Set the list of strings to display."""
        self._selection = selection
        if status is None:
            self._index = 0
            self._viewport_start = 0
        else:
            if isinstance(status, self.Status):
                self._index = status.index
                self._viewport_start = status.viewport_start
            else:
                raise TypeError
        self._refresh_viewport()

    def set_status_bar(self, message):
        """Set the left aligned message of the status bar on the bottom."""
        max_y = self._screen.getmaxyx()[0]
        if isinstance(message, str) and max_y > 0:
            self._status_bar = message
            line = self._prepare_string(message)
            self._screen.addstr(max_y - 1, 0, line, curses.A_BOLD)  # pylint: disable=undefined-variable
        else:
            raise TypeError

    def move_selection(self, n=1):  # pylint: disable=invalid-name
        """Change the selected item of the selection by moving up or down."""
        # Calculate new index without going above or below the selection
        new_index = self._index + n
        if new_index < 0:
            new_index = 0
        elif new_index >= len(self._selection):
            new_index = len(self._selection) - 1

        # TODO: Either do a total or selective update of the selection
        #       Also move viewport, like, smartly-like

        max_y = self._screen.getmaxyx()[0]
        if new_index < self._viewport_start:
            # Moved up beyond viewport
            self._viewport_start = new_index
        elif new_index >= self._viewport_start + max_y - 1:
            # Moved down beyond viewport
            # viewport_start + max_y is the status bar
            self._viewport_start = new_index - max_y + 2

        self._index = new_index
        self._refresh_viewport()

    def move_viewport(self, n=1):  # pylint: disable=invalid-name
        """Change which part of the selection is visible by moving up or down."""
        self._viewport_start += n
        self._refresh_viewport()

    def _prepare_string(self, string, padding=" "):
        """Truncate and pad a string so it is exactly the screens width."""
        _, max_x = self._screen.getmaxyx()
        return "{{!s:{1}<{0}.{0}}}".format(max_x - 1, padding).format(string)

    def _refresh_viewport(self):
        """Print the selection anew."""
        index = self._viewport_start
        max_y, max_x = self._screen.getmaxyx()
        for y in range(max_y - 1):  # pylint: disable=invalid-name
            if 0 <= index < len(self._selection):
                line = self._prepare_string(self._selection[index])
            else:
                line = " "*(max_x - 1)
            color = curses.A_REVERSE if index == self._index else curses.A_NORMAL
            self._screen.addstr(y, 0, line, color)
            index += 1


#
# The client classes
#


class ProblemContainer(list):
    """The class for containing problems."""
    def __init__(
            self,
            iterable=(),
            *,
            name="",
        ):
        super().__init__(iterable)
        self.name = name
        self.status = None  # A Curses UI status

    def __str__(self):
        return "{}".format(self.name)


class Problem:
    """The wrapper class for problem dictionaries."""
    # TODO: There must be a better way to do this
    def __init__(
            self,
            obj,
            fmt,
        ):
        self.obj = obj
        self.fmt = fmt

    def __str__(self):
        return self.fmt.format(self.obj)

    @property
    def path(self):
        """Return the preferred relative path of the problem."""
        return pathlib.Path(str(self.obj["contestId"]))/self.obj["index"]


class CPClient(metaclass=abc.ABCMeta):
    @property
    @abc.abstractmethod
    def name(self):
        """The simple name of the server this client speaks to."""
        pass

    @abc.abstractmethod
    def get_catalogue(self):
        """Return the catalogue of problems."""
        _LOGGER.debug("Getting catalogue of %s", self.name)

    @abc.abstractmethod
    def get_tests(self, problem):
        """Return some form of problem tests"""
        _LOGGER.debug("Getting tests from %s", self.name)

    @abc.abstractmethod
    def load_problem(self, problem):
        """Load problem, whatever that entails.

        Applicable e.g. for Codeforces, where we display problem in browser.
        """
        _LOGGER.debug("Loading %s problem: %s", self.name, problem)

    @abc.abstractmethod
    def submit_solution(self, problem, solution_path):
        """Submit a solution to the server."""
        _LOGGER.debug("Submitting solution to %s to %s", problem, self.name)


class CodeforcesClient(CPClient):
    name = "Codeforces"

    def __init__(self, config):
        config = config[self.name]

        self._username = config["username"]
        self._password = config["password"]

        _LOGGER.info("Got username from config: %s", self._username)
        _LOGGER.info("Got password from config w/ sha256: %s", _hexdigest(self._password))

        self._key = config["key"]
        self._secret = config["secret"]

        _LOGGER.info("Got key from config w/ sha256: %s", _hexdigest(self._key))
        _LOGGER.info("Got secret from config w/ sha256: %s", _hexdigest(self._secret))

        url = config["url"]
        if url[-1] != "/":
            self._url = url + "/"
        else:
            self._url = url

        api_url = None  # TODO
        if api_url is None:
            self._api_url = self._url + "api/"
        else:
            self._api_url = api_url

        _LOGGER.debug("%s api_url = %s", self, self._api_url)

        self._client = None
        self._logged_in = False

    def __del__(self):
        if self._client is not None:
            # Close chrome
            _LOGGER.debug("%s closing chrome", self)
            self._client.close()

    @property
    def client(self):
        if self._client is None:
            _LOGGER.debug("%s firing up chrome", self)
            chrome_options = selenium.webdriver.ChromeOptions()
            chrome_options.add_argument("-incognito")
            self._client = selenium.webdriver.Chrome(options=chrome_options)
        return self._client

    def _log_in(self):
        """Attempt to log in to the Codeforces website."""
        if not self._logged_in:
            enter_url = self._url + "enter"
            self.client.get(enter_url)
            enter_form = self.client.find_element_by_id("enterForm")
            enter_form.find_element_by_id("handle").send_keys(self._username)
            enter_form.find_element_by_id("password").send_keys(self._password)
            enter_url = self.client.current_url
            enter_form.find_element_by_class_name("submit").click()
            while self.client.current_url == enter_url:
                pass  # TODO: This loop is ridiculous, do something else to wait
            self._logged_in = self._client.current_url == self._url

    def get_catalogue(self):
        super().get_catalogue()
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

                catalogue = ProblemContainer(
                    (
                        ProblemContainer(
                            (
                                Problem(
                                    problem,
                                    "{0[contestId]}/{0[index]}: {0[name]} (solved={0[solvedCount]})",
                                )
                                for problem in problems.values()),
                            name=contest_id,
                        )
                        for contest_id, problems in contests.items()
                    ),
                    name=self.name,
                )

                catalogue.sort(key=lambda contest: contest.name)
                #for contest in catalogue:
                #    contest.sort(key=lambda problem: problem.obj["index"])

                return catalogue
        raise ResponseError

    def load_problem(self, problem):
        super().load_problem(problem)
        url = "{}problemset/problem/{}/{}".format(
            self._url,
            problem.obj["contestId"],
            problem.obj["index"],
        )
        _LOGGER.debug("Getting %s", url)
        if self.client.current_url != url:
            self.client.get(url)
            self.client.execute_script(
                "return arguments[0].scrollIntoView();",
                self.client.find_element_by_class_name("problem-statement"),
            )
            self.client.execute_script("window.scrollBy(-window.screenX, 0)")

    def submit_solution(self, problem, solution_path):
        super().submit_solution(problem, solution_path)
        self._log_in()
        if solution_path.exists():
            self.load_problem(problem)
            file_input = self.client.find_element_by_css_selector("input[name=sourceFile]")
            file_input.send_keys(str(solution_path))  # TODO: str necessary?
            submit_button = self.client.find_element_by_css_selector("input.submit")
            self.client.execute_script("arguments[0].click();", submit_button)

    def get_tests(self, problem):
        # TODO: Can easily be done without selenium
        self._load_problem(problem)
        raise NotImplementedError


#
# The command line tool class
#


class Tool:
    def __init__(self, config):
        self._config = config

        # Store path
        self._path = pathlib.Path(config["cpc"]["path"]).expanduser()

        # Store language to use
        language_preferred = config["cpc"]["language"]
        for programming_language in ProgrammingLanguage.__subclasses__():
            if programming_language.name.startswith(language_preferred):
                self._language = programming_language
                break
        else:
            raise RuntimeError("Lacking support for preferred language")

        self._client = None

        self._screen = None
        self._ui = None

        self._stack = []
        self._current_selection = ProblemContainer(
            (
                ProblemContainer(name=CodeforcesClient.name),
                ProblemContainer(name="Kattis (Incoming)"),
                ProblemContainer(name="Project Euler (Incoming)"),
                ProblemContainer(name="ICPC (Incoming)"),
            ),
        )

    def __call__(self, screen):
        self._screen = screen
        self._ui = CursesUI(screen)
        self._ui.set_selection(self._current_selection)
        self.main()
        screen.clear()

    def main(self):

        count = 0
        history = collections.deque(maxlen=3)
        command = ""
        status_bar = None

        while True:
            _LOGGER.debug("Main loop iterating w/ history = %s", history)

            c = self._screen.getch()  # pylint: disable=invalid-name
            status_bar = chr(c)  # Default status bar string
            add_to_history = True

            _LOGGER.debug(
                "Got character c = %s; i.e., chr(c) = %s",
                c,
                repr(status_bar),  # status_bar starts off as chr(c)
            )

            if command:
                if c == ord("\n"):
                    command = command.split()
                    if "q" in command[0] and set(command[0]).issubset(":wqa!"):
                        break  # TODO: This has to be done smarter
                    status = self._ui.status
                    selected = self._current_selection[status.index]
                    status_bar = self._handle_command(command, selected)
                    command = ""
                elif c == curses.KEY_BACKSPACE:
                    command = command[:len(command) - 1]
                    status_bar = command
                else:
                    command += chr(c)
                    status_bar = command

                self._ui.set_status_bar(status_bar)
                continue

            # Handle numbers, they modify count
            if c in range(ord("0"), ord("9") + 1):
                count = 10*count + (c - ord("0"))
                _LOGGER.debug("This causes the count to become %s", count)
                continue

            # The resizing is a bit of a special case
            if c == curses.KEY_RESIZE:
                self._ui.refresh()
                continue  # Don't care to add to history or destroy count
            # Move down some
            elif c in (ord("j"), curses.KEY_DOWN):
                self._ui.move_selection(1 if count == 0 else count)
            # Move up some
            elif c in (ord("k"), curses.KEY_UP):
                self._ui.move_selection(-1 if count == 0 else -count)
            # Move down heaps
            elif c == curses.KEY_NPAGE:
                self._ui.move_selection(10 if count == 0 else 10*count)
            # Move up heaps
            elif c == curses.KEY_PPAGE:
                self._ui.move_selection(-10 if count == 0 else -10*count)
            # Move to top
            elif c == curses.KEY_HOME:
                self._ui.move_selection(-math.inf)
            # Move to top
            elif c == ord("g") and history and history[0] == ord("g"):
                self._ui.move_selection(-math.inf)
                history.clear()
                add_to_history = False
                status_bar = "gg"
            # Move to bottom
            elif c == curses.KEY_END or c == ord("G"):
                self._ui.move_selection(math.inf)
            # Move list down
            elif c == ord("\x05"):  # Ctrl+e
                self._ui.move_viewport(1 if count == 0 else count)
            # Move list up
            elif c == ord("\x19"):  # Ctrl+y
                self._ui.move_viewport(-1 if count == 0 else -count)
            # User starts a command
            elif c == ord(":"):
                command = status_bar  # ":"
                history.clear()  # History prior to the command has no effect
                add_to_history = False
            # Go down level or edit
            elif c in (ord("l"), curses.KEY_RIGHT, ord("\n")):
                self._go_down_level()
            # Go up level
            elif c in (ord("h"), curses.KEY_LEFT, curses.KEY_BACKSPACE):
                self._go_up_level()
            # No special handling
            else:
                pass

            # Beyond this point we do three things:
            #   - Set count back to zero
            #   - Set the status bar of the UI
            #   - Add to the history (unless told otherwise)

            count = 0
            try:
                self._ui.set_status_bar(status_bar)
            except curses.error:
                self._ui.set_status_bar("")
            if add_to_history:
                history.appendleft(c)

    def _get_paths(self, problem):
        """Return problem path and solution path."""
        problem_path = self._path/self._client.name/problem.path
        problem_path.mkdir(parents=True, exist_ok=True)
        solution_file_name = "solution" + self._language.extension
        solution_path = problem_path/solution_file_name
        return problem_path, solution_path

    #
    # The rest of the methods are mostly regarding the handling of commands
    #

    def _handle_command(self, command, selected):

        _LOGGER.debug("Handling command sequence %s", command)

        status_bar = ""
        non_command = False

        # All commands are in the context of a problem right now TODO
        if not isinstance(selected, Problem):
            _LOGGER.debug("%s is not a Problem, so do nothing")
            non_command = True
        # The edit command
        elif EDIT.startswith(command[0]):
            if len(command) == 1:
                self._edit(selected)
            else:
                non_command = True
        # The submit command
        elif SUBMIT.startswith(command[0]):
            if len(command) == 1:
                self._submit(selected)
            else:
                non_command = True
        # The compile command
        elif COMPILE.startswith(command[0]):
            if len(command) == 1:
                self._compile(selected)
            else:
                non_command = True
        # The test command
        elif TEST.startswith(command[0]):
            non_command = not self._test(command, selected)
        # Catchall
        else:
            non_command = True

        if non_command:
            status_bar = "Not a command"

        return status_bar

    def _go_up_level(self):
        if self._stack:
            self._current_selection.status = self._ui.status
            selection = self._stack.pop()
            self._current_selection = selection
            self._ui.set_selection(selection, status=selection.status)
            if not self._stack:
                self._client = None

    def _go_down_level(self):
        status = self._ui.status
        selected = self._current_selection[status.index]

        _LOGGER.debug("selected = %s", selected)

        if isinstance(selected, ProblemContainer):
            _LOGGER.debug("Move into container")
            if not self._stack:
                _LOGGER.debug("Container is representative of server")
                for client_class in CPClient.__subclasses__():
                    if selected.name == client_class.name:
                        self._client = client_class(self._config)
                        _LOGGER.debug("Instantiated client %s", self._client)
                        break
                else:
                    _LOGGER.debug("Unable to find an appropriate client Class")
                    return
                if not selected:
                    # Catalogue not yet loaded
                    self._ui.set_loading()
                    selected = self._client.get_catalogue()
                self._current_selection[status.index] = selected
            self._current_selection.status = status
            self._stack.append(self._current_selection)
            self._current_selection = selected
            self._ui.set_selection(selected, status=selected.status)
        elif isinstance(selected, Problem):
            _LOGGER.debug("Load problem")
            self._client.load_problem(selected)
        else:
            _LOGGER.warning("Unexpected, do nothing")

    def _edit(self, problem):
        _, solution_path = self._get_paths(problem)
        subprocess.call(["vim", str(solution_path)])
        self._ui.refresh()  # To avoid residual effects

    def _submit(self, problem):
        _, solution_path = self._get_paths(problem)
        self._client.submit_solution(problem, solution_path)

    def _test(self, command, problem):
        if len(command) == 1:
            _, solution_path = self._get_paths(problem)
            compiled_file = self._language.compile(solution_path)
            # TODO: Implement testing
        elif len(command) == 2:
            if "new".startswith(command[1]):
                pass  # Create new test files
            elif "load".startswith(command[1]):
                pass  # Load tests from server
            else:
                pass
        return False

    def _compile(self, problem):
        _, solution_path = self._get_paths(problem)
        return self._language.compile(solution_path)


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
        choices=logging._levelToName.values(),  # pylint: disable=protected-access
        dest="logging_level",
        help="set logging level and log to temp file",
    )
    args = arg_parser.parse_args()

    if args.version:
        print("Competitive Programming Client", __version__)
        sys.exit(0)

    if args.logging_level is not None:
        # Log to temporary log file
        handler = logging.StreamHandler(
            tempfile.NamedTemporaryFile(
                mode="w",
                prefix="cpc_{:03d}_".format(int(time.time())%1000),
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
