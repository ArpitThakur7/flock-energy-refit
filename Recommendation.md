# Recommendation: using washing-machine disaggregation at a utility

**In short:** using nothing but a home's 1-minute smart meter reading, the model spots about 8 out of 10 washes in homes it has never seen before, and its daily estimate of washing-machine energy is 28% more accurate than assuming zero. That's good enough for insights about patterns and for grouping customers, such as when and how often a home washes, or which homes are heavy users. It isn't good enough yet to put an exact washing-machine kWh figure on one customer's bill. These results come from 12 UK homes in the REFIT study (2013 to 2015), testing on each home in turn after training on the other 11.

## What it's good for

| Use | Why it holds up |
|---|---|
| Spotting whether, how often and when a home does its washing | 81% of washes are caught, and the start-time pattern comes through reliably |
| Grouping or ranking customers, for example heavy washers or people who wash at peak times | In most homes, washing days stand out clearly from non-washing days |
| Estimates across many homes, for example the total washing load on a feeder between 8 and 11am | Mistakes cancel out across homes: over all 12, the total energy estimate was within 3% |

## What it's not ready for

- **Quoting one home's exact washing-machine kWh.** For an individual home, the total can be off by 50% to 100%.
- **Making automatic decisions about, or penalising, an individual customer.** Roughly 6 in 10 predicted washes are really another heating appliance, such as a shower, oven or dishwasher.
- **Homes with unusual machines.** In one test home, the washing machine heated in short bursts and the model missed most of its washes.
- **Data at 15 or 30 minutes.** See the last section below.

---

## Section 4 answers

### An opportunity: moving washes out of peak times

**What I found.** Of all washes, 44% start between 7am and noon, and the single busiest time is Saturday at 9am. Two of the 12 homes already use their delay timers to wash at night: House 19 starts 58% of its washes between 10pm and 1am, and House 1 starts 21% between 3am and 6am. Each wash draws about 2 kW for 10 to 25 minutes. That's a big, short block of demand that can easily be moved, since nearly every modern machine has a delay-start button and no new equipment is needed.

**What I'd offer.** Customers the model picks out as regular morning- or evening-peak washers would get a personalised nudge, something like: "Your washing machine usually runs around 9am. If you set the delay timer to finish by 7am, you could save about £X a year on an off-peak tariff." Where there's a time-of-use tariff or a demand-flexibility event, the message would tie into that.

**How I'd check it worked.**

- **Set-up:** a randomised trial. Take the customers the model flags, record 4 to 8 weeks of normal behaviour first, then randomly split them into a group that gets the message and a group that doesn't.
- **Main measure:** the share of each customer's detected washes that start at peak times (for example 7 to 11am and 4 to 7pm), compared before and after and between the two groups. The same model is applied to both groups, so its mistakes affect them equally and the difference between them still holds.
- **Other measures:** peak-time energy use, the 9am load on the local network, and bill savings for customers on time-of-use tariffs.
- **Ground truth:** a quick text or in-app question to a sample of customers, such as "Did you use the delay timer this week?". It checks the result and gives labelled data to improve the model.

Overall consumption won't really change, because a wash uses the same energy whenever it runs. The value is in lowering peak demand and cutting customers' bills, and that's how the trial should be judged.

### Limitations

**Appliances that look alike.** Most of a wash's energy is a heating block of around 2 kW, and kettles, showers, ovens, dishwashers and tumble dryers produce very similar blocks. This is the model's biggest source of error, with about 61% of predicted washes being false alarms, and it's why I'd stick to grouped and pattern-based insights for now.

**Missing data.** Homes lose 6% to 25% of their minutes to outages, sometimes for weeks at a time. I never fill long gaps, so any figure shown to a customer should be worked out over the days that are actually available and say so (for example, "based on 26 of the last 30 days"). The dataset's own "Issues" flag would have removed about a third of the minutes when washing machines are running, so I didn't use it.

**Differences between homes.** Homes do anywhere from 2 to 11 washes a week, and a wash uses between 0.24 and 0.72 kWh depending on the machine and programme. A machine unlike any in training, like the one in House 19, gets mostly missed. Before launching in a new market, the model should be checked against a small labelled pilot group there.

**Using UK results in India.** The REFIT homes are mostly detached UK houses with washing machines that heat their own water. Indian homes differ in ways that matter here:

- Many machines have no heater, including semi-automatic top-loaders and many front-loaders run on cold washes. Without the 2 kW heating block, which is the model's strongest clue, a wash looks like a 200 to 500 W motor pattern that's much harder to pick out.
- The big appliances are different: air conditioners, water heaters (geysers), water pumps and inverter battery charging all produce large blocks of their own.
- Voltage varies more and power cuts are more common.
- Metering is often single-phase and lower resolution.

The overall approach would carry over: the cleaning steps, the wash rule and the leave-one-house-out testing. But the model would need retraining and re-testing on labelled Indian homes, and the wash thresholds would need resetting, for example a lower peak threshold for machines without a heater.

### What changes with 15- or 30-minute data

At 15 or 30 minutes, each reading averages over most or all of a wash's 10 to 25 minute heating block. The 2 kW block shrinks into a bump of a few hundred watts, about the same as boiling a kettle a few times or a hob on low. The details that make a wash recognisable, its tail, start and finish, get averaged away, and a wash that starts mid-interval gets split across two readings. Telling washes apart from everything else becomes much harder. I'd expect to reliably catch only long, hot washes during otherwise quiet periods, and to get far more confused during busy mornings and evenings. Estimates would have to move to daily or weekly totals with a range attached, along the lines of "probably 3 to 5 washes this week". The model would also have to rely more on habits (time of day, day of week) and household details, which means it would cope worse with unusual homes. You could still tell a customer roughly when they wash, to the nearest half hour, but not count individual washes or say how much energy each one used.
