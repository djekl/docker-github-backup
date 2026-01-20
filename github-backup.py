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
    try:
        user = next(get_json("https://api.github.com/user", token))
    except requests.exceptions.HTTPError as e:
        print(f"Error: Could not authenticate with token: {e}", file=sys.stderr)
        return False
    
    user_login = user["login"]
    
    # Create base directory for this token (named after the user)
    token_base_path = os.path.join(base_path, user_login)
    mkdir(token_base_path)
    print(f"Backing up repositories for user: {user_login} to {token_base_path}")

    # Fetch organizations the user has access to
    orgs = []
    try:
        for page in get_json("https://api.github.com/user/orgs", token):
            orgs.extend(page)
    except requests.exceptions.HTTPError as e:
        print(f"Warning: Could not fetch organizations for user {user_login}: {e}", file=sys.stderr)
        orgs = []

    # Backup repositories for each organization
    for org in orgs:
        org_login = org["login"]
        org_path = os.path.join(token_base_path, org_login)
        mkdir(org_path)
        print(f"  Backing up organization: {org_login}")

        # Fetch repositories for the organization
        try:
            for page in get_json("https://api.github.com/orgs/{}/repos".format(org_login), token):
                for repo in page:
                    name = check_name(repo["name"])
                    clone_url = repo["clone_url"]
                    print(f"    Backing up repo: {org_login}/{name}")
                    mirror(name, clone_url, org_path, user["login"], token)
        except requests.exceptions.HTTPError as e:
            print(f"Warning: Could not fetch repos for org {org_login}: {e}", file=sys.stderr)

    # Backup ALL repositories accessible to the user, organized by actual owner
    print(f"  Backing up all repositories accessible to: {user_login}")
    
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
                
                print(f"    Backing up repo: {owner}/{name}")
                mirror(name, clone_url, owner_path, user["login"], token)
    except requests.exceptions.HTTPError as e:
        print(f"Warning: Could not fetch user repos for {user_login}: {e}", file=sys.stderr)
    
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
        print("Created directory {0}".format(path), file=sys.stderr)

    # Process each token
    for i, token in enumerate(tokens):
        if len(tokens) > 1:
            print(f"\nProcessing token {i+1}/{len(tokens)} (ending in {token[-4:]})", file=sys.stderr)
        else:
            print("Processing token", file=sys.stderr)
            
        success = backup_repositories_for_token(token, path)
        if not success and len(tokens) == 1:  # If only one token, exit on error
            sys.exit(1)


if __name__ == "__main__":
    main()
