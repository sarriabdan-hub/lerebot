# SORT_SHEET_v5 — FULL vial-sort recording sheet (generated, seed=42)

VLA learns ONE atomic skill: "put the {color} vial in {destination}", color-
grounded in clutter. A VLM chains these to do full sorting (mismatch -> trash).
300 eps = 60 runs x 5. Fully crossed: 4 colors x 7 destinations
(L1 L3 L6 R1 R3 R6 + BIN/trash). Rack slots 2/4/5 held out -> interpolation test;
source slots 2/5 held out too. Episodes 0-indexed = lerobot episode_index.

HOW TO READ:  ep 000 | L: R* .  G  .  .  .  | R: .  C  .  .  .  .  | -> RIGHT pos 3
  6 cols/rack = slots 1..6.  . = empty.  R=red C=cyan G=dark-green.
  * = the TARGET (grasp THIS one).  '-> DEST' = where to place it.
  HOME the arm before EVERY episode. Set vials EXACTLY as shown.

PERSPECTIVE (fixed, 2026-08-05) — everything is defined from the SIDE CAMERA
image (the front RealSense, ee/align/new_rack_side.png), NOT your body:
  * LEFT rack  = the rack on the LEFT of the side image (the one BY THE BIN).
  * RIGHT rack = the rack on the RIGHT of the side image.
  * Slots 1->6 = the holes counted LEFT-TO-RIGHT in the side image, BOTH racks
    (slot 1 = leftmost hole, slot 6 = rightmost).
  The side cam FACES you: its left rack is on YOUR right if you stand behind the
  arm -> ALWAYS set up + read labels against the side-cam view, never your body.
  Recommended: tape 'L'/'R' + number the holes 1-6 on the racks to match.

==============================================================================
  PHASE A  (runs 1-30, eps 0-149)  >> EVAL pi0.5 HERE before Phase B <<
==============================================================================

RUN 01/60   "Put the cyan vial in the bin."
  ep 000 | L: .  G  .  .  R  . | R: G  .  C* .  .  . | -> BIN
  ep 001 | L: G  .  R  .  .  . | R: R  .  C* .  .  R | -> BIN
  ep 002 | L: G  .  C* .  .  . | R: G  .  .  R  .  . | -> BIN
  ep 003 | L: .  R  .  C* .  . | R: .  R  .  .  .  G | -> BIN
  ep 004 | L: G  .  R  .  .  . | R: C* .  .  R  .  R | -> BIN

RUN 02/60   "Place the red vial in position 6 of the right rack."
  ep 005 | L: G  .  .  R* .  . | R: C  .  G  .  .  . | -> RIGHT pos 6
  ep 006 | L: G  .  R* .  .  C | R: C  .  C  .  .  . | -> RIGHT pos 6
  ep 007 | L: C  .  R* .  .  C | R: G  .  .  C  .  . | -> RIGHT pos 6
  ep 008 | L: .  C  .  C  .  . | R: C  .  .  R* .  . | -> RIGHT pos 6
  ep 009 | L: C  .  .  G  .  R* | R: C  .  C  .  .  . | -> RIGHT pos 6

RUN 03/60   "Place the red vial in position 1 of the right rack."
  ep 010 | L: .  .  G  .  .  R* | R: .  .  G  .  G  . | -> RIGHT pos 1
  ep 011 | L: .  C  .  C  .  G | R: .  .  R* .  .  C | -> RIGHT pos 1
  ep 012 | L: R* .  .  .  .  C | R: .  .  .  C  .  . | -> RIGHT pos 1
  ep 013 | L: G  .  .  .  G  . | R: .  .  .  R* .  . | -> RIGHT pos 1
  ep 014 | L: R* .  .  .  C  . | R: .  .  C  .  G  . | -> RIGHT pos 1

RUN 04/60   "Place the cyan vial in position 6 of the left rack."
  ep 015 | L: .  R  .  R  .  . | R: .  .  C* .  G  . | -> LEFT pos 6
  ep 016 | L: C* .  .  .  .  . | R: G  .  G  .  .  . | -> LEFT pos 6
  ep 017 | L: C* .  .  .  .  . | R: G  .  .  R  .  R | -> LEFT pos 6
  ep 018 | L: .  .  C* .  .  . | R: .  R  .  G  .  R | -> LEFT pos 6
  ep 019 | L: .  .  .  C* .  . | R: .  G  .  .  G  . | -> LEFT pos 6

RUN 05/60   "Place the dark green vial in position 6 of the left rack."
  ep 020 | L: R  .  .  G* .  . | R: .  C  .  R  .  C | -> LEFT pos 6
  ep 021 | L: R  .  G* .  .  . | R: C  .  .  .  R  . | -> LEFT pos 6
  ep 022 | L: .  C  .  G* .  . | R: .  R  .  R  .  C | -> LEFT pos 6
  ep 023 | L: .  C  .  G* .  . | R: C  .  .  C  .  . | -> LEFT pos 6
  ep 024 | L: C  .  G* .  .  . | R: R  .  C  .  .  . | -> LEFT pos 6

