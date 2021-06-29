# REAM Model Changelog

This file specifies the changes that we have done to the model.

Pull requests that change the model in a way that will impact our
results should list their changes here. Pull requests that don't affect our results 
(e.g. improvements to performance, refactors, workflow, etc.) should not
update this file.

## Changes to model

Changes are listed from oldest (first line) to newest (last line of table).

| PR | Month | Change description |
| ---- | --- | ---------------------|
| #8 | Feb 2021 | feat: Add support for other types of GHGs (NOx, SO2, CH4) |
| #12 | March 2021 |fix: use the middle of the period instead of the start as the cutoff for retirement and predetermined buildout. |
| #15 | March 2021 |fix: Fix bug where storage costs where being over-counted. |
| #36 | May 2021 |fix: Remove duplicate transmission lines |
| #10 | June 2021 | feat: Add support for California policies module |
| #40  | June 2021 | feat: Add support for planning reserves module |
| #50 | June 2021 | Upgraded to Pyomo 6.0 |
| #56 | June 2021 | fix: Convert 2020 predetermined build years to 2019 in get_inputs to avoid conflicts with 2020 period. |
| #57 | June 2021 | fix: specify predetermined storage energy capacity (previously left unspecified). |
| #42 | June 2021| feat: Add parameters to the storage module for self-discharge rate, land use and discharge efficiency. |
| #68 | June 2021 | fix: change financial params to 2018 dollars & 5% interest rate. Start using terrain multipliers (which now include the economic multiplier). |