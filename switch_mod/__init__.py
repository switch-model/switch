"""

This package defines the Switch model for Pyomo.

The core modules in this package are timescales, financials, load_zones,
fuels, gen_tech, and project.

For the moment fuel_markets is also required, although I hope to write a
simple replacement for it that just uses simple flat costs instead of a
tiered supply curve.

Also, an additional module is required to constrain project dispatch -
either project.no_commit or project.unitcommit.

Most applications of this Switch will also benefit from optional modules
such as transmission, local_td, reserves, etc.

I wrote some magic sauce so that you can treat this package as a module
that includes all of the core modules instead of having to refer to them
individually. This means you can either specify your module list as:

switch_modules = ('switch_mod', 'project.no_commit', 'fuel_markets')

or as

switch_modules = (
    'timescales', 'financials', 'load_zones', 'fuels', 'gen_tech',
    'project', 'project.no_commit', 'fuel_markets')

You will get an error if you include both the package and the core modules,
because they are redundant.

"""

core_modules = [
    'timescales', 'financials', 'load_zones', 'fuels', 'gen_tech', 'project']