RUN 06/60   "Place the dark green vial in position 3 of the left rack."
  ep 025 | L: R  .  .  .  .  C | R: C  .  .  G* .  . | -> LEFT pos 3
  ep 026 | L: .  .  .  .  .  . | R: C  .  G* .  .  C | -> LEFT pos 3
  ep 027 | L: .  .  .  .  .  G* | R: R  .  R  .  .  C | -> LEFT pos 3
  ep 028 | L: G* .  .  .  C  . | R: .  R  .  .  C  . | -> LEFT pos 3
  ep 029 | L: R  .  .  .  .  C | R: .  .  .  G* .  . | -> LEFT pos 3

RUN 07/60   "Place the red vial in position 3 of the right rack."
  ep 030 | L: C  .  .  R* .  C | R: G  .  .  .  .  . | -> RIGHT pos 3
  ep 031 | L: G  .  G  .  .  G | R: C  .  .  .  .  R* | -> RIGHT pos 3
  ep 032 | L: .  G  .  C  .  R* | R: C  .  .  .  .  C | -> RIGHT pos 3
  ep 033 | L: G  .  C  .  .  G | R: R* .  .  .  .  G | -> RIGHT pos 3
  ep 034 | L: .  G  .  .  C  . | R: C  .  .  .  .  R* | -> RIGHT pos 3

RUN 08/60   "Put the red vial in the bin."
  ep 035 | L: R* .  .  .  .  G | R: .  .  .  C  .  . | -> BIN
  ep 036 | L: .  .  R* .  .  . | R: .  .  .  C  .  C | -> BIN
  ep 037 | L: .  .  .  R* .  . | R: .  .  C  .  .  G | -> BIN
  ep 038 | L: G  .  .  G  .  . | R: R* .  .  .  G  . | -> BIN
  ep 039 | L: G  .  G  .  .  . | R: .  .  R* .  .  . | -> BIN

RUN 09/60   "Place the cyan vial in position 6 of the right rack."
  ep 040 | L: .  R  .  R  .  C* | R: G  .  G  .  .  . | -> RIGHT pos 6
  ep 041 | L: .  G  .  R  .  C* | R: G  .  .  .  .  . | -> RIGHT pos 6
  ep 042 | L: R  .  .  .  R  . | R: R  .  .  C* .  . | -> RIGHT pos 6
  ep 043 | L: R  .  .  .  R  . | R: C* .  .  .  .  . | -> RIGHT pos 6
  ep 044 | L: .  G  .  R  .  . | R: G  .  C* .  .  . | -> RIGHT pos 6

RUN 10/60   "Place the red vial in position 6 of the left rack."
  ep 045 | L: R* .  G  .  .  . | R: .  C  .  C  .  . | -> LEFT pos 6
  ep 046 | L: .  .  .  C  .  . | R: R* .  .  G  .  G | -> LEFT pos 6
  ep 047 | L: .  G  .  C  .  . | R: .  C  .  C  .  R* | -> LEFT pos 6
  ep 048 | L: R* .  G  .  .  . | R: G  .  C  .  .  G | -> LEFT pos 6
  ep 049 | L: .  .  .  R* .  . | R: .  .  C  .  C  . | -> LEFT pos 6

RUN 11/60   "Put the dark green vial in the bin."
  ep 050 | L: C  .  .  G* .  . | R: .  .  .  R  .  R | -> BIN
  ep 051 | L: .  .  R  .  C  . | R: .  C  .  G* .  . | -> BIN
  ep 052 | L: .  .  .  .  C  . | R: .  .  C  .  .  G* | -> BIN
  ep 053 | L: R  .  R  .  .  . | R: G* .  .  C  .  . | -> BIN
  ep 054 | L: .  R  .  .  .  . | R: C  .  R  .  .  G* | -> BIN

RUN 12/60   "Place the dark green vial in position 3 of the right rack."
  ep 055 | L: R  .  C  .  .  C | R: G* .  .  .  C  . | -> RIGHT pos 3
  ep 056 | L: C  .  C  .  .  G* | R: .  .  .  .  .  C | -> RIGHT pos 3
  ep 057 | L: C  .  .  G* .  . | R: C  .  .  .  .  . | -> RIGHT pos 3
  ep 058 | L: .  R  .  C  .  G* | R: C  .  .  .  .  R | -> RIGHT pos 3
  ep 059 | L: C  .  C  .  .  G* | R: C  .  .  .  R  . | -> RIGHT pos 3

RUN 13/60   "Place the red vial in position 1 of the left rack."
  ep 060 | L: .  .  .  C  .  . | R: R* .  .  .  G  . | -> LEFT pos 1
  ep 061 | L: .  .  .  .  .  G | R: R* .  .  C  .  . | -> LEFT pos 1
  ep 062 | L: .  .  G  .  C  . | R: .  .  .  R* .  G | -> LEFT pos 1
  ep 063 | L: .  .  R* .  G  . | R: .  .  .  C  .  G | -> LEFT pos 1
  ep 064 | L: .  .  G  .  G  . | R: .  .  G  .  .  R* | -> LEFT pos 1

