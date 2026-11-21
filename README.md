<p align="center">
  <a href="https://github.com/AethDesign/quality-code/actions/workflows/verify.yml"><img alt="Verify toolkit" src="https://github.com/AethDesign/quality-code/actions/workflows/verify.yml/badge.svg"></a>
  <a href="LICENSE"><img alt="License: MIT" src="https://img.shields.io/badge/license-MIT-222222"></a>
  <img alt="Python 3.11 or newer" src="https://img.shields.io/badge/python-3.11%2B-222222">
  <img alt="Standard version 3" src="https://img.shields.io/badge/standard-v3-222222">
  <a href="https://www.aethdesign.com/"><img alt="Built by AethDesign" src="https://img.shields.io/badge/by-AethDesign-C0C0C0"></a>
</p>

# Quality Code + Visuals by AethDesign

An open baseline for agent-assisted software work. Define what a change must do, verify it in proportion to its risk, and get an independent review where the outcome warrants one.

| Standard | What it gives a project |
| --- | --- |
| [Quality Code](docs/STANDARD.md) | Project context, acceptance criteria, behavioral checks and independent code audits |
| [Quality Visuals](docs/QUALITY_VISUALS.md) | A starting baseline for useful content, intentional composition, working interfaces and independent visual review |

## Quick start

Use Python 3.11+ and Git. The project wrapper also requires a POSIX shell.

```sh
git clone https://github.com/AethDesign/quality-code.git
cd quality-code
python3 scripts/quality_code.py adopt /path/to/project --modules code,visuals
cd /path/to/project
./quality validate
```

Use `init` in place of `adopt` for a new project. Tailor `MAP.md`, `TESTING.md`, and `.quality/quality.toml` to the product before relying on the verification commands. Run `./quality verify changed` for configured checks and follow the applicable independent review gate.

[Installation and audit walkthrough](docs/GETTING_STARTED.md) · [Download combined instructions](docs/downloads/quality-standards-by-aethdesign.zip) · [Module options](docs/MODULES.md)

## Case study: what independent review changed

Before launch, an independent reviewer found that adoption could overwrite unrelated runtime files and that mixed-path routing could hide higher-risk changes. The fixes added collision checks before writes and evaluated risk per path. The re-audit reproduced the corrections, and the regressions remain executable.

[Read the Quality Code case study](docs/CASE_STUDY.md)

Quality Visuals is a practical starting point. AethDesign’s exploratory trials have surfaced useful failure patterns, but they have yet to demonstrate a reliable improvement in design quality.

## Research and public scope

The [research index](docs/RESEARCH.md) holds the visual trials, delegation experiments, and historical Quality Swarms results. The [public edition policy](docs/PUBLIC_EDITION.md) explains what AethDesign publishes and which studio guidance it maintains separately.

[Contribute](CONTRIBUTING.md) · [Report a security issue](SECURITY.md) · [MIT license](LICENSE) · [AethDesign studio](https://www.aethdesign.com/)
