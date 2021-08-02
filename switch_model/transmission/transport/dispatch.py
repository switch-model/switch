# Copyright (c) 2015-2019 The Switch Authors. All rights reserved.
# Licensed under the Apache License, Version 2.0, which is in the LICENSE file.

"""
Defines model components to describe transmission dispatch for the
Switch model.
"""

from pyomo.environ import *

import os
from switch_model.reporting import write_table
from switch_model.tools.graph import graph

dependencies = (
    "switch_model.timescales",
    "switch_model.balancing.load_zones",
    "switch_model.financials",
    "switch_model.transmission.transport.build",
)


def define_components(mod):
    """

    Adds components to a Pyomo abstract model object to describe the
    dispatch of transmission resources in an electric grid. This
    includes parameters, dispatch decisions and constraints. Unless
    otherwise stated, all power capacity is specified in units of MW,
    all energy amounts are specified in units of MWh, and all sets and
    parameters are mandatory.

    TRANS_TIMEPOINTS describes the scope that transmission dispatch
    decisions must be made over. It is defined as the set of
    DIRECTIONAL_TX crossed with TIMEPOINTS. It is indexed as
    (load_zone_from, load_zone_to, timepoint) and may be abbreviated as
    [z_from, zone_to, tp] for brevity.

    DispatchTx[z_from, zone_to, tp] is the decision of how much power
    to send along each transmission line in a particular direction in
    each timepoint.

    Maximum_DispatchTx is a constraint that forces DispatchTx to
    stay below the bounds of installed capacity.

    TxPowerSent[z_from, zone_to, tp] is an expression that describes the
    power sent down a transmission line. This is completely determined by
    DispatchTx[z_from, zone_to, tp].

    TxPowerReceived[z_from, zone_to, tp] is an expression that describes the
    power sent down a transmission line. This is completely determined by
    DispatchTx[z_from, zone_to, tp] and trans_efficiency[tx].

    TXPowerNet[z, tp] is an expression that returns the net power from
    transmission for a load zone. This is the sum of TxPowerReceived by
    the load zone minus the sum of TxPowerSent by the load zone.

    """

    mod.TRANS_TIMEPOINTS = Set(
        dimen=3, initialize=lambda m: m.DIRECTIONAL_TX * m.TIMEPOINTS
    )
    mod.DispatchTx = Var(mod.TRANS_TIMEPOINTS, within=NonNegativeReals)

    mod.Maximum_DispatchTx = Constraint(
        mod.TRANS_TIMEPOINTS,
        rule=lambda m, zone_from, zone_to, tp: (
            m.DispatchTx[zone_from, zone_to, tp]
            <= m.TxCapacityNameplateAvailable[
                m.trans_d_line[zone_from, zone_to], m.tp_period[tp]
            ]
        ),
    )

    mod.TxPowerSent = Expression(
        mod.TRANS_TIMEPOINTS,
        rule=lambda m, zone_from, zone_to, tp: (m.DispatchTx[zone_from, zone_to, tp]),
    )
    mod.TxPowerReceived = Expression(
        mod.TRANS_TIMEPOINTS,
        rule=lambda m, zone_from, zone_to, tp: (
            m.DispatchTx[zone_from, zone_to, tp]
            * m.trans_efficiency[m.trans_d_line[zone_from, zone_to]]
        ),
    )

    def TXPowerNet_calculation(m, z, tp):
        return sum(
            m.TxPowerReceived[zone_from, z, tp]
            for zone_from in m.TX_CONNECTIONS_TO_ZONE[z]
        ) - sum(
            m.TxPowerSent[z, zone_to, tp] for zone_to in m.TX_CONNECTIONS_TO_ZONE[z]
        )

    mod.TXPowerNet = Expression(
        mod.LOAD_ZONES, mod.TIMEPOINTS, rule=TXPowerNet_calculation
    )
    # Register net transmission as contributing to zonal energy balance
    mod.Zone_Power_Injections.append("TXPowerNet")


def post_solve(instance, outdir):
    write_table(
        instance,
        instance.TRANS_TIMEPOINTS,
        headings=(
            "load_zone_from",
            "load_zone_to",
            "timestamp",
            "transmission_dispatch",
            "dispatch_limit",
            "transmission_limit_dual",
        ),
        values=lambda m, zone_from, zone_to, t: (
            zone_from,
            zone_to,
            m.tp_timestamp[t],
            m.DispatchTx[zone_from, zone_to, t],
            m.TxCapacityNameplateAvailable[
                m.trans_d_line[zone_from, zone_to], m.tp_period[t]
            ],
            m.get_dual(
                "Maximum_DispatchTx",
                zone_from,
                zone_to,
                t,
                divider=m.bring_timepoint_costs_to_base_year[t],
            ),
        ),
        output_file=os.path.join(outdir, "transmission_dispatch.csv"),
    )


@graph(
    "transmission_limit_duals",
    title="Transmission limit duals per period",
    note="Note: Outliers and zero-valued duals are ignored from box plot.",
)
def graph(tools):
    dispatch = tools.get_dataframe("transmission_dispatch")
    dispatch = tools.transform.timestamp(dispatch)
    dispatch["transmission_limit_dual"] = tools.pd.to_numeric(
        dispatch["transmission_limit_dual"], errors="coerce"
    )
    dispatch = dispatch[["transmission_limit_dual", "time_row"]]
    dispatch = dispatch.pivot(columns="time_row", values="transmission_limit_dual")
    # Multiply the duals by -1 since the formulation gives negative duals
    dispatch *= -1
    percent_of_zeroes = sum(dispatch == 0) / len(dispatch) * 100
    # Don't include the zero-valued duals.
    dispatch = dispatch.replace(0, tools.np.nan)
    if dispatch.count().sum() != 0:
        dispatch.plot.box(
            ax=tools.get_axes(note=f"{percent_of_zeroes:.1f}% of duals are zero"),
            xlabel="Period",
            ylabel="Transmission limit duals ($/MW)",
            showfliers=False,
        )