RUN 14/60   "Place the cyan vial in position 3 of the left rack."
  ep 065 | L: R  .  .  .  .  C* | R: R  .  G  .  R  . | -> LEFT pos 3
  ep 066 | L: C* .  .  .  .  R | R: .  G  .  G  .  . | -> LEFT pos 3
  ep 067 | L: R  .  .  .  R  . | R: .  .  .  C* .  . | -> LEFT pos 3
  ep 068 | L: .  .  .  .  .  C* | R: .  .  G  .  .  G | -> LEFT pos 3
  ep 069 | L: .  .  .  .  .  R | R: .  R  .  .  .  C* | -> LEFT pos 3

RUN 15/60   "Place the cyan vial in position 3 of the right rack."
  ep 070 | L: .  G  .  R  .  G | R: C* .  .  .  G  . | -> RIGHT pos 3
  ep 071 | L: .  G  .  .  .  C* | R: R  .  .  .  G  . | -> RIGHT pos 3
  ep 072 | L: .  R  .  C* .  G | R: R  .  .  .  R  . | -> RIGHT pos 3
  ep 073 | L: C* .  G  .  R  . | R: R  .  .  .  .  R | -> RIGHT pos 3
  ep 074 | L: R  .  .  C* .  . | R: R  .  .  .  .  . | -> RIGHT pos 3

RUN 16/60   "Place the red vial in position 3 of the left rack."
  ep 075 | L: .  .  .  .  .  G | R: C  .  R* .  C  . | -> LEFT pos 3
  ep 076 | L: C  .  .  .  .  G | R: .  .  .  R* .  C | -> LEFT pos 3
  ep 077 | L: C  .  .  .  .  C | R: .  C  .  .  .  R* | -> LEFT pos 3
  ep 078 | L: G  .  .  .  C  . | R: .  .  .  R* .  G | -> LEFT pos 3
  ep 079 | L: C  .  .  .  .  R* | R: G  .  G  .  .  . | -> LEFT pos 3

RUN 17/60   "Place the dark green vial in position 1 of the right rack."
  ep 080 | L: G* .  C  .  R  . | R: .  .  C  .  C  . | -> RIGHT pos 1
  ep 081 | L: R  .  .  G* .  . | R: .  .  .  C  .  R | -> RIGHT pos 1
  ep 082 | L: .  C  .  C  .  . | R: .  .  G* .  .  . | -> RIGHT pos 1
  ep 083 | L: C  .  G* .  C  . | R: .  .  .  .  .  C | -> RIGHT pos 1
  ep 084 | L: .  .  C  .  C  . | R: .  .  G* .  .  C | -> RIGHT pos 1

RUN 18/60   "Place the cyan vial in position 1 of the right rack."
  ep 085 | L: R  .  .  .  G  . | R: .  .  .  R  .  C* | -> RIGHT pos 1
  ep 086 | L: G  .  C* .  .  R | R: .  .  .  .  .  G | -> RIGHT pos 1
  ep 087 | L: G  .  R  .  .  C* | R: .  .  .  .  G  . | -> RIGHT pos 1
  ep 088 | L: .  R  .  R  .  G | R: .  .  .  R  .  C* | -> RIGHT pos 1
  ep 089 | L: G  .  .  R  .  . | R: .  .  .  R  .  C* | -> RIGHT pos 1

RUN 19/60   "Place the dark green vial in position 6 of the right rack."
  ep 090 | L: C  .  .  R  .  C | R: C  .  G* .  .  . | -> RIGHT pos 6
  ep 091 | L: C  .  C  .  C  . | R: R  .  .  G* .  . | -> RIGHT pos 6
  ep 092 | L: C  .  C  .  .  C | R: G* .  R  .  .  . | -> RIGHT pos 6
  ep 093 | L: G* .  .  C  .  . | R: .  R  .  C  .  . | -> RIGHT pos 6
  ep 094 | L: .  C  .  .  C  . | R: .  C  .  G* .  . | -> RIGHT pos 6

RUN 20/60   "Place the dark green vial in position 1 of the left rack."
  ep 095 | L: .  .  .  G* .  R | R: .  C  .  C  .  C | -> LEFT pos 1
  ep 096 | L: .  .  .  .  .  G* | R: R  .  .  R  .  R | -> LEFT pos 1
  ep 097 | L: .  .  .  G* .  . | R: R  .  .  .  R  . | -> LEFT pos 1
  ep 098 | L: .  .  G* .  .  . | R: .  R  .  .  .  C | -> LEFT pos 1
  ep 099 | L: .  .  .  G* .  . | R: .  .  .  C  .  C | -> LEFT pos 1

RUN 21/60   "Place the cyan vial in position 1 of the left rack."
  ep 100 | L: .  .  C* .  R  . | R: .  .  .  G  .  . | -> LEFT pos 1
  ep 101 | L: .  .  C* .  R  . | R: .  R  .  .  G  . | -> LEFT pos 1
  ep 102 | L: .  .  R  .  .  R | R: R  .  .  C* .  G | -> LEFT pos 1
  ep 103 | L: .  .  G  .  R  . | R: .  .  C* .  .  . | -> LEFT pos 1
  ep 104 | L: .  .  .  C* .  R | R: .  R  .  G  .  R | -> LEFT pos 1

