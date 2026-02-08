#!/usr/bin/env python3

import os
import re
import sys
import json
import shlex
import errno
import argparse
import requests
import subprocess
import urllib.parse


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
    """Create directory with Unraid-compatible permissions"""
    try:
        os.makedirs(path, 0o777, exist_ok=True)
        # Try to ensure correct ownership (may fail in some environments)
        try:
            os.chown(path, 99, 100)
        except:
            pass  # Non-critical if this fails
        return True
    except PermissionError:
        print(f"Permission denied creating directory: {path}", file=sys.stderr, flush=True)
        return False
    except Exception as e:
        if errno.errorcode.get(e.errno) != 'EEXIST':
            print(f"Error creating directory {path}: {e}", file=sys.stderr, flush=True)
            return False
        return True


def mirror(repo_name, repo_url, to_path, username, token):
    """Create an empty GIT rep so we have the history, but not the files"""
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
    subprocess.call(
        shlex.split(f"git init --bare --quiet"),
        cwd=repo_path,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    # https://github.com/blog/1270-easier-builds-and-deployments-using-git-over-https-and-oauth:
    # "To avoid writing tokens to disk, don't clone."
    subprocess.call(
        shlex.split(f"git fetch --force --prune --tags --quiet {repo_url} refs/heads/*:refs/heads/*"),
        cwd=repo_path,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def download_zip_snapshot(owner, repo, to_path, token):
    """Download ZIP Snapshot of the repo"""
    zip_url = f"https://api.github.com/repos/{owner}/{repo}/zipball"
    zip_path = os.path.join(to_path, f"{repo}.zip")

    try:
        r = requests.get(
            zip_url,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {token}",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            stream=True,
            timeout=300,
        )
        r.raise_for_status()
        with open(zip_path, "wb") as fh:
            for chunk in r.iter_content(chunk_size=1024 * 64):
                fh.write(chunk)
    except requests.exceptions.HTTPError as e:
        # print(f"    Warning: could not fetch ZIP for {owner}/{repo}: {e}\n", file=sys.stderr, flush=True)
        pass


def backup_repositories_for_token(token, base_path):
    """Backup repositories for a single token"""
    try:
        user = next(get_json("https://api.github.com/user", token))
    except requests.exceptions.HTTPError as e:
        print(f"Error: Could not authenticate with token: {e}", file=sys.stderr, flush=True)
        return False

    user_login = user["login"]

    # Create base directory for this token (named after the user)
    token_base_path = os.path.join(base_path, user_login)
    mkdir(token_base_path)
    print(f"Backing up repositories for user: {user_login} to {token_base_path}", flush=True)

    # Fetch organizations the user has access to
    orgs = []
    try:
        for page in get_json("https://api.github.com/user/orgs", token):
            orgs.extend(page)
    except requests.exceptions.HTTPError as e:
        print(f"Warning: Could not fetch organizations for user {user_login}: {e}", file=sys.stderr, flush=True)
        orgs = []

    # Backup repositories for each organization
    for org in orgs:
        org_login = org["login"]
        org_path = os.path.join(token_base_path, org_login)
        mkdir(org_path)
        print(f"\n  Backing up organization: {org_login}", flush=True)

        # Fetch repositories for the organization
        try:
            for page in get_json("https://api.github.com/orgs/{}/repos".format(org_login), token):
                for repo in page:
                    name = check_name(repo["name"])
                    clone_url = repo["clone_url"]

                    print(f"    -> Backing up repo: {org_login}/{name}", flush=True)
                    mirror(name, clone_url, org_path, user["login"], token)

                    print(f"     + Downloading repo zip snapshot: {org_login}/{name}.zip\n", flush=True)
                    download_zip_snapshot(org_login, name, org_path, token)
        except requests.exceptions.HTTPError as e:
            print(f"Warning: Could not fetch repos for org {org_login}: {e}\n", file=sys.stderr, flush=True)

    # Backup ALL repositories accessible to the user, organized by actual owner
    print(f"\n\n  Backing up all repositories accessible to: {user_login}", flush=True)
    processed_repos = set()  # Track already backed up repos to avoid duplicates

    try:
        for page in get_json("https://api.github.com/user/repos", token):
            for repo in page:
                name = check_name(repo["name"])
                owner = check_name(repo["owner"]["login"])
                clone_url = repo["clone_url"]

                # Create unique identifier to prevent duplicates
                repo_id = f"{owner}/{name}"
                if repo_id in processed_repos:
                    continue
                processed_repos.add(repo_id)

                # Create directory structure based on actual repository owner
                owner_path = os.path.join(token_base_path, owner)
                mkdir(owner_path)

                print(f"    -> Backing up repo: {owner}/{name}", flush=True)
                mirror(name, clone_url, owner_path, user["login"], token)

                print(f"     + Downloading repo zip snapshot: {owner}/{name}.zip\n", flush=True)
                download_zip_snapshot(owner, name, owner_path, token)
    except requests.exceptions.HTTPError as e:
        print(f"Warning: Could not fetch user repos for {user_login}: {e}\n", file=sys.stderr, flush=True)

    return True


def main():
    parser = argparse.ArgumentParser(description="Backup GitHub repositories")
    parser.add_argument("config", metavar="CONFIG", help="a configuration file")
    args = parser.parse_args()

    with open(args.config, "rb") as f:
        config = json.loads(f.read())

    # Handle both 'token' (legacy) and 'tokens' (new) config formats
    if "tokens" in config:
        tokens_config = config["tokens"]
    elif "token" in config:
        tokens_config = config["token"]
        # Convert single token to list for consistency
        if isinstance(tokens_config, str):
            tokens_config = [tokens_config]
    else:
        raise ValueError("Config must contain either 'tokens' or 'token' field")

    # Handle multiple tokens format
    if isinstance(tokens_config, str):
        tokens = [token.strip() for token in tokens_config.split(",")]
    elif isinstance(tokens_config, list):
        tokens = tokens_config
    else:
        raise ValueError("tokens must be a string (comma-separated) or a list")

    path = os.path.expanduser(config["directory"])
    if mkdir(path):
        print("Created directory {0}".format(path), file=sys.stderr, flush=True)

    # Process each token
    for i, token in enumerate(tokens):
        if len(tokens) > 1:
            print(f"\nProcessing token {i + 1}/{len(tokens)} (ending in {token[-4:]})", file=sys.stderr, flush=True)
        else:
            print("Processing token", file=sys.stderr, flush=True)

        success = backup_repositories_for_token(token, path)
        if not success and len(tokens) == 1:  # If only one token, exit on error
            sys.exit(1)


if __name__ == "__main__":
    main()
