# Agent-level trajectories: rule (R-clock) and LLM (H-clock)

Mode by day: C car, B bus or train, H home; `|` marks the start of the charge. Same commuters, same seed and settings in both arms. Quotes are the LLM's replies, word for word.

## NZ6_s1

### LLM switched to bus or train, rule kept driving (commuter 6; 115 such commuters)

Traits H3 F2 P3 S2; parking NZ$12.75; pays the charge; cannot work from home; bus or train 18 min, drive 5 min with no traffic.

- Rule:  `CCCCC | CCCCC   (drives at 09:45 throughout)`
- LLM:   `CCCCC | BBBBB`

- Day 6, asked (charge): **bus_or_train**, back-up if bus or train disrupted: drive; main reason other_money. "Driving still costs me about $19.25 a day with the charge, but the bus is $7 and only 13 minutes longer, so it's clearly cheaper and I'd happily switch since I don't mind buses."
- Day 6, rule woken (T2): Chose to drive at 09:45 over drive at 09:30: lowest total cost (NZ$24.04 vs NZ$27.78), mainly arrival time.

### LLM kept driving at the usual time, rule changed (commuter 7; 115 such commuters)

Traits H4 F3 P4 S3; parking NZ$0.00; pays the charge; can work from home; bus or train 31 min, drive 13 min with no traffic.

- Rule:  `CCCCC | CCCCC   (drives at 08:45, then 06:30)`
- LLM:   `CCCCC | CCCCC   (drives at 08:45 throughout)`

- Day 6, asked (charge): **keep_as_is**; main reason routine. "The charge is annoying, but driving is still cheaper and quicker than the bus once I count my time, and my routine works, so I'll keep driving the same way."
- Day 6, rule woken (T2): Chose to drive at 06:30 for the early start over drive at 08:45: lowest total cost (NZ$27.24 vs NZ$25.94), mainly the charge.

### LLM chose a mixed week (commuter 39; 35 such commuters)

Traits H3 F4 P3 S3; parking NZ$17.00; pays the charge; can work from home; bus or train 20 min, drive 6 min with no traffic.

- Rule:  `CCCCC | CCCCC   (drives at 08:15, then 06:45)`
- LLM:   `CCCCC | HHCHH   (drives at 08:15 throughout)`

- Day 6, asked (charge): **work_from_home** + keep_as_is 1 days a week; main reason flexibility. "The charge is annoying, but the bus costs more than driving and the charge together and work from home is free, so I'll just work from home most days. Since I'm flexible I'd still drive in on one day."
- Day 6, rule woken (T2): Chose to drive at 06:45 for the early start over drive at 08:15: lowest total cost (NZ$32.41 vs NZ$33.60), mainly the charge.

### LLM tried something and reviewed it (commuter 8; 122 such commuters)

Traits H4 F3 P3 S4; parking NZ$0.00; pays the charge; cannot work from home; bus or train 36 min, drive 16 min with no traffic.

- Rule:  `CCCCC | CCCCC   (drives at 08:00 throughout)`
- LLM:   `CCCCC | BBBBB`

- Day 6, asked (charge): **bus_or_train**, trial 3 days, back-up if bus or train disrupted: drive; main reason road_charge. "The bus gets me there at about the same time and costs less than driving with fuel and the new $6 charge, so I'll switch and see how it goes."
- Day 9, asked (review): **keep_as_is**, back-up if bus or train disrupted: bus_anyway; main reason other_money. "The bus has worked fine for three days, getting me there about 4 minutes early and costing $7 against over $16 to drive, so I'll stay with it."
- Day 6, rule woken (T2): Chose to drive at 08:00 over drive at 07:15: lowest total cost (NZ$24.55 vs NZ$27.08), mainly arrival time.

### Asked about lateness before the charge (commuter 57; 30 such commuters)

Traits H3 F1 P4 S5; parking NZ$0.00; pays the charge; can work from home; bus or train 24 min, drive 9 min with no traffic.

- Rule:  `CCCCC | CCCCC   (drives at 08:30 throughout)`
- LLM:   `CCCCC | BBBBB`

- Day 3, asked (late): **drive_other_time**, trial 3 days; main reason arrival_time. "I keep turning up late driving at 08:45, so I'll leave 15 minutes earlier and still drive. It costs me no extra money, I arrive before nine, and it's a small change compared with the bus or a big shift in hours."
- Day 6, asked (charge): **bus_or_train**, trial 3 days, back-up if bus or train disrupted: drive; main reason road_charge. "The new charge makes driving at my usual time cost $6 on top of fuel, so I'd rather not pay that. Changing my hours is a real hassle, so I'll take the bus, which gets me there before nine for about the same money overall."
- Day 9, asked (review): **keep_as_is**, back-up if bus or train disrupted: drive; main reason other_money. "The bus has worked fine, getting me there before nine for $7, while driving would cost nearly $11 plus a late arrival. I'll stay on the bus and not bother changing."
- Day 2, rule woken (T3): Chose to drive at 08:30 over drive at 08:45: lowest total cost (NZ$9.53 vs NZ$13.67), mainly arrival time.
- Day 6, rule woken (T2): Chose to drive at 08:30 over drive at 06:45 for the early start: lowest total cost (NZ$20.36 vs NZ$21.75), mainly arrival time.

## NZ18_s1

### LLM switched to bus or train, rule kept driving (commuter 1; 96 such commuters)

Traits H5 F1 P3 S1; parking NZ$0.00; pays the charge; cannot work from home; bus or train 26 min, drive 10 min with no traffic.

- Rule:  `CCCCC | CCCCC   (drives at 08:00 throughout)`
- LLM:   `CCCCC | BBBBB`

- Day 6, asked (charge): **bus_or_train**, back-up if bus or train disrupted: drive; main reason road_charge. "The bus gets me there at 08:26 leaving at my usual time and costs $7 instead of $23 for driving, so with no change to my hours I'll switch to it."
- Day 6, rule woken (T2): Chose to drive at 08:00 over drive at 06:45 for the early start: lowest total cost (NZ$28.04 vs NZ$28.60), mainly arrival time.

