"""
Creates a map of the WECC with each load zone labelled with it's SWITCH name.
Useful for figuring out what load zone name matches what physical region.
The map is available in the REAM Google Drive under Research -> Switch documentation.
"""

from matplotlib import pyplot as plt

from papers.Martin_Staadecker_et_al_2022.util import get_scenario, set_style, save_figure
from switch_model.tools.graph.main import GraphTools

tools = GraphTools([get_scenario("1342")], set_style=False)
tools.pre_graphing(multi_scenario=False)

# %% CREATE PLOT FRAME
set_style()
plt.close()
fig = plt.figure()
fig.set_size_inches(6.850394, 6.850394)
ax = fig.add_subplot(1, 1, 1, projection=tools.maps.get_projection())

tools.maps.draw_base_map(ax)

centers = {}

for _, lz in tools.maps._center_points.iterrows():
    center = lz.geometry.centroid
    ax.scatter(center.x, center.y, color="k", s=5, alpha=0.5)
    ax.text(center.x, center.y, lz.gen_load_zone, fontsize="small")
    centers[lz.gen_load_zone] = center

tx = tools.get_dataframe("transmission_lines.csv", from_inputs=True)
tx = tx[["trans_lz1", "trans_lz2"]]
for _, line in tx.iterrows():
    from_center = centers[line["trans_lz1"]]
    to_center = centers[line["trans_lz2"]]
    ax.plot([from_center.x, to_center.x], [from_center.y, to_center.y], color="k", linestyle="--", linewidth=1, alpha=0.3)

for lz, center in centers.items():
    ax.text(center.x, center.y, lz, fontsize="small")

plt.tight_layout()
# %%
save_figure("figure-s5-map-of-load-zones.png")