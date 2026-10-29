# Recommendation: washing-machine disaggregation for utility use

**Bottom line:** using only a home's 1-minute whole-house meter, the model finds about **8 in 10 washes** in homes it has never seen. Its **daily** washing-machine energy estimate is 28% more accurate than assuming zero. It is ready for **aggregated and pattern-based insights** (when and how often a home washes, which homes are heavy users). It is **not** ready for exact per-home kWh figures on a bill. Tested on 12 UK homes from REFIT, 2013–2015, holding out one home at a time.

## Suitable uses

| Use | Why it is supported |
|---|---|
| Detect whether, how often and when a home washes | 81% of washes found; the start-hour pattern is reliable |
| Rank or segment customers (heavy washers, peak-time washers) | Wash days are clearly separated from non-wash days in most homes |
| Portfolio-level estimates (e.g. washing load at 08:00–11:00 across a feeder) | Errors cancel out across homes: −3% total energy error pooled over 12 homes |

## Not suitable (yet)

* **An exact kWh figure for one home's washing machine.** Single-home totals can be off by ±50–100%.
* **Automated decisions or penalties for an individual customer.** About 6 in 10 predicted washes are other heating appliances such as showers, ovens and dishwashers.
* **Homes with unusual machines.** One test home with a short-burst heater was mostly missed. **Data at 15 or 30 minutes**: see below.

---

## Section 4 answers

### Opportunity: shift washes out of the morning peak and toward cheap off-peak hours

**Finding.** 44% of washes start between 07:00 and 12:00, and the busiest slot is Saturday 09:00. Two of the 12 homes already use delay timers to wash at night: House 19 starts 58% of washes between 22:00 and 01:00, and House 1 starts 21% between 03:00 and 06:00. Each wash draws about **2 kW for 10–25 minutes**, a large, short and **movable** block. Nearly every modern machine has a delay-start button, so shifting a wash needs no new hardware.

**Offer.** Customers the model flags as frequent morning or evening-peak washers get a tailored message ("Your washing machine usually runs around 9 am. Setting the delay timer to finish by 7 am on the off-peak rate would save about £X a year"). Where a time-of-use tariff or a demand-flexibility event exists, link it to that.

**Measuring whether it worked.**
* *Design:* a randomised controlled trial. Randomly split the flagged customers into a group that gets the message and a control group that does not, and record a baseline period of 4–8 weeks before sending.
* *Primary metric:* the share of detected washes starting in peak hours (e.g. 07:00–11:00 and 16:00–19:00), per customer, before vs after, treatment vs control (difference-in-differences). The same detector is applied to both groups, so its errors affect them equally and the *difference* stays valid.
* *Secondary metrics:* peak-hour kWh and the 09:00 load at feeder level, and bill savings for customers on time-of-use tariffs.
* *Ground truth check:* a short in-app or SMS question ("Did you use the delay timer this week?") for a sample of customers, which also gives labelled data to improve the model.

Total consumption barely changes, because a wash uses the same energy whenever it runs. The value is in **peak reduction and lower cost for the customer**, and the evaluation should be framed that way.

### Limitations

* **Overlapping appliance signatures.** The washing machine's main energy is a ~2 kW heating plateau, and kettles, showers, ovens, dishwashers and tumble dryers create similar blocks. This is the largest source of error (about 61% of predicted washes are false) and the reason we recommend aggregated and pattern-based outputs.
* **Missing data.** Homes lose 6–25% of minutes to outages, including gaps of weeks. We never fill long gaps. Any customer-facing figure must be calculated over available days and say so (e.g. "based on 26 of 30 days"). The official REFIT "Issues" flag would remove a third of washing-machine minutes, so we did not rely on it.
* **Household differences.** Washes per week range from 2 to 11, and energy per wash from 0.24 to 0.72 kWh, by machine and programme. A machine unlike those in training (House 19) is mostly missed. Performance in a new market must be checked on a labelled pilot before launch.
* **Applying UK results to India.** The UK homes are mostly detached houses with heater-equipped washers that heat their own water. Indian homes differ in several ways that matter:
  * Many machines (semi-automatic top-loaders, many front-loaders on cold washes) have **no heater**, so the 2 kW plateau, the model's strongest clue, is absent. A wash becomes a 200–500 W motor pattern, much harder to separate.
  * Other dominant loads differ: air conditioners, water heaters (geysers), water pumps, and inverter/UPS battery charging all create large blocks.
  * There is more voltage variation and more power cuts.
  * Metering is often single-phase and at lower resolution.

  The pipeline (cleaning, cycle rule, leave-one-house-out validation) transfers, but **the model must be retrained and re-validated on labelled Indian homes**, and the cycle thresholds re-set (e.g. a lower peak threshold for machines without heaters).

### If only 15- or 30-minute smart-meter data were available

At 15–30 minutes a single reading averages over most or all of a wash's 10–25 minute heating plateau. The 2 kW block becomes a modest bump of a few hundred watts, the same size as a kettle used a few times or a cooker on low. The tail, start and end that make a wash recognisable are averaged away, and a wash that starts mid-interval is split across two readings. Telling washes apart from other loads would become much harder: we would expect reliable detection only for hot, long programmes in otherwise quiet periods, and much more confusion during busy morning and evening hours. Estimates would have to move to **daily or weekly totals and probabilistic statements** ("likely 3–5 washes this week"). The model would also lean more on habits (time of day, day of week) and household information, so it would generalise worse to unusual homes. Timing insights such as "you wash at 9 am" would still be possible to the nearest half-hour. Exact cycle counts and per-wash energy would not.