### LLM kept driving at the usual time, rule changed (commuter 19; 55 such commuters)

Traits H3 F2 P1 S4; parking NZ$12.75; pays the charge; cannot work from home; bus or train 21 min, drive 7 min with no traffic.

- Rule:  `CCCCC | CCCCC   (drives at 09:30 throughout)`
- LLM:   `CCCCC | CCCCC   (drives at 09:30 throughout)`

- Day 6, asked (charge): **keep_as_is**; main reason bus_train_preference. "I hate buses and trains, and the charge only adds $12 to a drive that already costs about $16, so I'm staying in the car for now. It stings, but I'll see how it goes."
- Day 6, rule woken (T2): Chose to drive at 09:45 over drive at 09:30: lowest total cost (NZ$40.76 vs NZ$38.51), mainly overall cost.
- Day 7, rule woken (T3): Chose to drive at 09:30 over drive at 09:45: lowest total cost (NZ$36.80 vs NZ$36.80), mainly arrival time.

### LLM chose a mixed week (commuter 20; 51 such commuters)

Traits H2 F3 P2 S3; parking NZ$17.00; pays the charge; can work from home; bus or train 26 min, drive 10 min with no traffic.

- Rule:  `CCCCC | HHHHH`
- LLM:   `CCCCC | BBCBB   (drives at 09:00 throughout)`

- Day 6, asked (charge): **bus_or_train** + keep_as_is 1 days a week, trial 3 days, back-up if bus or train disrupted: drive; main reason other_money. "Working from home costs nothing and avoids the charge, but I'd rather not rearrange my whole routine, so I'll weigh the costs: driving now costs 16+17+7.14 = about $40 a day. The bus is $7 and only 12 minutes longer, but I don't like buses. Working from home most days is far cheaper, but it's a bigger change, so I'll take the bus for the saving and keep driving on a day or two."
- Day 9, asked (review): **keep_as_is** + drive 1 days a week, back-up if bus or train disrupted: drive; main reason other_money. "The bus has worked fine, arriving early for $7 against about $37 to drive, so I'll stay on it. I'll still drive one day a week for convenience, since I'd rather not ride every day."
- Day 6, rule woken (T2): Chose to work from home over drive at 09:00: lowest total cost (NZ$43.38 vs NZ$51.95), mainly the charge.

### LLM tried something and reviewed it (commuter 8; 205 such commuters)

Traits H4 F3 P3 S4; parking NZ$0.00; pays the charge; cannot work from home; bus or train 36 min, drive 16 min with no traffic.

- Rule:  `CCCCC | BBBBB`
- LLM:   `CCCCC | BBBBB`

- Day 6, asked (charge): **bus_or_train**, trial 3 days, back-up if bus or train disrupted: drive; main reason road_charge. "Paying $18 on top of fuel to drive isn't worth it when the bus gets me there at 08:26 for $7, and it's barely any longer. I'll switch to the bus and see how it goes."
- Day 9, asked (review): **keep_as_is**, back-up if bus or train disrupted: bus_anyway; main reason other_money. "The bus has worked fine for three days, getting me in just before 08:30 for $7, while driving would cost over $22 and have me arriving over an hour early. I'm staying on the bus and I'm settled on it."
- Day 6, rule woken (T2): Chose to take PT over drive at 08:00: lowest total cost (NZ$33.82 vs NZ$45.55), mainly the charge.

### Asked about lateness before the charge (commuter 57; 30 such commuters)

Traits H3 F1 P4 S5; parking NZ$0.00; pays the charge; can work from home; bus or train 24 min, drive 9 min with no traffic.

- Rule:  `CCCCC | BBBBB`
- LLM:   `CCCCC | BBBBB`

- Day 3, asked (late): **drive_other_time**, trial 3 days; main reason arrival_time. "I keep turning up late driving at 08:45, so I'll leave 15 minutes earlier and still drive. It costs me no extra money, I arrive before nine, and it's a small change compared with the bus or a big shift in hours."
- Day 6, asked (charge): **bus_or_train**, back-up if bus or train disrupted: work_from_home; main reason road_charge. "The driving charge is too steep, so I'll take the bus. It gets me in at 08:54 for $7 with no change to my hours, and that's far easier than driving at a strange time or working an early day."
- Day 2, rule woken (T3): Chose to drive at 08:30 over drive at 08:45: lowest total cost (NZ$9.53 vs NZ$13.67), mainly arrival time.
- Day 6, rule woken (T2;T6): Chose to take PT over drive at 06:45 for the early start: lowest total cost (NZ$23.73 vs NZ$37.25), mainly the charge.

## NZ6_s1_disrupted

### LLM switched to bus or train, rule kept driving (commuter 10; 76 such commuters)

Traits H2 F4 P3 S3; parking NZ$0.00; pays the charge; cannot work from home; bus or train 39 min, drive 18 min with no traffic.

- Rule:  `CCCCC | CCCCC   (drives at 07:00 throughout)`
- LLM:   `CCCCC | BBBBB`

- Day 6, asked (charge): **bus_or_train**, back-up if bus or train disrupted: drive; main reason other_money. "Driving now costs about $17.88 a day with the charge, but the bus is only $7 and gets me there about the same time, 1 minute early, so I'll switch to the bus or train."
- Day 6, rule woken (T2): Chose to drive at 07:00 over drive at 06:45: lowest total cost (NZ$25.43 vs NZ$27.37), mainly arrival time.

### LLM kept driving at the usual time, rule changed (commuter 7; 116 such commuters)

Traits H4 F3 P4 S3; parking NZ$0.00; pays the charge; can work from home; bus or train 31 min, drive 13 min with no traffic.

- Rule:  `CCCCC | CCCCC   (drives at 08:45, then 06:30)`
- LLM:   `CCCCC | CCCCC   (drives at 08:45 throughout)`

- Day 6, asked (charge): **keep_as_is**; main reason routine. "The charge is annoying, but driving is still cheaper and quicker than the bus once I count my time, and my routine works, so I'll keep driving the same way."
- Day 6, rule woken (T2): Chose to drive at 06:30 for the early start over drive at 08:45: lowest total cost (NZ$27.24 vs NZ$25.94), mainly the charge.