RUN 22/60   "Place the red vial in position 1 of the right rack."
  ep 105 | L: G  .  C  .  G  . | R: .  .  C  .  .  R* | -> RIGHT pos 1
  ep 106 | L: .  .  .  G  .  R* | R: .  .  C  .  .  . | -> RIGHT pos 1
  ep 107 | L: C  .  .  R* .  . | R: .  .  .  G  .  C | -> RIGHT pos 1
  ep 108 | L: C  .  R* .  .  . | R: .  .  .  .  .  G | -> RIGHT pos 1
  ep 109 | L: G  .  G  .  G  . | R: .  .  .  R* .  C | -> RIGHT pos 1

RUN 23/60   "Place the red vial in position 6 of the left rack."
  ep 110 | L: C  .  .  R* .  . | R: .  G  .  .  .  G | -> LEFT pos 6
  ep 111 | L: .  C  .  G  .  . | R: R* .  .  .  .  . | -> LEFT pos 6
  ep 112 | L: .  .  R* .  .  . | R: C  .  C  .  .  . | -> LEFT pos 6
  ep 113 | L: C  .  .  .  .  . | R: .  C  .  R* .  C | -> LEFT pos 6
  ep 114 | L: C  .  .  G  .  . | R: R* .  .  C  .  C | -> LEFT pos 6

RUN 24/60   "Put the red vial in the bin."
  ep 115 | L: C  .  .  .  .  . | R: R* .  C  .  .  . | -> BIN
  ep 116 | L: .  .  R* .  .  . | R: .  .  G  .  .  G | -> BIN
  ep 117 | L: G  .  .  .  .  . | R: .  C  .  .  .  R* | -> BIN
  ep 118 | L: R* .  .  .  C  . | R: .  G  .  .  .  C | -> BIN
  ep 119 | L: .  C  .  C  .  . | R: R* .  C  .  .  . | -> BIN

RUN 25/60   "Place the dark green vial in position 6 of the right rack."
  ep 120 | L: .  C  .  .  R  . | R: .  .  G* .  .  . | -> RIGHT pos 6
  ep 121 | L: .  C  .  .  C  . | R: .  R  .  G* .  . | -> RIGHT pos 6
  ep 122 | L: R  .  .  G* .  R | R: .  .  R  .  .  . | -> RIGHT pos 6
  ep 123 | L: .  .  .  C  .  . | R: C  .  G* .  .  . | -> RIGHT pos 6
  ep 124 | L: G* .  .  .  C  . | R: C  .  .  .  .  . | -> RIGHT pos 6

RUN 26/60   "Place the red vial in position 1 of the left rack."
  ep 125 | L: .  .  C  .  .  C | R: G  .  .  R* .  . | -> LEFT pos 1
  ep 126 | L: .  .  .  G  .  G | R: .  G  .  R* .  C | -> LEFT pos 1
  ep 127 | L: .  .  R* .  .  G | R: C  .  C  .  .  . | -> LEFT pos 1
  ep 128 | L: .  .  G  .  C  . | R: .  .  R* .  G  . | -> LEFT pos 1
  ep 129 | L: .  .  .  .  .  . | R: R* .  G  .  C  . | -> LEFT pos 1

RUN 27/60   "Put the cyan vial in the bin."
  ep 130 | L: .  .  .  .  R  . | R: G  .  C* .  .  . | -> BIN
  ep 131 | L: G  .  G  .  .  . | R: C* .  .  .  .  . | -> BIN
  ep 132 | L: G  .  .  .  .  G | R: .  G  .  C* .  . | -> BIN
  ep 133 | L: G  .  .  R  .  G | R: .  G  .  C* .  . | -> BIN
  ep 134 | L: G  .  .  R  .  R | R: R  .  C* .  .  . | -> BIN

RUN 28/60   "Put the dark green vial in the bin."
  ep 135 | L: .  .  .  .  .  . | R: .  C  .  G* .  C | -> BIN
  ep 136 | L: .  .  C  .  .  R | R: G* .  .  .  .  . | -> BIN
  ep 137 | L: G* .  .  C  .  . | R: .  R  .  C  .  R | -> BIN
  ep 138 | L: .  .  .  C  .  G* | R: .  R  .  .  C  . | -> BIN
  ep 139 | L: .  R  .  .  C  . | R: G* .  .  C  .  C | -> BIN

RUN 29/60   "Place the cyan vial in position 1 of the left rack."
  ep 140 | L: .  .  G  .  .  R | R: G  .  C* .  .  R | -> LEFT pos 1
  ep 141 | L: .  .  G  .  .  C* | R: R  .  R  .  G  . | -> LEFT pos 1
  ep 142 | L: .  .  C* .  G  . | R: G  .  R  .  .  . | -> LEFT pos 1
  ep 143 | L: .  .  .  G  .  C* | R: G  .  R  .  .  R | -> LEFT pos 1
  ep 144 | L: .  .  .  .  .  C* | R: G  .  R  .  .  G | -> LEFT pos 1

