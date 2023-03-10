#!/usr/bin/env python3

import datetime
import logging
import pathlib

from selenium.webdriver import Chrome, ChromeOptions, DesiredCapabilities
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import import_cdp
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions
from selenium.webdriver.support.ui import WebDriverWait

import util

STARS = 400
LASTCOMMIT = 2 * 365 * 24 * 3600  # 2 years * 365 days * 24 hours * 3600 seconds
INDENT_SIZE = 4
INDENT = " " * INDENT_SIZE
HEADLESS = True

RESULT = "fetch-repo.txt"
CANDIDATES = "lua/colorswitch/candidates.lua"


def duplicate_color(repos, r):
    def delimiter_position(url):
        assert isinstance(url, str)
        if url.endswith(".vim"):
            return url.find(".vim")
        if url.endswith(".nvim"):
            return url.find(".nvim")
        if url.endswith("-vim"):
            return url.find("-vim")
        if url.endswith("-nvim"):
            return url.find("-nvim")
        return -1

    def same_color(r1, r2):
        r1 = r1.url.split("/")[-1]
        r2 = r2.url.split("/")[-1]
        if r1 == r2 and (
            r1 != "vim"
            and r1 != "nvim"
            and r1 != "neovim"
            and r2 != "vim"
            and r2 != "nvim"
            and r2 != "neovim"
        ):
            return True
        pos1 = delimiter_position(r1)
        pos2 = delimiter_position(r2)
        if pos1 <= 0 or pos2 <= 0:
            return False
        base1 = r1[:pos1]
        base2 = r2[:pos2]
        return base1 == base2

    for repo in repos:
        if repo == r or same_color(repo, r):
            return repo
    return None


def plugin_blacklist(repo):
    if repo.url.find("rafi/awesome-vim-colorschemes") >= 0:
        return True
    if repo.url.find("sonph/onehalf") >= 0:
        return True
    if repo.url.find("mini.nvim#minischeme") >= 0:
        return True
    if repo.url.find("olimorris/onedarkpro.nvim") >= 0:
        return True
    return False


def find_element(driver, xpath):
    WebDriverWait(driver, 30).until(
        expected_conditions.presence_of_element_located((By.XPATH, xpath))
    )
    return driver.find_element(By.XPATH, xpath)


def find_elements(driver, xpath):
    WebDriverWait(driver, 30).until(
        expected_conditions.presence_of_element_located((By.XPATH, xpath))
    )
    return driver.find_elements(By.XPATH, xpath)


def make_driver():
    options = ChromeOptions()
    if HEADLESS:
        options.add_argument("--headless")
    options.add_argument("--no-sandbox")
    options.add_argument("--single-process")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--allow-running-insecure-content")
    options.add_argument("--ignore-certificate-errors")
    options.add_argument("--allow-insecure-localhost")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("useAutomationExtension", False)
    options.add_experimental_option("excludeSwitches", ["enable-automation"])

    desired_capabilities = DesiredCapabilities().CHROME.copy()
    # desired_capabilities["pageLoadStrategy"] = "eager"
    desired_capabilities["acceptInsecureCerts"] = True

    return Chrome(options=options, desired_capabilities=desired_capabilities)


class ColorPlugin:
    def __init__(self, url, stars, last_update):
        assert isinstance(url, str)
        assert isinstance(stars, int) or isinstance(stars, float)
        assert isinstance(last_update, datetime.datetime) or last_update is None
        url = url.strip()
        while url.startswith("/"):
            url = url[1:]
        while url.endswith("/"):
            url = url[:-1]
        self.url = url
        self.stars = int(stars)
        self.last_update = last_update

    def __str__(self):
        return f"<PluginData url:{self.url}, stars:{self.stars}, last_update:{self.last_update.isoformat() if isinstance(self.last_update, datetime.datetime) else None}>"

    def __hash__(self):
        return hash(self.url.lower())

    def __eq__(self, other):
        return isinstance(other, ColorPlugin) and self.url.lower() == other.url.lower()

    def github_url(self):
        return f"https://github.com/{self.url}"

    def fetch_branches(self):
        try:
            with make_driver() as driver:
                driver.get(self.github_url() + "/branches")
                branches = find_elements(driver, "//branch-filter-item")
                for b in branches:
                    if b.get_attribute("branch") == "main":
                        return "main"
            return "master"
        except Exception as e:
            logging.error(e)
            return "master"

    def lazy_name(self):
        url_splits = self.url.split("/")
        org = url_splits[0]
        repo = url_splits[1]

        def name_in_blacklist(n):
            return n == "vim" or n == "nvim" or n == "neovim"

        return org if name_in_blacklist(repo) else None

    def color_names(self):
        url_splits = self.url.split("/")
        org = url_splits[0]
        repo = url_splits[1]

        def name_in_blacklist(n):
            return n == "vim" or n == "nvim" or n == "neovim"

        def preprocess(name):
            if name.find("-") > 0:
                name_splits = name.split("-")
                return [n for n in name_splits if not name_in_blacklist(n)]
            elif name.find(".") > 0:
                name_splits = name.split(".")
                return [n for n in name_splits if not name_in_blacklist(n)]
            else:
                return [name]

        if name_in_blacklist(repo):
            return preprocess(org)
        else:
            return preprocess(repo)


