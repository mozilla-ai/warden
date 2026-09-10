# The dashboard page

Agent gates appears in the Otari dashboard sidebar once the plugin is loaded.
The page is served by the gateway at `/plugins/agent-gates/ui/` and calls the
plugin's API with the dashboard's own session cookie, so it needs no token.

- **Overview.** Pass rate and total runs, recent runs, and the repos whose
  subscription judge gates reported the most cost.
- **Runs.** Every reviewed turn, newest first, with each gate's own outcome when
  expanded. Filtered to one session it becomes a chronological timeline: attempt
  1 failed, attempt 2 fixed it, in the order it happened. A `gave_up` marker shows
  as its own status, distinct from a failing verdict: nothing was evaluated, the
  loop just stopped retrying. "View gates YAML" shows the stored policy's current
  definition, which may differ from what the run checked against if it has since
  been edited; a repo-carried gates file has no stored definition to show.
- **Sessions, Repos, Branches.** Grouped summaries with run counts and cost
  totals, each drilling into Runs filtered to that group.
- **Gates.** The editor for stored policies, one gate at a time: add a gate to an
  existing policy or start a new one, edit or delete a gate in place. Deleting a
  policy's last gate deletes the policy. A repo's own `.otari-gates.yml` never
  appears here.

A failing or gave-up run can be **dismissed** from its detail. That acknowledges it
without changing the verdict, so it stops reading as an open problem. Dismissal is
one-way.

## Cost figures

A `subscription` judge gate runs on your existing Claude login at zero marginal
cost, but the `claude` CLI's envelope still reports what those tokens would have
cost through the API, and the plugin sums that number verbatim. Read every
`total_cost_usd` as "what this would have cost without the subscription", not as
a bill. It is `null`, not zero, on a run with nothing to report: all-mechanical
gates, or a `provider`-backend judge whose cost is metered through Otari's own
pricing instead.

## Data retention

Nothing prunes history on a schedule. Use the "Clear old records" control on the
Runs page, or the API directly:

```bash
curl -X DELETE "$OTARI_URL/api/v1/plugins/agent-gates/policy-checks/history?older_than_days=90" \
  -H "Authorization: Bearer $OTARI_MASTER_KEY"
```

History rows store the verdict and each gate's outcome, never the transcript
excerpt that produced it.
