# Vanilla baseline prompt

Paste this into a fresh agent session with **no** ad-spy-kit (or any ad skill) installed,
then paste the fixture's `artifacts/screenshots/<fixture>/ads.raw.json` under it.

> Tear down this brand's Black Friday / Cyber Monday Meta ads. Tell me which ads are
> winning, what offers and hooks they use, where the gaps are, and what ads I should run
> against them. The ads export is below.

Save the reply verbatim as `evals/baseline/vanilla/<fixture>.md`. First line:
`<!-- vanilla capture: <model/agent>, <date>, no kit installed -->`.
Then run `bash evals/compare-baseline.sh`.
