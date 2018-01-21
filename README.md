# cpc: Competitive Programming Client

Competitive Programming Client (`cpc`) is a part-console part-webbrowser client to do competitive programming.
It is written in the Python 3 programming language and cross-platform (MAC, Windows, Linux, ...).


## Setup

### Step 1: Script

Download the `competitive_programming_client.py`,
from now on referred to as `cpc` because we recommend making that alias for it.

### Step 2: Configuration

Download the `.competitive_programming_client.cfg` configuration file and put it in your home directory.
Open the file up and set up your credentials.

### Step 3: Requirements (never too late)

`cpc` requires:
* Python 3
* Chrome
* The `selenium` Python 3 library
	* In most situations, run `pip install selenium` to install it


## Usage

Use standard `vim` controls to move around.

Find the problem you want to tackle and run any of the commands:
* `:edit`: Edit your solution
* `:test`: NOT YET IMPLEMENTED
* `:submit`: Submit your solution
* `:compile`: Compile your solution


## TODO

Some outstanding items:

* Add competitive programming servers
	* Codeforces
		* Competition support
		* Shortcut to friend list standings during competitions
	* ICPC
	* Kattis
	* Project Euler
* Use `asyncio` for working asynchronously with the servers
* Support more languages
	* Java
	* C++
* Support for editors that aren't vim
* Have a default template for each language
* Fetch and run tests locally (":test", perhaps)
* Shortcut for creating tests (":test create", perhaps)
* Different sorting
* Had trouble detecting ESC keypress


## Personal learning outcomes

Familiarity with the following python libraries:

* Standard libraries
	* `argparse`
	* `configparser`
	* `curses`
	* `logging`
	* `pathlib`
	* `subprocess`
	* `tempfile`
* Third-party
	* `selenium`
