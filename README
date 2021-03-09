This contains version 2 of the Switch electricity planning model.
This optimization model is modular and can be used with varying levels
of complexity. Look in the examples directory for demonstrations of
using Switch for investment planning or production cost simulation. The
examples enable varying levels of model complexity by choosing which
modules to include.

See INSTALL for installation instructions.

To generate documentation, go to the doc folder and run ./make_doc.sh.
This will build html documentation files from python doc strings which
will include descriptions of each module, their intentions, model
components they define, and what input files they expect.

TESTING
To test the entire codebase, run this command from the root directory:
	python run_tests.py

EXAMPLES
To run an example, navigate to an example directory and run the command:
	switch solve --verbose --log-run

CONFIGURING YOUR OWN MODELS

At a minimum, each model requires a list of SWITCH modules to define the model
and a set of input files to provide the data. The SWITCH framework and
individual modules also accept command-line arguments to change their behavior.

Each SWITCH model or collection of models is defined in a specific directory
(e.g., examples/3zone_toy). This directory contains one or more subdirectories
that hold input data and results (e.g., "inputs" and "outputs"). The models in
the examples directory show the type of text files used to provide inputs for a
model. You can change any of the model's input data by editing the *.csv files
in the input directory.

SWITCH contains a number of different modules, which can be selected and
combined to create models with different capabilities and amounts of detail.
You can look through the *.py files within switch_mod and its subdirectories to
see the standard modules that are available and the columns that each one will
read from the input files. You can also add modules of your own by creating
Python files in the main model directory and adding their name (without the
".py") to the module list, discussed below. These should define the same
functions as the standard modules (e.g., define_components()).

Each model has a text file which lists the modules that will be used for that
model. Normally this file is called "modules.txt" and is stored in the main
model directory or in an inputs subdirectory. SWITCH will automatically look in
those locations for this list; alternatively, you can specify a different file
with the "--module-list" argument.

Use "switch --help", "switch solve --help" or "switch solve-scenarios --help"
to see a list of command-line arguments that are available.

You can specify these arguments on the command line when you solve the model
(e.g., "switch solve --solver cplex"). You can also place frequently used
arguments in a file called "options.txt" in the main model directory. These can
all be on one line, or they can be placed on multiple lines for easier
readability (be sure to include the "--" part in all the argument names in
options.txt). The "switch solve" command first reads all the arguments from
options.txt, and then applies any arguments you specified on the command line.
If the same argument is specified multiple times, the last one takes priority.

You can also define scenarios, which are sets of command-line arguments to
define different models. These additional arguments can be placed in a scenario
list file, usually called "scenarios.txt" in the main model directory (or you
can use a different file specified by "--scenario-list"). Each scenario should
be defined on a single line, which includes a "--scenario-name" argument and
any other arguments needed to define the scenario. "switch solve-scenarios"
will solve all the scenarios listed in this file. For each scenario, it will
first apply all arguments from options.txt, then arguments from the relevant
line of scenarios.txt, then any arguments specified on the command line.

After the model runs, results will be written in tab-separated text files (with
extension .tsv or .tab) in the "outputs" directory (or some other directory
specified via the "--outputs-dir" argument).
