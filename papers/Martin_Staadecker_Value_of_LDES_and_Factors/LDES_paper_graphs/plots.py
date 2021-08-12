import pandas as pd
from matplotlib import pyplot as plt
from matplotlib.pyplot import setp
from matplotlib.ticker import PercentFormatter

from switch_model.tools.graph.main import graph_scenarios, graph, Scenario

X_LABEL = "WECC-wide Storage Capacity (TWh)"


def set_styles(tools):
    tools.plt.rcParams['font.family'] = 'sans-serif'


@graph(
    "figure_1",
    supports_multi_scenario=True,
    title="Figure 1: The value of storage in the WECC",
    note="Panel 1: Shaded area represents the 25th to 75th percentile range"
         " for dual values.\nDual values for non-binding energy balance constraints"
         " are ignored."
)
def figure_1(tools):
    set_styles(tools)

    figure_size = (12, 12)
    fig = tools.get_figure(size=figure_size)
    axes = fig.subplots(2, 2)

    tools.plt.rcParams['lines.marker'] = '.'
    figure_1_panel_1(tools, axes[0][0])
    figure_1_panel_2(tools, axes[0][1])
    figure_1_panel_3(tools, axes[1][0])
    figure_1_panel_4(tools, axes[1][1])
    tools.plt.rcParams['lines.marker'] = None

    for row in axes:
        for ax in row:
            ax.set_xlabel(X_LABEL)


def figure_1_panel_1(tools, ax):
    df = tools.get_dataframe('load_balance.csv') \
        .rename({"normalized_energy_balance_duals_dollar_per_mwh": "value"}, axis=1)
    df = df[df.value != 0]
    load_balance_group = df \
        .groupby("scenario_name") \
        .value
    mean = load_balance_group.mean().rename("mean_val")
    upper = load_balance_group.quantile(0.75).rename("upper")
    lower = load_balance_group.quantile(0.25).rename("lower")
    df = pd.concat([lower, mean, upper], axis=1)
    # Convert from $/MWh to cents/kWh
    df *= 0.1

    x = df.index.values
    ax.plot(x, df.mean_val.values, color="black")
    ax.fill_between(x, df.lower.values, df.upper.values, alpha=0.5, color="gray")
    ax.set_ylabel("Mean Energy Balance Duals (cents/kWh)")


def figure_1_panel_2(tools, ax):
    # Read dispatch.csv
    df = tools.get_dataframe(
        'dispatch.csv',
        usecols=["gen_tech", "gen_energy_source", "Curtailment_MW", "is_renewable", "tp_weight_in_year_hrs"],
        na_filter=False,  # For performance
    )
    # Keep only renewable
    df = df[df["is_renewable"]]
    # Add the gen_type column
    df = tools.transform.gen_type(df)
    # Convert to GW
    df["value"] = df["Curtailment_MW"] * df["tp_weight_in_year_hrs"] / 1000
    df = df.groupby(["scenario_name", "gen_type"], as_index=False).value.sum()
    df = df.pivot(index="scenario_name", columns="gen_type", values="value")
    df /= 1000
    df = df.rename_axis("Technology", axis=1)
    df.plot(
        ax=ax,
        color=tools.get_colors(),
    )
    ax.set_ylabel("Yearly Curtailment (GWh)")


def figure_1_panel_3(tools, ax):
    df = tools.get_dataframe("transmission.csv", usecols=["BuildTx"], convert_dot_to_na=True)
    df = df.fillna(0).rename({"BuildTx": "value"}, axis=1)
    df = df.groupby("scenario_name").value.sum() / 1000
    df.plot(ax=ax, color="black")
    ax.set_ylim(0, 60)
    ax.set_ylabel("New Transmission Capacity Built (GW)")