### LLM chose a mixed week (commuter 6; 102 such commuters)

Traits H3 F2 P3 S2; parking NZ$12.75; pays the charge; cannot work from home; bus or train 18 min, drive 5 min with no traffic.

- Rule:  `CCCCC | CCCCC   (drives at 09:45 throughout)`
- LLM:   `CCCCC | BBCBB   (drives at 09:45 throughout)`

- Day 6, asked (charge): **bus_or_train**, back-up if bus or train disrupted: drive; main reason other_money. "Driving still costs me about $19.25 a day with the charge, but the bus is $7 and only 13 minutes longer, so it's clearly cheaper and I'd happily switch since I don't mind buses."
- Day 8: bus or train disrupted; the commuter's own back-up applied (drive), no LLM call.
- Day 6, rule woken (T2): Chose to drive at 09:45 over drive at 09:30: lowest total cost (NZ$24.04 vs NZ$27.78), mainly arrival time.

### LLM tried something and reviewed it (commuter 8; 128 such commuters)

Traits H4 F3 P3 S4; parking NZ$0.00; pays the charge; cannot work from home; bus or train 36 min, drive 16 min with no traffic.

- Rule:  `CCCCC | CCCCC   (drives at 08:00 throughout)`
- LLM:   `CCCCC | BBCBB   (drives at 08:00 throughout)`

- Day 6, asked (charge): **bus_or_train**, trial 3 days, back-up if bus or train disrupted: drive; main reason road_charge. "The bus gets me there at about the same time and costs less than driving with fuel and the new $6 charge, so I'll switch and see how it goes."
- Day 9, asked (review): **keep_as_is**, back-up if bus or train disrupted: drive; main reason other_money. "The bus gets me in about 4 minutes early for $7, while driving costs over $16 with fuel and the charge and only gets me there 1 minute early, so I'll stay on the bus. If it's disrupted I'll drive since I have to be there on time."
- Day 8: bus or train disrupted; the commuter's own back-up applied (drive), no LLM call.
- Day 6, rule woken (T2): Chose to drive at 08:00 over drive at 07:15: lowest total cost (NZ$24.68 vs NZ$27.11), mainly arrival time.

### Asked about lateness before the charge (commuter 57; 31 such commuters)

Traits H3 F1 P4 S5; parking NZ$0.00; pays the charge; can work from home; bus or train 24 min, drive 9 min with no traffic.

- Rule:  `CCCCC | CCCCC   (drives at 08:30 throughout)`
- LLM:   `CCCCC | BBBBB`

- Day 3, asked (late): **drive_other_time**, trial 3 days; main reason arrival_time. "I keep turning up late driving at 08:45, so I'll leave 15 minutes earlier and still drive. It costs me no extra money, I arrive before nine, and it's a small change compared with the bus or a big shift in hours."
- Day 6, asked (charge): **bus_or_train**, trial 3 days, back-up if bus or train disrupted: drive; main reason road_charge. "The new charge makes driving at my usual time cost $6 on top of fuel, so I'd rather not pay that. Changing my hours is a real hassle, so I'll take the bus, which gets me there before nine for about the same money overall."
- Day 9, asked (review): **keep_as_is**, back-up if bus or train disrupted: drive; main reason other_money. "The bus has worked fine, getting me there before nine for $7, while driving would cost nearly $11 plus a late arrival. I'll stay on the bus and not bother changing."
- Day 2, rule woken (T3): Chose to drive at 08:30 over drive at 08:45: lowest total cost (NZ$9.53 vs NZ$13.67), mainly arrival time.
- Day 6, rule woken (T2): Chose to drive at 08:30 over drive at 06:45 for the early start: lowest total cost (NZ$20.36 vs NZ$21.75), mainly arrival time.

### Bus or train disrupted, one-day question (commuter 16; 44 such commuters)

Traits H1 F1 P4 S4; parking NZ$17.00; pays the charge; can work from home; bus or train 36 min, drive 16 min with no traffic.

- Rule:  `BBBBB | BBBBB`
- LLM:   `BBBBB | BBBBB`

- Day 3, asked (today: disruption): **bus_or_train**; main reason other_money. "The bus is slow today, but I'd still arrive just before 09:45 for only $7, whereas driving costs about $27 and working from home or leaving at 06:30 means disrupting my day. I'll stick with the bus."
- Day 8, asked (today: disruption): **bus_or_train**; main reason other_money. "The bus would take over an hour but I'd still get there about on time for just $7, while driving costs over $30 with the charge. Working from home would be free, but rearranging my day is a hassle, and the bus worked on the last disrupted day, so I'll take it again."
- Day 3, rule woken (T4): Chose to take PT over drive at 09:30: lowest total cost (NZ$31.71 vs NZ$32.41), mainly parking.
- Day 4, rule woken (T4): Chose to take PT over drive at 09:30: lowest total cost (NZ$27.02 vs NZ$32.42), mainly parking.
- Day 6, rule woken (T2): Chose to take PT over drive at 09:30: lowest total cost (NZ$27.02 vs NZ$39.41), mainly parking.
- Day 8, rule woken (T4): Chose to take PT over drive at 09:30: lowest total cost (NZ$31.71 vs NZ$37.88), mainly parking.
- Day 9, rule woken (T4): Chose to take PT over drive at 09:30: lowest total cost (NZ$27.02 vs NZ$37.44), mainly parking.

### Bus or train disrupted, own back-up used (commuter 6; 94 such commuters)

Traits H3 F2 P3 S2; parking NZ$12.75; pays the charge; cannot work from home; bus or train 18 min, drive 5 min with no traffic.

- Rule:  `CCCCC | CCCCC   (drives at 09:45 throughout)`
- LLM:   `CCCCC | BBCBB   (drives at 09:45 throughout)`

