#!/usr/bin/env python3

import os
import re
import sys
import json
import errno
import argparse
import subprocess
import urllib.parse

import requests


def get_json(url, token):
    while True:
        response = requests.get(
            url, headers={"Authorization": "token {0}".format(token)}
        )
        response.raise_for_status()
        yield response.json()

        if "next" not in response.links:
            break
        url = response.links["next"]["url"]


def check_name(name):
    if not re.match(r"^[-\.\w]*$", name):
        raise RuntimeError("invalid name '{0}'".format(name))
    return name


def mkdir(path):
    try:
        os.makedirs(path, 0o770)
    except OSError as ose:
        if ose.errno != errno.EEXIST:
            raise
        return False
    return True


def mirror(repo_name, repo_url, to_path, username, token):
    parsed = urllib.parse.urlparse(repo_url)
    modified = list(parsed)
    modified[1] = "{username}:{token}@{netloc}".format(
        username=username, token=token, netloc=parsed.netloc
    )
    repo_url = urllib.parse.urlunparse(modified)

    repo_path = os.path.join(to_path, repo_name)
    mkdir(repo_path)

    # git-init manual:
    # "Running git init in an existing repository is safe."
    subprocess.call(["git", "init", "--bare", "--quiet"], cwd=repo_path)

    # https://github.com/blog/1270-easier-builds-and-deployments-using-git-over-https-and-oauth:
    # "To avoid writing tokens to disk, don't clone."
    subprocess.call(
        [
            "git",
            "fetch",
            "--force",
            "--prune",
            "--tags",
            repo_url,
            "refs/heads/*:refs/heads/*",
        ],
        cwd=repo_path,
    )


def backup_repositories_for_token(token, base_path):
    """Backup repositories for a single token"""
    user = next(get_json("https://api.github.com/user", token))
    user_login = user["login"]
    
    # Fetch organizations the user has access to
    orgs = []
    try:
        for page in get_json("https://api.github.com/user/orgs", token):
            orgs.extend(page)
    except requests.exceptions.HTTPError as e:
        print(f"Warning: Could not fetch organizations for token ending in {token[-4:]}: {e}", file=sys.stderr)
        orgs = []

    # Backup repositories for each organization
    for org in orgs:
        org_login = org["login"]
        org_path = os.path.join(base_path, org_login)
        mkdir(org_path)
        print(f"Backing up organization: {org_login}")

        # Fetch repositories for the organization
        try:
            for page in get_json("https://api.github.com/orgs/{}/repos".format(org_login), token):
                for repo in page:
                    name = check_name(repo["name"])
                    clone_url = repo["clone_url"]
                    print(f"  Backing up repo: {org_login}/{name}")
                    mirror(name, clone_url, org_path, user["login"], token)
        except requests.exceptions.HTTPError as e:
            print(f"Warning: Could not fetch repos for org {org_login}: {e}", file=sys.stderr)

    # Backup user's own repositories in a folder named after the user
    user_path = os.path.join(base_path, user_login)
    mkdir(user_path)
    print(f"Backing up user repositories for: {user_login}")

    try:
        for page in get_json("https://api.github.com/user/repos", token):
            for repo in page:
                name = check_name(repo["name"])
                owner = check_name(repo["owner"]["login"])
                clone_url = repo["clone_url"]
                print(f"  Backing up repo: {owner}/{name}")
                mirror(name, clone_url, user_path, user["login"], token)
    except requests.exceptions.HTTPError as e:
        print(f"Warning: Could not fetch user repos: {e}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description="Backup GitHub repositories")
    parser.add_argument("config", metavar="CONFIG", help="a configuration file")
    args = parser.parse_args()

    with open(args.config, "rb") as f:
        config = json.loads(f.read())

    # Handle both single token and multiple tokens
    tokens_config = config["tokens"]
    if isinstance(tokens_config, str):
        tokens = [token.strip() for token in tokens_config.split(",")]
    elif isinstance(tokens_config, list):
        tokens = tokens_config
    else:
        raise ValueError("tokens must be a string (comma-separated) or a list")

    path = os.path.expanduser(config["directory"])
    if mkdir(path):
        print("Created directory {0}".format(path), file=sys.stderr)

    # Process each token
    for i, token in enumerate(tokens):
        if len(tokens) > 1:
            print(f"\nProcessing token {i+1}/{len(tokens)}", file=sys.stderr)
        else:
            print("Processing token", file=sys.stderr)
            
        try:
            backup_repositories_for_token(token, path)
        except Exception as e:
            print(f"Error processing token ending in {token[-4:]}: {e}", file=sys.stderr)
            if len(tokens) == 1:  # If only one token, exit on error
                raise


if __name__ == "__main__":
    main()