class Vimcolorscheme:
    def pages(self):
        i = 0
        while True:
            if i == 0:
                yield "https://vimcolorschemes.com/top"
            else:
                yield f"https://vimcolorschemes.com/top/page/{i+1}"
            i += 1

    def parse_repo(self, element: WebElement) -> util.Repo:
        url = "/".join(
            element.find_element(By.XPATH, "./a[@class='card__link']")
            .get_attribute("href")
            .split("/")[-2:]
        )
        stars = int(
            element.find_element(
                By.XPATH,
                "./a/section/header[@class='meta-header']//div[@class='meta-header__statistic']//b",
            ).text
        )
        creates_updates = element.find_elements(
            By.XPATH,
            "./a/section/footer[@class='meta-footer']//div[@class='meta-footer__column']//p[@class='meta-footer__row']",
        )
        last_update = datetime.datetime.fromisoformat(
            creates_updates[1]
            .find_element(By.XPATH, "./b/time")
            .get_attribute("datetime")
        )
        return util.Repo(url, stars, last_update)

    def fetch(self) -> None:
        with make_driver() as driver:
            for page_url in self.pages():
                driver.get(page_url)
                any_valid_stars = False
                for element in find_elements(driver, "//article[@class='card']"):
                    repo = self.parse_repo(element)
                    logging.debug(f"vsc repo:{repo}")
                    if repo.stars < STARS:
                        logging.debug(f"vsc skip for stars - repo:{repo}")
                        continue
                    assert isinstance(repo.last_update, datetime.datetime)
                    if (
                        repo.last_update.timestamp() + LASTCOMMIT
                        < datetime.datetime.now().timestamp()
                    ):
                        logging.debug(f"vsc skip for last_update - repo:{repo}")
                        continue
                    logging.debug(f"vsc get - repo:{repo}")
                    repo.save()
                    any_valid_stars = True
                if not any_valid_stars:
                    logging.debug(f"vsc no valid stars, exit")
                    break


class AwesomeNeovim:
    def parse_repo(self, element: WebElement) -> util.Repo:
        a = element.find_element(By.XPATH, "./a").text
        a_splits = a.split("(")
        repo = a_splits[0]
        stars = util.parse_number(a_splits[1])
        return util.Repo(repo, stars, None, priority=100)

    def parse_color(self, driver: Chrome, tag_id: str) -> list[util.Repo]:
        repositories = []
        colors_group = find_element(
            driver,
            f"//main[@class='markdown-body']/h4[@id='{tag_id}']/following-sibling::ul",
        )
        for e in colors_group.find_elements(By.XPATH, "./li"):
            repo = self.parse_repo(e)
            logging.debug(f"acs repo:{repo}")
            repositories.append(repo)
        return repositories

    def fetch(self) -> None:
        with make_driver() as driver:
            driver.get(
                "https://www.trackawesomelist.com/rockerBOO/awesome-neovim/readme"
            )
            treesitter_repos = self.parse_color(
                driver, "tree-sitter-supported-colorscheme"
            )
            lua_repos = self.parse_color(driver, "lua-colorscheme")
            repos = treesitter_repos + lua_repos
            for repo in repos:
                if repo.stars < STARS:
                    logging.debug(f"asc skip for stars - repo:{repo}")
                    continue
                logging.debug(f"acs get - repo:{repo}")
                repo.save()


def format_report(plugin: ColorPlugin):
    name = plugin.lazy_name()
    optional_name = f"{INDENT * 2}name = '{name}',\n" if name else ""
    branch = plugin.fetch_branches()
    optional_branch = (
        f"{INDENT * 2}branch = '{branch}',\n" if branch != "master" else ""
    )
    return f"""{INDENT}{{
{INDENT*2}-- stars:{int(plugin.stars)}, repo:{plugin.github_url()}
{INDENT*2}'{plugin.url}',
{INDENT*2}lazy = true,
{INDENT*2}priority = 1000,
{optional_name}{optional_branch}{INDENT}}},
"""


def format_candidate(plugin: ColorPlugin):
    color_names = ", ".join(plugin.color_names())
    return f"{INDENT}'{color_names}',\n"


if __name__ == "__main__":
    options = util.parse_options()
    util.init_logging(options)
    AwesomeNeovim().fetch()
    Vimcolorscheme().fetch()
