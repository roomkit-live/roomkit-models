# RoomKit Models

A shared model catalogue, published independently of RoomKit releases. A small
static interface makes the data searchable; the same deployment serves JSON for
Python, Rust and application consumers.

**Catalogue:** https://roomkit-live.github.io/roomkit-models/

The initial scope is the chat model catalogues from RoomKit: 13 providers. It
does not claim to list every model or to verify account access. Image generation,
speech, realtime and regional deployment catalogues remain outside this first
edition. Existing RoomKit and RoomKit Code consumers still use their current
embedded catalogues; adopting this endpoint is a separate integration.

## Data ownership

- `data/catalog.json` is the maintained source. `model` preserves RoomKit's
  `ModelInfo` fields, including dated list prices and provider execution tags.
- `upstream` holds advisory metadata from models.dev, matched by **provider and
  exact model ID**. It never replaces reviewed prices, limits or runtime tags.
  Its retrieval date says when it was fetched, not when its facts were verified.
- `pricing_basis: reference` marks a legacy price taken from another seller.
  The UI labels it as a reference and excludes it from provider-price sorting;
  clients must not treat it as this offer's rate. The compatibility export
  retains the original `ModelInfo` for existing consumers, including this
  historical limitation. The full catalogue is the preferred integration API.
- `guidance` holds optional, dated recommendations with evidence and limitations.
  Initial entries have no coding evaluation. Provider descriptions remain
  attributed to models.dev and are not presented as RoomKit evaluations.

The initial RoomKit revision and per-file sources are recorded in the data.
`data/upstream-lock.json` identifies the downloaded models.dev snapshot by its
SHA-256 and the observed model IDs for each matched provider. No credentials,
project settings or conversation data are included.

## Static API

Paths are relative to the GitHub Pages project root:

| Endpoint | Contract |
| --- | --- |
| `v1/manifest.json` | Schema version, catalogue path, SHA-256, update date and count |
| `v1/catalog.json` | Providers and entries with reviewed data, upstream metadata and guidance |
| `v1/roomkit/<provider>.json` | An array of the original `ModelInfo` shape, without enrichment |

Updates to data need no RoomKit package release. Consumers should retain a
bundled fallback, check the schema, verify the downloaded catalogue against the
manifest, and replace their cached snapshot only after validation. If a
deployment changes between those two reads, retry both together. Offline or
invalid refreshes retain the last accepted snapshot. Unknown prices and
capabilities stay unknown. Do not replace a custom provider's price with another
host's rate or change an explicit user setting from this catalogue.

`v1` describes the JSON contract, not a frozen dataset. A Git revision pins the
source for reproducible builds. Runtime consumers must continue to determine
availability from the configured account, and validate execution compatibility
through their adapter; catalogue presence does not grant or prove either.

## Updating the catalogue

Edit `data/catalog.json`, retain evidence in `source`, update `updated_on`, and
run `make check build`. A push to `main` publishes a new website and API together.
Prices are USD per million tokens; `verified` retains the original verification
date until the provider's documentation is checked again.

Comparisons normalize OpenRouter/Google's cache storage premium to RoomKit's
full, disjoint cache-write charge before checking differences. The website and
daily report use the same comparison implementation. Reference-only prices
from another seller are not compared as this provider's rates.

The daily GitHub Actions job runs at **07:17 UTC**, and can also be started
manually. It compares models.dev with the current data and stores a Markdown and
JSON report as a run artifact. The run summary shows changed metadata, price and
context disagreements, unmatched IDs and new upstream text model IDs since the
reviewed inventory in `data/upstream-lock.json`. Models deliberately outside
the catalogue do not reappear as new every day. Refresh that inventory from the
same downloaded source after reviewing new IDs, retaining its hash and date.

The job has read-only repository permissions. It does not edit data, create PRs,
publish recommendations or retire a missing model. Review findings against the
provider's documentation before applying them. Upstream outages fail the job
instead of recording a successful verification. GitHub schedules are best effort
and can be disabled after repository inactivity; monitor the Actions page.

For an offline comparison against an already downloaded snapshot:

```sh
python3 scripts/upstream.py --source /path/to/api.json --report reports/upstream.md
```

## Development

Python 3.11+ and Node.js (syntax check only) are sufficient. No runtime package
installation, model account or credentials are needed to build or test.

```sh
make check
make build
make serve
```

Open `http://127.0.0.1:8765`. Site links work under a GitHub Pages project prefix
and at a domain root. `dist/` contains only public HTML, CSS, JavaScript, JSON and
license notices; the entire repository is never uploaded as the Pages artifact.

GitHub Pages must use **GitHub Actions** as its publishing source. A custom
domain, broader discovery and evidence-based coding guidance can follow without
changing the catalogue's ownership or requiring a server.

## License

MIT. See `LICENSE` and `NOTICE` for the upstream data attribution.