RUN 30/60   "Place the dark green vial in position 3 of the left rack."
  ep 145 | L: .  .  .  .  .  R | R: .  .  R  .  .  G* | -> LEFT pos 3
  ep 146 | L: .  .  .  .  R  . | R: .  .  G* .  .  C | -> LEFT pos 3
  ep 147 | L: R  .  .  .  .  G* | R: .  R  .  .  R  . | -> LEFT pos 3
  ep 148 | L: G* .  .  .  .  R | R: .  C  .  .  C  . | -> LEFT pos 3
  ep 149 | L: G* .  .  .  R  . | R: .  R  .  .  C  . | -> LEFT pos 3
==============================================================================
  PHASE B  (runs 31-60, eps 150-299)  thicken to ~10 eps/combo
==============================================================================

RUN 31/60   "Place the dark green vial in position 6 of the left rack."
  ep 150 | L: .  C  .  R  .  . | R: .  C  .  G* .  C | -> LEFT pos 6
  ep 151 | L: C  .  .  R  .  . | R: C  .  C  .  .  G* | -> LEFT pos 6
  ep 152 | L: R  .  .  G* .  . | R: R  .  C  .  .  R | -> LEFT pos 6
  ep 153 | L: .  .  .  G* .  . | R: .  R  .  C  .  C | -> LEFT pos 6
  ep 154 | L: C  .  .  C  .  . | R: .  .  .  R  .  G* | -> LEFT pos 6

RUN 32/60   "Place the red vial in position 3 of the left rack."
  ep 155 | L: .  .  .  .  .  C | R: .  G  .  R* .  C | -> LEFT pos 3
  ep 156 | L: G  .  .  .  G  . | R: .  .  R* .  C  . | -> LEFT pos 3
  ep 157 | L: .  .  .  .  .  C | R: C  .  R* .  .  . | -> LEFT pos 3
  ep 158 | L: G  .  .  .  C  . | R: .  C  .  R* .  G | -> LEFT pos 3
  ep 159 | L: .  .  .  .  .  R* | R: .  G  .  .  .  G | -> LEFT pos 3

RUN 33/60   "Place the cyan vial in position 3 of the left rack."
  ep 160 | L: R  .  .  .  .  R | R: G  .  G  .  .  C* | -> LEFT pos 3
  ep 161 | L: G  .  .  .  .  R | R: .  R  .  R  .  C* | -> LEFT pos 3
  ep 162 | L: R  .  .  .  .  G | R: R  .  .  C* .  R | -> LEFT pos 3
  ep 163 | L: .  .  .  .  G  . | R: R  .  .  C* .  R | -> LEFT pos 3
  ep 164 | L: .  .  .  .  .  . | R: .  G  .  G  .  C* | -> LEFT pos 3

RUN 34/60   "Place the red vial in position 3 of the right rack."
  ep 165 | L: .  .  G  .  .  C | R: R* .  .  .  .  . | -> RIGHT pos 3
  ep 166 | L: .  C  .  G  .  G | R: R* .  .  .  .  G | -> RIGHT pos 3
  ep 167 | L: R* .  C  .  C  . | R: G  .  .  .  .  G | -> RIGHT pos 3
  ep 168 | L: G  .  .  C  .  R* | R: G  .  .  .  .  G | -> RIGHT pos 3
  ep 169 | L: G  .  C  .  C  . | R: R* .  .  .  .  . | -> RIGHT pos 3

RUN 35/60   "Place the dark green vial in position 1 of the right rack."
  ep 170 | L: R  .  .  .  C  . | R: .  .  .  G* .  . | -> RIGHT pos 1
  ep 171 | L: C  .  C  .  .  . | R: .  .  G* .  .  . | -> RIGHT pos 1
  ep 172 | L: .  .  G* .  .  C | R: .  .  R  .  C  . | -> RIGHT pos 1
  ep 173 | L: .  C  .  .  C  . | R: .  .  G* .  .  R | -> RIGHT pos 1
  ep 174 | L: R  .  G* .  R  . | R: .  .  .  R  .  . | -> RIGHT pos 1

RUN 36/60   "Place the cyan vial in position 1 of the right rack."
  ep 175 | L: .  G  .  .  .  R | R: .  .  C* .  G  . | -> RIGHT pos 1
  ep 176 | L: G  .  .  C* .  R | R: .  .  .  .  G  . | -> RIGHT pos 1
  ep 177 | L: .  R  .  R  .  G | R: .  .  R  .  .  C* | -> RIGHT pos 1
  ep 178 | L: G  .  .  C* .  R | R: .  .  R  .  .  . | -> RIGHT pos 1
  ep 179 | L: .  G  .  .  R  . | R: .  .  .  G  .  C* | -> RIGHT pos 1

RUN 37/60   "Place the cyan vial in position 3 of the right rack."
  ep 180 | L: R  .  .  G  .  G | R: C* .  .  .  G  . | -> RIGHT pos 3
  ep 181 | L: .  .  .  C* .  R | R: .  .  .  .  R  . | -> RIGHT pos 3
  ep 182 | L: G  .  R  .  G  . | R: .  .  .  .  .  C* | -> RIGHT pos 3
  ep 183 | L: .  G  .  C* .  . | R: G  .  .  .  .  . | -> RIGHT pos 3
  ep 184 | L: .  .  R  .  .  G | R: R  .  .  .  .  C* | -> RIGHT pos 3

