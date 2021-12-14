


# Third-party package
import cartopy
import cartopy.crs as ccrs
import geopandas as gpd
import matplotlib.pyplot as plt
import matplotlib as mpl
import numpy as np
import pandas as pd

from cartopy.feature import ShapelyFeature
from matplotlib.lines import Line2D
from matplotlib.patches import Patch, Circle
import matplotlib.patches as mpatches
from shapely.geometry import LineString

# Local imports
from utils import get_data
from utils import config, tech_order, tech_colors, PLOT_PARAMS

#%%

# Matplotlib configuration
mpl.rcParams["figure.dpi"] = 100
mpl.rcParams["font.family"] = "Source Sans Pro"


# Define default paramters for map
map_proj = ccrs.Mercator()
map_colors = {
    "ocean": "lightblue",
    "land": "whitesmoke",
}  # Based on colors used in PyPSA
resolution = "50m"

fig = plt.figure(figsize=(5, 5))

#%%

def basemap(figsize=(5, 5), states=True, **kwargs):
    """ Create basemap to plot geolocated data"""
    map_proj = ccrs.Mercator()
    map_colors = {
        "ocean": "lightblue",
        "land": "whitesmoke",
    }  # Based on colors used in PyPSA
    resolution = "50m"

    fig = plt.figure(figsize=figsize, **kwargs)
    ax = fig.add_subplot(projection=map_proj)
    ax.set_global()  # Apply projection to features added

    # Area of interest for WECC
    ax.set_extent([-125, -100, 30, 51])

    # Add land and ocean to map
    ax.add_feature(
        cartopy.feature.LAND.with_scale(resolution),
        facecolor=map_colors["land"],
    )
    ax.add_feature(
        cartopy.feature.OCEAN.with_scale(resolution), facecolor=map_colors["ocean"]
    )

    # Add international borders
    border = cartopy.feature.BORDERS.with_scale(resolution)
    ax.add_feature(border, linewidth=0.1, edgecolor="white")

    # Add state borders
    if states:
        ax.add_feature(cartopy.feature.STATES, linewidth=0.1)

    # Remove outer border
    ax.spines["geo"].set_visible(False)

    return ax


# Read Wecc centroids
wecc_lz = gpd.read_file("../data/gis/wecc_lz_4326.geojson")
wecc_lz.info()

#%%

ax = basemap()
ax.add_geometries(
    wecc_lz.geometry,
    crs=ccrs.PlateCarree(),
    facecolor="whitesmoke",
    edgecolor="k",
    lw=0.5,
    ls="--",
    zorder=10,
    alpha=0.5,
)

if savefig:
    plt.savefig("../figs/wecc_lz.pdf", dpi=300, bbox_inches="tight")

#%% md

## Read SWITCH-WECC load zones centroids

#%%

wecc_centroids = gpd.read_file(
    "../data/gis/wecc_centroids_4326_3.geojson", crs="epsg:4326"
)
wecc_centroids = wecc_centroids.rename({"LOAD_AREA": "gen_load_zone"}, axis=1)

# Create lat and lng column
wecc_centroids["lat"] = wecc_centroids["geometry"].x
wecc_centroids["lng"] = wecc_centroids["geometry"].y

wecc_centroids.head()

#%%

ax = basemap()
ax.scatter(wecc_centroids.lat, wecc_centroids.lng, transform=ccrs.PlateCarree())

#%% md

## Read existing transmission lines

#%%

existing_Tx = pd.read_csv("transmission_lines.csv")
existing_Tx = existing_Tx.rename(
    {"trans_lz1": "from", "trans_lz2": "to", "existing_trans_cap": "value"}, axis=1
)
existing_Tx = existing_Tx[["from", "to", "value"]]
existing_Tx.value *= 1e-3  # MW to GW
existing_Tx = existing_Tx.groupby(["from", "to"], as_index=False)["value"].sum()
existing_Tx

#%%

existing_Tx_merged = existing_Tx.merge(
    wecc_centroids.add_prefix("from_"),
    left_on="from",
    right_on="from_gen_load_zone",
).merge(wecc_centroids.add_prefix("to_"), left_on="to", right_on="to_gen_load_zone")[
    ["from_geometry", "to_geometry", "value"]
]
existing_Tx_merged

