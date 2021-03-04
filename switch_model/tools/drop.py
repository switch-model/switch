import os
import pandas
from switch_model.utilities import query_yes_no
from argparse import ArgumentParser, RawTextHelpFormatter

"""
This file offers the command line utility 'switch drop'.
switch drop allows you to drop entire periods or load zones from 
the input CSVs to form a smaller model that is easier to test.
Usage details can be found by running 'switch drop -h'.
"""

# data_types is a dictionary where each key-value pair is a type of switch ID
# that we can filter out. For example, we can filter out load zones or periods.
#
# Each value in the dictionary is a tuple containing the primary file and a list
# of files to check. The primary file is the file containing the complete list
# of valid IDs for that data type. The list of files to check is a list of files
# through which we will remove rows where the ID is not found in the primary file.
#
# Each "file" is actually a tuple where the first element is the filename, and the
# second element is the relevant column name
data_types = {
    "load_zones": (
        ('load_zones.csv', "LOAD_ZONE"),
        [
            ('fuel_cost.csv', 'load_zone'),
            ('generation_projects_info.csv', 'gen_load_zone'),
            ('loads.csv', 'LOAD_ZONE'),
            ('rps_targets.csv', 'load_zone'),
            ('transmission_lines.csv', 'trans_lz1'),
            ('transmission_lines.csv', 'trans_lz2'),
            ('zone_balancing_areas.csv', 'LOAD_ZONE'),
            ('zone_to_regional_fuel_market.csv', 'load_zone')
        ]
    ),
    "regional_fuel_markets": (
        ('zone_to_regional_fuel_market.csv', "regional_fuel_market"),
        [
            ('fuel_supply_curves.csv', 'regional_fuel_market'),
            ('regional_fuel_markets.csv', 'regional_fuel_market')
        ]
    ),
    "balancing_areas": (
        ('zone_balancing_areas.csv', "balancing_area"),
        [
            ('balancing_areas.csv', "BALANCING_AREAS")
        ]
    ),
    "periods": (
        ('periods.csv', "INVESTMENT_PERIOD"),
        [
            ('carbon_policies.csv', 'PERIOD'),
            ('fuel_cost.csv', 'period'),
            ('fuel_supply_curves.csv', 'period'),
            ('rps_targets.csv', 'period'),
            ('timeseries.csv', 'ts_period'),
            # It is impossible to know if a row in gen_build_costs.csv is for predetermined generation or for
            # a period that was removed. So instead we don't touch it and let the user manually edit
            # the input file.
        ]
    ),
    "timeseries": (
        ('timeseries.csv', 'TIMESERIES'),
        [
            ('hydro_timeseries.csv', 'timeseries'),
            ('timepoints.csv', 'timeseries')
        ]
    ),
    "timepoints": (
        ('timepoints.csv', 'timepoint_id'),
        [
            ('loads.csv', 'TIMEPOINT'),
            ('variable_capacity_factors.csv', 'timepoint')
        ]
    ),
    "projects": (
        ('generation_projects_info.csv', "GENERATION_PROJECT"),
        [
            ('gen_build_costs.csv', 'GENERATION_PROJECT'),
            ('gen_build_predetermined.csv', 'GENERATION_PROJECT'),
            ('hydro_timeseries.csv', 'hydro_project'),
            ('variable_capacity_factors.csv', 'GENERATION_PROJECT')
        ]
    ),
}


def main(args=None):
    # Setup parser & validate user input
    parser = ArgumentParser(
        description="Drops subsets of the input data to form a smaller model that is easier to debug.",
        epilog="To use this command,\n"
               "\t1) Remove the subset you wish to drop. For example, if you want to drop some load zones, "
               "remove them from load_zones.csv. If you want to drop periods, remove them from periods.csv.\n\n"
               "\t2) Run 'switch drop --run' to remove all the references to now missing keys. For example"
               " if you've removed a load zone, all the projects, transmissions lines, etc. for that load "
               "zone will be removed from the input files.",
    formatter_class=RawTextHelpFormatter)

    parser.add_argument('--run', default=False, action='store_true', help='Drop the data.')
    parser.add_argument('--inputs-dir', default='inputs', help='Directory of the input files. Defaults to "inputs".')
    args = parser.parse_args(args)

    if not args.run:
        parser.print_help()
        return

    if not os.path.isdir(args.inputs_dir):
        raise NotADirectoryError("{} is not a directory".format(args.inputs_dir))

    should_continue = query_yes_no("WARNING: This will permanently delete data from directory '{}' "
                                   "WITHOUT backing it up. Are you sure you want to continue?".format(args.inputs_dir))

    if not should_continue:
        print("Operation cancelled.")
        return

    # We do multiple passes since one data type can remove a key from another data type which would only be
    # Caught on a second pass
    # We stop the passes when now rows have been removed.
    total_rows_removed = 0
    warn_about_periods = False
    pass_count = 0
    while pass_count == 0 or rows_removed_in_pass != 0:
        print("Pass {}...".format(pass_count), flush=True)
        rows_removed_in_pass = 0
        for name, data_type in data_types.items():
            print("Checking '{}'...".format(name), flush=True)
            rows_removed = drop_data(data_type, args)
            rows_removed_in_pass += rows_removed

            if name == "periods" and rows_removed != 0:
                warn_about_periods = True
        print("Removed {} rows during pass.".format(rows_removed_in_pass))

        total_rows_removed += rows_removed_in_pass
        pass_count += 1

    print("\n\nRemove {} rows in total from the input files.".format(total_rows_removed))
    print("\n\nNote: If SWITCH fails to load the model when solving it is possible that some input files were missed."
          " If this is the case, please add the missing input files to 'data_types' in 'switch_model/tools/drop.py'.")

    # It is impossible to know if a row in gen_build_costs.csv is for predetermined generation or for
    # a period that was removed. So instead we don't touch it and let the user manually edit
    # the input file.
    if warn_about_periods:
        print("\n\nWARNING: Could not update gen_build_costs.csv. Please manually edit gen_build_costs.csv to remove "
              "references to the removed periods.")


def drop_data(id_type, args):
    primary_file, files_to_check = id_type
    valid_ids = get_valid_ids(primary_file, args)

    if valid_ids is None:
        return 0

    rows_removed = 0
    for filename, foreign_key in files_to_check:
        rows_removed += drop_from_file(filename, foreign_key, valid_ids, args)
    return rows_removed


def get_valid_ids(primary_file, args):
    filename, primary_key = primary_file
    path = os.path.join(args.inputs_dir, filename)

    if not os.path.exists(path):
        print("\n Warning: {} was not found.".format(filename))
        return None

    valid_ids = pandas.read_csv(path)[primary_key]
    return valid_ids


def drop_from_file(filename, foreign_key, valid_ids, args):
    path = os.path.join(args.inputs_dir, filename)

    if not os.path.exists(path):
        return

    df = pandas.read_csv(path)
    count = len(df)
    df = df[df[foreign_key].isin(valid_ids)]
    rows_removed = count - len(df)

    if rows_removed != 0:
        df.to_csv(path, index=False)

        print("Removed {} rows {}.".format(rows_removed, filename))
        if rows_removed == count:
            print("WARNING: {} is now empty.".format(filename))

    return rows_removed


if __name__ == '__main__':
    main()