- Day 6, asked (charge): **bus_or_train**, back-up if bus or train disrupted: drive; main reason other_money. "Driving still costs me about $19.25 a day with the charge, but the bus is $7 and only 13 minutes longer, so it's clearly cheaper and I'd happily switch since I don't mind buses."
- Day 8: bus or train disrupted; the commuter's own back-up applied (drive), no LLM call.
- Day 6, rule woken (T2): Chose to drive at 09:45 over drive at 09:30: lowest total cost (NZ$24.04 vs NZ$27.78), mainly arrival time.

## NZ18_s1_disrupted

### LLM switched to bus or train, rule kept driving (commuter 1; 61 such commuters)

Traits H5 F1 P3 S1; parking NZ$0.00; pays the charge; cannot work from home; bus or train 26 min, drive 10 min with no traffic.

- Rule:  `CCCCC | CCCCC   (drives at 08:00 throughout)`
- LLM:   `CCCCC | BBBBB`

- Day 6, asked (charge): **bus_or_train**, back-up if bus or train disrupted: drive; main reason road_charge. "The bus gets me there at 08:26 leaving at my usual time and costs $7 instead of $23 for driving, so with no change to my hours I'll switch to it."
- Day 6, rule woken (T2): Chose to drive at 08:00 over drive at 06:45 for the early start: lowest total cost (NZ$28.04 vs NZ$28.60), mainly arrival time.

### LLM kept driving at the usual time, rule changed (commuter 19; 54 such commuters)

Traits H3 F2 P1 S4; parking NZ$12.75; pays the charge; cannot work from home; bus or train 21 min, drive 7 min with no traffic.

- Rule:  `CCCCC | CCCCC   (drives at 09:30 throughout)`
- LLM:   `CCCCC | CCCCC   (drives at 09:30 throughout)`

- Day 6, asked (charge): **keep_as_is**; main reason bus_train_preference. "I hate buses and trains, and the charge only adds $12 to a drive that already costs about $16, so I'm staying in the car for now. It stings, but I'll see how it goes."
- Day 6, rule woken (T2): Chose to drive at 09:45 over drive at 09:30: lowest total cost (NZ$40.76 vs NZ$38.51), mainly overall cost.
- Day 7, rule woken (T3): Chose to drive at 09:30 over drive at 09:45: lowest total cost (NZ$36.80 vs NZ$36.80), mainly arrival time.

### LLM chose a mixed week (commuter 5; 196 such commuters)

Traits H5 F2 P2 S5; parking NZ$12.75; pays the charge; cannot work from home; bus or train 26 min, drive 10 min with no traffic.

- Rule:  `CCCCC | CCCCC   (drives at 09:45 throughout)`
- LLM:   `CCCCC | BBCBB   (drives at 09:45 throughout)`

- Day 6, asked (charge): **bus_or_train**, back-up if bus or train disrupted: drive; main reason road_charge. "Driving now costs me $12.00 more on top of parking and fuel, about $29.56 a day, while the bus is $7.00 and gets me there at the same time. I don't like buses, but this is clearly better, so I'll switch."
- Day 8: bus or train disrupted; the commuter's own back-up applied (drive), no LLM call.
- Day 6, rule woken (T2): Chose to drive at 09:45 over take PT: lowest total cost (NZ$43.42 vs NZ$46.13), mainly the PT trip.

### LLM tried something and reviewed it (commuter 8; 214 such commuters)

Traits H4 F3 P3 S4; parking NZ$0.00; pays the charge; cannot work from home; bus or train 36 min, drive 16 min with no traffic.

- Rule:  `CCCCC | BBCCC   (drives at 08:00, then 07:00)`
- LLM:   `CCCCC | BBCBB   (drives at 08:00 throughout)`

- Day 6, asked (charge): **bus_or_train**, trial 3 days, back-up if bus or train disrupted: drive; main reason road_charge. "Paying $18 on top of fuel to drive isn't worth it when the bus gets me there at 08:26 for $7, and it's barely any longer. I'll switch to the bus and see how it goes."
- Day 9, asked (review): **keep_as_is**, back-up if bus or train disrupted: drive; main reason other_money. "The bus has worked fine, getting me there about 4 minutes early for $7, while driving would cost around $22 and have me arriving over an hour early. I'll stay on the bus, and if it's disrupted I'll drive in that day."
- Day 8: bus or train disrupted; the commuter's own back-up applied (drive), no LLM call.
- Day 6, rule woken (T2): Chose to take PT over drive at 08:00: lowest total cost (NZ$33.82 vs NZ$45.68), mainly the charge.
- Day 8, rule woken (T4): Chose to drive at 07:00 over take PT: lowest total cost (NZ$33.49 vs NZ$36.71), mainly the PT trip.
- Day 9, rule woken (T4): Chose to drive at 07:00 over take PT: lowest total cost (NZ$31.90 vs NZ$32.82), mainly the PT trip.

### Asked about lateness before the charge (commuter 57; 31 such commuters)

Traits H3 F1 P4 S5; parking NZ$0.00; pays the charge; can work from home; bus or train 24 min, drive 9 min with no traffic.

- Rule:  `CCCCC | BBBBB`
- LLM:   `CCCCC | BBBBB`

- Day 3, asked (late): **drive_other_time**, trial 3 days; main reason arrival_time. "I keep turning up late driving at 08:45, so I'll leave 15 minutes earlier and still drive. It costs me no extra money, I arrive before nine, and it's a small change compared with the bus or a big shift in hours."
- Day 6, asked (charge): **bus_or_train**, back-up if bus or train disrupted: work_from_home; main reason road_charge. "The driving charge is too steep, so I'll take the bus. It gets me in at 08:54 for $7 with no change to my hours, and that's far easier than driving at a strange time or working an early day."
- Day 2, rule woken (T3): Chose to drive at 08:30 over drive at 08:45: lowest total cost (NZ$9.53 vs NZ$13.67), mainly arrival time.
- Day 6, rule woken (T2;T6): Chose to take PT over drive at 06:45 for the early start: lowest total cost (NZ$23.73 vs NZ$37.25), mainly the charge.

### Bus or train disrupted, one-day question (commuter 16; 44 such commuters)