#%%

def make_line(df):
    return LineString([df["from_geometry"], df["to_geometry"]])


existing_Tx_merged["geometry"] = existing_Tx_merged.apply(make_line, axis=1)
existing_Tx_merged["Capacity_cat"] = pd.cut(
    existing_Tx_merged["value"], bins=[0, 5, 10, 30], labels=["5", "10", "30"]
)

#%%

Tx_lines = gpd.GeoDataFrame(
    existing_Tx_merged[["geometry", "value", "Capacity_cat"]], geometry="geometry"
)
Tx_lines = Tx_lines.query("value  > 0")
Tx_lines.head()

#%%

Tx_lines.value.hist()

#%%

ax = basemap(figsize=(3, 3), dpi=600, states=False)
ax.scatter(
    wecc_centroids.lat,
    wecc_centroids.lng,
    transform=ccrs.PlateCarree(),
    facecolor="r",
    edgecolor="r",
    s=10,
)
ax.add_geometries(
    wecc_lz.geometry,
    crs=ccrs.PlateCarree(),
    facecolor="none",
    edgecolor="k",
    lw=0.2,
    # ls="--",
    zorder=2,
    # alpha=0.5,
)


for cat, tx_lines in Tx_lines.groupby("Capacity_cat"):
    if cat == "5":
        lw = 0.5
    elif cat == "10":
        lw = 1.5
    else:
        lw = 2.5
    ax.add_geometries(
        tx_lines.geometry,
        crs=ccrs.PlateCarree(),
        facecolor="whitesmoke",
        edgecolor="red",
        alpha=0.5,
        lw=lw,
    )
# make legend with dummy points
for lw, Tx_rate in zip([2.5, 1.5, 0.5], ["30", "10", "5"]):
    plt.plot([], [], c="red", alpha=0.5, lw=lw, label=f"{Tx_rate:>3} GW")
Tx_lines_legend = [
    Line2D([0], [0], color="r", lw=2.5, label="30"),
    Line2D([0], [0], color="r", lw=1.5, label="10"),
    Line2D([0], [0], color="r", lw=0.5, label="  5"),
]
ax.legend(
    handles=Tx_lines_legend,
    scatterpoints=2,
    frameon=False,
    title="Tx capacity (GW)",
    labelspacing=0.5,
    loc="lower left",
    handletextpad=2,
    handlelength=2,
    handleheight=1,
    title_fontsize=5,
    fontsize=5,
    bbox_to_anchor=(1, 0.8),
)
fname = "wecc_existing_Tx.pdf"
if True:
    plt.savefig(fig_path / fname, dpi=600, bbox_inches="tight")

#%%

fname = "transmission.csv"
optimal_Tx = get_data(scenario, fname)
optimal_Tx["BuildTx"] = optimal_Tx["BuildTx"].replace(".", np.nan).astype(float)
optimal_Tx.head()

#%%

optimal_Tx = optimal_Tx.rename(
    {"trans_lz1": "from", "trans_lz2": "to", "BuildTx": "value"}, axis=1
)
optimal_Tx = optimal_Tx[["from", "to", "value"]]
optimal_Tx.value *= 1e-3  # MW to GW
optimal_Tx = optimal_Tx.groupby(["from", "to"], as_index=False)["value"].sum()
optimal_Tx.head()

#%%

optimal_Tx_merged = optimal_Tx.merge(
    wecc_centroids.add_prefix("from_"),
    left_on="from",
    right_on="from_gen_load_zone",
).merge(wecc_centroids.add_prefix("to_"), left_on="to", right_on="to_gen_load_zone")[
    ["from_geometry", "to_geometry", "value"]
]
optimal_Tx_merged

#%%

def make_line(df):
    return LineString([df["from_geometry"], df["to_geometry"]])


optimal_Tx_merged["geometry"] = optimal_Tx_merged.apply(make_line, axis=1)
optimal_Tx_merged["Capacity_cat"] = pd.cut(
    optimal_Tx_merged["value"], bins=[0, 5, 10, 30], labels=["5", "10", "30"]
)

#%%

