"""
Helper code to create maps of the WECC
"""

import numpy as np
from matplotlib import pyplot as plt, colors
import warnings


class GraphMapTools:
    def __init__(self, graph_tools):
        """
        graph_tools is a reference to the parent tools object
        """
        self._tools = graph_tools
        self._loaded_dependencies = False
        self._center_points = None
        self._wecc_lz = None
        self._shapely = None
        self._geopandas = None
        self._cartopy = None
        self._projection = None

    def get_projection(self):
        self._load_maps()
        return self._projection

    def _load_maps(self):
        """
        Loads all the mapping files and dependencies needed for mapping.
        """
        if self._loaded_dependencies:
            return self._wecc_lz, self._center_points

        try:
            import geopandas
            import shapely
            import cartopy
        except ModuleNotFoundError:
            raise Exception(
                "Could not find package geopandas, shapely or cartopy. "
                "If on Windows make sure you install them through conda."
            )

        self._shapely = shapely
        self._cartopy = cartopy
        self._geopandas = geopandas
        self._projection = cartopy.crs.PlateCarree()

        # Read shape files
        try:
            self._wecc_lz = geopandas.read_file(
                self._tools.get_file_path("maps/wecc_lz_4326.geojson", from_inputs=True)
            )
            self._center_points = geopandas.read_file(
                self._tools.get_file_path(
                    "maps/wecc_centroids_4326_3.geojson", from_inputs=True
                ),
                crs="epsg:4326",
            )
        except FileNotFoundError:
            raise Exception(
                "Can't create maps, files are missing. Try running switch get_inputs."
            )

        self._wecc_lz = self._wecc_lz.rename({"LOAD_AREA": "gen_load_zone"}, axis=1)
        self._center_points = self._center_points.rename(
            {"LOAD_AREA": "gen_load_zone"}, axis=1
        )
        self._center_points = self._center_points[["gen_load_zone", "geometry"]]

        self._loaded_dependencies = True
        return self._wecc_lz, self._center_points

    def draw_base_map(self, ax):
        wecc_lz, center_points = self._load_maps()

        map_colors = {
            "ocean": "lightblue",
            "land": "whitesmoke",
        }  # Based on colors used in PyPSA
        resolution = "50m"
        ax.set_global()  # Apply projection to features added
        # Area of interest for WECC
        ax.set_extent([-125, -102, 30, 51])

        # Add land and ocean to map
        ax.add_feature(
            self._cartopy.feature.LAND.with_scale(resolution),
            facecolor=map_colors["land"],
        )
        ax.add_feature(
            self._cartopy.feature.OCEAN.with_scale(resolution),
            facecolor=map_colors["ocean"],
        )

        # Add international borders
        ax.add_feature(
            self._cartopy.feature.BORDERS.with_scale(resolution),
            linewidth=0.1,
            edgecolor="k",
        )

        # Add state borders
        # ax.add_feature(self._cartopy.feature.STATES, linewidth=0.1, edgecolor="k")

        # Remove outer border
        ax.spines["geo"].set_visible(False)
        ax.add_geometries(
            wecc_lz.geometry,
            crs=self._projection,
            facecolor="whitesmoke",
            edgecolor="k",
            lw=0.5,
            ls="--",
            # alpha=0.5,
        )
        return ax

    def _pie_plot(self, x, y, ratios, colors, size, ax):
        # REFERENC: https://tinyurl.com/app/myurls
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
                s=size * si**2,
                c=c,
                edgecolor="k",
                transform=self._projection,
                zorder=10,
            )

    def graph_pie_chart(
        self,
        df,
        bins=(0, 10, 30, 60, 1000),
        sizes=(200, 400, 600, 800),
        labels=("<10 GW", "10 to 30 GW", "30 to 60 GW", "60+ GW"),
        ax=None,
    ):
        """
        Graphs the data from the dataframe to a map pie chart.
        The dataframe should have 3 columns, gen_load_zone, gen_type and value.
        """
        _, center_points = self._load_maps()

        if ax is None:
            ax = self._tools.get_axes()
            self.draw_base_map(ax)
        df = df.merge(center_points, on="gen_load_zone")

        assert not df["gen_type"].isnull().values.any()
        colors = self._tools.get_colors()
        lz_values = df.groupby("gen_load_zone")[["value"]].sum()
        lz_values["size"] = self._tools.pd.cut(lz_values.value, bins=bins, labels=sizes)
        if lz_values["size"].isnull().values.any():
            lz_values["size"] = 300
            warnings.warn(
                "Not using variable pie chart size since values were out of bounds during cutting"
            )
        for index, group in df.groupby("gen_load_zone"):
            x, y = group["geometry"].iloc[0].x, group["geometry"].iloc[0].y
            group_sum = group.groupby("gen_type")["value"].sum().sort_values()
            group_sum = group_sum[group_sum != 0].copy()

            tech_color = [colors[tech] for tech in group_sum.index.values]
            total_size = lz_values.loc[index]["size"]
            ratios = (group_sum / group_sum.sum()).values
            self._pie_plot(x, y, ratios, tech_color, total_size, ax)

        legend_points = [
            # self._tools.plt.patches.Rectangle((0, 0), 1, 1, fc="w", fill=False, edgecolor='none', linewidth=0, label="Capacity")
        ]
        for size, label in zip(sizes, labels):
            legend_points.append(
                plt.scatter([], [], c="k", alpha=0.5, s=size, label=str(label))
            )
        legend = ax.legend(
            handles=legend_points,
            title="Capacity",
            labelspacing=1.5,
            bbox_to_anchor=(1.0, 0.5),
            framealpha=0
            # loc="upper right",
        )
        ax.add_artist(
            legend
        )  # Required, see : https://matplotlib.org/stable/tutorials/intermediate/legend_guide.html#multiple-legends-on-the-same-axes

        return ax

    def _bin_data(self, data, bins, mapping):
        """
        Puts the data into bins and returns the binned data as well as labels and data needed
        to make a legend.
        data : Series containing the data to transform
        bins : list containing the cuts between the bins (not including the ends)
        mapping : function that given the bin index returns the desired value
        Returns a tuple with 3 elements. The first is an array with the binned data.
        The second is a list of labels for the bins
        The third is the value associated with each bin matching the label ordering.
        """
        binned_data = []
        num_bins = len(bins) + 1
        for point in data:
            if point > bins[-1]:
                binned_data.append(num_bins - 1)
                continue
            for i, bin in enumerate(bins):
                if point <= bin:
                    binned_data.append(i)
                    break
        binned_and_mapped = []
        for point in binned_data:
            binned_and_mapped.append(mapping(point))

        labels = [f"<{bins[0]}"]
        legend_vals = [mapping(0.0)]
        for i in range(1, len(bins)):
            legend_vals.append(mapping(i))
            labels.append(f"{bins[i - 1]}-{bins[i]}")
        labels.append(f">{bins[-1]}")
        legend_vals.append(mapping(num_bins - 1))

        return binned_and_mapped, labels, legend_vals

    def graph_duration(self, df, bins=(5, 8, 10, 15), cmap="RdPu", ax=None, size=20):
        """
        Graphs the data from the dataframe to a points on each cell.
        The dataframe should have 2 columns, gen_load_zone and value.
        """
        _, center_points = self._load_maps()

        cmap_func = cmap
        num_bins = len(bins) + 1
        if type(cmap_func) == str:
            cmap_func = plt.get_cmap(cmap_func)

        if ax is None:
            ax = self._tools.get_axes()
            self.draw_base_map(ax)
        # self._plot_states(ax)
        df = df.merge(center_points, on="gen_load_zone", validate="one_to_one")
        colors, legend_labels, legend_colors = self._bin_data(
            df["value"], bins, lambda x: cmap_func(float(x / (num_bins - 1)))
        )
        for i, row in df.iterrows():
            x, y = row["geometry"].x, row["geometry"].y
            ax.scatter(
                x,
                y,
                s=size * 2,
                color="dimgray",
                transform=self._projection,
                zorder=10,
            )  # Add a black border
            ax.scatter(
                x,
                y,
                s=size,
                color=colors[i],
                transform=self._projection,
                zorder=10,
            )
        legend = ax.legend(
            title="Storage duration (h)",
            handles=[
                self._tools.plt.lines.Line2D(
                    [],
                    [],
                    color=c,
                    marker=".",
                    markersize=10,
                    label=l,
                    linestyle="None",
                )
                for c, l in zip(legend_colors, legend_labels)
            ],
            bbox_to_anchor=(1.0, 1.0),
            framealpha=0,
        )
        # ax.add_artist(legend) # Required, see : https://matplotlib.org/stable/tutorials/intermediate/legend_guide.html#multiple-legends-on-the-same-axes

    def graph_points(self, df, ax=None):
        """
        Graphs a point in each load zone based on a dataframe with two columns
        - gen_load_zone
        - value
        """
        _, center_points = self._load_maps()

        df = df.merge(center_points, on="gen_load_zone")
        # Cast to GeoDataFrame
        df = self._geopandas.GeoDataFrame(
            df[["geometry", "value"]], geometry="geometry"
        )

        if ax is None:
            ax = self._tools.get_axes()
            self.draw_base_map(ax)
        df.plot(
            ax=ax,
            column="value",
            legend=True,
            cmap="coolwarm",
            markersize=30,
            norm=colors.CenteredNorm(),
        )

    def graph_transmission(self, df, cutoff, ax=None, legend=True):
        """
        Graphs the data frame a dataframe onto a map.
        The dataframe should have 4 columns:
        - from: the load zone where we're starting from
        - to: the load zone where we're going to
        - value: the value to plot
        """
        if ax is None:
            ax = self._tools.get_axes()
            self.draw_base_map(ax)
        _, center_points = self._load_maps()

        # Merge duplicate rows if table was unidirectional
        df[["from", "to"]] = df[["from", "to"]].apply(
            sorted, axis=1, result_type="expand"
        )
        df = df.groupby(["from", "to"], as_index=False)["value"].sum()

        df = df.merge(
            center_points.add_prefix("from_"),
            left_on="from",
            right_on="from_gen_load_zone",
        ).merge(
            center_points.add_prefix("to_"), left_on="to", right_on="to_gen_load_zone"
        )[
            ["from_geometry", "to_geometry", "value"]
        ]

        def make_line(r):
            return self._shapely.geometry.LineString(
                [r["from_geometry"], r["to_geometry"]]
            )

        df["geometry"] = df.apply(make_line, axis=1)
        # Cast to GeoDataFrame
        df = self._geopandas.GeoDataFrame(
            df[["geometry", "value"]], geometry="geometry"
        )
        df.plot(
            ax=ax,
            column="value",
            legend=legend,
            cmap="Reds",
            norm=colors.LogNorm(vmin=cutoff, vmax=df.value.max()),
        )
        return ax
