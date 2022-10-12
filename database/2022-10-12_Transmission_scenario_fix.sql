-- October 12, 2022
-- Author: pesap

-- Reason: We detected a type in the transmission derating factor for all the transmission
-- lines for the WECC model. This is the description in the switch module of what the
-- transmission derate factor does: trans_derating_factor[tx in TRANSMISSION_LINES] is an
-- overall derating factor for each transmission line that can reflect forced outage
-- rates, stability or contingency limitations. This parameter is optional and defaults to
-- 1. This parameter should be in the range of 0 to 1, being 0 a value that disables the
-- line completely.
-- In our scenarios we have been using 0.59 for no apparent reason and this limited the
-- amount of electricity that flow throught the transmission line. The new value that we
-- will use for the scenarios is 0.95 or a 5% derate.


UPDATE switch.transmission_lines SET derating_factor = 0.95;
