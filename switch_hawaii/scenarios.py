import argparse, os, collections

try:
    import fcntl
    def flock(f):
        fcntl.flock(f, fcntl.LOCK_EX)
    def funlock(f):
        fcntl.flock(f, fcntl.LOCK_UN)
except ImportError:
    # probably using windows
    # rely on opportunistic file writing (hope that scenarios aren't 
    # added to completed_scenarios.txt at the same time by parallel processes)
    # TODO: add support for file locking on windows, e.g., like
    # https://www.safaribooksonline.com/library/view/python-cookbook/0596001673/ch04s25.html
    def flock(f):
        pass
    def funlock(f):
        pass

def iterify(item):
    """Return an iterable for the one or more items passed."""
    if isinstance(item, basestring):
        i = iter([item])
    else:
        try:
            # check if it's iterable
            i = iter(item)
        except TypeError:
            i = iter([item])
    return i

class AddModuleAction(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        for m in iterify(values):
            setattr(namespace, m, True)

class RemoveModuleAction(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        for m in iterify(values):
            setattr(namespace, m, False)

class AddListAction(argparse.Action):
    def __call__(self, parser, namespace, values, option_string=None):
        if getattr(namespace, self.dest) is None:
            setattr(namespace, self.dest, list())
        getattr(namespace, self.dest).extend(iterify(values))

# define a standard argument parser, which can be used to setup scenarios
# NOTE: you can't safely use default values here, because those end up being
# assigned to cmd_line_args(), and then they override any values set for the
# standard scenarios.
parser = argparse.ArgumentParser(description='Solve one or more Switch-Hawaii scenarios.')
parser.add_argument('--inputs', dest='inputs_dir')
parser.add_argument('--inputs-subdir')
parser.add_argument('--outputs', dest='outputs_dir')
parser.add_argument('--scenario', action=AddListAction, dest='scenario_to_run')
parser.add_argument('--scenarios', action=AddListAction, nargs='+', dest='scenario_to_run')
parser.add_argument('--scenario-name')
parser.add_argument('--exclude', action=AddModuleAction, dest='exclude_module', nargs='+')
parser.add_argument('-n', action=RemoveModuleAction, dest='exclude_module')
parser.add_argument('--include', action=AddModuleAction, dest='include_module', nargs='+')
parser.add_argument('-y', action=AddModuleAction, dest='include_module')
parser.add_argument(action=AddModuleAction, dest='include_module', nargs='*')

def args_dict(*a):
    """call the parser to get the args, then return them as a dictionary, omitting None's'"""
    return {k: v for k, v in vars(parser.parse_args(*a)).iteritems() if v is not None}

# report current command line arguments for use by various functions
# This is a function instead of a constant, so users can call
# scenarios.parser.add_argument() to add arguments of their own before evaluation
def cmd_line_args():
    return args_dict()

def get_required_scenario_names():
    """Return list of names of scenario(s) that were requested or defined from the command line 
    via --scenario[s] or --scenario-name.
    Return an empty list if none were requested/defined."""
    a = cmd_line_args()
    if "scenario_to_run" in a:
        return a["scenario_to_run"]
    elif "scenario_name" in a or not os.path.isfile('scenarios_to_run.txt'):
        # They have defined one specific scenario on the command line, which is not based on any standard scenario,
        # or there are no standard scenarios.
        # Return a no-name scenario, which indicates to build the scenario without referring to any standard scenario.
        return ['']
    else:
        # no specific scenarios were requested on the command line; run the standard scenarios instead
        return []


def start_next_standard_scenario():
    """find the next scenario definition in 'scenarios_to_run.txt' that isn't reported
    as having been completed in 'completed_scenarios.txt'. 
    Then report it as completed and return the scenario arguments 
    (including any modifications from the command line)."""
    scenarios_list = get_standard_scenarios_dict()
    for (s, args) in scenarios_list.iteritems():
        if scenario_already_run(s):
            continue
        else:
            return merge_scenarios(args, cmd_line_args())
    return None     # no more scenarios to run

def get_scenario_args(scenario):
    """Return the arguments for the specified standard scenario, amended with any command-line arguments.
    This may also be called with an empty scenario name ('') to define a scenario using only command-line arguments."""
    if scenario == '':
        return merge_scenarios(cmd_line_args())
    else:
        scenario_list = get_standard_scenarios_dict()
        if scenario not in scenario_list:
            raise RuntimeError("Scenario {s} has not been defined.".format(s=scenario))
        else:
            return merge_scenarios(scenario_list[scenario], cmd_line_args())
        
def get_standard_scenarios_dict():
    """Return collection of standard scenarios, as defined in scenarios_to_run.txt.
    They are returned as an OrderedDict with keys equal to the scenario names and values
    that are each a dictionary of arguments for that scenario."""
    # note: we read the list from the disk each time so that we get a fresher version
    # if the standard list is changed during a long solution effort.
    with open('scenarios_to_run.txt', 'r') as f:
        # wait for exclusive access to the file (to avoid reading while the file is being changed)
        flock(f)
        scenarios_list = list(f.read().splitlines())    # note: ignores presence/absence of \n at end of file
        funlock(f)
    args_list = [args_dict(s.split(' ')) for s in scenarios_list]
    return collections.OrderedDict([(s["scenario_name"], s) for s in args_list])
        
def merge_scenarios(*scenarios):
    # combine scenarios: start with the first and then apply most settings from later ones
    # but concatenate "tag" entries and remove "scenario_to_run" entries
    d = dict(tag='')
    for s in scenarios:
        t1 = d["tag"]
        t2 = s.get("tag", "")
        s["tag"] = t1 + ("" if t1 == "" or t2 == "" else "_") + t2
        d.update(s)
    if 'scenario_to_run' in d:
        del d['scenario_to_run']
    return d

def report_completed_scenario(scenario):
    scenario_already_run(scenario)

def scenario_already_run(scenario):
    """Add the specified scenario to the list in completed_scenarios.txt. 
    Return False if it wasn't there already."""
    with open('completed_scenarios.txt', 'a+') as f:
        # wait for exclusive access to the list (to avoid writing the same scenario twice in a race condition)
        flock(f)
        # file starts with pointer at end; move to start
        f.seek(0, 0)                    
        if scenario + '\n' in f:
            already_run = True
        else:
            already_run = False
            # append name to the list (will always go at end, because file was opened in 'a' mode)
            f.write(scenario + '\n')
        funlock(f)
    return already_run
