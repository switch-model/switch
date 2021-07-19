import pandas as pd

from switch_model.wecc.get_inputs.register_post_process import register_post_process


@register_post_process("Replacing _ALL_ZONES plants with a plant in each zone")
def replace_plants_in_zone_all():
    """
    This post-process step replaces all the generation projects that have a load called
    _ALL_ZONES with a generation project for each load zone.
    """
    # Read load_zones.csv
    load_zones = pd.read_csv("load_zones.csv", index_col=False)
    load_zones["dbid_suffix"] = "_" + load_zones["zone_dbid"].astype(str)
    num_zones = len(load_zones)

    def replace_rows(plants_to_copy, filename, df=None, plants_col="GENERATION_PROJECT", load_column=None):
        # If the df does not already exist, read the file
        if df is None:
            df = pd.read_csv(filename, index_col=False)

        # Save the columns for later use
        df_col = df.columns
        df_rows = len(df)

        # Force the plants_col to string type to allow concating
        df = df.astype({plants_col: str})

        # Extract the rows that need copying
        should_copy = df[plants_col].isin(plants_to_copy)
        rows_to_copy = df[should_copy]
        # Filter out the plants that need replacing from our data frame
        df = df[~should_copy]
        # replacement is the cross join of the plants that need replacement
        # with the load zones. The cross join is done by joining over a column called
        # key that is always 1.
        replacement = rows_to_copy.assign(key=1).merge(
            load_zones.assign(key=1),
            on='key',
        )

        replacement[plants_col] = replacement[plants_col] + replacement["dbid_suffix"]

        if load_column is not None:
            # Set gen_load_zone to be the LOAD_ZONE column
            replacement[load_column] = replacement["LOAD_ZONE"]

        # Keep the same columns as originally
        replacement = replacement[df_col]

        # Add the replacement plants to our dataframe
        df = df.append(replacement)

        assert len(df) == df_rows + len(rows_to_copy) * (num_zones - 1)

        df.to_csv(filename, index=False)

    plants = pd.read_csv("generation_projects_info.csv", index_col=False)
    # Find the plants that need replacing
    to_replace = plants[plants["gen_load_zone"] == "_ALL_ZONES"]
    # If no plant needs replacing end there
    if to_replace.empty:
        return
    # If to_replace has variable capacity factors we raise exceptions
    # since the variabale capacity factors won't be the same across zones
    if not all(to_replace["gen_is_variable"] == 0):
        raise Exception("generation_projects_info.csv contains variable plants "
                        "with load zone _ALL_ZONES. This is not allowed since "
                        "copying variable capacity factors to all "
                        "zones is not implemented (and likely unwanted).")

    plants_to_replace = to_replace["GENERATION_PROJECT"]
    replace_rows(plants_to_replace, "generation_projects_info.csv", load_column="gen_load_zone")
    replace_rows(plants_to_replace, "gen_build_costs.csv")
    replace_rows(plants_to_replace, "gen_build_predetermined.csv")