Traits H1 F1 P4 S4; parking NZ$17.00; pays the charge; can work from home; bus or train 36 min, drive 16 min with no traffic.

- Rule:  `BBBBB | BBBBB`
- LLM:   `BBBBB | BBBBB`

- Day 3, asked (today: disruption): **bus_or_train**; main reason other_money. "The bus is slow today, but I'd still arrive just before 09:45 for only $7, whereas driving costs about $27 and working from home or leaving at 06:30 means disrupting my day. I'll stick with the bus."
- Day 8, asked (today: disruption): **bus_or_train**; main reason other_money. "The bus is slower today but still gets me there before 09:45 for just $7, whereas driving would cost nearly $39 with the charge and leave me a few minutes late. I stuck with the bus on the last disrupted day too, so I'll do that again."
- Day 3, rule woken (T4): Chose to take PT over drive at 09:30: lowest total cost (NZ$31.71 vs NZ$32.41), mainly parking.
- Day 4, rule woken (T4): Chose to take PT over drive at 09:30: lowest total cost (NZ$27.02 vs NZ$32.42), mainly parking.
- Day 6, rule woken (T2): Chose to take PT over drive at 09:30: lowest total cost (NZ$27.02 vs NZ$53.41), mainly the charge.
- Day 8, rule woken (T4): Chose to take PT over drive at 09:30: lowest total cost (NZ$31.71 vs NZ$48.82), mainly parking.
- Day 9, rule woken (T4): Chose to take PT over drive at 09:30: lowest total cost (NZ$27.02 vs NZ$47.49), mainly parking.

### Bus or train disrupted, own back-up used (commuter 5; 170 such commuters)

Traits H5 F2 P2 S5; parking NZ$12.75; pays the charge; cannot work from home; bus or train 26 min, drive 10 min with no traffic.

- Rule:  `CCCCC | CCCCC   (drives at 09:45 throughout)`
- LLM:   `CCCCC | BBCBB   (drives at 09:45 throughout)`

- Day 6, asked (charge): **bus_or_train**, back-up if bus or train disrupted: drive; main reason road_charge. "Driving now costs me $12.00 more on top of parking and fuel, about $29.56 a day, while the bus is $7.00 and gets me there at the same time. I don't like buses, but this is clearly better, so I'll switch."
- Day 8: bus or train disrupted; the commuter's own back-up applied (drive), no LLM call.
- Day 6, rule woken (T2): Chose to drive at 09:45 over take PT: lowest total cost (NZ$43.42 vs NZ$46.13), mainly the PT trip.

## NZ6_s2

### LLM switched to bus or train, rule kept driving (commuter 10; 112 such commuters)

Traits H1 F5 P3 S3; parking NZ$0.00; pays the charge; cannot work from home; bus or train 31 min, drive 13 min with no traffic.

- Rule:  `CCCCC | CCCCC   (drives at 07:45, then 07:15)`
- LLM:   `CCCCC | BBBBB`

- Day 6, asked (charge): **bus_or_train**, trial 3 days, back-up if bus or train disrupted: drive; main reason road_charge. "With the new charge, driving would cost me about $14 a day against $7 on the bus, and the bus still gets me there before 08:30. I'm happy to switch and see how it goes."
- Day 9, asked (review): **keep_as_is**, back-up if bus or train disrupted: drive; main reason other_money. "The bus has worked fine for three days and gets me in 9 minutes early at about half the cost of driving, so I'll stick with it and treat it as decided."
- Day 6, rule woken (T2): Chose to drive at 07:15 over drive at 07:45: lowest total cost (NZ$16.27 vs NZ$18.77), mainly the charge.

### LLM kept driving at the usual time, rule changed (commuter 1; 127 such commuters)

Traits H3 F4 P2 S4; parking NZ$17.00; pays the charge; can work from home; bus or train 34 min, drive 15 min with no traffic.

- Rule:  `CCCCC | CCCCC   (drives at 07:30, then 07:00)`
- LLM:   `CCCCC | CCCCC   (drives at 07:30 throughout)`

- Day 6, asked (charge): **keep_as_is**; main reason routine. "The charge is only about $1.20 less if I leave 15 minutes earlier, and I'd rather not take the bus, so I'll just keep driving as I have been and pay it."
- Day 6, rule woken (T2): Chose to drive at 07:00 over drive at 07:30: lowest total cost (NZ$38.06 vs NZ$38.91), mainly the charge.

### LLM chose a mixed week (commuter 32; 29 such commuters)

Traits H5 F5 P3 S3; parking NZ$0.00; pays the charge; can work from home; bus or train 34 min, drive 15 min with no traffic.

- Rule:  `CCCCC | HHHHH`
- LLM:   `CCCCC | HHCHH   (drives at 06:30 throughout)`

- Day 6, asked (charge): **work_from_home** + keep_as_is 1 days a week, trial 3 days; main reason flexibility. "Working from home costs nothing and saves the NZ$4 charge, fuel and the trip, and my employer lets me, so I'd rather do that most days. I'll still drive in on one day a week in my usual early slot."
- Day 9, asked (review): **keep_as_is** + drive_early_day 1 days a week; main reason other_money. "Working from home is free and avoids the charge and fuel, so I'll keep doing that most days. I'll still drive in one day a week on my early 07:00 shift, which has worked fine."
- Day 6, rule woken (T2): Chose to work from home over drive at 06:30 for the early start: lowest total cost (NZ$27.60 vs NZ$27.32), mainly travel time.

### LLM tried something and reviewed it (commuter 10; 123 such commuters)

Traits H1 F5 P3 S3; parking NZ$0.00; pays the charge; cannot work from home; bus or train 31 min, drive 13 min with no traffic.

- Rule:  `CCCCC | CCCCC   (drives at 07:45, then 07:15)`
- LLM:   `CCCCC | BBBBB`

