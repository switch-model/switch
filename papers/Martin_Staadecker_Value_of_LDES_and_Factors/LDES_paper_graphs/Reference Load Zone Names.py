from matplotlib import pyplot as plt

from papers.Martin_Staadecker_Value_of_LDES_and_Factors.LDES_paper_graphs.util import get_scenario, set_style
from switch_model.tools.graph.main import GraphTools

tools = GraphTools([get_scenario("1342")])
tools.pre_graphing(multi_scenario=False)

# %% CREATE PLOT FRAME
set_style()
plt.close()
fig = plt.figure()
fig.set_size_inches(8, 8)
ax = fig.add_subplot(1, 1, 1, projection=tools.maps.get_projection())

tools.maps.draw_base_map(ax)

for _, lz in tools.maps._center_points.iterrows():
    center = lz.geometry.centroid
    ax.scatter(center.x, center.y, color="k", s=10, alpha=0.5)
    ax.text(center.x, center.y, lz.gen_load_zone, fontsize="x-small")
    # ax.add_geometries(
    #     lz.geometry,
    #     crs=tools.maps.get_projection(),
    #     facecolor=(0, 0, 0, 0), # Transparent
    #     edgecolor="tab:green",
    #     linewidth=2,
    #     # linestyle="--",
    #     # alpha=0,
    # )

plt.subplots_adjust(left=0, right=1, bottom=0, top=1)