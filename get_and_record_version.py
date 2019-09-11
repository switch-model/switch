from __future__ import print_function
import argparse
import logging
import os
import subprocess

"""
Define a precise package version that includes any git digests for any commits
made subsequently to a package release. The base version (2.0.4 in this
example) is obtained from the last tag that starts with "2". version. Also use
the git-standard "dirty" suffix instead of "localmod" for installations from
code that hasn't been committed.

Example: 
1) 112 commits were made subsequent to an official release (possibly on
a branch), plus some uncommitted modifications. The version would be:
2.0.4+112+{gitsha}+dirty
2) Same scenario, but no uncommitted modifications: 2.0.4+112+{gitsha}
3) No commits since the last tagged release: 2.0.4

These functions are encoded into a separate file from setup.py to support
including precise versions in docker tags.
"""

def get_git_version():
    """
    Try to get git version like '{tag}+{gitsha}', with the added suffix
    "+dirty" if the git repo has had any uncommitted modifications. 
    The "+{gitsha}" suffix will be dropped if this is the tagged version.
    Code adapted from setuptools_git_version which has an MIT license.
        https://pypi.org/project/setuptools-git-version/
    Note: Only look for tags that start with "2." to avoid tags of
    non-released versions.
    """
    git_command = "git describe --all --long --match '2.*' --dirty --always"
    fmt = '{base_v}+{count}+{gitsha}{dirty}'

    git_version = subprocess.check_output(git_command, shell=True).decode('utf-8').strip()
    # The prefix tags/ may not appear in every context, and should be ignored.
    match = re.match("(tags/)?(.*)-([\d]+)-g([0-9a-f]+)(-dirty)?", git_version)
    assert match, (
        "Trouble parsing git version output. Got {}, expected 3 or 4 things "
        "separated by dashes. This has been encountered when the local git repo "
        "lacks tags, which can be solved by fetching from the main repo:\n"
        "`git remote add main https://github.com/switch-model/switch.git && "
        "git fetch --all`".format(git_version)
    )
    parts = match.groups()[1:]
    if parts[-1] == '-dirty':
        dirty = '+dirty'
    else:
        dirty = ''
    base_v, count, sha = parts[:3]
    if count == '0' and not dirty:
        return base_v
    return fmt.format(base_v=base_v, count=count, gitsha=sha, dirty=dirty)

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