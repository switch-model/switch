
-- April 19, 2022
-- DOE 

-- Importing new wave energy sites with hourly capacity factors
-- Source:
-- Description:


COPY public.wave_colocation_CF
FROM '/home/schoudhury/REAM_lab/newData/switch_wave_CF.csv'
DELIMITER ',' NULL AS 'NULL' CSV HEADER;

-- Quality control:
select * from public.wave_colocation_CF;

select site, count(*) 
from public.wave_colocation_CF
group by site
order by site;




-- Importing new offshore wind sites with hourly capacity factors
-- Source:
-- Description:



COPY public.offshore_colocation_cf
FROM '/home/schoudhury/REAM_lab/newData/switch_offshore_CF.csv'
DELIMITER ',' NULL AS 'NULL' CSV HEADER;

select * from public.offshore_colocation_cf;

select site, count(*) 
from public.offshore_colocation_cf
group by site
order by site;