optimal_Tx_lines = gpd.GeoDataFrame(
    optimal_Tx_merged[["geometry", "value", "Capacity_cat"]], geometry="geometry"
)
optimal_Tx_lines = optimal_Tx_lines.query("value  > 0")
optimal_Tx_lines.head()

#%%

optimal_Tx_lines.value.hist()

#%%

ax = basemap()
ax.scatter(
    wecc_centroids.geometry.x,
    wecc_centroids.geometry.y,
    transform=ccrs.PlateCarree(),
    facecolor="r",
    edgecolor="r",
    s=10,
)
for cat, tx_lines in optimal_Tx_lines.groupby("Capacity_cat"):
    if cat == "5":
        lw = 0.5
    elif cat == "10":
        lw = 1.5
    else:
        lw = 2.5
    ax.add_geometries(
        tx_lines.geometry,
        crs=ccrs.PlateCarree(),
        facecolor="whitesmoke",
        edgecolor="red",
        alpha=0.5,
        lw=lw,
    )
# make legend with dummy points
for lw, Tx_rate in zip([2.5, 1.5, 0.5], ["30", "10", "5"]):
    plt.plot([], [], c="red", alpha=0.5, lw=lw, label=f"{Tx_rate:>2} GW")
l2 = plt.legend(
    scatterpoints=1,
    frameon=False,
    labelspacing=1,
    loc="lower left",
    handletextpad=2,
    fontsize=5,
)
fname = f"wecc_optimal_Tx_{scenario}.pdf"
if savefig:
    plt.savefig(fig_path / fname, dpi=300, bbox_inches="tight")

#%% md

# Built capacity

#%%

# scenario = "178_19_17-1year_baseline"

#%%

fname = "generation_projects_info.csv"
columns = [
    "GENERATION_PROJECT",
    "gen_tech",
    "gen_capacity_limit_mw",
    "gen_tech",
    "gen_load_zone",
]

gen_projects = get_data(scenario, fname, fpath="inputs", usecols=columns)
gen_projects.info()

#%%

fname = "gen_cap.csv"
build_gen = get_data(scenario, fname)

# Rename columns to match generation_projects_info
build_gen = build_gen.rename(columns={"PERIOD": "period", "GenCapacity": "gen_cap_MW"})
build_gen = build_gen.loc[:, ["GENERATION_PROJECT", "period", "gen_cap_MW", "scenario"]]
build_gen

#%%

build_gen = pd.merge(
    left=build_gen,
    right=gen_projects,
    on=["GENERATION_PROJECT", "scenario"],
    validate="many_to_one",
)
build_gen = build_gen.query("period == 2050 ")
build_gen.head()

#%%

projection = "EPSG:3857"
cap_by_lz = wecc_centroids.merge(
    build_gen, right_on="gen_load_zone", left_on="gen_load_zone"
).to_crs(projection)
cap_by_lz["build_gen_GW"] = cap_by_lz["gen_cap_MW"] / 1e3
cap_by_lz.head()

#%%

# REFERENCE: https://tinyurl.com/app/myurls
def pie_plot(lat, lng, ratios, colors, size=20, ax=None):
    # determine arches
    start = 0.0
    xy = []
    s = []
    for ratio in ratios:
        x0 = [0] + np.cos(
            np.linspace(2 * np.pi * start, 2 * np.pi * (start + ratio), 30)
        ).tolist()  # 30
        y0 = [0] + np.sin(
            np.linspace(2 * np.pi * start, 2 * np.pi * (start + ratio), 30)
        ).tolist()  # 30

        xy1 = np.column_stack([x0, y0])
        s1 = np.abs(xy1).max()

        xy.append(xy1)
        s.append(s1)
        start += ratio

    for xyi, si, c in zip(xy, s, colors):
        ax.scatter(
            [x],
            [y],
            marker=xyi,
            s=size * si ** 2,
            c=c,
            edgecolor="k",
            lw=0.05,
            zorder=10,
        )

#%%

