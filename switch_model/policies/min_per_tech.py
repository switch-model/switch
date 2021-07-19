"""
This module allows defining a constraint that specifies a minimum buildout for a certain type of gen_tech.

The advantage of this module is that it stills allows switch to decide where to place
the specified technology.
"""
import os

from pyomo.environ import *

from switch_model.reporting import write_table


def define_components(mod):
    mod.GEN_TECH_PER_PERIOD = Set(
        initialize=lambda m: m.GENERATION_TECHNOLOGIES * m.PERIODS,
        dimen=2,
        doc="Set of generation technologies and periods",
    )

    mod.minimum_capacity_mw = Param(
        mod.GEN_TECH_PER_PERIOD,
        within=NonNegativeReals,
        default=0,
        doc="The minimum amount of capacity for a period and generation technology",
    )

    mod.minimum_energy_capacity_mwh = Param(
        mod.GEN_TECH_PER_PERIOD,
        within=NonNegativeReals,
        default=0,
        doc="The minimum amount of energy capacity for a period and generation technology (only considers storage)",
    )

    mod.GenCapacityPerTech = Expression(
        mod.GEN_TECH_PER_PERIOD,
        rule=lambda m, tech, p: sum(
            m.GenCapacity[g, p] for g in m.GENS_BY_TECHNOLOGY[tech]
        ),
        doc="The amount of power capacity for a period and technology.",
    )

    mod.GenEnergyCapacityPerTech = Expression(
        mod.GEN_TECH_PER_PERIOD,
        rule=lambda m, tech, p: sum(
            m.StorageEnergyCapacity[g, p]
            for g in m.STORAGE_GENS
            if m.gen_tech[g] == tech
        ),
        doc="The amount of energy capacity for a period and technology (only considers storage from the storage module).",
    )

    power_scaling_factor = 1e-4

    mod.Enforce_Minimum_Capacity_Per_Tech = Constraint(
        mod.GEN_TECH_PER_PERIOD,
        rule=lambda m, tech, p: Constraint.Skip
        if m.minimum_capacity_mw[tech, p] == 0
        else m.GenCapacityPerTech[tech, p] * power_scaling_factor
        >= m.minimum_capacity_mw[tech, p] * power_scaling_factor,
        doc="Constraint enforcing that the power capacity > minimum",
    )

    energy_scaling_factor = 1e-5

    mod.Enforce_Minimum_Energy_Capacity_Per_Tech = Constraint(
        mod.GEN_TECH_PER_PERIOD,
        rule=lambda m, tech, p: Constraint.Skip
        if m.minimum_energy_capacity_mwh[tech, p] == 0
        else m.GenEnergyCapacityPerTech[tech, p] * energy_scaling_factor
        >= m.minimum_energy_capacity_mwh[tech, p] * energy_scaling_factor,
        doc="Constraint enforcing that the energy capacity > minimum",
    )


def load_inputs(mod, switch_data, inputs_dir):
    """
    Expected input file:

     min_per_tech.csv with the following format:
         gen_tech,period,minimum_capacity_mw,minimum_energy_capacity_mwh
         Nuclear,2040,10,.
    """
    switch_data.load_aug(
        filename=os.path.join(inputs_dir, "min_per_tech.csv"),
        param=(mod.minimum_capacity_mw, mod.minimum_energy_capacity_mwh),
        auto_select=True,
        # We want this module to run even if we don't specify a constraint so we still get the useful outputs
        optional=True,
        optional_params=(mod.minimum_capacity_mw, mod.minimum_energy_capacity_mwh),
    )


def post_solve(mod, outdir):
    write_table(
        mod,
        mod.GEN_TECH_PER_PERIOD,
        output_file=os.path.join(outdir, "gen_cap_per_tech.csv"),
        headings=(
            "gen_tech",
            "period",
            "gen_capacity",
            "minimum_capacity_mw",
            "energy_capacity",
            "minimum_energy_capacity_mwh",
        ),
        values=lambda m, tech, p: (
            tech,
            p,
            m.GenCapacityPerTech[tech, p],
            m.minimum_capacity_mw[tech, p],
            m.GenEnergyCapacityPerTech[tech, p],
            m.minimum_energy_capacity_mwh[tech, p],
        ),
    )