RUN 38/60   "Place the red vial in position 6 of the right rack."
  ep 185 | L: .  .  .  C  .  G | R: .  .  R* .  .  . | -> RIGHT pos 6
  ep 186 | L: .  .  .  .  .  C | R: R* .  G  .  .  . | -> RIGHT pos 6
  ep 187 | L: G  .  R* .  G  . | R: .  .  .  .  .  . | -> RIGHT pos 6
  ep 188 | L: .  G  .  R* .  . | R: C  .  .  .  .  . | -> RIGHT pos 6
  ep 189 | L: G  .  R* .  .  G | R: C  .  G  .  .  . | -> RIGHT pos 6

RUN 39/60   "Place the cyan vial in position 6 of the right rack."
  ep 190 | L: .  G  .  R  .  C* | R: .  .  G  .  .  . | -> RIGHT pos 6
  ep 191 | L: .  G  .  .  G  . | R: .  .  C* .  .  . | -> RIGHT pos 6
  ep 192 | L: C* .  .  R  .  G | R: R  .  .  R  .  . | -> RIGHT pos 6
  ep 193 | L: R  .  .  R  .  . | R: C* .  .  G  .  . | -> RIGHT pos 6
  ep 194 | L: C* .  R  .  G  . | R: G  .  R  .  .  . | -> RIGHT pos 6

RUN 40/60   "Place the dark green vial in position 1 of the left rack."
  ep 195 | L: .  .  C  .  .  R | R: G* .  R  .  R  . | -> LEFT pos 1
  ep 196 | L: .  .  C  .  .  G* | R: .  .  R  .  R  . | -> LEFT pos 1
  ep 197 | L: .  .  .  R  .  . | R: R  .  .  C  .  G* | -> LEFT pos 1
  ep 198 | L: .  .  .  C  .  G* | R: .  R  .  R  .  C | -> LEFT pos 1
  ep 199 | L: .  .  .  R  .  R | R: R  .  .  .  .  G* | -> LEFT pos 1

RUN 41/60   "Place the dark green vial in position 3 of the right rack."
  ep 200 | L: R  .  C  .  .  . | R: .  .  .  .  .  G* | -> RIGHT pos 3
  ep 201 | L: R  .  G* .  R  . | R: .  .  .  .  .  R | -> RIGHT pos 3
  ep 202 | L: .  C  .  R  .  G* | R: C  .  .  .  R  . | -> RIGHT pos 3
  ep 203 | L: .  C  .  .  C  . | R: G* .  .  .  .  . | -> RIGHT pos 3
  ep 204 | L: R  .  .  R  .  R | R: G* .  .  .  .  . | -> RIGHT pos 3

RUN 42/60   "Place the cyan vial in position 6 of the left rack."
  ep 205 | L: G  .  C* .  .  . | R: .  G  .  G  .  R | -> LEFT pos 6
  ep 206 | L: .  R  .  C* .  . | R: G  .  G  .  G  . | -> LEFT pos 6
  ep 207 | L: R  .  R  .  .  . | R: C* .  .  R  .  . | -> LEFT pos 6
  ep 208 | L: .  .  C* .  .  . | R: .  R  .  G  .  G | -> LEFT pos 6
  ep 209 | L: .  .  C* .  .  . | R: .  .  R  .  R  . | -> LEFT pos 6

RUN 43/60   "Place the red vial in position 1 of the right rack."
  ep 210 | L: G  .  .  .  .  R* | R: .  .  G  .  G  . | -> RIGHT pos 1
  ep 211 | L: R* .  .  .  .  . | R: .  .  G  .  .  C | -> RIGHT pos 1
  ep 212 | L: .  G  .  C  .  . | R: .  .  R* .  .  C | -> RIGHT pos 1
  ep 213 | L: R* .  G  .  G  . | R: .  .  .  .  .  . | -> RIGHT pos 1
  ep 214 | L: R* .  .  .  C  . | R: .  .  G  .  .  G | -> RIGHT pos 1

RUN 44/60   "Place the cyan vial in position 6 of the left rack."
  ep 215 | L: C* .  .  .  .  . | R: .  .  G  .  .  R | -> LEFT pos 6
  ep 216 | L: R  .  .  R  .  . | R: R  .  .  G  .  C* | -> LEFT pos 6
  ep 217 | L: .  R  .  .  .  . | R: .  R  .  .  .  C* | -> LEFT pos 6
  ep 218 | L: G  .  .  R  .  . | R: .  .  .  C* .  R | -> LEFT pos 6
  ep 219 | L: G  .  .  C* .  . | R: R  .  .  R  .  R | -> LEFT pos 6

