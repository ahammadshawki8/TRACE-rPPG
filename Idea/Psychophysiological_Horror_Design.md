# Psychophysiological Horror Design

## Purpose

TRACE Night Signal uses camera-derived heart rate as a game input. The aim is
to alternate short arousal events with recovery windows, then record how the
estimated BPM changes. It is an interactive signal-processing demonstration,
not a method for diagnosing fear, stress, or cardiac conditions.

The audio is **BPM-synchronized**, not heartbeat-phase synchronized. The live
pipeline estimates a rate from a moving video window; it does not locate an ECG
R-peak. The game therefore schedules its synthetic double-thump every `60/BPM`
seconds but cannot claim that a speaker thump coincides with a physical beat.

## Evidence translated into game rules

### 1. Sudden onset can create a short cardiac response

An experimental acoustic-startle study reported an average heart-rate increase
of 10.8 BPM, peaking 3.4 seconds after a brief loud stimulus. TRACE uses the
onset and surprise mechanism, not the study's 110 dB laboratory intensity. All
Web Audio gains are bounded and pass through a compressor.

- Game rule: a jumpscare combines a sudden visual replacement, a short filtered
  noise burst, sub-bass fall and dissonant stereo pair.
- Source: [Effects of an auditory startle stimulus on blood pressure and heart rate in humans](https://pubmed.ncbi.nlm.nih.gov/10703886/)

### 2. Identical repeated scares lose effect

Cardiac, skin-conductance and motor components habituate at different rates
under repeated acoustic startle probes.

- Game rule: the director rotates face, hands, apparition, lighting and pursuit
  events and enforces randomized cooldowns. Relay scares are separated by a
  full level and recovery interval.
- Source: [Habituation of parasympathetic-mediated heart rate responses to recurring acoustic startle](https://pubmed.ncbi.nlm.nih.gov/25477830/)

### 3. Uncertainty sustains anticipation

Human threat experiments find larger contextual startle under unpredictable
than neutral conditions, and greater attentional engagement for unpredictable
aversive pictures than predictable ones.

- Game rule: the player knows the ward is active but does not receive a precise
  countdown. Director intervals and event types vary inside bounded ranges.
- Sources: [Startle potentiation in rapidly alternating conditions of threat predictability](https://pubmed.ncbi.nlm.nih.gov/17644240/), [Defensive motivation and attention under predictable and unpredictable threat](https://pubmed.ncbi.nlm.nih.gov/28370078/)

### 4. Darkness strengthens the threat context

Darkness increased fear-potentiated startle to an explicit threat cue in a
human experiment.

- Game rule: the flashlight creates useful visibility but also extends the
  stalker's sight range. Heartbeat waves briefly cut through the darkness.
- Source: [Effects of threat of shock, electrode placement and darkness on startle](https://pubmed.ncbi.nlm.nih.gov/9545658/)

### 5. Maximum fear is not maximum enjoyment

A haunted-house field study found an inverted-U relationship between enjoyment
and fear, and linked frightening experience to larger-scale heart-rate
fluctuations.

- Game rule: three escalating levels alternate pressure with recovery. Standard,
  Nightmare and Quiet settings keep intensity selectable.
- Source: [Playing With Fear: A Field Study in Recreational Horror](https://pubmed.ncbi.nlm.nih.gov/33137263/)

### 6. Recovery uses paced breathing without promising a BPM drop

Slow breathing near six cycles per minute consistently increases several HRV
or vagal-modulation measures. Studies do not justify promising that every user
will show an immediate lower mean heart rate.

- Game rule: Level I and II end with one 10-second cycle: four seconds inhale,
  six seconds exhale. The screen displays entry and current BPM and exports the
  recovery interval for later analysis.
- Sources: [Deep breathing randomized controlled trial](https://pubmed.ncbi.nlm.nih.gov/23029969/), [Benefits from slow and deep breathing modes](https://pubmed.ncbi.nlm.nih.gov/39050620/)

### 7. Sound tempo follows physiology

Controlled music experiments report that cardiorespiratory responses track
musical emphasis and tempo, with pauses associated with relaxation responses.

- Game rule: accepted live BPM controls double-thump spacing. Baseline-relative
  elevation shifts its pitch, drone dissonance and stalker hearing distance.
  Recovery replaces the pulse bed with a slower breathing cue.
- Source: [Dynamic Interactions Between Musical, Cardiovascular, and Cerebral Rhythms in Humans](https://www.ahajournals.org/doi/10.1161/CIRCULATIONAHA.108.806174)

## Three-level structure

1. **The Listening Ward:** one stalker, morgue relay, teaches heartbeat waves.
2. **The Blackout:** second stalker wakes, archive relay, denser uncertainty.
3. **The Choir:** faster pursuit and director cadence, final relay and extraction.

Level transitions record a full paced-breathing cycle. Exported frames include
BPM, baseline, feedback intensity, recovery flag, level, player position and
stalker state for an arousal-versus-recovery plot after the run.
