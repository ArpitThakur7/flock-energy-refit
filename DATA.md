# Data: coverage, quality and cleaning

## 1. The dataset

I used the REFIT Electrical Load Measurements dataset from the University of Strathclyde (Murray et al., 2017, *Scientific Data* 4:160122), which is released under CC-BY 4.0.

It covers 20 homes around Loughborough in the UK, numbered 1 to 21 (there's no House 14), between September 2013 and July 2015. Each home was monitored for somewhere between 15 and 21 months. Every home has one current clamp on the main supply (the "aggregate", meaning the whole house) and nine plug-in monitors on individual appliances. All readings are active power in watts.

Readings come in roughly every 6 to 8 seconds. The sensors aren't synchronised with each other, so any given reading may be up to 8 seconds old. I worked at 1-minute resolution throughout, using the average of the readings in each minute.

Files I used:

| Part | Files | From |
|---|---|---|
| 1 (cleaning raw data) | `RAW_House1_Part1.csv`, `RAW_House1_Part2.csv` | `REFIT_RAW_081116.7z` |
| 2 and 3 (analysis and model) | `CLEAN_House{1,2,3,4,5,7,15,16,17,18,19,21}.csv` | `CLEAN_REFIT_081116.7z` |

The download links in the brief returned "403 Forbidden" for me. The same files are available at `pure.strath.ac.uk/ws/portalfiles/portal/<id>/<filename>`, which is what `src/get_data.py` uses.

Some limitations worth knowing about up front:

- The appliance labels describe what was plugged in when the monitors were installed. Householders sometimes moved them later, and the readme lists several known changes.
- A "television site" or "computer site" monitor can cover several devices on one extension lead.
- Plug monitors only see plug-in appliances. Hard-wired loads like an electric shower, oven or immersion heater only ever show up in the whole-house reading, so they're never labelled.
- The official cleaned files fill short gaps with the previous value and replace plug readings above 4 kW with zero. Long outages simply have no rows.
- There are some long stretches of missing data, especially in February 2014. The readme puts these down to internet, hardware and network failures.

---

## 2. What I found in the raw House 1 data

These numbers come from `src/part1_clean_raw.py`, which saves them to `outputs/raw_h1_inspection.csv`.

| Check | Part1 (Oct 2013 to Oct 2014) | Part2 (Jun 2014 to Jul 2015) |
|---|---|---|
| Rows | 4,377,877 | 4,140,886 |
| Timestamps that failed to parse | 0 | 0 |
| Times where the clock goes backwards | 1 | 0 |
| Repeated timestamps | 1,004,404 | 14,755 |
| ...of which the whole row is a copy | 884,307 | 393 |
| Typical gap between readings | 3 s (99% under 15 s) | 7 s (99% under 9 s) |
| Gaps longer than 5 min / 1 hour | 380 / 14 | 72 / 19 |
| Longest gap | 998 hours (41.6 days, 24 Jan to 6 Mar 2014) | 208 hours |
| Missing cells | 0% (sensors that weren't reporting were written as 0) | 12.8% (written as blank) |
| Whole-house readings over 15 kW | 82 (highest 24,000 W) | 104 (highest 29,159 W) |
| Plug readings over 4 kW | 3,038 | 911 |
| Highest plug reading | 98,301 W | 98,301 W |
| Negative values | 0 | 0 |

The things that stood out:

1. **The older file (Part1) is in local time, not UTC.** It recorded UK clock time but stored it as if it were UTC. Three things gave this away:

    - The single place where the clock jumps backwards is `2013-10-27 01:59:59` to `01:00:01`. That's exactly when the clocks went back that autumn, so the hour from 1am to 2am appears twice.
    - The 1am hour is missing on 30 March 2014, when the clocks went forward.
    - When I lined up raw readings against the official cleaned file, Part1 matched with a one-hour shift from April to October and no shift from November to March. Part2 matched with no shift all year, so Part2 was already in UTC.

    If I'd ignored this, every summer reading would be an hour out, and one autumn hour would be out of order.

2. **The two files overlap from 27 June to 1 October 2014,** and they don't agree there: only 20% of the timestamps they share have the same whole-house reading. The official cleaned file follows Part1 for that period.

3. **There are sensor error codes in the data.** Plug readings of 4,096, 8,192, 16,384, 32,767, 65,535 and 98,301 W are integer overflow or bit errors. A plug socket can't deliver much more than 3 kW. Some glitches are lower and harder to spot. For example, the washing machine monitor at one point reads 2,048 W while the whole house is only drawing 190 W.

4. **Part1 has a huge amount of duplication.** About a quarter of its rows repeat an earlier timestamp, and most are exact copies. Part2 has a different quirk: a single reading is split across several rows, each with some sensors filled in and the others blank.

5. **A few whole-house readings are above 15 kW,** 186 in total, up to 29 kW. That isn't strictly impossible on a 100 A supply, but this home normally peaks at around 10 to 12 kW in short bursts (a kettle or shower), so I treated them as bad readings.

---

## 3. How I cleaned House 1

Every step and its counts are logged in `outputs/raw_h1_steps.csv`.

| Step | What I did | How much it changed |
|---|---|---|
| 1. Read | Used the `Unix` column as the clock. The `Time` column is just a text copy of it. | No failures |
| 2. Fix the timezone | Converted Part1 from UK local time to UTC. For the hour that appears twice in October, I used the order of rows in the file to tell the first pass (summer time) from the second (winter time). Part2 was left alone. | 2,795,917 Part1 rows moved by an hour |
| 3. Handle the overlap | Used Part1 up to its last reading (1 Oct 2014, 00:27 UTC) and Part2 only after that. Part1 has more readings in the overlap and matches the official data. | 944,950 Part2 rows dropped |
| 4. Remove impossible values | Plug readings over 4 kW, whole-house readings over 15 kW, and negative values set to missing, not zero, so they don't look like "off". | 3,895 plug and 171 whole-house readings |
| 5. Sort and de-duplicate | Sorted by time, dropped exact duplicate rows, and merged rows sharing a timestamp by keeping the latest non-missing value in each column. This also stitches Part2's split rows back together. | 884,254 dropped, 131,831 merged |
| 6. Resample | Took the average of each UTC minute. | 920,091 minutes |
| 6b. Sanity check | An appliance can't use more than the whole house, so any appliance minute above 1.1 times the whole-house reading plus 50 W was set to missing. This catches glitches under 4 kW. | 3,821 appliance-minutes (2,498 of them on the electric heater) |
| 7a. Short gaps | Filled gaps of 5 minutes or less with the last value. A sensor skipping a report usually just means nothing changed, and 5 minutes is short next to any appliance cycle. | 812 minutes filled |
| 7b. Long gaps | Left anything longer as missing, marked it in an `outage` column and listed it in `outputs/raw_h1_outages.csv`. | 408 outages, 121,355 minutes (13.2% of the period) |

There were 384 outages between 5 minutes and an hour long, 12 between an hour and a day, and 12 longer than a day. The longest was 41.6 days (24 January to 6 March 2014), then 8.6 days in May 2015 and 7.5 days in June 2015. I didn't fill any of these. There's no honest way to make up days of appliance use, so they stay missing and later steps skip over them.

**Checking the result.** I compared my cleaned whole-house series with the official cleaned version over the 797,815 minutes where both have data:

| | Correlation with the official data | Average difference |
|---|---|---|
| Raw data as recorded | 0.768 | 89.5 W |
| After my cleaning | 0.997 | 4.4 W |

So a fairly simple pipeline gets very close to the official one. Almost all of the improvement comes from fixing the timezone and handling the overlap correctly.

The plots:

- `figures/p1_before_after_week.png` shows four days of the whole-house, washing machine and fridge readings, before and after cleaning. The fake fridge spike of about 17,000 W disappears, the fridge's normal on/off pattern becomes visible, and summer readings move by an hour.
- `figures/p1_before_after_outage.png` covers February and March 2014, with the 41-day outage left as a visible gap.
- `figures/p1_daily_coverage.png` shows, day by day, what share of minutes have a reading.

![House 1, raw vs cleaned over four days: sensor error spikes removed and summer readings shifted back by an hour](figures/p1_before_after_week.png)

![House 1, February to March 2014: the 41-day outage is left as a gap instead of being filled](figures/p1_before_after_outage.png)

My cleaning differs from the official version in two ways. I set bad plug readings to missing where the official version sets them to zero. And I didn't try to reassign monitors that householders moved between appliances, since that needs a manual review of each house and the brief says it's out of scope.

---

## 4. The cleaned data I used for the washing-machine work

**Which homes.** I used every home where the readme clearly names a washing machine. That came to 12:

| House | Washing machine channel | Notes |
|---|---|---|
| 1 | Appliance5 | This house also has a washer-dryer (Appliance4). It isn't part of the target, so it will confuse the model. |
| 2, 3, 7, 15, 16, 17, 18, 19, 21 | as listed in `src/config.py` | |
| 4 | Appliance4 plus Appliance5 | Two washing machines, so I add them together. They look the same in the whole-house signal either way. |
| 5 | Appliance3 | The model number (AEG L99695HWD) shows it's actually a washer-dryer, so its drying runs look different. |

I left out Houses 8 and 9 because their washing machine and washer-dryer channels are hard to tell apart. Houses 6, 10, 11, 12, 13 and 20 have a washing-machine channel that's missing, unlabelled or changes partway through. They could be added later after a closer look.

**Resampling.** Same idea as Part 1: the average of the readings in each UTC minute (see `src/clean_data.py`). Minutes with no readings stay missing, so outages get counted rather than filled. I only use local UK time for the hour-of-day and day-of-week analysis.

**Coverage and quality** (saved as `outputs/wm_quality.csv`):

| House | Period | Missing minutes | Gaps over 1 h | "Issues" flag | Washing machine off | Cycles | Cycles per week |
|---|---|---|---|---|---|---|---|
| 1 | Oct 2013 to Jul 2015 | 12.6% | 22 | 2.1% | 98.1% | 379 | 4.8 |
| 2 | Sep 2013 to May 2015 | 24.6% | 78 | 2.0% | 95.3% | 320 | 4.8 |
| 3 | Sep 2013 to Jun 2015 | 11.4% | 17 | 7.7% | 94.3% | 633 | 8.1 |
| 4 | Oct 2013 to Jul 2015 | 13.7% | 212 | 3.1% | 98.5% | 256 | 3.3 |
| 5 | Sep 2013 to Jul 2015 | 9.3% | 203 | 8.4% | 92.3% | 693 | 8.3 |
| 7 | Nov 2013 to Jul 2015 | 12.6% | 23 | 4.6% | 91.6% | 834 | 10.9 |
| 15 | Dec 2013 to Jul 2015 | 13.7% | 198 | 1.6% | 97.1% | 249 | 3.6 |
| 16 | Jan 2014 to Jul 2015 | 17.3% | 201 | 1.0% | 96.3% | 307 | 4.8 |
| 17 | Mar 2014 to Jun 2015 | 6.2% | 13 | 4.3% | 97.6% | 279 | 4.4 |
| 18 | Mar 2014 to May 2015 | 5.8% | 14 | 5.8% | 98.8% | 132 | 2.2 |
| 19 | Mar 2014 to Jun 2015 | 6.5% | 12 | 4.1% | 96.1% | 255 | 4.1 |
| 21 | Mar 2014 to Jul 2015 | 9.4% | 15 | 5.4% | 96.9% | 229 | 3.6 |

"Off" here means 20 W or less. In every home the washing machine is off between 92% and 99% of the time. That imbalance matters a lot when choosing how to measure the model, which I come back to in RESULTS.md.

### The dataset's "Issues" flag is biased against washing machines

The readme suggests throwing away rows where the `Issues` column is 1, which marks moments when the nine plug monitors add up to more than the whole-house reading. Before doing that, I checked when it actually fires:

| House | 1 | 2 | 3 | 4 | 5 | 7 | 15 | 16 | 17 | 18 | 19 | 21 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Flagged, out of all minutes | 2% | 2% | 8% | 3% | 8% | 5% | 2% | 1% | 4% | 6% | 4% | 5% |
| Flagged, out of minutes when the washing machine is on | 33% | 17% | 27% | 41% | 30% | 23% | 36% | 5% | 47% | 22% | 34% | 37% |
| Washing machine alone reads higher than the whole house | 5.0% | 0.4% | 4.5% | 2.8% | 4.9% | 0.9% | 1.7% | 0.2% | 2.6% | 0.4% | 1.2% | 9.0% |

The flag goes off five to ten times more often while the washing machine is running. That makes sense once you think about it. Adding up nine unsynchronised monitors during a 2 kW load means a few seconds of lag can easily push the total over the clamp reading. So following the readme's advice would quietly remove a large part of the very thing I'm trying to model.

What I did instead was keep the flagged minutes and only drop minutes where the washing machine on its own reads more than 1.1 times the whole house plus 50 W, which genuinely can't happen.

---

## 5. Things I'm still not fully comfortable with

- **Moved monitors.** I trust the readme's labels. If someone moved a monitor to a different appliance partway through, the "true" washing machine values are wrong for that stretch.
- **Back-to-back washes.** Because pauses of up to 15 minutes get bridged, two washes run one after the other can merge into one long cycle. You can see this for Houses 5 and 21 in `p2_detected_cycles.png`. It makes some cycles look longer and more energy-hungry than they are, and slightly undercounts washes.
- **Washer-dryers.** House 5's machine, and the extra one in House 1, have drying phases that don't look like a normal wash.
- **Big unlabelled loads.** Showers, ovens and immersion heaters are in the whole-house reading but never metered on their own. They're the main reason the model raises false alarms.
- **Zeros in Part1.** Before Part2, a sensor that wasn't reporting was written as 0, so in Part1 there's no way to tell "off" from "not reporting". This mostly affects the plug monitors, since the whole-house reading is almost never zero.