RUN 45/60   "Place the cyan vial in position 3 of the right rack."
  ep 220 | L: R  .  C* .  R  . | R: G  .  .  .  .  G | -> RIGHT pos 3
  ep 221 | L: .  R  .  R  .  C* | R: G  .  .  .  .  R | -> RIGHT pos 3
  ep 222 | L: .  R  .  G  .  G | R: C* .  .  .  .  G | -> RIGHT pos 3
  ep 223 | L: G  .  .  G  .  C* | R: .  .  .  .  .  . | -> RIGHT pos 3
  ep 224 | L: C* .  .  .  R  . | R: R  .  .  .  .  . | -> RIGHT pos 3

RUN 46/60   "Put the dark green vial in the bin."
  ep 225 | L: .  .  .  .  R  . | R: R  .  G* .  C  . | -> BIN
  ep 226 | L: .  .  .  G* .  C | R: R  .  .  C  .  C | -> BIN
  ep 227 | L: .  .  .  R  .  C | R: R  .  G* .  .  R | -> BIN
  ep 228 | L: .  C  .  .  C  . | R: .  .  .  .  .  G* | -> BIN
  ep 229 | L: R  .  R  .  C  . | R: .  .  G* .  .  C | -> BIN

RUN 47/60   "Place the cyan vial in position 6 of the right rack."
  ep 230 | L: G  .  C* .  R  . | R: G  .  .  R  .  . | -> RIGHT pos 6
  ep 231 | L: R  .  .  .  .  R | R: R  .  C* .  .  . | -> RIGHT pos 6
  ep 232 | L: C* .  .  R  .  . | R: .  .  G  .  .  . | -> RIGHT pos 6
  ep 233 | L: R  .  C* .  G  . | R: R  .  .  R  .  . | -> RIGHT pos 6
  ep 234 | L: R  .  .  .  .  G | R: .  .  .  C* .  . | -> RIGHT pos 6

RUN 48/60   "Place the dark green vial in position 1 of the left rack."
  ep 235 | L: .  .  R  .  .  G* | R: C  .  C  .  C  . | -> LEFT pos 1
  ep 236 | L: .  .  .  G* .  R | R: .  C  .  .  .  C | -> LEFT pos 1
  ep 237 | L: .  .  C  .  .  C | R: C  .  .  G* .  . | -> LEFT pos 1
  ep 238 | L: .  .  G* .  R  . | R: C  .  C  .  .  . | -> LEFT pos 1
  ep 239 | L: .  .  G* .  .  C | R: .  C  .  .  .  . | -> LEFT pos 1

RUN 49/60   "Place the dark green vial in position 6 of the left rack."
  ep 240 | L: .  .  .  R  .  . | R: .  C  .  C  .  G* | -> LEFT pos 6
  ep 241 | L: .  R  .  R  .  . | R: G* .  C  .  C  . | -> LEFT pos 6
  ep 242 | L: .  .  G* .  .  . | R: C  .  C  .  .  C | -> LEFT pos 6
  ep 243 | L: .  R  .  C  .  . | R: .  .  C  .  .  G* | -> LEFT pos 6
  ep 244 | L: R  .  C  .  .  . | R: .  .  .  G* .  . | -> LEFT pos 6

RUN 50/60   "Place the red vial in position 6 of the right rack."
  ep 245 | L: .  .  G  .  .  R* | R: .  .  .  G  .  . | -> RIGHT pos 6
  ep 246 | L: .  .  .  .  .  C | R: G  .  R* .  .  . | -> RIGHT pos 6
  ep 247 | L: G  .  R* .  C  . | R: .  .  .  G  .  . | -> RIGHT pos 6
  ep 248 | L: R* .  .  C  .  C | R: .  .  C  .  .  . | -> RIGHT pos 6
  ep 249 | L: G  .  .  .  C  . | R: G  .  R* .  .  . | -> RIGHT pos 6

RUN 51/60   "Place the red vial in position 6 of the left rack."
  ep 250 | L: .  .  R* .  .  . | R: G  .  G  .  .  G | -> LEFT pos 6
  ep 251 | L: .  G  .  G  .  . | R: R* .  .  C  .  C | -> LEFT pos 6
  ep 252 | L: R* .  G  .  .  . | R: C  .  G  .  .  . | -> LEFT pos 6
  ep 253 | L: .  .  .  C  .  . | R: .  .  .  R* .  C | -> LEFT pos 6
  ep 254 | L: .  G  .  G  .  . | R: R* .  .  G  .  . | -> LEFT pos 6

RUN 52/60   "Place the red vial in position 1 of the left rack."
  ep 255 | L: .  .  .  R* .  G | R: .  C  .  .  G  . | -> LEFT pos 1
  ep 256 | L: .  .  G  .  .  . | R: R* .  .  C  .  . | -> LEFT pos 1
  ep 257 | L: .  .  .  .  .  R* | R: C  .  .  C  .  . | -> LEFT pos 1
  ep 258 | L: .  .  G  .  G  . | R: .  .  R* .  G  . | -> LEFT pos 1
  ep 259 | L: .  .  R* .  G  . | R: G  .  .  G  .  . | -> LEFT pos 1

