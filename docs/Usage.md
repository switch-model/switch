# Usage

## Prerequistes

1. Install [Python](https://www.python.org/downloads/) (at least version 3.8). You need
   Python since the entire model is written in Python and is run through Python.

2. Install [Gurobi](https://www.gurobi.com/downloads/gurobi-optimizer-eula/) or another
   solver (e.g. GPLK). Gurobi requires applying for a free academic license on their website.

3. Install [Anaconda](https://www.anaconda.com/products/individual) (or [miniconda](https://docs.conda.io/en/latest/miniconda.html)
   for a lightweight version that works just the same). Anaconda allows you to work
   in multiple virtual environments which is often helpful. You can also use Python's built-in
   `venv` package.

4. Install [Git](https://git-scm.com/) (you can learn more about Git [here](https://www.git-scm.com/doc)).

## Install

1. Clone this repository to your computer:`git clone https://github.com/REAM-lab/switch`

2. Navigate to the repository: `cd switch`.

3. Create a Python virtual environment from where you'll run Switch: `conda create --name switch`.

4. Activate the newly created environment: `conda activate switch`.

5. Install the `switch_model` library using: `pip install --editable .[dev]`. Note
   the `--editable` flag indicating that the `switch` command will always use your latest local
   copy. That is, you don't need to reinstall the package after making a change to it.

6. Run `switch --help` to make sure your package installed properly.