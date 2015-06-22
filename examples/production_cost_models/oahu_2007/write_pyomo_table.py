import csv
import os
import sys
import psycopg2
import time
from textwrap import dedent

# TODO: set this up to use ssl certificates or an SSH tunnel, because
# otherwise postgres sends the password over the network as clear text.

# define formatting options for pyomo .tab files
# these are similar to ampl, but don't have ampl's extra headers ("ampl.tab\n<#_index_cols> <#_cols>\n")
csv.register_dialect("ampl-tab", 
    delimiter="\t", 
    lineterminator="\n",
    doublequote=False, escapechar="\\", 
    quotechar='"', quoting=csv.QUOTE_MINIMAL,
    skipinitialspace = False
)

try:
    pghost='switch.eng.hawaii.edu'
    # note: the connection gets created when the module loads and never gets closed (until presumably python exits)
    con = psycopg2.connect(database='switch', host=pghost, user='switch_user')
    
except psycopg2.OperationalError:
    print dedent("""
        ############################################################################################
        Error while connecting to switch database on postgres server {server} as user 'switch_user'.
        Please ensure that there is a line like "*:*:*:switch_user:<password>" in 
        ~/.pgpass (which should be chmod 0600) or %APPDATA%\postgresql\pgpass.conf (Windows).    
        See http://www.postgresql.org/docs/9.1/static/libpq-pgpass.html for more details.
        ############################################################################################
        """.format(server=pghost))
    raise

def write_table(output_file, query, arguments):
    cur = con.cursor()

    print "Writing {file} ...".format(file=output_file),
    sys.stdout.flush()  # display the part line to the user

    start=time.time()
    cur.execute(dedent(query), arguments)

    with open(output_file, 'wb') as f:
        w = csv.writer(f, dialect="ampl-tab")
        # write header row
        w.writerow([d[0] for d in cur.description])
        # write the query results (cur is used as an iterator here to get all the rows one by one)
        w.writerows(cur)

    print "time taken: {dur:.2f}s".format(dur=time.time()-start)
