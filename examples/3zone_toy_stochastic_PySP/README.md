################################
# Introduction

This example illustrates the use of the PySP module of Pyomo for formulating
and solving stochastic optimization problems. It is recommended that the user
first consult the available documentation online before jumping into these
examples.

Watson, J. P., Woodruff, D. & Hart, W. (2012). PySP: modeling and solving
stochastic programs in Python. Mathematical Programming Computation 4(2).
Available at: http://mpc.zib.de/index.php/MPC/article/viewFile/85/39

Pyomo Online Documentation:
https://software.sandia.gov/downloads/pub/pyomo/PyomoOnlineDocs.html

If any concepts on stochastic programming need to be acquired or refreshed, a
good reference is:  Birge, J. R. & Louveaux, F. (2011). Introduction to
Stochastic Programming. 2nd Edition. Springer Science+Business Media.

################################
# File explanations

In order for PySP to formulate the stochastic problems some files are required.

ReferenceModel.py
    This script will be loaded as a module by the runef and runph algorithms and
    must create a Pyomo model object named "model". In the case of Switch, this
    is done importing the Utilities module and using its define_AbstractModel
    function. This requires the specification of the inputs directory, since
    command line options are not yet supported in this initial version.
    In this example, the model object is augmented with expressions that sum the
    investment and operations cost, which coincide with annual and timepoint
    costs when the fuel_markets module is not loaded. These expressions may be
    changed at will, as long as they represent total costs at each stage. Both
    runef and runph need to be given either a Var or an Expr object which sums
    up costs in each stage.

PySPInputGenerator.py
    This script builds the .dat files required by PySP to formulate the scenario
    tree and the stochastic problem. Some problem-specific parameters must be
    inputted in this script, such as the names of the stages, variables and
    scenarios. A model object will be created and instantiated with a set of
    deterministic inputs that must be provided, so that these parameters are
    saved on the RootNode.dat file. This nodal approach of specifying data
    avoids redundancies so that only parameters that are subject to uncertainty
    must be re-defined in branch and leaf nodes. The other generated file is
    ScenarioStructure.dat, which specifies the structure of the stochastic
    problem. Further documentation on the construction of these files is located
    inside this script. Note: branch and leaf node .dat files are not generated
    by this file, they must be built by the user.
    You may execute this script with the SWITCH command line option
    "--sorted-output" (without quotes) to get a sorted .dat file.

rhosetter.py
    When using the progressive hedging algorithm a value for the Rho parameter
    -which affects the value of W, a pseudo-dual variable that forces the non-
    anticipativity constraints- may be set by default for all variables and 
    scenarios. But, a script may be indicated so that Rho is set per variable
    and per scenario, which (if tuned correctly for the specific problem at
    hand) may accelerate and improve convergence. Rhosetter.py uses a cost
    proportional strategy such as is described in Watson, J. P., & Woodruff, 
    D. L.  (2011). Progressive hedging innovations for a class of stochastic  
    mixed-integer resource allocation problems. Computational  Management Science.
    To achieve this, the objective function expression is parsed to obtain the
    cost coefficient of each variable and its Rho is set to that value.

rhosetter-FS-only.py
    For problems bigger than trivial examples, the rho setting process may start
    taking significant time. This can be avoided by setting custom rho values only
    for variables that are located in the root node or in the branch nodes. Leaf
    node variables are not subject to non-anticipativity constraints, so leaving
    their rho values as the default will have no effect on the algorithm or the 
    solution, except reducing rho setting time. This particular rhosetter script
    is tailored for a two stage problem. Also, the model must have an expression 
    that sums the first stage costs.  

################################
# Running the example

First, the scenario tree inputs must be built. For this, the PySPInputGenerator.py
script must be executed. This script will build the following input files for the 
stochastic simulation:

ScenarioStructure.dat
    This file specifies the node and scenario names and probabilities in the
    scenario tree.
RootNode.dat
    This file contains every parameter and set specified in .dat format at the
    root node.

To run this script, the following command must be executed. Inside the script a
default relative inputs directory is specified, with a default value of "inputs".
In this directory, a complete set of .tab files specifying all parameters and sets
from the deterministic version of the model must be found. This path may be manually 
changed to fit the user's directory structure.

    >>>python PySPInputGenerator.py

After this, nodal .dat files may be constructed specifying uncertain parameter 
values. In this example, a simple scenario tree with a root node -where investment
decisions are made- and 3 leaf nodes -where operations take place- is presented.
Each scenario represents a realization of fuels prices, for which example .dat
files are provided.

Once the scenarios are defined, the problem may be solved either by an extensive 
form formulation -EF- or by the progressive hedging algorithm -PH-.

