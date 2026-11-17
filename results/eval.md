Model: `gemini/gemini-3.5-flash-lite`. Gold labels: single annotator, synthetic copy (see README).

| split | n | hook acc | hook kappa | cta acc | cta kappa | features exact-set |
|---|---|---|---|---|---|---|
| dev | 29 | 1.00 | 1.00 | 0.90 | 0.84 | 0.97 |
| test | 30 | 0.97 | 0.95 | 0.90 | 0.85 | 0.93 |
| all | 59 | 0.98 | 0.98 | 0.90 | 0.84 | 0.95 |

Per-class `hook` on the test split (support = gold count):

| class | support | predicted | precision | recall |
|---|---|---|---|---|
| fail_challenge | 5 | 5 | 1.00 | 1.00 |
| satisfying | 2 | 2 | 1.00 | 1.00 |
| story | 6 | 5 | 1.00 | 0.83 |
| fake_gameplay | 5 | 5 | 1.00 | 1.00 |
| other | 12 | 13 | 0.92 | 1.00 |

Per-class `cta` on the test split (support = gold count):

| class | support | predicted | precision | recall |
|---|---|---|---|---|
| install | 15 | 16 | 0.94 | 1.00 |
| play_now | 7 | 7 | 0.86 | 0.86 |
| pre_register | 2 | 2 | 1.00 | 1.00 |
| limited_offer | 2 | 0 | - | 0.00 |
| none | 4 | 5 | 0.80 | 1.00 |

Per-feature on the test split:

| feature | support | predicted | agreement | precision | recall |
|---|---|---|---|---|---|
| levels | 4 | 4 | 1.00 | 1.00 | 1.00 |
| offline | 2 | 2 | 1.00 | 1.00 | 1.00 |
| pvp | 1 | 2 | 0.97 | 0.50 | 1.00 |
| coop | 1 | 1 | 1.00 | 1.00 | 1.00 |
| rewards | 5 | 4 | 0.97 | 1.00 | 0.80 |
| customization | 2 | 2 | 1.00 | 1.00 | 1.00 |
| idle | 1 | 1 | 1.00 | 1.00 | 1.00 |
| story_choices | 2 | 2 | 1.00 | 1.00 | 1.00 |
