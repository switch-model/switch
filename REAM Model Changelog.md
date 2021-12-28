# REAM Model Breaking Changes

This file specifies the breaking changes that we have done to the model.
A breaking change is any change that would change the results of previously
completed runs.

## List of breaking changes to model

Changes are listed from oldest (first line) to newest (last line of table).

| PR | Estimated Merge Time (check PR for exact date) | Change description |
| ---- | --- | ---------------------|
| #12 | March 2021 | Use the middle of the period instead of the start as the cutoff for retirement and predetermined buildout. |
| #15 | March 2021 | Fix bug where storage costs where being over-counted. |
| #36 | May 2021 | Correct inputs to only list transmission lines in one direction. |
| #56 | June 2021 | Convert 2020 predetermined build years to 2019 in `get_inputs.py` to avoid conflicts with 2020 period. |
| #57 | June 2021 | Specify predetermined storage energy capacity in inputs (previously left unspecified). |
| #68 | June 2021 | Change financial params to 2018 dollars & 5% interest rate. Start using terrain multipliers (which now include the economic multiplier). |
| #72 | July 2021 | Drop build and O&M costs of existing transmission lines. |
| #89 | August 2021 | Change hydro module average flow constraint to a monthly constraint rather than per timeseries and change it to a <= rather than ==. |
| #90 | August 2021 | Change the lifetime of transmission lines from 20yr to 85yr |