def figure_1_panel_4(tools, ax):
    df = tools.get_dataframe("BuildGen.csv").rename(columns={
        "GEN_BLD_YRS_1": "GENERATION_PROJECT",
        "GEN_BLD_YRS_2": "period",
        "BuildGen": "value"
    })
    df = df[df.period == 2050]
    projects = tools.get_dataframe("generation_projects_info.csv", from_inputs=True, usecols=[
        "GENERATION_PROJECT", "gen_tech", "gen_energy_source"
    ]).drop("scenario_index", axis=1)
    df = df.merge(
        projects,
        on=["GENERATION_PROJECT", "scenario_name"],
        validate="one_to_one",
        how="left"
    ).drop("GENERATION_PROJECT", axis=1)
    del projects
    df = tools.transform.gen_type(df)
    df = df.rename({"GenCapacity": "value"}, axis=1)
    df = df.groupby(["scenario_name", "gen_type"], as_index=False).value.sum()
    df.value /= 1000
    df = df[df["gen_type"] != "Storage"]
    df = df[df.value != 0]
    df = df.pivot(index="scenario_name", columns="gen_type", values="value")
    df.loc["total", :] = df.sum()
    df = df.sort_values("total", axis=1)
    df = df.drop("total")
    df = df.rename_axis("Technology", axis=1)
    df.plot(
        ax=ax,
        kind="area",
        color=tools.get_colors(),
    )
    ax.set_ylabel("Newly Capacity Installations (GW)")


@graph(
    "figure_2",
    title="Figure 2: Generation Mix",
    supports_multi_scenario=True
)
def figure_2(tools):
    set_styles(tools)
    fig = tools.get_figure(size=(12, 12))
    ax1 = fig.add_subplot(3, 2, 1)
    ax2 = fig.add_subplot(3, 2, 2, sharey=ax1)
    ax3 = fig.add_subplot(3, 2, 3, sharey=ax1, sharex=ax1)
    ax4 = fig.add_subplot(3, 2, 4, sharey=ax1, sharex=ax2)
    ax5 = fig.add_subplot(3, 2, (5, 6))

    setp(ax2.get_yticklabels(), visible=False)
    setp(ax4.get_yticklabels(), visible=False)
    setp(ax1.get_xticklabels(), visible=False)
    setp(ax2.get_xticklabels(), visible=False)

    figure_2_energy_balance(tools, ax1, scenario_name=1.94)
    figure_2_energy_balance(tools, ax2, scenario_name=4)
    figure_2_energy_balance(tools, ax3, scenario_name=16)
    figure_2_energy_balance(tools, ax4, scenario_name=64)
    figure_2_panel_5(tools, ax5)
    handles, labels = ax1.get_legend_handles_labels()
    unique = [(h, l) for i, (h, l) in enumerate(zip(handles, labels)) if l not in labels[:i]]
    plt.figlegend(*zip(*unique))


def figure_2_panel_5(tools, ax):
    df = tools.get_dataframe("gen_cap.csv",
                             usecols=["gen_tech", "gen_energy_source", "GenCapacity"])
    df = tools.transform.gen_type(df)
    df = df.rename({"GenCapacity": "value"}, axis=1)
    df = df.groupby(["scenario_name", "gen_type"], as_index=False).value.sum()
    scaling = df[df["scenario_name"] == 1.94][["gen_type", "value"]].rename(columns={"value": "scaling"})
    df = df.merge(scaling, on="gen_type")
    df.value /= df.scaling
    df.value = (df.value - 1) * 100
    df = df[df["gen_type"].isin(("Wind", "Solar", "Biomass"))]
    df = df.pivot(index="scenario_name", columns="gen_type", values="value")
    df = df.rename_axis("Technology", axis=1)
    df.plot(
        ax=ax,
        color=tools.get_colors(),
        legend=False
    )
    ax.set_ylabel("Percent Change in Installed Capacity against Baseline")
    ax.yaxis.set_major_formatter(PercentFormatter())
    ax.set_xlabel(X_LABEL)


def filter_scenario(df, scenario_name):
    return df[df["scenario_name"] == scenario_name].drop(columns=["scenario_name", "scenario_index"]).copy()