def draw_pie(lat, lng, ratios, colors, size=10, ax=None):
    if ax is None:
        fig, ax = plt.subplots()

    slices = []
    start_loc = 0.0  # For the pie plot
    for color, ratio in zip(colors, ratios):
        increase = start_loc + ratio
        x = np.cos(2 * np.pi * np.linspace(start_loc, increase))
        y = np.sin(2 * np.pi * np.linspace(start_loc, increase))
        xy = np.row_stack([[0, 0], np.column_stack([x, y])])
        s = size * np.abs(xy).max() ** 2
        slices.append({"marker": xy, "s": s, "c": color})
        start_loc = increase
    for pie_slice in slices:
        ax.scatter(x=lng, y=lat - 0.01, edgecolor="k", lw=0.1, zorder=100, **pie_slice)

#%%

ax = basemap()

ax.add_geometries(
    wecc_lz.geometry,
    crs=ccrs.PlateCarree(),
    facecolor="whitesmoke",
    edgecolor="black",
    lw=0.1,
    ls=":",
    zorder=-1,
)
sizes = []
for index, group in cap_by_lz.groupby(["gen_load_zone"]):
    lat, lng = group["geometry"].iloc[0].y, group["geometry"].iloc[0].x
    group_sum = group.groupby("tech_map")["build_gen_GW"].sum().sort_values()
    group_sum = group_sum[(group_sum != 0)].copy()

    tech_color = [tech_colors.get(tech) for tech in group_sum.index.values]
    total_size = group_sum.sum()

    sizes.append(total_size)
    ratios = (group_sum / total_size).values
    if total_size < 5:
        total_size = 10
    else:
        total_size = total_size + 10
    draw_pie(lat, lng, ratios, tech_color, size=(total_size) * 4, ax=ax)

ax.spines["geo"].set_visible(False)
fname = "wecc_cap.pdf"
if savefig:
    plt.savefig(fig_path / fname, dpi=400, bbox_inches="tight")

#%%

def export_legend(legend, filename="legend.pdf"):
    fig = legend.figure
    fig.canvas.draw()
    bbox = legend.get_window_extent().transformed(fig.dpi_scale_trans.inverted())
    fig.savefig(filename, dpi=500, bbox_inches=bbox, transparent=True)


for a in [100, 50, 5]:
    plt.scatter([], [], c="k", alpha=0.5, s=a * 4, label=str(a) + " GW")

l1 = plt.legend(
    scatterpoints=1,
    frameon=False,
    labelspacing=2.0,
    loc=4,
    handletextpad=1.5,
    fontsize=6,
)

export_legend(l1, filename="capcaity_legend.png")
plt.show()
# figlegend.savefig('legend.png')

#%%

# make legend with dummy points
for lw, Tx_rate in zip([2.5, 1.5, 0.5], ["30", "10", "5"]):
    plt.plot([], [], c="red", alpha=0.5, lw=lw, label=f"{Tx_rate:>3} GW")
l2 = plt.legend(
    scatterpoints=1,
    frameon=False,
    labelspacing=0,
    loc="lower left",
    handletextpad=2,
    fontsize=6,
)
export_legend(l2, filename="Tx_legend.pdf")
plt.show()

#%%

cap_by_lz["cap_zone"] = cap_by_lz.groupby("gen_load_zone")["build_gen_GW"].transform(
    sum
)
cap_by_lz["cap_cat"] = pd.cut(
    cap_by_lz["cap_zone"],
    bins=[0, 10, 50, 150],
    labels=["10", "50", "100"],
)

#%%

total_capacity_by_lz = pd.pivot_table(
    cap_by_lz,
    index=["gen_load_zone", "lat", "lng"],
    values="build_gen_GW",
    aggfunc=np.sum,
).reset_index()
total_capacity_by_lz.head()

#%%

total_capacity_by_lz["category"] = pd.cut(
    total_capacity_by_lz["build_gen_GW"],
    bins=[0, 10, 50, 150],
    labels=["10", "50", "100"],
)
total_capacity_by_lz.head()

#%%

ax = basemap(figsize=(3.26, 3.26), dpi=600)

ax.add_geometries(
    wecc_lz.geometry,
    crs=ccrs.PlateCarree(),
    facecolor="whitesmoke",
    edgecolor="black",
    lw=0.1,
    ls=":",
    zorder=-1,
)
for cat, tx_lines in optimal_Tx_lines.groupby("Capacity_cat"):
    if cat == "5":
        lw = 0.5
    elif cat == "10":
        lw = 1.5
    else:
        lw = 2.5
    ax.add_geometries(
        tx_lines.geometry,
        crs=ccrs.PlateCarree(),
        facecolor="whitesmoke",
        edgecolor="red",
        alpha=0.5,
        lw=lw,
    )