- Day 6, asked (charge): **bus_or_train**, trial 3 days, back-up if bus or train disrupted: drive; main reason road_charge. "With the new charge, driving would cost me about $14 a day against $7 on the bus, and the bus still gets me there before 08:30. I'm happy to switch and see how it goes."
- Day 9, asked (review): **keep_as_is**, back-up if bus or train disrupted: drive; main reason other_money. "The bus has worked fine for three days and gets me in 9 minutes early at about half the cost of driving, so I'll stick with it and treat it as decided."
- Day 6, rule woken (T2): Chose to drive at 07:15 over drive at 07:45: lowest total cost (NZ$16.27 vs NZ$18.77), mainly the charge.

### Asked about lateness before the charge (commuter 24; 64 such commuters)

Traits H4 F3 P1 S4; parking NZ$17.00; pays the charge; can work from home; bus or train 23 min, drive 8 min with no traffic.

- Rule:  `CCCCC | CCCCC   (drives at 07:45, then 07:00)`
- LLM:   `CCCCC | CCCCC   (drives at 07:45 throughout)`

- Day 5, asked (late): **drive_other_time**, trial 3 days; main reason arrival_time. "I keep turning up late sitting in traffic and the entry queue, and I hate buses, so I'll just leave 15 minutes earlier and still drive, getting in well before the start without changing my hours or my costs."
- Day 6, asked (charge): **keep_as_is**; main reason routine. "I'll keep driving and leave at 07:45 as I do now; the charge is only NZ$5.80 and I'm still getting in well before 08:15, and I hate buses so that's out. Changing my hours or leaving earlier is a hassle for the saving."
- Day 3, rule woken (T3;T5): Chose to drive at 07:45 over drive at 08:00: lowest total cost (NZ$27.11 vs NZ$35.22), mainly arrival time.
- Day 6, rule woken (T2;T6): Chose to drive at 07:00 over drive at 07:15: lowest total cost (NZ$34.92 vs NZ$34.60), mainly travel time.

## NZ6_s3

### LLM switched to bus or train, rule kept driving (commuter 4; 117 such commuters)

Traits H5 F4 P3 S3; parking NZ$17.00; pays the charge; cannot work from home; bus or train 20 min, drive 6 min with no traffic.

- Rule:  `CCCCC | CCCCC   (drives at 06:30 throughout)`
- LLM:   `CCCCC | BBBBB`

- Day 6, asked (charge): **bus_or_train**, trial 3 days, back-up if bus or train disrupted: drive; main reason other_money. "The bus costs $7 against $23.36 for driving with the new charge, and I'd still get in 5 minutes before my start, so I'm switching to the bus. I'll give it a few days and drive if it goes badly."
- Day 9, asked (review): **keep_as_is**, back-up if bus or train disrupted: drive; main reason other_money. "The bus has worked fine for three days and I'm arriving on time, and it's $13+ cheaper than driving with the charge, so I'm sticking with it."
- Day 6, rule woken (T2): Chose to drive at 06:30 over drive at 07:00: lowest total cost (NZ$27.08 vs NZ$29.03), mainly changing routine.

### LLM kept driving at the usual time, rule changed (commuter 1; 129 such commuters)

Traits H5 F1 P4 S1; parking NZ$17.00; pays the charge; can work from home; bus or train 21 min, drive 7 min with no traffic.

- Rule:  `CCCCC | BBBBB`
- LLM:   `CCCCC | CCCCC   (drives at 09:00 throughout)`

- Day 6, asked (charge): **keep_as_is**; main reason routine. "The charge is only about six dollars and doesn't bother me much, and my drive is short and gets me in comfortably early, so I'll just keep driving as I always have."
- Day 6, rule woken (T2): Chose to take PT over drive at 09:00: lowest total cost (NZ$24.78 vs NZ$26.84), mainly parking.

### LLM chose a mixed week (commuter 3; 29 such commuters)

Traits H1 F1 P2 S3; parking NZ$17.00; pays the charge; can work from home; bus or train 20 min, drive 6 min with no traffic.

- Rule:  `CCCCC | CCCCC   (drives at 08:30 throughout)`
- LLM:   `CCCCC | HHCHH   (drives at 08:30 throughout)`

- Day 6, asked (charge): **work_from_home** + keep_as_is 1 days a week, trial 3 days; main reason flexibility. "Working from home costs nothing and avoids the charge, parking and fuel, so I'll work from home most days and drive in on one day when I need to be there."
- Day 9, asked (review): **keep_as_is** + drive 1 days a week; main reason other_money. "Working from home costs nothing and has worked fine, so I'll keep it as my main way and drive in on the one day I need to be there."
- Day 6, rule woken (T2): Chose to drive at 08:30 over drive at 08:15: lowest total cost (NZ$31.84 vs NZ$33.29), mainly arrival time.

### LLM tried something and reviewed it (commuter 3; 140 such commuters)

Traits H1 F1 P2 S3; parking NZ$17.00; pays the charge; can work from home; bus or train 20 min, drive 6 min with no traffic.

- Rule:  `CCCCC | CCCCC   (drives at 08:30 throughout)`
- LLM:   `CCCCC | HHCHH   (drives at 08:30 throughout)`

- Day 6, asked (charge): **work_from_home** + keep_as_is 1 days a week, trial 3 days; main reason flexibility. "Working from home costs nothing and avoids the charge, parking and fuel, so I'll work from home most days and drive in on one day when I need to be there."
- Day 9, asked (review): **keep_as_is** + drive 1 days a week; main reason other_money. "Working from home costs nothing and has worked fine, so I'll keep it as my main way and drive in on the one day I need to be there."
- Day 6, rule woken (T2): Chose to drive at 08:30 over drive at 08:15: lowest total cost (NZ$31.84 vs NZ$33.29), mainly arrival time.

### Asked about lateness before the charge (commuter 38; 45 such commuters)

Traits H5 F2 P4 S5; parking NZ$0.00; pays the charge; cannot work from home; bus or train 37 min, drive 17 min with no traffic.

- Rule:  `CCCCC | BBBBB`
- LLM:   `CCBBB | BBBBB`