def figure_2_energy_balance(tools, ax, scenario_name):
    # Get dispatch dataframe
    dispatch = tools.get_dataframe("dispatch.csv", usecols=[
        "timestamp", "gen_tech", "gen_energy_source", "DispatchGen_MW"
    ]).rename({"DispatchGen_MW": "value"}, axis=1)
    dispatch = filter_scenario(dispatch, scenario_name)
    dispatch = tools.transform.gen_type(dispatch)

    # Sum dispatch across all the projects of the same type and timepoint
    dispatch = dispatch.groupby(["timestamp", "gen_type"], as_index=False).sum()
    dispatch = dispatch[dispatch["gen_type"] != "Storage"]

    # Get load dataframe
    load = tools.get_dataframe("load_balance.csv", usecols=[
        "timestamp", "zone_demand_mw", "TXPowerNet"
    ])
    load = filter_scenario(load, scenario_name)

    def process_time(df):
        df = df.astype({"period": int})
        df = df[df["period"] == df["period"].max()].drop(columns="period")
        return df.set_index("datetime")

    # Sum load across all the load zones
    load = load.groupby("timestamp", as_index=False).sum()

    # Include Tx Losses in demand and flip sign
    load["value"] = (load["zone_demand_mw"] + load["TXPowerNet"]) * -1

    # Rename and convert from wide to long format
    load = load[["timestamp", "value"]]

    # Add the timestamp information and make period string to ensure it doesn't mess up the graphing
    dispatch = process_time(tools.transform.timestamp(dispatch))
    load = process_time(tools.transform.timestamp(load))

    # Convert to TWh (incl. multiply by timepoint duration)
    dispatch["value"] *= dispatch["tp_duration"] / 1e6
    load["value"] *= load["tp_duration"] / 1e6

    days = 14
    freq = str(days) + "D"
    offset = tools.pd.Timedelta(freq) / 2

    def rolling_sum(df):
        df = df.rolling(freq, center=True).value.sum().reset_index()
        df["value"] /= days
        df = df[(df.datetime.min() + offset < df.datetime) & (df.datetime < df.datetime.max() - offset)]
        return df

    dispatch = rolling_sum(dispatch.groupby("gen_type", as_index=False))
    load = rolling_sum(load).set_index("datetime")["value"]

    # Get the state of charge data
    soc = tools.get_dataframe("StateOfCharge.csv", dtype={"STORAGE_GEN_TPS_1": str}) \
        .rename(columns={"STORAGE_GEN_TPS_2": "timepoint", "StateOfCharge": "value"})
    soc = filter_scenario(soc, scenario_name)
    # Sum over all the projects that are in the same scenario with the same timepoint
    soc = soc.groupby(["timepoint"], as_index=False).sum()
    soc["value"] /= 1e6  # Convert to TWh
    max_soc = soc["value"].max()

    # Group by time
    soc = process_time(tools.transform.timestamp(soc, use_timepoint=True, key_col="timepoint"))
    soc = soc.rolling(freq, center=True)["value"].mean().reset_index()
    soc = soc[(soc.datetime.min() + offset < soc.datetime) & (soc.datetime < soc.datetime.max() - offset)]
    soc = soc.set_index("datetime")["value"]

    dispatch = dispatch[dispatch["value"] != 0]
    dispatch = dispatch.pivot(columns="gen_type", index="datetime", values="value")
    dispatch = dispatch[dispatch.std().sort_values().index].rename_axis("Technology", axis=1)
    total_dispatch = dispatch.sum(axis=1)

    max_val = max(total_dispatch.max(), load.max())

    # Scale soc to the graph
    soc *= 100 / scenario_name

    # Plot
    # Get the colors for the lines
    # plot
    ax.set_ylim(0, max_val * 1.05)
    dispatch.plot(
        ax=ax,
        color=tools.get_colors(),
        legend=False,
        xlabel=""
    )
    ax2 = ax.twinx()
    ax2.yaxis.set_major_formatter(PercentFormatter())
    ax2.set_ylim(0, 100)
    soc.plot(ax=ax2, color="black", linestyle="dotted", label="State of Charge", xlabel="")
    load.plot(ax=ax, color="red", linestyle="dashed", label="Total Demand", xlabel="")
    total_dispatch.plot(ax=ax, color="green", linestyle="dashed", label="Total Generation", xlabel="")
    ax.fill_between(total_dispatch.index, total_dispatch.values, load.values, alpha=0.2, where=load < total_dispatch,
                    facecolor="green")
    ax.fill_between(total_dispatch.index, total_dispatch.values, load.values, alpha=0.2, where=load > total_dispatch,
                    facecolor="red")
    ax.set_title(str(scenario_name) + "TWh of storage")


