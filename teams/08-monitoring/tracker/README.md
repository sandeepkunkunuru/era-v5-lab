# Diagnosis tracker

`build_tracker.py` makes one row per student: their diagnosis pull request, how many rows are labelled,
the medicine sheet state, and problems to fix.

```
python -I build_tracker.py --roster ~/private/roster.csv --out ~/private/tracker
python -I build_tracker.py --roster ~/private/roster.csv --out ~/private/tracker --as-of 2026-10-27T23:59+05:30
```

- **Roster:** a private CSV with columns `student,team,pack`, copied from the pack table on the CAP plan
  sheet. Keep it out of git. Do not put emails in it.
- **Output:** `tracker.csv` and `tracker.md` in `--out`. They hold student names, so keep them out of git too.
- **Matching:** the `Name:` line of the pull request, then the `Pack:` line or folder when only one student
  has that pack. Unmatched pull requests are listed at the end of `tracker.md`.
- **`--as-of`:** reads each pull request at its last commit before that time, as the graders do at each due date.
- Needs the `gh` CLI, logged in. Commit files are cached in `<out>/cache`.

| Column | Meaning |
|---|---|
| status | `on track` (at least `--target` labelled rows, default 150), `behind`, `closed`, or `no PR` |
| labelled / rows | rows with verdict clean, fix or drop / all rows in `labels.csv` |
| medicine | `missing`, `template` (unchanged copy), or its size |
| issues | folder pack differs from the roster, header lines missing, folder is not the PR author, evidence or note may hold an email or phone number, more than one open PR |
| other_prs | the student's other pull requests |

The email/phone check reports a count only. It never prints the value.
