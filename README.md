# SARG-ATHLETE-CONTRACT-EQUIVALENCY-MODEL
Tax-equivalency and recommendation engine for professional athlete contracts across state tax jurisdictions.

# Overview:
On September 8, 2026, the New England Patriots and Christian Gonzalez agreed to a four-year, $135 million contract extension — the largest in NFL history for a cornerback. But the headline number doesn't tell the whole story: Massachusetts imposes a 4% surtax on income over $1,107,750, on top of standard income tax.

This raises the core question the project is built around: after accounting for state tax policy, is Gonzalez's $135M deal actually the most valuable contract a cornerback could sign — and how much would another team need to offer him to match or beat its after-tax value?

This project builds a tax-equivalency model that estimates the after-tax value of pro sports contracts and determines the salary one team would need to offer to match or exceed the effective value of another team's deal.

# Flagship deliverable: recommendation dashboard

The centerpiece of this project is an interactive dashboard that takes two or more competing contract offers and returns a ranked recommendation of which delivers the highest true after-tax value, with a plain-language explanation (e.g. "Offer B is worth $4.2M more after tax due to Florida having no state income tax, despite a $6M lower sticker value").

Planned features, in build order:
  1. Offer comparison & recommendation: Ranks 2–4 competing offers by after-tax value
  2. Break-even calculator: Computes what another team would need to offer to match/beat an existing offer after taxes
  3. State tax "home-field advantage" index: Ranks team locations by tax friendliness at different income levels
  4. What-if scenarios: Simulate a trade or change tax assumptions and see the after-tax impact
  5. Historical validation: Compares real player moves against the model's predicted tax savings/losses
  6. Cost-of-living adjustment (stretch): combines tax and cost-of-living into one comparison
# Repository Structure
/data-sources/   scraper configs, source URLs, refresh schedules
/etl/            ingestion scripts and the tax calculation engine
/schema/         SQL DDL, migrations, entity-relationship diagram
/analysis/       equivalency/recommendation model, notebooks
/dashboard/      recommendation dashboard (comparison, break-even calc, map, sliders)
/docs/           methodology detail, timeline, research paper drafts
