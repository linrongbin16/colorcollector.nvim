#!/usr/bin/env python3

import datetime
import logging
import os
import pathlib
import shutil

import util


def dedup() -> set[util.Repo]:
    def greater_than(a: util.Repo, b: util.Repo) -> bool:
        if a.priority != b.priority:
            return a.priority > b.priority
        if a.stars != b.stars:
            return a.stars > b.stars
        # for duplicated colors, we suppose neovim/lua plugins are better
        # and we don't fetch last commit datetime in awesome-neovim's plugins
        # so the repo don't have last_update has higher priority
        if a.last_update is None or b.last_update is None:
            return True if a.last_update is None else False
        return a.last_update.timestamp() > b.last_update.timestamp()

    colors: dict[str, util.Repo] = dict()
    repos: set[util.Repo] = set()

    for repo in util.Repo.get_all():
        with util.GitObject(repo) as candidate:
            for color in candidate.colors:
                # detect duplicated color
                if color in colors:
                    old_repo = colors[color]
                    logging.info(
                        f"detect duplicated color on new repo:{repo} and old repo:{old_repo}"
                    )
                    # replace old repo if new repo has higher priority
                    if greater_than(repo, old_repo):
                        logging.info(
                            f"replace old repo:{old_repo} with new repo:{repo}"
                        )
                        colors[color] = repo
                        repos.add(repo)
                        repos.remove(old_repo)
                else:
                    # add new color
                    colors[color] = repo
                    repos.add(repo)
    return repos


def dump_submodule(repo: util.Repo) -> None:
    submodule_path = pathlib.Path(f"submodule/{repo.url}")
    if not submodule_path.exists() or not submodule_path.is_dir():
        submodule_cmd = (
            f"git submodule add -b {repo.config.branch} --force https://github.com/{repo.url} {submodule_path}"
            if repo.config and repo.config.branch
            else f"git submodule add --force https://github.com/{repo.url} {submodule_path}"
        )
        logging.info(submodule_cmd)
        os.system(submodule_cmd)
    else:
        logging.info(f"submodule:{submodule_path} already exist, skip...")


def dump_color(fp, repo: util.Repo) -> None:
    colors_dir = pathlib.Path(f"submodule/{repo.url}/colors")
    colors_files = [
        f
        for f in colors_dir.iterdir()
        if f.is_file() and (str(f).endswith(".vim") or str(f).endswith(".lua"))
    ]
    colors = [str(c.name)[:-4] for c in colors_files]
    submodule_path = pathlib.Path(f"submodule/{repo.url}")
    submodule = str(submodule_path)
    if submodule.find("\\") >= 0:
        submodule = submodule.replace("\\", "/")
    for c in colors:
        fp.writelines(f"{util.INDENT}['{c}']='{submodule}',\n")


def build() -> None:
    # clean candidate dir
    candidate_path = pathlib.Path("candidate")
    if candidate_path.exists() and candidate_path.is_dir():
        shutil.rmtree(candidate_path)

    # clone candidates
    for repo in util.Repo.get_all():
        with util.GitObject(repo) as candidate:
            candidate.clone()

    # dedup candidates
    deduped_repos = dedup()

    # dump submodule
    for repo in deduped_repos:
        dump_submodule(repo)
    update_submodule_cmd = "git submodule update --init --remote"
    logging.info(update_submodule_cmd)
    os.system(update_submodule_cmd)

    # dump colors
    with open("lua/colorswitch/candidates.lua", "w") as fp:
        fp.writelines(f"-- Colorscheme Collections\n")
        fp.writelines(f"return {{\n")
        for repo in deduped_repos:
            dump_color(fp, repo)
        fp.writelines(f"}}\n")


if __name__ == "__main__":
    options = util.parse_options()
    util.init_logging(options)
    build()
