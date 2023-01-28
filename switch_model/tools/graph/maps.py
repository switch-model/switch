"""
Helper code to create maps of the WECC
"""

import numpy as np
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

    @staticmethod
    def can_make_maps():
        try:
            import geopandas
            import shapely
            import cartopy
        except ModuleNotFoundError:
            warnings.warn(
                "Packages geopandas, shapely or cartopy are missing, no maps will be created. "
                "If on Windows make sure you install them through conda."
            )
            return False
        return True

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

    def draw_base_map(self, ax=None):
        wecc_lz, center_points = self._load_maps()

        if ax is None:
            ax = self._tools.get_axes(projection=self._projection)

        # We check that the axes are cartopy Axes. Otherwise .set_global() and .set_extent()
        # will not be defined.
        # Note we first need to check that self._cartopy.mpl exists since it starts out
        # uninitialized.
        if (not hasattr(self._cartopy, "mpl")) or type(
            ax
        ) != self._cartopy.mpl.geoaxes.GeoAxesSubplot:
            raise Exception(
                "Axes need to be create with 'projection=tools.maps.get_projection()'"
            )

        map_colors = {
            "ocean": "lightblue",
            "land": "whitesmoke",
        }  # Based on colors used in PyPSA
        resolution = "50m"
        ax.set_global()  # Apply projection to features added
        # Area of interest for WECC
        ax.set_extent([-124, -102.5, 30.5, 51.5])

        # Add land and ocean to map
        ax.add_feature(
            self._cartopy.feature.LAND.with_scale(resolution),
            facecolor=map_colors["land"],
        )
        # ax.add_feature(
        #     self._cartopy.feature.OCEAN.with_scale(resolution), facecolor=map_colors["ocean"]
        # )

        # Remove outer border
        ax.spines["geo"].set_visible(False)

        # Add load zone borders
        ax.add_geometries(
            wecc_lz.geometry,
            crs=self._projection,
            facecolor="whitesmoke",
            edgecolor="dimgray",
            linewidth=0.25,
            linestyle="--",
            # alpha=0.5,
        )

        # Add state borders
        ax.add_feature(
            self._cartopy.feature.STATES, linewidth=0.25, edgecolor="dimgray"
        )

        # Add international borders
        ax.add_feature(
            self._cartopy.feature.BORDERS.with_scale(resolution),
            linewidth=0.25,
            edgecolor="dimgray",
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
                edgecolor="dimgray",
                transform=self._projection,
                zorder=10,
                linewidth=0.25,
            )

    def graph_pie_chart(
        self,
        df,
        bins=(0, 10, 30, 60, float("inf")),
        sizes=(100, 200, 300, 400),
        ax=None,
        title="Power Capacity (GW)",
        legend=True,
    ):
        """
        Graphs the data from the dataframe to a map pie chart.
        The dataframe should have 3 columns, gen_load_zone, gen_type and value.
        """
        _, center_points = self._load_maps()

        if ax is None:
            ax = self.draw_base_map()
        df = df.merge(center_points, on="gen_load_zone")

        assert not df["gen_type"].isnull().values.any()
        colors = self._tools.get_colors()
        lz_values = df.groupby("gen_load_zone")[["value"]].sum()
        if (lz_values["value"] == 0).any():
            raise NotImplementedError(
                "Can't plot when some load zones have total value of 0"
            )
        lz_values["size"] = self._tools.pd.cut(lz_values.value, bins=bins, labels=sizes)
        if lz_values["size"].isnull().values.any():
            lz_values["size"] = 150
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

        if legend:
            legend_points = []
            for size, label in zip(sizes, self._tools.create_bin_labels(bins)):
                legend_points.append(
                    ax.scatter([], [], c="k", alpha=0.5, s=size, label=str(label))
                )
            legend = ax.legend(
                handles=legend_points,
                title=title,
                labelspacing=0.75,
                bbox_to_anchor=(1, 0),
                framealpha=0,
                loc="lower left",
                fontsize="small",
                title_fontsize="small",
            )
            ax.add_artist(
                legend
            )  # Required, see : https://matplotlib.org/stable/tutorials/intermediate/legend_guide.html#multiple-legends-on-the-same-axes

            legend_points = []
            for tech in df["gen_type"].unique():
                legend_points.append(
                    ax.scatter([], [], c=colors[tech], marker="s", label=tech)
                )

            legend = ax.legend(
                handles=legend_points,
                ncol=5,
                loc="upper left",
                bbox_to_anchor=(0, 0),
                # framealpha=0,
                fontsize="small",
                title_fontsize="small",
                labelspacing=0.3,
            )
            ax.add_artist(legend)

        return ax

    def graph_duration(
        self,
        df,
        bins=(0, 4, 6, 8, 10, float("inf")),
        ax=None,
        title="Storage duration (h)",
        **kwargs
    ):
        return self.graph_points(df, bins=bins, ax=ax, title=title, **kwargs)

    def graph_points(
        self, df, bins, cmap="RdPu", ax=None, size=30, title=None, legend=True
    ):
        """
        Graphs the data from the dataframe to a points on each cell.
        The dataframe should have 2 columns, gen_load_zone and value.
        """
        _, center_points = self._load_maps()

        if type(cmap) == str:
            cmap = self._tools.plt.pyplot.get_cmap(cmap)

        if ax is None:
            ax = self.draw_base_map()
        df = df.merge(center_points, on="gen_load_zone", validate="one_to_one")
        n = len(bins)
        colors = [cmap(x / (n - 2)) for x in range(n - 1)]
        df["color"] = self._tools.pd.cut(df.value, bins=bins, labels=colors)
        if "size" not in df.columns:
            df["size"] = size
        for i, row in df.iterrows():
            x, y = row["geometry"].x, row["geometry"].y
            ax.scatter(
                x,
                y,
                s=row["size"],
                color=row["color"],
                transform=self._projection,
                zorder=10,
                linewidth=0.5,
                edgecolor="dimgray",
            )
        legend_handles = [
            self._tools.plt.lines.Line2D(
                [],
                [],
                color=c,
                marker=".",
                markersize=7.5,
                label=l,
                linestyle="None",
                markeredgewidth=0.5,
                markeredgecolor="dimgray",
            )
            for c, l in zip(colors, self._tools.create_bin_labels(bins))
        ]
        if legend:
            legend = ax.legend(
                title=title,
                handles=legend_handles,
                bbox_to_anchor=(1, 1),
                loc="upper left",
                framealpha=0,
                fontsize="small",
                title_fontsize="small",
                # labelspacing=1
            )
            ax.add_artist(
                legend
            )  # Required, see : https://matplotlib.org/stable/tutorials/intermediate/legend_guide.html#multiple-legends-on-the-same-axes
        return legend_handles

    def graph_transmission_capacity(
        self, df, bins=(0, 1, 5, 10, float("inf")), title="Tx Capacity (GW)", **kwargs
    ):
        self.graph_lines(df, bins=bins, title=title, **kwargs)

    def graph_load_zone_colors(self, colors, ax):
        _, center_points = self._load_maps()

        if ax is None:
            ax = self.draw_base_map()

        for _, lz in self._wecc_lz.iterrows():
            # Add load zone borders
            ax.add_geometries(
                lz.geometry,
                crs=self._projection,
                facecolor=colors.loc[lz.gen_load_zone],
                edgecolor="dimgray",
                linewidth=0.25,
                linestyle="--",
                # alpha=0.8,
            )

    def graph_lines(
        self,
        df,
        bins,
        ax=None,
        legend=True,
        widths=(0.25, 0.5, 1, 1.5),
        color="red",
        bbox_to_anchor=(1, 0.3),
        title=None,
    ):
        """
        Graphs the data frame a dataframe onto a map.
        The dataframe should have 4 columns:
        - from: the load zone where we're starting from
        - to: the load zone where we're going to
        - value: the value to plot
        """
        if ax is None:
            ax = self.draw_base_map()
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
        df = df[df.value != 0]  # Drop lines with no thickness
        # Cast to GeoDataFrame
        df = self._geopandas.GeoDataFrame(
            df[["geometry", "value"]], geometry="geometry"
        )
        df["width"] = self._tools.pd.cut(df.value, bins=bins, labels=widths)
        if df["width"].isnull().values.any():
            df["width"] = 0.5
            warnings.warn(
                "Not using variable widths for tx lines since values were out of bounds during binning"
            )
        df.plot(ax=ax, legend=legend, lw=df["width"], color=color)

        if legend:
            legend_points = []
            for width, label in zip(widths, self._tools.create_bin_labels(bins)):
                legend_points.append(
                    ax.plot([], [], c=color, lw=width, label=str(label))[0]
                )
            legend = ax.legend(
                handles=legend_points,
                title=title,
                bbox_to_anchor=bbox_to_anchor,
                framealpha=0,
                loc="center left",
                fontsize="small",
                title_fontsize="small",
            )
            ax.add_artist(
                legend
            )  # Required, see : https://matplotlib.org/stable/tutorials/intermediate/legend_guide.html#multiple-legends-on-the-same-axes

        return ax