- Day 3, asked (late): **bus_or_train**, back-up if bus or train disrupted: drive; main reason arrival_time. "I keep turning up late driving at 08:00, and leaving earlier is a hassle, so the bus gets me there at 08:27 for $7 and saves me $11.85 in fuel. I'll switch to the bus."
- Day 2, rule woken (T3): Chose to drive at 07:45 over drive at 08:00: lowest total cost (NZ$21.24 vs NZ$22.80), mainly arrival time.
- Day 6, rule woken (T2): Chose to take PT over drive at 07:45: lowest total cost (NZ$27.41 vs NZ$30.29), mainly the charge.

## NZ18_s2

### LLM switched to bus or train, rule kept driving (commuter 53; 90 such commuters)

Traits H5 F3 P2 S2; parking NZ$12.75; pays the charge; cannot work from home; bus or train 26 min, drive 10 min with no traffic.

- Rule:  `CCCCC | CCCCC   (drives at 08:45, then 09:30)`
- LLM:   `CCCCC | BBBBB`

- Day 6, asked (charge): **bus_or_train**, trial 3 days, back-up if bus or train disrupted: drive; main reason other_money. "I'd rather not take the bus, but driving later means arriving 41 minutes late and paying $12 plus parking and fuel. The bus gets me there before 9 for $7, so I'll take it and see how it goes."
- Day 9, asked (review): **keep_as_is**, back-up if bus or train disrupted: drive; main reason other_money. "The bus has got me there before nine for $7 and driving would cost about $30 and make me 41 minutes late, so I'll stick with the bus and treat it as decided."
- Day 6, rule woken (T2;T6): Chose to drive at 09:30 over take PT: lowest total cost (NZ$43.56 vs NZ$44.88), mainly the PT trip.
- Day 7, rule woken (T3): Chose to drive at 09:30 over take PT: lowest total cost (NZ$41.16 vs NZ$46.38), mainly the PT trip.
- Day 8, rule woken (T3): Chose to drive at 09:30 over drive at 09:45: lowest total cost (NZ$40.53 vs NZ$46.36), mainly changing routine.
- Day 9, rule woken (T3): Chose to drive at 09:30 over drive at 09:45: lowest total cost (NZ$40.09 vs NZ$45.92), mainly changing routine.
- Day 10, rule woken (T3): Chose to drive at 09:30 over drive at 09:45: lowest total cost (NZ$39.78 vs NZ$45.61), mainly changing routine.

### LLM kept driving at the usual time, rule changed (commuter 2; 63 such commuters)

Traits H4 F2 P1 S4; parking NZ$0.00; pays the charge; cannot work from home; bus or train 20 min, drive 6 min with no traffic.

- Rule:  `CCCCC | CCCCC   (drives at 08:00, then 06:45)`
- LLM:   `CCCCC | CCCCC   (drives at 08:00 throughout)`

- Day 6, asked (charge): **keep_as_is**; main reason routine. "I hate buses and trains and don't want to change my hours, but $18 a day on top of fuel is a lot. Leaving at 06:45 for the $12 charge is awkward, so I'll stay put for now and see how it goes."
- Day 6, rule woken (T2): Chose to drive at 06:45 for the early start over drive at 08:00: lowest total cost (NZ$34.53 vs NZ$38.70), mainly the charge.

### LLM chose a mixed week (commuter 1; 40 such commuters)

Traits H3 F4 P2 S4; parking NZ$17.00; pays the charge; can work from home; bus or train 34 min, drive 15 min with no traffic.

- Rule:  `CCCCC | HHHHH`
- LLM:   `CCCCC | BBHBB`

- Day 6, asked (charge): **bus_or_train** + work_from_home 1 days a week, trial 3 days, back-up if bus or train disrupted: work_from_home; main reason other_money. "I won't pay more than $12 to drive, and the bus gets me there on time for $7 with no parking or fuel, though I don't love buses. Working from home would be cheapest, but I'll mostly take the bus and see how it goes."
- Day 9, asked (review): **keep_as_is** + work_from_home 1 days a week, back-up if bus or train disrupted: work_from_home; main reason other_money. "The bus has worked fine, getting me in early for $7, and driving would cost about $38 a day, so I'll stick with the bus most days and work from home once a week."
- Day 6, rule woken (T2;T6): Chose to work from home over take PT: lowest total cost (NZ$39.60 vs NZ$44.09), mainly the PT trip.

### LLM tried something and reviewed it (commuter 1; 216 such commuters)

Traits H3 F4 P2 S4; parking NZ$17.00; pays the charge; can work from home; bus or train 34 min, drive 15 min with no traffic.

- Rule:  `CCCCC | HHHHH`
- LLM:   `CCCCC | BBHBB`

- Day 6, asked (charge): **bus_or_train** + work_from_home 1 days a week, trial 3 days, back-up if bus or train disrupted: work_from_home; main reason other_money. "I won't pay more than $12 to drive, and the bus gets me there on time for $7 with no parking or fuel, though I don't love buses. Working from home would be cheapest, but I'll mostly take the bus and see how it goes."
- Day 9, asked (review): **keep_as_is** + work_from_home 1 days a week, back-up if bus or train disrupted: work_from_home; main reason other_money. "The bus has worked fine, getting me in early for $7, and driving would cost about $38 a day, so I'll stick with the bus most days and work from home once a week."
- Day 6, rule woken (T2;T6): Chose to work from home over take PT: lowest total cost (NZ$39.60 vs NZ$44.09), mainly the PT trip.

### Asked about lateness before the charge (commuter 24; 64 such commuters)

Traits H4 F3 P1 S4; parking NZ$17.00; pays the charge; can work from home; bus or train 23 min, drive 8 min with no traffic.

- Rule:  `CCCCC | HHHHH`
- LLM:   `CCCCC | HHHHH`

- Day 5, asked (late): **drive_other_time**, trial 3 days; main reason arrival_time. "I keep turning up late sitting in traffic and the entry queue, and I hate buses, so I'll just leave 15 minutes earlier and still drive, getting in well before the start without changing my hours or my costs."
- Day 6, asked (charge): **work_from_home**; main reason bus_train_preference. "I can't drive at that charge, and I hate buses, so working from home costs me nothing and spares me the bus. I'll work from home every day I can and only take the bus if I really have to."
- Day 3, rule woken (T3;T5): Chose to drive at 07:45 over drive at 08:00: lowest total cost (NZ$27.11 vs NZ$35.22), mainly arrival time.
- Day 6, rule woken (T2;T6): Chose to work from home over take PT: lowest total cost (NZ$40.30 vs NZ$55.11), mainly the PT trip.

