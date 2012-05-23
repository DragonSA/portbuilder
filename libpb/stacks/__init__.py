"""
The stacks module.  This module contains code to implement the various
stacks (made up of stages) for Port.

The stacks are (using the env.flags["target"] notation):
 common  - the config and depend stages, required for all other stacks
 build   - build a port directly
 package - install a port from a locally built repository
 repo    - install a port from a remote repository
"""

from libpb.stacks.base import Stage, Stack
from libpb.stacks.common import Config, Depend
from libpb.stacks.build import Checksum, Fetch, Build, Install, Package
from libpb.stacks.package import PkgInstall
from libpb.stacks.repo import RepoConfig, RepoFetch, RepoInstall

__all__ = [
        # The base elements
        "Stage", "Stack",
        # "Common" stack"
        "Config", "Depend",
        # "Build" stack
        "Checksum", "Fetch", "Build", "Install", "Package",
        # "Package" stack
        "PkgInstall",
        # "Repo" stack
        "RepoConfig", "RepoFetch", "RepoInstall",
    ]