for index, group in cap_by_lz.groupby(["gen_load_zone"]):
    x, y = group["geometry"].iloc[0].x, group["geometry"].iloc[0].y
    group_sum = group.groupby("tech_map")["build_gen_GW"].sum().sort_values()
    group_sum = group_sum[(group_sum != 0)].copy()

    tech_color = [tech_colors.get(tech) for tech in group_sum.index.values]
    total_size = group_sum.sum()
    sizes.append(total_size)
    #     if group["cap_cat"].unique() == "10":
    #         size = 25
    #     elif group["cap_cat"].unique() == "50":
    #         size = 75
    #     else:
    #         size = 150
    ratios = (group_sum / total_size).values
    if total_size < 5:
        total_size = 10
    else:
        total_size = total_size + 10
    pie_plot(x, y, ratios, tech_color, ax=ax, size=total_size * 2)
ax.spines["geo"].set_visible(False)

technology_patches = [
    mpatches.Patch(color=color, label=tech) for tech, color in tech_colors.items()
]


l1 = ax.legend(
    handles=technology_patches,
    title="Candidate technology",
    scatterpoints=1,
    frameon=False,
    labelspacing=1.0,
    ncol=1,
    handlelength=0.8,
    handleheight=0.8,
    title_fontsize=5,
    fontsize=5,
    bbox_to_anchor=(1.0, 1),
    loc=2,
)

for a in [100, 50, 10]:
    sc = ax.scatter(
        [], [], edgecolor="k", lw=0.5, facecolors="none", s=a * 2, label=str(a)
    )
    sc.set_facecolor("none")


l2 = ax.legend(
    scatterpoints=1,
    frameon=False,
    title="Total capacity (GW)",
    labelspacing=1.5,
    loc="lower left",
    handletextpad=2,
    handlelength=2,
    handleheight=1,
    title_fontsize=5,
    fontsize=4,
    bbox_to_anchor=(1, 0),
)

ax.add_artist(l1)
ax.add_artist(l2)

Tx_lines = [
    Line2D([0], [0], color="r", lw=2.5, label="30"),
    Line2D([0], [0], color="r", lw=1.5, label="10"),
    Line2D([0], [0], color="r", lw=0.5, label="  5"),
]
l3 = ax.legend(
    handles=Tx_lines,
    scatterpoints=2,
    frameon=False,
    title="Tx capacity (GW)",
    labelspacing=0.5,
    loc="upper right",
    handletextpad=2,
    handlelength=2,
    handleheight=1,
    title_fontsize=5,
    fontsize=5,
    # bbox_to_anchor=(1, 0.0),
)

fname = f"wecc_cap_Tx_{scenario}.pdf"
if True:
    plt.savefig(fig_path / fname, dpi=600, bbox_inches="tight", pad_inches=0)

#%%



ax = basemap(figsize=(3, 3), dpi=600)
ax.scatter(
    wecc_centroids.lat,
    wecc_centroids.lng,
    transform=ccrs.PlateCarree(),
    facecolor="r",
    edgecolor="r",
    s=1,
)


technology_patches = [
    mpatches.Patch(color=color, label=tech) for tech, color in tech_colors.items()
]


l1 = ax.legend(
    handles=patches,
    title="Candidate technology",
    scatterpoints=1,
    frameon=False,
    labelspacing=1.0,
    loc="lower left",
    ncol=2,
    handlelength=0.8,
    handleheight=0.8,
    title_fontsize=5,
    fontsize=3,
    bbox_to_anchor=(1, 0.74),
)

for a in [100, 50, 10]:
    sc = plt.scatter(
        [], [], edgecolor="k", lw=0.5, facecolors="none", s=a, label=str(a)
    )
    sc.set_facecolor("none")


l2 = plt.legend(
    scatterpoints=1,
    frameon=False,
    title="Total capacity (GW)",
    labelspacing=1.5,
    loc="lower left",
    handletextpad=2,
    handlelength=2,
    handleheight=1,
    title_fontsize=5,
    fontsize=5,
    bbox_to_anchor=(1, 0.40),
)

