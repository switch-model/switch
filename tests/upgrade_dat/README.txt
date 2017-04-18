This is a set of input directories with old versions that test upgrade
functionality.

If you edit the code in a way that requires adding a new upgrade plugin, you
should update inputs in the examples directory, but you should not update
these input files because they will test that your upgrade plugin is
performing as expected.

If you fix a bug in the code that changes the objective function value, you
should update the total_cost.txt files in these directories.

You may add test cases to this directory, especially if you notice a bug in
how switch upgrades your data. Please keep new test cases as small as possible
so that the test suite will continue to run quickly.
