# Stage 6: dated Codal evidence and fund separation

The financial gate converts explicit Jalali publication dates to Gregorian using `persiantools`; invalid dates and publications after the analysis date cannot be scored. Equity scoring now selects whole reports among revisions available at the cutoff, so a later restatement cannot replace a historical decision. Fund reports use the same cutoff and remain separate from company EPS and growth scoring. Fund NAV/unit must be a positive observed cell with report ID, location and unit. A zero placeholder is reported as unusable, not a valuation signal.

Codal rate limits and partial sync remain visible. Historical fund net asset series, holdings and independently verified current NAV are unavailable when source reports do not provide them; no value is inferred from price. Publication times on the cutoff day are interpreted as end-of-day availability because the current analysis contract has a date, not an intraday timestamp.