ax.add_artist(l1)
ax.add_artist(l2)

Tx_lines = [
    Line2D([0], [0], color="r", lw=2.5, label="30"),
    Line2D([0], [0], color="r", lw=1.5, label="10"),
    Line2D([0], [0], color="r", lw=0.5, label="  5"),
]
l3 = ax.legend(
    handles=Tx_lines,
    scatterpoints=2,
    frameon=False,
    title="Tx capacity (GW)",
    labelspacing=0.5,
    loc="lower left",
    handletextpad=2,
    handlelength=2,
    handleheight=1,
    title_fontsize=5,
    fontsize=5,
    bbox_to_anchor=(1, 0.20),
)

#%% md

## Installed storage difference

#%%

scenarios = ["178_14_12-1week_baseline", "178_19_17-1year_baseline"]

#%%

fname = "generation_projects_info.csv"
columns = [
    "GENERATION_PROJECT",
    "gen_tech",
    "gen_capacity_limit_mw",
    "gen_tech",
    "gen_load_zone",
]

gen_projects = get_data(scenarios, fname, fpath="inputs", usecols=columns)
gen_projects.info()

#%%

fname = "storage_capacity.csv"
build_gen = get_data(scenarios, fname)

# Rename columns to match generation_projects_info
build_gen = build_gen.rename(
    columns={
        "PERIOD": "period",
        "GenCapacity": "gen_cap_MW",
        "generation_project": "GENERATION_PROJECT",
    }
)
# build_gen = build_gen.loc[:, ["GENERATION_PROJECT", "period", "gen_cap_MW", "scenario"]]
build_gen

#%%

storage_build = build_gen.groupby(["scenario", "load_zone"], as_index=False)[
    ["OnlinePowerCapacityMW", "OnlineEnergyCapacityMWh"]
].sum()
storage_build.head()

#%%

storage_build["cap_GW"] = storage_build["OnlinePowerCapacityMW"] / 1e3
storage_build["energy_TWh"] = storage_build["OnlineEnergyCapacityMWh"] / 1e3


storage_build.head()

#%%

cap_diff = pd.pivot_table(
    storage_build,
    index="load_zone",
    columns="scenario",
    values=["energy_TWh", "cap_GW"],
)


metric = "energy_TWh"

cap_diff = cap_diff[metric]
cap_diff = cap_diff  # / cap_diff.sum(axis=0)
baseline = cap_diff["178_14_12-1week_baseline"]
difference = ((cap_diff["178_19_17-1year_baseline"] - baseline)).to_frame(
    "capacity_differnece"
)
# # difference
difference = difference.replace(0, np.nan)
difference = difference.replace(np.inf, np.nan)


cap_diff.sum(axis=0)

#%%

(difference).hist()

#%%

projection = "EPSG:4326"
cap_by_lz = wecc_lz.merge(
    difference * 100, right_on="load_zone", left_on="LOAD_AREA"
).to_crs(projection)
# cap_by_lz["build_gen_GW"] = cap_by_lz["gen_cap_MW"] / 1e3
# cap_by_lz.head()
cap_by_lz.head()

#%%

difference.describe()

#%%

import matplotlib

ax = basemap(states=False, figsize=(3, 3), dpi=600)
norm = matplotlib.colors.TwoSlopeNorm(vmin=-100, vcenter=0, vmax=11)
# norm = matplotlib.colors.Normalize(vmin=-1.5, vcenter=0, vmax=1.5)
cmap = plt.cm.RdBu

for i, row in cap_by_lz.iterrows():
    region = ShapelyFeature(
        row["geometry"],
        ccrs.PlateCarree(),
        facecolor=cmap(norm(row["capacity_differnece"])),
        edgecolor="white",
        lw=0.1,
    )
    ax.add_feature(region)

sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
sm._A = []

cbar = plt.colorbar(sm, ax=ax, shrink=0.9)
cbar.set_label("Capacity difference (GW)")

fname = f"wecc_{metric}_baseline.pdf"
if True:
    plt.savefig(fig_path / fname, dpi=600, bbox_inches="tight")

#%%


