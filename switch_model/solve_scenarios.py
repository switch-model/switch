#!/usr/bin/env python
# Copyright (c) 2015-2017 The Switch Authors. All rights reserved.
# Licensed under the Apache License, Version 2.0, which is in the LICENSE file.

"""Scenario management module. 
Reads scenario-related arguments from the command line and the same options 
file that solve.py would read, and uses them to setup scenarios_to_run(). 
For each scenario, this generator yields a tokenized list of arguments that 
define that scenario (similar to sys.argv, but based on a line from a scenario 
definition file, followed by any options specified on the command line). 
Then it calls solve.main() with this list of arguments (once for each scenario).

A queueing system (based on lock directories within a queue directory) is used to
ensure that scenarios_to_run() will always return the next unsolved 
scenario from the scenario list file, even if the file is edited while this
script is running. This makes it possible to amend the scenario list while
long solver jobs are running. Multiple solver scripts can also use 
scenarios_to_run() in separate processes to select the next job to run.
"""

from __future__ import print_function, absolute_import
import sys, os, time
import argparse, shlex, socket, io, glob
from collections import OrderedDict

from .utilities import _ArgumentParser

# load the solve module from the same package as this module
from . import solve

# retrieve base options and command-line arguments
option_file_args = solve.get_option_file_args()
cmd_line_args = sys.argv[1:]

# Parse scenario-manager-related command-line arguments.
# Other command-line arguments will be passed through to solve.py via scenario_cmd_line_args
parser = _ArgumentParser(
    allow_abbrev=False, description='Solve one or more SWITCH scenarios.'
)
parser.add_argument('--scenario', '--scenarios', nargs='+', dest='scenarios', default=[])
#parser.add_argument('--scenarios', nargs='+', default=[])
parser.add_argument("--scenario-list", default="scenarios.txt")
parser.add_argument("--scenario-queue", default="scenario_queue")
parser.add_argument("--job-id", default=None)

#import pdb; pdb.set_trace()
scenario_manager_args = parser.parse_known_args(args=option_file_args + cmd_line_args)[0]
scenario_option_file_args = parser.parse_known_args(args=option_file_args)[1]
scenario_cmd_line_args = parser.parse_known_args(args=cmd_line_args)[1]

requested_scenarios = scenario_manager_args.scenarios
scenario_list_file = scenario_manager_args.scenario_list
scenario_queue_dir = scenario_manager_args.scenario_queue
job_id = scenario_manager_args.job_id

# Make a best effort to get a unique, persistent job_id for each job.
# This is used to clear the queue of running tasks if a task is stopped and
# restarted. (would be better if other jobs could do this when this job dies
# but it's hard to see how they can detect when this job fails.)
# (The idea is that the user will run multiple jobs in parallel, with one 
# thread per job, to process all the scenarios. These might be run in separate
# terminal windows, or in separate instances of gnu screen, or as numbered
# jobs on an HPC system. Sometimes a job will get interrupted, e.g., if the
# user presses ctrl-c in a terminal window or if the job is launched on an 
# interruptible queue. This script attempts to detect when that job gets 
# relaunched, and re-run the interrupted scenario.)
if job_id is None:
    job_id = os.environ.get('JOB_ID') # could be set by user
if job_id is None:
    job_id = os.environ.get('JOBID') # could be set by user
if job_id is None:
    job_id = os.environ.get('SLURM_JOBID')
if job_id is None:
    job_id = os.environ.get('OMPI_MCA_ess_base_jobid')
if job_id is None:
    # construct one from hostname and parent's pid
    # this way, each job launched from a different terminal window 
    # or different instance of gnu screen will have a persistent ID
    # (This won't work on Windows before Python 3.2; in that case, 
    # users should specify a --job-id or set an environment variable 
    # when running multiple jobs in parallel. Without that, all 
    # jobs will think they have the same ID, and at startup they will 
    # try to re-run the scenario currently being run by some other job.)
    if hasattr(os, 'getppid'):
        job_id = socket.gethostname() + '_' + str(os.getppid())
    else:
        # won't be able to automatically clear previously interrupted job
        job_id = socket.gethostname() + '_' + str(os.getpid())

running_scenarios_file = os.path.join(scenario_queue_dir, job_id+"_running.txt")

# list of scenarios currently being run by this job (always just one with the current code)
running_scenarios = []

#import pdb; pdb.set_trace()

def main(args=None):
    # make sure the scenario_queue_dir exists (marginally better to do this once
    # rather than every time we need to write a file there)
    try:
        os.makedirs(scenario_queue_dir)
    except OSError:
        pass    # directory probably exists already
    
    # remove lock directories for any scenarios that were
    # previously being solved by this job but were interrupted
    unlock_running_scenarios()
    
    for (scenario_name, args) in scenarios_to_run():
        print(
            "\n\n=======================================================================\n"
            + "running scenario {s}\n".format(s=scenario_name)
            + "arguments: {}\n".format(args)
            + "=======================================================================\n"
        )

        # call the standard solve module with the arguments for this particular scenario
        solve.main(args=args)

        # another option:
        # subprocess.call(shlex.split("python -m solve") + args) <- omit args from options.txt
        # it should also be possible to use a solver server, but that's not really needed
        # since this script has built-in queue management.

        mark_completed(scenario_name)

