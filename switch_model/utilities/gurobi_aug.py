"""
This file defines an augmented Gurobi solver interface which support warm starting for linear
programs. It extends Pyomo's GurobiDirect solver interface but adds the option to a) output
a pickle file containing the data needed to warm start a future run and b) load a warm start
file previously outputed to warm_start the current run.

A few important notes:

- Warm starting works best when all the variables and constraints existed in the previous run (that you're warm starting from)
- Warm starting only works with Gurobi's simplex method ("method=1")
- There are two modes to warm start. Both modes are supported.
    1) Warm staring from the simplex results. This is faster but only available if the previous run finished with Simplex (i.e. had crossover)
    2) Warm starting from the dual/primal results.
- By default we try to use the simplex mode if it is available.
"""
import warnings
from typing import List, Optional, Dict

import numpy as np
import pickle

from pyomo.solvers.plugins.solvers.gurobi_direct import GurobiDirect
from pyomo.environ import *

from switch_model.utilities import StepTimer, catch_exceptions


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
        self._names_buffer: Dict = {}  # Used to help save_component run faster
        self._next_index: int = 0
        self.n: int = n

    def save_component(self, component, val):
        """Add a Pyomo Component (e.g. Variable Data) to our object for later pickling"""
        self._names[self._next_index] = component.getname(
            fully_qualified=True, name_buffer=self._names_buffer
        )
        self._vals[self._next_index] = val
        self._next_index += 1

    def _get_dict(self):
        """Creates a dictionary based on the _names and _vals arrays."""
        if self._dict is None:
            self._dict = {n: v for n, v in zip(self._names, self._vals)}
        return self._dict

    def get_component(self, component):
        """Retrieves a component from the data."""
        # Initialize the dictionary on the first call to this function
        return self._get_dict()[
            component.getname(fully_qualified=True, name_buffer=self._names_buffer)
        ]

    def __getstate__(self):
        """Return value is what gets pickled."""
        if self._next_index != self.n:
            warnings.warn(
                "Pickling more data than necessary, n is greater than the number of components stored"
            )
        return (
            np.array(self._names),
            self._vals,
        )  # Note, we cast self._names to a numpy array to save space.

    def __setstate__(self, state):
        """Called when restoring the object from a pickle file."""
        self._names, self._vals = state
        self._dict = None
        self._names_buffer = {}

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

    def get_component(self, component):
        return -1 if super(CBasis, self).get_component(component) else 0


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

    def get_component(self, component):
        return int(super(VBasis, self).get_component(component)) * -1


class WarmStartData:
    """Data that gets pickled"""

    def __init__(self, var_data, const_data, use_c_v_basis):
        self.var_data = var_data
        self.const_data = const_data
        self.use_c_v_basis = use_c_v_basis