RUN 53/60   "Place the red vial in position 3 of the left rack."
  ep 260 | L: G  .  .  .  .  C | R: .  C  .  .  .  R* | -> LEFT pos 3
  ep 261 | L: G  .  .  .  G  . | R: G  .  C  .  .  R* | -> LEFT pos 3
  ep 262 | L: G  .  .  .  .  G | R: R* .  C  .  C  . | -> LEFT pos 3
  ep 263 | L: C  .  .  .  .  C | R: .  G  .  G  .  R* | -> LEFT pos 3
  ep 264 | L: G  .  .  .  G  . | R: .  C  .  R* .  G | -> LEFT pos 3

RUN 54/60   "Place the dark green vial in position 3 of the right rack."
  ep 265 | L: .  R  .  R  .  . | R: R  .  .  .  .  G* | -> RIGHT pos 3
  ep 266 | L: C  .  .  .  .  . | R: G* .  .  .  R  . | -> RIGHT pos 3
  ep 267 | L: R  .  G* .  R  . | R: R  .  .  .  .  C | -> RIGHT pos 3
  ep 268 | L: R  .  C  .  .  R | R: G* .  .  .  C  . | -> RIGHT pos 3
  ep 269 | L: .  R  .  .  .  G* | R: R  .  .  .  C  . | -> RIGHT pos 3

RUN 55/60   "Place the dark green vial in position 1 of the right rack."
  ep 270 | L: G* .  .  C  .  R | R: .  .  .  .  C  . | -> RIGHT pos 1
  ep 271 | L: .  R  .  R  .  G* | R: .  .  .  .  C  . | -> RIGHT pos 1
  ep 272 | L: .  C  .  .  C  . | R: .  .  G* .  .  . | -> RIGHT pos 1
  ep 273 | L: G* .  C  .  C  . | R: .  .  .  R  .  R | -> RIGHT pos 1
  ep 274 | L: G* .  .  .  R  . | R: .  .  .  R  .  C | -> RIGHT pos 1

RUN 56/60   "Put the cyan vial in the bin."
  ep 275 | L: .  R  .  G  .  . | R: R  .  .  .  .  C* | -> BIN
  ep 276 | L: R  .  .  C* .  . | R: .  .  G  .  G  . | -> BIN
  ep 277 | L: .  G  .  C* .  R | R: R  .  .  R  .  . | -> BIN
  ep 278 | L: R  .  C* .  G  . | R: .  .  R  .  .  . | -> BIN
  ep 279 | L: .  G  .  C* .  G | R: .  R  .  .  .  . | -> BIN

RUN 57/60   "Put the red vial in the bin."
  ep 280 | L: .  .  C  .  C  . | R: G  .  C  .  .  R* | -> BIN
  ep 281 | L: .  .  .  C  .  R* | R: .  G  .  .  .  C | -> BIN
  ep 282 | L: .  C  .  R* .  G | R: .  .  .  .  .  C | -> BIN
  ep 283 | L: C  .  .  R* .  . | R: .  .  .  G  .  . | -> BIN
  ep 284 | L: .  .  R* .  C  . | R: .  .  C  .  .  . | -> BIN

RUN 58/60   "Place the cyan vial in position 3 of the left rack."
  ep 285 | L: R  .  .  .  .  C* | R: .  .  R  .  R  . | -> LEFT pos 3
  ep 286 | L: G  .  .  .  .  G | R: R  .  C* .  .  R | -> LEFT pos 3
  ep 287 | L: R  .  .  .  G  . | R: .  G  .  C* .  G | -> LEFT pos 3
  ep 288 | L: G  .  .  .  .  G | R: .  G  .  R  .  C* | -> LEFT pos 3
  ep 289 | L: R  .  .  .  .  R | R: G  .  .  C* .  . | -> LEFT pos 3

RUN 59/60   "Place the cyan vial in position 1 of the right rack."
  ep 290 | L: C* .  .  .  G  . | R: .  .  R  .  .  . | -> RIGHT pos 1
  ep 291 | L: .  R  .  G  .  R | R: .  .  R  .  .  C* | -> RIGHT pos 1
  ep 292 | L: .  G  .  .  G  . | R: .  .  C* .  .  R | -> RIGHT pos 1
  ep 293 | L: G  .  C* .  .  G | R: .  .  .  .  .  R | -> RIGHT pos 1
  ep 294 | L: G  .  .  .  .  C* | R: .  .  .  G  .  G | -> RIGHT pos 1

RUN 60/60   "Place the dark green vial in position 3 of the left rack."
  ep 295 | L: R  .  .  .  .  . | R: G* .  R  .  R  . | -> LEFT pos 3
  ep 296 | L: R  .  .  .  .  . | R: .  C  .  G* .  . | -> LEFT pos 3
  ep 297 | L: G* .  .  .  C  . | R: .  R  .  .  R  . | -> LEFT pos 3
  ep 298 | L: .  .  .  .  .  G* | R: R  .  C  .  .  C | -> LEFT pos 3
  ep 299 | L: R  .  .  .  .  G* | R: .  C  .  .  .  R | -> LEFT pos 3

==============================================================================
  TOTAL: 300 episodes, 60 runs. After each 25-ep session: audit_labels.py
==============================================================================
