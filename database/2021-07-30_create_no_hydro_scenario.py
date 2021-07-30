"""
####################
Create a no hydro scenario

Date applied: 2021-07-30
Description:
This script adds a scenario to the database that effectively removes all hydro generation from the model.
#################
"""
import time

from switch_model.utilities import query_yes_no, format_seconds
from switch_model.wecc.utilities import connect
import pandas as pd

all_plants_scenario = 23

new_scenario_id = 25
new_scenario_name = "No Hydro"
new_scenario_description = "All average flows are zero effectively removing all hydro generation from the model." \
                           " Represents as an extreme edge case of no hydro generation."


def main():
    db_conn = connect()
    db_cursor = db_conn.cursor()

    # 1. Get all the hydro plants
    db_cursor.execute(
        f"""
        SELECT DISTINCT generation_plant_id, year, month, hydro_min_flow_mw, hydro_avg_flow_mw FROM hydro_historical_monthly_capacity_factors
        WHERE hydro_simple_scenario_id={all_plants_scenario};
    """)
    df = pd.DataFrame(db_cursor.fetchall(),
                      columns=["generation_plant_id", "year", "month", "hydro_min_flow_mw", "hydro_avg_flow_mw"])

    # 2. Set all the flows to zero and set the scenario id
    df["hydro_min_flow_mw"] = 0
    df["hydro_avg_flow_mw"] = 0
    df["hydro_simple_scenario_id"] = new_scenario_id

    # 3. Add data to database
    print(f"hydro_simple_scenario: {new_scenario_id}")
    print(f"name: {new_scenario_name}")
    print(f"description: {new_scenario_description}")
    print(f"Num hydro plants: {df.generation_plant_id.nunique()}")
    print(f"Example data:\n{df.head()}")

    if not query_yes_no("\nAre you sure you want to add this data to the database?", default="no"):
        raise SystemExit

    db_cursor.execute(
        "INSERT INTO hydro_simple_scenario(hydro_simple_scenario_id, name, description) "
        f"VALUES ('{new_scenario_id}','{new_scenario_name}','{new_scenario_description}')"
    )

    n = len(df)
    start_time = time.time()
    for i, r in enumerate(df.itertuples(index=False)):
        if i != 0 and i % 1000 == 0:
            print(
                f"{i}/{n} inserts completed. Estimated time remaining {format_seconds((n - i) * (time.time() - start_time) / i)}")
        db_cursor.execute(
            f"INSERT INTO hydro_historical_monthly_capacity_factors(hydro_simple_scenario_id, generation_plant_id, year, month, hydro_min_flow_mw, hydro_avg_flow_mw) "
            f"VALUES ({r.hydro_simple_scenario_id},{r.generation_plant_id},{r.year},{r.month},{r.hydro_min_flow_mw},{r.hydro_avg_flow_mw})"
        )

    db_conn.commit()
    db_cursor.close()
    db_conn.close()
    print("Done.")


if __name__ == "__main__":
    main()
