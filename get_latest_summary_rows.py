from collections import OrderedDict

with open("demand_response_summary.tsv") as f:
    data=f.read().splitlines()
dd = OrderedDict()
latest = dict()
for row in data[1:]:
    cols = row.split('\t')
    scen = cols[0]
    iter = int(cols[1])
    if iter > latest.get(scen, -1):
        latest[scen] = iter
        dd[scen] = row

with open("demand_response_summary_latest.tsv", "w") as f:
    f.write(data[0]+"\n")
    f.write("\n".join(dd.values()) + "\n")