## NZ18_s3

### LLM switched to bus or train, rule kept driving (commuter 0; 85 such commuters)

Traits H3 F5 P2 S4; parking NZ$0.00; pays the charge; cannot work from home; bus or train 20 min, drive 6 min with no traffic.

- Rule:  `CCCCC | CCCCC   (drives at 09:15, then 06:45)`
- LLM:   `CCCCC | BBBBB`

- Day 6, asked (charge): **bus_or_train**, trial 3 days, back-up if bus or train disrupted: drive; main reason road_charge. "The new charge is steep, and the bus at NZ$7 gets me there 5 minutes early without the NZ$17.20 charge, so I'll put up with it even though I'd rather not ride. Leaving an hour earlier to work 07:00 to 15:00 and drive is cheaper on the charge but wastes my time, so the bus wins."
- Day 9, asked (review): **keep_as_is**, back-up if bus or train disrupted: bus_anyway; main reason road_charge. "The bus costs me $7 and gets me there 5 minutes early, while driving would add the $17.20 charge plus fuel for only a small time saving. I'd rather not ride, but the bus is clearly cheaper, so I'm sticking with it."
- Day 3, rule woken (T5): Chose to drive at 09:15 over drive at 09:00: lowest total cost (NZ$7.58 vs NZ$5.48), mainly travel time.
- Day 6, rule woken (T2): Chose to drive at 06:45 for the early start over drive at 09:15: lowest total cost (NZ$27.87 vs NZ$30.58), mainly the charge.

### LLM kept driving at the usual time, rule changed (commuter 14; 79 such commuters)

Traits H4 F3 P3 S5; parking NZ$0.00; pays the charge; cannot work from home; no bus or train, drive 8 min with no traffic.

- Rule:  `CCCCC | CCCCC   (drives at 08:15, then 07:15)`
- LLM:   `CCCCC | CCCCC   (drives at 08:15 throughout)`

- Day 6, asked (charge): **keep_as_is**; main reason routine. "I need my vehicle for work, so I'll keep driving at my usual time; leaving an hour earlier to save $6 isn't worth the hassle and I'll just wear the charge."
- Day 6, rule woken (T2): Chose to drive at 07:15 over drive at 08:15: lowest total cost (NZ$36.56 vs NZ$43.30), mainly the charge.

### LLM chose a mixed week (commuter 9; 41 such commuters)

Traits H2 F3 P2 S3; parking NZ$17.00; pays the charge; can work from home; bus or train 29 min, drive 12 min with no traffic.

- Rule:  `CCCCC | HHHHH`
- LLM:   `CCCCC | BBHBB`

- Day 6, asked (charge): **bus_or_train** + work_from_home 1 days a week, trial 3 days, back-up if bus or train disrupted: work_from_home; main reason other_money. "With the charge, driving would cost me about $42 a day before my time, and the bus gets me there on time for $7. I don't love buses, but that gap is too big to ignore, so I'll try the bus at my usual time and work from home one day a week."
- Day 9, asked (review): **keep_as_is** + work_from_home 1 days a week, back-up if bus or train disrupted: work_from_home; main reason road_charge. "The bus has got me there on time every day for $7, and driving would still cost about $36 plus the charge with a late arrival, so I'll stay with the bus and keep working from home one day a week."
- Day 6, rule woken (T2): Chose to work from home over drive at 08:30: lowest total cost (NZ$42.51 vs NZ$55.60), mainly the charge.

### LLM tried something and reviewed it (commuter 0; 216 such commuters)

Traits H3 F5 P2 S4; parking NZ$0.00; pays the charge; cannot work from home; bus or train 20 min, drive 6 min with no traffic.

- Rule:  `CCCCC | CCCCC   (drives at 09:15, then 06:45)`
- LLM:   `CCCCC | BBBBB`

- Day 6, asked (charge): **bus_or_train**, trial 3 days, back-up if bus or train disrupted: drive; main reason road_charge. "The new charge is steep, and the bus at NZ$7 gets me there 5 minutes early without the NZ$17.20 charge, so I'll put up with it even though I'd rather not ride. Leaving an hour earlier to work 07:00 to 15:00 and drive is cheaper on the charge but wastes my time, so the bus wins."
- Day 9, asked (review): **keep_as_is**, back-up if bus or train disrupted: bus_anyway; main reason road_charge. "The bus costs me $7 and gets me there 5 minutes early, while driving would add the $17.20 charge plus fuel for only a small time saving. I'd rather not ride, but the bus is clearly cheaper, so I'm sticking with it."
- Day 3, rule woken (T5): Chose to drive at 09:15 over drive at 09:00: lowest total cost (NZ$7.58 vs NZ$5.48), mainly travel time.
- Day 6, rule woken (T2): Chose to drive at 06:45 for the early start over drive at 09:15: lowest total cost (NZ$27.87 vs NZ$30.58), mainly the charge.

### Asked about lateness before the charge (commuter 38; 45 such commuters)

Traits H5 F2 P4 S5; parking NZ$0.00; pays the charge; cannot work from home; bus or train 37 min, drive 17 min with no traffic.

- Rule:  `CCCCC | BBBBB`
- LLM:   `CCBBB | BBBBB`

- Day 3, asked (late): **bus_or_train**, back-up if bus or train disrupted: drive; main reason arrival_time. "I keep turning up late driving at 08:00, and leaving earlier is a hassle, so the bus gets me there at 08:27 for $7 and saves me $11.85 in fuel. I'll switch to the bus."
- Day 2, rule woken (T3): Chose to drive at 07:45 over drive at 08:00: lowest total cost (NZ$21.24 vs NZ$22.80), mainly arrival time.
- Day 6, rule woken (T2): Chose to take PT over drive at 07:45: lowest total cost (NZ$27.41 vs NZ$54.29), mainly the charge.