@SolverFactory.register(
    "gurobi_aug", doc="Python interface to Gurobi that supports LP warm starting"
)
class GurobiAugmented(GurobiDirect):
    CBASIS_DEFAULT = 0  # Corresponds to a basic constraint
    VBASIS_DEFAULT = 0  # Corresponds to a basic variable

    def _presolve(self, *args, **kwds):
        """Allows three additional parameters to be specified when calling solve()

        @param write_warm_start: file path of where the output warm start pickle file should be written
        @param read_warm_start: file path of where to read the input warm start pickle file
        @param save_c_v_basis: If true, we save the c_v_basis. if False we save the dual start end
        """
        self._write_warm_start = kwds.pop("write_warm_start", None)
        self._read_warm_start = kwds.pop("read_warm_start", None)
        self._save_c_v_basis = kwds.pop("save_c_v_basis", None)
        # Note we don't need to modify solver_symbolic_labels since we are working with Pyomo Var names, not Gurobi
        return super(GurobiAugmented, self)._presolve(*args, **kwds)

    def _warm_start(self):
        """Override the default _warm_start function that only works for MIP."""
        if self._solver_model.IsMIP:
            return super(GurobiAugmented, self)._warm_start()

        time = StepTimer(msg="Loading warm start data...")
        if self._read_warm_start is None:
            raise Exception("Must specify warm_start_in= when running solve()")

        # For some reason this is required. Without it warnings get thrown.
        # It seems like to set VBasis/CBasis the variables needs to already be in
        # the Gurobi model (hence why we need to call update()).
        self._update()

        # Load the basis information from a previous pickle file
        with open(self._read_warm_start, "rb") as f:
            warm_start_data = pickle.load(f)

        # Keep track of any variables or constraints that weren't in the pickle file
        error = None
        error_count = 0
        # Specify which Gurobi Attributes we should set depending on whether we are using C/V Basis or P/D Start.
        if warm_start_data.use_c_v_basis:
            var_attr = self._gurobipy.GRB.Attr.VBasis
            const_attr = self._gurobipy.GRB.Attr.CBasis
            var_default = GurobiAugmented.VBASIS_DEFAULT
            const_default = GurobiAugmented.CBASIS_DEFAULT
        else:
            var_attr = self._gurobipy.GRB.Attr.PStart
            const_attr = self._gurobipy.GRB.Attr.DStart
            var_default = 0
            const_default = 0
        # Set the VBasis or PStart for each variable
        for pyomo_var, gurobi_var in self._pyomo_var_to_solver_var_map.items():
            try:
                val = warm_start_data.var_data.get_component(pyomo_var)
            except KeyError as e:
                val, error = var_default, e
                error_count += 1
            gurobi_var.setAttr(var_attr, val)

        # Set the CBasis or DStart for each constraint
        for pyomo_const, gurobi_const in self._pyomo_con_to_solver_con_map.items():
            try:
                val = warm_start_data.const_data.get_component(pyomo_const)
            except KeyError as e:
                val, error = const_default, e
                error_count += 1
            gurobi_const.setAttr(const_attr, val)

        if error is not None:
            warnings.warn(
                f"{error} and {error_count - 1} others were not found in warm start pickle file. "
                f"If many variables or constraints are not found it may be more efficient to not use --warm-start."
            )

        print(f"Time spent warm starting: {time.step_time_as_str()}")

    def _postsolve(self):
        """
        Called after solving. Add option to output the VBasis/CBasis information to a pickle file.
        """
        results = super(GurobiAugmented, self)._postsolve()
        if self._write_warm_start is not None:
            if self._solver_model.IsMIP:
                warnings.warn(
                    "--save-warm-start doesn't work for MIP models. Not creating a .pickle file."
                )
            else:
                timer = StepTimer(msg="Saving results to warm_start.pickle...")
                self._save_warm_start(self._save_c_v_basis)
                print(f"Created warm start pickle file in {timer.step_time_as_str()}")
        return results

    @catch_exceptions(warning_msg="Failed to save warm start information.")
    def _save_warm_start(self, save_c_v_basis):
        """Create a pickle file containing the CBasis/VBasis information."""
        # Setup our data objects
        n_var = len(self._pyomo_var_to_solver_var_map)
        n_const = len(self._pyomo_con_to_solver_con_map)

        if save_c_v_basis is None:
            save_c_v_basis = True

        if save_c_v_basis:
            var_data = VBasis(n=n_var)
            const_data = CBasis(n=n_const)
            var_attr = self._gurobipy.GRB.Attr.VBasis
            const_attr = self._gurobipy.GRB.Attr.CBasis
        else:
            var_data = PicklableData(n=n_var, val_dtype=float)
            const_data = PicklableData(n=n_const, val_dtype=float)
            var_attr = self._gurobipy.GRB.Attr.X
            const_attr = self._gurobipy.GRB.Attr.Pi

        try:
            # Save the variable data
            for pyomo_var, gurobipy_var in self._pyomo_var_to_solver_var_map.items():
                var_data.save_component(pyomo_var, gurobipy_var.getAttr(var_attr))
        except AttributeError as e:
            if save_c_v_basis:
                # If we get an Attribute error and using c_v_basis it's probably cause
                # there was no crossover. In this case we retry without c_v_basis
                return self._save_warm_start(save_c_v_basis=False)
            raise e

        # Save the constraint data
        for pyomo_const, gurobipy_const in self._pyomo_con_to_solver_con_map.items():
            const_data.save_component(pyomo_const, gurobipy_const.getAttr(const_attr))

        # Dump the data to a pickle file
        with open(self._write_warm_start, "wb") as f:
            data = WarmStartData(var_data, const_data, save_c_v_basis)
            pickle.dump(data, f)