@graph(
    "figure_3",
    title="Figure 3: Map of buildout",
    supports_multi_scenario=True
)
def figure_3(tools):
    fig = tools.get_figure(size=(24, 12))
    axes = fig.subplots(2, 4)

    plot_buildout(tools, 1.94, axes[0][0])
    plot_buildout(tools, 4, axes[0][1])
    plot_buildout(tools, 16, axes[0][2])
    plot_buildout(tools, 64, axes[0][3])

    dispatch_map(tools, 1.94, axes[1][0])
    dispatch_map(tools, 4, axes[1][1])
    dispatch_map(tools, 16, axes[1][2])
    dispatch_map(tools, 64, axes[1][3])


def plot_buildout(tools, scenario_name, ax):
    buildout = tools.get_dataframe("gen_cap.csv").rename({"GenCapacity": "value"}, axis=1)
    buildout = filter_scenario(buildout, scenario_name)
    buildout = tools.transform.gen_type(buildout)
    buildout = buildout.groupby(["gen_type", "gen_load_zone"], as_index=False)["value"].sum()
    tools.maps.graph_pie_chart(buildout, ax=ax, max_size=1500)
    transmission = tools.get_dataframe("transmission.csv", convert_dot_to_na=True).fillna(0)
    transmission = filter_scenario(transmission, scenario_name)
    transmission = transmission.rename({"trans_lz1": "from", "trans_lz2": "to", "BuildTx": "value"}, axis=1)
    transmission = transmission[["from", "to", "value", "PERIOD"]]
    transmission = transmission.groupby(["from", "to", "PERIOD"], as_index=False).sum().drop("PERIOD", axis=1)
    # Rename the columns appropriately
    transmission.value *= 1e-3
    tools.maps.graph_transmission(transmission, cutoff=0.1, ax=ax, zorder=50, legend=False)
    ax.set_title(str(scenario_name) + "TWh of storage")

def dispatch_map(tools, scenario_name, ax):
    dispatch = tools.get_dataframe("transmission_dispatch.csv")
    dispatch = filter_scenario(dispatch, scenario_name)
    dispatch = tools.transform.timestamp(dispatch).astype({"period": int})
    # Keep only the last period
    last_period = dispatch["period"].max()
    dispatch = dispatch[dispatch["period"] == last_period]
    dispatch = dispatch.rename({"load_zone_from": "from", "load_zone_to": "to", "transmission_dispatch": "value"},
                               axis=1)
    dispatch["value"] *= dispatch["tp_duration"] * 1e-6  # Change from power value to energy value
    dispatch = dispatch.groupby(["from", "to"], as_index=False)["value"].sum()
    ax = tools.maps.graph_transmission(dispatch, cutoff=1, ax=ax)
    exports = dispatch[["from", "value"]].rename({"from": "gen_load_zone"}, axis=1).copy()
    imports = dispatch[["to", "value"]].rename({"to": "gen_load_zone"}, axis=1).copy()
    imports["value"] *= -1
    exports = pd.concat([imports, exports])
    exports = exports.groupby("gen_load_zone", as_index=False).sum()
    tools.maps.graph_points(exports, ax)


if __name__ == "__main__":
    baseline = Scenario("1342", name=1.94)
    min_4 = Scenario("M6", name=4)
    min_8 = Scenario("M5", name=8)
    min_16 = Scenario("M4", name=16)
    min_32 = Scenario("M3", name=32)
    min_64 = Scenario("M2", name=64)
    minimum_scenarios = [baseline, min_4, min_8, min_16, min_32, min_64]
    kwargs = dict(graph_dir="LDES_paper_graphs", overwrite=True, module_names=[])
    # graph_scenarios(
    #     scenarios=minimum_scenarios,
    #     figures=["figure_2"],
    #     **kwargs
    # )
    graph_scenarios(
        scenarios=[baseline, min_4, min_16, min_64],
        figures=["figure_3"],
        **kwargs
    )