############################
# Extensive Formulation (EF) 

The runef script has multiple options. Refer to PySP documentation for more
specifications. A simple and effective way of solving this example problem is to 
execute the following command from the /3zone_toy_stochastic_PySP directory:

    >>>runef --model-location=. --instance-directory=inputs/pysp_inputs --solve \
        --solver=glpk --output-solver-log --output-times --traceback \
        --solution-writer=pyomo.pysp.plugins.csvsolutionwriter

The model directory needs to contain the ReferenceModel.py file; in this example
it is a period - the relative path to the current directory.

The instance directory needs to contain the .dat files generated by
PySPInputGenerator.py, in addition to the manually-constructed .dat files
named after each scenario: HighFuelCosts.dat, LowFuelCosts.dat, and 
MediumFuelCosts.dat in this example.

The solver may be any solver that can handle the deterministic version of the problem 
and is installed in the machine. In this example, Gurobi - a solver with free 
licenses for students - was used to solve the optimization problem produce the outputs.
A default option of GLPK is written in this example command, because it is a free
solver for any user.

The other options send additional output information to the terminal when running 
the algorithm. The solution writer is a useful plugin which writes CSV files with 
the stochastic problem's solutions. All variable values at optimum are printed in
ef.csv, while in CostVarDetail.csv a summary of stage and nodal costs is written.

Note: If runef is run without options for solving (--solve and --solver), then 
an extensive formulation of the problem is printed in an .lp file (can be set 
to .nl format as well). The user could then later apply a solver and obtain solutions.

##########################
# Progressive Hedging (PH)

The runph script has multiple options. Refer to PySP documentation for more
specifications. One way of solving a problem is to execute the following command:

    >>>runph --model-location=. --instance-directory=inputs/pysp_inputs \
        --solver=gurobi --default-rho=1000.0 --traceback --rho-cfgfile=rhosetter.py \
        --solution-writer=pyomo.pysp.plugins.csvsolutionwriter \
        --output-scenario-tree-solution

Note: In this command, the solver must be able to solve problems with non-linear
terms in the objective function. Gurobi is a solver with free licenses for
students that can handle such non linear proximity term. Cplex is another option
with similar availability for students. 

If only linear solvers are available, then the quadratic term in the PH
algorithm objective function may be linearized by runph with the option
--linearize-nonbinary-penalty-terms=PIECES, with PIECES indicating the number of
lines segments in the linearized function. To use this option, all variables in
the proximity term must have lower and upper bounds in order for the algorithm
to create the piecewise linear function. If variables do not have upper and
lower bounds set in the core mathematical model, bounds can be added in a
configuration file which is named pha_bounds_cfg.py in this example. To run
progressive hedging with a linear solver such as glpk, use the following command:

    >>>runph --model-location=. --instance-directory=inputs/pysp_inputs \
        --solver=glpk --default-rho=1000.0 --traceback \
        --rho-cfgfile=rhosetter.py \
        --solution-writer=pyomo.pysp.plugins.csvsolutionwriter \
        --output-scenario-tree-solution --linearize-nonbinary-penalty-terms=5 \
        --bounds-cfgfile=pha_bounds_cfg.py

Note that the solutions from a linearized approximation will not be numerically
equivalent to the quadratic solution. The obtained investment and operational
decisions are similar, but slightly different.

Another equivalent way of solving this example is to run the command:

    >>>runph --model-location=. --instance-directory=inputs/pysp_inputs \
        --solver=gurobi --default-rho=1000.0 --traceback \
        --rho-cfgfile=rhosetter-FS-only.py \
        --solution-writer=pyomo.pysp.plugins.csvsolutionwriter \
        --output-scenario-tree-solution

This will set Rho values only for first stage variables, thus decreasing the
model formulation time. Refer to documentation inside each of the rhosetter
scripts for further details on implementation and customization.


################################
# Inputs and outputs

The example input files provided formulate a 4 node scenario tree, with a root
noot representing investment decisions and 3 leaf nodes for different fuel cost
scenarios.

LowFuelCosts: All carbon based fuels that are used by projects have their prices
halved.
MediumFuelCosts: Prices are the same as in the deterministic formulation.
HighFuelCosts: Prices are doubled from their deterministic values.

Note: MediumFuelCosts.dat is empty, since all its parameters present the same
value as the deterministic formulation, which has all of its inputs printed
in the root node .dat file.

Outputs are provided for all the described commands. These include both the
solution files written by the plugin and the standard output that PySP sends
to the terminal, for reference. These runs were perfomed on a desktop computer
and used the solver Gurobi.