def scenarios_to_run():
    """Generator function which returns argument lists for each scenario that should be run.
    
    Note: each time a new scenario is required, this re-reads the scenario_list file
    and then returns the first scenario that hasn't already started running.
    This allows multiple copies of the script to be run and allocate scenarios among 
    themselves."""
    
    skipped = []
    ran = []
    
    if requested_scenarios:
        # user requested one or more scenarios
        # just run them in the order specified, with no queue-management
        for scenario_name in requested_scenarios:
            completed = False
            scenario_args = scenario_option_file_args + get_scenario_dict()[scenario_name] + scenario_cmd_line_args
            # flag the scenario as being run; then run it whether or not it was previously run
            checkout(scenario_name, force=True)
            yield (scenario_name, scenario_args)
        # no more scenarios to run
        return
    else:   # no specific scenarios requested
        # Run every scenario in the list, with queue management
        # This is done by repeatedly scanning the scenario list and choosing
        # the first scenario that hasn't been run. This way, users can edit the
        # list and this script will adapt to the changes as soon as it finishes 
        # the current scenario.
        all_done = False
        while not all_done:
            all_done = True
            # cache a list of scenarios that have been run, to avoid trying to checkout every one. 
            # This list is found by retrieving the names of the lock-directories.
            already_run = filter(os.path.isdir, os.listdir("."))
            for scenario_name, base_args in get_scenario_dict().items():
                if scenario_name not in already_run and checkout(scenario_name):
                    # run this scenario, then start again at the top of the list
                    ran.append(scenario_name)
                    scenario_args = scenario_option_file_args + base_args + scenario_cmd_line_args
                    yield (scenario_name, scenario_args)
                    all_done = False
                    break
                else:
                    if scenario_name not in skipped and scenario_name not in ran:
                        skipped.append(scenario_name)
                        print("Skipping {} because it was already run.".format(scenario_name))
                # move on to the next candidate
        # no more scenarios to run
        if skipped and not ran:
            print(
                "Please remove the {sq} directory or its contents if you would like to "
                "run these scenarios again. (rm -rf {sq})".format(sq=scenario_queue_dir)
            )
        return
        

def parse_arg(arg, args=sys.argv[1:], **parse_kw):
    """Parse one argument from the argument list, using options as specified for argparse"""
    parser = _ArgumentParser(allow_abbrev=False)
    # Set output destination to 'option', so we can retrieve the value predictably.
    # This is done by updating parse_kw, so it can't be overridden by callers.
    # (They have no reason to set the destination anyway.)
    # note: we use the term "option" so that parsing errors will make a little more
    # sense, e.g., if users call with "--suffixes <blank>" (instead of just omitting it)
    parse_kw["dest"]="option"
    parser.add_argument(arg, **parse_kw)
    return parser.parse_known_args(args)[0].option

def get_scenario_name(scenario_args):
    # use ad-hoc parsing to extract the scenario name from a scenario-definition string
    return parse_arg("--scenario-name", default=None, args=scenario_args)

def get_scenario_dict():
    # note: we read the list from the disk each time so that we get a fresher version
    # if the standard list is changed during a long solution effort.
    with open(scenario_list_file, 'r') as f:
        scenario_list_text = [r.strip() for r in f.read().splitlines()]
        scenario_list_text = [r for r in scenario_list_text if r and not r.startswith("#")]
        
    # note: text.splitlines() omits newlines and ignores presence/absence of \n at end of the text
    # shlex.split() breaks an command-line-style argument string into a list like sys.argv
    scenario_list = [shlex.split(r) for r in scenario_list_text]
    return OrderedDict((get_scenario_name(s), s) for s in scenario_list)

def checkout(scenario_name, force=False):
    # write a flag that we are solving this scenario, before actually trying to lock it
    # this way, if the job gets interrupted in the middle of this function, the
    # worst that can happen is the scenario will be restarted then next time the job restarts
    # (if we locked the scenario and then got interrupted before setting the flag, then
    # the scenario would not be restarted when the job restarts, which is worse.)
    running_scenarios.append(scenario_name)
    write_running_scenarios_file()
    try:
        # create a lock directory for this scenario
        os.mkdir(os.path.join(scenario_queue_dir, scenario_name))
        locked = True
    except OSError as e:
        if e.errno != 17:     # File exists
            raise
        locked = False
    if locked or force:
        return True
    else:
        # remove the flag that we're running this scenario
        running_scenarios.remove(scenario_name)
        write_running_scenarios_file()
        return False

def mark_completed(scenario_name):
    # remove the scenario from the list of running scenarios (since it's been completed now)
    running_scenarios.remove(scenario_name)
    write_running_scenarios_file()
    # note: the scenario lock directory is left in place so the scenario won't get checked 
    # out again
    
def write_running_scenarios_file():
    # write the list of scenarios currently being run by this job to disk
    # so they can be released back to the queue if the job is interrupted and restarted
    if running_scenarios:
        # note: we use open("r+") and truncate() instead of open("w")
        # to give a better chance of retaining the original file contents if this
        # job is interrupted in the middle of writing the file. This is not an issue unless
        # this job is running multiple scenarios at once
        # (If the file is only partial, then the queue will just think some jobs have been
        # done that actually haven't.)
        flags = "r+" if os.path.exists(running_scenarios_file) else "w"
        with open(running_scenarios_file, flags) as f:
            f.write("\n".join(running_scenarios)+"\n")
            f.truncate()
    else:
        # remove the running_scenarios_file entirely if it would be empty
        try: 
            os.remove(running_scenarios_file)
        except OSError as e:
            if e.errno != 2:    # no such file
                raise

def unlock_running_scenarios():
    # called during startup to remove lockfiles for any scenarios that were still running
    # when this job was interrupted
    if os.path.exists(running_scenarios_file):
        with open(running_scenarios_file) as f:
            interrupted = f.read().splitlines()
        for scenario_name in interrupted:
            try: 
                os.rmdir(scenario_name)
            except OSError as e:
                if e.errno != 2:    # no such file
                    raise

# run the main function if called as a script
if __name__ == "__main__":
    main()
