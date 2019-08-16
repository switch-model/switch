from __future__ import print_function
import argparse
import logging
import os
import subprocess

"""
Define a precise package version that includes any git digests for any commits
made subsequently to a package release. 

Example: 
1) Some commits have been made subsequent to an official release (possibly on
a branch), plus some uncommitted modifications. The version would be:
v1.0.4+{gitsha}+localmod
2) Same scenario, but no uncommitted modifications: v1.0.4+{gitsha}
3) No commits since the last official release: v1.0.4

These functions are encoded into a separate file from setup.py to support
including precise versions in docker tags.
"""

def get_git_version():
    """
    Try to get git version like '{tag}+{gitsha}', with the added suffix
    "+localmod" if the git repo has had any uncommitted modifications. 
    The "+{gitsha}" suffix will be dropped if this is the tagged version.
    Code adapted from setuptools_git_version which has an MIT license.
        https://pypi.org/project/setuptools-git-version/
    Note: Only look for tags that start with "2." to avoid tags like "demo-v1.0.1".
    """
    git_command = "git describe --tags --long --match '2.*' --dirty --always"
    fmt = '{tag}+{gitsha}{dirty}'

    git_version = subprocess.check_output(git_command, shell=True).decode('utf-8').strip()
    parts = git_version.split('-')
    # FYI, if it can't find a tag for whatever reason, len may be 1 or 2
    assert len(parts) in (3, 4), (
        "Trouble parsing git version output. Got {}, expected 3 or 4 things "
        "separated by dashes. This has been caused by the repository having no "
        "available tags, which was solved by fetching from the main repo:\n"
        "`git remote add main https://github.com/switch-model/switch.git && "
        "git fetch --all`".format(git_version)
    )
    if len(parts) == 4:
        dirty = '+localmod'
    else:
        dirty = ''
    tag, count, sha = parts[:3]
    if count == '0' and not dirty:
        return tag
    return fmt.format(tag=tag, gitsha=sha.lstrip('g'), dirty=dirty)

def get_and_record_version(repo_path):
    """
    Attempt to get an absolute version number that includes commits made since
    the last release. If that succeeds, record the absolute version and use it
    for the pip catalog. If that fails, fall back to something reasonable and
    vague for the pip catalog, using the data from base_version.py.
    """
    pkg_dir = os.path.join(repo_path , 'switch_model' )
    data_dir = os.path.join(pkg_dir, 'data' )
    __version__ = None
    try:
        __version__ = get_git_version()
        with open(os.path.join(data_dir, 'installed_version.txt'), 'w+') as f:
            f.write(__version__)
    except subprocess.CalledProcessError as e:
        logging.warning(
            "Could not call git as a subprocess to determine precise version."
            "Falling back to using the static version from version.py")
        logging.exception(e)
    except AssertionError as e:
        logging.warning("Trouble parsing git output.")
        logging.exception(e)
    except Exception as e:
        logging.warning(
            "Trouble getting precise version from git repository; "
            "using base version from switch_model/version.py. "
            "Error was: {}".format(e)
        )
    if __version__ is None:
        module_dat = {}
        with open(os.path.join(pkg_dir, 'version.py')) as fp:
            exec(fp.read(), module_dat)
        __version__ = module_dat['__version__']
    return __version__

def get_args():
    parser = argparse.ArgumentParser(
        description='Get a precise local version of this git repository',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument(
        '--verbose', '-v', dest='verbose', default=False, 
        action='store_const', const=logging.WARNING,
        help='Show information about model preparation and solution')
    parser.add_argument(
        '--very-verbose', '-vv', dest='verbose', default=False, 
        action='store_const', const=logging.INFO,
        help='Show more information about model preparation and solution')
    parser.add_argument(
        '--very-very-verbose', '-vvv', dest='verbose', default=False, 
        action='store_const', const=logging.DEBUG,
        help='Show debugging-level information about model preparation and solution')
    parser.add_argument(
        '--quiet', '-q', dest='verbose', action='store_false',
        help="Don't show information about model preparation and solution "
             "(cancels --verbose setting)")

    args = parser.parse_args()
    return args

def main():
    args = get_args()
    if args.verbose:
        logging.basicConfig(format='%(levelname)s:%(message)s', level=args.verbose)
    repo_path = os.path.dirname(os.path.realpath(__file__))
    __version__ = get_and_record_version(repo_path)
    print(__version__)

if __name__ == "__main__":
    main()