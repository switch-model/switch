"""
This file defines an augmented Gurobi solver interface which support warm starting for linear
programs. It extends Pyomo's GurobiDirect solver interface but adds the option to a) output
a pickle file containing the data needed to warm start a future run and b) load a warm start
file previously outputed to warm_start the current run.

Note that warm starting only works if all variables are the same between both runs.
"""
import warnings
from typing import List, Optional, Dict

import numpy as np
import pickle

from pyomo.solvers.plugins.solvers.gurobi_direct import GurobiDirect
from pyomo.environ import *

from switch_model.utilities import StepTimer


class PicklableData:
    """
    A class that is used to store and retrieve the VBasis and CBasis values
    for warm starting.

    By leveraging numpy arrays, the class takes little space when pickled.
    It stores a mapping of component names to values.
    """

    def __init__(self, n, val_dtype):
        """
        @param n: The number of elements in the mapping.
        @param val_dtype: The numpy data type of the values.
        """
        self._names: List[str] = [""] * n  # Initialize as empty string array
        self._vals = np.empty(n, dtype=val_dtype)
        self._dict: Optional[Dict[str, val_dtype]] = None
        self.i: int = 0
        self.n: int = n

    def save_component(self, component, val):
        self._names[self.i] = component.name
        self._vals[self.i] = val
        self.i += 1

    def _get_dict(self):
        """Creates a dictionary based on the _names and _vals arrays."""
        return {n: v for n, v in zip(self._names, self._vals)}

    def load_component(self, component):
        """Retrieves a component from the data."""
        if self._dict is None:
            self._dict = self._get_dict()

        return self._dict[component.name]

    def __getstate__(self):
        """Return value is what gets pickled."""
        if self.i != self.n:
            warnings.warn("Pickling more data than necessary, n is greater ")
        return (
            np.array(self._names),
            self._vals,
        )  # Note, we cast self._names to a numpy array to save space.

    def __setstate__(self, state):
        """Called when restoring the object from a pickle file."""
        self._names, self._vals = state
        self._dict = None

    def __repr__(self):
        return str(self._get_dict())


class CBasis(PicklableData):
    """
    Small wrapper around PicklableData that sets the type as bool.
    This is because the parameter CBasis can either be 0 (False) or -1 (True).
    Note that when loading the component back from the file we unconvert the bool into 0 or -1.
    """

    def __init__(self, n):
        super(CBasis, self).__init__(n, val_dtype="bool")

    def load_component(self, component):
        return -1 if super(CBasis, self).load_component(component) else 0


class VBasis(PicklableData):
    """
    Small wrapper around PicklableData that sets the type to uint8.
    This is because the parameter VBasis can either any value between -3 and 0 (incl.).
    As such we multiply the value by -1 and then cast it into a uint8 element to save space.
    """

    def __init__(self, n):
        super(VBasis, self).__init__(n, val_dtype="uint8")

    def save_component(self, component, val):
        return super(VBasis, self).save_component(component, val * -1)

    def load_component(self, component):
        return int(super(VBasis, self).load_component(component)) * -1


@SolverFactory.register(
    "gurobi_aug", doc="Python interface to Gurobi that supports LP warm starting"
)
class GurobiAugmented(GurobiDirect):
    CBASIS_DEFAULT = 0  # Corresponds to a basic constraint
    VBASIS_DEFAULT = 0  # Corresponds to a basic variable

    def _presolve(self, *args, **kwds):
        """Simply allows a warm_start_in and warm_start_out file to be specified."""
        self._warm_start_in = kwds.pop("warm_start_in", None)
        self._warm_start_out = kwds.pop("warm_start_out", None)
        return super(GurobiAugmented, self)._presolve(*args, **kwds)

    def _warm_start(self):
        """Override the default _warm_start function that only works for MIP."""
        if self._solver_model.IsMIP:
            return super(GurobiAugmented, self)._warm_start()

        time = StepTimer()
        if self._warm_start_in is None:
            raise Exception("Must specify warm_start_in= when running solve()")

        # For some reason this is required. Without it warnings get thrown.
        # It seems like to set VBasis/CBasis the variables needs to already be in
        # the Gurobi model (hence why we need to call update()).
        self._update()

        # Read the previous basis information
        with open(self._warm_start_in, "rb") as f:
            cbasis, vbasis = pickle.load(f)

        error = None
        # Load the VBasis for each variable
        for pyomo_var, gurobi_var in self._pyomo_var_to_solver_var_map.items():
            try:
                gurobi_var.VBasis = vbasis.load_component(pyomo_var)
            except KeyError as e:
                error = e
                gurobi_var.VBasis = GurobiAugmented.VBASIS_DEFAULT

        # Load the CBasis for each constraint
        for pyomo_const, gurobi_const in self._pyomo_con_to_solver_con_map.items():
            try:
                gurobi_const.CBasis = cbasis.load_component(pyomo_const)
            except KeyError as e:
                error = e
                gurobi_const.CBasis = GurobiAugmented.CBASIS_DEFAULT

        if error is not None:
            warnings.warn(
                f"{error} (and maybe others) were not found in warm_start.pickle. If you expect multiple variables and constraints"
                f" to not be found in warm_start.pickle, it may be more efficient to not use --warm-start."
            )

        print(f"Time spent warm starting: {time.step_time_as_str()}")

    def _postsolve(self):
        """
        Called after solving. Add option to output the VBasis/CBasis information to a pickle file.
        """
        results = super(GurobiAugmented, self)._postsolve()
        if self._warm_start_out is not None:
            self._save_warm_start()
        return results

    def _save_warm_start(self):
        """Create a pickle file containing the CBasis/VBasis information."""
        timer = StepTimer()
        # Create the VBasis data class
        vbasis = VBasis(n=len(self._pyomo_var_to_solver_var_map))
        for pyomo_var, gurobipy_var in self._pyomo_var_to_solver_var_map.items():
            vbasis.save_component(pyomo_var, gurobipy_var.VBasis)

        # Create the CBasis data class
        cbasis = CBasis(n=len(self._pyomo_con_to_solver_con_map))
        for pyomo_const, gurobipy_const in self._pyomo_con_to_solver_con_map.items():
            cbasis.save_component(pyomo_const, gurobipy_const.CBasis)

        # Save both to a pickle file
        with open(self._warm_start_out, "wb") as f:
            pickle.dump((cbasis, vbasis), f)

        print(f"Created 'warm_start.pickle' in {timer.step_time_as_str()}")
