# Introduction

This repository contains code and example files for the Switch power system
planning model. Switch is written in the Python language and several other
open-source projects (notably Pyomo, Pandas and glpk). The instructions below
show you how to install  these components on a Linux, Mac or Windows computer.

We recommend that you use the Anaconda scientific computing environment to
install and run Switch. This provides an easy, cross-platform way to install
most of the resources that Switch needs, and it avoids interfering with your
system's built-in Python installation (if present). The instructions below
assume you will use the Anaconda distribution. If you prefer to use a different
distribution, you will need to adjust the instructions accordingly. In
particular, it is possible to install Switch and most of its dependencies using
the pip package manager if you have that installed and working well, but you
will need to do additional work to install glpk or coincbc, and possibly git.


# Install Conda and Python

Download and install Miniconda from
https://docs.conda.io/en/latest/miniconda.html or Anaconda from
https://www.anaconda.com/distribution . We recommend using the 64-bit version
with Python 3.7. Anaconda and Miniconda install a similar environment, but
Anaconda installs more packages by default and Miniconda installs them as
needed.

Note that you do not need administrator privileges to install the Windows Conda
environment or add packages to it if you select the option to install "just for
me".

If you want, this is a good point to create an Conda environment specifically
for using or testing Switch. See here for more details:
https://docs.conda.io/projects/conda/en/latest/user-guide/tasks/manage-environments.html


# Install Switch and its Dependencies

After installing Anaconda or Miniconda, open an Anaconda Command Prompt
(Windows) or Terminal.app (Mac) and type the following command:

    conda install -c conda-forge switch_model

This will install the `switch` command line utility, along with various software
used by Switch (the Pyomo optimization framework, Pandas data manipulation
framework and glpk numerical solver).

If you would also like to enable automatic output graphs, run this command:

    conda install -c conda-forge ggplot

If you would like to try the coincbc solver instead of glpk, you can run this
command:

    conda install coincbc

If you plan to use the iterative demand response model with a custom, nonlinear
demand system, then you should add these packages:

    conda install rpy2 scipy

At this point, you can solve example models or your own power system models.
See README for more information.


# View Examples

If you want to view the Switch source code and examples, you can find them at
https://github.com/switch-model/switch. You can browse these online or clone them to a local repository (see below if you'd like to run Switch directly from a local repository).


# Install a Proprietary Solver (Optional)

To solve larger models, you will need to install the cplex or gurobi solvers,
which are an order of magnitude faster than glpk or coincbc. Both of these have
free trials available, and are free long-term for academics. You can install
one of these now or after you install Switch. More information on these solvers
can be found at the following links:

Professional:
- https://www.gurobi.com/products/gurobi-optimizer/
- https://www.ibm.com/products/ilog-cplex-optimization-studio/pricing

Academic:
- https://www.gurobi.com/academia/
- https://developer.ibm.com/docloud/blog/2019/07/04/cplex-optimization-studio-for-students-and-academics/

For any meaningful-sized problem, you will need the unlimited-size versions of
these solvers, which will require either purchasing a license, using a
time-limited trial version, or using an academic-licensed version. The
small-size free or community versions (typically 1000 variables and constraints)
will not be enough for any realistic model.


# Developer Installation (Optional)

Many people find it useful to browse and edit a "live" installation of Switch
that they also use to solve models. This supports a number of activities:

- reading the documentation built into the switch_model modules
- reading the source code of the modules to understand the details of how Switch
  works
- updating Switch or fixing bugs to meet local needs or contribute to the main
  repository
- setting breakpoints for debugging
- switching between different versions of Switch
- trying pre-release branches of Switch

To work this way, first install Switch as described above (this will install all
the Switch dependencies, even though you will later reinstall Switch itself).
Then, in a terminal window or Anaconda command prompt Anaconda command prompt,
use the `cd` and `mkdir` commands to create and/or enter the directory where you
would like to store the Switch model code and examples. Once you are in that
directory, run the following commands (don't type the comments that start with
'#'):

    # Install git software manager.
    conda install git

    # Download Switch to a directory called `switch`.
    git clone https://github.com/switch-model/switch.git

    # Uninstall the previous copy of Switch and tell Python to use this one
    # instead. Note that Python will always load switch_model directly from this
    # directory, so you can edit it as needed and Python will see the changes.
    cd switch
    pip install --upgrade --editable .

    # Run tests (optional)
    python run_tests.py

    # View switch_model code (optional)
    cd switch_model
    ls
    cd ..

    # View or run examples (optional)
    cd examples
    ls
    cd <example dir>
    switch solve

After this, you can pull the latest version of the Switch code and examples from
the main Switch repository at any time by launching a Terminal window or
Anaconda prompt, then cd'ing into the 'switch' directory and running this
command:

    git pull

This will attempt to merge your local changes with changes with changes in the main
repository. If there are any conflicts, you should follow the instructions given
by the git command to resolve them.
