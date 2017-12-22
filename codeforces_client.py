#!/usr/bin/env python3


import configparser
import curses
import json
import os
import re
import selenium.webdriver
import urllib.request
import enum


CODEFORCES_URL = "http://codeforces.com/"


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


#def get_problems():
#    response = requests.get(CODEFORCES_API_URL + "problemset.problems")
#    if response.status_code == 200:
#        response_dict = response.json()
#        if response_dict["status"] == "OK":
#            return_list = []
#            ids_to_indices = {}
#
#            problems = response_dict["result"]["problems"]
#            statistics = response_dict["result"]["problemStatistics"]
#
#            assert len(problems) == len(statistics)
#
#            for problem in problems:
#                contest_id = problem["contestId"]
#                index = problem["index"]
#                assert isinstance(contest_id, int) and 0 < contest_id < 99999
#                assert isinstance(index, str) and len(index) in range(1, 4), index
#                ids_to_indices[(contest_id, index)] = len(return_list)
#                return_list.append(problem)
#
#            for statistic in statistics:
#                contest_id = statistic["contestId"]
#                index = statistic["index"]
#                return_index = ids_to_indices[(contest_id, index)]
#                return_list[return_index]["solvedCount"] = statistic["solvedCount"]
#
#            assert all("solvedCount" in problem for problem in return_list)
#
#            return return_list
#    raise ResponseError
#
#
#class State(enum.Enum):
#    SELECTION = enum.auto()
#
#
#def problem_sort_ids(problem):
#    return (problem["contestId"], problem["index"])
#
#
#def problem_sort_solved(problem):
#    return problem["solvedCount"]
#
#
#class Tool:
#    def __init__(self):
#        self.screen = None
#        self.max_y = None
#        self.max_x = None
#        self.state = State.SELECTION
#        self.selected = 0  # Selected problem
#        self.relative = 0  # Relative position in the list
#        self.list_start = 0
#
#    def __call__(self, screen):
#        self.screen = screen
#        self.update_yx()
#        self.main()
#
#    def main(self):
#        if self.screen is None:
#            raise RuntimeError
#
#        self.screen.clear()
#        self.make_header()
#        self.screen.refresh()
#        run = True
#
#        problems = get_problems()
#        problems.sort(key=problem_sort_solved, reverse=True)
#
#        while run:
#            if state == State.SELECTION:
#                self.selection()
#
#    def selection(self):
#        while True:
#            c = self.screen.getch()
#            if c == ord("q"):
#                run = False
#                break
#            elif c == ord("G"):
#                selected = len(problems) - 1
#                selected_lo = len(problems) - self.max_y + 1
#                selected_hi = len(problems) - 1
#            elif c == curses.KEY_RESIZE:
#                self.update_yx()
#                selected_lo = selected
#                selected_hi = self.max_y - 2
#            elif c in [ord("j"), curses.KEY_DOWN]:
#                if selected == len(problems) - 1:
#                    continue
#                selected += 1
#                if selected > selected_hi:
#                    selected_lo += 1
#                    selected_hi += 1
#                    self.clear_list()
#            elif c in [ord("k"), curses.KEY_UP]:
#                if selected == 0:
#                    continue
#                selected -= 1
#                if selected < selected_lo:
#                    selected_lo -= 1
#                    selected_hi -= 1
#                    self.clear_list()
#
#
#            self.screen.refresh()
#
#    def update_yx(self):
#        self.max_y, self.max_x = self.screen.getmaxyx()
#
#    def update_list(self):
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
#    def make_header(self):
#        self.screen.addstr(0, 0, "       #  |  Solved count  |  Problem name", curses.A_UNDERLINE)
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
    #curses.wrapper(Tool())
    client = CodeforcesClient()
    client.login(USERNAME, PASSWORD)
else:
    raise ImportError("Don't import this for now")
